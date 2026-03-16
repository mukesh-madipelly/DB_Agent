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
        except ImportError:
            raise ImportError(
                "Snowflake connector not installed. Run: pip install snowflake-connector-python"
            )
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
            raise ConnectionError(
                f"Failed to connect to snowflake: {str(e)}\n"
                "Check your credentials in .env file"
            )
        except Exception as e:
            if conn:
                conn.close()
            raise ConnectionError(f"Unexpected error occured connecting to snowflake: {str(e)}")

    elif config.DB_TYPE == "postgresql":
        try:
            import psycopg2
        except ImportError:
            raise ImportError(
                "psycopg2 not installed. Run: pip install psycopg2-binary"
            )
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
            raise ConnectionError(
                f"Failed to connect to PostgreSQL: {str(e)}\n"
                "Check DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD in your .env file"
            )
        except Exception as e:
            if conn:
                conn.close()
            raise ConnectionError(f"Unexpected error connecting to PostgreSQL: {str(e)}")

    else:
        raise ValueError(
            f"Unsupported DB_TYPE: '{config.DB_TYPE}'. "
            "Supported values: 'snowflake', 'postgresql'"
        )
