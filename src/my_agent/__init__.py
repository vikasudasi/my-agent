"""Local macOS deep agent powered by LangChain Deep Agents."""

from __future__ import annotations

import warnings

# HuggingFace tokenizers uses Rust's Rayon for parallelism. When the process
# forks (e.g. via multiprocessing) after a tokenizer has already been loaded,
# the child inherits locks in an inconsistent state. HF disables parallelism
# in the child to avoid deadlocks and emits a warning about it. This warning
# is informational-only — tokenization still works (single-threaded in child
# processes). Suppress it to avoid noise in the terminal.
warnings.filterwarnings(
    "ignore",
    message=".*The current process just got forked, after parallelism has already been used.*",
)

__version__ = "0.1.0"
