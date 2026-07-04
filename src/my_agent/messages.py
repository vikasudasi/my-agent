from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage


def extract_messages(state: Any) -> list[BaseMessage]:
    """Extract LangChain messages from an agent state object or dict."""
    if isinstance(state, dict):
        messages = state.get("messages", [])
    else:
        messages = getattr(state, "messages", [])
    return [message for message in messages if isinstance(message, BaseMessage)]


def message_text(message: BaseMessage) -> str:
    """Return plain text from a message's content blocks."""
    return stringify_content(message.content)


def latest_assistant_text(messages: list[BaseMessage]) -> str:
    """Return text from the most recent AI message, if any."""
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return stringify_content(message.content)
    return ""


def stringify_content(content: Any) -> str:
    """Normalize message content (str, blocks, or other) to plain text."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, dict):
                parts.append(json.dumps(block, ensure_ascii=True))
            else:
                parts.append(str(block))
        return "\n".join(part for part in parts if part).strip()
    if content is None:
        return ""
    return str(content).strip()


def snippet(
    text: str | None,
    max_len: int,
    *,
    empty: str | None = None,
) -> str | None:
    """Truncate text to max_len; return ``empty`` when there is no content."""
    if not text or not text.strip():
        return empty
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[: max_len - 3]}..."
