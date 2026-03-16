# 🧠 DB Agent (ADK Edition)

An automated, AI-powered system for deep database analysis, schema drift detection, and business insight generation using **Google's Agent Development Kit (ADK)** and **Gemini LLMs**.

---

## 🌟 Executive Summary

The **Database Intelligence Agent** is designed to provide visibility into complex database environments. It serves as an automated "DBA Assistant" that scans Snowflake or PostgreSQL databases, profiles data quality, detects orphaned relationships, tracks historical schema changes, and synthesizes technical data into business-relevant insights.

---

## 🚀 How It Works: The Pipeline Architecture

The system operates as a **sequential pipeline** of specialized AI agents. Each agent handles a specific domain of knowledge, passing its findings to the next step via a persistent session state.

1.  **Metadata Agent**: Scans the database catalog to extract table names, column types, and primary keys.
2.  **Profiler Agent**: Samples data to calculate null percentages, distinct counts, and value ranges for every column.
3.  **Relations Agent**: Uses an LLM to identify potential foreign-key relationships that aren't explicitly defined in the DDL.
4.  **Drift Agent**: Compares the current scan against a stored `schema_snapshot.json` to detect added, removed, or modified columns/tables.
5.  **Insights Agent**: Consumes all technical metadata and generates higher-level business observations (e.g., "Table X contains sensitive PII but has no last_updated column").
6.  **Reporter Agent**: Aggregates all findings into a structured Markdown executive summary and a machine-readable JSON export.

---

## 📂 Project Structure

```text
DB_Agent/
├── adk_agents/             # 🤖 ADK CORE (Conversational Framework)
│   ├── agents/             # Individual agent personality definitions
│   ├── tools/              # Py-functions the agents call (SQL runners, File writers)
│   ├── workflows/          # High-level pipeline flow definitions
│   ├── orchestrator.py     # Controls sequential execution & rate limiting
│   └── state_manager.py    # Manages JSON-based persistence between 
│
├── .env.example            # 🔑 Template for credentials (REDATED)
├── main_adk.py             # 🏁 Main entry point for the ADK system
├── config.py               # ⚙️ Central configuration (reads from .env)
├── connector.py            # 🔌 Database connection abstraction
├── requirements.txt        # 📦 Python dependency list
├── SETUP_GUIDE.md          # 📖 Step-by-step installation instructions
└── state/                  # 💾 (Auto-generated) Stores session state JSONs
```

---

## 🛠️ Step-by-Step Setup

### 1. Environment Preparation
```powershell
# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 2. Configuration
1. Rename `.env.example` to `.env`.
2. Enter your **Google Gemini API Key**.
3. Set your `DB_TYPE` (`snowflake` or `postgresql`).
4. Enter your connection credentials.

### 3. Execution Options

#### Option A: Automated Pipeline (CLI)
To trigger the full automated intelligence cycle in the terminal:
```bash
python main_adk.py run-pipeline
```

#### Option B: Interactive Conversational Mode (Web UI)
This system supports a full conversational interface via the ADK Web server.
```bash
# Start the interactive server
adk web .
```
1. Open the provided link (e.g., `http://127.0.0.1:8000/`) in your browser.
2. Enter natural language instructions (e.g., *"Run the database intelligence pipeline"* or *"Scan my Snowflake metadata"*).
3. Watch the agents collaborate in real-time.

---

## 📊 Output Artifacts

- **Executive Report** (`db_report_... .md`): Structured summary with tables, relationship maps, and AI insights.
- **Intelligence Export** (`db_intelligence_... .json`): Full technical data dump for integration with other analytics tools.

---

## 🛡️ Security & Safety

- **Read-Only Access**: All database sessions are strictly set to `READ ONLY`. The agent cannot modify data, drop tables, or alter schema.
- **Redacted Secrets**: No credentials are ever stored in the `db_intelligence` JSON exports or the Markdown reports.
- **Rate Limit Intelligent**: Built-in 2-second delays (configurable) prevent API throttling on free-tier Gemini keys.


