from __future__ import annotations

import queue
import threading
from typing import Callable


class VoiceQueue:
    """Serialize short companion phrases for text-to-speech playback."""

    def __init__(
        self,
        synthesize: Callable[[str], None],
        *,
        on_enqueue: Callable[[str], None] | None = None,
    ) -> None:
        self._synthesize = synthesize
        self._on_enqueue = on_enqueue
        self._pending: queue.Queue[str | None] = queue.Queue()
        self._worker = threading.Thread(target=self._run, name="voice-queue", daemon=True)
        self._active = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._closed = False
        self._worker.start()

    def enqueue(self, text: str) -> None:
        """Queue text for spoken output."""
        cleaned = " ".join(text.split())
        if not cleaned or self._closed:
            return
        if self._on_enqueue is not None:
            self._on_enqueue(cleaned)
        self._idle.clear()
        self._pending.put(cleaned)

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until all queued speech has finished."""
        if timeout is None:
            return self._idle.wait()
        return self._idle.wait(timeout=timeout)

    def close(self) -> None:
        """Stop accepting new phrases and shut down the worker."""
        if self._closed:
            return
        self._closed = True
        self._pending.put(None)
        self._worker.join(timeout=5.0)

    def _run(self) -> None:
        while True:
            phrase = self._pending.get()
            try:
                if phrase is None:
                    return
                self._active.set()
                self._synthesize(phrase)
            finally:
                self._pending.task_done()
                if self._pending.empty():
                    self._active.clear()
                    self._idle.set()
