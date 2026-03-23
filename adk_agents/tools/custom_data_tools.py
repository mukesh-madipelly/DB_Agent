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
from adk_agents.logger import get_logger
from adk_agents.state_manager import (
    get_state_manager,
    get_active_session_id,
)

import config

logger = get_logger()


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
            f"{c.get('name')}({c.get('type', '?')})" for c in info.get("columns", [])
        )
        lines.append(f'  "{tbl}"  rows:{info.get("row_count", "?")}  cols:[{cols}]')
    return "\n".join(lines)


def _generate_sql_from_question(question: str, schema_ref: str) -> str:
    """Use LLM to generate a SQL query from a natural language question."""
    from google import genai

    api_key = config.AGENT_API_KEYS.get("insights", config.GOOGLE_API_KEY)
    model = config.AGENT_MODELS.get("insights", config.ADK_MODEL)
    client = genai.Client(api_key=api_key)

    if config.DB_TYPE == "postgresql":
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
    elif config.DB_TYPE == "snowflake":
        prompt = f"""You are an expert Snowflake developer.
Write a SINGLE read-only SELECT query that answers this question:
"{question}"

Rules:
- Use plain identifiers for table and column names (no double quotes needed).
- Only use tables/columns listed in the schema below.
- You must return a JSON object with exactly two keys: "title" (a short, descriptive heading for a report section) and "sql" (the raw snowflake query itself).
- Do not wrap the JSON in markdown fences (no ```json).

{schema_ref}
"""
    else:
        prompt = f"""You are an expert SQL developer.
Write a SINGLE read-only SELECT query that answers this question:
"{question}"

Rules:
- Use appropriate identifier quoting for the database type.
- Only use tables/columns listed in the schema below.
- You must return a JSON object with exactly two keys: "title" (a short, descriptive heading for a report section) and "sql" (the raw query itself).
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
            time.sleep(2**attempt)


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
    logger.info(
        "🔧 Tool invocation: execute_ad_hoc_query (Async Turbo Engine active ⚡)"
    )
    logger.info(f"   - Question: {question}")

    session_id = (
        getattr(tool_context, "session_id", None)
        or get_active_session_id()
        or str(id(tool_context.state))
    )

    state_manager = get_state_manager()
    state = state_manager.load_state(session_id) or {}

    # Get schema from state for SQL generation
    schema = state.get("schema", {})
    if not schema:
        return {
            "status": "error",
            "message": "No schema found in state. The pipeline must run scan_database_tables first.",
        }

    # Step 1: Generate SQL from question using LLM + schema
    schema_ref = _build_schema_reference(schema)
    try:
        title, query = _generate_sql_from_question(question, schema_ref)
        logger.info(f"   - Generated Title: {title}")
        logger.info(f"   - Generated SQL: {query}")
    except Exception as e:
        return {"status": "error", "message": f"Failed to generate SQL: {str(e)}"}

    # Safety check - only allow SELECT or WITH (CTEs)
    clean_query = re.sub(r"--.*$", "", query, flags=re.MULTILINE)
    clean_query = re.sub(r"/\*.*?\*/", "", clean_query, flags=re.DOTALL)

    if not re.match(r"^\s*(SELECT|WITH)\b", clean_query, re.IGNORECASE):
        return {
            "status": "error",
            "message": "Generated query must be a SELECT or WITH statement. Aborting for safety.",
        }

    # Step 2: Execute the query securely using appropriate connection
    try:
        if config.DB_TYPE == "postgresql":
            # Use async operations for PostgreSQL
            from adk_agents.tools.connection_tools import get_async_database_pool

            pool = await get_async_database_pool(tool_context)
            async with pool.acquire() as conn:
                # Enforce Read-Only and set a generous 30s timeout
                await conn.execute(
                    "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;"
                )
                await conn.execute("SET statement_timeout = 30000;")

                rows = await conn.fetch(query)

                # Convert rows to list of dicts with JSON-serializable values
                results = []
                for row in rows:
                    row_dict = {}
                    for col, val in dict(row).items():
                        row_dict[col] = _serialize_value(val)
                    results.append(row_dict)

        elif config.DB_TYPE == "snowflake":
            # Use sync operations for Snowflake
            from adk_agents.tools.connection_tools import get_database_connection

            sync_conn = get_database_connection(tool_context)
            cursor = sync_conn.cursor()
            try:
                # Execute query with timeout
                cursor.execute(query)
                rows = cursor.fetchall()

                # Convert rows to list of dicts with JSON-serializable values
                results = []
                column_names = [desc[0] for desc in cursor.description]
                for row in rows:
                    row_dict = dict(zip(column_names, row))
                    for col, val in row_dict.items():
                        row_dict[col] = _serialize_value(val)
                    results.append(row_dict)
            finally:
                cursor.close()
                sync_conn.close()
        else:
            return {
                "status": "error",
                "message": f"Unsupported database type: {config.DB_TYPE}",
            }

        logger.info(f"   ✅ Query returned {len(results)} rows")

        # Store in state for the reporter
        custom_findings = state.get("custom_findings", [])
        finding = {
            "title": title,
            "description": question,
            "query": query,
            "results": results[:20],  # limit to 20 rows for the report
            "total_rows_found": len(results),
        }
        custom_findings.append(finding)
        state["custom_findings"] = custom_findings

        # Sync back to tool_context
        for k, v in state.items():
            tool_context.state[k] = v

        # Save DIRECTLY to disk
        state_manager.save_state(session_id, state)
        logger.info(
            f"   💾 Saved custom_findings to state file (session: {session_id})"
        )

        return {
            "status": "success",
            "message": f"Found {len(results)} rows for: {question}",
            "description": question,
            "row_count": len(results),
            "preview": results[:5],
        }

    except Exception as e:
        from adk_agents.tools.error_utils import log_and_raise_connection_error

        log_and_raise_connection_error("Failed to execute custom query", e)
