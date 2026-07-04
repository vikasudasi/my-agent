from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


_HOME_AGENT_DIR = Path.home() / ".my-agent"


@dataclass(frozen=True)
class LLMConfig:
    model: str
    temperature: float


@dataclass(frozen=True)
class AgentConfig:
    root_dir: Path
    system_prompt: str


@dataclass(frozen=True)
class SecurityConfig:
    require_approval: bool


@dataclass(frozen=True)
class PathsConfig:
    agent_state_dir: Path
    skills_user_dir: Path
    skills_project_dir: Path
    chroma_dir: Path


@dataclass(frozen=True)
class MemoryConfig:
    collection_name: str
    embedding_model: str
    index_on_each_turn: bool


@dataclass(frozen=True)
class TavilyConfig:
    max_results: int = 5
    topic: str = "general"
    search_depth: str = "basic"
    include_answer: bool = False
    include_raw_content: bool = False


@dataclass(frozen=True)
class DisplayConfig:
    show_reasoning: bool = True
    show_tool_calls: bool = True
    show_tool_results: bool = True
    show_skills: bool = True
    tool_result_max_chars: int = 500


@dataclass(frozen=True)
class SummarizationConfig:
    enabled: bool = True
    max_messages: int = 30
    keep_last: int = 10
    model: str = ""
    temperature: float = 0.0


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool = False
    model: str = "openai/whisper-large-v3"
    language: str = ""
    max_duration_seconds: float = 120.0
    confirm_before_send: bool = True


@dataclass(frozen=True)
class VoiceConversationConfig:
    enabled: bool = False
    tts_backend: str = "macos"
    tts_voice: str = ""
    max_speak_chars: int = 500
    strip_voice_tags_from_terminal: bool = True
    show_speaker_notes: bool = True


@dataclass(frozen=True)
class CheckpointConfig:
    backend: str = "sqlite"
    sqlite_path: str = "checkpoints.sqlite"
    max_threads: int = 50
    max_thread_age_days: int = 0


@dataclass(frozen=True)
class StoreConfig:
    backend: str = "sqlite"
    sqlite_path: str = "store.sqlite"


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: str = "stdio"
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class MCPConfig:
    enabled: bool = True
    servers: tuple[MCPServerConfig, ...] = ()


@dataclass(frozen=True)
class AppConfig:
    llm: LLMConfig
    agent: AgentConfig
    security: SecurityConfig
    paths: PathsConfig
    memory: MemoryConfig
    summarization: SummarizationConfig
    tavily: TavilyConfig
    voice: VoiceConfig
    voice_conversation: VoiceConversationConfig
    display: DisplayConfig
    checkpoint: CheckpointConfig
    store: StoreConfig
    mcp: MCPConfig
    project_root: Path  # cwd at agent startup
    home_agent_dir: Path  # ~/.my-agent resolved
    agents_md_paths: tuple[Path, ...]  # all existing AGENTS.md paths (home first, then cwd)
    config_dir: Path  # directory of the loaded config.toml
    has_cwd_skills: bool  # whether ./skills exists

    def build_backend_awareness(self) -> str:
        """Generate backend routing rules and examples for the system prompt.

        Gives the agent self-awareness about virtual paths, backend tools,
        and how to translate between file tools and shell commands.
        """
        project_root = self.project_root
        skills_user_dir = self.paths.skills_user_dir
        project_skills_mapping = ""
        project_skills_row = ""
        project_skill_virtual = "/skills/project/{name}/SKILL.md"
        project_skill_example = (
            f'`read_file("{project_skill_virtual.replace("{name}", "tavily-web-search")}")`'
        )
        project_skill_shell = (
            f'`execute("cat {self.paths.skills_project_dir}/tavily-web-search/SKILL.md")`'
        )
        activate_skill_step = '2. `read_file("/skills/project/{name}/SKILL.md")`'

        if self.has_cwd_skills:
            project_skills_mapping = (
                f"- `/skills/project/` -> `{self.paths.skills_project_dir}/`\n"
            )
            project_skills_row = (
                f"| `/skills/project/` | Project-scoped skills "
                f"(`{self.paths.skills_project_dir}/`) | On disk | "
                f'`/skills/project/tavily-web-search/SKILL.md` |\n'
            )
        else:
            project_skill_example = (
                f'`read_file("/skills/my-workflow/SKILL.md")`'
            )
            project_skill_shell = (
                f'`execute("cat {skills_user_dir}/my-workflow/SKILL.md")`'
            )
            activate_skill_step = '2. `read_file("/skills/{name}/SKILL.md")`'

        return f"""## Backend & filesystem self-awareness

You have a **virtual filesystem** backed by multiple storage layers. Path choice matters — using the wrong prefix causes "file not found" or writing to the wrong place.

### Host path mappings

- `/cwd/` -> `{project_root}/`
- `/skills/` -> `{skills_user_dir}/`
{project_skills_mapping}- default (`execute` cwd) -> `{project_root}/`

### Golden rules

1. **File tools** (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`) → always use **virtual paths** with the correct prefix.
2. **`execute` (shell)** → use **real host paths** from Host path mappings above. Shell cwd is `{project_root}/`.
3. **Never mix styles** in one action: `read_file("/cwd/src/main.py")` ✓ but `execute("cat /cwd/src/main.py")` ✗ — shell does not understand `/cwd/`.
4. **Prefer `/cwd/`** for project files. Do not use bare paths like `/src/main.py` or `src/main.py` unless you have a specific reason.
5. **`execute` is not sandboxed** — it can read/write anywhere your user can, regardless of virtual path rules. Use carefully.

### Virtual path routing

| Virtual prefix | What it is | Persists? | Example |
|----------------|------------|-----------|---------|
| `/cwd/` | Project files (directory you launched from) | On disk | `/cwd/src/my_agent/agent.py` |
| `/memories/` | Durable personal notes | Across threads & restarts | `/memories/user.md` |
| `/skills/` | User-scoped skills (`{skills_user_dir}/`) | On disk | `/skills/my-workflow/SKILL.md` |
{project_skills_row}| `/.agent/` | Internal scratch space for this chat thread | This thread only | `/.agent/scratch.md` |
| *(no prefix)* | Falls through to default backend (project root) | On disk | `/notes.txt` → project dir (avoid — use `/cwd/` instead) |

### Available backend tools

| Tool | Purpose | Path style |
|------|---------|------------|
| `ls` | List directory | Virtual |
| `read_file` | Read file (supports images) | Virtual |
| `write_file` | Create/overwrite file | Virtual |
| `edit_file` | Find-and-replace in file | Virtual |
| `glob` | Find files by pattern | Virtual |
| `grep` | Search file contents | Virtual |
| `execute` | Run shell command on host | **Real paths** in command string |

Destructive file/shell actions (`execute`, `write_file`, `edit_file`) may pause for user approval before running.

### Path translation cheat sheet

| Intent | File tool path | Shell command |
|--------|----------------|---------------|
| Read project source | `read_file("/cwd/src/foo.py")` | `execute("cat {project_root}/src/foo.py")` |
| Run tests | — | `execute("pytest tests/ -q")` |
| Save a preference | `write_file("/memories/preferences.md", ...)` | *(don't use shell for memories)* |
| Read a skill | {project_skill_example} | {project_skill_shell} |
| List project tree | `ls("/cwd/src")` | `execute("ls {project_root}/src")` |

### Common mistakes (avoid these)

| Wrong | Right | Why |
|-------|-------|-----|
| `execute("cat /cwd/src/main.py")` | `execute("cat {project_root}/src/main.py")` | Shell doesn't resolve `/cwd/` |
| `read_file("src/main.py")` | `read_file("/cwd/src/main.py")` | Relative paths are ambiguous |
| `write_file("/memories/foo.md", ...)` via shell | `write_file("/memories/foo.md", ...)` | `/memories/` is a store, not a normal folder for `cat`/`echo` |
| `read_file("/skills/tavily-web-search/...")` when skill is in repo | `read_file("/skills/project/tavily-web-search/...")` | Project skills live under `/skills/project/` |
| Putting secrets in `/memories/` or skills | Reference env var names only | Memories and skills persist locally |

### Where to store what

| Information type | Where | Tool |
|------------------|-------|------|
| User preference ("remember my email") | `/memories/user.md` | `write_file` / `edit_file` |
| Project coding rules | `/cwd/AGENTS.md` | `read_file` / `edit_file` |
| Repeatable workflow | `/skills/project/{{name}}/SKILL.md` or `/skills/{{name}}/SKILL.md` | `write_file` |
| Past conversation recall | — | `search_past_conversations` (not filesystem) |
| Temporary notes for this chat | `/.agent/` | `write_file` (ephemeral) |

### Skills vs filesystem

- At startup you see skill **names and descriptions** only (metadata).
- When a task matches a skill, **read the full SKILL.md** before acting:
  - Project skill: `/skills/project/{{name}}/SKILL.md`
  - User skill: `/skills/{{name}}/SKILL.md`
- Supporting files (`references/`, `scripts/`) are loaded only when the skill instructions say so.

### Example workflows

**Edit a project file**
1. `read_file("/cwd/src/my_agent/config.py")`
2. `edit_file("/cwd/src/my_agent/config.py", old_string="...", new_string="...")`
3. `execute("pytest tests/test_config.py -q")`

**Remember something for future sessions**
1. `read_file("/memories/user.md")` (if exists)
2. `write_file("/memories/user.md", "...")` or `edit_file(...)`

**Run a command in the project**
1. `execute("pytest tests/ -q")` — shell cwd is already `{project_root}/`

**Activate a skill**
1. Match task to skill description (e.g. "search the web")
{activate_skill_step}
3. Follow the skill's steps using the appropriate tools"""

    def build_path_mappings(self) -> str:
        """Backward-compatible alias for :meth:`build_backend_awareness`."""
        return self.build_backend_awareness()


def _expand_path(value: str, base: Path) -> Path:
    expanded = os.path.expanduser(value)
    path = Path(expanded)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _read_agents_md(file_path: Path) -> str | None:
    if file_path.is_file():
        return file_path.read_text(encoding="utf-8").strip()
    return None


def _interpolate_env(value: str) -> str:
    """Replace ``${VAR_NAME}`` placeholders with environment variable values."""

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1).strip()
        if not var_name:
            return match.group(0)
        return os.environ.get(var_name, match.group(0))

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _interpolate_env_value(value: Any) -> Any:
    """Recursively interpolate env vars in MCP config string values."""
    if isinstance(value, str):
        return _interpolate_env(value)
    if isinstance(value, list):
        return [_interpolate_env_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _interpolate_env_value(item) for key, item in value.items()}
    return value


def _load_voice_conversation_config(raw: dict[str, Any]) -> VoiceConversationConfig:
    """Parse ``[voice.conversation]`` settings."""
    return VoiceConversationConfig(
        enabled=bool(raw.get("enabled", False)),
        tts_backend=str(raw.get("tts_backend", "macos")),
        tts_voice=str(raw.get("tts_voice", "")),
        max_speak_chars=int(raw.get("max_speak_chars", 500)),
        strip_voice_tags_from_terminal=bool(
            raw.get("strip_voice_tags_from_terminal", True)
        ),
        show_speaker_notes=bool(raw.get("show_speaker_notes", True)),
    )


def _parse_mcp_server(raw: dict[str, Any]) -> MCPServerConfig:
    """Build an MCPServerConfig with env-var interpolation applied."""
    headers = raw.get("headers")
    return MCPServerConfig(
        name=str(raw["name"]),
        transport=str(raw.get("transport", "stdio")),
        command=_interpolate_env_value(raw.get("command")),
        args=_interpolate_env_value(raw.get("args")),
        url=_interpolate_env_value(raw.get("url")),
        headers=_interpolate_env_value(headers) if headers is not None else None,
    )


def _build_system_prompt(
    configured_prompt: str,
    home_agents: str | None,
    cwd_agents: str | None,
) -> str:
    """Combine AGENTS.md contents with optional configured prompt override.

    Order: home AGENTS.md first, then cwd AGENTS.md (so cwd rules can
    supplement or refine personal rules). A configured prompt in config.toml
    replaces all file-based content.
    """
    if configured_prompt:
        return configured_prompt

    parts: list[str] = []
    for content in (home_agents, cwd_agents):
        if content and content not in parts:
            parts.append(content)

    if not parts:
        return "You are a helpful personal macOS assistant."

    return "\n\n---\n\n".join(parts)


def load_config(config_path: Path | None = None, env_path: Path | None = None) -> AppConfig:
    project_root = Path.cwd().resolve()
    home_agent = _HOME_AGENT_DIR.resolve()

    # ------------------------------------------------------------------
    # 1. Config file: --config > ./config.toml > ~/.my-agent/config.toml
    # ------------------------------------------------------------------
    if config_path is not None:
        config_file = config_path.resolve()
    else:
        cwd_config = project_root / "config.toml"
        home_config = home_agent / "config.toml"
        if cwd_config.is_file():
            config_file = cwd_config
        elif home_config.is_file():
            config_file = home_config
        else:
            example = project_root / "config.toml.example"
            if example.is_file():
                raise FileNotFoundError(
                    f"Missing config.toml. Copy config.toml.example to one of:\n"
                    f"  {cwd_config}\n"
                    f"  {home_config}\n"
                    "then edit it."
                )
            raise FileNotFoundError(
                f"Missing config file. Create {cwd_config} or {home_config}."
            )

    config_dir = config_file.parent.resolve()

    # ------------------------------------------------------------------
    # 2. Dotenv: system env first, then ~/.my-agent/.env, then ./.env overrides
    # ------------------------------------------------------------------
    dotenv_file = env_path
    if dotenv_file is None:
        home_dotenv = home_agent / ".env"
        cwd_dotenv = project_root / ".env"
        # Load home first, cwd overrides
        if home_dotenv.is_file():
            load_dotenv(home_dotenv)
        if cwd_dotenv.is_file():
            load_dotenv(cwd_dotenv, override=True)

    with config_file.open("rb") as handle:
        raw = tomllib.load(handle)

    llm_section = raw.get("llm", {})
    agent_section = raw.get("agent", {})
    security_section = raw.get("security", {})
    paths_section = raw.get("paths", {})
    memory_section = raw.get("memory", {})
    summarization_section = raw.get("summarization", {})
    tavily_section = raw.get("tavily", {})
    voice_section = raw.get("voice", {})
    display_section = raw.get("display", {})
    checkpoint_section = raw.get("checkpoint", {})
    store_section = raw.get("store", {})
    mcp_section = raw.get("mcp", {})

    model = llm_section.get("model", "").strip()
    if not model:
        raise ValueError("config.toml [llm].model is required")

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is not set. Add it to .env (see .env.example)."
        )

    # ------------------------------------------------------------------
    # 3. AGENTS.md paths (home first, cwd second)
    # ------------------------------------------------------------------
    cwd_agents_md = project_root / "AGENTS.md"
    home_agents_md = home_agent / "AGENTS.md"
    home_agents_content = _read_agents_md(home_agents_md)
    cwd_agents_content = _read_agents_md(cwd_agents_md)

    agents_md_paths: tuple[Path, ...] = ()
    if home_agents_content is not None:
        agents_md_paths += (home_agents_md,)
    if cwd_agents_content is not None and (
        not agents_md_paths or cwd_agents_md != agents_md_paths[-1]
    ):
        agents_md_paths += (cwd_agents_md,)

    configured_prompt = agent_section.get("system_prompt", "").strip()
    system_prompt = _build_system_prompt(
        configured_prompt, home_agents_content, cwd_agents_content
    )

    # ------------------------------------------------------------------
    # 4. Paths
    # ------------------------------------------------------------------
    paths = PathsConfig(
        agent_state_dir=_expand_path(
            paths_section.get("agent_state_dir", "~/.my-agent"), project_root
        ),
        skills_user_dir=_expand_path(
            paths_section.get("skills_user_dir", "~/.my-agent/skills"), project_root
        ),
        skills_project_dir=_expand_path(
            paths_section.get("skills_project_dir", "./skills"), project_root
        ),
        chroma_dir=_expand_path(
            paths_section.get("chroma_dir", "~/.my-agent/chroma"), project_root
        ),
    )

    for directory in (
        paths.agent_state_dir,
        paths.skills_user_dir,
        paths.chroma_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 5. Check if .cwd skills exist
    # ------------------------------------------------------------------
    has_cwd_skills = (project_root / "skills").is_dir()

    # ------------------------------------------------------------------
    # 6. MCP servers: merge from home config + cwd config
    # ------------------------------------------------------------------
    mcp_enabled = bool(mcp_section.get("enabled", True))
    merged_servers: dict[str, MCPServerConfig] = {}
    for cfg_path in (home_agent / "config.toml", project_root / "config.toml"):
        if cfg_path.is_file() and cfg_path != config_file:
            with cfg_path.open("rb") as handle:
                other_raw = tomllib.load(handle)
            other_mcp = other_raw.get("mcp", {})
            for s in other_mcp.get("servers", ()):
                merged_servers[s["name"]] = _parse_mcp_server(s)
    # Also add servers from the primary config file (these win on name conflict)
    for s in mcp_section.get("servers", ()):
        merged_servers[s["name"]] = _parse_mcp_server(s)

    mcp = MCPConfig(enabled=mcp_enabled, servers=tuple(merged_servers.values()))

    # ------------------------------------------------------------------
    # 7. Build AppConfig
    # ------------------------------------------------------------------
    return AppConfig(
        llm=LLMConfig(
            model=model,
            temperature=float(llm_section.get("temperature", 0)),
        ),
        agent=AgentConfig(
            root_dir=_expand_path(agent_section.get("root_dir", "~"), project_root),
            system_prompt=system_prompt,
        ),
        security=SecurityConfig(
            require_approval=bool(security_section.get("require_approval", True)),
        ),
        paths=paths,
        memory=MemoryConfig(
            collection_name=memory_section.get("collection_name", "conversations"),
            embedding_model=memory_section.get(
                "embedding_model", "sentence-transformers/all-MiniLM-L6-v2"
            ),
            index_on_each_turn=bool(memory_section.get("index_on_each_turn", True)),
        ),
        summarization=SummarizationConfig(
            enabled=bool(summarization_section.get("enabled", True)),
            max_messages=int(summarization_section.get("max_messages", 30)),
            keep_last=int(summarization_section.get("keep_last", 10)),
            model=str(summarization_section.get("model", "")),
            temperature=float(summarization_section.get("temperature", 0.0)),
        ),
        tavily=TavilyConfig(
            max_results=int(tavily_section.get("max_results", 5)),
            topic=str(tavily_section.get("topic", "general")),
            search_depth=str(tavily_section.get("search_depth", "basic")),
            include_answer=bool(tavily_section.get("include_answer", False)),
            include_raw_content=bool(tavily_section.get("include_raw_content", False)),
        ),
        voice=VoiceConfig(
            enabled=bool(voice_section.get("enabled", False)),
            model=str(voice_section.get("model", "openai/whisper-large-v3")),
            language=str(voice_section.get("language", "")),
            max_duration_seconds=float(
                voice_section.get("max_duration_seconds", 120.0)
            ),
            confirm_before_send=bool(voice_section.get("confirm_before_send", True)),
        ),
        voice_conversation=_load_voice_conversation_config(
            voice_section.get("conversation", {})
        ),
        display=DisplayConfig(
            show_reasoning=bool(display_section.get("show_reasoning", True)),
            show_tool_calls=bool(display_section.get("show_tool_calls", True)),
            show_tool_results=bool(display_section.get("show_tool_results", True)),
            show_skills=bool(display_section.get("show_skills", True)),
            tool_result_max_chars=int(display_section.get("tool_result_max_chars", 500)),
        ),
        checkpoint=CheckpointConfig(
            backend=str(checkpoint_section.get("backend", "sqlite")).strip().lower(),
            sqlite_path=str(
                checkpoint_section.get("sqlite_path", "checkpoints.sqlite")
            ),
            max_threads=int(checkpoint_section.get("max_threads", 50)),
            max_thread_age_days=int(
                checkpoint_section.get("max_thread_age_days", 0)
            ),
        ),
        store=StoreConfig(
            backend=str(store_section.get("backend", "sqlite")).strip().lower(),
            sqlite_path=str(store_section.get("sqlite_path", "store.sqlite")),
        ),
        mcp=mcp,
        project_root=project_root,
        home_agent_dir=home_agent,
        agents_md_paths=agents_md_paths,
        config_dir=config_dir,
        has_cwd_skills=has_cwd_skills,
    )
