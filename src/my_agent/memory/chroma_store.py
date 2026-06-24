from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_huggingface import HuggingFaceEmbeddings

from my_agent.config import AppConfig


@dataclass
class ConversationHit:
    thread_id: str
    role: str
    content: str
    timestamp: str
    turn_index: int
    message_id: str
    score: float | None = None


class ChromaConversationStore:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._vector_store = Chroma(
            collection_name=config.memory.collection_name,
            embedding_function=HuggingFaceEmbeddings(
                model_name=config.memory.embedding_model
            ),
            persist_directory=str(config.paths.chroma_dir),
        )

    def index_messages(
        self,
        thread_id: str,
        messages: list[BaseMessage],
        *,
        turn_index: int,
    ) -> int:
        if not messages:
            return 0

        timestamp = datetime.now(timezone.utc).isoformat()
        documents: list[Document] = []
        user_text = ""
        assistant_text = ""

        for message in messages:
            role, content = _message_role_and_content(message)
            if not content.strip():
                continue

            message_id = _message_id(thread_id, turn_index, role, content)
            documents.append(
                Document(
                    page_content=content,
                    metadata={
                        "thread_id": thread_id,
                        "role": role,
                        "timestamp": timestamp,
                        "turn_index": turn_index,
                        "message_id": message_id,
                        "doc_type": "message",
                    },
                )
            )

            if role == "user":
                user_text = content
            elif role == "assistant":
                assistant_text = content

        if user_text and assistant_text:
            summary = f"User: {user_text}\n\nAssistant: {assistant_text}"
            documents.append(
                Document(
                    page_content=summary,
                    metadata={
                        "thread_id": thread_id,
                        "role": "turn_summary",
                        "timestamp": timestamp,
                        "turn_index": turn_index,
                        "message_id": _message_id(
                            thread_id, turn_index, "turn_summary", summary
                        ),
                        "doc_type": "turn_summary",
                    },
                )
            )

        if not documents:
            return 0

        self._vector_store.add_documents(documents)
        return len(documents)

    def search(self, query: str, limit: int = 5) -> list[ConversationHit]:
        results = self._vector_store.similarity_search_with_score(query, k=limit)
        hits: list[ConversationHit] = []
        for document, score in results:
            metadata = document.metadata
            hits.append(
                ConversationHit(
                    thread_id=str(metadata.get("thread_id", "")),
                    role=str(metadata.get("role", "")),
                    content=document.page_content,
                    timestamp=str(metadata.get("timestamp", "")),
                    turn_index=int(metadata.get("turn_index", 0)),
                    message_id=str(metadata.get("message_id", "")),
                    score=float(score),
                )
            )
        return hits

    def get_conversation(self, thread_id: str) -> list[ConversationHit]:
        collection = self._vector_store._collection
        raw = collection.get(where={"thread_id": thread_id}, include=["documents", "metadatas"])
        hits: list[ConversationHit] = []
        for content, metadata in zip(raw.get("documents", []), raw.get("metadatas", [])):
            if metadata is None:
                continue
            hits.append(
                ConversationHit(
                    thread_id=str(metadata.get("thread_id", "")),
                    role=str(metadata.get("role", "")),
                    content=content or "",
                    timestamp=str(metadata.get("timestamp", "")),
                    turn_index=int(metadata.get("turn_index", 0)),
                    message_id=str(metadata.get("message_id", "")),
                )
            )
        hits.sort(key=lambda hit: (hit.turn_index, hit.timestamp, hit.role))
        return hits

    def list_recent_conversations(self, limit: int = 10) -> list[dict[str, Any]]:
        collection = self._vector_store._collection
        raw = collection.get(include=["documents", "metadatas"])
        threads: dict[str, dict[str, Any]] = {}

        for content, metadata in zip(raw.get("documents", []), raw.get("metadatas", [])):
            if metadata is None:
                continue
            thread_id = str(metadata.get("thread_id", ""))
            if not thread_id:
                continue

            timestamp = str(metadata.get("timestamp", ""))
            role = str(metadata.get("role", ""))
            entry = threads.setdefault(
                thread_id,
                {
                    "thread_id": thread_id,
                    "first_user_message": "",
                    "latest_timestamp": "",
                },
            )

            if timestamp > entry["latest_timestamp"]:
                entry["latest_timestamp"] = timestamp

            if role == "user" and not entry["first_user_message"]:
                entry["first_user_message"] = _snippet(content or "", 200)

        recent = sorted(
            threads.values(),
            key=lambda item: item["latest_timestamp"],
            reverse=True,
        )
        return recent[:limit]


def _message_role_and_content(message: BaseMessage) -> tuple[str, str]:
    if isinstance(message, HumanMessage):
        return "user", _stringify_content(message.content)
    if isinstance(message, AIMessage):
        return "assistant", _stringify_content(message.content)
    if isinstance(message, ToolMessage):
        return "tool", _stringify_content(message.content)
    message_type = getattr(message, "type", message.__class__.__name__)
    return str(message_type), _stringify_content(getattr(message, "content", ""))


def _stringify_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                else:
                    parts.append(json.dumps(block, ensure_ascii=True))
            else:
                parts.append(str(block))
        return "\n".join(part for part in parts if part)
    if content is None:
        return ""
    return str(content)


def _message_id(thread_id: str, turn_index: int, role: str, content: str) -> str:
    digest = hashlib.sha256(
        f"{thread_id}:{turn_index}:{role}:{content}".encode("utf-8")
    ).hexdigest()[:16]
    return f"{thread_id}-{turn_index}-{role}-{digest}"


def _snippet(text: str, max_len: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."
