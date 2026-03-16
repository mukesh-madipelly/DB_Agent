"""
Session State Manager for ADK Database Intelligence

Provides state persistence, validation, and management.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, Optional
import uuid
from adk_agents.logger import get_logger

logger = get_logger()


import sqlite3
import threading

class StateManager:
    """Manages session state persistence and validation using SQLite."""
    
    def __init__(self, state_dir: str = "state"):
        """
        Initialize state manager.
        
        Args:
            state_dir: Directory to store state metadata
        """
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.db_path = os.path.join(state_dir, "state.db")
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Initialize the SQLite database schema."""
        conn = self._get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_states (
                    session_id TEXT PRIMARY KEY,
                    last_saved TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    state_json TEXT
                )
            """)
            conn.commit()
        finally:
            conn.close()
    def _get_connection(self):
        """Get a SQLite connection."""
        return sqlite3.connect(self.db_path, timeout=10)

    def save_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        """
        Save session state to database.
        
        Args:
            session_id: Unique session identifier
            state: Session state dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            state_json = json.dumps(state)
            now = datetime.now().isoformat()
            
            with self._lock:
                conn = self._get_connection()
                try:
                    conn.execute("""
                        INSERT OR REPLACE INTO session_states (session_id, last_saved, state_json)
                        VALUES (?, ?, ?)
                    """, (session_id, now, state_json))
                    conn.commit()
                finally:
                    conn.close()
            
            return True
        except Exception as e:
            logger.error(f"Error saving state for session {session_id}: {e}")
            return False
    
    def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Load session state from database. Falls back to JSON file for migration.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            Session state dictionary or None if not found
        """
        try:
            # 1. Try DB first
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    "SELECT state_json FROM session_states WHERE session_id = ?", 
                    (session_id,)
                )
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
            finally:
                conn.close()
            
            # 2. Fallback to legacy JSON file for migration
            state_file = os.path.join(self.state_dir, f"{session_id}.json")
            if os.path.exists(state_file):
                logger.info(f"Migrating legacy state file for session {session_id}")
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                state = data.get("state", {})
                if state:
                    self.save_state(session_id, state)
                    # Clean up legacy file after migration (optional, keeping for safety)
                    # os.remove(state_file)
                return state
                
            return None
        except Exception as e:
            logger.error(f"Error loading state for session {session_id}: {e}")
            return None
    
    def delete_state(self, session_id: str) -> bool:
        """
        Delete session state from database.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._lock:
                conn = self._get_connection()
                try:
                    conn.execute("DELETE FROM session_states WHERE session_id = ?", (session_id,))
                    conn.commit()
                finally:
                    conn.close()
            
            # Also clean up legacy file if it exists
            state_file = os.path.join(self.state_dir, f"{session_id}.json")
            if os.path.exists(state_file):
                os.remove(state_file)
                
            return True
        except Exception as e:
            logger.error(f"Error deleting state for session {session_id}: {e}")
            return False

    def validate_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and normalize session state.
        
        Args:
            state: Session state dictionary
            
        Returns:
            Validated and normalized state
        """
        if not state:
            return {}
            
        # Safely copy state to preserve custom keys
        validated_state = {}
        
        # Handle state objects that might not be dicts (ADK tool_context.state)
        if hasattr(state, "get"):
            # Required fields with defaults
            validated_state["connection_established"] = state.get("connection_established", False)
            validated_state["schema"] = state.get("schema", {})
            validated_state["tables_scanned"] = state.get("tables_scanned", False)
            validated_state["profiling_complete"] = state.get("profiling_complete", False)
            validated_state["relationships"] = state.get("relationships", [])
            validated_state["changes"] = state.get("changes", [])
            validated_state["llm_insights"] = state.get("llm_insights", {})
            validated_state["report_path"] = state.get("report_path", "")
            validated_state["json_report_path"] = state.get("json_report_path", "")
            validated_state["data_samples"] = state.get("data_samples", {})
            
            # Preserve extra keys
            for key in ["licensing_context", "custom_findings", "pii_alerts", "audit_complete", "steps_completed"]:
                if key in state:
                    validated_state[key] = state.get(key)
            
            # Track progress
            validated_state["current_step"] = state.get("current_step", 0)
            validated_state["total_steps"] = state.get("total_steps", 6)
        else:
            # Fallback for simple dicts
            validated_state = dict(state)
        
        return validated_state
    
    def get_state_summary(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Get summary of session state."""
        return {
            "connection_established": state.get("connection_established", False),
            "tables_scanned": state.get("tables_scanned", False),
            "profiling_complete": state.get("profiling_complete", False),
            "relationship_count": len(state.get("relationships", [])),
            "change_count": len(state.get("changes", [])),
            "insights_generated": bool(state.get("llm_insights", {})),
            "reports_generated": bool(state.get("report_path") or state.get("json_report_path")),
            "current_step": state.get("current_step", 0),
            "total_steps": state.get("total_steps", 6),
            "steps_completed": state.get("steps_completed", []),
        }
    
    def cleanup_old_states(self, retention_days: int = 30) -> tuple[int, int, int]:
        """
        Remove states older than retention_days from DB and disk.
        
        Args:
            retention_days: Number of days to retain 
            
        Returns:
            Tuple of (records_removed, legacy_files_removed, total_space_freed_kb)
        """
        records_removed = 0
        legacy_files_removed = 0
        space_freed_bytes = 0
        
        try:
            # 1. Cleanup SQLite
            with self._lock:
                conn = self._get_connection()
                try:
                    # Approximation: retention logic via date string
                    cursor = conn.execute("""
                        DELETE FROM session_states 
                        WHERE last_saved < datetime('now', ?)
                    """, (f'-{retention_days} days',))
                    records_removed = cursor.rowcount
                    conn.commit()
                finally:
                    conn.close()
            
            # 2. Cleanup legacy JSON files
            import glob
            import time
            now_ts = time.time()
            retention_secs = retention_days * 24 * 3600
            
            legacy_files = glob.glob(os.path.join(self.state_dir, "*.json"))
            for f in legacy_files:
                try:
                    if now_ts - os.path.getmtime(f) > retention_secs:
                        space_freed_bytes += os.path.getsize(f)
                        os.remove(f)
                        legacy_files_removed += 1
                except OSError:
                    continue
        except Exception as e:
            logger.error(f"Error in cleanup_old_states: {e}")
            
        return (records_removed, legacy_files_removed, space_freed_bytes // 1024)
    
    def get_state_dir_stats(self) -> dict:
        """Get statistics about the state database and legacy files."""
        import glob
        
        legacy_files = glob.glob(os.path.join(self.state_dir, "*.json"))
        db_size = 0
        if os.path.exists(self.db_path):
            db_size = os.path.getsize(self.db_path)
            
        row_count = 0
        try:
            conn = self._get_connection()
            try:
                cursor = conn.execute("SELECT COUNT(*) FROM session_states")
                row_count = cursor.fetchone()[0]
            finally:
                conn.close()
        except Exception:
            pass
            
        return {
            "db_sessions": row_count,
            "db_size_kb": db_size // 1024,
            "legacy_files": len(legacy_files),
            "state_dir": self.state_dir,
        }


# Global state manager instance
_state_manager = StateManager()


# Active session tracking (for orchestrator-to-tools communication)
_active_session_id: Optional[str] = None
_fallback_session_id: Optional[str] = None

def set_active_session_id(session_id: str) -> None:
    """
    Set the globally active session ID. This is used during pipeline runs so
    that tools can determine which session state file to read/write when the
    internal ADK tool_context does not expose the session_id directly.
    """
    global _active_session_id
    _active_session_id = session_id

def get_active_session_id() -> str:
    """
    Retrieve the globally active session ID if one has been set.
    If none is set, generates and caches a stable fallback ID so that 
    all subagents in a single execution share the exact same state file.

    Returns:
        The active session ID or a stable generated fallback ID.
    """
    global _active_session_id, _fallback_session_id
    if _active_session_id:
        return _active_session_id
    
    if not _fallback_session_id:
        _fallback_session_id = "run_" + str(uuid.uuid4())[:8]
    
    return _fallback_session_id


def get_state_manager() -> StateManager:
    """
    Get global state manager instance.
    
    Returns:
        StateManager instance
    """
    return _state_manager


def initialize_state(tool_context) -> Dict[str, Any]:
    """
    Initialize session state with defaults.
    
    Args:
        tool_context: ADK tool context
        
    Returns:
        Initialized state dictionary
    """
    state_manager = get_state_manager()
    
    # Try to load existing state
    session_id = str(id(tool_context.state))
    existing_state = state_manager.load_state(session_id)
    
    if existing_state:
        # Validate and return existing state
        return state_manager.validate_state(existing_state)
    else:
        # Create new state
        new_state = {
            "connection_established": False,
            "schema": {},
            "tables_scanned": False,
            "profiling_complete": False,
            "relationships": [],
            "changes": [],
            "llm_insights": {},
            "report_path": "",
            "json_report_path": "",
            "current_step": 0,
            "total_steps": 6,
            "steps_completed": [],
        }
        
        # Save initial state
        state_manager.save_state(session_id, new_state)
        
        return new_state


def save_current_state(tool_context) -> bool:
    """
    Save current session state.
    
    Args:
        tool_context: ADK tool context
        
    Returns:
        True if successful, False otherwise
    """
    state_manager = get_state_manager()
    # try to use a context attribute first, then fall back to the globally
    # active session ID; finally use the state object's id as a last resort
    from adk_agents.state_manager import get_active_session_id
    session_id = (getattr(tool_context, 'session_id', None)
                  or get_active_session_id()
                  or str(id(tool_context.state)))
    
    # Validate state before saving
    validated_state = state_manager.validate_state(tool_context.state)
    
    # Update tool_context.state with validated state
    tool_context.state.update(validated_state)
    
    # Save to file
    return state_manager.save_state(session_id, validated_state)


def update_step_progress_state(state: dict, step_name: str, session_id: str, tool_context=None) -> None:
    """
    Update pipeline step progress in a state dict and optionally tool_context.
    
    Args:
        state: State dictionary
        step_name: Name of completed step
        session_id: Session ID for saving
        tool_context: Optional ADK tool context to sync with
    """
    if "steps_completed" not in state:
        state["steps_completed"] = []
    
    if step_name not in state["steps_completed"]:
        state["steps_completed"].append(step_name)
    
    # Update current step based on completed steps
    step_mapping = {
        "metadata": 1,
        "metadata_scanning": 1,
        "profiler": 2,
        "data_profiling": 2,
        "relations": 3,
        "relationship_detection": 3,
        "drift": 4,
        "drift_detection": 4,
        "insights": 5,
        "llm_insights": 5,
        "reporter": 6,
        "report_generation": 6,
    }
    
    if step_name in step_mapping:
        target_step = step_mapping[step_name]
        # Only advance, never regress the current step
        if state.get("current_step", 0) < target_step:
            state["current_step"] = target_step
    
    # Optional: sync to tool_context memory
    if tool_context and hasattr(tool_context, "state"):
        for k, v in state.items():
            tool_context.state[k] = v
    
    # Save updated state
    state_manager = get_state_manager()
    state_manager.save_state(session_id, state)


def update_step_progress(tool_context, step_name: str) -> None:
    """
    Update pipeline step progress.
    
    Args:
        tool_context: ADK tool context
        step_name: Name of completed step
    """
    if "steps_completed" not in tool_context.state:
        tool_context.state["steps_completed"] = []
    
    if step_name not in tool_context.state["steps_completed"]:
        tool_context.state["steps_completed"].append(step_name)
    
    # Update current step based on completed steps
    step_mapping = {
        "metadata": 1,
        "metadata_scanning": 1,
        "profiler": 2,
        "data_profiling": 2,
        "relations": 3,
        "relationship_detection": 3,
        "drift": 4,
        "drift_detection": 4,
        "insights": 5,
        "llm_insights": 5,
        "reporter": 6,
        "report_generation": 6,
    }
    
    if step_name in step_mapping:
        target_step = step_mapping[step_name]
        # Only advance, never regress the current step
        if tool_context.state.get("current_step", 0) < target_step:
            tool_context.state["current_step"] = target_step
    
    # Save updated state
    save_current_state(tool_context)


def check_prerequisites_state(state: dict, required_state_keys: list) -> Dict[str, Any]:
    """
    Check if prerequisites are met in a state dict.
    
    Args:
        state: State dictionary
        required_state_keys: List of required state keys
        
    Returns:
        Dictionary with status and missing prerequisites
    """
    logger.debug(f"Checking prerequisites: {required_state_keys}")
    logger.debug(f"Available state keys: {list(state.keys())}")
    
    missing = []
    
    for key in required_state_keys:
        if key not in state:
            missing.append(key)
            logger.debug(f"Missing: {key} (key not present)")
        else:
            val = state[key]
            # treat None or False as missing
            if val is None or (isinstance(val, bool) and val is False):
                missing.append(key)
                logger.debug(f"Missing: {key} (falsey value)")
            # treat dicts and strings with length 0 as missing
            elif isinstance(val, (dict, str)) and len(val) == 0:
                missing.append(key)
                logger.debug(f"Missing: {key} (empty)")
            else:
                # lists are allowed to be empty; other types non-empty
                logger.debug(f"Found: {key} = {val}")
    
    if missing:
        result = {
            "status": "error",
            "missing_prerequisites": missing,
            "message": f"Missing prerequisites: {', '.join(missing)}"
        }
        logger.error(f"Prerequisites check failed: {result['message']}")
        return result
    else:
        result = {
            "status": "success",
            "message": "All prerequisites met"
        }
        logger.success("Prerequisites check passed")
        return result


def check_prerequisites(tool_context, required_state_keys: list) -> Dict[str, Any]:
    """
    Check if prerequisites are met.
    
    Args:
        tool_context: ADK tool context
        required_state_keys: List of required state keys
        
    Returns:
        Dictionary with status and missing prerequisites
    """
    logger.debug(f"Checking prerequisites: {required_state_keys}")
    logger.debug(f"Available state keys: {list(tool_context.state.keys())}")
    
    missing = []
    
    for key in required_state_keys:
        if key not in tool_context.state or not tool_context.state[key]:
            missing.append(key)
            logger.debug(f"Missing: {key}")
        else:
            logger.debug(f"Found: {key} = {tool_context.state[key]}")
    
    if missing:
        result = {
            "status": "error",
            "missing_prerequisites": missing,
            "message": f"Missing prerequisites: {', '.join(missing)}"
        }
        logger.error(f"Prerequisites check failed: {result['message']}")
        return result
    else:
        result = {
            "status": "success",
            "message": "All prerequisites met"
        }
        logger.success("Prerequisites check passed")
        return result


def validate_tool_execution(tool_context, tool_name: str, expected_state_changes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate that a tool execution produced expected state changes.
    
    Args:
        tool_context: ADK tool context
        tool_name: Name of the tool that was executed
        expected_state_changes: Dictionary of expected state key-value pairs
        
    Returns:
        Validation result dictionary
    """
    logger.debug(f"Validating tool execution: {tool_name}")
    
    validation_issues = []
    
    for key, expected_value in expected_state_changes.items():
        actual_value = tool_context.state.get(key)
        
        if expected_value is True and actual_value is not True:
            validation_issues.append(f"Expected {key} to be True, got {actual_value}")
        elif expected_value == "non_empty" and not actual_value:
            validation_issues.append(f"Expected {key} to be non-empty, got {actual_value}")
        elif expected_value == "populated" and (not actual_value or len(actual_value) == 0):
            validation_issues.append(f"Expected {key} to be populated, got {actual_value}")
        
        logger.debug(f"{key}: expected={expected_value}, actual={actual_value}")
    
    if validation_issues:
        result = {
            "status": "error",
            "issues": validation_issues,
            "message": f"Tool validation failed: {'; '.join(validation_issues)}"
        }
        logger.error(f"Tool validation failed: {result['message']}")
        return result
    else:
        result = {
            "status": "success",
            "message": f"Tool {tool_name} validation passed"
        }
        logger.success(f"Tool validation passed for {tool_name}")
        return result


# Export public functions
__all__ = [
    "StateManager",
    "get_state_manager",
    "initialize_state",
    "save_current_state",
    "update_step_progress",
    "check_prerequisites",
    "check_prerequisites_state",
    "update_step_progress_state",
    "set_active_session_id",
    "get_active_session_id",
    "validate_tool_execution",
]