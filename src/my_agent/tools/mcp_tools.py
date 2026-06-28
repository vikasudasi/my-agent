from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Any

import httpx
from langchain_core.tools import StructuredTool, ToolException
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp.client.streamable_http import create_mcp_http_client

from my_agent.config import AppConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keep-alive fix: the MCP server closes TCP connections after each response.
# The MCP SDK's StreamableHTTPTransport reuses the httpx connection pool, so
# the second POST in a session fails with httpx.ReadError.
#
# We inject a custom httpx_client_factory that sets max_keepalive=0 on the
# connection pool, forcing a fresh TCP connection per POST.
# ---------------------------------------------------------------------------


def _make_no_keepalive_client(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """Return an ``httpx.AsyncClient`` that never reuses TCP connections.

    Each POST (initialize, tool call) opens a new connection, avoiding the
    ``httpx.ReadError`` that occurs when the server silently closes the
    connection after the first response.
    """
    client = create_mcp_http_client(headers, timeout, auth)
    pool = client._transport._pool
    pool._max_keepalive_connections = 0
    pool._keepalive_expiry = 0.0
    return client


# ---------------------------------------------------------------------------
# Connection builder
# ---------------------------------------------------------------------------

_SERVER_NAME_PREFIX = "mcp"


def _build_connections(config: AppConfig) -> dict[str, dict[str, Any]]:
    """Build the ``connections`` dict for ``MultiServerMCPClient``.

    Each server entry receives the custom ``httpx_client_factory`` so that
    the keep-alive fix applies to every session.
    """
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
                "httpx_client_factory": _make_no_keepalive_client,
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

    return connections


def _add_sync_support(tools: list[Any]) -> list[Any]:
    """Add sync invocation support to MCP tools that are async-only.

    ``langchain-mcp-adapters`` creates ``StructuredTool`` instances with only
    a ``coroutine`` (async function) and no ``func`` (sync function). When
    the agent calls these tools synchronously (via ``.invoke()``),
    ``StructuredTool._run()`` raises:

        NotImplementedError: StructuredTool does not support sync invocation.

    This function wraps each such tool's coroutine so it can be called
    synchronously. It handles two cases:

    1. **No running event loop** — uses ``asyncio.run()`` directly.
    2. **Already inside a running event loop** — runs the coroutine in a
       dedicated thread with a fresh event loop.

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
        tool_name = tool.name  # capture eagerly to avoid closure late-binding

        def _make_sync_call(tool_coro: Any, name: str) -> Any:
            def _sync_call(*args: Any, **kwargs: Any) -> Any:
                try:
                    # If no event loop is running, plain asyncio.run() works fine
                    asyncio.get_running_loop()
                    # A loop IS running — run coroutine in a separate thread
                    # with its own event loop.
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(asyncio.run, tool_coro(*args, **kwargs))
                        return future.result()
                except RuntimeError:
                    # No running event loop — plain asyncio.run is safe
                    try:
                        return asyncio.run(tool_coro(*args, **kwargs))
                    except ToolException as e:
                        logger.error("MCP tool '%s' failed: %s", name, e)
                        return _error_result(name, str(e))
                    except Exception as e:
                        logger.error(
                            "MCP tool '%s' raised unexpected error: %s",
                            name,
                            e,
                        )
                        return _error_result(name, str(e))
                except ToolException as e:
                    logger.error("MCP tool '%s' failed: %s", name, e)
                    return _error_result(name, str(e))
                except Exception as e:
                    logger.error(
                        "MCP tool '%s' raised unexpected error: %s",
                        name,
                        e,
                    )
                    return _error_result(name, str(e))

            return _sync_call

        tool.func = _make_sync_call(coro, tool_name)
        tool.handle_tool_error = True
        logger.debug("Added sync wrapper to MCP tool '%s'", tool_name)

    return tools


def _error_result(tool_name: str, message: str) -> tuple[str, None]:
    """Return a standardized error tuple for ``response_format='content_and_artifact'``."""
    return (
        f"MCP tool '{tool_name}' failed: {message}",
        None,
    )


def load_mcp_tools(config: AppConfig) -> list[Any]:
    """Load tools from configured MCP servers.

    Connects to each MCP server defined in config.mcp.servers and
    returns a combined list of LangChain-compatible tools.

    Each tool call runs in its own session with a fresh TCP connection
    (the keep-alive fix avoids ``httpx.ReadError`` on connection reuse).

    Server failures are logged as warnings and skipped — the agent
    continues to work with whatever tools could be loaded.

    Returns:
        A list of LangChain tool objects (empty list if MCP is disabled
        or no servers are configured).
    """
    if not config.mcp.enabled or not config.mcp.servers:
        return []

    connections = _build_connections(config)
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
