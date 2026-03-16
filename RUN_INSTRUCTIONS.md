# 🚀 Quick Start Guide: Setup & Execution

Follow these steps to set up and run the Database Intelligence Agent on your local machine.

### 1. Environment Setup
Run these commands in your terminal (PowerShell/CMD) from the project root:

```powershell

# Create a fresh virtual environment
python -m venv .venv

# Activate the environment
.venv\Scripts\activate

# Install all required dependencies
pip install -r requirements.txt
```

### 2. Execution Commands

#### **A. Run Complete Pipeline (CLI)**
This runs the full automated analysis (Scanning -> Profiling -> Insights -> Report).
```powershell
python main_adk.py run-pipeline
```

#### **B. Run Interactive Chat (CLI Chat)**
This starts an interactive terminal session where you can ask specific questions about your data.
```powershell
python main_adk.py chat
```

#### **C. Launch Web Interface (ADK Web)**
This launches the full web-based dashboard for the agent.
```powershell
adk web .
```

#### **D. View All Options**
```powershell
python main_adk.py help
```

---
### 🛠️ Configuration
Before running any commands, ensure your **`.env`** file is configured:

1.  **Database Connection**:
    *   Set `DB_TYPE` to either `postgresql` or `snowflake`.
    *   Fill in the host, port, user, password, and database name.
2.  **AI Access**:
    *   Set `GOOGLE_API_KEY` with your Gemini API key.

All logic for switching between PostgreSQL and Snowflake is handled automatically based on your `.env` settings.
