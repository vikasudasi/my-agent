from __future__ import annotations

import io
import threading
import time
import wave
from typing import Callable

from my_agent.config import VoiceConfig


class CaptureCancelled(RuntimeError):
    """Raised when the user cancels microphone capture."""


class CaptureDependencyError(RuntimeError):
    """Raised when optional microphone dependencies are unavailable."""


def _import_numpy():
    try:
        import numpy as np  # type: ignore[import-untyped]
    except ImportError as exc:
        raise CaptureDependencyError(
            "Microphone capture requires the 'numpy' package. "
            "Install my-agent with: pip install 'my-agent[voice]'"
        ) from exc
    return np


def _import_sounddevice():
    try:
        import sounddevice as sd  # type: ignore[import-untyped]
    except ImportError as exc:
        raise CaptureDependencyError(
            "Microphone capture requires the 'sounddevice' package. "
            "Install my-agent with: pip install 'my-agent[voice]'"
        ) from exc
    return sd


def _import_pynput_keyboard():
    try:
        from pynput import keyboard  # type: ignore[import-untyped]
    except ImportError as exc:
        raise CaptureDependencyError(
            "Push-to-talk requires the 'pynput' package. "
            "Install my-agent with: pip install 'my-agent[voice]'"
        ) from exc
    return keyboard


def _frames_to_wav_bytes(frames, sample_rate: int) -> bytes:  # noqa: ANN001
    """Encode mono int16 PCM frames as an in-memory WAV file."""
    np = _import_numpy()
    clipped = np.clip(frames, -1.0, 1.0)
    pcm = (clipped * np.iinfo(np.int16).max).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())
    return buffer.getvalue()


def record_push_to_talk(
    voice_config: VoiceConfig,
    *,
    on_waiting: Callable[[], None] | None = None,
    on_recording: Callable[[], None] | None = None,
    on_stopped: Callable[[float], None] | None = None,
) -> bytes:
    """Record audio while the user holds the space bar.

    Returns WAV bytes suitable for OpenRouter transcription.
    """
    sd = _import_sounddevice()
    keyboard = _import_pynput_keyboard()
    np = _import_numpy()

    sample_rate = 16_000
    chunks: list = []
    recording = threading.Event()
    finished = threading.Event()
    cancelled = threading.Event()
    started_at = 0.0

    def _audio_callback(indata, _frames, _time_info, status) -> None:  # noqa: ANN001
        if status:
            return
        if recording.is_set() and not cancelled.is_set():
            chunks.append(indata.copy())

    def _on_press(key) -> None:  # noqa: ANN001
        nonlocal started_at
        if key == keyboard.Key.esc:
            cancelled.set()
            recording.clear()
            finished.set()
            return
        if key == keyboard.Key.space and not recording.is_set() and not cancelled.is_set():
            chunks.clear()
            started_at = time.monotonic()
            recording.set()
            if on_recording is not None:
                on_recording()

    def _on_release(key) -> bool | None:  # noqa: ANN001
        if key == keyboard.Key.space and recording.is_set():
            recording.clear()
            finished.set()
            return False
        if key == keyboard.Key.esc:
            cancelled.set()
            recording.clear()
            finished.set()
            return False
        return None

    if on_waiting is not None:
        on_waiting()

    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        callback=_audio_callback,
    ):
        listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
        listener.start()
        try:
            finished.wait(timeout=voice_config.max_duration_seconds + 30.0)
        finally:
            listener.stop()

    if cancelled.is_set():
        raise CaptureCancelled("Voice capture cancelled.")

    if not chunks:
        raise CaptureCancelled("No audio captured. Hold Space while speaking.")

    duration = time.monotonic() - started_at if started_at else 0.0
    if duration > voice_config.max_duration_seconds:
        raise CaptureCancelled(
            f"Recording exceeded {voice_config.max_duration_seconds:.0f}s limit."
        )

    frames = np.concatenate(chunks, axis=0)
    if on_stopped is not None:
        on_stopped(duration)

    return _frames_to_wav_bytes(frames, sample_rate)
