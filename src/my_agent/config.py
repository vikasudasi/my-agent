from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


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
class AppConfig:
    llm: LLMConfig
    agent: AgentConfig
    security: SecurityConfig
    paths: PathsConfig
    memory: MemoryConfig
    tavily: TavilyConfig
    display: DisplayConfig
    checkpoint: CheckpointConfig
    store: StoreConfig
    project_root: Path  # cwd at agent startup
    cwd: Path  # current working directory (same as project_root for now, separate for clarity)
    home_agent_dir: Path  # ~/.my-agent resolved
    agents_md_paths: tuple[Path, ...]  # all existing AGENTS.md paths (home first, then cwd)
    config_dir: Path  # directory of the loaded config.toml
    has_cwd_skills: bool  # whether ./skills exists


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
    tavily_section = raw.get("tavily", {})
    display_section = raw.get("display", {})
    checkpoint_section = raw.get("checkpoint", {})
    store_section = raw.get("store", {})

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
    # 6. Build AppConfig
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
        tavily=TavilyConfig(
            max_results=int(tavily_section.get("max_results", 5)),
            topic=str(tavily_section.get("topic", "general")),
            search_depth=str(tavily_section.get("search_depth", "basic")),
            include_answer=bool(tavily_section.get("include_answer", False)),
            include_raw_content=bool(tavily_section.get("include_raw_content", False)),
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
        project_root=project_root,
        cwd=project_root,
        home_agent_dir=home_agent,
        agents_md_paths=agents_md_paths,
        config_dir=config_dir,
        has_cwd_skills=has_cwd_skills,
    )
