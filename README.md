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
| `[memory]` | Chroma collection and embedding model |
| `[tavily]` | Web search defaults |
| `[display]` | Streaming verbosity defaults |

Local state is stored under `~/.my-agent/` by default (checkpoints, Chroma, user skills).

## Usage

### Chat

```bash
# New conversation
my-agent chat

# Resume the most recent thread
my-agent chat --continue

# Resume a specific thread
my-agent chat --thread-id <uuid>

# Show reasoning and tool activity
my-agent chat --verbose

# Hide internal activity
my-agent chat --quiet
```

### One-shot run

```bash
my-agent run "List the five largest files in my Downloads folder"
my-agent run --continue "Now sort them by date"
```

### Thread management

```bash
# List saved threads (newest first)
my-agent threads list

# Limit results
my-agent threads list --limit 10
```

Type `exit` or `quit` to leave interactive chat.

## Memory

The agent uses several memory layers:

| Layer | Storage | Purpose |
|-------|---------|---------|
| **Thread checkpoint** | `~/.my-agent/checkpoints.sqlite` | Exact replay of the current chat (`thread_id`) |
| **Chroma** | `~/.my-agent/chroma` | Semantic search across past conversations |
| **AGENTS.md** | Project root | Always-on operating principles and instructions |
| **Skills** | `skills/` and `~/.my-agent/skills/` | Repeatable workflows loaded when relevant |

Within a thread, the agent remembers prior turns automatically. Across threads, it can call `search_past_conversations` and related tools to find older context.

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
