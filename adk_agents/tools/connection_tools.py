"""
ADK Tools for Database Connection Management

Uses module-level connection cache to avoid pickle errors.
Connections are keyed by session_id and reused across all tools.
"""

from . import connector
from . import async_connector
from google.adk.tools.tool_context import ToolContext

# Module-level connection cache (NOT stored in session state)
_connection_cache = {}
_async_pool_cache = {}


async def get_async_database_pool(tool_context: ToolContext):
    """
    Gets or creates an asynchronous database pool for the current session.
    """
    from adk_agents.state_manager import get_active_session_id
    session_id = (
        getattr(tool_context, "session_id", None)
        or get_active_session_id()
        or str(id(tool_context.state))
    )

    if session_id in _async_pool_cache:
        # Check if pool is closed or dead
        pool = _async_pool_cache[session_id]
        # asyncpg pools don't have a simple .is_closed(), but we can check internal state or just return it
        return pool

    # Create new pool
    pool = await async_connector.create_async_db_pool()
    _async_pool_cache[session_id] = pool
    return pool


def get_database_connection(tool_context: ToolContext):
    """
    Gets or creates a database connection for the current session.
    
    This helper function manages connections at the module level to avoid
    pickle errors when storing in session state.
    
    Args:
        tool_context: ADK context with session_id
    
    Returns:
        Database connection object
    """
    from adk_agents.state_manager import get_active_session_id
    session_id = (getattr(tool_context, 'session_id', None)
                  or get_active_session_id()
                  or id(tool_context.state))  # Use session_id if available, else state id
    
    # Check if connection exists and is alive
    if session_id in _connection_cache:
        conn = _connection_cache[session_id]
        cursor = None
        try:
            # Test if connection is still alive
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            return conn
        except:
            # Connection is dead, remove it
            del _connection_cache[session_id]
        finally:
            if cursor:
                cursor.close()
    
    # Create new connection
    conn = connector.open_database_connection()
    _connection_cache[session_id] = conn
    
    return conn


def establish_database_connection(tool_context: ToolContext) -> dict:
    """Establishes a database connection and marks it in session state.
    
    This tool should be called FIRST before any other database tools.
    The actual connection is stored in a module-level cache, not in session state.
    
    Args:
        tool_context (ToolContext): ADK context for accessing session state
    
    Returns:
        dict: Connection status
    """
    try:
        # Check if already marked as established
        if tool_context.state.get("connection_established"):
            return {
                "status": "success",
                "message": "Database connection already established and reusing existing connection"
            }
        
        # Get or create connection (stored in module-level cache)
        conn = get_database_connection(tool_context)
        
        # Mark as established in state (but don't store the connection object)
        tool_context.state["connection_established"] = True
        from adk_agents.state_manager import save_current_state
        save_current_state(tool_context)
        
        return {
            "status": "success",
            "message": "Database connection established successfully"
        }
    
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to establish database connection: {str(e)}"
        }


async def close_database_connection(tool_context: ToolContext) -> dict:
    """Closes both sync connections and async pools for the current session."""
    try:
        from adk_agents.state_manager import get_active_session_id

        session_id = (
            getattr(tool_context, "session_id", None)
            or get_active_session_id()
            or str(id(tool_context.state))
        )

        results = []

        # 1. Close Sync Connection
        if session_id in _connection_cache:
            _connection_cache[session_id].close()
            del _connection_cache[session_id]
            results.append("Sync connection closed")

        # 2. Close Async Pool
        if session_id in _async_pool_cache:
            await _async_pool_cache[session_id].close()
            del _async_pool_cache[session_id]
            results.append("Async pool closed")

        # Update state
        tool_context.state["connection_established"] = False
        from adk_agents.state_manager import save_current_state

        save_current_state(tool_context)

        message = " and ".join(results) or "No active connections found"
        return {"status": "success", "message": message}

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to close connections: {str(e)}",
        }
