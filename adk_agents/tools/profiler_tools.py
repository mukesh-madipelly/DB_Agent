import config
import asyncio
from google.adk.tools.tool_context import ToolContext
from adk_agents.tools.connection_tools import get_database_connection, get_async_database_pool
from adk_agents.tools.query_cache import get_query_cache
from adk_agents.state_manager import check_prerequisites_state, update_step_progress_state, get_state_manager, save_current_state


def _wrap_identifier(name: str) -> str:
    """Wraps identifier in double quotes for databases that require it for special characters or case sensitivity."""
    return '"' + name + '"'


async def _profile_table_async(table: str, info: dict, pool, semaphore, data_samples: dict):
    """Profiles a single table asynchronously with a concurrency limit."""
    async with semaphore:
        print(f"   [Turbo] Sampling {table}...")
        table_ref = _wrap_identifier(table)
        
        async with pool.acquire() as conn:
            try:
                # 1. Row count
                row_count = await conn.fetchval(f"SELECT COUNT(*) FROM {table_ref}")
                info["row_count"] = row_count
                
                # 2. Determine if there's a date col
                date_col = None
                for col in info.get("columns", []):
                    col_name = col.get("name", "")
                    col_type = str(col.get("type", "")).lower()
                    if "timestamp" in col_type or "date" in col_type:
                        if "created" in col_name.lower() or "issue" in col_name.lower():
                            date_col = col_name
                            break
                        if not date_col:
                            date_col = col_name

                # 3. Fetch samples (Limit 50)
                if date_col:
                    query = f"SELECT * FROM {table_ref} ORDER BY {_wrap_identifier(date_col)} DESC LIMIT 50"
                else:
                    query = f"SELECT * FROM {table_ref} LIMIT 50"
                
                rows = await conn.fetch(query)
                
                # Convert to dicts and handle dates
                processed_rows = []
                for row in rows:
                    r_dict = dict(row)
                    for k, v in r_dict.items():
                        if hasattr(v, "isoformat"):
                            r_dict[k] = v.isoformat()
                    processed_rows.append(r_dict)
                
                data_samples[table] = processed_rows
                info["columns_profile"] = {} # Clear old profile
                return True
            except Exception as e:
                from adk_agents.tools.error_utils import log_and_raise_connection_error
                log_and_raise_connection_error(f"Error sampling table {table}", e)


async def analyze_column_statistics(tool_context: ToolContext) -> dict:
    """Analyzes data quality and statistics for all columns in database tables (Turbo Mode)."""
    print("🔧 Tool invocation: analyze_column_statistics (Turbo Engine Enabled ⚡)")
    
    from adk_agents.state_manager import get_active_session_id
    session_id = (getattr(tool_context, 'session_id', None)
                  or get_active_session_id()
                  or str(id(tool_context.state)))
    
    # 1. Cache Check
    cache = get_query_cache()
    db_config = {
        "host": config.POSTGRESQL.get("host") if config.DB_TYPE == "postgresql" else config.SNOWFLAKE.get("account"),
        "dbname": config.POSTGRESQL.get("dbname") if config.DB_TYPE == "postgresql" else config.SNOWFLAKE.get("database"),
        "schema": config.POSTGRESQL_SCHEMA if config.DB_TYPE == "postgresql" else config.SNOWFLAKE.get("schema"),
    }
    
    force_refresh = tool_context.state.get("force_refresh", False)
    cached_result = cache.get("column_profiling", db_config, force_refresh=force_refresh)
    
    if cached_result:
        print(f"   - 📦 Cache hit! (Turbo Engine bypassing SQL execution)")
        state_manager = get_state_manager()
        state = state_manager.load_state(session_id) or {}
        state["schema"] = cached_result.get("schema", {})
        state["data_samples"] = cached_result.get("data_samples", {})
        state["profiling_complete"] = True
        for k, v in state.items():
            tool_context.state[k] = v
        update_step_progress_state(state, "profiler", session_id)
        save_current_state(tool_context)
        return {"status": "success", "from_cache": True, "message": "Successfully loaded cached profiling stats"}

    # 2. Logic Check
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id) or {}
    prereq_check = check_prerequisites_state(state, ["connection_established", "tables_scanned"])
    if prereq_check["status"] == "error":
        return {"status": "error", "message": prereq_check["message"]}

    try:
        # 3. Parallel Execution (Turbo Mode) - Only for PostgreSQL
        schema = state.get("schema", {})
        data_samples = {}
        
        if config.DB_TYPE == "postgresql":
            # Use async operations for PostgreSQL
            pool = await get_async_database_pool(tool_context)
            # Limit concurrency to 5 connections to protect the DB
            semaphore = asyncio.Semaphore(5)
            
            tasks = []
            for table, info in schema.items():
                tasks.append(_profile_table_async(table, info, pool, semaphore, data_samples))
            
            print(f"   🚀 Turbo Engine: Parallelizing analysis for {len(tasks)} tables...")
            results = await asyncio.gather(*tasks)
            tables_profiled = sum(1 for r in results if r)
        else:
            # Use sync operations for Snowflake and other databases
            print(f"   📊 Analyzing columns for {len(schema)} tables (sync mode)...")
            sync_conn = get_database_connection(tool_context)
            cursor = sync_conn.cursor()
            
            try:
                tables_profiled = 0
                for table, info in schema.items():
                    print(f"   [Sync] Analyzing {table}...")
                    table_ref = _wrap_identifier(table)
                    
                    # Get row count
                    cursor.execute(f"SELECT COUNT(*) FROM {table_ref}")
                    row_count = cursor.fetchone()[0]
                    info["row_count"] = row_count
                    
                    # Sample data (limit 50)
                    cursor.execute(f"SELECT * FROM {table_ref} LIMIT 50")
                    rows = cursor.fetchall()
                    
                    # Convert to dict format
                    processed_rows = []
                    if rows:
                        column_names = [desc[0] for desc in cursor.description]
                        for row in rows:
                            r_dict = dict(zip(column_names, row))
                            processed_rows.append(r_dict)
                    
                    data_samples[table] = processed_rows
                    tables_profiled += 1
                    
            finally:
                cursor.close()
                sync_conn.close()

        # 4. Finalize State
        state["data_samples"] = data_samples
        state["schema"] = schema
        state["profiling_complete"] = True
        
        for k, v in state.items():
            tool_context.state[k] = v
            
        update_step_progress_state(state, "profiler", session_id)
        save_current_state(tool_context)
        
        # Cache for next time
        cache.set("column_profiling", db_config, {
            "schema": state.get("schema", {}),
            "data_samples": state.get("data_samples", {})
        })
        
        print(f"✅ Success! Turbo Engine profiled {tables_profiled} tables in parallel. ⚡")
        return {
            "status": "success",
            "tables_profiled": tables_profiled,
            "message": f"Turbo Engine completed parallel profiling for {tables_profiled} tables."
        }

    except Exception as e:
        print(f"❌ Turbo Engine Error: {str(e)}")
        return {"status": "error", "message": str(e)}
