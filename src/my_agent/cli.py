from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import typer

from my_agent.config import DisplayConfig
from my_agent.agent import get_runtime
from my_agent.runner import run_turn

app = typer.Typer(
    name="my-agent",
    help="Local macOS deep agent powered by LangChain Deep Agents and OpenRouter.",
    no_args_is_help=True,
)


def _resolve_config_path(config: Optional[Path]) -> str | None:
    return str(config.resolve()) if config else None


def _resolve_display(
    base: DisplayConfig,
    *,
    verbose: bool,
    quiet: bool,
) -> DisplayConfig:
    if verbose and quiet:
        raise typer.BadParameter("Use either --verbose or --quiet, not both.")
    if verbose:
        return DisplayConfig(
            show_reasoning=True,
            show_tool_calls=True,
            show_tool_results=True,
            show_skills=True,
            tool_result_max_chars=base.tool_result_max_chars,
        )
    if quiet:
        return DisplayConfig(
            show_reasoning=False,
            show_tool_calls=False,
            show_tool_results=False,
            show_skills=False,
            tool_result_max_chars=base.tool_result_max_chars,
        )
    return base


@app.command()
def chat(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to config.toml (default: ./config.toml).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    thread_id: Optional[str] = typer.Option(
        None,
        "--thread-id",
        help="Resume an existing LangGraph thread.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show reasoning, tool calls, tool results, and loaded skills.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Hide reasoning, tool calls, tool results, and loaded skills.",
    ),
) -> None:
    """Interactive REPL chat with the agent."""
    config_path = _resolve_config_path(config)
    app_config, chroma_store, agent = get_runtime(config_path)
    display = _resolve_display(app_config.display, verbose=verbose, quiet=quiet)
    active_thread = thread_id or str(uuid.uuid4())
    turn_index = 0

    typer.echo(f"my-agent chat (thread_id={active_thread})")
    typer.echo("Type 'exit' or 'quit' to leave.\n")

    while True:
        try:
            user_input = typer.prompt("You")
        except (EOFError, KeyboardInterrupt):
            typer.echo("\nBye.")
            raise typer.Exit(0) from None

        if user_input.strip().lower() in {"exit", "quit"}:
            typer.echo("Bye.")
            break

        turn_index += 1
        run_turn(
            agent,
            app_config,
            chroma_store,
            user_message=user_input,
            thread_id=active_thread,
            turn_index=turn_index,
            stream=True,
            display=display,
        )


@app.command()
def run(
    task: str = typer.Argument(..., help="One-shot task for the agent."),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to config.toml (default: ./config.toml).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    thread_id: Optional[str] = typer.Option(
        None,
        "--thread-id",
        help="Optional thread id (default: new uuid).",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show reasoning, tool calls, tool results, and loaded skills.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Hide reasoning, tool calls, tool results, and loaded skills.",
    ),
) -> None:
    """Run a single task and exit."""
    config_path = _resolve_config_path(config)
    app_config, chroma_store, agent = get_runtime(config_path)
    display = _resolve_display(app_config.display, verbose=verbose, quiet=quiet)
    active_thread = thread_id or str(uuid.uuid4())

    reply = run_turn(
        agent,
        app_config,
        chroma_store,
        user_message=task,
        thread_id=active_thread,
        turn_index=1,
        stream=True,
        display=display,
    )
    if reply and not reply.endswith("\n"):
        typer.echo("")


if __name__ == "__main__":
    app()
