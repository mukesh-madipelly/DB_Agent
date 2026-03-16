"""
ADK Tools for Ad-hoc Custom Query Execution

This tool accepts a natural-language question and generates + executes the SQL internally,
using the database schema from session state context.
"""

import json
import re
import time
from datetime import datetime, date, time as dt_time
from google.adk.tools.tool_context import ToolContext
from adk_agents.tools.connection_tools import get_database_connection
from adk_agents.state_manager import get_state_manager, get_active_session_id, save_current_state
import config


def _serialize_value(value):
    """Convert non-JSON-serializable types to JSON-compatible formats."""
    if value is None:
        return None
    elif isinstance(value, (datetime, date, dt_time)):
        return value.isoformat()
    elif isinstance(value, (int, float, str, bool)):
        return value
    else:
        return str(value)


def _build_schema_reference(schema: dict) -> str:
    """Build a compact schema reference string for the LLM to use when generating SQL."""
    lines = ["=== DATABASE SCHEMA ==="]
    for tbl, info in schema.items():
        cols = ", ".join(
            f'{c.get("name")}({c.get("type", "?")})'
            for c in info.get("columns", [])
        )
        lines.append(f'  "{tbl}"  rows:{info.get("row_count", "?")}  cols:[{cols}]')
    return "\n".join(lines)


def _generate_sql_from_question(question: str, schema_ref: str) -> str:
    """Use LLM to generate a SQL query from a natural language question."""
    from google import genai

    api_key = config.AGENT_API_KEYS.get("insights", config.GOOGLE_API_KEY)
    model = config.AGENT_MODELS.get("insights", config.ADK_MODEL)
    client = genai.Client(api_key=api_key)

    prompt = f"""You are an expert PostgreSQL developer.
Write a SINGLE read-only SELECT query that answers this question:
"{question}"

Rules:
- Use double-quoted identifiers for table and column names (e.g. "Organisation", "User", "Id").
- Only use tables/columns listed in the schema below.
- You must return a JSON object with exactly two keys: "title" (a short, descriptive heading for a report section) and "sql" (the raw postgresql query itself).
- Do not wrap the JSON in markdown fences (no ```json).

{schema_ref}
"""
    for attempt in range(3):
        try:
            response = client.models.generate_content(model=model, contents=prompt)
            output = response.text.strip()
            # Strip markdown fences if present
            output = re.sub(r"^```(?:json)?", "", output, flags=re.IGNORECASE).strip()
            output = re.sub(r"```$", "", output).strip()
            
            # Parse the JSON to get title and SQL
            try:
                data = json.loads(output)
                return data.get("title", question), data.get("sql", "")
            except json.JSONDecodeError:
                # Fallback if the LLM ignores instructions and returns raw SQL
                return question, output

        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


async def execute_ad_hoc_query(tool_context: ToolContext, question: str) -> dict:
    """Executes a custom data lookup requested by the user.

    This tool takes a natural-language question, generates the SQL automatically 
    using the database schema, and stores results for the final report.

    Args:
        tool_context (ToolContext): ADK context for accessing session state.
        question (str): The user's data question in plain English, e.g. "find top 5 organizations by user count".

    Returns:
        dict: Status and result summary.
    """
    print(f"🔧 Tool invocation: execute_ad_hoc_query (Async Turbo Engine active ⚡)")
    print(f"   - Question: {question}")
    
    session_id = (getattr(tool_context, 'session_id', None)
                  or get_active_session_id()
                  or str(id(tool_context.state)))

    state_manager = get_state_manager()
    state = state_manager.load_state(session_id) or {}

    # Get schema from state for SQL generation
    schema = state.get("schema", {})
    if not schema:
        return {
            "status": "error",
            "message": "No schema found in state. The pipeline must run scan_database_tables first."
        }

    # Step 1: Generate SQL from question using LLM + schema
    schema_ref = _build_schema_reference(schema)
    try:
        title, query = _generate_sql_from_question(question, schema_ref)
        print(f"   - Generated Title: {title}")
        print(f"   - Generated SQL: {query}")
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to generate SQL: {str(e)}"
        }

    # Safety check - only allow SELECT
    clean_query = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
    clean_query = re.sub(r'/\*.*?\*/', '', clean_query, flags=re.DOTALL)
    
    if not clean_query.strip().lower().startswith("select"):
        return {
            "status": "error",
            "message": "Generated query is not a SELECT statement. Aborting for safety."
        }

    # Step 2: Execute the query securely using async pool
    from adk_agents.tools.connection_tools import get_async_database_pool
    try:
        pool = await get_async_database_pool(tool_context)
        async with pool.acquire() as conn:
            # Enforce Read-Only and set a generous 30s timeout
            await conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;")
            await conn.execute("SET statement_timeout = 30000;")
            
            rows = await conn.fetch(query)
            
            # Convert rows to list of dicts with JSON-serializable values
            results = []
            for row in rows:
                row_dict = {}
                for col, val in dict(row).items():
                    row_dict[col] = _serialize_value(val)
                results.append(row_dict)

            print(f"   ✅ Query returned {len(rows)} rows")

            # Store in state for the reporter
            custom_findings = state.get("custom_findings", [])
            finding = {
                "title": title,
                "description": question,
                "query": query,
                "results": results[:20],  # limit to 20 rows for the report
                "total_rows_found": len(rows)
            }
            custom_findings.append(finding)
            state["custom_findings"] = custom_findings

            # Sync back to tool_context
            for k, v in state.items():
                tool_context.state[k] = v

            # Save DIRECTLY to disk
            state_manager.save_state(session_id, state)
            print(f"   💾 Saved custom_findings to state file (session: {session_id})")

            return {
                "status": "success",
                "message": f"Found {len(rows)} rows for: {question}",
                "description": question,
                "row_count": len(rows),
                "preview": results[:5]
            }

    except Exception as e:
        from adk_agents.tools.error_utils import log_and_raise_connection_error
        log_and_raise_connection_error("Failed to execute custom query", e)
