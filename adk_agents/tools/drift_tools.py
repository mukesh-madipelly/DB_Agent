"""
ADK Tools for Schema Drift Detection
"""

from datetime import datetime
from google.adk.tools.tool_context import ToolContext
from adk_agents.state_manager import check_prerequisites_state, update_step_progress_state, update_step_progress, save_current_state, get_state_manager


async def detect_schema_changes(tool_context: ToolContext) -> dict:
    """Detects changes between previous and current database schema (Turbo Mode)."""
    print("🔧 Tool invocation: detect_schema_changes (Async Turbo Engine active ⚡)")
    
    from adk_agents.state_manager import get_active_session_id
    session_id = (getattr(tool_context, 'session_id', None)
                  or get_active_session_id()
                  or str(id(tool_context.state)))
    
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id) or {}
    
    prereq_check = check_prerequisites_state(state, ["tables_scanned", "profiling_complete"])
    if prereq_check["status"] == "error":
        return {"status": "error", "message": prereq_check["message"]}
    
    try:
        current_schema = state.get("schema", {})
        if not current_schema:
            return {"status": "error", "message": "No schema found."}
        
        import os, json, config
        # Compute identity
        if config.DB_TYPE.lower() == "postgresql":
            db_identity = f"postgresql_{config.POSTGRESQL.get('dbname', 'db')}_{getattr(config, 'POSTGRESQL_SCHEMA', 'public')}"
        else:
            db_identity = f"snowflake_{config.SNOWFLAKE.get('account', 'acc')}"

        snapshot_path = os.path.join(getattr(config, "SNAPSHOT_ROOT", "snapshots"), db_identity, "schema_snapshot.json")
        os.makedirs(os.path.dirname(snapshot_path), exist_ok=True)
        
        previous_schema = None
        if os.path.exists(snapshot_path):
            with open(snapshot_path, 'r') as f:
                previous_schema = json.load(f).get('schema', {})

        if not previous_schema:
            changes = ["ℹ️  First run baseline created."]
            tool_context.state["changes"] = changes
            with open(snapshot_path, 'w') as f:
                json.dump({"schema": current_schema, "timestamp": str(datetime.now())}, f, indent=2)
            update_step_progress(tool_context, "drift")
            return {"status": "success", "change_count": 0, "changes": changes}

        changes = []
        # Comparison logic (simplified for brevity while maintaining core functionality)
        prev_tables = set(previous_schema.keys())
        curr_tables = set(current_schema.keys())
        
        # New/Dropped Tables
        for t in sorted(curr_tables - prev_tables): changes.append(f"🆕 New table: **{t}**")
        for t in sorted(prev_tables - curr_tables): changes.append(f"❌ Dropped table: **{t}**")
        
        # Column changes in common tables
        for t in sorted(prev_tables & curr_tables):
            def get_cols(td): return {c["name"]: c["type"] for c in (td if isinstance(td, list) else td.get("columns", []))}
            p_cols = get_cols(previous_schema[t])
            c_cols = get_cols(current_schema[t])
            for c in sorted(set(c_cols) - set(p_cols)): changes.append(f"🆕 **{t}**: New column `{c}`")
            for c in sorted(set(p_cols) - set(c_cols)): changes.append(f"❌ **{t}**: Dropped column `{c}`")
        
        if not changes: changes.append("✅ No changes detected.")
        tool_context.state["changes"] = changes
        
        # Update baseline
        with open(snapshot_path, 'w') as f:
            json.dump({"schema": current_schema, "timestamp": str(datetime.now())}, f, indent=2)
            
        update_step_progress(tool_context, "drift")
        
        print(f"✅ Drift Check OK: {len(changes)} changes (Turbo Engine ⚡)")
        return {"status": "success", "change_count": len(changes), "changes": changes}
    except Exception as e:
        from adk_agents.tools.error_utils import log_and_raise_connection_error
        log_and_raise_connection_error("Turbo Engine Error in drift detection", e)
