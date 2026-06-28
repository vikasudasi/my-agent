from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from my_agent.config import AppConfig

logger = logging.getLogger(__name__)


def _add_sync_support(tools: list[Any]) -> list[Any]:
    """Add sync invocation support to MCP tools that are async-only.

    ``langchain-mcp-adapters`` creates ``StructuredTool`` instances with only
    a ``coroutine`` (async function) and no ``func`` (sync function). When
    the agent calls these tools synchronously (via ``.invoke()``),
    ``StructuredTool._run()`` raises:

        NotImplementedError: StructuredTool does not support sync invocation.

    This function wraps each such tool's coroutine with ``asyncio.run()`` so
    it can be called synchronously.

    Args:
        tools: List of LangChain tool objects returned by ``load_mcp_tools``.

    Returns:
        The same list with sync ``func`` added to any ``StructuredTool``
        that had only a ``coroutine``.
    """
    for tool in tools:
        if not isinstance(tool, StructuredTool):
            continue
        if tool.func is not None:
            continue  # already has sync support
        if tool.coroutine is None:
            continue  # nothing to wrap

        coro = tool.coroutine

        def _sync_call(*args: Any, **kwargs: Any) -> Any:
            return asyncio.run(coro(*args, **kwargs))

        tool.func = _sync_call
        logger.debug("Added sync wrapper to MCP tool '%s'", tool.name)

    return tools


def load_mcp_tools(config: AppConfig) -> list[Any]:
    """Load tools from configured MCP servers.

    Connects to each MCP server defined in config.mcp.servers and
    returns a combined list of LangChain-compatible tools.

    Server failures are logged as warnings and skipped — the agent
    continues to work with whatever tools could be loaded.

    Returns:
        A list of LangChain tool objects (empty list if MCP is disabled
        or no servers are configured).
    """
    if not config.mcp.enabled or not config.mcp.servers:
        return []

    _SSE_TRANSPORTS = frozenset({"sse"})
    _HTTP_TRANSPORTS = frozenset({"http", "streamable_http", "streamable-http"})

    connections: dict[str, dict[str, Any]] = {}
    for server in config.mcp.servers:
        if server.transport == "stdio" and server.command:
            connections[server.name] = {
                "transport": "stdio",
                "command": server.command,
                "args": server.args or [],
            }
        elif server.transport in _SSE_TRANSPORTS and server.url:
            entry: dict[str, Any] = {
                "transport": "sse",
                "url": server.url,
            }
            if server.headers:
                entry["headers"] = server.headers
            connections[server.name] = entry
        elif server.transport in _HTTP_TRANSPORTS and server.url:
            entry: dict[str, Any] = {
                "transport": "streamable_http",
                "url": server.url,
            }
            if server.headers:
                entry["headers"] = server.headers
            connections[server.name] = entry
        elif server.transport == "websocket" and server.url:
            connections[server.name] = {
                "transport": "websocket",
                "url": server.url,
            }
        else:
            logger.warning(
                "MCP server '%s': unsupported transport '%s' or missing command/url",
                server.name,
                server.transport,
            )

    if not connections:
        return []

    client = MultiServerMCPClient(connections)
    try:
        tools = asyncio.run(client.get_tools())
        tools = _add_sync_support(tools)
        logger.info(
            "Loaded %d MCP tool(s) from %d server(s)",
            len(tools),
            len(connections),
        )
        return tools
    except Exception:
        logger.warning(
            "Failed to load MCP tools",
            exc_info=True,
        )
        return []
