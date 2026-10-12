from unittest.mock import patch

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from agents.prioritizer_agent import run_prioritizer


class TestPrioritizerAgent:

    @patch("agents.prioritizer_agent.ChatGroq")
    def test_priority_scoring(self, mock_llm_class):
        """Action item prioritization scores should match structured format."""
        mock_response = AIMessage(content=(
            '[{"action": "Fix critical production bug", "owner": "Dev Team", "deadline": "2026-07-01", '
            '"deadline_type": "explicit", "source_excerpt": "Fix it now.", "confidence": 0.99, '
            '"needs_review": false, "urgency_score": 5, "impact_score": 5, "priority_score": 25, '
            '"priority_label": "Critical", "reason": "Immediate blocker."}]'
        ))
        mock_llm_class.return_value = RunnableLambda(lambda _: mock_response)

        items = [{"action": "Fix critical production bug", "owner": "Dev Team", "deadline": "2026-07-01"}]
        result = run_prioritizer(items)

        assert len(result) == 1
        assert result[0]["priority_score"] == 25
        assert result[0]["priority_label"] == "Critical"
        assert "urgency_score" in result[0]

    def test_handles_empty_list(self):
        """Should return empty list without crashing."""
        result = run_prioritizer([])
        assert result == []

    @patch("agents.prioritizer_agent.ChatGroq")
    def test_handles_invalid_json_fallback(self, mock_llm_class):
        """Should gracefully fall back to default scores if LLM output fails to parse."""
        mock_response = AIMessage(content="Invalid JSON string")
        mock_llm_class.return_value = RunnableLambda(lambda _: mock_response)

        items = [{"action": "Regular task", "owner": "Vijay", "deadline": "TBD"}]
        result = run_prioritizer(items)

        assert len(result) == 1
        assert result[0]["priority_score"] == 9
        assert result[0]["priority_label"] == "Medium"
        assert "parsing failed" in result[0]["reason"].lower()
