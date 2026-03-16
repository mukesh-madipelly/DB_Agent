import config

def open_database_connection():
    """
    Opens and returns a connection to the configured database.
    Works with Snowflake (cloud) and PostgreSQL — no code changes needed elsewhere.

    All connections are opened in READ-ONLY mode — no data is ever written,
    modified, or deleted in the database.
    """
    if config.DB_TYPE == "snowflake":
        try:
            import snowflake.connector
        except ImportError as e:
            from adk_agents.tools.error_utils import log_and_raise_import_error
            log_and_raise_import_error("Snowflake connector not installed. Run: pip install snowflake-connector-python", e)
        conn = None
        try:
            conn = snowflake.connector.connect(**config.SNOWFLAKE)
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT CURRENT_DATABASE()")
            finally:
                cursor.close()
            return conn
        except snowflake.connector.errors.DatabaseError as e:
            if conn:
                conn.close()
            from adk_agents.tools.error_utils import log_and_raise_connection_error
            log_and_raise_connection_error("Failed to connect to snowflake. Check your credentials in .env file", e)
        except Exception as e:
            if conn:
                conn.close()
            from adk_agents.tools.error_utils import log_and_raise_connection_error
            log_and_raise_connection_error("Unexpected error occured connecting to snowflake", e)

    elif config.DB_TYPE == "postgresql":
        try:
            import psycopg2
        except ImportError as e:
            from adk_agents.tools.error_utils import log_and_raise_import_error
            log_and_raise_import_error("psycopg2 not installed. Run: pip install psycopg2-binary", e)
        conn = None
        try:
            conn = psycopg2.connect(**config.POSTGRESQL)
            # ── READ-ONLY: no INSERT/UPDATE/DELETE/DDL can ever be executed ──
            conn.set_session(readonly=True, autocommit=True)
            # Validate connection
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT 1")
            finally:
                cursor.close()
            return conn
        except psycopg2.OperationalError as e:
            if conn:
                conn.close()
            from adk_agents.tools.error_utils import log_and_raise_connection_error
            log_and_raise_connection_error("Failed to connect to PostgreSQL. Check DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD in your .env file", e)
        except Exception as e:
            if conn:
                conn.close()
            from adk_agents.tools.error_utils import log_and_raise_connection_error
            log_and_raise_connection_error("Unexpected error connecting to PostgreSQL", e)

    else:
        raise ValueError(
            f"Unsupported DB_TYPE: '{config.DB_TYPE}'. "
            "Supported values: 'snowflake', 'postgresql'"
        )
