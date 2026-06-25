from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import typer

from my_agent.agent import get_runtime
from my_agent.checkpoint import get_latest_thread_id, list_threads
from my_agent.config import DisplayConfig, load_config
from my_agent.runner import get_thread_state_info, run_turn

app = typer.Typer(
    name="my-agent",
    help="Local macOS deep agent powered by LangChain Deep Agents and OpenRouter.",
    no_args_is_help=True,
)
threads_app = typer.Typer(help="Inspect and manage saved chat threads.")
app.add_typer(threads_app, name="threads")


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


def _resolve_thread_id(
    *,
    thread_id: str | None,
    continue_: bool,
    app_config,
) -> tuple[str, bool]:
    """Return (thread_id, is_resume)."""
    if continue_ and thread_id:
        raise typer.BadParameter("Use either --continue or --thread-id, not both.")

    if continue_:
        latest = get_latest_thread_id(app_config)
        if latest:
            return latest, True
        typer.echo("No saved threads found. Starting a new chat.")
        return str(uuid.uuid4()), False

    if thread_id:
        return thread_id, True

    return str(uuid.uuid4()), False


def _print_chat_banner(agent, thread_id: str, *, is_resume: bool) -> None:
    if not is_resume:
        typer.echo(f"my-agent chat (thread_id={thread_id})")
        return

    info = get_thread_state_info(agent, thread_id)
    if info and info.message_count > 0:
        typer.echo(
            f"Resuming thread {thread_id} ({info.message_count} messages)"
        )
    else:
        typer.echo(f"my-agent chat (thread_id={thread_id})")


def _initial_turn_index(agent, thread_id: str) -> int:
    info = get_thread_state_info(agent, thread_id)
    return info.human_turn_count if info else 0


def _snippet(text: str | None, *, max_len: int = 72) -> str:
    if not text:
        return "(no user message)"
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[: max_len - 1]}…"


@threads_app.command("list")
def threads_list(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to config.toml (default: ./config.toml).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        min=1,
        help="Maximum number of threads to show.",
    ),
) -> None:
    """List saved chat threads (newest first)."""
    config_path = _resolve_config_path(config)
    app_config = load_config(Path(config_path) if config_path else None)
    _, _, agent = get_runtime(config_path)
    threads = list_threads(app_config, agent=agent, limit=limit)

    if not threads:
        typer.echo("No saved threads.")
        raise typer.Exit(0)

    typer.echo(f"Saved threads ({len(threads)}):")
    for index, thread in enumerate(threads, start=1):
        updated = thread.updated_at or "unknown"
        typer.echo(f"{index}. thread_id={thread.thread_id}")
        typer.echo(f"   updated={updated}")
        if thread.message_count:
            typer.echo(f"   messages={thread.message_count}")
        typer.echo(f"   first_user_message: {_snippet(thread.first_user_message)}")


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
    continue_: bool = typer.Option(
        False,
        "--continue",
        help="Resume the most recently updated thread.",
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
    active_thread, is_resume = _resolve_thread_id(
        thread_id=thread_id,
        continue_=continue_,
        app_config=app_config,
    )
    turn_index = _initial_turn_index(agent, active_thread)

    _print_chat_banner(agent, active_thread, is_resume=is_resume)
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
    continue_: bool = typer.Option(
        False,
        "--continue",
        help="Resume the most recently updated thread.",
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
    active_thread, _ = _resolve_thread_id(
        thread_id=thread_id,
        continue_=continue_,
        app_config=app_config,
    )
    turn_index = _initial_turn_index(agent, active_thread) + 1

    reply = run_turn(
        agent,
        app_config,
        chroma_store,
        user_message=task,
        thread_id=active_thread,
        turn_index=turn_index,
        stream=True,
        display=display,
    )
    if reply and not reply.endswith("\n"):
        typer.echo("")


if __name__ == "__main__":
    app()
