---
name: mcp-config
description: MCP (Model Context Protocol) server configuration for this agent. Teaches the agent how it can connect to external MCP servers, what transport types are supported, how servers are defined in config.toml, and how to help a user configure MCP when they share server details in chat. Triggers: "mcp", "mcp server", "configure mcp", "add mcp", "mcp tool", "connect to", "external tool", "config.toml", "mcp config", "model context protocol".
allowed-tools: read_file, write_file, edit_file, execute
---

# MCP (Model Context Protocol) Configuration

This agent supports **MCP (Model Context Protocol)** server integration via `langchain-mcp-adapters`. MCP servers expose additional tools that the agent can discover and use at runtime — think databases, APIs, file systems, or any service with an MCP interface.

## How it works

At agent startup, `load_mcp_tools()` in `src/my_agent/tools/mcp_tools.py` connects to each configured MCP server, discovers its available tools via the MCP protocol, and injects them into the agent's tool list alongside built-in tools (fetch_page, tavily_search, delegate_task, etc.).

```
config.toml  →  MCPServerConfig dataclasses  →  MultiServerMCPClient  →  tools[]
```

**Key behaviors:**
- Server failures are logged as warnings and **silently skipped** — the agent continues without them.
- MCP tool loading happens at agent startup, before any user interaction.
- MCP **does not** need to be restarted mid-session to pick up changes — a new agent session loads fresh config.
- The `mcp_tools.py` module uses `asyncio.run()` for the async MCP handshake since the agent creation chain is synchronous.
- If MCP is disabled (`[mcp] enabled = false`) or no servers are configured, the agent loads zero MCP tools (no error).

## Supported transports

| Transport | `transport` value in config | Use case |
|-----------|---------------------------|----------|
| **stdio** | `"stdio"` | Local subprocess — spawns a command (e.g. `npx`, `uvx`, `python`) that speaks MCP over stdin/stdout |
| **SSE** | `"sse"` | Remote server via Server-Sent Events (HTTP streaming) |
| **Streamable HTTP** | `"http"`, `"streamable_http"`, or `"streamable-http"` | Remote server via HTTP POST (can be simpler than SSE) |
| **WebSocket** | `"websocket"` | Remote server via WebSocket connection |

## Configuration location

MCP servers are defined in `config.toml`. The agent loads config from two locations (merged):

1. **Home config:** `~/.my-agent/config.toml` (shared across projects)
2. **Project config:** `./config.toml` (project-specific, overrides home)

Resolution order: `--config` CLI flag > `./config.toml` > `~/.my-agent/config.toml`

## Per-server configuration fields

Each server is defined as a `[[mcp.servers]]` TOML table. The fields map to the `MCPServerConfig` dataclass:

```python
@dataclass(frozen=True)
class MCPServerConfig:
    name: str                        # Unique server name (used as connection key)
    transport: str = "stdio"         # "stdio" | "sse" | "http" | "streamable_http" | "streamable-http" | "websocket"
    command: str | None = None       # For stdio: the executable (e.g. "npx", "uvx", "python")
    args: list[str] | None = None    # For stdio: CLI arguments
    url: str | None = None           # For SSE/HTTP/WebSocket: the server URL
    headers: dict[str, str] | None = None  # Optional HTTP headers for SSE/HTTP servers
```

## Quick-start examples

### 1. Local stdio server (most common)

```toml
[[mcp.servers]]
name = "my-local-server"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
```

### 2. Remote SSE server

```toml
[[mcp.servers]]
name = "my-remote-server"
transport = "sse"
url = "https://mcp.example.com/sse"
headers = { Authorization = "Bearer ${MY_API_TOKEN}" }
```

### 3. Streamable HTTP server

```toml
[[mcp.servers]]
name = "my-http-server"
transport = "http"
url = "https://api.example.com/mcp"
```

### 4. WebSocket server

```toml
[[mcp.servers]]
name = "my-ws-server"
transport = "websocket"
url = "wss://ws.example.com/mcp"
```

### 5. Multiple servers

```toml
[mcp]
enabled = true

[[mcp.servers]]
name = "db-server"
transport = "stdio"
command = "uvx"
args = ["mcp-database-server"]

[[mcp.servers]]
name = "api-server"
transport = "http"
url = "https://api.example.com/mcp"
```

## Environment variable interpolation

The config loader uses `${VAR_NAME}` syntax for environment variable substitution in config values. This avoids hardcoding secrets in `config.toml`.

```toml
[[mcp.servers]]
name = "secure-server"
transport = "sse"
url = "https://${MCP_HOST}/sse"
headers = { Authorization = "Bearer ${MCP_API_KEY}" }
```

The actual values are read from the process environment or `.env` files (loaded from `~/.my-agent/.env` and `./.env`).

## Disabling MCP

To disable MCP entirely without removing server definitions:

```toml
[mcp]
enabled = false
```

When disabled, `load_mcp_tools()` returns an empty list immediately.

## Example config.toml with MCP

```toml
[llm]
model = "deepseek/deepseek-v4-flash"
temperature = 0

# ... other config sections ...

[mcp]
enabled = true

[[mcp.servers]]
name = "filesystem"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]

[[mcp.servers]]
name = "github"
transport = "stdio"
command = "npx"
args = ["-y", "@modelcontextprotocol/server-github"]

[mcp.servers.headers]
Authorization = "Bearer ${GITHUB_TOKEN}"
```

> **Note:** The `[mcp.servers.headers]` inline table syntax works for shared headers. For per-server headers, use `{ key = "value" }` syntax shown in examples above.

## Source code reference

- **Config models:** `src/my_agent/config.py` — `MCPServerConfig`, `MCPConfig` dataclasses
- **Tool loader:** `src/my_agent/tools/mcp_tools.py` — `load_mcp_tools()` function
- **Integration point:** `src/my_agent/agent.py` — calls `load_mcp_tools()` and spreads results into tools list
- **Client library:** `langchain_mcp_adapters.client.MultiServerMCPClient`

## When a user shares MCP server details in chat

When a user says "I have an MCP server running at ..." or gives you MCP configuration details:

1. **Check current config** — Read `~/.my-agent/config.toml` and `./config.toml` to see what's already configured.
2. **Determine the transport** from what the user describes:
   - "I run `npx ...`" → stdio (need command + args)
   - "It's at http://..." or "SSE endpoint" → SSE/HTTP (need url)
   - "WebSocket at ws://..." → websocket (need url)
3. **Ask for missing fields** — not all users provide complete config. Ask specifically:
   - For stdio: "What command do I run? What arguments?"
   - For URL-based: "What's the URL? Any authentication headers?"
4. **Write the config** — Add a `[[mcp.servers]]` section to the appropriate `config.toml`.
   - Prefer `~/.my-agent/config.toml` for user-wide servers.
   - Prefer `./config.toml` for project-specific servers.
5. **Tell the user** they need to restart the agent for changes to take effect (MCP tools are loaded at startup only).
6. **For sensitive values** (API keys, tokens), suggest environment variables with `${VAR}` syntax so secrets stay out of config files.