from __future__ import annotations

from unittest.mock import patch

import pytest

from my_agent.tools.mcp_tools import load_mcp_tools


class TestLoadMCPTools:
    """load_mcp_tools handles server config and failures gracefully."""

    def test_returns_empty_when_mcp_disabled(self) -> None:
        config = _make_config(enabled=False)
        assert load_mcp_tools(config) == []

    def test_returns_empty_when_no_servers(self) -> None:
        config = _make_config(enabled=True, servers=())
        assert load_mcp_tools(config) == []

    def test_returns_empty_when_all_connections_fail(self) -> None:
        config = _make_config(
            enabled=True,
            servers=(
                _server(
                    name="bad",
                    transport="stdio",
                    command="nonexistent-binary",
                    args=[],
                ),
            ),
        )
        with patch("my_agent.tools.mcp_tools.logger") as mock_logger:
            result = load_mcp_tools(config)
            assert result == []
            mock_logger.warning.assert_any_call(
                "Failed to load MCP tools", exc_info=True
            )


class TestTransportTranslation:
    """Each transport type produces the correct connection dict."""

    def test_stdio(self) -> None:
        config = _make_config(
            enabled=True,
            servers=(_server("srv", "stdio", command="npx", args=["-y", "srv"]),),
        )
        with _patch_client() as mock_client:
            load_mcp_tools(config)
        mock_client.assert_called_once_with({
            "srv": {"transport": "stdio", "command": "npx", "args": ["-y", "srv"]}
        })

    def test_sse(self) -> None:
        config = _make_config(
            enabled=True,
            servers=(
                _server(
                    "srv",
                    transport="sse",
                    url="http://localhost:8000/mcp/sse",
                    headers={"Authorization": "Bearer tok"},
                ),
            ),
        )
        with _patch_client() as mock_client:
            load_mcp_tools(config)
        mock_client.assert_called_once_with({
            "srv": {
                "transport": "sse",
                "url": "http://localhost:8000/mcp/sse",
                "headers": {"Authorization": "Bearer tok"},
            }
        })

    def test_sse_without_headers(self) -> None:
        config = _make_config(
            enabled=True,
            servers=(_server("srv", transport="sse", url="http://localhost:8000/sse"),),
        )
        with _patch_client() as mock_client:
            load_mcp_tools(config)
        mock_client.assert_called_once_with({
            "srv": {"transport": "sse", "url": "http://localhost:8000/sse"}
        })

    @pytest.mark.parametrize(
        "transport_alias",
        ["http", "streamable_http", "streamable-http"],
    )
    def test_http_aliases(self, transport_alias: str) -> None:
        config = _make_config(
            enabled=True,
            servers=(
                _server(
                    "srv",
                    transport=transport_alias,
                    url="http://localhost:8000/mcp",
                    headers={"Authorization": "Bearer tok"},
                ),
            ),
        )
        with _patch_client() as mock_client:
            load_mcp_tools(config)
        mock_client.assert_called_once_with({
            "srv": {
                "transport": "streamable_http",
                "url": "http://localhost:8000/mcp",
                "headers": {"Authorization": "Bearer tok"},
            }
        })

    def test_websocket(self) -> None:
        config = _make_config(
            enabled=True,
            servers=(_server("srv", transport="websocket", url="ws://localhost:8000/mcp"),),
        )
        with _patch_client() as mock_client:
            load_mcp_tools(config)
        mock_client.assert_called_once_with({
            "srv": {"transport": "websocket", "url": "ws://localhost:8000/mcp"}
        })

    def test_unsupported_transport_is_skipped(self) -> None:
        config = _make_config(
            enabled=True,
            servers=(
                _server("good", transport="stdio", command="npx", args=["srv"]),
                _server("bad", transport="grpc", url="http://x"),
            ),
        )
        with _patch_client() as mock_client:
            load_mcp_tools(config)
        mock_client.assert_called_once_with({
            "good": {"transport": "stdio", "command": "npx", "args": ["srv"]}
        })


def _make_config(*, enabled: bool, servers=()) -> object:
    """Build a fake AppConfig-like object with just the MCP fields we need."""

    class _FakeMCP:
        def __init__(self) -> None:
            self.enabled = enabled
            self.servers = servers

    class _FakeConfig:
        def __init__(self) -> None:
            self.mcp = _FakeMCP()

    return _FakeConfig()


def _server(
    name: str,
    transport: str = "stdio",
    command: str | None = None,
    args: list[str] | None = None,
    url: str | None = None,
    headers: dict[str, str] | None = None,
) -> object:
    """Build a fake MCPServerConfig-like object."""
    from types import SimpleNamespace

    return SimpleNamespace(
        name=name,
        transport=transport,
        command=command,
        args=args,
        url=url,
        headers=headers,
    )


def _patch_client():
    """Patch MultiServerMCPClient so we can inspect its connection dict."""
    return patch(
        "my_agent.tools.mcp_tools.MultiServerMCPClient",
        autospec=True,
    )
