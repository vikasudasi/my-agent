from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


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
class AppConfig:
    llm: LLMConfig
    agent: AgentConfig
    security: SecurityConfig
    paths: PathsConfig
    memory: MemoryConfig
    tavily: TavilyConfig
    display: DisplayConfig
    project_root: Path
    agents_md_path: Path


def _expand_path(value: str, base: Path) -> Path:
    expanded = os.path.expanduser(value)
    path = Path(expanded)
    if not path.is_absolute():
        path = (base / path).resolve()
    return path


def _read_agents_md(project_root: Path) -> str:
    agents_md = project_root / "AGENTS.md"
    if agents_md.is_file():
        return agents_md.read_text(encoding="utf-8").strip()
    return "You are a helpful personal macOS assistant."


def load_config(config_path: Path | None = None, env_path: Path | None = None) -> AppConfig:
    project_root = Path.cwd().resolve()
    config_file = config_path or (project_root / "config.toml")
    if not config_file.is_file():
        example = project_root / "config.toml.example"
        if example.is_file():
            raise FileNotFoundError(
                f"Missing {config_file}. Copy config.toml.example to config.toml and edit it."
            )
        raise FileNotFoundError(f"Missing config file: {config_file}")

    dotenv_file = env_path or (project_root / ".env")
    if dotenv_file.is_file():
        load_dotenv(dotenv_file)

    with config_file.open("rb") as handle:
        raw = tomllib.load(handle)

    llm_section = raw.get("llm", {})
    agent_section = raw.get("agent", {})
    security_section = raw.get("security", {})
    paths_section = raw.get("paths", {})
    memory_section = raw.get("memory", {})
    tavily_section = raw.get("tavily", {})
    display_section = raw.get("display", {})

    model = llm_section.get("model", "").strip()
    if not model:
        raise ValueError("config.toml [llm].model is required")

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is not set. Add it to .env (see .env.example)."
        )

    agents_md_path = project_root / "AGENTS.md"
    configured_prompt = agent_section.get("system_prompt", "").strip()
    system_prompt = configured_prompt or _read_agents_md(project_root)

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
        paths.skills_project_dir,
        paths.chroma_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

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
        project_root=project_root,
        agents_md_path=agents_md_path,
    )
