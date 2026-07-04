from __future__ import annotations

from my_agent.voice.companion import sanitize_spoken_text
from my_agent.voice.queue import VoiceQueue

_VOICE_OPEN = "[voice]"
_VOICE_CLOSE = "[/voice]"


class VoiceTagStreamFilter:
    """Extract ``[voice]...[/voice]`` blocks for TTS while streaming assistant text."""

    def __init__(
        self,
        voice_queue: VoiceQueue,
        *,
        max_chars: int,
        strip_from_terminal: bool = True,
    ) -> None:
        self._voice_queue = voice_queue
        self._max_chars = max_chars
        self._strip_from_terminal = strip_from_terminal
        self._carry = ""
        self._in_voice = False
        self._voice_buffer = ""

    def feed(self, text: str) -> str:
        """Process streamed text; return the portion that should appear on terminal."""
        if not text:
            return ""
        self._carry += text
        terminal_parts: list[str] = []

        while self._carry:
            if self._in_voice:
                close_index = self._carry.find(_VOICE_CLOSE)
                if close_index == -1:
                    hold_back = max(0, len(self._carry) - len(_VOICE_CLOSE) + 1)
                    self._voice_buffer += self._carry[:hold_back]
                    self._carry = self._carry[hold_back:]
                    break
                self._voice_buffer += self._carry[:close_index]
                self._carry = self._carry[close_index + len(_VOICE_CLOSE) :]
                self._enqueue_voice(self._voice_buffer)
                self._voice_buffer = ""
                self._in_voice = False
                continue

            open_index = self._carry.find(_VOICE_OPEN)
            if open_index == -1:
                hold_back = max(0, len(self._carry) - len(_VOICE_OPEN) + 1)
                terminal_parts.append(self._carry[:hold_back])
                self._carry = self._carry[hold_back:]
                if hold_back == 0:
                    break
                continue

            terminal_parts.append(self._carry[:open_index])
            self._carry = self._carry[open_index + len(_VOICE_OPEN) :]
            self._in_voice = True

        terminal_text = "".join(terminal_parts)
        if self._strip_from_terminal and self._in_voice:
            return terminal_text
        if self._strip_from_terminal:
            return terminal_text
        return terminal_text

    def flush(self) -> str:
        """Flush trailing buffered text at end of stream."""
        trailing = ""
        if self._in_voice and self._voice_buffer.strip():
            self._enqueue_voice(self._voice_buffer)
            self._voice_buffer = ""
            self._in_voice = False
        elif not self._in_voice and self._carry:
            trailing = self._carry
            self._carry = ""
        else:
            self._carry = ""
        return trailing

    def _enqueue_voice(self, text: str) -> None:
        cleaned = sanitize_spoken_text(text)
        if not cleaned:
            return
        if len(cleaned) > self._max_chars:
            cleaned = cleaned[: self._max_chars - 3].rstrip() + "..."
        self._voice_queue.enqueue(cleaned)
