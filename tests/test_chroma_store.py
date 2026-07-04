from __future__ import annotations

from unittest.mock import MagicMock, patch

from my_agent.memory.chroma_store import ChromaConversationStore, delete_conversation_index


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
