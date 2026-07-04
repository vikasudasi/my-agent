from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpTopic:
    name: str
    aliases: tuple[str, ...]
    summary: str
    body: str


_OVERVIEW = """\
my-agent — local macOS deep agent (LangChain Deep Agents + OpenRouter)

Command tree:
  chat                         Interactive REPL
  run <task>                   One-shot task
  transcribe <audio>           Transcribe an audio file (OpenRouter STT)
  threads list                 List saved chat threads
  threads prune                Delete old threads (retention limits)
  threads delete <id>          Delete one thread
  memories list                List /memories/ files
  memories read <path>         Print a /memories/ file
  help [topic]                 This help (e.g. help chat, help threads prune)

Global option (most commands):
  --config FILE                Path to config.toml
                               (default: ./config.toml -> ~/.my-agent/config.toml)

Config resolution order:
  1. --config <path> CLI flag
  2. ./config.toml (project directory)
  3. ~/.my-agent/config.toml (personal defaults)

Environment: ~/.my-agent/.env then ./.env (cwd overrides home).

Per-command details:
  my-agent help chat
  my-agent help run
  my-agent help threads
  my-agent help memories

Typer also provides: my-agent <command> --help
"""

_CHAT = """\
my-agent chat — interactive REPL chat with the agent

Each session prints a thread_id at startup. Type exit or quit to leave.

Options:
  --thread-id TEXT    Resume a specific saved thread
  --continue          Resume the most recently updated thread
  --voice             Enable voice input (/mic for push-to-talk)
  --conversation      Voice companion mode: /mic input + spoken companion audio
  --verbose           Show reasoning, tool calls, tool results, loaded skills
  --quiet             Hide reasoning, tool calls, tool results, loaded skills
  --config FILE       Path to config.toml

Notes:
  --continue and --thread-id cannot be used together.
  Resuming shows: Resuming thread <uuid> (N messages)
  In voice mode, type /mic then hold Space to record.
  After transcription: Enter to send, e to edit, r to re-record, c to cancel.
  In conversation mode, the agent speaks often (JARVIS-style): acknowledgments,
  progress before tools, and wrap-ups. Speaker note lines show what is spoken aloud.

Examples:
  my-agent chat
  my-agent chat --voice
  my-agent chat --conversation
  my-agent chat --continue
  my-agent chat --thread-id <uuid>
  my-agent chat --verbose
"""

_RUN = """\
my-agent run — run a single task and exit

Arguments:
  TASK                One-shot prompt for the agent (optional with --audio)

Options:
  --audio FILE        Transcribe audio via OpenRouter and use as the task
  --thread-id TEXT    Attach to an existing thread (default: new UUID)
  --continue          Use the most recently updated thread
  --verbose           Show reasoning, tool calls, tool results, loaded skills
  --quiet             Hide reasoning, tool calls, tool results, loaded skills
  --config FILE       Path to config.toml

Examples:
  my-agent run "List the five largest files in my Downloads folder"
  my-agent run --audio question.wav
  my-agent run "Summarize this:" --audio meeting.mp3
  my-agent run --continue "Now sort them by date"
  my-agent run --verbose "Summarize today's AI news"
"""

_TRANSCRIBE = """\
my-agent transcribe — transcribe an audio file via OpenRouter STT

Arguments:
  AUDIO               Audio file (wav, mp3, flac, m4a, ogg, webm, aac)

Options:
  --config FILE       Path to config.toml

Config ([voice] in config.toml):
  model               STT model slug (default: openai/whisper-large-v3)
  language            Optional ISO-639-1 hint (empty = auto-detect)

Conversation mode (--conversation):
  speak tool          Agent queues brief spoken status lines during a turn
  [voice]...[/voice]  Optional spoken wrap-up tags in assistant text
  Speaker note        Terminal line showing each phrase queued for audio
  tts_backend         macOS say (default) via [voice.conversation]

Examples:
  my-agent transcribe question.wav
  my-agent transcribe meeting.mp3
"""

_THREADS = """\
my-agent threads — inspect and manage saved chat threads

Subcommands:
  list                List threads (newest first)
  prune               Delete old threads by retention limits
  delete <thread-id>  Delete one thread

Thread data is stored in ~/.my-agent/checkpoints.sqlite (config [checkpoint]).

Examples:
  my-agent threads list
  my-agent threads prune --dry-run
  my-agent threads delete <uuid> --yes

See also:
  my-agent help threads list
  my-agent help threads prune
  my-agent help threads delete
"""

_THREADS_LIST = """\
my-agent threads list — list saved chat threads (newest first)

Shows thread_id, updated time, message count, and first user message snippet.

Options:
  --limit N           Maximum threads to show (default: 20)
  --config FILE       Path to config.toml

Examples:
  my-agent threads list
  my-agent threads list --limit 10

Use thread_id with: my-agent chat --thread-id <uuid>
"""

_THREADS_PRUNE = """\
my-agent threads prune — delete old threads by count and/or age

Uses config [checkpoint] unless overridden. The newest thread is protected
by default (the one my-agent chat --continue would resume).

Options:
  --keep N              Keep N newest threads (0 = no count limit)
                        Default: config max_threads
  --max-age-days N      Delete threads older than N days (0 = disabled)
                        Default: config max_thread_age_days
  --dry-run             Preview deletions without applying
  --no-protect-latest   Allow deleting the most recent thread
  --no-vacuum           Skip SQLite VACUUM after prune
  --config FILE         Path to config.toml

Config (config.toml):
  [checkpoint]
  max_threads = 50
  max_thread_age_days = 0

Examples:
  my-agent threads prune --dry-run
  my-agent threads prune
  my-agent threads prune --keep 20
  my-agent threads prune --max-age-days 90
"""

_THREADS_DELETE = """\
my-agent threads delete — delete one thread and all checkpoint data

Arguments:
  THREAD_ID           Thread to delete (from threads list)

Options:
  --yes, -y           Skip confirmation prompt
  --config FILE       Path to config.toml

Examples:
  my-agent threads delete 0353da51-f909-4144-b95a-52db1ea8986f
  my-agent threads delete 0353da51-f909-4144-b95a-52db1ea8986f --yes
"""

_MEMORIES = """\
my-agent memories — inspect agent memory files under /memories/

Files persist in ~/.my-agent/store.sqlite (config [store]).
The agent writes personal facts here via write_file / edit_file.

Subcommands:
  list                List memory files (newest first)
  read <path>         Print file contents

Examples:
  my-agent memories list
  my-agent memories read /memories/user.md

See also:
  my-agent help memories list
  my-agent help memories read
"""

_MEMORIES_LIST = """\
my-agent memories list — list persisted /memories/ files

Options:
  --limit N           Maximum files to show (default: 50)
  --config FILE       Path to config.toml

Examples:
  my-agent memories list
  my-agent memories list --limit 20
"""

_MEMORIES_READ = """\
my-agent memories read — print a /memories/ file

Arguments:
  PATH                Virtual path, e.g. /memories/user.md

Options:
  --config FILE       Path to config.toml

Examples:
  my-agent memories read /memories/user.md
  my-agent memories read /memories/preferences.md
"""

_TOPICS: tuple[HelpTopic, ...] = (
    HelpTopic("overview", ("", "all", "commands"), "All commands", _OVERVIEW),
    HelpTopic("chat", (), "Interactive REPL", _CHAT),
    HelpTopic("run", (), "One-shot task", _RUN),
    HelpTopic("transcribe", (), "Speech-to-text", _TRANSCRIBE),
    HelpTopic("threads", (), "Thread management", _THREADS),
    HelpTopic("threads list", ("threads-list",), "List threads", _THREADS_LIST),
    HelpTopic("threads prune", ("threads-prune",), "Prune threads", _THREADS_PRUNE),
    HelpTopic("threads delete", ("threads-delete",), "Delete thread", _THREADS_DELETE),
    HelpTopic("memories", (), "Memory files", _MEMORIES),
    HelpTopic("memories list", ("memories-list",), "List memories", _MEMORIES_LIST),
    HelpTopic("memories read", ("memories-read",), "Read memory file", _MEMORIES_READ),
)

_TOPIC_INDEX: dict[str, HelpTopic] = {}
for _topic in _TOPICS:
    _TOPIC_INDEX[_topic.name.lower()] = _topic
    for _alias in _topic.aliases:
        _TOPIC_INDEX[_alias.lower()] = _topic


def list_help_topics() -> list[str]:
    """Return canonical topic names for tab completion / listing."""
    seen: set[str] = set()
    names: list[str] = []
    for topic in _TOPICS:
        if topic.name not in seen:
            seen.add(topic.name)
            names.append(topic.name)
    return names


def render_help(topic: str | None = None) -> str:
    """Return help text for a topic, or the full overview when topic is None."""
    if topic is None or topic.strip() == "":
        return _OVERVIEW

    key = topic.strip().lower()
    entry = _TOPIC_INDEX.get(key)
    if entry is None:
        available = ", ".join(list_help_topics())
        return (
            f"Unknown help topic: {topic!r}\n\n"
            f"Available topics: {available}\n\n"
            "Run my-agent help for an overview."
        )
    return entry.body
