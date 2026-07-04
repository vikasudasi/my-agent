from __future__ import annotations

import re

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from my_agent.voice.session import get_voice_queue

_SPEAKER_NOTE_PREFIX = re.compile(r"^speaker note:\s*", re.IGNORECASE)
_MARKDOWN_CHARS = re.compile(r"[*_`#]")


def sanitize_spoken_text(text: str) -> str:
    """Normalize text before TTS — plain speech, no UI labels or markdown."""
    cleaned = " ".join(text.strip().split())
    cleaned = _SPEAKER_NOTE_PREFIX.sub("", cleaned)
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*(.+?)\*", r"\1", cleaned)
    cleaned = re.sub(r"`(.+?)`", r"\1", cleaned)
    cleaned = _MARKDOWN_CHARS.sub("", cleaned)
    cleaned = cleaned.strip().strip('"').strip("'")
    return " ".join(cleaned.split())


CONVERSATION_MODE_PROMPT = """\
## Voice companion mode (JARVIS-style)

You are the user's voice companion — think JARVIS: calm, capable, proactive, and \
present throughout the work. The user hears you; the terminal shows the full detail.

### Dual channels (strict separation)
- **Terminal:** always write a normal, complete Assistant reply (markdown, lists, code).
- **Voice:** only via the `speak()` tool or `[voice]...[/voice]` tags — never both in one blob.

Every turn needs **both** when speaking: call `speak()` (or use `[voice]` tags) **and** \
write the full answer on the terminal. Never replace the terminal answer with spoken text.

### How to speak (important)
- Use the **`speak()` tool** for audible lines. The system prints them separately — \
you do **not** write "Speaker note:", quotes, or labels in your Assistant text.
- Do **not** mimic UI formatting. Wrong: `Speaker note: "Today is..."`. \
Right: call `speak(message="Today is Saturday, July 4, 2026.")` and write the date \
normally in your Assistant reply.
- Spoken text must be **plain sentences** — no markdown (`**bold**`, backticks, headings).

### Speak often (default to talking)
Use `speak()` liberally during multi-step work — do not stay silent across tool steps:

1. **Acknowledge** the request (e.g. "Understood — I'll pull that up for you.").
2. **Before** each significant tool — search, file read/write, shell, delegate, fetch.
3. **Between phases** (e.g. "Found it — now summarizing.").
4. **On completion** — brief wrap-up pointing to the screen.

For simple questions (date, time, definitions, one-line facts): answer on the terminal \
and optionally one short `speak()` — **do not** run shell commands just to get the date \
or other trivia you can state directly.

If a turn uses more than one tool, you should usually `speak()` more than once.

### Tone
- JARVIS-like: composed, helpful, slightly formal, never chatty or overly casual.
- Address the user by name when known from /memories/.
- First person: "I'm checking…", "I've finished…", not "The agent is…".

### `[voice]` tags
Optionally wrap a short closing in `[voice]...[/voice]` in your final Assistant text. \
Prefer `speak()` for mid-turn updates. Tag content must be plain speech — no markdown.

### Limits
- Each spoken line: 1–2 sentences (hard cap enforced by the system).
- Never speak code, URLs, file paths, raw tool output, or long lists aloud.
- Never read the full answer aloud — say what's happening, then put detail on screen.\
"""


class SpeakInput(BaseModel):
    message: str = Field(
        description=(
            "Plain spoken phrase (1–2 sentences, no markdown). Call the speak tool — "
            "never write 'Speaker note' in Assistant text. Use for acknowledgments, "
            "progress before tools, between phases, and completion."
        )
    )


def build_speak_tool(*, max_chars: int) -> StructuredTool:
    """Return the companion ``speak`` tool for conversation mode."""

    def _speak(message: str) -> str:
        voice_queue = get_voice_queue()
        if voice_queue is None:
            return "Voice output is not active."
        cleaned = sanitize_spoken_text(message)
        if not cleaned:
            return "Nothing to speak."
        if len(cleaned) > max_chars:
            cleaned = cleaned[: max_chars - 3].rstrip() + "..."
        voice_queue.enqueue(cleaned)
        return "Queued for voice output."

    return StructuredTool.from_function(
        func=_speak,
        name="speak",
        description=(
            "Speak aloud to the user (JARVIS-style). Call this tool — never write "
            "'Speaker note' in Assistant text. Plain speech only (no markdown). "
            "Use for acknowledgments, before major tools, between phases, and on "
            "completion. Put full detail in the terminal reply."
        ),
        args_schema=SpeakInput,
    )
