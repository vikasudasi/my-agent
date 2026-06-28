from __future__ import annotations

import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

from my_agent.config import AppConfig

logger = logging.getLogger(__name__)


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
        # Using asyncio.run() since the agent creation chain is synchronous
        import asyncio

        tools = asyncio.run(client.get_tools())
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
