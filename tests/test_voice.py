from __future__ import annotations

import io
import json
import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from my_agent.config import VoiceConfig
from my_agent.voice.capture import (
    CaptureCancelled,
    CaptureDependencyError,
    record_push_to_talk,
)
from my_agent.voice.input import ConfirmAction, capture_and_transcribe, confirm_transcript
from my_agent.voice.transcribe import (
    TranscriptionError,
    TranscriptionResult,
    audio_format_from_path,
    transcribe_audio,
    transcribe_file,
)


def _make_wav_bytes(duration_seconds: float = 0.1, sample_rate: int = 16_000) -> bytes:
    frame_count = int(sample_rate * duration_seconds)
    frames = struct.pack(f"<{frame_count}h", *([0] * frame_count))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)
    return buffer.getvalue()


class TestAudioFormatFromPath:
    def test_maps_known_extensions(self) -> None:
        assert audio_format_from_path(Path("clip.wav")) == "wav"
        assert audio_format_from_path(Path("clip.MP3")) == "mp3"

    def test_rejects_unknown_extension(self) -> None:
        with pytest.raises(ValueError, match="Unsupported audio format"):
            audio_format_from_path(Path("clip.txt"))


class TestTranscribeAudio:
    def test_transcribes_via_openrouter(self) -> None:
        response_body = {
            "text": "Hello from speech.",
            "usage": {"seconds": 1.2, "cost": 0.0001},
        }
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(response_body).encode("utf-8")
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with patch(
                "my_agent.voice.transcribe.urllib.request.urlopen",
                return_value=fake_response,
            ) as urlopen:
                result = transcribe_audio(
                    _make_wav_bytes(),
                    audio_format="wav",
                    model="openai/whisper-large-v3",
                    language="en",
                )

        assert result.text == "Hello from speech."
        assert result.seconds == 1.2
        assert result.cost == 0.0001

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["model"] == "openai/whisper-large-v3"
        assert payload["language"] == "en"
        assert payload["input_audio"]["format"] == "wav"
        assert request.get_header("Authorization") == "Bearer test-key"

    def test_requires_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(TranscriptionError, match="OPENROUTER_API_KEY"):
                transcribe_audio(
                    _make_wav_bytes(),
                    audio_format="wav",
                    model="openai/whisper-large-v3",
                )

    def test_rejects_empty_audio(self) -> None:
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
            with pytest.raises(TranscriptionError, match="empty"):
                transcribe_audio(
                    b"",
                    audio_format="wav",
                    model="openai/whisper-large-v3",
                )


class TestTranscribeFile:
    def test_reads_file_and_transcribes(self, tmp_path: Path) -> None:
        audio_path = tmp_path / "note.wav"
        audio_path.write_bytes(_make_wav_bytes())

        with patch(
            "my_agent.voice.transcribe.transcribe_audio",
            return_value=MagicMock(text="file transcript", seconds=None, cost=None),
        ) as transcribe:
            result = transcribe_file(
                audio_path,
                VoiceConfig(model="openai/whisper-1", language="en"),
            )

        assert result.text == "file transcript"
        transcribe.assert_called_once()
        kwargs = transcribe.call_args.kwargs
        assert kwargs["audio_format"] == "wav"
        assert kwargs["model"] == "openai/whisper-1"
        assert kwargs["language"] == "en"


class TestConfirmTranscript:
    def test_send_on_enter(self) -> None:
        console = MagicMock()
        console.input.return_value = ""
        assert confirm_transcript(console, "hello") == "hello"

    def test_edit_then_send(self) -> None:
        console = MagicMock()
        console.input.side_effect = ["e", "edited text", ""]
        assert confirm_transcript(console, "hello") == "edited text"

    def test_rerecord_action(self) -> None:
        console = MagicMock()
        console.input.return_value = "r"
        assert confirm_transcript(console, "hello") is ConfirmAction.RERECORD

    def test_invalid_choice_shows_hint(self) -> None:
        console = MagicMock()
        console.input.side_effect = ["x", ""]
        assert confirm_transcript(console, "hello") == "hello"
        console.print.assert_any_call(
            "[yellow]Invalid choice. Press Enter to send, e to edit, r to re-record, or c to cancel.[/yellow]"
        )

    def test_edit_empty_keeps_current(self) -> None:
        console = MagicMock()
        console.input.side_effect = ["e", "", ""]
        assert confirm_transcript(console, "hello") == "hello"
        console.print.assert_any_call("[yellow]No changes — keeping current text.[/yellow]")

    def test_cancel_action(self) -> None:
        console = MagicMock()
        console.input.return_value = "c"
        assert confirm_transcript(console, "hello") is ConfirmAction.CANCEL


class TestCaptureAndTranscribe:
    def test_auto_send_shows_transcript_preview(self) -> None:
        console = MagicMock()
        voice_config = VoiceConfig(confirm_before_send=False)

        with patch(
            "my_agent.voice.input.record_push_to_talk",
            return_value=b"wav-bytes",
        ):
            result = capture_and_transcribe(
                console,
                voice_config,
                transcribe=lambda _audio: TranscriptionResult(text="hello there"),
            )

        assert result == "hello there"
        console.print.assert_any_call(
            '[bold yellow]You said:[/bold yellow] [cyan]"hello there"[/cyan]'
        )
        console.input.assert_not_called()

    def test_missing_dependencies_show_friendly_message(self) -> None:
        console = MagicMock()
        voice_config = VoiceConfig()

        with patch(
            "my_agent.voice.input.record_push_to_talk",
            side_effect=CaptureDependencyError(
                "Install my-agent with: pip install 'my-agent[voice]'"
            ),
        ):
            result = capture_and_transcribe(console, voice_config)

        assert result is None
        console.print.assert_any_call(
            "[red]Voice input unavailable:[/red] "
            "Install my-agent with: pip install 'my-agent[voice]'"
        )


class TestRecordPushToTalk:
    def test_cancels_when_no_audio_captured(self) -> None:
        voice_config = VoiceConfig(max_duration_seconds=5.0)
        fake_keyboard = MagicMock()
        fake_keyboard.Key.space = "space"
        fake_keyboard.Key.esc = "esc"

        class FakeListener:
            def __init__(self, on_press=None, on_release=None) -> None:
                self._on_press = on_press
                self._on_release = on_release

            def start(self) -> None:
                if self._on_press is not None:
                    self._on_press(fake_keyboard.Key.space)
                if self._on_release is not None:
                    self._on_release(fake_keyboard.Key.space)

            def stop(self) -> None:
                return None

        fake_keyboard.Listener.side_effect = FakeListener

        fake_sd = MagicMock()
        fake_stream = MagicMock()
        fake_stream.__enter__.return_value = fake_stream
        fake_stream.__exit__.return_value = False
        fake_sd.InputStream.return_value = fake_stream

        with patch("my_agent.voice.capture._import_sounddevice", return_value=fake_sd):
            with patch(
                "my_agent.voice.capture._import_pynput_keyboard",
                return_value=fake_keyboard,
            ):
                with pytest.raises(CaptureCancelled, match="No audio captured"):
                    record_push_to_talk(voice_config)
