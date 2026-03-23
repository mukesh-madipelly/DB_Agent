"""
Root Agent - Main Orchestrator for Database Intelligence Pipeline

This is the main agent that orchestrates all database analysis agents.
It manages user interaction and delegates specialized tasks to sub-agents.
"""

from google.adk.agents import Agent
from adk_agents.agents.pipeline_agent import create_adaptive_pipeline_agent
import config


def create_root_agent() -> Agent:
    """
    Creates the root interactive agent.
    It manages user intent and delegates to specialized sub-agents.
    """

    pipeline_agent = create_adaptive_pipeline_agent()

    # Root agent — Interactive interface
    root_agent = Agent(
        name="root_agent",
        description="Root orchestrator for database intelligence analysis",
        model=config.ADK_MODEL,
        tools=[],  # No hardcoded multi-step tools; orchestration is agentic now
        instruction="""
        You are the Global Database Analyst. Your role is to understand user intentions and coordinate database analysis.

        ## DELEGATION
        - If the user wants ANY kind of database analysis (e.g., "run the pipeline", "analyze the DB", 
          "find specific data", "check for changes", or "generate a report"):
          - IMMEDIATELY transfer the conversation to the `adaptive_pipeline` agent.
          - Do NOT try to run steps yourself.

        ## CONVERSATION
        - Answer general questions about the system directly.
        - After a report is generated, stay available to discuss the results 
          using the shared session state.

        ## PRIVACY & SAFETY
        - Always respect the read-only constraints of the underlying tools.
        """,
        sub_agents=[pipeline_agent],
    )

    return root_agent


# Export the agent creation function
__all__ = ["create_root_agent"]
