from __future__ import annotations

from rich.console import Console

SPEAKER_NOTE_LABEL = "[bold magenta]Speaker note[/bold magenta]"


def print_speaker_note(console: Console, text: str) -> None:
    """Show companion audio text on the terminal."""
    cleaned = " ".join(text.split())
    if not cleaned:
        return
    console.print(f'{SPEAKER_NOTE_LABEL}: [italic cyan]"{cleaned}"[/italic cyan]')
