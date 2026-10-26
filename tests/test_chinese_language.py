from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from agents.extractor_agent import EXTRACTOR_SYSTEM_PROMPT
from agents.formatter_agent import ActionItem, MeetingOutput, run_formatter
from agents.prioritizer_agent import PRIORITIZER_SYSTEM_PROMPT
from transcriber.whisper_api import WhisperTranscriber


@patch("transcriber.whisper_api.Groq")
def test_transcribe_defaults_to_chinese(mock_groq):
    mock_groq.return_value.audio.transcriptions.create.return_value = "小王负责完善需求文档。"
    transcriber = WhisperTranscriber(api_key="dummy-test-key")

    result = transcriber.transcribe(BytesIO(b"fake audio"), filename="meeting.mp3")

    assert result == "小王负责完善需求文档。"
    assert mock_groq.return_value.audio.transcriptions.create.call_args.kwargs["language"] == "zh"


@patch("transcriber.whisper_api.Groq")
def test_timestamp_transcription_defaults_to_chinese(mock_groq):
    mock_groq.return_value.audio.transcriptions.create.return_value = SimpleNamespace(
        text="中文会议内容", segments=[]
    )
    transcriber = WhisperTranscriber(api_key="dummy-test-key")

    result = transcriber.transcribe_with_timestamps(BytesIO(b"fake audio"))

    assert result["text"] == "中文会议内容"
    assert mock_groq.return_value.audio.transcriptions.create.call_args.kwargs["language"] == "zh"


@patch("transcriber.whisper_api.Groq")
def test_auto_detection_can_still_be_requested_explicitly(mock_groq):
    mock_groq.return_value.audio.transcriptions.create.return_value = "Detected transcript"
    transcriber = WhisperTranscriber(api_key="dummy-test-key")

    transcriber.transcribe(BytesIO(b"fake audio"), language=None)

    assert mock_groq.return_value.audio.transcriptions.create.call_args.kwargs["language"] is None


def test_chinese_agent_prompts_preserve_names():
    assert "Simplified Chinese" in EXTRACTOR_SYSTEM_PROMPT
    assert "Never translate or romanize Chinese names" in EXTRACTOR_SYSTEM_PROMPT
    assert 'Preserve all existing "action", "owner", and "source_excerpt"' in PRIORITIZER_SYSTEM_PROMPT


@patch("agents.formatter_agent.ChatGroq")
def test_formatter_requests_chinese_task_text_and_original_names(mock_chat_groq):
    mock_structured = mock_chat_groq.return_value.with_structured_output.return_value
    mock_structured.invoke.return_value = MeetingOutput(
        actions=[
            ActionItem(
                task="完善需求文档",
                owner="小王",
                deadline="2026-10-28",
                urgency_score=3,
                impact_score=3,
                priority_score=9,
                priority_label="Medium",
                confidence=0.95,
            )
        ]
    )

    result = run_formatter([{"action": "完善需求文档", "owner": "小王"}])

    assert result[0]["owner"] == "小王"
    instruction = mock_structured.invoke.call_args.args[0]
    assert "Simplified Chinese" in instruction
    assert "never translate or romanize" in instruction
