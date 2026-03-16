import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
import config
from adk_agents.tools.llm_insights_tools import generate_business_insights, format_insights_for_report

@pytest.mark.asyncio
async def test_generalized_insights_healthcare_mocked():
    """Verify that the insights agent can handle a completely different domain (Healthcare)."""
    
    # 1. Mock Schema & State
    mock_schema = {
        "Patients": {
            "row_count": 5000,
            "columns": [
                {"name": "PatientID", "type": "INT"},
                {"name": "Name", "type": "TEXT"},
                {"name": "Age", "type": "INT"}
            ]
        },
        "Appointments": {
            "row_count": 10000,
            "columns": [
                {"name": "ApptID", "type": "INT"},
                {"name": "PatientID", "type": "INT"},
                {"name": "ApptDate", "type": "TIMESTAMP"},
                {"name": "Status", "type": "TEXT"}
            ]
        }
    }
    
    # Mock ToolContext and StateManager
    mock_context = MagicMock()
    mock_context.session_id = "test_session_123"
    mock_context.state = {"schema": mock_schema, "tables_scanned": True}
    
    # 2. Mock LLM - Discovery Plan (Stage 1)
    plan_json = {
        "plan": [
            {
                "title": "Patient Demographics",
                "sql": "SELECT \"Age\", COUNT(*) as patient_count FROM \"Patients\" GROUP BY \"Age\" LIMIT 5",
                "description": "Distribution of patients by age."
            }
        ]
    }
    
    # 3. Mock LLM - Narrative (Stage 3)
    narrative_json = {
        "summary": "The patient base is primarily composed of elderly individuals.",
        "key_insights": ["Majority of patients are over 60.", "Appointment volume is steady."],
        "recommendations": ["Increase geriatric specialists."]
    }

    # Setup Mocks
    with patch("adk_agents.tools.llm_insights_tools._llm_client_model") as mock_llm_setup, \
         patch("adk_agents.tools.llm_insights_tools._llm_generate") as mock_generate, \
         patch("adk_agents.tools.llm_insights_tools._run_sql_async", new_callable=AsyncMock) as mock_sql, \
         patch("adk_agents.tools.llm_insights_tools.get_state_manager") as mock_sm_getter:
        
        mock_llm_setup.return_value = (MagicMock(), "gemini-model")
        
        # Sequentially return plan then narrative
        mock_generate.side_effect = [json.dumps(plan_json), json.dumps(narrative_json)]
        
        # Mocking SQL Result for Patient Demographics
        mock_sql.return_value = [{"Age": 70, "patient_count": 200}, {"Age": 65, "patient_count": 150}]
        
        # Mock StateManager
        mock_sm = MagicMock()
        mock_sm.load_state.return_value = mock_context.state
        mock_sm_getter.return_value = mock_sm
        
        # EXECUTE
        result = await generate_business_insights(mock_context)
        
        # VERIFY Result Structure
        assert result["status"] == "success"
        insights = result["insights"]
        
        # Test should be flexible to what's in config
        current_goal = getattr(config, "INSIGHTS_GOAL", "Analyze key data trends and anomalies.")
        assert insights["goal"] == current_goal
        assert insights["summary"] == narrative_json["summary"]
        assert len(insights["datasets"]) == 1
        assert insights["datasets"][0]["title"] == "Patient Demographics"
        assert insights["datasets"][0]["data"][0]["Age"] == 70
        
        # VERIFY Table Formatting
        report = format_insights_for_report(insights)
        assert "## 🤖 AI-Powered Database Insights" in report
        # Dynamic table should contain headers from mocked data
        assert "| Age | patient_count |" in report
        assert "| 70 | 200 |" in report
        assert "Increase geriatric specialists." in report

if __name__ == "__main__":
    pytest.main([__file__])
