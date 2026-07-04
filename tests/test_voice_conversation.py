from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from my_agent.config import VoiceConversationConfig
from my_agent.voice.companion import build_speak_tool
from my_agent.voice.conversation import effective_voice_config
from my_agent.config import VoiceConfig
from my_agent.voice.extract import VoiceTagStreamFilter
from my_agent.voice.notes import print_speaker_note
from my_agent.voice.queue import VoiceQueue
from my_agent.voice.session import activate_voice_queue, deactivate_voice_queue, get_voice_queue
from my_agent.voice.synthesize import SynthesisError, build_synthesizer


class TestVoiceTagStreamFilter:
    def test_extracts_voice_block_and_strips_from_terminal(self) -> None:
        spoken: list[str] = []

        def _speak(text: str) -> None:
            spoken.append(text)

        voice_queue = VoiceQueue(_speak)
        try:
            filter_ = VoiceTagStreamFilter(voice_queue, max_chars=280)

            terminal = filter_.feed("Hello ")
            terminal += filter_.feed("[voice]I'll read this aloud.[/voice]")
            terminal += filter_.feed(" More on screen.")
            terminal += filter_.flush()
            voice_queue.wait_idle(timeout=2.0)
        finally:
            voice_queue.close()

        assert terminal == "Hello  More on screen."
        assert spoken == ["I'll read this aloud."]

    def test_handles_split_tags_across_tokens(self) -> None:
        spoken: list[str] = []

        def _speak(text: str) -> None:
            spoken.append(text)

        voice_queue = VoiceQueue(_speak)
        try:
            filter_ = VoiceTagStreamFilter(voice_queue, max_chars=280)
            for chunk in ["[vo", "ice]Hi there[/", "voice]"]:
                filter_.feed(chunk)
            filter_.flush()
            voice_queue.wait_idle(timeout=2.0)
        finally:
            voice_queue.close()

        assert spoken == ["Hi there"]

    def test_truncates_long_voice_segments(self) -> None:
        spoken: list[str] = []

        def _speak(text: str) -> None:
            spoken.append(text)

        voice_queue = VoiceQueue(_speak)
        try:
            filter_ = VoiceTagStreamFilter(voice_queue, max_chars=20)
            filter_.feed(f"[voice]{'x' * 30}[/voice]")
            filter_.flush()
            voice_queue.wait_idle(timeout=2.0)
        finally:
            voice_queue.close()

        assert spoken[0].endswith("...")
        assert len(spoken[0]) == 20


class TestVoiceQueue:
    def test_plays_phrases_in_order(self) -> None:
        spoken: list[str] = []

        def _speak(text: str) -> None:
            spoken.append(text)
            time.sleep(0.01)

        queue = VoiceQueue(_speak)
        try:
            queue.enqueue("first")
            queue.enqueue("second")
            assert queue.wait_idle(timeout=2.0)
        finally:
            queue.close()

        assert spoken == ["first", "second"]

    def test_ignores_empty_phrases(self) -> None:
        spoken: list[str] = []
        queue = VoiceQueue(spoken.append)
        try:
            queue.enqueue("   ")
            queue.enqueue("hello")
            assert queue.wait_idle(timeout=2.0)
        finally:
            queue.close()
        assert spoken == ["hello"]

    def test_on_enqueue_callback_fires_before_playback(self) -> None:
        spoken: list[str] = []
        noted: list[str] = []
        queue = VoiceQueue(spoken.append, on_enqueue=noted.append)
        try:
            queue.enqueue("hello")
            assert noted == ["hello"]
            assert queue.wait_idle(timeout=2.0)
        finally:
            queue.close()
        assert spoken == ["hello"]


class TestSpeakTool:
    def test_queues_message_when_session_active(self) -> None:
        spoken: list[str] = []
        queue = VoiceQueue(spoken.append)
        token = activate_voice_queue(queue)
        try:
            tool = build_speak_tool(max_chars=280)
            result = tool.invoke({"message": "On it."})
            assert queue.wait_idle(timeout=2.0)
        finally:
            deactivate_voice_queue(token)
            queue.close()

        assert result == "Queued for voice output."
        assert spoken == ["On it."]

    def test_returns_inactive_message_without_queue(self) -> None:
        tool = build_speak_tool(max_chars=280)
        assert tool.invoke({"message": "Hello"}) == "Voice output is not active."
        assert get_voice_queue() is None


class TestEffectiveVoiceConfig:
    def test_disables_confirm_in_conversation_mode(self) -> None:
        base = VoiceConfig(confirm_before_send=True)
        updated = effective_voice_config(base, conversation_enabled=True)
        assert updated.confirm_before_send is False
        assert effective_voice_config(base, conversation_enabled=False) is base


class TestSynthesizer:
    def test_macos_backend_requires_say(self) -> None:
        with patch("my_agent.voice.synthesize.shutil.which", return_value=None):
            with pytest.raises(SynthesisError, match="say"):
                build_synthesizer(backend="macos")

    def test_unknown_backend_raises(self) -> None:
        with pytest.raises(SynthesisError, match="Unsupported"):
            build_synthesizer(backend="unknown")

    def test_macos_backend_invokes_say(self) -> None:
        with patch("my_agent.voice.synthesize.shutil.which", return_value="/usr/bin/say"):
            with patch("my_agent.voice.synthesize.subprocess.run") as run:
                speak = build_synthesizer(backend="macos", voice="Samantha")
                speak("Hello")
        run.assert_called_once_with(["say", "-v", "Samantha", "Hello"], check=True)


class TestConversationPrompt:
    def test_encourages_frequent_jarvis_style_speech(self) -> None:
        from my_agent.voice.companion import CONVERSATION_MODE_PROMPT

        assert "JARVIS" in CONVERSATION_MODE_PROMPT
        assert "Speak often" in CONVERSATION_MODE_PROMPT
        assert "more than one tool" in CONVERSATION_MODE_PROMPT

    def test_forbids_writing_speaker_note_in_assistant_text(self) -> None:
        from my_agent.voice.companion import CONVERSATION_MODE_PROMPT

        assert 'do **not** write "Speaker note:"' in CONVERSATION_MODE_PROMPT
        assert "write the full answer on the terminal" in CONVERSATION_MODE_PROMPT


class TestSanitizeSpokenText:
    def test_strips_speaker_note_prefix_and_markdown(self) -> None:
        from my_agent.voice.companion import sanitize_spoken_text

        raw = 'Speaker note: "Today is **Saturday**, July 4, 2026."'
        assert sanitize_spoken_text(raw) == "Today is Saturday, July 4, 2026."

    def test_strips_inline_markdown(self) -> None:
        from my_agent.voice.companion import sanitize_spoken_text

        assert sanitize_spoken_text("Today is **Saturday**") == "Today is Saturday"


class TestSpeakerNotes:
    def test_prints_labeled_line(self) -> None:
        from io import StringIO
        from rich.console import Console

        buffer = StringIO()
        console = Console(file=buffer, width=120, highlight=False)
        print_speaker_note(console, "Checking the latest news.")
        output = buffer.getvalue()
        assert "Speaker note" in output
        assert "Checking the latest news." in output


class TestCreateVoiceQueue:
    def test_wires_speaker_notes_when_console_provided(self) -> None:
        from io import StringIO
        from rich.console import Console
        from my_agent.voice.conversation import create_voice_queue

        buffer = StringIO()
        console = Console(file=buffer, width=120, highlight=False)
        with patch("my_agent.voice.conversation.build_synthesizer", return_value=lambda _: None):
            queue = create_voice_queue(
                VoiceConversationConfig(show_speaker_notes=True),
                console=console,
            )
            try:
                queue.enqueue("On it.")
            finally:
                queue.close()
        assert "Speaker note" in buffer.getvalue()
        assert "On it." in buffer.getvalue()

    def test_hides_speaker_notes_when_disabled(self) -> None:
        from io import StringIO
        from rich.console import Console
        from my_agent.voice.conversation import create_voice_queue

        buffer = StringIO()
        console = Console(file=buffer, width=120, highlight=False)
        with patch("my_agent.voice.conversation.build_synthesizer", return_value=lambda _: None):
            queue = create_voice_queue(
                VoiceConversationConfig(show_speaker_notes=False),
                console=console,
            )
            try:
                queue.enqueue("On it.")
            finally:
                queue.close()
        assert buffer.getvalue() == ""


class TestVoiceConversationConfig:
    def test_parses_nested_section(self, tmp_path, mock_env_openrouter_key) -> None:
        from my_agent.config import VoiceConversationConfig, load_config

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[llm]
model = "anthropic/claude-sonnet-4-6"

[voice.conversation]
enabled = true
tts_backend = "macos"
tts_voice = "Alex"
max_speak_chars = 100
strip_voice_tags_from_terminal = false
""".strip()
        )
        config = load_config(config_file)
        assert config.voice_conversation == VoiceConversationConfig(
            enabled=True,
            tts_backend="macos",
            tts_voice="Alex",
            max_speak_chars=100,
            strip_voice_tags_from_terminal=False,
            show_speaker_notes=True,
        )
