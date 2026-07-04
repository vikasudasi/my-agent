from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from my_agent.agent import get_runtime
from my_agent.checkpoint import (
    delete_thread,
    get_latest_thread_id,
    list_threads,
    prune_threads,
)
from my_agent.config import DisplayConfig, load_config
from my_agent.help_text import render_help
from my_agent.messages import snippet as text_snippet
from my_agent.runner import get_thread_state_info, run_turn
from my_agent.store import list_memories, read_memory

app = typer.Typer(
    name="my-agent",
    help="Local macOS deep agent powered by LangChain Deep Agents and OpenRouter.",
    no_args_is_help=True,
)
threads_app = typer.Typer(help="Inspect and manage saved chat threads.")
memories_app = typer.Typer(help="Inspect agent memory files under /memories/.")
app.add_typer(threads_app, name="threads")
app.add_typer(memories_app, name="memories")

_console = Console()


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
        _console.print("[yellow]No saved threads found. Starting a new chat.[/yellow]")
        return str(uuid.uuid4()), False

    if thread_id:
        return thread_id, True

    return str(uuid.uuid4()), False


def _print_chat_banner(agent, thread_id: str, *, is_resume: bool) -> None:
    if is_resume:
        info = get_thread_state_info(agent, thread_id)
        msg_count = f" ({info.message_count} messages)" if info and info.message_count else ""
        _console.print(
            Panel(
                f"[bold]Resuming thread[/bold] {thread_id}{msg_count}\n"
                "[italic]Type 'exit' or 'quit' to leave[/italic]",
                title="[bold cyan]my-agent[/bold cyan]",
                border_style="bright_blue",
                padding=(1, 2),
            )
        )
    else:
        _console.print(
            Panel(
                f"[dim]thread_id={thread_id}[/dim]\n"
                "[italic]Type 'exit' or 'quit' to leave[/italic]",
                title="[bold cyan]my-agent[/bold cyan]  [dim]new session[/dim]",
                border_style="bright_blue",
                padding=(1, 2),
            )
        )


def _initial_turn_index(agent, thread_id: str) -> int:
    info = get_thread_state_info(agent, thread_id)
    return info.human_turn_count if info else 0


def _snippet(text: str | None, *, max_len: int = 72) -> str:
    return text_snippet(text, max_len, empty="(no user message)") or "(no user message)"


@app.command("help")
def help_cmd(
    topic: Optional[list[str]] = typer.Argument(
        None,
        help="Topic: chat, run, threads, threads list, memories, etc.",
    ),
) -> None:
    """Show command reference (all documented CLI commands)."""
    joined = " ".join(topic).strip() if topic else None
    typer.echo(render_help(joined or None))


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
        _console.print("[yellow]No saved threads.[/yellow]")
        raise typer.Exit(0)

    _console.print(f"[bold]Saved threads[/bold] ([cyan]{len(threads)}[/cyan]):")
    for index, thread in enumerate(threads, start=1):
        updated = thread.updated_at or "unknown"
        _console.print(f"  [cyan]{index}.[/cyan] [bold]thread_id[/bold]={thread.thread_id}")
        _console.print(f"       updated={updated}")
        if thread.message_count:
            _console.print(f"       messages={thread.message_count}")
        _console.print(f"       first_user_message: [dim]{_snippet(thread.first_user_message)}[/dim]")


@threads_app.command("delete")
def threads_delete(
    thread_id: str = typer.Argument(..., help="Thread id to delete."),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to config.toml (default: ./config.toml).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
) -> None:
    """Delete a saved chat thread and its checkpoint history."""
    config_path = _resolve_config_path(config)
    app_config = load_config(Path(config_path) if config_path else None)

    if not yes:
        typer.confirm(
            f"Delete thread {thread_id} and all its checkpoint data?",
            abort=True,
        )

    delete_thread(app_config, thread_id)
    _console.print(f"[green]Deleted[/green] thread {thread_id}.")


@threads_app.command("prune")
def threads_prune(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to config.toml (default: ./config.toml).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    keep: Optional[int] = typer.Option(
        None,
        "--keep",
        min=0,
        help="Keep this many newest threads (0 = no count limit). Default: config [checkpoint].max_threads.",
    ),
    max_age_days: Optional[int] = typer.Option(
        None,
        "--max-age-days",
        min=0,
        help="Delete threads older than N days (0 = disabled). Default: config [checkpoint].max_thread_age_days.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show threads that would be deleted without deleting.",
    ),
    no_protect_latest: bool = typer.Option(
        False,
        "--no-protect-latest",
        help="Allow deleting the most recently updated thread.",
    ),
    no_vacuum: bool = typer.Option(
        False,
        "--no-vacuum",
        help="Skip SQLite VACUUM after deleting threads.",
    ),
) -> None:
    """Delete old chat threads by count and/or age limits."""
    config_path = _resolve_config_path(config)
    app_config = load_config(Path(config_path) if config_path else None)

    keep_limit = app_config.checkpoint.max_threads if keep is None else keep
    age_limit = (
        app_config.checkpoint.max_thread_age_days
        if max_age_days is None
        else max_age_days
    )

    if keep_limit <= 0 and age_limit <= 0:
        _console.print(
            "[yellow]No retention limits configured[/yellow]. Set [checkpoint].max_threads "
            "or max_thread_age_days in config.toml, or pass --keep / --max-age-days."
        )
        raise typer.Exit(1)

    result = prune_threads(
        app_config,
        keep=keep,
        max_age_days=max_age_days,
        protect_latest=not no_protect_latest,
        dry_run=dry_run,
        vacuum=not no_vacuum,
    )

    if not result.deleted:
        _console.print("[yellow]No threads to prune.[/yellow]")
        raise typer.Exit(0)

    action = "Would delete" if result.dry_run else "Deleted"
    _console.print(f"[bold]{action}[/bold] [cyan]{len(result.deleted)}[/cyan] thread(s):")
    for thread_id in result.deleted:
        _console.print(f"  [red]-[/red] {thread_id}")

    if result.dry_run:
        _console.print("\n[dim]Re-run without --dry-run to apply.[/dim]")
    elif result.vacuumed:
        _console.print("[green]Ran SQLite VACUUM[/green] on checkpoints database.")


@memories_app.command("list")
def memories_list(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to config.toml (default: ./config.toml).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        min=1,
        help="Maximum number of memory files to show.",
    ),
) -> None:
    """List persisted files under /memories/ (newest first)."""
    config_path = _resolve_config_path(config)
    app_config = load_config(Path(config_path) if config_path else None)
    files = list_memories(app_config, limit=limit)

    if not files:
        _console.print("[yellow]No memory files saved yet.[/yellow]")
        _console.print("The agent can write durable notes to paths like [cyan]/memories/user.md[/cyan].")
        raise typer.Exit(0)

    _console.print(f"[bold]Memory files[/bold] ([cyan]{len(files)}[/cyan]):")
    for index, entry in enumerate(files, start=1):
        updated = entry.updated_at or "unknown"
        _console.print(f"  [cyan]{index}.[/cyan] [bold]{entry.path}[/bold]")
        _console.print(f"       updated={updated}  size={entry.size} bytes")
        if entry.snippet:
            _console.print(f"       snippet: [dim]{entry.snippet}[/dim]")


@memories_app.command("read")
def memories_read(
    path: str = typer.Argument(
        ...,
        help="Virtual memory path (e.g. /memories/user.md).",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Path to config.toml (default: ./config.toml).",
        exists=True,
        dir_okay=False,
        resolve_path=True,
    ),
) -> None:
    """Print the contents of a /memories/ file."""
    config_path = _resolve_config_path(config)
    app_config = load_config(Path(config_path) if config_path else None)
    try:
        content = read_memory(app_config, path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if content is None:
        _console.print(f"[yellow]No memory file at[/yellow] {path!r}.")
        raise typer.Exit(1)

    _console.print(content)


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

    while True:
        try:
            user_input = _console.input("[bold yellow]You:[/bold yellow] ")
        except (EOFError, KeyboardInterrupt):
            _console.print("\n[dim]Bye.[/dim]")
            raise typer.Exit(0) from None

        if user_input.strip().lower() in {"exit", "quit"}:
            _console.print("[dim]Bye.[/dim]")
            break

        turn_index += 1
        try:
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
        except KeyboardInterrupt:
            # Ctrl+C mid-turn: let user redirect the agent
            _console.print()
            _console.print("[yellow]Interrupted. Type your correction or press Enter to discard:[/yellow]")
            try:
                correction = _console.input("[bold yellow]Redirect:[/bold yellow] ")
            except (EOFError, KeyboardInterrupt):
                _console.print("\n[dim]Discarded.[/dim]")
                _console.print()
                _console.print(Rule(style="bright_black"))
                _console.print()
                continue
            if correction.strip():
                turn_index += 1
                run_turn(
                    agent,
                    app_config,
                    chroma_store,
                    user_message=correction,
                    thread_id=active_thread,
                    turn_index=turn_index,
                    stream=True,
                    display=display,
                )
            _console.print()
            _console.print(Rule(style="bright_black"))
            _console.print()
            continue

        _console.print()
        _console.print(Rule(style="bright_black"))
        _console.print()


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
        _console.print("")


if __name__ == "__main__":
    app()
