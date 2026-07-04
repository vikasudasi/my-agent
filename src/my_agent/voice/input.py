from __future__ import annotations

from enum import Enum
from typing import Callable

from rich.console import Console

from my_agent.config import VoiceConfig
from my_agent.voice.capture import CaptureCancelled, record_push_to_talk
from my_agent.voice.transcribe import TranscriptionError, TranscriptionResult, transcribe_audio


class ConfirmAction(Enum):
    SEND = "send"
    CANCEL = "cancel"
    RERECORD = "rerecord"


def confirm_transcript(
    console: Console,
    transcript: str,
    *,
    allow_rerecord: bool = True,
) -> ConfirmAction | str:
    """Let the user approve, edit, re-record, or cancel a transcript."""
    current = transcript.strip()
    while True:
        console.print(f'\n[bold]Transcript:[/bold] "{current}"')
        options = "[Enter]=send, [e]=edit"
        if allow_rerecord:
            options += ", [r]=re-record"
        options += ", [c]=cancel"
        choice = console.input(f"Send? ({options}): ").strip().lower()

        if choice in {"", "y", "yes", "send"}:
            return current
        if choice in {"e", "edit"}:
            edited = console.input("[bold yellow]Edit:[/bold yellow] ").strip()
            if edited:
                current = edited
            continue
        if allow_rerecord and choice in {"r", "re-record", "record"}:
            return ConfirmAction.RERECORD
        if choice in {"c", "cancel"}:
            return ConfirmAction.CANCEL
        console.print("[yellow]Please press Enter, e, r, or c.[/yellow]")


def capture_and_transcribe(
    console: Console,
    voice_config: VoiceConfig,
    *,
    transcribe: Callable[[bytes], TranscriptionResult] | None = None,
) -> str | None:
    """Push-to-talk capture, transcription, and optional confirmation."""
    transcribe_fn = transcribe or (
        lambda audio: transcribe_audio(
            audio,
            audio_format="wav",
            model=voice_config.model,
            language=voice_config.language.strip() or None,
        )
    )

    while True:
        try:
            console.print(
                "[dim]Hold [Space] to record, release to send. Esc to cancel.[/dim]"
            )
            wav_bytes = record_push_to_talk(
                voice_config,
                on_waiting=lambda: console.print("[dim]Waiting for Space…[/dim]"),
                on_recording=lambda: console.print("[bold cyan]Recording…[/bold cyan]"),
                on_stopped=lambda seconds: console.print(
                    f"[dim]Captured {seconds:.1f}s of audio. Transcribing…[/dim]"
                ),
            )
            result = transcribe_fn(wav_bytes)
        except CaptureCancelled as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            return None
        except TranscriptionError as exc:
            console.print(f"[red]Transcription failed:[/red] {exc}")
            return None

        if result.seconds is not None or result.cost is not None:
            parts: list[str] = []
            if result.seconds is not None:
                parts.append(f"{result.seconds:.1f}s audio")
            if result.cost is not None:
                parts.append(f"${result.cost:.4f}")
            console.print(f"[dim]STT usage: {', '.join(parts)}[/dim]")

        if not voice_config.confirm_before_send:
            return result.text

        decision = confirm_transcript(console, result.text, allow_rerecord=True)
        if isinstance(decision, str):
            return decision
        if decision is ConfirmAction.CANCEL:
            return None
        if decision is ConfirmAction.RERECORD:
            continue
