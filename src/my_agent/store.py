from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from my_agent.config import AppConfig

MEMORIES_NAMESPACE: tuple[str, ...] = ("memories",)


@dataclass(frozen=True)
class MemoryFileSummary:
    path: str
    updated_at: str | None
    size: int
    snippet: str | None


def _resolve_sqlite_path(config: AppConfig) -> Path:
    raw = config.store.sqlite_path
    expanded = Path(os.path.expanduser(raw))
    if expanded.is_absolute():
        return expanded.resolve()
    return (config.paths.agent_state_dir / expanded).resolve()


@lru_cache(maxsize=4)
def build_store(config_key: tuple[str, str, str]) -> BaseStore:
    """Return a process-lifetime store singleton."""
    backend, sqlite_path, _agent_state_dir = config_key
    if backend == "memory":
        return InMemoryStore()

    db_path = Path(sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(db_path),
        check_same_thread=False,
        isolation_level=None,
    )
    from langgraph.store.sqlite import SqliteStore

    store = SqliteStore(conn)
    store.setup()
    return store


def get_store(config: AppConfig) -> BaseStore:
    backend = config.store.backend
    if backend not in {"sqlite", "memory"}:
        raise ValueError(
            f"config.toml [store].backend must be 'sqlite' or 'memory', got {backend!r}"
        )

    key = (
        backend,
        str(_resolve_sqlite_path(config)),
        str(config.paths.agent_state_dir),
    )
    return build_store(key)


def list_memories(
    config: AppConfig,
    *,
    limit: int = 50,
) -> list[MemoryFileSummary]:
    """List files under /memories/ (newest first)."""
    store = get_store(config)
    results = store.search(MEMORIES_NAMESPACE, limit=limit)
    summaries: list[MemoryFileSummary] = []
    for item in results:
        content = _extract_content(item.value)
        summaries.append(
            MemoryFileSummary(
                path=str(item.key),
                updated_at=str(item.updated_at) if item.updated_at else None,
                size=len(content),
                snippet=_snippet(content),
            )
        )

    summaries.sort(key=lambda entry: entry.updated_at or "", reverse=True)
    return summaries[:limit]


def read_memory(config: AppConfig, path: str) -> str | None:
    """Return file content for a /memories/ path, or None if missing."""
    normalized = _normalize_memory_path(path)
    store = get_store(config)
    item = store.get(MEMORIES_NAMESPACE, normalized)
    if item is None:
        return None
    return _extract_content(item.value)


def _normalize_memory_path(path: str) -> str:
    cleaned = path.strip()
    if not cleaned.startswith("/memories/"):
        raise ValueError(f"Memory path must start with /memories/, got {path!r}")
    return cleaned


def _extract_content(value: dict) -> str:
    raw = value.get("content", "")
    if isinstance(raw, list):
        return "\n".join(str(line) for line in raw)
    return str(raw) if raw is not None else ""


def _snippet(text: str, *, max_len: int = 72) -> str | None:
    if not text.strip():
        return None
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[: max_len - 1]}…"
