"""
ADK Tools for Detecting Table Relationships (Async Turbo Engine active ⚡)
"""

import config
import asyncio
from google.adk.tools.tool_context import ToolContext
from adk_agents.state_manager import check_prerequisites_state, update_step_progress_state, get_state_manager, save_current_state

async def detect_table_relationships(tool_context: ToolContext) -> dict:
    """Detects relationships between database tables (Turbo Mode)."""
    print("🔧 Tool invocation: detect_table_relationships (Async Turbo Engine active ⚡)")
    
    from adk_agents.state_manager import get_active_session_id
    session_id = (getattr(tool_context, 'session_id', None)
                  or get_active_session_id()
                  or str(id(tool_context.state)))
    
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id) or {}
    
    # Check prerequisites
    if state.get("tables_scanned") is not True:
        return {"status": "error", "message": "Metadata scan required first."}
    
    try:
        schema = state.get("schema", {})
        from adk_agents.tools.connection_tools import get_async_database_pool
        pool = await get_async_database_pool(tool_context)
        
        found = set()
        fk_count = 0
        naming_count = 0
        
        async with pool.acquire() as conn:
            if config.DB_TYPE == "snowflake":
                # Fallback to sync for Snowflake
                from adk_agents.tools.connection_tools import get_database_connection
                sync_conn = get_database_connection(tool_context)
                cursor = sync_conn.cursor()
                try:
                    cursor.execute(f"SELECT fk_table_name, fk_column_name, pk_table_name, pk_column_name FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS WHERE fk_schema = '{config.SNOWFLAKE.get('schema', 'PUBLIC')}'")
                    fk_results = cursor.fetchall()
                    for r in fk_results:
                        found.add(f"{r[0].lower()}.{r[1].lower()} → {r[2].lower()}.{r[3].lower()}")
                        fk_count += 1
                finally:
                    cursor.close()
            else:
                pg_schema = config.POSTGRESQL_SCHEMA
                fk_results = await conn.fetch("""
                    SELECT kcu.table_name, kcu.column_name, ccu.table_name as parent_table, ccu.column_name as parent_column
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
                    WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = $1
                """, pg_schema)
                for r in fk_results:
                    r_dict = dict(r)
                    found.add(f"{r_dict['table_name'].lower()}.{r_dict['column_name'].lower()} → {r_dict['parent_table'].lower()}.{r_dict['parent_column'].lower()}")
                    fk_count += 1

        # Naming conventions
        table_names = list(schema.keys())
        for table, info in schema.items():
            for col in info["columns"]:
                if col["name"].endswith("_id"):
                    parent_guess = col["name"].replace("_id", "")
                    parent = None
                    if parent_guess in table_names: parent = parent_guess
                    elif parent_guess + "s" in table_names: parent = parent_guess + "s"
                    
                    if parent:
                        rel = f"{table}.{col['name']} → {parent}.id"
                        if rel not in found:
                            found.add(rel)
                            naming_count += 1
        
        relationships = sorted(found)
        state["relationships"] = relationships
        for k, v in state.items():
            tool_context.state[k] = v
            
        update_step_progress_state(state, "relations", session_id)
        save_current_state(tool_context)
        
        print(f"✅ Relations OK: Found {len(relationships)} (Turbo Engine ⚡)")
        return {
            "status": "success",
            "relationship_count": len(relationships),
            "fk_count": fk_count,
            "naming_convention_count": naming_count,
            "relationships": relationships
        }
    except Exception as e:
        from adk_agents.tools.error_utils import log_and_raise_connection_error
        log_and_raise_connection_error("Turbo Engine Error in table relationship detection", e)
