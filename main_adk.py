"""
ADK Entry Point for Database Intelligence Pipeline

This is the main entry point for the ADK-based database intelligence system.
It initializes state management and provides hooks for running the pipeline.
"""

import os
import sys
import asyncio
from datetime import datetime
from google.adk import Runner
from adk_agents.state_manager import initialize_state, get_state_manager, save_current_state
from adk_agents.tools.connection_tools import establish_database_connection, close_database_connection
from adk_agents.logger import get_logger
import config


def initialize_session_state():
    """
    Initialize session state for ADK tools.
    
    Returns:
        dict: Initialized session state
    """
    # Create a mock tool_context for initialization
    class MockToolContext:
        def __init__(self):
            self.state = {}
    
    tool_context = MockToolContext()
    
    # Initialize state
    state = initialize_state(tool_context)
    tool_context.state = state
    
    return tool_context


async def run_complete_pipeline_async(custom_query_request: str = None, force_refresh: bool = False):
    """
    Run the complete database intelligence pipeline using the Adaptive Pipeline Agent.
    
    Args:
        custom_query_request: Optional user request for additional analysis.
        force_refresh: Whether to bypass cache and refresh all data.
    
    Returns:
        dict: Pipeline execution results
    """
    # Initialize session state and ID
    session_id = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    from adk_agents.state_manager import set_active_session_id, get_state_manager
    set_active_session_id(session_id)
    
    from google.adk import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as gt
    from adk_agents.agents.pipeline_agent import create_adaptive_pipeline_agent
    from adk_agents.tools.connection_tools import establish_database_connection, close_database_connection
    
    # Initialize tool context state
    tool_context = initialize_session_state()
    tool_context.session_id = session_id
    logger = get_logger(session_id)
    
    if force_refresh:
        tool_context.state["force_refresh"] = True
        logger.info("Cache bypass enabled for this run", icon="🔄")
    
    try:
        # Step 1: Open connection
        logger.info(f"Session ID: {session_id}", icon="🔑")
        logger.info("1️⃣  Establishing database connection...")
        establish_database_connection(tool_context)
        logger.success("Database connection established")
        
        # Step 2: Initialize Agentic Run
        agent = create_adaptive_pipeline_agent()
        session_service = InMemorySessionService()
        runner = Runner(
            app_name=config.ADK_APP_NAME,
            agent=agent,
            session_service=session_service,
            auto_create_session=True
        )        
        logger.info("2️⃣  Running Adaptive Database Intelligence Pipeline...", icon="🚀")
        logger.info("🤖 AGENT ORCHESTRATING", icon="🤖")
        
        prompt = "Analyze the database and generate a comprehensive report."
        if custom_query_request:
            prompt += f" Special Request: {custom_query_request}"
            
        user_id = "db_admin"
        message = gt.Content(role="user", parts=[gt.Part(text=prompt)])
        
        # [DEBUG] Tracing start of runner
        logger.info("Initializing ADK Runner session...")
        
        # Create the session with our initial state before running
        session = await session_service.create_session(
            app_name=config.ADK_APP_NAME, 
            user_id=user_id, 
            session_id=session_id
        )
        session.state.update(tool_context.state)
        
        logger.info(f"Submitting orchestration prompt to LLM: {config.ADK_MODEL}")
        
        event_count = 0
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message
        ):
            event_count += 1
            if event_count == 1:
                logger.info("First event received from LLM orchestrator.")
                
            if hasattr(event, 'text') and event.text:
                print(event.text, end="", flush=True)
        
        if event_count == 0:
            logger.warning("No events were received from the LLM orchestrator!")

        print("\n============================================================\n")
        
        # Reload state from disk to get final values
        sm = get_state_manager()
        final_state = sm.load_state(session_id) or {}
        
        logger.success("Orchestration complete")
        
    finally:
        # Step 3: Always close connection
        logger.info("3️⃣  Closing database connection...")
        await close_database_connection(tool_context)
        logger.success("Connection closed")
    
    return {
        "status": "success",
        "session_id": session_id,
        "state_summary": sm.get_state_summary(final_state),
        "report_path": final_state.get("report_path"),
        "json_report_path": final_state.get("json_report_path"),
        "agent_response": "Pipeline orchestrated successfully by Adaptive Agent.",
        "message": "Pipeline execution completed"
    }


def run_complete_pipeline(custom_query_request: str = None, force_refresh: bool = False):
    """
    Run the complete database intelligence pipeline (synchronous wrapper).
    
    Args:
        custom_query_request: Optional user request for additional analysis before report generation.
        force_refresh: Whether to bypass cache and refresh all data.
    
    Returns:
        dict: Pipeline execution results
    """
    return asyncio.run(run_complete_pipeline_async(custom_query_request, force_refresh))


async def run_individual_agent_async(agent_name: str):
    """
    Run an individual agent from the pipeline asynchronously.
    
    Args:
        agent_name: Name of the agent to run (metadata, profiler, relations, graph, drift, insights, reporter)
    
    Returns:
        dict: Agent execution results
    """
    print(f"🚀 Running {agent_name} agent")
    print("=" * 50)
    
    # Initialize session state
    tool_context = initialize_session_state()
    
    try:
        # Import the adaptive pipeline agent
        from adk_agents.agents.pipeline_agent import create_adaptive_pipeline_agent
        agent = create_adaptive_pipeline_agent()

        # Map legacy agent names to their primary tool
        tool_map = {
            "metadata": "scan_database_tables",
            "profiler": "analyze_column_statistics",
            "relations": "detect_table_relationships",
            "drift": "detect_schema_changes",
            "insights": "generate_business_insights",
            "reporter": "generate_comprehensive_report",
        }
        
        target_tool = tool_map.get(agent_name)
        if not target_tool:
            return {
                "status": "error",
                "message": f"Unknown agent/step: {agent_name}. Available: {', '.join(tool_map.keys())}"
            }

        
        # Create runner with InMemorySessionService
        from google.adk.sessions import InMemorySessionService
        from google.genai import types
        
        session_service = InMemorySessionService()
        runner = Runner(
            app_name=f"db_intelligence_{agent_name}",
            agent=agent,
            session_service=session_service,
            auto_create_session=True
        )
        
        # Run the agent with a message
        user_id = "db_admin"
        session_id = f"{agent_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        message = types.Content(
            role="user",
            parts=[types.Part(text=f"Run the {agent_name} agent")]
        )
        
        result_text = ""
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message
        ):
            if hasattr(event, 'text') and event.text:
                result_text += event.text
                print(event.text, end='', flush=True)
        
        print()
        # Update progress and save state
        from adk_agents.state_manager import update_step_progress_state
        state = get_state_manager().load_state(session_id)
        update_step_progress_state(state, "metadata", session_id, tool_context)
        # Also save the context (keeps connection_established, etc.)
        save_current_state(tool_context)
        
        print(f"\n✅ {agent_name} agent execution completed")
        return {
            "status": "success",
            "agent": agent_name,
            "result": result_text,
            "message": f"{agent_name} agent execution completed"
        }
    
    except Exception as e:
        print(f"\n❌ {agent_name} agent execution failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "agent": agent_name,
            "error": str(e),
            "message": f"{agent_name} agent execution failed: {str(e)}"
        }


def run_individual_agent(agent_name: str):
    """
    Run an individual agent from the pipeline (synchronous wrapper).
    
    Args:
        agent_name: Name of the agent to run
    
    Returns:
        dict: Agent execution results
    """
    return asyncio.run(run_individual_agent_async(agent_name))


def load_previous_state(session_id: str):
    """
    Load previous session state.
    
    Args:
        session_id: Session identifier
    
    Returns:
        dict: Loaded state information
    """
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id)
    
    if state:
        print(f"✅ Loaded state for session: {session_id}")
        summary = state_manager.get_state_summary(state)
        return {
            "status": "success",
            "session_id": session_id,
            "state": state,
            "summary": summary,
            "message": f"State loaded for session {session_id}"
        }
    else:
        return {
            "status": "error",
            "session_id": session_id,
            "message": f"No state found for session {session_id}"
        }


def chat(session_id: str = ""):
    """
    Start an interactive chat session using the root agent and ADK Runner.
    This allows the agent to handle both Q&A and pipeline execution.

    Usage:
        python main_adk.py chat
        python main_adk.py chat pipeline_20260311_190156   # specific session
    """
    import asyncio
    import glob
    from adk_agents.state_manager import get_state_manager, set_active_session_id
    from adk_agents.agents.root_agent import create_root_agent
    from google.adk import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as gt

    state_manager = get_state_manager()

    # ── Auto-discover latest session ──────────────────────────────────────
    if not session_id:
        latest_session = state_manager.get_latest_session_id("pipeline_")
        if latest_session:
            session_id = latest_session
            print(f"📂 Auto-loaded latest session: {session_id}")
        else:
            session_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            print(f"🆕 Starting new session: {session_id}")

    set_active_session_id(session_id)
    
    # ── Initialize ADK Runner ─────────────────────────────────────────────
    agent = create_root_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="db_intelligence_chat",
        agent=agent,
        session_service=session_service,
        auto_create_session=True
    )

    print("\n" + "=" * 60)
    print("💬 DB INTELLIGENCE CHAT  (type 'exit' or 'quit' to stop)")
    print(f"📊 Session: {session_id}  |  Model: {config.ADK_MODEL}")
    print("   🚀 I can answer questions or run the full pipeline (just ask!)")
    print("=" * 60 + "\n")

    async def chat_loop():
        # Ensure database connection is established for tools
        from adk_agents.tools.connection_tools import establish_database_connection
        class MockContext:
            def __init__(self):
                self.state = {}
                self.session_id = session_id
        ctx = MockContext()
        establish_database_connection(ctx)

        user_id = "db_admin"
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n👋 Chat ended.")
                break

            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("👋 Chat ended.")
                break

            print("Agent: ", end="", flush=True)
            try:
                message = gt.Content(role="user", parts=[gt.Part(text=user_input)])
                async for event in runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=message
                ):
                    if hasattr(event, 'text') and event.text:
                        print(event.text, end="", flush=True)
            except Exception as exc:
                print(f"\n❌ Error: {exc}")
            print("\n")

    asyncio.run(chat_loop())


def run_report_customization_silent_tool_call(session_id: str, user_request: str):
    """
    Execute a custom query directly to answer the user's request.
    This is used during pipeline execution before report generation.
    
    Args:
        session_id (str): The pipeline session.
        user_request (str): The user's additional analysis request (natural language).
    
    Returns:
        dict: Status and results.
    """
    from adk_agents.tools.custom_data_tools import execute_ad_hoc_query
    from adk_agents.state_manager import set_active_session_id, get_state_manager
    
    set_active_session_id(session_id)
    
    # Create a mock tool context
    class MockContext:
        def __init__(self):
            self.state = {}
            self.session_id = session_id
    
    tool_context = MockContext()
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id) or {}
    tool_context.state = state
    
    try:
        # Execute the query using the tool (which generates its own SQL internally)
        result = execute_ad_hoc_query(tool_context, user_request)
        
        return {
            "status": "success",
            "query_executed": result.get("query_executed", "Dynamic SQL"),
            "tool_result": result,
            "message": "Custom query executed and results added to state."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to execute custom query: {str(e)}"
        }



def run_report_customization(session_id: str, user_request: str):
    """
    Run the report customization agent to handle additional user analysis requests post-pipeline.
    1. Loads the session state.
    2. Invokes the report_customization_agent with the user's request.
    3. Re-runs the report generator to include new findings.
    Args:
        session_id (str): The pipeline session to augment.
        user_request (str): The user's additional analysis request (natural language).
    Returns:
        dict: Status and updated report paths.
    """
    from adk_agents.agents.report_customization_agent import create_report_customization_agent
    from adk_agents.tools.reporter_tools import generate_comprehensive_report
    from google.adk import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types as gt
    from adk_agents.state_manager import set_active_session_id, get_state_manager

    set_active_session_id(session_id)
    agent = create_report_customization_agent()
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="db_report_customization",
        agent=agent,
        session_service=session_service,
        auto_create_session=True
    )
    user_id = "db_admin"
    message = gt.Content(role="user", parts=[gt.Part(text=user_request)])
    # Run the agent to process the custom request
    result_text = ""
    import asyncio
    async def run_agent():
        nonlocal result_text
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message
        ):
            if hasattr(event, 'text') and event.text:
                result_text += event.text
    asyncio.run(run_agent())
    # Re-run the report generator to include new findings
    from adk_agents.state_manager import get_state_manager
    tool_context = type('MockContext', (), {'state': {}, 'session_id': session_id})()
    state_manager = get_state_manager()
    state = state_manager.load_state(session_id) or {}
    tool_context.state = state
    report_result = generate_comprehensive_report(tool_context)
    return {
        "status": "success",
        "customization_response": result_text,
        "report_path": report_result.get("report_path"),
        "json_report_path": report_result.get("json_report_path"),
        "message": "Report updated with additional analysis."
    }


def main():
    """
    Main entry point for ADK database intelligence.
    
    Usage:
        python main_adk.py [command] [args]
        
    Commands:
        run-pipeline [delay]  Run the complete pipeline
        run-agent <name>      Run a specific agent
        load-state <id>       Load previous session state
        chat [session_id]     Interactive Q&A on database (uses latest session)
        help                  Show this help message
    """
    if len(sys.argv) < 2:
        print("Usage: python main_adk.py [command] [args]")
        print("\nCommands:")
        print("  run-pipeline [delay]  Run the complete pipeline (default delay: 2.0s)")
        print("  run-agent <name>      Run a specific agent")
        print("  load-state <id>       Load previous session state")
        print("  chat [session_id]     Ask anything about your database (uses latest run)")
        print("  help                  Show this help message")
        return
    
    command = sys.argv[1].lower()
    
    if command == "run-pipeline":
        force_refresh = "--force-refresh" in sys.argv
        result = run_complete_pipeline(force_refresh=force_refresh)
        print(f"\nResult: {result.get('status', 'unknown')}")
        print(f"Message: {result.get('message', 'No message')}")
        
        if result.get('status') == 'success':
            print(f"\nPipeline finished. State summary:")
            print(result.get("state_summary", ""))
            if result.get('failed_steps'):
                print(f"Failed steps: {', '.join(result.get('failed_steps', []))}")
    
    elif command == "run-agent":
        if len(sys.argv) < 3:
            print("Error: Agent name required")
            print("Usage: python main_adk.py run-agent <agent_name>")
            print("Available agents: metadata, profiler, relations, graph, drift, insights, reporter")
            return
        
        agent_name = sys.argv[2].lower()
        result = run_individual_agent(agent_name)
        print(f"\nResult: {result.get('status', 'unknown')}")
        print(f"Message: {result.get('message', 'No message')}")
    
    elif command == "load-state":
        if len(sys.argv) < 3:
            print("Error: Session ID required")
            print("Usage: python main_adk.py load-state <session_id>")
            return
        
        session_id = sys.argv[2]
        result = load_previous_state(session_id)
        print(f"\nResult: {result.get('status', 'unknown')}")
        print(f"Message: {result.get('message', 'No message')}")
        
        if result.get("status") == "success":
            summary = result.get("summary", {})
            print(f"\nState Summary:")
            for key, value in summary.items():
                print(f"  {key}: {value}")
    
    elif command == "chat":
        sid = sys.argv[2] if len(sys.argv) >= 3 else ""
        chat(session_id=sid)


    elif command == "help":
        print("ADK Database Intelligence System")
        print("=" * 40)
        print("\nThis system provides comprehensive database analysis including:")
        print("  - Schema scanning and metadata extraction")
        print("  - Data profiling and quality analysis")
        print("  - Relationship detection")
        print("  - Drift detection")
        print("  - LLM-powered business insights")
        print("  - Comprehensive report generation")
        
        print("\nUsage:")
        print("  python main_adk.py run-pipeline [--force-refresh]")
        print("    - --force-refresh: Ignore cache and re-execute all queries")
        print("  python main_adk.py run-pipeline-with-query <user_request> [--force-refresh]")
        print("  python main_adk.py run-agent <agent_name>")
        print("  python main_adk.py load-state <session_id>")
        print("  python main_adk.py chat [session_id]")
        print("    - Starts interactive Q&A using the latest (or specified) pipeline session")
        print("  python main_adk.py clear-cache")
        print("    - Clear all cached query results")
        print("  python main_adk.py cache-stats")
        print("    - Show cache statistics and expiration info")
        print("  python main_adk.py cleanup-states [days]")
        print("    - Remove state files older than N days (default: 30)")
        print("  python main_adk.py state-stats")
        print("    - Show state directory statistics")
        print("  python main_adk.py help")
        
        print("\nConfiguration:")
        print("  - Set database credentials in .env file")
        print("  - Configure Gemini API key for LLM insights")
        print("  - Adjust settings in config.py")
        print("  - Model: Set ADK_MODEL in .env (default: gemini-3.1-flash-lite-preview)")
        
        print("\nCaching & Cleanup:")
        print("  - Schema and profiling results cached for 24 hours (default)")
        print("  - Disable caching by setting QUERY_CACHE_DISABLED=TRUE in .env")
        print("  - TTL: Set QUERY_CACHE_TTL_HOURS in .env (default: 24)")
        print("  - Cache location: .cache/ directory (set QUERY_CACHE_DIR in .env)")
        print("  - Use 'clear-cache' command to remove all cached data")
        print("  - State files archived after 30 days; use 'cleanup-states' to remove old files")
        print("  - Free up disk space with 'cleanup-states' to delete files older than N days")

    elif command == "clear-cache":
        from adk_agents.tools.query_cache import get_query_cache
        cache = get_query_cache()
        count = cache.clear()
        print(f"✅ Cleared {count} cache entries")
        
    elif command == "cache-stats":
        from adk_agents.tools.query_cache import get_query_cache
        cache = get_query_cache()
        stats = cache.get_stats()
        print("\n📊 Cache Statistics:")
        print(f"  Total cached files: {stats['total_files']}")
        print(f"  Total size: {stats['total_size_bytes'] / 1024:.1f} KB")
        print(f"  Expired files: {stats['expired_files']}")
        print(f"  Cache directory: {stats['cache_dir']}")
        print(f"  TTL: {stats['ttl_hours']} hours")
        print(f"  Cleanup expired: {cache.cleanup_expired()} files removed")
    
    elif command == "cleanup-states":
        from adk_agents.state_manager import get_state_manager
        import os
        
        retention_days = 30
        if len(sys.argv) >= 3:
            try:
                retention_days = int(sys.argv[2])
            except ValueError:
                pass
        
        sm = get_state_manager()
        stats_before = sm.get_state_dir_stats()
        files_removed, files_kept, space_freed_kb = sm.cleanup_old_states(retention_days)
        stats_after = sm.get_state_dir_stats()
        
        print(f"\n🧹 State File Cleanup (retention: {retention_days} days)")
        print(f"  Files removed: {files_removed}")
        print(f"  Files kept: {files_kept}")
        print(f"  Space freed: {space_freed_kb} KB")
        print(f"\nBefore: {stats_before['total_files']} files, {stats_before['total_size_kb']} KB")
        print(f"After: {stats_after['total_files']} files, {stats_after['total_size_kb']} KB")
    
    elif command == "state-stats":
        from adk_agents.state_manager import get_state_manager
        
        sm = get_state_manager()
        stats = sm.get_state_dir_stats()
        
        print(f"\n📁 State Directory Statistics:")
        print(f"  Total files: {stats['total_files']}")
        print(f"  Total size: {stats['total_size_kb']} KB")
        print(f"  Location: {stats['state_dir']}")
    
    else:
        print(f"Error: Unknown command '{command}'")
        print("Use 'python main_adk.py help' for usage information")


if __name__ == "__main__":
    main()
