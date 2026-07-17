from unittest.mock import MagicMock, patch

import pytest

from agents.extractor_agent import run_extractor


class TestExtractorAgent:

    @patch("agents.extractor_agent.ChatOpenAI")
    def test_extracts_explicit_action(self, mock_llm_class):
        """Clear assignment should be extracted successfully."""
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

        # Mock LLM response with proper JSON string
        mock_response = MagicMock()
        mock_response.content = (
            '[{"action": "prepare report", "owner": "Sarah", "deadline": "2026-07-05", '
            '"deadline_type": "explicit", "source_excerpt": "Sarah will prepare the report by July 5th.", '
            '"confidence": 0.95, "needs_review": false}]'
        )
        mock_llm.return_value = mock_response

        result = run_extractor("Sarah will prepare the report by July 5th.")
        assert len(result) >= 1
        assert result[0]["action"] == "prepare report"
        assert result[0]["owner"] == "Sarah"
        assert result[0]["deadline"] == "2026-07-05"

    def test_handles_empty_transcript(self):
        """Empty transcript should return empty list without crashing."""
        result = run_extractor("")
        assert result == []

    @patch("agents.extractor_agent.ChatOpenAI")
    def test_handles_invalid_json_gracefully(self, mock_llm_class):
        """If the LLM outputs invalid JSON, a fallback review task is returned."""
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm
        mock_response = MagicMock()
        mock_response.content = "This is definitely not valid JSON."
        mock_llm.return_value = mock_response

        result = run_extractor("Some meeting text.")
        assert len(result) == 1
        assert result[0]["needs_review"] is True
        assert "manual" in result[0]["action"].lower()
