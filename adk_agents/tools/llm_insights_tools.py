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
    update_step_progress_state,
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
    from .connection_tools import get_async_database_pool

    sql = sql.strip().rstrip(";")
    
    # Strict Read-Only Check
    # Disallow anything that isn't a SELECT or WITH (for CTEs)
    clean_sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE) # remove comments
    if not re.match(r"^\s*(SELECT|WITH)\b", clean_sql, re.IGNORECASE):
        raise ValueError(f"Forbidden: Only SELECT or WITH queries allowed. Got: {sql[:80]}")
        
    # Block destructive keywords even if nested
    destructive = ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "GRANT", "REVOKE"]
    for word in destructive:
        if re.search(fr"\b{word}\b", clean_sql, re.IGNORECASE):
            raise ValueError(f"Forbidden: Destructive keyword '{word}' detected in query.")

        pool = await get_async_database_pool(tool_context)
        async with pool.acquire() as conn:
            try:
                # Enforce read-only transaction if supported (PostgreSQL)
                # Snowflake handles this via permissions, but we add an extra layer here
                if getattr(config, "DB_TYPE", "").lower() == "postgresql":
                    await conn.execute("SET TRANSACTION READ ONLY")
                rows = await conn.fetch(sql)
                processed_rows = []
                for row in rows:
                    r_dict = dict(row)
                    for k, v in r_dict.items():
                        if hasattr(v, "isoformat"):
                            r_dict[k] = v.isoformat()
                    processed_rows.append(r_dict)
                return processed_rows
            except Exception as e:
                from adk_agents.tools.error_utils import log_and_raise_connection_error
                log_and_raise_connection_error("SQL execution failed in LLM insights tool", e)


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
        no_drift = any("No schema or data changes detected" in str(c) for c in changes)
        
        if no_drift and os.path.exists(snapshot_path):
            try:
                with open(snapshot_path, 'r') as f:
                    cached_insights = json.load(f)
                    
                    # GOAL-AWARE CACHING: Only reuse if the goal hasn't changed
                    if cached_insights.get("goal") == goal:
                        state["llm_insights"] = cached_insights
                        update_step_progress_state(state, "insights", session_id)
                        print(f"   [Insights] 📦 Bypassing LLM: Re-using last insights (No DB drift & same Goal).")
                        return {"status": "success", "insights": cached_insights}
                    else:
                        print(f"   [Insights] 🔄 Goal changed from '{cached_insights.get('goal')}' to '{goal}'. Forcing fresh run.")
            except Exception:
                pass

        # ------------------------------------------------------------------
        # Stage 1: Discovery Plan
        # ------------------------------------------------------------------
        discovery_prompt = f"""You are a senior data architect for {db_type}.
Based on the database schema below and the user's business goal, identify 2-3 specific SQL queries that would provide the most value.

User Goal: {goal}

Rules:
1. ONLY produce SELECT queries.
2. Use double-quoted identifiers for tables/columns.
3. Keep queries efficient.
4. Return a JSON object with a 'plan' array:
   [{{ "title": "Human Readable Title", "sql": "SELECT ...", "description": "Why this matters" }}]

{ref}
"""
        print(f"   [Insights] 🕵️ Discovery Phase: Generating exploration plan for goal: '{goal}'...")
        plan_raw = _llm_generate(client, model, discovery_prompt)
        
        # Parse JSON Plan
        try:
            m = re.search(r"\{.*\}", plan_raw, re.DOTALL)
            plan = json.loads(m.group()) if m else {}
            queries = plan.get("plan", [])
        except Exception as e:
            print(f"   [Insights] ❌ Failed to parse discovery plan: {e}")
            return {"status": "error", "message": "Failed to generate discovery plan."}

        # ------------------------------------------------------------------
        # Stage 2: Execution
        # ------------------------------------------------------------------
        datasets = []
        for q_item in queries:
            title = q_item.get("title", "Insight Data")
            sql = q_item.get("sql", "")
            if not sql: continue
            
            print(f"   [Insights] 🚀 Executing: {title}...")
            try:
                rows = await _run_sql_async(sql, tool_context)
                datasets.append({
                    "title": title,
                    "description": q_item.get("description", ""),
                    "data": rows[:10] # Limit per dataset for LLM narrative
                })
            except Exception as exc:
                print(f"   [Insights] ⚠️ Failed query '{title}': {exc}")

        if not datasets:
            return {"status": "error", "message": "No data could be retrieved during discovery."}

        # ------------------------------------------------------------------
        # Stage 3: Narrative Narrative
        # ------------------------------------------------------------------
        datasets_json = json.dumps(datasets, indent=2)
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
        print("   [Insights] 📝 Narrative Phase: Synthesizing results...")
        narrative_raw = _llm_generate(client, model, narrative_prompt)
        
        try:
            m = re.search(r"\{.*\}", narrative_raw, re.DOTALL)
            narrative = json.loads(m.group()) if m else {}
        except:
            narrative = {}

        insights = {
            "domain": "Dynamic Discovery",
            "goal": goal,
            "summary": narrative.get("summary", "No summary generated."),
            "datasets": datasets,
            "key_insights": narrative.get("key_insights", []),
            "recommendations": narrative.get("recommendations", []),
            "schema_stats": _schema_stats(schema, relationships),
        }

        state["llm_insights"] = insights
        update_step_progress_state(state, "insights", session_id)

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
