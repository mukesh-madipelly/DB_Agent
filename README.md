# DB Agent (ADK) - Database Intelligence Analysis Tool

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)

A powerful, AI-powered database intelligence agent built with Google ADK (Agent Development Kit). This tool automatically analyzes your database, generates insights, detects changes, and creates comprehensive reports—all without requiring any technical expertise.

## 🚀 What is DB Agent?

DB Agent is an intelligent assistant that makes database analysis accessible to everyone. It can:

- **Scan** your database schema and metadata
- **Profile** data quality and statistics
- **Detect** table relationships and foreign keys
- **Monitor** schema changes (drift detection)
- **Generate** business insights using AI
- **Audit** data for PII and quality issues
- **Create** detailed reports in Markdown and JSON formats

The agent understands natural language questions and can answer specific queries about your data, making complex database analysis as simple as asking a question.

## ✨ Key Features

- **Zero Technical Knowledge Required**: Works through simple CLI commands or web interface
- **Multi-Database Support**: PostgreSQL and Snowflake
- **AI-Powered Insights**: Uses Google Gemini for intelligent analysis
- **Comprehensive Reporting**: Generates human-readable reports and structured JSON data
- **Change Detection**: Tracks schema drift over time
- **Data Quality Auditing**: Identifies PII and data quality issues
- **Caching System**: Speeds up repeated analyses
- **Session Management**: Maintains state across analysis sessions

## 📋 Prerequisites

- Python 3.8 or higher
- Access to a PostgreSQL or Snowflake database
- Google AI Studio API key (for AI insights)
- Docker (optional, for containerized deployment)

## 🛠️ Installation

### Option 1: Local Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mukesh-madipelly/DB_Agent.git
   cd db-agent-adk
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Option 2: Docker Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mukesh-madipelly/DB_Agent.git
   cd db-agent-adk
   ```

2. **Build the Docker image:**
   ```bash
   docker build -t db-agent-adk .
   ```

## ⚙️ Configuration

### Environment Variables (.env file)

Create a `.env` file in the project root directory with the following variables:

```env
# Database Configuration
DB_TYPE=postgresql  # or 'snowflake'
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database_name
DB_USER=your_username
DB_PASSWORD=your_password
POSTGRESQL_SCHEMA=public  # For PostgreSQL only

# For Snowflake (if using DB_TYPE=snowflake)
SNOWFLAKE_ACCOUNT=your_account
SNOWFLAKE_USER=your_username
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_DATABASE=your_database
SNOWFLAKE_SCHEMA=your_schema
SNOWFLAKE_WAREHOUSE=your_warehouse

# AI Configuration
GOOGLE_API_KEY=your_google_ai_studio_api_key
ADK_MODEL=gemini-3.1-flash-lite-preview

# Application Settings
ADK_APP_NAME=db_intelligence_agent
INSIGHTS_GOAL=Analyze the latest license trends and user growth.

# Optional Settings
QUERY_CACHE_DISABLED=FALSE
QUERY_CACHE_TTL_HOURS=24
```

### Database Permissions

Your database user needs `SELECT` permissions on the target database and schema. The agent operates in read-only mode and never modifies your data.

## 🚀 Usage

### Local Usage

1. **Activate virtual environment:**
   ```bash
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

2. **Run the complete pipeline:**
   ```bash
   python main_adk.py run-pipeline
   ```

3. **Run individual analysis steps:**
   ```bash
   python main_adk.py run-agent metadata    # Scan database schema
   python main_adk.py run-agent profiler    # Profile data quality
   python main_adk.py run-agent relations   # Detect relationships
   python main_adk.py run-agent drift       # Check for changes
   python main_adk.py run-agent insights    # Generate AI insights
   python main_adk.py run-agent reporter    # Create reports
   ```

4. **Interactive chat mode:**
   ```bash
   python main_adk.py chat
   ```
   Ask natural language questions like:
   - "Show me the top 5 organizations by user count"
   - "What changed in the database this month?"
   - "Generate a comprehensive report"

5. **Other commands:**
   ```bash
   python main_adk.py help                    # Show all commands
   python main_adk.py cache-stats             # View cache statistics
   python main_adk.py cleanup-states [days]   # Clean old session files
   python main_adk.py state-stats             # Show state directory info
   ```

### Docker Usage

1. **Run with Docker:**
   ```bash
   docker run -it --env-file .env -v $(pwd)/reports:/app/reports -v $(pwd)/state:/app/state db-agent-adk
   ```

2. **Run specific commands:**
   ```bash
   # Complete pipeline
   docker run --env-file .env -v $(pwd)/reports:/app/reports db-agent-adk python main_adk.py run-pipeline

   # Interactive chat
   docker run -it --env-file .env -v $(pwd)/state:/app/state db-agent-adk python main_adk.py chat

   # Clean up old states
   docker run --env-file .env db-agent-adk python main_adk.py cleanup-states 30
   ```

## 📊 Output Files

The agent generates reports in the `reports/` directory:

- **Markdown Reports**: `reports/markdown/db_report_YYYYMMDD_HHMMSS.md`
- **JSON Data**: `reports/json/db_intelligence_YYYYMMDD_HHMMSS.json`
- **Session State**: `state/` directory (for resuming analyses)

## 🔧 Customization

### Changing the Agent's Goal

Edit the `INSIGHTS_GOAL` in your `.env` file to customize what the AI focuses on:

```env
INSIGHTS_GOAL=Analyze customer behavior patterns and sales trends.
```

### Advanced Configuration

- **Model Selection**: Change `ADK_MODEL` to use different Gemini models
- **Cache Settings**: Adjust `QUERY_CACHE_TTL_HOURS` or disable with `QUERY_CACHE_DISABLED=TRUE`
- **Report Directories**: Modify paths in `config.py` if needed

## 🐛 Troubleshooting

### Common Issues

1. **"Connection refused" errors:**
   - Check your database credentials in `.env`
   - Ensure the database server is running and accessible

2. **"API rate limit exceeded":**
   - Wait a few minutes and try again
   - Consider using a different Gemini model

3. **"Module not found" errors:**
   - Ensure you're in the virtual environment: `.venv\Scripts\activate`
   - Reinstall dependencies: `pip install -r requirements.txt`

4. **Reports not generating:**
   - Check file permissions on the `reports/` directory
   - Ensure you have write access to the output directories

### Getting Help

- Check the logs in `logs/db_agent.log`
- Use `python main_adk.py help` for command details
- Review the `SETUP_GUIDE.md` for detailed setup instructions


## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Google ADK](https://github.com/google/adk)
- Powered by [Google Gemini](https://ai.google.dev/)
- Database support via [psycopg2](https://www.psycopg.org/) and [Snowflake Connector](https://docs.snowflake.com/en/user-guide/python-connector.html)

---
