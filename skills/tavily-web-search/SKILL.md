---
name: tavily-web-search
description: Search the live web with Tavily for current events, documentation, prices, news, and facts not in local files or memory. Use when the user asks to look something up online, verify recent information, compare sources, or when local context is insufficient.
allowed-tools: tavily_search
---

# Tavily Web Search

## When to use

Use `tavily_search` when:

- The user asks for current or external information (news, releases, prices, weather, docs).
- Local files, shell output, or `search_past_conversations` do not answer the question.
- You need to verify a fact, find official documentation, or cite web sources.

Prefer local tools first when the answer is likely on disk or in prior threads.

## Tool

The agent exposes `tavily_search` (LangChain `TavilySearch`). It requires `TAVILY_API_KEY` in `.env`.

Default settings come from `config.toml` `[tavily]`:

- `max_results` (default 5)
- `topic`: `general`, `news`, or `finance`
- `search_depth`: `basic`, `advanced`, `fast`, or `ultra-fast`
- `include_answer` / `include_raw_content`: set at config time only

## Query workflow

1. Write a focused natural-language query (under ~400 characters).
2. Call `tavily_search` with `query` and optional invocation overrides:
   - `search_depth`: use `advanced` for niche or multi-hop topics; `fast`/`ultra-fast` for quick facts.
   - `time_range`: `day`, `week`, `month`, or `year` when recency matters.
   - `include_domains` / `exclude_domains`: when the user names specific sites or sources to include/avoid.
   - `topic`: `news` for breaking stories; `finance` for markets and earnings.
3. Read `results` (title, url, content, score). Prefer higher scores and authoritative domains.
4. Summarize for the user with source links. Say when results conflict or are thin.

## Examples

**Recent news**

```
tavily_search(query="latest macOS security updates", time_range="month", topic="news")
```

**Official docs only**

```
tavily_search(query="LangGraph checkpointer API", include_domains=["langchain.com", "python.langchain.com"])
```

**Deep technical lookup**

```
tavily_search(query="ChromaDB persistent client embedding function", search_depth="advanced")
```

## Edge cases

- Missing `TAVILY_API_KEY`: tell the user to add it to `.env` (see `.env.example`).
- Empty or low-quality results: broaden the query, switch `search_depth` to `advanced`, or remove domain filters.
- Time-sensitive answers: include today's date in the query or use `time_range`.
- Do not treat search snippets as ground truth for security, medical, or legal advice without cross-checking sources.
