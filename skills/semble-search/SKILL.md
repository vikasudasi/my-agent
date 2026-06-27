---
name: semble-search
description: "Search codebases using natural language with Semble. Uses ~98% fewer tokens than grep+read. Use when the user asks to search a codebase, find relevant code, understand how something works in a repo, or when traditional grep/file-reading would be expensive. Triggers: \"semble\", \"code search\", \"find in codebase\", \"search the repo\"."
allowed-tools: execute
---

# Semble Search

Search codebases with natural language queries using `semble`. Returns only the relevant code snippets — no full-file reads.

## Prerequisites

```bash
uv tool install semble
```

## CLI Commands

Semble has 3 subcommands visible in `semble --help`:

```
usage: semble [-h] {search,find-related,init} ...
```

Plus management commands (from README): `install`, `uninstall`, `savings`.

---

### `semble search` — Search a codebase

```
semble search [-h] [-k TOP_K] [-m {hybrid,semantic,bm25}] query [path]
```

| Argument/Option | Description | Default |
|----------------|-------------|---------|
| `query` | Natural language or code query | **required** |
| `path` | Local path or git URL | current directory |
| `-k`, `--top-k` | Number of results | 5 |
| `-m`, `--mode` | Search mode: `hybrid`, `semantic`, `bm25` | `hybrid` |
| `--content` | Source type: `code`, `docs`, `config`, `all` | `code` |
| `--ref` | Branch/tag to check out (git URLs only) | — |

**Examples:**
```bash
semble search "authentication flow"              # default: current dir, hybrid, top 5
semble search "CLI commands" ./ --top-k 3        # limit results
semble search "deployment guide" ./ --content docs  # search docs/markdown
semble search "database host" --content config      # search config files only
semble search "auth" ./ --content all               # code + docs + config
semble search "error handling" https://github.com/user/repo --ref main  # remote repo
semble search "save model" . --mode bm25         # BM25 keyword search
```

---

### `semble find-related` — Find code similar to a known location

```
semble find-related [-h] [-k TOP_K] file_path line [path]
```

Useful when refactoring or understanding patterns — takes a file+line from a search result and finds conceptually similar code.

| Argument/Option | Description | Default |
|----------------|-------------|---------|
| `file_path` | File path as shown in search results | **required** |
| `line` | Line number (1-indexed) | **required** |
| `path` | Local path or git URL | current directory |
| `-k`, `--top-k` | Number of results | 5 |

**Examples:**
```bash
semble find-related src/auth.py 42 ./
semble find-related src/main.py 10 ./ --top-k 3
```

---

### `semble init` — Write sub-agent file

```
semble init [-h] [--force]
```

Writes `.claude/agents/semble-search.md` for Claude Code sub-agent support. `--force` overwrites if the file already exists.

---

### Management commands

**Install / configure:**
```bash
semble install    # interactive setup — detects agents, enables MCP/instructions/sub-agent
semble uninstall  # removes all Semble integrations
```

**Token savings dashboard:**
```bash
semble savings
```
Shows: total tokens saved, total calls, efficiency ratio (%), breakdown by period (day/week/month/all) and by call type (search vs find_related).

**Cache location override:**
```bash
export SEMBLE_CACHE_LOCATION=~/my-custom-cache/semble
```
Default: `~/Library/Caches/semble/` (macOS), `~/.cache/semble/` (Linux), `%LOCALAPPDATA%\semble\Cache\` (Windows).

---

## MCP Server

`uvx --from "semble[mcp]" semble` (no subcommand = MCP mode)

The MCP server exposes `search_code` and `search_code_find_related` tools. Append `--content all` to index everything:
```bash
uvx --from "semble[mcp]" semble --content all
```

If `semble install` was run with MCP integration, the agent can call Semble directly as a tool.

### Per-agent MCP config

```bash
# Claude Code
claude mcp add semble -s user -- uvx --from "semble[mcp]" semble
```

```json
// Cursor — ~/.cursor/mcp.json or ./.cursor/mcp.json
{
  "mcpServers": {
    "semble": {
      "command": "uvx",
      "args": ["--from", "semble[mcp]", "semble"]
    }
  }
}
```

```json
// VS Code — .vscode/mcp.json
{
  "servers": {
    "semble": {
      "command": "uvx",
      "args": ["--from", "semble[mcp]", "semble"]
    }
  }
}
```

Supports: Claude Code, Cursor, Codex, OpenCode, VS Code, GitHub Copilot, Windsurf, Gemini CLI, Kiro, Zed, Reasonix, Pi, Command Code, Antigravity.

---

## Controlling what's indexed

- **`.gitignore`** — respected automatically
- **`.sembleignore`** — same syntax as gitignore, merged with `.gitignore`
  - Exclude: `generated/`, `*.pb.go`
  - Force-include non-default extensions: `!*.proto`, `!*.cob`
- Well-known non-source dirs (`node_modules/`, `.venv/`, `dist/`, `build/`, `__pycache__/`) are always skipped

## Index behavior

- Index is built and cached automatically on first search
- Invalidated automatically when files change
- Average: ~250 ms to index a repo, ~1.5 ms per query

## Edge cases

- **Semble not found on `$PATH`**: Use `uvx --from "semble[mcp]" semble` instead of `semble`
- **Large repos**: Index may take a few seconds on first run; subsequent searches are instant
- **New files**: Index auto-invalidates on file changes — no manual refresh needed
- **Binary/non-text files**: Skipped automatically
- **Upgrade**: `uv tool upgrade semble` then `uv cache clean semble` (restart MCP client after)  
- **Library usage**: Also usable as Python library — `from semble import SembleIndex, ContentType`

## When to use this vs grep

| Use Case | Tool |
|----------|------|
| "How is X implemented?" / "Find code that does Y" | `semble search` |
| "Find code similar to this function" | `semble find-related` |
| "Find every occurrence of literal string `foo`" | `grep` |
| "Search docs/prose about deployment" | `semble search --content docs` |
