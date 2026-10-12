# SPDX-License-Identifier: GPL-3.0
"""Global status bar — connection indicator, DB stats, last action.

Sections (left-to-right):
  ● Connected / Disconnected   |   Engine preset   |   DB stats (docs, entities)
  Last action (right-aligned)   |   GPU info
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import QStatusBar, QLabel, QWidget, QHBoxLayout, QFrame
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class _DotLabel(QLabel):
    """A small coloured circle (8×8) used as a connection indicator."""

    _pixmap_cache: dict[str, QPixmap] = {}

    def __init__(self):
        super().__init__()
        self.setFixedSize(10, 10)
        self._color = Colors.TEXT_MUTED
        # Pre-cache pixmaps for the 4 status colors
        for color in (Colors.SUCCESS, Colors.ERROR, Colors.WARNING, Colors.TEXT_MUTED):
            if color not in _DotLabel._pixmap_cache:
                _DotLabel._pixmap_cache[color] = self._create_pixmap(color)
        self._update_pixmap()

    @staticmethod
    def _create_pixmap(color: str) -> QPixmap:
        pm = QPixmap(10, 10)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, 8, 8)
        p.end()
        return pm

    def set_color(self, color: str):
        if color != self._color:
            self._color = color
            self._update_pixmap()

    def _update_pixmap(self):
        if self._color not in _DotLabel._pixmap_cache:
            _DotLabel._pixmap_cache[self._color] = self._create_pixmap(self._color)
        self.setPixmap(_DotLabel._pixmap_cache[self._color])


class SplatsDBStatusBar(QStatusBar):
    """Enhanced global status bar with connection, DB stats, and last action."""

    def __init__(self):
        super().__init__()
        self._last_action_text: str = ""
        self._last_action_time: Optional[datetime] = None
        self._connected: bool = False
        self._doc_count: int = 0
        self._entity_count: int = 0

        self._build_ui()

        # Timer to update relative timestamps every 30 s
        self._ts_timer = QTimer(self)
        self._ts_timer.timeout.connect(self._refresh_last_action)
        self._ts_timer.start(30_000)

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self):
        # Connection indicator: coloured dot + text
        self.conn_dot = _DotLabel()
        self.addWidget(self.conn_dot)

        self.conn_label = QLabel("Disconnected")
        self.conn_label.setAccessibleName("Connection Status")
        self.conn_label.setAccessibleDescription("Shows whether the application is connected to a database")
        self.conn_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px; margin-left: 2px;")
        self.addWidget(self.conn_label)

        self._sep()

        # Engine / model name
        self.model_icon = QLabel()
        self.model_icon.setPixmap(icon("cpu", Colors.TEXT_DIM, 14).pixmap(14, 14))
        self.addWidget(self.model_icon)

        self.model_label = QLabel("No engine")
        self.model_label.setAccessibleName("Engine")
        self.model_label.setAccessibleDescription("Current embedding engine or model preset")
        self.model_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        self.addWidget(self.model_label)

        self._sep()

        # DB stats: document count + entity count
        self.stats_icon = QLabel()
        self.stats_icon.setPixmap(icon("database", Colors.TEXT_DIM, 14).pixmap(14, 14))
        self.addWidget(self.stats_icon)

        self.stats_label = QLabel("0 docs · 0 entities")
        self.stats_label.setAccessibleName("Database Statistics")
        self.stats_label.setAccessibleDescription("Number of documents and entities in the database")
        self.stats_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        self.addWidget(self.stats_label)

        self._sep()

        # Last action (permanent — right side but before GPU)
        self.action_sep = QFrame()
        self.action_sep.setFrameShape(QFrame.VLine)
        self.action_sep.setFrameShadow(QFrame.Sunken)
        self.action_sep.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none; background: {Colors.TEXT_MUTED}; max-width: 1px; margin: 0 6px;")
        self.addPermanentWidget(self.action_sep)

        self.action_icon = QLabel()
        self.action_icon.setPixmap(icon("clock", Colors.TEXT_DIM, 14).pixmap(14, 14))
        self.addPermanentWidget(self.action_icon)

        self.action_label = QLabel("No actions yet")
        self.action_label.setAccessibleName("Last Action")
        self.action_label.setAccessibleDescription("Description and time of the last user action")
        self.action_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        self.addPermanentWidget(self.action_label)

        self._sep_permanent = QFrame()
        self._sep_permanent.setFrameShape(QFrame.VLine)
        self._sep_permanent.setFrameShadow(QFrame.Sunken)
        self._sep_permanent.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none; background: {Colors.TEXT_MUTED}; max-width: 1px; margin: 0 6px;")
        self.addPermanentWidget(self._sep_permanent)

        # GPU (permanent — far right)
        self.gpu_icon = QLabel()
        self.gpu_icon.setPixmap(icon("zap", Colors.TEXT_DIM, 14).pixmap(14, 14))
        self.addPermanentWidget(self.gpu_icon)

        self.gpu_label = QLabel("CPU")
        self.gpu_label.setAccessibleName("GPU Info")
        self.gpu_label.setAccessibleDescription("Current GPU or compute device information")
        self.gpu_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        self.addPermanentWidget(self.gpu_label)

    def _sep(self):
        s = QFrame()
        s.setFrameShape(QFrame.VLine)
        s.setFrameShadow(QFrame.Sunken)
        s.setStyleSheet(f"color: {Colors.TEXT_MUTED}; border: none; background: {Colors.TEXT_MUTED}; max-width: 1px; margin: 0 6px;")
        self.addWidget(s)

    # ── Public API ───────────────────────────────────────────────

    def set_connected(self, connected: bool, preset: str = ""):
        """Update connection indicator with coloured dot."""
        self._connected = connected
        if connected:
            self.conn_dot.set_color(Colors.SUCCESS)
            self.conn_label.setText("Connected")
            self.conn_label.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 11px; margin-left: 2px;")
        else:
            self.conn_dot.set_color(Colors.ERROR)
            self.conn_label.setText("Disconnected")
            self.conn_label.setStyleSheet(f"color: {Colors.ERROR}; font-size: 11px; margin-left: 2px;")

        if preset:
            self.model_label.setText(preset)
            self.model_label.setStyleSheet(f"color: {Colors.TEXT}; font-size: 11px;")

    def set_model(self, name: str):
        self.model_label.setText(name or "No engine")

    def set_doc_count(self, count: int):
        """Set document / vector count."""
        self._doc_count = count
        self._update_stats()

    def set_entity_count(self, count: int):
        """Set entity count."""
        self._entity_count = count
        self._update_stats()

    def set_db_stats(self, doc_count: int = 0, entity_count: int = 0):
        """Update both document and entity counts at once."""
        self._doc_count = doc_count
        self._entity_count = entity_count
        self._update_stats()

    def set_last_action(self, description: str):
        """Record the last user action with a timestamp."""
        self._last_action_text = description
        self._last_action_time = datetime.now()
        self._refresh_last_action()

    def set_gpu(self, info: str):
        self.gpu_label.setText(info)

    def show_message(self, msg: str, timeout: int = 4000):
        self.showMessage(msg, timeout)
        # Record as last action (only updates if not already set this call)
        if msg and len(msg) < 80:
            self._last_action_text = msg
            self._last_action_time = datetime.now()
            self._refresh_last_action()

    # ── Internal helpers ─────────────────────────────────────────

    def _update_stats(self):
        if self._doc_count == 0 and self._entity_count == 0:
            self.stats_label.setText("—")
            return
        parts = []
        if self._doc_count:
            parts.append(f"{self._doc_count:,} docs")
        else:
            parts.append("0 docs")
        parts.append(f"{self._entity_count:,} entities")
        self.stats_label.setText(" · ".join(parts))

    def _refresh_last_action(self):
        """Update the last-action label with relative time."""
        if not self._last_action_text or not self._last_action_time:
            return

        delta = datetime.now() - self._last_action_time
        seconds = int(delta.total_seconds())

        if seconds < 5:
            ago = "just now"
        elif seconds < 60:
            ago = f"{seconds}s ago"
        elif seconds < 3600:
            ago = f"{seconds // 60}m ago"
        elif seconds < 86400:
            ago = f"{seconds // 3600}h ago"
        else:
            ago = self._last_action_time.strftime("%H:%M")

        self.action_label.setText(f"{self._last_action_text} — {ago}")
        self.action_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
