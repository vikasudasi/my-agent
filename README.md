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

## Configuration

Copy `config.toml.example` to `config.toml` and edit as needed. Secrets go in `.env`:

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
| `[checkpoint]` | Thread persistence (`sqlite` or `memory`) |
| `[store]` | `/memories/` persistence (`sqlite` or `memory`) |
| `[memory]` | Chroma collection and embedding model |
| `[tavily]` | Web search defaults |
| `[display]` | Streaming verbosity defaults |

Local state is stored under `~/.my-agent/` by default (checkpoints, Chroma, user skills).

## CLI reference

```
my-agent
├── chat              Interactive REPL
├── run <task>        One-shot task
├── threads list      List saved chat threads
└── memories
    ├── list          List /memories/ files
    └── read <path>   Print a /memories/ file
```

Global options are available on every command:

| Option | Description |
|--------|-------------|
| `--config FILE` | Path to `config.toml` (default: `./config.toml`) |
| `--help` | Show command help |

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
```

## Memory

The agent uses several memory layers:

| Layer | Storage | Purpose |
|-------|---------|---------|
| **Thread checkpoint** | `~/.my-agent/checkpoints.sqlite` | Exact replay of the current chat (`thread_id`) |
| **`/memories/` store** | `~/.my-agent/store.sqlite` | Durable agent-written notes (preferences, contacts, facts) |
| **Chroma** | `~/.my-agent/chroma` | Semantic search across past conversations |
| **AGENTS.md** | Project root | Always-on operating principles and instructions |
| **Skills** | `skills/` and `~/.my-agent/skills/` | Repeatable workflows loaded when relevant |

Within a thread, the agent remembers prior turns automatically. Personal facts should be saved under `/memories/` (persists across restarts). Across threads, it can call `search_past_conversations` and related tools to find older context.

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
