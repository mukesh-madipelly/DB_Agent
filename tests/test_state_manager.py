import os
import json
import sqlite3


def test_save_and_load_state_sqlite(state_manager):
    """Test that state can be correctly saved and loaded via SQLite."""
    session_id = "test_session_sql"
    test_state = {"key": "value", "count": 100}

    # Save state
    success = state_manager.save_state(session_id, test_state)
    assert success is True

    # Check if DB exists and contains the row
    assert os.path.exists(state_manager.db_path)
    with sqlite3.connect(state_manager.db_path) as conn:
        cursor = conn.execute(
            "SELECT state_json FROM session_states WHERE session_id = ?", (session_id,)
        )
        row = cursor.fetchone()
        assert row is not None
        assert json.loads(row[0]) == test_state

    # Load state
    loaded_state = state_manager.load_state(session_id)
    assert loaded_state == test_state


def test_migration_from_json(state_manager, temp_state_dir):
    """Test that legacy JSON files are migrated to SQLite on load."""
    session_id = "legacy_session"
    legacy_state = {"legacy": True, "migrated": False}

    # Create legacy file
    legacy_path = os.path.join(temp_state_dir, f"{session_id}.json")
    with open(legacy_path, "w", encoding="utf-8") as f:
        json.dump({"session_id": session_id, "state": legacy_state}, f)

    # Load state - should trigger migration
    loaded_state = state_manager.load_state(session_id)
    assert loaded_state == legacy_state

    # Verify it's now in DB
    with sqlite3.connect(state_manager.db_path) as conn:
        cursor = conn.execute(
            "SELECT state_json FROM session_states WHERE session_id = ?", (session_id,)
        )
        row = cursor.fetchone()
        assert row is not None
        assert json.loads(row[0]) == legacy_state


def test_cleanup_sqlite_and_files(state_manager, temp_state_dir):
    """Test cleanup of both DB records and legacy files."""
    import time

    # 1. Create a legacy old file
    old_file_session = "old_file"
    old_path = os.path.join(temp_state_dir, f"{old_file_session}.json")
    with open(old_path, "w") as f:
        json.dump({"state": {"old": "file"}}, f)

    # Set mtime to 32 days ago
    old_time = time.time() - (32 * 24 * 3600)
    os.utime(old_path, (old_time, old_time))

    # 2. Create a new DB entry
    new_session = "new_db_session"
    state_manager.save_state(new_session, {"status": "fresh"})

    # Run cleanup
    records, files, _ = state_manager.cleanup_old_states(retention_days=30)

    # Files removed should be 1
    assert files == 1
    assert not os.path.exists(old_path)

    # DB record should still be there (it's new)
    assert state_manager.load_state(new_session) == {"status": "fresh"}


def test_validate_state_robustness(state_manager):
    """Test validate_state handles various inputs."""
    # Test minimal dict
    minimal = {"connection_established": True}
    validated = state_manager.validate_state(minimal)
    assert validated["connection_established"] is True
    assert "schema" in validated
    assert validated["total_steps"] == 6

    # Test None/Empty
    assert state_manager.validate_state(None) == {}
    assert state_manager.validate_state({}) == {}
