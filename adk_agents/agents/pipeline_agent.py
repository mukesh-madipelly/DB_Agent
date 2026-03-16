import config
from google.adk.agents import LlmAgent
from adk_agents.tools import (
    scan_database_tables,
    analyze_column_statistics,
    detect_table_relationships,
    detect_schema_changes,
    generate_business_insights,
    generate_comprehensive_report,
    execute_ad_hoc_query,
    audit_data_quality
)

def create_adaptive_pipeline_agent() -> LlmAgent:
    """
    Creates a 'Master Orchestrator' agent that intelligently manages the 
    database intelligence pipeline and handles ad-hoc user requests.
    """
    
    agent = LlmAgent(
        name="adaptive_pipeline",
        description="Master orchestrator for database intelligence analysis and reporting.",
        model=config.AGENT_MODELS.get("insights", config.ADK_MODEL),
        tools=[
            scan_database_tables,
            analyze_column_statistics,
            detect_table_relationships,
            detect_schema_changes,
            generate_business_insights,
            generate_comprehensive_report,
            execute_ad_hoc_query,
            audit_data_quality
        ],
        instruction="""
        You are the Master Database Architect. Your goal is to provide a comprehensive, up-to-date analysis of the database.

        ## MANDATORY CORE SEQUENCE (RUN EVERY TIME)
        You MUST run these tools in order in every 'run the pipeline' session, even if `ToolContext.state` indicates they were previously completed. Production data changes frequently; absolute freshness is required.
        1.  Execute `scan_database_tables`.
        2.  Execute `analyze_column_statistics`.
        3.  Execute `detect_table_relationships`.
        4.  Execute `detect_schema_changes`.
        5.  Execute `audit_data_quality` (PII compliance check).
        
        ## OPTIONAL & FINAL STEPS
        - **Ad-hoc Requests**: If the user asks a specific data question, call `execute_ad_hoc_query` anytime AFTER Step 2.
        - **Smart Insights**: Call `generate_business_insights`. 
          *OPTIMIZATION*: If Step 4 (`detect_schema_changes`) resulted in "No changes detected" AND `llm_insights` already exists in state, you may skip this step and use the existing insights.
        - **Final Reporting**: ALWAYS finish by calling `generate_comprehensive_report`.

        ## RULES
        - Do NOT skip Steps 1-5 based on state flags. ALWAYS re-run them for real-time accuracy.
        - If a tool fails, report it but try to proceed with subsequent mandatory steps.
        - Only call `generate_comprehensive_report` once at the very end.
        """
    )
    
    return agent
