from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from my_agent.config import (
    AppConfig,
    AgentConfig,
    CheckpointConfig,
    DisplayConfig,
    LLMConfig,
    MCPConfig,
    MemoryConfig,
    PathsConfig,
    SecurityConfig,
    StoreConfig,
    SummarizationConfig,
    TavilyConfig,
    VoiceConfig,
)


@pytest.fixture
def tmp_project_root(tmp_path: Path) -> Path:
    """A temporary project root with a minimal config.toml."""
    return tmp_path


@pytest.fixture
def mock_config(tmp_project_root: Path) -> AppConfig:
    """Create a minimal AppConfig for testing."""
    agent_state_dir = tmp_project_root / ".my-agent"
    agent_state_dir.mkdir(parents=True, exist_ok=True)
    skills_dir = tmp_project_root / "skills"
    skills_dir.mkdir(exist_ok=True)
    chroma_dir = tmp_project_root / "chroma"
    chroma_dir.mkdir(exist_ok=True)
    projects_skills_dir = tmp_project_root / "project-skills"
    projects_skills_dir.mkdir(exist_ok=True)

    return AppConfig(
        llm=LLMConfig(model="test-model", temperature=0.0),
        agent=AgentConfig(
            root_dir=tmp_project_root,
            system_prompt="You are a test agent.",
        ),
        security=SecurityConfig(require_approval=False),
        paths=PathsConfig(
            agent_state_dir=agent_state_dir,
            skills_user_dir=skills_dir,
            skills_project_dir=projects_skills_dir,
            chroma_dir=chroma_dir,
        ),
        memory=MemoryConfig(
            collection_name="test_conversations",
            embedding_model="test-embedding",
            index_on_each_turn=False,
        ),
        summarization=SummarizationConfig(
            enabled=False,
            max_messages=30,
            keep_last=10,
            model="",
            temperature=0.0,
        ),
        tavily=TavilyConfig(),
        voice=VoiceConfig(),
        display=DisplayConfig(),
        checkpoint=CheckpointConfig(backend="sqlite", sqlite_path=":memory:"),
        store=StoreConfig(backend="sqlite", sqlite_path=":memory:"),
        mcp=MCPConfig(),
        project_root=tmp_project_root,
        home_agent_dir=tmp_project_root / ".my-agent",
        agents_md_paths=(),
        config_dir=tmp_project_root,
        has_cwd_skills=True,
    )


@pytest.fixture
def mock_env_openrouter_key() -> Any:
    """Temporarily set OPENROUTER_API_KEY for tests that load config."""
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}, clear=False) as env:
        yield env


@pytest.fixture
def mock_agent() -> MagicMock:
    """A generic mock agent object for runner/CLI tests."""
    agent = MagicMock()
    agent.stream_events.return_value.interrupted = False
    agent.stream_events.return_value.output = {
        "messages": [MagicMock(content="Hello from fake agent!")]
    }
    return agent