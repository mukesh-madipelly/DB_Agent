"""
ADK Tools for Database Metadata Scanning (Async Turbo Engine active ⚡)
"""

import config
from google.adk.tools.tool_context import ToolContext
from adk_agents.tools.query_cache import get_query_cache
from adk_agents.logger import get_logger
from adk_agents.state_manager import (
    update_step_progress,
)

logger = get_logger()


async def scan_database_tables(tool_context: ToolContext) -> dict:
    """Scans the database and returns a complete map of all tables and their columns (Turbo Mode)."""
    logger.info("Tool invocation: scan_database_tables (Async Turbo Engine active ⚡)")

    from adk_agents.state_manager import get_active_session_id

    (
        getattr(tool_context, "session_id", None)
        or get_active_session_id()
        or str(id(tool_context.state))
    )

    # Check cache first
    cache = get_query_cache()
    db_config = {
        "host": config.POSTGRESQL.get("host")
        if config.DB_TYPE == "postgresql"
        else config.SNOWFLAKE.get("account"),
        "dbname": config.POSTGRESQL.get("dbname")
        if config.DB_TYPE == "postgresql"
        else config.SNOWFLAKE.get("database"),
        "schema": config.POSTGRESQL_SCHEMA
        if config.DB_TYPE == "postgresql"
        else config.SNOWFLAKE.get("schema"),
    }

    force_refresh = tool_context.state.get("force_refresh", False)
    cached_result = cache.get("schema_scan", db_config, force_refresh=force_refresh)

    if cached_result:
        logger.info("Cache hit for schema scan", icon="📦")
        schema = cached_result.get("schema", {})
        update_step_progress(tool_context, "metadata")
        return {
            "status": "success",
            "from_cache": True,
            "table_count": len(schema),
            "schema": schema,
        }

    try:
        if config.DB_TYPE == "postgresql":
            # Use async operations for PostgreSQL
            from adk_agents.tools.connection_tools import get_async_database_pool

            pool = await get_async_database_pool(tool_context)
            async with pool.acquire() as conn:
                pg_schema = config.POSTGRESQL_SCHEMA
                logger.info(
                    f"Executing schema query on PostgreSQL (schema: {pg_schema})..."
                )
                rows = await conn.fetch(
                    """
                    SELECT table_name, column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = $1
                    ORDER BY table_name, ordinal_position
                """,
                    pg_schema,
                )
        else:
            # Use sync operations for Snowflake and other databases
            from adk_agents.tools.connection_tools import get_database_connection

            sync_conn = get_database_connection(tool_context)
            cursor = sync_conn.cursor()
            try:
                if config.DB_TYPE == "snowflake":
                    sf_schema = config.SNOWFLAKE.get("schema", "PUBLIC")
                    logger.info(
                        f"Executing schema query on Snowflake (schema: {sf_schema})..."
                    )
                    cursor.execute(
                        f"SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = '{sf_schema}' ORDER BY TABLE_NAME, ORDINAL_POSITION"
                    )
                else:
                    # Fallback for other databases
                    logger.info(f"Executing schema query on {config.DB_TYPE}...")
                    cursor.execute(
                        "SELECT table_name, column_name, data_type FROM information_schema.columns ORDER BY table_name, ordinal_position"
                    )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        # Process results (works for both sync and async)
        schema = {}
        for row in rows:
            if not isinstance(row, (tuple, list)):
                r_dict = dict(row)
                table_name, col_name, col_type = (
                    r_dict["table_name"],
                    r_dict["column_name"],
                    r_dict["data_type"],
                )
            else:
                table_name, col_name, col_type = row
            if table_name not in schema:
                schema[table_name] = {"columns": []}
            schema[table_name]["columns"].append({"name": col_name, "type": col_type})

        logger.info(f"Processed {len(schema)} tables")
        tool_context.state["schema"] = schema
        tool_context.state["tables_scanned"] = True
        update_step_progress(tool_context, "metadata")
        cache.set("schema_scan", db_config, {"schema": schema})
        logger.success("Tool execution completed successfully (Turbo Engine ⚡)")
        return {
            "status": "success",
            "from_cache": False,
            "table_count": len(schema),
            "schema": schema,
        }
    except Exception as e:
        from adk_agents.tools.error_utils import log_and_raise_connection_error

        log_and_raise_connection_error("Turbo Engine Error in metadata scan", e)
        logger.error(f"Turbo Engine Error: {str(e)}")
        return {"status": "error", "message": str(e)}
