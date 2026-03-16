# 🚀 Database Intelligence Agent: Comprehensive Setup Guide

This guide provides step-by-step instructions to get the **Database Intelligence Agent (ADK Version)** running on your local machine. This system uses Google's Agent Development Kit (ADK) to perform deep analysis of snowflake or PostgreSQL databases.

---

## 📋 1. Prerequisites

Before you begin, ensure you have the following:

- **Python**: Version 3.8 to 3.12 installed.
- **Git** (Optional): To clone the repository if not provided as a zip.
- **Google Gemini API Key**: 
  1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
  2. Click "Get API key" and create a new key.
  3. *Pro Tip:* Get two keys from two different accounts if you plan to scan very large databases to avoid rate limits.
- **Database Access**:
  - **Snowflake**: Account URL, Username, Password, Database, Schema, Warehouse, and Role.
  - **PostgreSQL**: Host, Port, Database Name, Username, and Password.

---

## 🛠️ 2. Installation & Environment Setup

### Step 1: Extract and Navigate
Unzip the provided package and open a terminal (PowerShell or Command Prompt) in the `DB_Agent` folder.

### Step 2: Create a Virtual Environment
It is highly recommended to use a virtual environment to avoid dependency conflicts.
```powershell
# Create environment
python -m venv .venv

# Activate environment (Windows)
.venv\Scripts\activate

# Activate environment (Mac/Linux)
source .venv/bin/activate
```

### Step 3: Install Dependencies
Install all required libraries including `google-adk`, `snowflake-connector`, and `rich`.
```bash
pip install -r requirements.txt
```

---

## ⚙️ 3. Configuration (.env)

The system relies on environment variables for security. Follow these steps carefully:

1.  Locate the `.env.example` file in the root directory.
2.  Duplicate it and rename the copy to exactly `.env`.
3.  Fill in the following sections:

### A. AI Credentials
- `GOOGLE_API_KEY`: Paste your primary Gemini API key here.
- `GOOGLE_GENAI_USE_VERTEXAI`: Keep as `FALSE` unless you are specifically using Google Cloud Vertex AI.

### B. Database Selection
- `DB_TYPE`: Set this to `snowflake` or `postgresql` depending on your source.

### C. Database Credentials
- Fill in the section corresponding to your `DB_TYPE`.
- **Snowflake Note:** Your `SF_ACCOUNT` is usually the part of your URL before `.snowflakecomputing.com`.
- **Postgres Note:** The default schema is `public`.

### D. Advanced: Rate Limit Distribution
If you have a second API key, fill in `GOOGLE_API_KEY_SECONDARY`. The system will automatically use it for the "Insights" agent to prevent the primary key from hitting rate limits.

---

## 🚀 4. Running the Intelligence Pipeline

### The Complete Run (Recommended)
This command triggers the full sequence: Connection -> Metadata -> Profiler -> Relations -> Graph -> Drift -> Insights -> Reporter.
### Option A: Complete Pipeline (CLI)
This runs the full automated analysis in a conversational mode, producing detailed reports and insights.
```bash
python main_adk.py run-pipeline
```

### Option B: Interactive Mode (Web UI)
Recommended for a visual experience. This allows you to interact with the agents using natural language in your browser.
```bash
adk web .
```
1.  Wait for the terminal to print: `Server started at http://127.0.0.1:8000/`
2.  Open that URL in your browser.
3.  Type a command like: **"Start the database intelligence pipeline"**
4.  Optionally, ask follow-up questions about your data!

### Option C: Individual Agents
If you only need specific components (e.g., just schema scanning or just AI insights):
```bash
python main_adk.py run-agent metadata   # Scan tables/columns
python main_adk.py run-agent profiler   # Analyze data quality
python main_adk.py run-agent insights   # Generate AI business insights
```

---

## 📂 5. Understanding the Output

Once the pipeline completes, check the current directory for:

1.  **MD Report** (`db_report_... .md`): A human-readable executive summary. Open this in VS Code or any Markdown viewer.
2.  **JSON Export** (`db_intelligence_... .json`): Machine-readable data containing everything the agents found.
3.  **Schema Snapshot** (`schema_snapshot.json`): A baseline file. If you run the agent again after making database changes, it will compare the new scan to this file to detect "Drift".
4.  **Schema Graph** (`schema_graph.png`): (Optional) A visual representation of your table relationships.

---

## ⚠️ 6. Troubleshooting

- **"Account is locked/invalid credentials"**: Double-check your `.env` file for typos. Ensure there are no spaces around the `=` signs.
- **"429 Resource Exhausted"**: This is a Gemini rate limit. Simply wait a minute and run again, or use the `10.0` delay flag.
- **"Module not found"**: Ensure your virtual environment is activated (`.venv\Scripts\activate`).
- **Missing data in reports**: Ensure the user provided in `.env` has `SELECT` permissions on the target database and schema.
