# SPDX-License-Identifier: GPL-3.0
"""Shared application state — accessible from all views and mixins."""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class ConnectionState:
    """Backend connection state."""
    url: str = "http://127.0.0.1:8199"
    api_key: str = ""
    connected: bool = False
    version: str = ""


@dataclass
class EmbeddingState:
    """Current embedding model state."""
    active_model: str = ""
    available_models: list = field(default_factory=list)
    device: str = "auto"  # auto | cuda | cpu
    dimension: int = 0
    loading: bool = False


@dataclass
class OCRState:
    """OCR engine state."""
    engine: str = "auto"  # auto | tesseract | paddleocr
    language: str = "spa+eng"
    available: bool = False


@dataclass
class UIState:
    """UI preferences."""
    theme: str = "dark"
    sounds_enabled: bool = True
    font_size: int = 13
    param_panel_visible: bool = True
    bottom_panel_visible: bool = False


@dataclass
class AppState:
    """Root application state container."""
    connection: ConnectionState = field(default_factory=ConnectionState)
    embedding: EmbeddingState = field(default_factory=EmbeddingState)
    ocr: OCRState = field(default_factory=OCRState)
    ui: UIState = field(default_factory=UIState)

    # Current collection context
    current_collection: Optional[str] = None
    collections: list = field(default_factory=list)

    # Recent files / projects
    recent_files: list = field(default_factory=list)

    # Config file path
    config_dir: Path = field(default_factory=lambda: Path.home() / ".splatsdb-ui")
    models_dir: Path = field(default_factory=lambda: Path.home() / "models")
