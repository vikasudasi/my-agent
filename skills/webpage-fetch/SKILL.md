---
name: webpage-fetch
description: Fetch and read simple web pages using the fetch_page tool. Use when the user asks to view, read, load, open, check, or fetch a URL, link, website, webpage, or HTML page — or when they give you a URL and ask what it contains.
allowed-tools: fetch_page
---

# Webpage Fetch

A dedicated `fetch_page` tool wraps `httpx` to retrieve web pages as plain text. It strips HTML tags, scripts, and styles, and truncates output at ~8000 characters.

## When to use

- User gives you a URL and says "read this", "check this", "what's on this page", "open this link", etc.
- User asks for content from a specific website or article.
- User asks you to fetch a simple HTTP endpoint (REST API returning text/JSON).

**Do NOT use** when Tavily web search is more appropriate (e.g. user asks a research question — search is better than fetching a single page).

## Usage

Just call the `fetch_page` tool with the URL:

```
fetch_page(url="https://example.com/some-page")
```

Optionally adjust timeout:

```
fetch_page(url="https://slow-site.com/page", timeout=30)
```

## What it returns

- Plain text with HTML markup removed
- Truncated at 8000 characters with a note if longer
- Error messages for timeouts, HTTP errors, connection failures

## Limitations

- Does **not** execute JavaScript — single-page apps (React, Vue) may return minimal content
- Does **not** handle logins, cookies, or sessions
- Stripped HTML means you lose tables, lists, and layout structure
- For rich content or JS-rendered pages, suggest the user view it in a browser
