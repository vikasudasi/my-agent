from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    LocalShellBackend,
    StateBackend,
    StoreBackend,
)
from deepagents.middleware.skills import SkillsMiddleware
from langchain.agents.middleware.types import AgentMiddleware
from langgraph.runtime import Runtime
from langchain_core.runnables import RunnableConfig
from my_agent.checkpoint import get_checkpointer
from my_agent.config import AppConfig, load_config
from my_agent.memory.chroma_store import ChromaConversationStore
from my_agent.middleware import SummarizationMiddleware
from my_agent.tools.conversation_memory import build_conversation_tools
from my_agent.tools.delegate_task import build_delegate_task_tool
from my_agent.tools.fetch_page import fetch_page
from my_agent.tools.mcp_tools import load_mcp_tools
from my_agent.store import get_store
from my_agent.tools.tavily_search import build_tavily_tools


class _RefreshSkillsMiddleware(AgentMiddleware):
    """Forces skills re-scan on every session start, even when --continue
    restores checkpointed state containing stale skills_metadata.

    SkillsMiddleware skips loading if 'skills_metadata' is already present
    in checkpointed state. This middleware clears that key before
    SkillsMiddleware's before_agent runs, ensuring newly added skills on
    disk are always picked up.
    """

    def before_agent(
        self, state: dict[str, Any], runtime: Runtime, config: RunnableConfig
    ) -> dict[str, Any] | None:
        if "skills_metadata" in state:
            return {"skills_metadata": []}
        return None

    async def abefore_agent(
        self, state: dict[str, Any], runtime: Runtime, config: RunnableConfig
    ) -> dict[str, Any] | None:
        return self.before_agent(state, runtime, config)


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


def create_delegate_agent(config_path: str | None = None):
    """Create a fresh agent for subagent delegation (no caching).

    Each call returns a new agent instance for isolated subagent execution.
    """
    config = load_config(config_path=Path(config_path) if config_path else None)
    chroma_store = ChromaConversationStore(config)
    return _create_agent(config, chroma_store), config, chroma_store


def _create_agent(config: AppConfig, chroma_store: ChromaConversationStore):
    home = str(config.project_root)
    shell_env = os.environ.copy()
    for path_entry in ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"):
        if path_entry not in shell_env.get("PATH", ""):
            shell_env["PATH"] = f"{path_entry}:{shell_env.get('PATH', '')}"

    store = get_store(config)

    routes: dict[str, Any] = {
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
    }
    if config.has_cwd_skills:
        routes["/skills/project/"] = FilesystemBackend(
            root_dir=str(config.paths.skills_project_dir),
            virtual_mode=True,
        )

    backend = CompositeBackend(
        default=LocalShellBackend(
            root_dir=home,
            virtual_mode=True,
            env=shell_env,
            inherit_env=False,
        ),
        routes=routes,
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

    # Build skills + summarization middleware stack
    middleware_stack: list[AgentMiddleware] = [
        _RefreshSkillsMiddleware(),
        SkillsMiddleware(
            backend=backend,
            sources=["/skills/", "/skills/project/"],
        ),
    ]

    summarization_mw = SummarizationMiddleware(
        config.summarization,
        config.llm.model,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
    )
    middleware_stack.append(summarization_mw)

    mcp_tools = load_mcp_tools(config)

    system_prompt = (
        config.agent.system_prompt
        + "\n\n"
        + config.build_backend_awareness()
    )

    return create_deep_agent(
        model=f"openrouter:{config.llm.model}",
        system_prompt=system_prompt,
        backend=backend,
        middleware=middleware_stack,
        tools=[
            fetch_page,
            build_delegate_task_tool(config, chroma_store),
            *build_conversation_tools(chroma_store),
            *build_tavily_tools(config.tavily),
            *mcp_tools,
        ],
        memory=memory_sources,
        interrupt_on=interrupt_on,
        checkpointer=get_checkpointer(config),
        store=store,
    )
