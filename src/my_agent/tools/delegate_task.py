from __future__ import annotations

import hashlib
import sys

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool

from my_agent.config import AppConfig
from my_agent.display import TurnStreamPrinter
from my_agent.memory.chroma_store import ChromaConversationStore


def build_delegate_task_tool(
    config: AppConfig,
    chroma_store: ChromaConversationStore,
):
    """Create a tool that delegates tasks to a subagent with visible streaming progress.

    Unlike the built-in `task` tool which hides subagent internals, this tool
    streams the subagent's reasoning, tool calls, and results to the terminal
    in real time.

    Args:
        config: Application configuration.
        chroma_store: Chroma conversation store for memory.

    Returns:
        A LangChain tool for delegating tasks with streaming progress.
    """

    @tool
    def delegate_task(description: str) -> str:
        """Delegate a complex multi-step task to a subagent with visible streaming progress.

        The subagent's reasoning, tool calls, and intermediate results are shown
        in the terminal in real time. Use this instead of the built-in `task` tool
        when you want the user to see the subagent's progress.

        Args:
            description: A detailed description of the task for the subagent to
                perform autonomously. Include all necessary context and specify
                the expected output format.

        Returns:
            The subagent's final response text.
        """
        # Lazy import to avoid circular dependency (agent.py imports this module)
        from my_agent.agent import _create_agent  # noqa: PLC0415

        subagent = _create_agent(config, chroma_store)

        thread_id = f"delegate-{hashlib.md5(description.encode()).hexdigest()[:12]}"
        graph_config = {"configurable": {"thread_id": thread_id}}

        # Print a visual separator so the user can see where subagent output begins
        sys.stdout.write(
            "\n"
            + "━" * 28
            + " Subagent started "
            + "━" * 28
            + "\n"
        )
        sys.stdout.flush()

        try:
            printer = TurnStreamPrinter(config.display)
            event_stream = subagent.stream_events(
                {"messages": [HumanMessage(content=description)]},
                config=graph_config,
                version="v3",
            )
            printer.consume_run(event_stream)
            printer.finish()

            if getattr(event_stream, "interrupted", False):
                result = "[Subagent interrupted — requires approval]"
            else:
                output = getattr(event_stream, "output", None)
                if output is None:
                    result = "[Subagent produced no output]"
                else:
                    messages = _extract_messages(output)
                    result = _latest_assistant_text(messages)
        except Exception:
            import traceback

            result = f"[Subagent error: {traceback.format_exc()}]"

        sys.stdout.write(
            "━" * 28
            + " Subagent finished "
            + "━" * 28
            + "\n"
        )
        sys.stdout.flush()

        return result

    return delegate_task


def _extract_messages(state: object) -> list[BaseMessage]:
    """Extract BaseMessage list from an agent state object."""
    if isinstance(state, dict):
        messages = state.get("messages", [])
    else:
        messages = getattr(state, "messages", [])
    return [m for m in messages if isinstance(m, BaseMessage)]


def _latest_assistant_text(messages: list[BaseMessage]) -> str:
    """Get the content of the most recent AI message."""
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        parts.append(str(block.get("text", "")))
                return "\n".join(part for part in parts if part)
    return ""