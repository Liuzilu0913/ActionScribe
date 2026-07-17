from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_check():
    """Verify health check endpoint returns 200 and correct status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "meeting-action-pipeline"


@patch("api.main.workflow.invoke")
def test_process_meeting_with_transcript(mock_workflow):
    """Verify /api/v1/pipeline/process processes a plain text transcript."""
    # Mock workflow response
    mock_workflow.return_value = {
        "transcript": "Test transcript",
        "structured_items": [
            {
                "task": "Test task",
                "owner": "Shubham",
                "deadline": "2026-07-20",
                "urgency_score": 3,
                "impact_score": 3,
                "priority_score": 9,
                "priority_label": "Medium",
                "confidence": 0.95,
                "needs_review": False,
            }
        ],
        "mcp_results": {
            "notion": {"success": True, "created": 1, "total": 1},
            "slack": {"success": True, "items_sent": 1},
        },
        "errors": [],
    }

    # Post plain transcript
    response = client.post(
        "/api/v1/pipeline/process",
        data={"raw_transcript": "Vijay will do X by next week."},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total_items"] == 1
    assert data["extracted_actions"][0]["task"] == "Test task"
    assert data["mcp_results"]["notion"]["success"] is True


def test_process_meeting_missing_params():
    """Verify endpoint rejects requests with missing fields with a 400 error."""
    response = client.post("/api/v1/pipeline/process")
    assert response.status_code == 400
    assert "either" in response.json()["detail"].lower()


@patch("api.main.WhisperTranscriber")
def test_transcribe_audio_unsupported_format(mock_transcriber_class):
    """Verify endpoint validates audio content types."""
    # Post unsupported content type (e.g. text/plain as audio)
    response = client.post(
        "/api/v1/transcribe",
        files={"audio_file": ("test.txt", b"some plain text contents", "text/plain")},
    )
    assert response.status_code == 422
    assert "unsupported" in response.json()["detail"].lower()
