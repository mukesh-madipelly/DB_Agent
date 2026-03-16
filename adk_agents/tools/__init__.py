"""
ADK Function Tools

This module contains ADK-compatible function tools converted from the original agents.
Each tool is a Python function with proper docstrings that ADK can understand.
"""

from .metadata_tools import scan_database_tables
from .profiler_tools import analyze_column_statistics
from .relations_tools import detect_table_relationships
from .drift_tools import detect_schema_changes
from .llm_insights_tools import generate_business_insights
from .reporter_tools import generate_comprehensive_report
from .custom_data_tools import execute_ad_hoc_query
from .quality_audit_tool import audit_data_quality
from .connection_tools import get_database_connection, establish_database_connection
from .query_cache import get_query_cache

__all__ = [
    'scan_database_tables',
    'analyze_column_statistics',
    'detect_table_relationships',
    'detect_schema_changes',
    'generate_business_insights',
    'generate_comprehensive_report',
    'execute_ad_hoc_query',
    'audit_data_quality',
    'get_database_connection',
    'establish_database_connection',
    'get_query_cache'
]
