import asyncpg
import config
import asyncio

async def create_async_db_pool():
    """
    Creates and returns an asynchronous connection pool for PostgreSQL.
    Enforces read-only sessions for security.
    """
    if config.DB_TYPE != "postgresql":
        raise ValueError("Async Turbo Engine currently only supports PostgreSQL (via asyncpg).")

    try:
        # Use existing config but adapt for asyncpg
        pg_config = config.POSTGRESQL.copy()
        
        # asyncpg connect params are slightly different from psycopg2
        # It prefers a DSN or kwarg-based connection.
        pool = await asyncpg.create_pool(
            user=pg_config.get("user"),
            password=pg_config.get("password"),
            database=pg_config.get("dbname"),
            host=pg_config.get("host"),
            port=pg_config.get("port", 5432),
            min_size=1,
            max_size=10,
            # Read-only enforcement via search_path and transaction mode
            init=setup_readonly_session
        )
        return pool
    except Exception as e:
        raise ConnectionError(f"Failed to create asyncpg pool: {str(e)}")

async def setup_readonly_session(conn):
    """Initializes the session in read-only mode."""
    # Enforce read-only for every connection in the pool
    await conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    # If a specific schema is configured, set it
    schema = getattr(config, "POSTGRESQL_SCHEMA", "public")
    if schema:
        await conn.execute(f"SET search_path TO {schema}")
