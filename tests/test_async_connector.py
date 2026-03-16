import pytest
import config
from unittest.mock import AsyncMock, patch
from adk_agents.tools.async_connector import create_async_db_pool

@pytest.mark.asyncio
async def test_create_async_db_pool_postgresql(mocker):
    """Test that the async pool is correctly created for PostgreSQL."""
    # Mock config
    mocker.patch.object(config, "DB_TYPE", "postgresql")
    mocker.patch.object(config, "POSTGRESQL", {
        "host": "localhost",
        "port": 5432,
        "user": "test_user",
        "password": "test_password",
        "dbname": "test_db"
    })
    
    # Mock asyncpg.create_pool accurately
    mock_pool = AsyncMock()
    # We need create_pool itself to be an AsyncMock so it's awaitable
    mock_create_pool = mocker.patch("asyncpg.create_pool", new_callable=AsyncMock)
    mock_create_pool.return_value = mock_pool
    
    pool = await create_async_db_pool()
    
    assert pool == mock_pool
    # Using any_order=True or checking specific subset because of init function
    mock_create_pool.assert_called_once()
    args, kwargs = mock_create_pool.call_args
    assert kwargs["host"] == "localhost"
    assert kwargs["port"] == 5432
    assert kwargs["user"] == "test_user"
    assert kwargs["password"] == "test_password"
    assert kwargs["database"] == "test_db"
    assert kwargs["min_size"] == 1
    assert kwargs["max_size"] == 10
    assert callable(kwargs["init"])

@pytest.mark.asyncio
async def test_create_async_db_pool_failure(mocker):
    """Test that database connection failures are handled."""
    mocker.patch.object(config, "DB_TYPE", "postgresql")
    # Mocking asyncpg.create_pool to raise an exception
    mocker.patch("asyncpg.create_pool", side_effect=Exception("Connection Refused"))
    
    with pytest.raises(ConnectionError) as excinfo:
        await create_async_db_pool()
    
    assert "Failed to create asyncpg pool" in str(excinfo.value)
