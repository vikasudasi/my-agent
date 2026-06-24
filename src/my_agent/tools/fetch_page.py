from __future__ import annotations

import httpx
from langchain_core.tools import tool


@tool
def fetch_page(url: str, timeout: int = 15) -> str:
    """Fetch the text content of a simple web page. Use when the user asks to read, view, or fetch a URL, webpage, or website.

    Args:
        url: The full URL to fetch (e.g. https://example.com/page).
        timeout: Request timeout in seconds (default 15).

    Returns:
        The page content as plain text (up to ~8000 chars).
    """
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            text = resp.text

            if "text/html" in content_type:
                import re
                text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
                text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()

            max_chars = 8000
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n... [truncated: {len(text)} total chars]"

            return text

    except httpx.TimeoutException:
        return f"Error: Request to {url} timed out after {timeout}s."
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} fetching {url}."
    except Exception as e:
        return f"Error fetching {url}: {type(e).__name__}: {e}"
