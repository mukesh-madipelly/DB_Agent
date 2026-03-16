import pytest
import os
import shutil
import tempfile
from adk_agents.state_manager import StateManager

@pytest.fixture
def temp_state_dir(tmp_path):
    """Get a temporary directory for state files."""
    return str(tmp_path)

@pytest.fixture
def state_manager(temp_state_dir):
    """Create a StateManager instance with a temporary directory."""
    return StateManager(state_dir=temp_state_dir)

@pytest.fixture
def mock_tool_context():
    """Create a mock tool context for testing."""
    class MockState(dict):
        pass
    
    class MockToolContext:
        def __init__(self):
            self.state = MockState()
            self.session_id = "test_session"
            
    return MockToolContext()
