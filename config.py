import os

try:
    from dotenv import load_dotenv

    load_dotenv()  # Loads from a .env file if present (optional)
except ImportError:
    pass  # dotenv not installed – env vars / defaults will be used


# User's high-level business goal for the insights agent
INSIGHTS_GOAL = os.getenv(
    "INSIGHTS_GOAL",
    "Give me insights about my database schema and data to help me understand it better and make informed decisions.",
)

# ============================================
# ADK Configuration
# ============================================

# ADK requires this to determine which API to use
# FALSE = Gemini API (Google AI Studio) - for development
# TRUE = Vertex AI API (Google Cloud) - for production
GOOGLE_GENAI_USE_VERTEXAI = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")

# Google API Key (for Gemini API via Google AI Studio)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))

# ADK Application Name (identifies your app in session storage)
ADK_APP_NAME = os.getenv("ADK_APP_NAME", "db_intelligence_agent")


# ADK Model Configuration
ADK_MODEL = os.getenv("ADK_MODEL", "gemini-3.1-flash-lite-preview")

# ============================================
# Database Configuration
# ============================================

# Choose your database: "snowflake" | "postgresql"
DB_TYPE = os.getenv("DB_TYPE", "postgresql")

# Snowflake settings
SNOWFLAKE = {
    "account": os.getenv("SF_ACCOUNT", ""),
    "user": os.getenv("SF_USER", ""),
    "password": os.getenv("SF_PASSWORD", ""),
    "database": os.getenv("SF_DATABASE", ""),
    "schema": os.getenv("SF_SCHEMA", ""),
    "warehouse": os.getenv("SF_WAREHOUSE", ""),
    "role": os.getenv("SF_ROLE", ""),
}

# PostgreSQL settings
POSTGRESQL = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", ""),
    "password": os.getenv("DB_PASSWORD", ""),
    "dbname": os.getenv("DB_NAME", ""),
}

# PostgreSQL schema to scan
POSTGRESQL_SCHEMA = os.getenv("DB_SCHEMA", "public")

# ============================================
# Multi-API Key Configuration
# ============================================
GOOGLE_API_KEY_PRIMARY = os.getenv("GOOGLE_API_KEY_PRIMARY", GOOGLE_API_KEY)
GOOGLE_API_KEY_SECONDARY = os.getenv("GOOGLE_API_KEY_SECONDARY", GOOGLE_API_KEY)

# Per-Agent Model Configuration
AGENT_MODELS = {
    "metadata": os.getenv("METADATA_MODEL", ADK_MODEL),
    "profiler": os.getenv("PROFILER_MODEL", ADK_MODEL),
    "relations": os.getenv("RELATIONS_MODEL", ADK_MODEL),
    "graph": os.getenv("GRAPH_MODEL", ADK_MODEL),
    "drift": os.getenv("DRIFT_MODEL", ADK_MODEL),
    "insights": os.getenv("INSIGHTS_MODEL", ADK_MODEL),
    "reporter": os.getenv("REPORTER_MODEL", ADK_MODEL),
}

# Per-Agent API Key Configuration
AGENT_API_KEYS = {
    "metadata": os.getenv("METADATA_API_KEY", GOOGLE_API_KEY_PRIMARY),
    "profiler": os.getenv("PROFILER_API_KEY", GOOGLE_API_KEY_PRIMARY),
    "relations": os.getenv("RELATIONS_API_KEY", GOOGLE_API_KEY_PRIMARY),
    "graph": os.getenv("GRAPH_API_KEY", GOOGLE_API_KEY_PRIMARY),
    "drift": os.getenv("DRIFT_API_KEY", GOOGLE_API_KEY_PRIMARY),
    "insights": os.getenv("INSIGHTS_API_KEY", GOOGLE_API_KEY_SECONDARY),
    "reporter": os.getenv("REPORTER_API_KEY", GOOGLE_API_KEY_PRIMARY),
}

# ============================================
# Output & Snapshot Paths
# ============================================
SNAPSHOT_ROOT = os.getenv("SNAPSHOT_ROOT", "snapshots")
SNAPSHOT_PATH = os.getenv("SNAPSHOT_PATH", "schema_snapshot.json")
REPORT_DIR = os.getenv("REPORT_DIR", "reports")

# Legacy compatibility
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
GEMINI_API_KEY = GOOGLE_API_KEY
LLM_MODEL = ADK_MODEL
