from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openrouter import ChatOpenRouter
from langgraph.graph.message import RemoveMessage

from my_agent.config import SummarizationConfig

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = """\
You are a conversation summarizer for an AI assistant. Summarize the key points from \
the following conversation exchange between a user and an assistant. Focus on:

- What the user asked or requested
- What decisions or conclusions were reached
- Any important context, preferences, or constraints established
- Files that were read or modified, and why
- Do NOT include tool call details, error messages, or implementation specifics \
unless they are essential context

Conversation:
{conversation_text}

Write a concise, paragraph-style summary covering only what matters for continuing \
the conversation. Keep it under 200 words.
"""


class SummarizationMiddleware(AgentMiddleware):
    """Summarizes older conversation turns once the message count exceeds a threshold.

    Runs in ``after_agent`` (once per agent invocation). When the number of
    non-system messages exceeds ``max_messages``, the oldest messages are
    summarized into a single ``SystemMessage`` and removed from state via
    ``RemoveMessage``, keeping only the last ``keep_last`` messages intact.
    """

    def __init__(
        self,
        config: SummarizationConfig,
        model: str,
        *,
        api_key: str | None = None,
    ) -> None:
        self._config = config
        self._llm: ChatOpenRouter | None = None
        if config.enabled and (config.model or model):
            llm_model = config.model or model
            self._llm = ChatOpenRouter(
                model=llm_model,
                temperature=config.temperature,
                api_key=api_key,
            )

    def after_agent(
        self,
        state: dict[str, Any],
        runtime: Any,  # Runtime[ContextT]
    ) -> dict[str, Any] | None:
        if not self._config.enabled or self._llm is None:
            return None

        messages: list[BaseMessage] = state.get("messages", [])
        # Filter out system messages (system prompt, existing summaries)
        non_system = [m for m in messages if not isinstance(m, SystemMessage)]

        if len(non_system) <= self._config.max_messages:
            return None

        # Messages to summarize: all non-system messages except the last keep_last
        to_summarize = non_system[: -self._config.keep_last]

        # Build removal list (remove by id from the *full* messages list)
        remove_ids = {msg.id for msg in to_summarize if msg.id}
        if not remove_ids:
            return None

        # Summarize
        summary_text = self._summarize(to_summarize)

        # Produce state updates: RemoveMessages for old messages + a summary SystemMessage
        summary_msg = SystemMessage(
            content=f"[Summary of earlier conversation]\n{summary_text}",
        )
        updates: list[BaseMessage] = [RemoveMessage(id=mid) for mid in remove_ids]
        updates.append(summary_msg)

        return {"messages": updates}

    async def aafter_agent(
        self,
        state: dict[str, Any],
        runtime: Any,
    ) -> dict[str, Any] | None:
        """Async version — delegates to the sync implementation."""
        return self.after_agent(state, runtime)

    def _summarize(self, messages: list[BaseMessage]) -> str:
        """Call the LLM to produce a summary of the given messages."""
        assert self._llm is not None

        lines: list[str] = []
        for msg in messages:
            role = self._format_role(msg)
            content = msg.content
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        parts.append(str(block.get("text", "")))
                content = "\n".join(parts)
            lines.append(f"[{role}]\n{content}")

        conversation_text = "\n\n".join(lines)

        prompt = _SUMMARY_PROMPT.format(conversation_text=conversation_text)
        try:
            response = self._llm.invoke(
                [HumanMessage(content=prompt)],
            )
            summary = response.content.strip() if response.content else ""
            return summary if summary else "(empty summary)"
        except Exception as exc:
            logger.warning("Summarization LLM call failed: %s", exc)
            return "(summary unavailable)"

    @staticmethod
    def _format_role(msg: BaseMessage) -> str:
        if isinstance(msg, HumanMessage):
            return "User"
        if isinstance(msg, AIMessage):
            return "Assistant"
        return msg.type.capitalize()


# Convenience: check if summarization is possible at import time
def _check_openrouter_import() -> None:
    try:
        from langchain_openrouter import ChatOpenRouter  # noqa: F401
    except ImportError:
        logger.warning(
            "langchain-openrouter not installed; summarization middleware "
            "will be disabled."
        )


_check_openrouter_import()