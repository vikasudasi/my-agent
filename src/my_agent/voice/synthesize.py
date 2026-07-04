from __future__ import annotations

import shutil
import subprocess
from typing import Callable


class SynthesisError(RuntimeError):
    """Raised when text-to-speech playback fails."""


def build_synthesizer(*, backend: str, voice: str = "") -> Callable[[str], None]:
    """Return a callable that speaks ``text`` using the configured backend."""
    normalized = backend.strip().lower()
    if normalized in {"macos", "say"}:
        return _macos_synthesizer(voice=voice)
    raise SynthesisError(
        f"Unsupported TTS backend {backend!r}. Supported: macos"
    )


def _macos_synthesizer(*, voice: str) -> Callable[[str], None]:
    if shutil.which("say") is None:
        raise SynthesisError(
            "macOS 'say' command not found. Conversation mode requires macOS TTS."
        )

    def speak(text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        command = ["say"]
        if voice.strip():
            command.extend(["-v", voice.strip()])
        command.append(cleaned)
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as exc:
            raise SynthesisError(f"macOS say failed: {exc}") from exc

    return speak
