from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint
from langgraph.checkpoint.memory import InMemorySaver, MemorySaver

from my_agent.config import AppConfig

_LATEST_THREADS_SQL = """
SELECT c.thread_id, c.type, c.checkpoint
FROM checkpoints c
INNER JOIN (
    SELECT thread_id, MAX(checkpoint_id) AS checkpoint_id
    FROM checkpoints
    WHERE checkpoint_ns = ''
    GROUP BY thread_id
) latest
    ON c.thread_id = latest.thread_id
    AND c.checkpoint_id = latest.checkpoint_id
ORDER BY c.checkpoint_id DESC
"""


@dataclass(frozen=True)
class ThreadSummary:
    thread_id: str
    updated_at: str | None
    message_count: int = 0
    first_user_message: str | None = None


@dataclass(frozen=True)
class PruneResult:
    deleted: tuple[str, ...]
    dry_run: bool
    vacuumed: bool


def _resolve_sqlite_path(config: AppConfig) -> Path:
    raw = config.checkpoint.sqlite_path
    expanded = Path(os.path.expanduser(raw))
    if expanded.is_absolute():
        return expanded.resolve()
    return (config.paths.agent_state_dir / expanded).resolve()


@lru_cache(maxsize=4)
def build_checkpointer(config_key: tuple[str, str, str]) -> BaseCheckpointSaver:
    """Return a process-lifetime checkpointer singleton.

    ``config_key`` is ``(backend, sqlite_path, agent_state_dir)`` so the
    cached instance tracks config changes across reloads within one process.
    """
    backend, sqlite_path, _agent_state_dir = config_key
    if backend == "memory":
        return MemorySaver()

    db_path = Path(sqlite_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    from langgraph.checkpoint.sqlite import SqliteSaver

    saver = SqliteSaver(conn)
    saver.setup()
    return saver


def get_checkpointer(config: AppConfig) -> BaseCheckpointSaver:
    backend = config.checkpoint.backend
    if backend not in {"sqlite", "memory"}:
        raise ValueError(
            f"config.toml [checkpoint].backend must be 'sqlite' or 'memory', got {backend!r}"
        )

    key = (
        backend,
        str(_resolve_sqlite_path(config)),
        str(config.paths.agent_state_dir),
    )
    return build_checkpointer(key)


def list_threads(
    config: AppConfig,
    *,
    agent: Any | None = None,
    limit: int = 20,
) -> list[ThreadSummary]:
    """Return recent threads ordered by latest checkpoint (newest first)."""
    checkpointer = get_checkpointer(config)
    if config.checkpoint.backend == "memory":
        summaries = _list_threads_memory(checkpointer, limit=limit)
    else:
        summaries = _list_threads_sqlite(checkpointer, config, limit=limit)

    if agent is None:
        return summaries

    return [_enrich_thread_summary(agent, summary) for summary in summaries]


def delete_thread(config: AppConfig, thread_id: str) -> None:
    """Delete all checkpoint data for a thread."""
    checkpointer = get_checkpointer(config)
    checkpointer.delete_thread(thread_id)


def prune_threads(
    config: AppConfig,
    *,
    keep: int | None = None,
    max_age_days: int | None = None,
    protect_latest: bool = True,
    dry_run: bool = False,
    vacuum: bool = True,
) -> PruneResult:
    """Delete old threads by count and/or age limits.

    A thread is removed when it exceeds the keep-newest count and/or is older
    than ``max_age_days``. ``0`` disables each limit. Config defaults apply
    when ``keep`` or ``max_age_days`` is ``None``.
    """
    keep_limit = config.checkpoint.max_threads if keep is None else keep
    age_limit = (
        config.checkpoint.max_thread_age_days
        if max_age_days is None
        else max_age_days
    )

    if keep_limit <= 0 and age_limit <= 0:
        return PruneResult(deleted=(), dry_run=dry_run, vacuumed=False)

    all_threads = list_threads(config, limit=0)
    if not all_threads:
        return PruneResult(deleted=(), dry_run=dry_run, vacuumed=False)

    protected = {all_threads[0].thread_id} if protect_latest and all_threads else set()
    to_delete = _select_threads_to_prune(
        all_threads,
        keep=keep_limit,
        max_age_days=age_limit,
        protected=protected,
    )

    if not dry_run:
        checkpointer = get_checkpointer(config)
        for thread_id in to_delete:
            checkpointer.delete_thread(thread_id)
        vacuumed = vacuum and bool(to_delete) and config.checkpoint.backend == "sqlite"
        if vacuumed:
            _vacuum_sqlite(config)
    else:
        vacuumed = False

    return PruneResult(
        deleted=tuple(to_delete),
        dry_run=dry_run,
        vacuumed=vacuumed,
    )


def _select_threads_to_prune(
    threads: list[ThreadSummary],
    *,
    keep: int,
    max_age_days: int,
    protected: set[str],
) -> list[str]:
    """Return thread ids to delete (newest-first input list)."""
    candidates: set[str] = set()

    if keep > 0 and len(threads) > keep:
        for summary in threads[keep:]:
            candidates.add(summary.thread_id)

    if max_age_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        for summary in threads:
            updated = _parse_checkpoint_ts(summary.updated_at)
            if updated is not None and updated < cutoff:
                candidates.add(summary.thread_id)

    return [
        thread_id
        for thread_id in candidates
        if thread_id not in protected
    ]


def _parse_checkpoint_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _vacuum_sqlite(config: AppConfig) -> None:
    db_path = _resolve_sqlite_path(config)
    if not db_path.is_file():
        return
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("VACUUM")
    finally:
        conn.close()


def get_latest_thread_id(config: AppConfig) -> str | None:
    """Return the most recently updated thread id, if any."""
    threads = list_threads(config, limit=1)
    return threads[0].thread_id if threads else None


def _list_threads_sqlite(
    checkpointer: BaseCheckpointSaver,
    config: AppConfig,
    *,
    limit: int = 20,
) -> list[ThreadSummary]:
    db_path = _resolve_sqlite_path(config)
    if not db_path.is_file():
        return []

    query = _LATEST_THREADS_SQL
    params: tuple[Any, ...] = ()
    if limit > 0:
        query = f"{query}\nLIMIT ?"
        params = (limit,)

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    summaries: list[ThreadSummary] = []
    for thread_id, blob_type, checkpoint_blob in rows:
        checkpoint = _load_checkpoint_blob(checkpointer, blob_type, checkpoint_blob)
        summaries.append(
            ThreadSummary(
                thread_id=thread_id,
                updated_at=checkpoint.get("ts"),
            )
        )
    return summaries


def _list_threads_memory(
    checkpointer: BaseCheckpointSaver,
    *,
    limit: int = 20,
) -> list[ThreadSummary]:
    if not isinstance(checkpointer, InMemorySaver):
        return []

    summaries: list[ThreadSummary] = []
    for thread_id in checkpointer.storage:
        checkpoint_tuple = checkpointer.get_tuple(
            {"configurable": {"thread_id": thread_id}}
        )
        if checkpoint_tuple is None:
            continue
        summaries.append(
            ThreadSummary(
                thread_id=thread_id,
                updated_at=checkpoint_tuple.checkpoint.get("ts"),
            )
        )

    summaries.sort(key=lambda item: item.updated_at or "", reverse=True)
    if limit > 0:
        return summaries[:limit]
    return summaries


def _load_checkpoint_blob(
    checkpointer: BaseCheckpointSaver,
    blob_type: str,
    checkpoint_blob: bytes,
) -> Checkpoint:
    return checkpointer.serde.loads_typed((blob_type, checkpoint_blob))


def _enrich_thread_summary(agent: Any, summary: ThreadSummary) -> ThreadSummary:
    from my_agent.runner import get_thread_state_info

    info = get_thread_state_info(agent, summary.thread_id)
    if info is None:
        return summary

    return ThreadSummary(
        thread_id=summary.thread_id,
        updated_at=summary.updated_at,
        message_count=info.message_count,
        first_user_message=info.first_user_message,
    )
