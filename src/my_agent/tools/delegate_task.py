from __future__ import annotations

import hashlib
import logging
import sys

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool

from my_agent.config import AppConfig
from my_agent.display import TurnStreamPrinter
from my_agent.memory.chroma_store import ChromaConversationStore
from my_agent.messages import extract_messages, latest_assistant_text

logger = logging.getLogger(__name__)


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
                    messages = extract_messages(output)
                    result = latest_assistant_text(messages)
        except Exception as exc:
            logger.exception("Subagent failed for task delegation")
            result = f"[Subagent error: {type(exc).__name__}: {exc}]"

        sys.stdout.write(
            "━" * 28
            + " Subagent finished "
            + "━" * 28
            + "\n"
        )
        sys.stdout.flush()

        return result

    return delegate_task
