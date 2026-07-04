from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from my_agent.config import _build_system_prompt, load_config


class TestBuildSystemPrompt:
    """_build_system_prompt combines home and cwd AGENTS.md content."""

    def test_configured_prompt_takes_precedence(self) -> None:
        result = _build_system_prompt(
            "Explicit system prompt.",
            "home content",
            "cwd content",
        )
        assert result == "Explicit system prompt."

    def test_combines_home_and_cwd(self) -> None:
        result = _build_system_prompt("", "home rules", "cwd rules")
        assert "home rules" in result
        assert "cwd rules" in result

    def test_fallback_when_no_content(self) -> None:
        result = _build_system_prompt("", None, None)
        assert result == "You are a helpful personal macOS assistant."

    def test_deduplicates_identical_content(self) -> None:
        result = _build_system_prompt("", "same content", "same content")
        assert result.count("same content") == 1


class TestLoadConfig:
    """load_config resolves configuration from disk."""

    def test_raises_when_nonexistent_config_path(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nonexistent.toml"
        with pytest.raises(FileNotFoundError, match="No such file or directory"):
            load_config(config_path=nonexistent)

    def test_raises_without_api_key(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[llm]\nmodel = "test-model"\n')

        # Real ~/.my-agent/.env may set OPENROUTER_API_KEY; isolate the test
        with patch("my_agent.config.load_dotenv", return_value=None):
            with patch.dict("os.environ", {}, clear=True):
                with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
                    load_config(config_path=config_file)

    def test_parses_voice_section(self, tmp_path: Path) -> None:
        from my_agent.config import VoiceConfig

        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[llm]
model = "test-model"

[voice]
enabled = true
model = "openai/whisper-1"
language = "en"
max_duration_seconds = 45
confirm_before_send = false
"""
        )
        with patch("my_agent.config.load_dotenv", return_value=None):
            with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}):
                config = load_config(config_path=config_file)

        assert config.voice == VoiceConfig(
            enabled=True,
            model="openai/whisper-1",
            language="en",
            max_duration_seconds=45.0,
            confirm_before_send=False,
        )


class TestExpandsUserPaths:
    """Path expansion in load_config handles ~ and relative paths."""

    def test_expand_home(self, tmp_path: Path) -> None:
        from my_agent.config import _expand_path

        result = _expand_path("~/some-dir", tmp_path)
        assert result.is_absolute()
        assert "some-dir" in result.parts


class TestMCPConfig:
    """MCP server config parsing and defaults."""

    def test_defaults_disabled_when_no_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text('[llm]\nmodel = "test-model"\n')
        from my_agent.config import MCPConfig, MCPServerConfig

        assert MCPConfig().enabled is True
        assert MCPConfig().servers == ()

    def test_parses_single_stdio_server(self) -> None:
        from my_agent.config import MCPServerConfig

        server = MCPServerConfig(
            name="math",
            transport="stdio",
            command="python",
            args=["/path/to/server.py"],
        )
        assert server.name == "math"
        assert server.transport == "stdio"
        assert server.command == "python"
        assert server.args == ["/path/to/server.py"]

    def test_parses_http_server_with_headers(self) -> None:
        from my_agent.config import MCPServerConfig

        server = MCPServerConfig(
            name="weather",
            transport="http",
            url="http://localhost:8000/mcp",
            headers={"Authorization": "Bearer token123"},
        )
        assert server.transport == "http"
        assert server.url == "http://localhost:8000/mcp"
        assert server.headers == {"Authorization": "Bearer token123"}


class TestMessageText:
    """Utility for extracting text from messages."""

    def test_extracts_plain_string(self) -> None:
        from my_agent.messages import message_text

        class FakeMessage:
            content = "Hello world"

        assert message_text(FakeMessage()) == "Hello world"

    def test_extracts_text_blocks(self) -> None:
        from my_agent.messages import message_text

        class FakeMessage:
            content = [{"type": "text", "text": "Hello"}, {"type": "text", "text": "world"}]

        assert message_text(FakeMessage()) == "Hello\nworld"

    def test_handles_empty_content(self) -> None:
        from my_agent.messages import message_text

        class FakeMessage:
            content = ""

        assert message_text(FakeMessage()) == ""

    def test_handles_unknown_type(self) -> None:
        from my_agent.messages import message_text

        class FakeMessage:
            content = 42

        assert message_text(FakeMessage()) == "42"


class TestMCPInterpolation:
    """MCP config values support ${ENV_VAR} substitution."""

    def test_interpolates_header_values(self) -> None:
        from my_agent.config import _parse_mcp_server

        with patch.dict("os.environ", {"MCP_TOKEN": "secret-token"}):
            server = _parse_mcp_server(
                {
                    "name": "weather",
                    "transport": "http",
                    "url": "http://localhost:8000/mcp",
                    "headers": {"Authorization": "Bearer ${MCP_TOKEN}"},
                }
            )

        assert server.headers == {"Authorization": "Bearer secret-token"}

    def test_leaves_missing_env_vars_unchanged(self) -> None:
        from my_agent.config import _interpolate_env

        with patch.dict("os.environ", {}, clear=True):
            assert _interpolate_env("Bearer ${MISSING_VAR}") == "Bearer ${MISSING_VAR}"