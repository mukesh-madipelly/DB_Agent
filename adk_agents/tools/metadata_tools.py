"""
ADK Tools for Database Metadata Scanning (Async Turbo Engine active ⚡)
"""

import config
import asyncio
from typing import Dict, List, Any
from google.adk.tools.tool_context import ToolContext
from adk_agents.tools.query_cache import get_query_cache
from adk_agents.state_manager import update_step_progress_state, get_state_manager, save_current_state

async def scan_database_tables(tool_context: ToolContext) -> dict:
    """Scans the database and returns a complete map of all tables and their columns (Turbo Mode)."""
    print("🔧 Tool invocation: scan_database_tables (Async Turbo Engine active ⚡)")
    
    from adk_agents.state_manager import get_active_session_id
    session_id = (getattr(tool_context, 'session_id', None)
                  or get_active_session_id()
                  or str(id(tool_context.state)))
    
    # Check cache first
    cache = get_query_cache()
    db_config = {
        "host": config.POSTGRESQL.get("host") if config.DB_TYPE == "postgresql" else config.SNOWFLAKE.get("account"),
        "dbname": config.POSTGRESQL.get("dbname") if config.DB_TYPE == "postgresql" else config.SNOWFLAKE.get("database"),
        "schema": config.POSTGRESQL_SCHEMA if config.DB_TYPE == "postgresql" else config.SNOWFLAKE.get("schema"),
    }
    
    force_refresh = tool_context.state.get("force_refresh", False)
    cached_result = cache.get("schema_scan", db_config, force_refresh=force_refresh)
    
    if cached_result:
        print(f"   - 📦 Cache hit for schema scan")
        schema = cached_result.get("schema", {})
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id) or {}
        state["schema"] = schema
        state["tables_scanned"] = True
        for k, v in state.items():
            tool_context.state[k] = v
        update_step_progress_state(state, "metadata", session_id)
        save_current_state(tool_context)
        return {"status": "success", "from_cache": True, "table_count": len(schema), "schema": schema}

    state_manager = get_state_manager()
    state = state_manager.load_state(session_id) or {}

    try:
        from adk_agents.tools.connection_tools import get_async_database_pool
        pool = await get_async_database_pool(tool_context)

        async with pool.acquire() as conn:
            if config.DB_TYPE == "snowflake":
                # Fallback to sync for Snowflake (asyncpg doesn't support it)
                from adk_agents.tools.connection_tools import get_database_connection
                sync_conn = get_database_connection(tool_context)
                cursor = sync_conn.cursor()
                try:
                    cursor.execute(f"SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{config.SNOWFLAKE.get('schema', 'PUBLIC')}' ORDER BY TABLE_NAME, ORDINAL_POSITION")
                    rows = cursor.fetchall()
                finally:
                    cursor.close()
            else:
                pg_schema = config.POSTGRESQL_SCHEMA
                print(f"   - Executing schema query on PostgreSQL (schema: {pg_schema})...")
                rows = await conn.fetch("""
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = $1
                    ORDER BY table_name, ordinal_position
                """, pg_schema)

            schema = {}
            for row in rows:
                if not isinstance(row, (tuple, list)):
                    r_dict = dict(row)
                    table_name, col_name, col_type = r_dict["table_name"], r_dict["column_name"], r_dict["data_type"]
                else:
                    table_name, col_name, col_type = row

                if table_name not in schema:
                    schema[table_name] = {"columns": []}
                schema[table_name]["columns"].append({"name": col_name, "type": col_type})

            print(f"   - Processed {len(schema)} tables")

            state["schema"] = schema
            state["tables_scanned"] = True
            for k, v in state.items():
                tool_context.state[k] = v

            update_step_progress_state(state, "metadata", session_id)
            save_current_state(tool_context)
            
            # Cache the schema
            cache.set("schema_scan", db_config, {"schema": schema})

            print("\u2705 Tool execution completed successfully (Turbo Engine ⚡)")
            return {
                "status": "success",
                "table_count": len(schema),
                "schema": schema,
                "from_cache": False,
                "message": f"Successfully scanned {len(schema)} tables"
            }
    
    except Exception as e:
        print(f"❌ Turbo Engine Error: {str(e)}")
        return {"status": "error", "message": str(e)}
