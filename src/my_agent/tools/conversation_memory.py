from __future__ import annotations

from langchain_core.tools import tool

from my_agent.memory.chroma_store import ChromaConversationStore
from my_agent.messages import snippet as text_snippet


def build_conversation_tools(store: ChromaConversationStore) -> list:
    @tool
    def search_past_conversations(query: str, limit: int = 5) -> str:
        """Semantic search over indexed past conversations.

        Use when the user references prior work or when older thread context may help.
        """
        hits = store.search(query=query, limit=limit)
        if not hits:
            return "No matching past conversations found."

        lines = ["Past conversation matches:"]
        for index, hit in enumerate(hits, start=1):
            lines.append(
                "\n".join(
                    [
                        f"{index}. thread_id={hit.thread_id}",
                        f"   role={hit.role} turn={hit.turn_index} at={hit.timestamp}",
                        f"   snippet: {text_snippet(hit.content, 300) or ''}",
                    ]
                )
            )
        return "\n".join(lines)

    @tool
    def get_conversation(thread_id: str) -> str:
        """Fetch all indexed messages for a conversation thread."""
        hits = store.get_conversation(thread_id)
        if not hits:
            return f"No indexed messages found for thread_id={thread_id}."

        lines = [f"Conversation thread_id={thread_id}:"]
        for hit in hits:
            lines.append(
                "\n".join(
                    [
                        f"- [{hit.timestamp}] {hit.role} (turn {hit.turn_index})",
                        text_snippet(hit.content, 500) or "",
                    ]
                )
            )
        return "\n".join(lines)

    @tool
    def list_recent_conversations(limit: int = 10) -> str:
        """List recent conversation threads with first user message and timestamp."""
        threads = store.list_recent_conversations(limit=limit)
        if not threads:
            return "No indexed conversations yet."

        lines = ["Recent conversations:"]
        for index, thread in enumerate(threads, start=1):
            lines.append(
                "\n".join(
                    [
                        f"{index}. thread_id={thread['thread_id']}",
                        f"   latest={thread['latest_timestamp']}",
                        f"   first_user_message: {thread['first_user_message'] or '(none)'}",
                    ]
                )
            )
        return "\n".join(lines)

    return [search_past_conversations, get_conversation, list_recent_conversations]

