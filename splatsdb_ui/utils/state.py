# SPDX-License-Identifier: GPL-3.0
"""Shared application state — accessible from all views and mixins."""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

log = logging.getLogger(__name__)


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
    models_dir: Path = field(default_factory=lambda: Path("/mnt/d/models"))

    # Recent searches (persisted to disk, max 10)
    recent_searches: list = field(default_factory=list)
    _max_recent_searches: int = 10

    # ── Recent-search persistence ─────────────────────────────────

    @property
    def _searches_file(self) -> Path:
        return self.config_dir / "recent_searches.json"

    def add_recent_search(self, query: str) -> None:
        """Add *query* to the recent-searches list (deduped, capped at 10)."""
        query = query.strip()
        if not query:
            return
        # Remove duplicate if present, then prepend
        if query in self.recent_searches:
            self.recent_searches.remove(query)
        self.recent_searches.insert(0, query)
        # Cap at max
        self.recent_searches = self.recent_searches[: self._max_recent_searches]
        self.save_recent_searches()

    def save_recent_searches(self) -> None:
        """Persist recent searches to JSON on disk."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self._searches_file.write_text(
                json.dumps(self.recent_searches, indent=2, ensure_ascii=False)
            )
        except OSError:
            log.warning("Failed to save recent searches", exc_info=True)

    def load_recent_searches(self) -> None:
        """Load recent searches from JSON on disk (safe no-op on failure)."""
        try:
            if self._searches_file.exists():
                data = json.loads(self._searches_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    self.recent_searches = data[: self._max_recent_searches]
        except (OSError, json.JSONDecodeError):
            log.warning("Failed to load recent searches", exc_info=True)
            self.recent_searches = []
