# my-agent

A local macOS personal assistant built on [LangChain Deep Agents](https://github.com/langchain-ai/deepagents). It runs shell commands, reads and writes files, searches the web, and remembers conversations across sessions.

## Features

- **Interactive chat** — REPL-style terminal chat with streaming output
- **One-shot tasks** — run a single prompt and exit
- **Persistent threads** — chat history survives restarts via SQLite checkpoints
- **Semantic memory** — ChromaDB indexes conversations for cross-thread search
- **Agent skills** — markdown workflows the agent loads on demand (`skills/`)
- **Web search** — Tavily integration for live information (optional)
- **Human-in-the-loop** — optional approval before shell commands and file writes
- **Verbose mode** — show reasoning, tool calls, tool results, and loaded skills
- **Portable by design** — run from any directory; global defaults + local overrides

## Requirements

- macOS (designed for local shell and filesystem access)
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) or pip
- [OpenRouter](https://openrouter.ai/) API key
- Tavily API key (optional, for web search)

## Quick start

```bash
git clone git@github.com:vikasudasi/my-agent.git
cd my-agent

# Create virtual environment and install
uv venv
uv pip install -e .

# Configure
cp config.toml.example config.toml
cp .env.example .env
# Edit .env with your OPENROUTER_API_KEY (and TAVILY_API_KEY if desired)

# Start chatting
my-agent chat
```

## Global installation

Install once, use from anywhere:

```bash
# Activate the venv (adjust path as needed)
# and add the agent to your PATH
echo 'export PATH="$HOME/my-agent/.venv/bin:$PATH"' >> ~/.zshrc

# Or symlink as a script entry point:
# uv pip install -e .   (already done above creates the my-agent entrypoint)
```

Once installed globally, `my-agent` resolves files in this order:

| Resource | Resolution | Detail |
|----------|------------|--------|
| **`config.toml`** | `--config` CLI > `./config.toml` > `~/.my-agent/config.toml` | First-found wins. |
| **`.env`** | `~/.my-agent/.env` then `./.env` (cwd overrides home) | Both loaded; cwd values override. |
| **`AGENTS.md` (memory)** | `~/.my-agent/AGENTS.md` **and** `./AGENTS.md` | Both injected into system prompt when they exist. |
| **User skills** | `~/.my-agent/skills/{name}/SKILL.md` | Always loaded. |
| **Project skills** | `./skills/{name}/SKILL.md` | Loaded when the directory exists. |
| **Checkpoints** | `~/.my-agent/checkpoints.sqlite` (or `[checkpoint].sqlite_path`) | Always under `agent_state_dir` (`~/.my-agent/` by default). |
| **`/memories/` store** | `~/.my-agent/store.sqlite` (or `[store].sqlite_path`) | Always under `agent_state_dir`. |
| **Chroma DB** | `~/.my-agent/chroma/` (or `[paths].chroma_dir`) | Always under `agent_state_dir`. |

This means you can run `my-agent chat` from any project directory and it will automatically pick up project-local config while sharing the same global checkpoints, memories, and skills across all your projects.

## Configuration

Copy `config.toml.example` to any of these locations:

```bash
# Personal defaults (used from any directory)
cp config.toml.example ~/.my-agent/config.toml

# Or project-specific (overrides personal defaults when in this directory)
cp config.toml.example /path/to/project/config.toml
```

Secrets go in `.env` — loaded from `~/.my-agent/.env` then overridden by `./.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENROUTER_API_KEY` | Yes | API key for the LLM via OpenRouter |
| `TAVILY_API_KEY` | No | Enables live web search |

Key `config.toml` sections:

| Section | Purpose |
|---------|---------|
| `[llm]` | Model slug (e.g. `anthropic/claude-sonnet-4-6`) and temperature |
| `[agent]` | Home directory root (`~`) and optional system prompt override |
| `[security]` | `require_approval` — prompt before destructive shell/file actions |
| `[checkpoint]` | Thread persistence (`sqlite` or `memory`), retention limits |
| `[store]` | `/memories/` persistence (`sqlite` or `memory`) |
| `[memory]` | Chroma collection and embedding model |
| `[tavily]` | Web search defaults |
| `[display]` | Streaming verbosity defaults |

Persistent data lives under `~/.my-agent/` by default (checkpoints, Chroma, memories store, user skills), making it safe to run from any directory.

## CLI reference

```
my-agent
├── chat                         Interactive REPL
├── run <task>                   One-shot task
├── help [topic]                 Command reference (this document in the terminal)
├── threads
│   ├── list          List saved chat threads
│   ├── prune         Delete old threads by retention limits
│   └── delete <id>   Delete one thread
└── memories
    ├── list          List /memories/ files
    └── read <path>   Print a /memories/ file
```

Global options are available on every command:

| Option | Description |
|--------|-------------|
| `--config FILE` | Path to `config.toml` (default: `./config.toml`, fallback `~/.my-agent/config.toml`) |
| `--help` | Show Typer help for one command |
| `my-agent help [topic]` | Full command reference (e.g. `help chat`, `help threads prune`) |

### `my-agent help`

Print documented command reference in the terminal. Without a topic, shows the full overview.

| Argument | Description |
|----------|-------------|
| `TOPIC` | Optional: `chat`, `run`, `threads`, `threads list`, `threads prune`, `threads delete`, `memories`, `memories list`, `memories read` |

```bash
my-agent help
my-agent help chat
my-agent help threads prune
my-agent help memories
```

### `my-agent chat`

Interactive REPL. Each session gets a `thread_id` printed at startup. Type `exit` or `quit` to leave.

| Option | Description |
|--------|-------------|
| `--thread-id TEXT` | Resume a specific saved thread |
| `--continue` | Resume the most recently updated thread |
| `--verbose` | Show reasoning, tool calls, tool results, and loaded skills |
| `--quiet` | Hide reasoning, tool calls, tool results, and loaded skills |

`--continue` and `--thread-id` cannot be used together. When resuming a thread with history, the banner shows message count (e.g. `Resuming thread <uuid> (12 messages)`).

```bash
my-agent chat
my-agent chat --continue
my-agent chat --thread-id 0353da51-f909-4144-b95a-52db1ea8986f
my-agent chat --verbose
my-agent chat --quiet
my-agent chat --config /path/to/config.toml
```

### `my-agent run`

Run a single task and exit. Useful for scripts and one-off prompts.

| Option | Description |
|--------|-------------|
| `--thread-id TEXT` | Attach to an existing thread (default: new UUID) |
| `--continue` | Use the most recently updated thread |
| `--verbose` | Show reasoning, tool calls, tool results, and loaded skills |
| `--quiet` | Hide reasoning, tool calls, tool results, and loaded skills |

```bash
my-agent run "List the five largest files in my Downloads folder"
my-agent run --continue "Now sort them by date"
my-agent run --verbose "What were the biggest AI news stories this week?"
```

### `my-agent threads list`

List chat threads saved in the checkpoint database (newest first). Shows `thread_id`, last updated time, message count, and first user message snippet.

| Option | Default | Description |
|--------|---------|-------------|
| `--limit N` | `20` | Maximum threads to show |

```bash
my-agent threads list
my-agent threads list --limit 10
```

Use the `thread_id` from this output with `my-agent chat --thread-id <id>` to resume a conversation.

### `my-agent threads prune`

Delete old threads using count and/or age limits from config (or CLI overrides). The most recently updated thread is protected by default (the one `chat --continue` would use).

| Option | Default | Description |
|--------|---------|-------------|
| `--keep N` | `[checkpoint].max_threads` | Keep N newest threads (`0` = no count limit) |
| `--max-age-days N` | `[checkpoint].max_thread_age_days` | Delete threads older than N days (`0` = disabled) |
| `--dry-run` | off | Preview deletions without applying |
| `--no-protect-latest` | off | Allow deleting the newest thread |
| `--no-vacuum` | off | Skip SQLite VACUUM after prune |

Config (`config.toml`):

```toml
[checkpoint]
max_threads = 50          # 0 = unlimited
max_thread_age_days = 0   # 0 = disabled; e.g. 90 to drop stale threads
```

```bash
my-agent threads prune --dry-run
my-agent threads prune
my-agent threads prune --keep 20
my-agent threads prune --max-age-days 90
```

### `my-agent threads delete`

Delete a single thread and all its checkpoint data.

| Option | Description |
|--------|-------------|
| `THREAD_ID` | Thread to delete (from `threads list`) |
| `--yes` / `-y` | Skip confirmation |

```bash
my-agent threads delete 0353da51-f909-4144-b95a-52db1ea8986f
my-agent threads delete 0353da51-f909-4144-b95a-52db1ea8986f --yes
```

### `my-agent memories list`

List files the agent has written under `/memories/` (persisted in `store.sqlite`). Shows path, updated time, size, and a content snippet.

| Option | Default | Description |
|--------|---------|-------------|
| `--limit N` | `50` | Maximum files to show |

```bash
my-agent memories list
my-agent memories list --limit 20
```

### `my-agent memories read`

Print the full contents of a `/memories/` file.

| Argument | Description |
|----------|-------------|
| `PATH` | Virtual path, e.g. `/memories/user.md` |

```bash
my-agent memories read /memories/user.md
my-agent memories read /memories/preferences.md
```

### Common workflows

```bash
# Start fresh, note the thread_id printed at startup
my-agent chat

# Pick up where you left off
my-agent chat --continue

# Find an older thread to resume
my-agent threads list
my-agent chat --thread-id <uuid-from-list>

# Inspect what the agent remembers about you
my-agent memories list
my-agent memories read /memories/user.md

# Reclaim checkpoint disk space
my-agent threads prune --dry-run
my-agent threads prune

# Use from a project directory with project-specific config
cd ~/projects/my-app
my-agent chat   # picks up ./config.toml if it exists, or falls back to ~/.my-agent/config.toml
```

## Memory

The agent uses several memory layers:

| Layer | Storage | Purpose |
|-------|---------|---------|
| **Thread checkpoint** | `~/.my-agent/checkpoints.sqlite` | Exact replay of the current chat (`thread_id`) |
| **`/memories/` store** | `~/.my-agent/store.sqlite` | Durable agent-written notes (preferences, contacts, facts) |
| **Chroma** | `~/.my-agent/chroma` | Semantic search across past conversations |
| **AGENTS.md (home)** | `~/.my-agent/AGENTS.md` | Personal operating principles (loaded first into system prompt) |
| **AGENTS.md (project)** | `./AGENTS.md` | Project-specific rules (loaded second into system prompt) |
| **Skills** | `skills/` and `~/.my-agent/skills/` | Repeatable workflows loaded when relevant |

Within a thread, the agent remembers prior turns automatically. Personal facts should be saved under `/memories/` (persisted across restarts). Across threads, it can call `search_past_conversations` and related tools to find older context.

When both `~/.my-agent/AGENTS.md` and `./AGENTS.md` exist, both are injected into the system prompt (home first, project second), so project rules can supplement personal rules.

## Skills

Skills are markdown files with YAML frontmatter that teach the agent repeatable workflows.

| Scope | Filesystem path | Virtual path (agent tools) |
|-------|-----------------|----------------------------|
| Project | `./skills/{name}/SKILL.md` | `/skills/project/{name}/` |
| User | `~/.my-agent/skills/{name}/SKILL.md` | `/skills/{name}/` |

Bundled skills:

- `skills/tavily-web-search/` — when and how to search the live web
- `skills/creating-skills/` — how the agent authors new skills

See [AGENTS.md](AGENTS.md) for the agent's operating principles.

## Virtual paths in the agent

The agent has access to a virtual filesystem. Paths starting with `/` are routed to different backends:

| Virtual path | Maps to | Description |
|--------------|---------|-------------|
| `/memories/` | `~/.my-agent/store.sqlite` (SqliteStore) | Durable agent-written notes |
| `/cwd/` | Current working directory (filesystem) | Read/write project files |
| `/skills/` | `~/.my-agent/skills/` | User-scoped skills |
| `/skills/project/` | `./skills/` | Project-scoped skills |
| `/.agent/` | Agent state (ephemeral per thread) | Internal agent files |

The `/cwd/` route is especially useful when running from a project directory — you can ask the agent to read, edit, or create files relative to the current directory using paths like `/cwd/src/main.py`.

## Project structure

```
my-agent/
├── AGENTS.md              # Agent instructions (injected into system prompt)
├── config.toml.example    # Configuration template
├── skills/                # Project-scoped agent skills
├── src/my_agent/
│   ├── agent.py           # Deep agent setup
│   ├── checkpoint.py      # Thread persistence
│   ├── store.py           # /memories/ persistence
│   ├── cli.py             # Typer CLI
│   ├── config.py          # Config loading
│   ├── display.py         # Streaming output
│   ├── runner.py          # Turn execution
│   ├── help_text.py       # CLI help text
│   ├── memory/            # Chroma conversation store
│   └── tools/             # fetch_page, Tavily, conversation memory
└── pyproject.toml
```

## Security notes

- The agent can run shell commands and modify files within its configured root directory.
- With `require_approval = true` (default), destructive actions pause for your approval.
- Checkpoints and Chroma may contain tool output from your machine — they live locally in `~/.my-agent/` and are not committed to git.
- Never commit `.env` or `config.toml` with real API keys.

## License

Personal project — no license specified.
