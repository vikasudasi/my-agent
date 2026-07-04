from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.messages import HumanMessage, ToolMessage

from my_agent.memory.chroma_store import (
    ChromaConversationStore,
    _ensure_unique_ids,
    _message_id,
    delete_conversation_index,
)


class TestChromaDeleteThread:
    def test_delete_thread_removes_matching_documents(self) -> None:
        store = MagicMock()
        collection = MagicMock()
        store._vector_store._collection = collection
        collection.get.return_value = {"ids": ["a", "b"]}

        deleted = ChromaConversationStore.delete_thread(store, "thread-1")

        collection.get.assert_called_once_with(where={"thread_id": "thread-1"})
        collection.delete.assert_called_once_with(ids=["a", "b"])
        assert deleted == 2

    def test_delete_thread_noop_when_missing(self) -> None:
        store = MagicMock()
        collection = MagicMock()
        store._vector_store._collection = collection
        collection.get.return_value = {"ids": []}

        deleted = ChromaConversationStore.delete_thread(store, "missing")

        collection.delete.assert_not_called()
        assert deleted == 0

    def test_delete_conversation_index_uses_store(self) -> None:
        config = MagicMock()
        with patch(
            "my_agent.memory.chroma_store.ChromaConversationStore"
        ) as mock_cls:
            mock_cls.return_value.delete_thread.return_value = 3
            removed = delete_conversation_index(config, "thread-9")

        mock_cls.assert_called_once_with(config)
        mock_cls.return_value.delete_thread.assert_called_once_with("thread-9")
        assert removed == 3


class TestMessageIds:
    def test_duplicate_tool_content_gets_distinct_ids(self) -> None:
        content = "Queued for voice output."
        first = _message_id(
            "thread-1",
            1,
            "tool",
            content,
            disambiguator="call-a",
        )
        second = _message_id(
            "thread-1",
            1,
            "tool",
            content,
            disambiguator="call-b",
        )
        assert first != second

    def test_ensure_unique_ids_adds_suffix_for_collisions(self) -> None:
        assert _ensure_unique_ids(["same", "same", "other"]) == [
            "same",
            "same-dup2",
            "other",
        ]


class TestIndexMessages:
    def test_indexes_multiple_identical_tool_results(self, mock_config) -> None:
        vector_store = MagicMock()
        with patch(
            "my_agent.memory.chroma_store.Chroma",
            return_value=vector_store,
        ):
            with patch(
                "my_agent.memory.chroma_store.HuggingFaceEmbeddings",
                return_value=MagicMock(),
            ):
                store = ChromaConversationStore(mock_config)

        messages = [
            HumanMessage(content="Say hello twice"),
            ToolMessage(content="Queued for voice output.", tool_call_id="call-1"),
            ToolMessage(content="Queued for voice output.", tool_call_id="call-2"),
            HumanMessage(content="Thanks"),
        ]
        indexed = store.index_messages("thread-1", messages, turn_index=1)

        assert indexed > 0
        vector_store.add_documents.assert_called_once()
        ids = vector_store.add_documents.call_args.kwargs["ids"]
        assert len(ids) == len(set(ids))
