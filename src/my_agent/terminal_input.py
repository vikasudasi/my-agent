from __future__ import annotations

import io
import select
import sys
from typing import TextIO

from rich.console import Console

_BRACKETED_PASTE_START = "\x1b[200~"
_BRACKETED_PASTE_END = "\x1b[201~"


def enable_bracketed_paste() -> None:
    """Ask the terminal to wrap pasted text in bracketed-paste escape sequences."""
    if sys.stdout.isatty():
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.flush()


def disable_bracketed_paste() -> None:
    """Turn off bracketed-paste mode when leaving interactive input."""
    if sys.stdout.isatty():
        sys.stdout.write("\x1b[?2004l")
        sys.stdout.flush()


def _has_pending_input(stream: TextIO | None) -> bool:
    """Return True when more input is already buffered (typical of a multi-line paste)."""
    if stream is not None:
        if isinstance(stream, io.StringIO):
            return stream.tell() < len(stream.getvalue())
        try:
            return bool(select.select([stream], [], [], 0.0)[0])
        except (OSError, ValueError):
            return False

    try:
        return bool(select.select([sys.stdin], [], [], 0.0)[0])
    except (OSError, ValueError):
        return False


def _read_line(stream: TextIO | None) -> str:
    if stream is not None:
        line = stream.readline()
        if not line:
            return line
        if line.endswith("\n"):
            return line[:-1]
        if line.endswith("\r"):
            return line[:-1]
        return line
    return input()


def _strip_bracketed_paste_markers(text: str) -> str:
    return text.replace(_BRACKETED_PASTE_START, "").replace(_BRACKETED_PASTE_END, "")


def read_input(
    console: Console,
    prompt: str = "",
    *,
    stream: TextIO | None = None,
) -> str:
    """Read user input, coalescing multi-line paste into a single string.

  When the user pastes several lines, terminals often buffer the full paste
  before the application reads it. ``input()`` returns after the first newline,
  leaving the rest to be consumed as separate REPL turns. This helper reads
  the first line, then drains any immediately pending input so a paste is
  delivered as one message.
    """
    if prompt:
        console.print(prompt, end="")

    lines = [_read_line(stream)]
    while _has_pending_input(stream):
        lines.append(_read_line(stream))

    return _strip_bracketed_paste_markers("\n".join(lines))
