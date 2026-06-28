"""Local macOS deep agent powered by LangChain Deep Agents."""

from __future__ import annotations

import os

# Setting this before any tokenizers import prevents HuggingFace tokenizers
# from enabling Rust/Rayon parallelism in the first place. When the process
# later forks (e.g. via ChromaDB's multiprocessing), there's no parallelism-in-
# progress to conflict with, so no warning is ever emitted. This is the standard
# fix used by transformers, haystack, and other HF-ecosystem projects.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

__version__ = "0.1.0"
