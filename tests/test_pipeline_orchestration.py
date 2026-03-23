import pytest
from unittest.mock import MagicMock
from adk_agents.agents.pipeline_agent import create_adaptive_pipeline_agent


@pytest.fixture
def mock_agent_event():
    """Create a mock ADK runner event."""
    event = MagicMock()
    event.text = "Analysis complete"
    return event


@pytest.mark.asyncio
async def test_pipeline_agent_creation():
    """Test that the pipeline agent is created with the correct tools."""
    agent = create_adaptive_pipeline_agent()
    assert agent.name == "adaptive_pipeline"

    # Check if mandatory tools are present
    # In ADK, tools might be wrapped or just have a __name__ attribute
    tool_names = [
        getattr(t, "name", getattr(t, "__name__", str(t))) for t in agent.tools
    ]
    assert any("scan_database_tables" in name for name in tool_names)
    assert any("analyze_column_statistics" in name for name in tool_names)
    assert any("detect_table_relationships" in name for name in tool_names)
    assert any("detect_schema_changes" in name for name in tool_names)
    assert any("audit_data_quality" in name for name in tool_names)


def test_pipeline_instruction_content():
    """Test that the agent instructions contain mandatory sequences."""
    agent = create_adaptive_pipeline_agent()
    instructions = agent.instruction.lower()

    assert "mandatory core sequence" in instructions
    assert "do not skip steps 1-5" in instructions
    assert "run every time" in instructions
