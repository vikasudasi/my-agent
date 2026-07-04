from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from my_agent.config import VoiceConversationConfig
from my_agent.voice.notes import print_speaker_note
from my_agent.voice.queue import VoiceQueue
from my_agent.voice.synthesize import build_synthesizer

if TYPE_CHECKING:
    from rich.console import Console


def create_voice_queue(
    config: VoiceConversationConfig,
    *,
    console: Console | None = None,
) -> VoiceQueue:
    """Build a voice queue for conversation mode."""
    synthesize = build_synthesizer(
        backend=config.tts_backend,
        voice=config.tts_voice,
    )
    on_enqueue = None
    if config.show_speaker_notes and console is not None:
        on_enqueue = lambda text: print_speaker_note(console, text)
    return VoiceQueue(synthesize, on_enqueue=on_enqueue)


def effective_voice_config(voice_config, *, conversation_enabled: bool):
    """Return voice input settings tuned for conversation mode."""
    if not conversation_enabled:
        return voice_config
    return replace(voice_config, confirm_before_send=False)
