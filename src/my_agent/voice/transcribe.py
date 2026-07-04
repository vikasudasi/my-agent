from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from my_agent.config import VoiceConfig

OPENROUTER_STT_URL = "https://openrouter.ai/api/v1/audio/transcriptions"

_FORMAT_BY_EXTENSION: dict[str, str] = {
    ".wav": "wav",
    ".mp3": "mp3",
    ".flac": "flac",
    ".m4a": "m4a",
    ".ogg": "ogg",
    ".webm": "webm",
    ".aac": "aac",
}


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    seconds: float | None = None
    cost: float | None = None


class TranscriptionError(RuntimeError):
    """Raised when OpenRouter speech-to-text fails."""


def audio_format_from_path(path: Path) -> str:
    """Map a file extension to an OpenRouter ``input_audio.format`` value."""
    ext = path.suffix.lower()
    try:
        return _FORMAT_BY_EXTENSION[ext]
    except KeyError as exc:
        supported = ", ".join(sorted(_FORMAT_BY_EXTENSION))
        raise ValueError(
            f"Unsupported audio format {ext!r}. Supported extensions: {supported}"
        ) from exc


def transcribe_audio(
    audio_bytes: bytes,
    *,
    audio_format: str,
    model: str,
    language: str | None = None,
    api_key: str | None = None,
    timeout_seconds: float = 120.0,
) -> TranscriptionResult:
    """Transcribe raw audio bytes via OpenRouter's STT endpoint."""
    resolved_key = (api_key or os.environ.get("OPENROUTER_API_KEY", "")).strip()
    if not resolved_key:
        raise TranscriptionError(
            "OPENROUTER_API_KEY is not set. Add it to .env (see .env.example)."
        )
    if not audio_bytes:
        raise TranscriptionError("Audio payload is empty.")

    payload: dict[str, object] = {
        "model": model,
        "input_audio": {
            "data": base64.b64encode(audio_bytes).decode("ascii"),
            "format": audio_format,
        },
    }
    if language:
        payload["language"] = language

    request = urllib.request.Request(
        OPENROUTER_STT_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {resolved_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise TranscriptionError(
            f"OpenRouter STT failed ({exc.code}): {error_body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise TranscriptionError(f"OpenRouter STT request failed: {exc}") from exc

    text = str(body.get("text", "")).strip()
    if not text:
        raise TranscriptionError("OpenRouter returned an empty transcription.")

    usage = body.get("usage") or {}
    seconds = usage.get("seconds")
    cost = usage.get("cost")
    return TranscriptionResult(
        text=text,
        seconds=float(seconds) if seconds is not None else None,
        cost=float(cost) if cost is not None else None,
    )


def transcribe_file(
    path: Path,
    voice_config: VoiceConfig,
    *,
    api_key: str | None = None,
) -> TranscriptionResult:
    """Read an audio file from disk and transcribe it."""
    audio_format = audio_format_from_path(path)
    audio_bytes = path.read_bytes()
    language = voice_config.language.strip() or None
    return transcribe_audio(
        audio_bytes,
        audio_format=audio_format,
        model=voice_config.model,
        language=language,
        api_key=api_key,
    )
