# SPDX-License-Identifier: GPL-3.0
"""Model registry — discovers and manages available embedding models."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from splatsdb_ui.embeddings.engine import ModelInfo, EmbeddingEngine


# ── Well-known models ───────────────────────────────────────────────

KNOWN_MODELS = {
    # ── Primary: BAAI/bge-m3 — matches SplatDB v2.6.0 default (1024d) ──
    "bge-m3": ModelInfo(
        name="bge-m3",
        display_name="BGE-M3 (1024D, multilingual — SplatDB default)",
        dimension=1024,
        provider="sentence",
        path="BAAI/bge-m3",
        size_gb=2.4,
    ),
    "llama-embed-nemotron-8b": ModelInfo(
        name="llama-embed-nemotron-8b",
        display_name="LLaMA-Embed Nemotron 8B (NVIDIA)",
        dimension=4096,
        provider="nemotron",
        path="llama-embed-nemotron-8b",
        size_gb=16.0,
    ),
    "all-MiniLM-L6-v2": ModelInfo(
        name="all-MiniLM-L6-v2",
        display_name="MiniLM L6 v2 (384D, fast)",
        dimension=384,
        provider="sentence",
        path="all-MiniLM-L6-v2",
        size_gb=0.09,
    ),
    "bge-small-en-v1.5": ModelInfo(
        name="bge-small-en-v1.5",
        display_name="BGE Small EN v1.5 (384D)",
        dimension=384,
        provider="sentence",
        path="BAAI/bge-small-en-v1.5",
        size_gb=0.13,
    ),
    "gte-small": ModelInfo(
        name="gte-small",
        display_name="GTE Small (384D)",
        dimension=384,
        provider="sentence",
        path="thenlper/gte-small",
        size_gb=0.13,
    ),
}


def create_engine(
    models_dir: str = "",
    config_path: Optional[str] = None,
) -> EmbeddingEngine:
    """Create and configure the embedding engine with discovered models."""
    engine = EmbeddingEngine(models_dir=models_dir)

    # Register known models if they exist locally
    for name, info in KNOWN_MODELS.items():
        if info.path and Path(info.path).exists():
            engine.register_model(info)

    # Auto-discover any other models in models_dir
    engine.auto_discover()

    # Load custom model registrations from config
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            cfg = json.load(f)
        for model_cfg in cfg.get("models", []):
            info = ModelInfo(**model_cfg)
            engine.register_model(info)

    return engine
