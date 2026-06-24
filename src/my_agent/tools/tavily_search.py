from __future__ import annotations

import os

from langchain_tavily import TavilySearch

from my_agent.config import TavilyConfig


def build_tavily_tools(config: TavilyConfig | None = None) -> list:
    """Return Tavily search tools when TAVILY_API_KEY is configured."""
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []

    settings = config or TavilyConfig()
    tool = TavilySearch(
        max_results=settings.max_results,
        topic=settings.topic,
        search_depth=settings.search_depth,
        include_answer=settings.include_answer,
        include_raw_content=settings.include_raw_content,
    )
    return [tool]
