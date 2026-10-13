from pathlib import Path
from unittest.mock import patch

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
        "integration_results": {
            "bitable": {"success": False, "skipped": True},
            "feishu_chat": {"success": False, "skipped": True},
        },
        "errors": [],
    }

    # Post plain transcript
    response = client.post(
        "/api/v1/pipeline/process",
        data={
            "raw_transcript": "Vijay will do X by next week.",
            "send_to_bitable": "false",
            "send_to_feishu_chat": "false",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["total_items"] == 1
    assert data["extracted_actions"][0]["task"] == "Test task"
    assert data["integration_results"]["bitable"]["skipped"] is True
    pipeline_input = mock_workflow.call_args.args[0]
    assert pipeline_input["send_to_bitable"] is False
    assert pipeline_input["send_to_feishu_chat"] is False
    assert pipeline_input["meeting_name"] == ""
    assert pipeline_input["meeting_date"] == ""


@pytest.mark.parametrize(
    "flags,metadata",
    [
        ({"send_to_bitable": "true"}, {"meeting_date": "2026-10-13"}),
        ({"send_to_feishu_chat": "true"}, {"meeting_name": "项目周会"}),
        (
            {"send_to_bitable": "true", "send_to_feishu_chat": "true"},
            {"meeting_name": "项目周会", "meeting_date": ""},
        ),
    ],
)
@patch("api.main.workflow.invoke")
def test_process_meeting_requires_metadata_for_any_enabled_integration(
    mock_workflow, flags, metadata
):
    data = {"raw_transcript": "讨论项目安排。", **flags, **metadata}
    response = client.post(
        "/api/v1/pipeline/process",
        data=data,
    )

    assert response.status_code == 422
    assert "会议名称不能为空" in response.json()["detail"] or "会议日期" in response.json()["detail"]
    mock_workflow.assert_not_called()


@patch("api.main.workflow.invoke")
def test_process_meeting_trims_and_passes_metadata_when_chat_enabled(mock_workflow):
    mock_workflow.return_value = {
        "structured_items": [],
        "integration_results": {},
        "errors": [],
    }

    response = client.post(
        "/api/v1/pipeline/process",
        data={
            "raw_transcript": "讨论项目安排。",
            "send_to_feishu_chat": "true",
            "meeting_name": "  项目周会  ",
            "meeting_date": "2026-10-13",
        },
    )

    assert response.status_code == 200
    state = mock_workflow.call_args.args[0]
    assert state["meeting_name"] == "项目周会"
    assert state["meeting_date"] == "2026-10-13"


@patch("api.main.workflow.invoke")
def test_process_meeting_rejects_invalid_date_before_workflow(mock_workflow):
    response = client.post(
        "/api/v1/pipeline/process",
        data={
            "raw_transcript": "讨论项目安排。",
            "send_to_feishu_chat": "true",
            "meeting_name": "项目周会",
            "meeting_date": "2026/10/13",
        },
    )

    assert response.status_code == 422
    assert "YYYY-MM-DD" in response.json()["detail"]
    mock_workflow.assert_not_called()


@patch("api.main.get_transcriber")
@patch("api.main.workflow.invoke")
def test_process_audio_missing_meeting_metadata_is_rejected_before_whisper(
    mock_workflow, mock_get_transcriber
):
    response = client.post(
        "/api/v1/pipeline/process",
        files={"audio_file": ("meeting.mp3", b"mock audio", "audio/mpeg")},
        data={
            "send_to_bitable": "true",
            "meeting_date": "2026-10-13",
        },
    )

    assert response.status_code == 422
    assert "会议名称不能为空" in response.json()["detail"]
    mock_get_transcriber.assert_not_called()
    mock_workflow.assert_not_called()


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


@patch("api.main.WhisperTranscriber")
def test_transcribe_sample_audio_with_mock(mock_transcriber_class):
    """Verify the bundled sample audio reaches the transcriber upload path."""
    sample_path = Path(__file__).resolve().parents[1] / "sample_meeting.mp3"
    mock_transcriber_class.return_value.transcribe.return_value = "Mock transcript text"

    response = client.post(
        "/api/v1/transcribe",
        files={"audio_file": (sample_path.name, sample_path.read_bytes(), "audio/mpeg")},
    )

    assert response.status_code == 200
    assert response.json()["transcript"] == "Mock transcript text"
    mock_transcriber_class.return_value.transcribe.assert_called_once()
