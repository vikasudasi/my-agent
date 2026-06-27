from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    LocalShellBackend,
    StateBackend,
    StoreBackend,
)
from my_agent.checkpoint import get_checkpointer
from my_agent.config import AppConfig, load_config
from my_agent.memory.chroma_store import ChromaConversationStore
from my_agent.tools.conversation_memory import build_conversation_tools
from my_agent.tools.fetch_page import fetch_page
from my_agent.store import get_store
from my_agent.tools.tavily_search import build_tavily_tools


@lru_cache(maxsize=4)
def _build_agent_bundle(config_path: str | None) -> tuple:
    config = load_config(config_path=Path(config_path) if config_path else None)
    chroma_store = ChromaConversationStore(config)
    agent = _create_agent(config, chroma_store)
    return config, chroma_store, agent


def get_agent(config_path: str | None = None):
    _, _, agent = _build_agent_bundle(config_path)
    return agent


def get_runtime(config_path: str | None = None):
    return _build_agent_bundle(config_path)


def _create_agent(config: AppConfig, chroma_store: ChromaConversationStore):
    home = str(config.agent.root_dir)
    shell_env = os.environ.copy()
    for path_entry in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"):
        if path_entry not in shell_env.get("PATH", ""):
            shell_env["PATH"] = f"{path_entry}:{shell_env.get('PATH', '')}"

    store = get_store(config)
    backend = CompositeBackend(
        default=LocalShellBackend(
            root_dir=home,
            virtual_mode=True,
            env=shell_env,
            inherit_env=False,
        ),
        routes={
            "/.agent/": StateBackend(),
            "/memories/": StoreBackend(namespace=lambda _rt: ("memories",)),
            "/cwd/": FilesystemBackend(
                root_dir=str(config.project_root),
                virtual_mode=True,
            ),
            "/skills/": FilesystemBackend(
                root_dir=str(config.paths.skills_user_dir),
                virtual_mode=True,
            ),
            "/skills/project/": FilesystemBackend(
                root_dir=str(config.paths.skills_project_dir),
                virtual_mode=True,
            ),
        },
    )

    interrupt_on = None
    if config.security.require_approval:
        interrupt_on = {
            "execute": True,
            "write_file": True,
            "edit_file": True,
        }

    # Memory sources: all existing AGENTS.md files are injected
    memory_sources = [str(p) for p in config.agents_md_paths] or None

    return create_deep_agent(
        model=f"openrouter:{config.llm.model}",
        system_prompt=config.agent.system_prompt,
        backend=backend,
        skills=[
            "/skills/",
            "/skills/project/",
        ],
        tools=[
            fetch_page,
            *build_conversation_tools(chroma_store),
            *build_tavily_tools(config.tavily),
        ],
        memory=memory_sources,
        interrupt_on=interrupt_on,
        checkpointer=get_checkpointer(config),
        store=store,
    )
