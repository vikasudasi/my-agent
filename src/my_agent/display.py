from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from rich.console import Console
from rich.rule import Rule
from rich.style import Style

from my_agent.config import DisplayConfig
from my_agent.voice.extract import VoiceTagStreamFilter


# ── Color & style palette ─────────────────────────────────────────────────

SKILLS_STYLE = Style(color="green", dim=True)
REASONING_STYLE = Style(color="bright_black", italic=True)
TOOL_NAME_STYLE = Style(color="cyan", bold=False)
TOOL_RESULT_STYLE = Style(color="green")
TOOL_ERROR_STYLE = Style(color="red")
ASSISTANT_LABEL = "[bold cyan]Assistant:[/bold cyan]"


class TurnStreamPrinter:
    """Render agent turn progress to the terminal during v3 streaming."""

    def __init__(
        self,
        config: DisplayConfig,
        *,
        output: TextIO | None = None,
        voice_filter: VoiceTagStreamFilter | None = None,
    ) -> None:
        self._config = config
        self._console = Console(file=output or sys.stdout, highlight=False)
        self._voice_filter = voice_filter
        self._assistant_header_printed = False
        self._printed_skills: set[str] = set()
        self._pending_tools: list[Any] = []
        self._announced_tool_calls: set[str] = set()

    def consume_run(self, run: Any) -> None:
        """Drive a `stream_events(version='v3')` run and print live progress."""
        for name, item in run.interleave("messages", "tool_calls", "values"):
            if name == "values":
                self._handle_values(item)
            elif name == "messages":
                self._handle_message_stream(item)
            elif name == "tool_calls":
                self._handle_tool_stream(item)
            self._flush_completed_tools()

    def finish(self) -> None:
        """Print any trailing tool results and ensure a newline after assistant text."""
        self._flush_completed_tools(force=True)
        if self._voice_filter is not None:
            trailing = self._voice_filter.flush()
            if trailing:
                if not self._assistant_header_printed:
                    self._raw_print(ASSISTANT_LABEL, end=" ")
                    self._assistant_header_printed = True
                self._write(trailing)
        if self._assistant_header_printed:
            self._write("\n")

    @property
    def wrote_assistant(self) -> bool:
        return self._assistant_header_printed

    def _handle_values(self, state: Any) -> None:
        if not self._config.show_skills or not isinstance(state, dict):
            return

        skills = state.get("skills_metadata") or []
        new_names = [
            skill["name"]
            for skill in skills
            if isinstance(skill, dict)
            and skill.get("name")
            and skill["name"] not in self._printed_skills
        ]
        if not new_names:
            return

        self._printed_skills.update(new_names)
        joined = ", ".join(new_names)
        self._console.print(f"[bold]Skills loaded[/bold]: {joined}", style=SKILLS_STYLE)

    def _handle_message_stream(self, stream: Any) -> None:
        had_reasoning = False
        if self._config.show_reasoning:
            for token in stream.reasoning:
                if not token:
                    continue
                if not had_reasoning:
                    self._console.print("Thought process: ", style=REASONING_STYLE, end="")
                    had_reasoning = True
                self._write(token)
            if had_reasoning:
                self._write("\n")
                self._console.print(Rule(style="bright_black"))
                self._console.print()

        if self._config.show_tool_calls:
            for tool_call in stream.tool_calls.get():
                self._announce_tool_call(tool_call)

        for token in stream.text:
            if not token:
                continue
            if self._voice_filter is not None:
                token = self._voice_filter.feed(token)
                if not token:
                    continue
            if not self._assistant_header_printed:
                self._raw_print(ASSISTANT_LABEL, end=" ")
                self._assistant_header_printed = True
            self._write(token)

    def _handle_tool_stream(self, stream: Any) -> None:
        if not self._config.show_tool_calls:
            return

        call_id = getattr(stream, "tool_call_id", "")
        if call_id and call_id not in self._announced_tool_calls:
            self._announce_tool_call(
                {
                    "name": getattr(stream, "tool_name", "tool"),
                    "args": getattr(stream, "input", None) or {},
                }
            )
            if call_id:
                self._announced_tool_calls.add(call_id)

        if stream not in self._pending_tools:
            self._pending_tools.append(stream)

    def _announce_tool_call(self, tool_call: dict[str, Any]) -> None:
        name = str(tool_call.get("name") or "tool")
        call_id = str(tool_call.get("id") or "")
        if call_id and call_id in self._announced_tool_calls:
            return
        if call_id:
            self._announced_tool_calls.add(call_id)

        args = tool_call.get("args")
        if args is None:
            args = tool_call.get("arguments", {})
        rendered_args = _format_tool_args(args)
        skill_hint = _skill_hint(name, args)
        line = f"[cyan]{name}[/cyan]"
        if rendered_args:
            line += f"({rendered_args})"
        if skill_hint:
            line += f"  [dim]{skill_hint}[/dim]"
        self._console.print(f"Tool: {line}")

    def _flush_completed_tools(self, *, force: bool = False) -> None:
        if not self._config.show_tool_results:
            self._pending_tools.clear()
            return

        still_pending: list[Any] = []
        for stream in self._pending_tools:
            if not getattr(stream, "completed", False) and not force:
                still_pending.append(stream)
                continue

            name = getattr(stream, "tool_name", "tool")
            error = getattr(stream, "error", None)
            if error:
                self._console.print(
                    f"Tool error: {name}: {error}", style=TOOL_ERROR_STYLE
                )
                continue

            output = getattr(stream, "output", None)
            if output is None:
                if not force:
                    still_pending.append(stream)
                continue

            rendered = _truncate(
                _format_tool_output(output), self._config.tool_result_max_chars
            )
            self._console.print(
                f"Tool result: [green]{name}[/green]: {rendered}",
                style=TOOL_RESULT_STYLE,
            )

        self._pending_tools = still_pending

    def _write(self, text: str) -> None:
        """Write raw text to the output stream (used for streaming tokens)."""
        self._console.file.write(text)
        self._console.file.flush()

    def _raw_print(self, *args: Any, **kwargs: Any) -> None:
        """Print rich text through console (used for labels)."""
        self._console.print(*args, **kwargs)


def _format_tool_args(args: Any) -> str:
    if not args:
        return ""
    if isinstance(args, str):
        return _truncate(args, 200)
    try:
        return _truncate(json.dumps(args, ensure_ascii=False), 200)
    except TypeError:
        return _truncate(str(args), 200)


def _format_tool_output(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, (dict, list)):
        try:
            return json.dumps(output, ensure_ascii=False)
        except TypeError:
            pass
    content = getattr(output, "content", None)
    if isinstance(content, str):
        return content
    return str(output)


def _skill_hint(tool_name: str, args: Any) -> str:
    if tool_name not in {"read_file", "grep", "glob"}:
        return ""
    path = _extract_path_arg(args)
    if path and "SKILL.md" in path.replace("\\", "/"):
        return f"(reading skill: {path})"
    return ""


def _extract_path_arg(args: Any) -> str:
    if isinstance(args, dict):
        for key in ("file_path", "path", "filepath"):
            value = args.get(key)
            if isinstance(value, str):
                return value
    return ""


def _truncate(text: str, max_len: int) -> str:
    cleaned = " ".join(text.split()) if "\n" not in text else text.strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."