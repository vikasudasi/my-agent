from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass
from typing import Any

from langchain_core._api import LangChainBetaWarning
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.types import Command

from my_agent.config import AppConfig, DisplayConfig
from my_agent.display import TurnStreamPrinter
from my_agent.memory.chroma_store import ChromaConversationStore


@dataclass(frozen=True)
class ThreadStateInfo:
    message_count: int
    human_turn_count: int
    first_user_message: str | None

warnings.filterwarnings(
    "ignore",
    category=LangChainBetaWarning,
    message="The v3 streaming protocol on Pregel is experimental.",
)


def run_turn(
    agent,
    config: AppConfig,
    chroma_store: ChromaConversationStore,
    *,
    user_message: str,
    thread_id: str,
    turn_index: int,
    stream: bool = True,
    display: DisplayConfig | None = None,
) -> str:
    graph_config = {"configurable": {"thread_id": thread_id}}
    stream_input: dict[str, Any] | Command = {
        "messages": [HumanMessage(content=user_message)],
    }
    printed_tokens = False
    messages_before = _message_count(agent, graph_config)
    active_display = display or config.display

    while True:
        if stream:
            reply = _stream_until_pause(
                agent,
                stream_input,
                graph_config,
                display=active_display,
                printed_tokens=printed_tokens,
            )
            printed_tokens = True
            if reply.interrupted:
                stream_input = _prompt_and_build_resume(reply.interrupt_value)
                continue

            final_messages = _new_messages(
                _extract_messages(reply.output),
                messages_before,
            )
            if config.memory.index_on_each_turn and final_messages:
                chroma_store.index_messages(
                    thread_id,
                    final_messages,
                    turn_index=turn_index,
                )
            return _latest_assistant_text(_extract_messages(reply.output))

        result = agent.invoke(stream_input, config=graph_config, version="v2")
        if getattr(result, "interrupts", None):
            interrupt_value = result.interrupts[0].value
            stream_input = _prompt_and_build_resume(interrupt_value)
            continue

        state = result.value if hasattr(result, "value") else result
        all_messages = _extract_messages(state)
        final_messages = _new_messages(all_messages, messages_before)
        if config.memory.index_on_each_turn and final_messages:
            chroma_store.index_messages(
                thread_id,
                final_messages,
                turn_index=turn_index,
            )
        return _latest_assistant_text(all_messages)


class _StreamResult:
    def __init__(self, *, interrupted: bool, interrupt_value: Any, output: Any) -> None:
        self.interrupted = interrupted
        self.interrupt_value = interrupt_value
        self.output = output


def _stream_until_pause(
    agent,
    stream_input: dict[str, Any] | Command,
    graph_config: dict[str, Any],
    *,
    display: DisplayConfig,
    printed_tokens: bool,
) -> _StreamResult:
    printer = TurnStreamPrinter(display)
    event_stream = agent.stream_events(stream_input, config=graph_config, version="v3")
    printer.consume_run(event_stream)

    if event_stream.interrupted:
        printer.finish()
        return _StreamResult(
            interrupted=True,
            interrupt_value=event_stream.interrupts[0].value,
            output=None,
        )

    if not printer.wrote_assistant and not printed_tokens:
        sys.stdout.write("\nAssistant: ")
        sys.stdout.flush()

    printer.finish()
    return _StreamResult(
        interrupted=False,
        interrupt_value=None,
        output=event_stream.output,
    )


def _prompt_and_build_resume(interrupt_value: dict[str, Any]) -> Command:
    action_requests = interrupt_value.get("action_requests", [])
    if not action_requests:
        return Command(resume={"decisions": [{"type": "approve"}]})

    decisions: list[dict[str, Any]] = []
    for action in action_requests:
        _print_action_request(action)
        decision = _read_decision(action)
        decisions.append(decision)

    return Command(resume={"decisions": decisions})


def _print_action_request(action: dict[str, Any]) -> None:
    sys.stdout.write("\n--- Approval required ---\n")
    description = action.get("description")
    if description:
        sys.stdout.write(f"{description}\n")
    else:
        sys.stdout.write(f"Tool: {action.get('name')}\n")
        sys.stdout.write(f"Args: {json.dumps(action.get('arguments', {}), indent=2)}\n")


def _read_decision(action: dict[str, Any]) -> dict[str, Any]:
    while True:
        sys.stdout.write("Approve this action? [y/n/e] (yes / no / edit): ")
        sys.stdout.flush()
        choice = sys.stdin.readline().strip().lower()
        if choice in {"y", "yes", "approve", "a"}:
            return {"type": "approve"}
        if choice in {"n", "no", "reject", "r"}:
            return {"type": "reject"}
        if choice in {"e", "edit"}:
            edited = _read_edited_action(action)
            return {"type": "edit", "edited_action": edited}
        sys.stdout.write("Please enter y, n, or e.\n")


def _read_edited_action(action: dict[str, Any]) -> dict[str, Any]:
    edited = dict(action)
    args = dict(action.get("arguments", {}))
    sys.stdout.write("Enter edited arguments as JSON (or press Enter to keep current): ")
    sys.stdout.flush()
    raw = sys.stdin.readline().strip()
    if raw:
        args.update(json.loads(raw))
    edited["arguments"] = args
    return edited


def _extract_messages(state: Any) -> list[BaseMessage]:
    if isinstance(state, dict):
        messages = state.get("messages", [])
    else:
        messages = getattr(state, "messages", [])
    return [message for message in messages if isinstance(message, BaseMessage)]


def get_thread_state_info(agent, thread_id: str) -> ThreadStateInfo | None:
    graph_config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = agent.get_state(graph_config)
        if not snapshot or not snapshot.values:
            return None
        messages = _extract_messages(snapshot.values)
    except Exception:
        return None

    first_user: str | None = None
    human_turn_count = 0
    for message in messages:
        if not isinstance(message, HumanMessage):
            continue
        human_turn_count += 1
        if first_user is None:
            first_user = _message_text(message)

    return ThreadStateInfo(
        message_count=len(messages),
        human_turn_count=human_turn_count,
        first_user_message=first_user,
    )


def _message_count(agent, graph_config: dict[str, Any]) -> int:
    info = get_thread_state_info(agent, graph_config["configurable"]["thread_id"])
    return info.message_count if info else 0


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def _new_messages(
    messages: list[BaseMessage],
    previous_count: int,
) -> list[BaseMessage]:
    if previous_count <= 0:
        return messages
    return messages[previous_count:]


def _latest_assistant_text(messages: list[BaseMessage]) -> str:
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
