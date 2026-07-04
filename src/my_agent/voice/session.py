from __future__ import annotations

import contextvars
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from my_agent.voice.queue import VoiceQueue

_voice_queue: contextvars.ContextVar[VoiceQueue | None] = contextvars.ContextVar(
    "voice_queue",
    default=None,
)


def get_voice_queue() -> VoiceQueue | None:
    """Return the active conversation voice queue, if any."""
    return _voice_queue.get()


def activate_voice_queue(voice_queue: VoiceQueue | None) -> contextvars.Token:
    """Bind a voice queue for the current async/thread context."""
    return _voice_queue.set(voice_queue)


def deactivate_voice_queue(token: contextvars.Token) -> None:
    """Restore the previous voice queue binding."""
    _voice_queue.reset(token)
