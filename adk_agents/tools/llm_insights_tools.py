"""
ADK Tools for LLM Insights Generation
---------------------------------------
Architecture (two phases):

Phase 1 – SQL Execution (deterministic, no LLM):
  The LLM produces a read-only SELECT; we execute it against the DB and format
  the organisation/user data directly from the raw rows.  Dates and names come
  straight from the database – the LLM never touches them.
from adk_agents.tools import error_utils

Phase 2 – Narrative (LLM):
  Only summary, key_insights, and recommendations are written by the LLM;
  those fields carry no dates or entity names that could be hallucinated.
"""

import json
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List

from google.adk.tools.tool_context import ToolContext
from adk_agents.state_manager import (
    check_prerequisites_state,
    get_state_manager,
    update_step_progress,
)
import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _schema_ref(schema: Dict[str, Any], relationships: List[str]) -> str:
    """Compact schema + FK reference text for LLM prompts."""
    lines = ["=== DATABASE SCHEMA ==="]
    for tbl, info in schema.items():
        cols = ", ".join(
            f'{c.get("name")}({c.get("type","?")})'
            for c in info.get("columns", [])
        )
        lines.append(f'  "{tbl}"  rows:{info.get("row_count","?")}  cols:[{cols}]')
    if relationships:
        lines += ["", "=== FOREIGN KEY RELATIONSHIPS ==="]
        lines += [f"  {r}" for r in relationships]
    return "\n".join(lines)


def _get_alias(row: Dict[str, Any], targets: List[str], default: Any = "") -> Any:
    """Case-insensitive, underscore-flexible alias lookup."""
    if not row:
        return default
    
    # 1. Exact matches first
    for t in targets:
        if t in row:
            return row[t]
            
    # 2. Normalized matches
    norm_row = {k.lower().replace("_", ""): v for k, v in row.items()}
    for t in targets:
        norm_t = t.lower().replace("_", "")
        if norm_t in norm_row:
            return norm_row[norm_t]
            
    return default


async def _run_sql_async(sql: str, tool_context: ToolContext) -> List[Dict[str, Any]]:
    """Execute a read-only SELECT and return rows as dicts (timestamps → ISO str)."""
    import config
    import re
    sql = sql.strip().rstrip(";")

    # For Snowflake, match identifiers to schema capitalization
    if getattr(config, "DB_TYPE", "").lower() == "snowflake":
        import json
        schema = None
        original_sql = sql
        
        # Load schema from tool_context state first
        if hasattr(tool_context, "state") and tool_context.state.get("schema"):
            schema = tool_context.state["schema"]
        # Fall back to session state manager
        if not schema:
            try:
                from adk_agents.state_manager import get_active_session_id, get_state_manager
                session_id = getattr(tool_context, "session_id", None) or get_active_session_id()
                if session_id:
                    state = get_state_manager().load_state(session_id) or {}
                    schema = state.get("schema")
            except Exception:
                pass
        # Fall back to snapshot file
        if not schema and hasattr(config, "SNAPSHOT_ROOT"):
            import os
            db_identity = _get_db_identity()
            snapshot_root = getattr(config, "SNAPSHOT_ROOT", "snapshots")
            snapshot_dir = os.path.join(snapshot_root, db_identity)
            snapshot_path = os.path.join(snapshot_dir, "schema_snapshot.json")
            try:
                with open(snapshot_path, "r") as f:
                    schema = json.load(f).get("schema")
            except Exception as e:
                pass
        
        if schema:
            # Build a case-insensitive mapping for faster lookup
            col_map = {}  # lowercase_ident -> actual_name
            for tbl, info in schema.items():
                col_map[tbl.lower()] = tbl  # table name mapping
                for col in info.get("columns", []):
                    col_map[col["name"].lower()] = col["name"]
            
            def replace_identifiers(match):
                ident = match.group(0)
                # Skip SQL keywords
                keywords = {"SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "EXISTS", "UNION", "ORDER", "BY", "GROUP", "HAVING", "LIMIT", "OFFSET", "AS", "ON", "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "CROSS", "WITH", "CASE", "WHEN", "THEN", "ELSE", "END", "DISTINCT", "ALL"}
                if ident.upper() in keywords:
                    return ident
                # Look up in case-insensitive mapping and wrap in double quotes for Snowflake
                if ident.lower() in col_map:
                    return f'"{col_map[ident.lower()]}"'
                return ident
            
            sql = re.sub(r'\b([A-Za-z_][A-Za-z0-9_]*)\b', replace_identifiers, sql)
        else:
            print(f"   [LLM SQL] ⚠️ Schema not found for Snowflake identifier mapping", file=__import__('sys').stderr)
        
        # No longer stripping quotes; Snowflake handles them correctly if matched to schema.
        pass

    # Strict Read-Only Check
    clean_sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
    if not re.match(r"^\s*(SELECT|WITH)\b", clean_sql, re.IGNORECASE):
        raise ValueError(f"Forbidden: Only SELECT or WITH queries allowed. Got: {sql[:80]}")
    destructive = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "GRANT", "REVOKE"]
    for word in destructive:
        if re.search(fr"\b{word}\b", clean_sql, re.IGNORECASE):
            raise ValueError(f"Forbidden: Destructive keyword '{word}' detected in query.")

    db_type = getattr(config, "DB_TYPE", "").lower()
    if db_type == "postgresql":
        from .connection_tools import get_async_database_pool
        pool = await get_async_database_pool(tool_context)
        async with pool.acquire() as conn:
            try:
                await conn.execute("SET TRANSACTION READ ONLY")
                rows = await conn.fetch(sql)
                import decimal
                processed_rows = []
                for row in rows:
                    r_dict = dict(row)
                    for k, v in r_dict.items():
                        if hasattr(v, "isoformat"):
                            r_dict[k] = v.isoformat()
                        elif isinstance(v, decimal.Decimal):
                            r_dict[k] = float(v)
                    processed_rows.append(r_dict)
                return processed_rows
            except Exception as e:
                from adk_agents.tools.error_utils import log_and_raise_connection_error
                log_and_raise_connection_error("SQL execution failed in LLM insights tool", e)
    elif db_type == "snowflake":
        from .connection_tools import get_database_connection
        sync_conn = get_database_connection(tool_context)
        cursor = sync_conn.cursor()
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            import decimal
            processed_rows = []
            column_names = [desc[0] for desc in cursor.description]
            for row in rows:
                r_dict = dict(zip(column_names, row))
                for k, v in r_dict.items():
                    if hasattr(v, "isoformat"):
                        r_dict[k] = v.isoformat()
                    elif isinstance(v, decimal.Decimal):
                        r_dict[k] = float(v)
                processed_rows.append(r_dict)
            return processed_rows
        except Exception as e:
            from adk_agents.tools.error_utils import log_and_raise_connection_error
            log_and_raise_connection_error("SQL execution failed in LLM insights tool", e)
        finally:
            cursor.close()
            sync_conn.close()
    else:
        raise ValueError(f"Unsupported DB_TYPE: {db_type}")


def _llm_client_model():
    from google import genai
    api_key = config.AGENT_API_KEYS.get("insights", config.GOOGLE_API_KEY)
    if not api_key:
        raise ValueError("No API key. Set INSIGHTS_API_KEY or GOOGLE_API_KEY.")
    model = config.AGENT_MODELS.get("insights", config.ADK_MODEL)
    return genai.Client(api_key=api_key), model


def _llm_generate(client, model: str, prompt: str, attempts: int = 3) -> str:
    for i in range(attempts):
        try:
            return client.models.generate_content(model=model, contents=prompt).text.strip()
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(2 ** i)


def _extract_json(text: str) -> Any:
    """Robustly extract the first JSON object or list from a string."""
    if not text:
        return {}
    try:
        # Find first occurrence of either { or [
        start_obj = text.find('{')
        start_list = text.find('[')
        
        if start_obj == -1 and start_list == -1:
            return {}
            
        if start_obj != -1 and (start_list == -1 or start_obj < start_list):
            start = start_obj
            end = text.rfind('}')
        else:
            start = start_list
            end = text.rfind(']')
            
        if start != -1 and end != -1 and end > start:
            json_str = text[start:end+1]
            # Clean up trailing commas and other common LLM artifacts
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            return json.loads(json_str)
    except Exception:
        pass
    
    # Fallback to a wider regex search
    try:
        m = re.search(r"([\{\[].*[\}\]])", text, re.DOTALL)
        if m:
            json_str = m.group(1)
            json_str = re.sub(r',\s*}', '}', json_str)
            json_str = re.sub(r',\s*]', ']', json_str)
            return json.loads(json_str)
    except Exception:
        pass
        
    return {}


def _schema_stats(schema: Dict[str, Any], relationships: List[str]) -> Dict[str, Any]:
    by_rows = sorted(
        [{"table": t, "row_count": int(i.get("row_count", 0))}
         for t, i in schema.items() if isinstance(i.get("row_count"), (int, float))],
        key=lambda x: x["row_count"], reverse=True
    )[:5]
    rc: Dict[str, int] = {}
    for rel in relationships or []:
        for part in rel.split("→"):
            if "." in part:
                rc[part.strip().split(".")[0]] = rc.get(part.strip().split(".")[0], 0) + 1
    by_rels = sorted(
        [{"table": t, "relationship_count": c} for t, c in rc.items()],
        key=lambda x: x["relationship_count"], reverse=True
    )[:5]
    return {"top_5_tables_by_row_count": by_rows, "top_5_tables_by_relationships": by_rels}


def _get_db_identity() -> str:
    """Computes a stable identity for the current database for snapshot isolation."""
    import config
    if config.DB_TYPE.lower() == "postgresql":
        db_name = config.POSTGRESQL.get("dbname", "unknown_db") or "unknown_db"
        db_schema = getattr(config, "POSTGRESQL_SCHEMA", "public")
        return f"postgresql_{db_name}_{db_schema}"
    elif config.DB_TYPE.lower() == "snowflake":
        account = config.SNOWFLAKE.get("account", "unknown_account") or "unknown_account"
        database = config.SNOWFLAKE.get("database", "unknown_db") or "unknown_db"
        schema_name = config.SNOWFLAKE.get("schema", "PUBLIC") or "PUBLIC"
        return f"snowflake_{account}_{database}_{schema_name}"
    return f"{config.DB_TYPE}_unknown"


# ---------------------------------------------------------------------------
# Main tool
# ---------------------------------------------------------------------------

async def generate_business_insights(tool_context: ToolContext) -> dict:
    """
    Generalized Database Insight Engine.
    Discovers valuable insights based on the schema and user-provided goal.
    """
    from adk_agents.state_manager import get_active_session_id

    session_id = (
        getattr(tool_context, "session_id", None)
        or get_active_session_id()
        or str(id(tool_context.state))
    )
    state = get_state_manager().load_state(session_id) or {}

    prereq = check_prerequisites_state(state, ["tables_scanned"])
    if prereq["status"] == "error":
        return {"status": "error", "message": prereq["message"]}

    try:
        schema: Dict[str, Any] = state.get("schema", {})
        relationships: List[str] = state.get("relationships", [])
        if not schema:
            return {"status": "error", "message": "No schema found. Run scan_database_tables first."}

        client, model = _llm_client_model()
        ref = _schema_ref(schema, relationships)
        
        # User Goal from Config
        goal = getattr(config, "INSIGHTS_GOAL", "Analyze key data trends and anomalies.")
        db_type = getattr(config, "DB_TYPE", "PostgreSQL")

        # Persistent Snapshot Logic
        import os
        db_identity = _get_db_identity()
        snapshot_root = getattr(config, "SNAPSHOT_ROOT", "snapshots")
        snapshot_dir = os.path.join(snapshot_root, db_identity)
        os.makedirs(snapshot_dir, exist_ok=True)
        snapshot_path = os.path.join(snapshot_dir, "last_insights.json")

        changes = state.get("changes", [])
        no_drift = any("No changes detected" in str(c) for c in changes)
        
        if no_drift and os.path.exists(snapshot_path):
            try:
                with open(snapshot_path, 'r') as f:
                    cached_insights = json.load(f)
                    
                    # GOAL-AWARE CACHING: Only reuse if the goal hasn't changed
                    if cached_insights.get("goal") == goal:
                        state["llm_insights"] = cached_insights
                        tool_context.state["llm_insights"] = cached_insights
                        update_step_progress(tool_context, "insights")
                        print(f"   [Insights] 📦 Bypassing LLM: Re-using last insights (No DB drift & same Goal).")
                        return {"status": "success", "insights": cached_insights}
                    else:
                        print(f"   [Insights] 🔄 Goal changed from '{cached_insights.get('goal')}' to '{goal}'. Forcing fresh run.")
            except Exception:
                pass

        # ------------------------------------------------------------------
        # Discovery & Execution Loop (with Retry)
        # ------------------------------------------------------------------
        all_datasets = []
        max_retries = 3
        failed_queries = []

        for attempt in range(max_retries):
            print(f"   [Insights] 🔄 Attempt {attempt + 1}/{max_retries}...")
            
            # Stage 1: Discovery Plan
            if db_type.lower() == "snowflake":
                prompt_quote_rule = "2. Do NOT use double-quoted identifiers for tables/columns. Use plain names."
            else:
                prompt_quote_rule = "2. Use double-quoted identifiers for tables/columns."
            
            retry_context = ""
            if failed_queries:
                retry_context = f"\nNote: The following queries previously returned no data or failed. Please try different approach or different tables:\n" + "\n".join([f"- {q}" for q in failed_queries[-5:]])

            discovery_prompt = f"""You are a senior data architect for {db_type}.
Based on the database schema below and the user's business goal, identify 2-3 specific SQL queries that would provide the most value.

User Goal: {goal}
{retry_context}

Rules:
1. ONLY produce SELECT queries.
{prompt_quote_rule}
3. Use only table and column names exactly as shown in the schema below, including capitalization. Do not invent names or change their case.
4. Keep queries efficient.
5. Return a JSON object with a 'plan' array:
   [{{ "title": "Human Readable Title", "sql": "SELECT ...", "description": "Why this matters" }}]
6. If the User Goal explicitly asks for a report, metric, or query (e.g., 'top 5 users'), you MUST include a SQL query that directly fulfills this request as one of your planned queries, mapping it to the most relevant tables and columns in the actual schema.

{ref}
"""
            print(f"   [Insights] 🕵️ Discovery Phase: Generating exploration plan (Attempt {attempt + 1})...")
            plan_raw = _llm_generate(client, model, discovery_prompt)
            
            # Parse JSON Plan
            plan_data = _extract_json(plan_raw)
            if isinstance(plan_data, list):
                queries = plan_data
            elif isinstance(plan_data, dict):
                queries = plan_data.get("plan", [])
            else:
                queries = []

            if not queries:
                print(f"   [Insights] ⚠️ No plan found in LLM response. Raw: {plan_raw[:100]}...")
                continue

            # Stage 2: Execution & Filtering
            current_attempt_datasets = []
            for q_item in queries:
                title = q_item.get("title", "Insight Data")
                sql = q_item.get("sql", "")
                if not sql: continue
                
                print(f"   [Insights] 🚀 Executing: {title}...")
                try:
                    rows = await _run_sql_async(sql, tool_context)
                    if rows and len(rows) > 0:
                        current_attempt_datasets.append({
                            "title": title,
                            "description": q_item.get("description", ""),
                            "data": rows[:10]
                        })
                    else:
                        print(f"   [Insights] ℹ️  Query '{title}' returned no data. Filtering out.")
                        failed_queries.append(sql)
                except Exception as exc:
                    print(f"   [Insights] ⚠️ Failed query '{title}': {exc}")
                    failed_queries.append(sql)

            # Combine with previous successful datasets (avoid duplicates by title)
            existing_titles = {d["title"] for d in all_datasets}
            for d in current_attempt_datasets:
                if d["title"] not in existing_titles:
                    all_datasets.append(d)
                    existing_titles.add(d["title"])

            if len(all_datasets) >= 2:
                print(f"   [Insights] ✅ Found {len(all_datasets)} valid datasets. Proceeding to synthesis.")
                break
            else:
                print(f"   [Insights] ⚠️ Only {len(all_datasets)} valid datasets found. Retrying...")

        if not all_datasets:
            return {"status": "error", "message": "No data could be retrieved during discovery after retries."}
        
        datasets = all_datasets

        # ------------------------------------------------------------------
        # Stage 3: Narrative Phase
        # ------------------------------------------------------------------
        print(f"   [Insights] 📝 Narrative Phase: Synthesizing results for {len(datasets)} datasets...")
        try:
            datasets_json = json.dumps(datasets, indent=2)
        except Exception as e:
            print(f"   [Insights] ⚠️ JSON dump failed, falling back to str representation: {e}")
            datasets_json = str(datasets)
        narrative_prompt = f"""You are a data-driven business analyst.
Review the raw datasets below and produce a structured report.

Business Goal: {goal}

Output Format (JSON strictly):
{{
  "summary": "High level executive overview (4-5 lines)",
  "key_insights": ["Bullet point 1", "Bullet point 2", ...],
  "recommendations": ["Actionable item 1", ...]
}}

Data:
{datasets_json}
"""
        narrative_raw = _llm_generate(client, model, narrative_prompt)
        
        narrative = _extract_json(narrative_raw)

        insights = {
            "domain": "Dynamic Discovery",
            "goal": goal,
            "summary": narrative.get("summary", "No summary generated."),
            "datasets": datasets,
            "key_insights": narrative.get("key_insights", []),
            "recommendations": narrative.get("recommendations", []),
            "schema_stats": _schema_stats(schema, relationships),
        }

        tool_context.state["llm_insights"] = insights
        tool_context.state["insights_generated"] = True
        update_step_progress(tool_context, "insights")

        # Cache snapshot
        try:
            with open(snapshot_path, 'w') as f:
                json.dump(insights, f, indent=2)
        except: pass

        return {"status": "success", "insights": insights, "message": "Generalized insights generated."}

    except Exception as exc:
        return {"status": "error", "message": f"Insights generation failed: {exc}"}


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def format_insights_for_report(insights: dict) -> str:
    """Format the insights dict into a Markdown block with dynamic tables."""
    if not insights:
        return "No insights available."

    lines = [
        "## 🤖 AI-Powered Database Insights", "",
        f"**Goal:** {insights.get('goal', 'Dynamic Discovery')}",
        "", "### Executive Summary",
        insights.get("summary", "No summary available."), "",
    ]

    # Dynamic Datasets
    datasets = insights.get("datasets") or []
    for ds in datasets:
        title = ds.get("title", "Dataset")
        desc = ds.get("description", "")
        data = ds.get("data") or []
        
        lines += [f"### 📊 {title}", ""]
        if desc:
            lines.append(f"_{desc}_")
            lines.append("")
            
        if not data:
            lines.append("_No data found for this insight._")
            lines.append("")
            continue
            
        # Render Dynamic Markdown Table
        headers = list(data[0].keys())
        header_row = "| " + " | ".join(headers) + " |"
        sep_row = "| " + " | ".join(["---"] * len(headers)) + " |"
        lines.append(header_row)
        lines.append(sep_row)
        
        for row in data:
            val_row = "| " + " | ".join(str(row.get(h, "")) for h in headers) + " |"
            lines.append(val_row)
        lines.append("")

    if insights.get("key_insights"):
        lines += ["### Key Insights", ""]
        for i, item in enumerate(insights["key_insights"], 1):
            lines.append(f"{i}. {item}")
        lines.append("")
        
    if insights.get("recommendations"):
        lines += ["### Recommendations", ""]
        for i, item in enumerate(insights["recommendations"], 1):
            lines.append(f"{i}. {item}")

    return "\n".join(lines)


# Alias for compatibility
async def get_llm_insights(tool_context: ToolContext) -> dict:
    return await generate_business_insights(tool_context)
