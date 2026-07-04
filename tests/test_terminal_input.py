from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

from rich.console import Console

from my_agent.cli import _read_chat_input
from my_agent.terminal_input import (
    _has_pending_input,
    _strip_bracketed_paste_markers,
    read_input,
)


class TestHasPendingInput:
    def test_stringio_with_remaining_content(self) -> None:
        stream = io.StringIO("line two\nline three\n")
        stream.readline()
        assert _has_pending_input(stream) is True

    def test_stringio_fully_consumed(self) -> None:
        stream = io.StringIO("only line\n")
        stream.readline()
        assert _has_pending_input(stream) is False


class TestStripBracketedPasteMarkers:
    def test_removes_escape_sequences(self) -> None:
        raw = "\x1b[200~hello\nworld\x1b[201~"
        assert _strip_bracketed_paste_markers(raw) == "hello\nworld"


class TestReadInput:
    def test_single_line(self) -> None:
        console = Console(file=io.StringIO(), force_terminal=False)
        stream = io.StringIO("hello\n")

        result = read_input(console, "You: ", stream=stream)

        assert result == "hello"

    def test_multiline_paste_coalesced(self) -> None:
        console = Console(file=io.StringIO(), force_terminal=False)
        stream = io.StringIO("line one\nline two\nline three\n")

        result = read_input(console, "You: ", stream=stream)

        assert result == "line one\nline two\nline three"

    def test_multiline_paste_without_trailing_newline(self) -> None:
        console = Console(file=io.StringIO(), force_terminal=False)
        stream = io.StringIO("alpha\nbeta\ngamma")

        result = read_input(console, prompt="", stream=stream)

        assert result == "alpha\nbeta\ngamma"

    def test_bracketed_paste_markers_stripped(self) -> None:
        console = Console(file=io.StringIO(), force_terminal=False)
        stream = io.StringIO("\x1b[200~first\nsecond\x1b[201~\n")

        result = read_input(console, prompt="", stream=stream)

        assert result == "first\nsecond"


class TestReadChatInput:
    def test_delegates_to_read_input(self) -> None:
        voice_config = MagicMock()
        with patch("my_agent.cli.read_input", return_value="typed message") as read_input_mock:
            result = _read_chat_input(voice_enabled=False, voice_config=voice_config)

        assert result == "typed message"
        read_input_mock.assert_called_once()

    def test_voice_command_still_works(self) -> None:
        voice_config = MagicMock()
        with patch("my_agent.cli.read_input", return_value="/mic"):
            with patch(
                "my_agent.cli.capture_and_transcribe",
                return_value="spoken text",
            ) as capture_mock:
                result = _read_chat_input(voice_enabled=True, voice_config=voice_config)

        assert result == "spoken text"
        capture_mock.assert_called_once()

    def test_custom_label_in_prompt(self) -> None:
        voice_config = MagicMock()
        with patch("my_agent.cli.read_input", return_value="fix that") as read_input_mock:
            result = _read_chat_input(
                voice_enabled=True,
                voice_config=voice_config,
                label="Redirect",
            )

        assert result == "fix that"
        read_input_mock.assert_called_once()
        prompt = read_input_mock.call_args.args[1]
        assert "Redirect" in prompt
        assert "/mic for voice" in prompt

    def test_redirect_mic_invokes_capture(self) -> None:
        voice_config = MagicMock()
        with patch("my_agent.cli.read_input", return_value="/mic"):
            with patch(
                "my_agent.cli.capture_and_transcribe",
                return_value="spoken correction",
            ) as capture_mock:
                result = _read_chat_input(
                    voice_enabled=True,
                    voice_config=voice_config,
                    label="Redirect",
                )

        assert result == "spoken correction"
        capture_mock.assert_called_once()
