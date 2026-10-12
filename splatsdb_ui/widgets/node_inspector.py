# SPDX-License-Identifier: GPL-3.0
"""Node Inspector — full node audit panel.

Shows: metadata, raw vector, connections table, attached files.
Splitter layout: Inspector (left) | File Preview (right).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSplitter, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QTableWidget, QTableWidgetItem,
    QSizePolicy, QApplication,
)
from PySide6.QtCore import Signal, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QPainter, QColor, QLinearGradient

from splatsdb_ui.utils.widgets import clearLayout
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class NodeInspector(QWidget):
    """Full audit panel for a selected node."""

    navigate_to_node = Signal(str)          # navigate to another node
    open_file_requested = Signal(str)       # open file externally
    preview_file_requested = Signal(str)    # preview file in widget

    def __init__(self):
        super().__init__()
        self.setMinimumWidth(360)
        self._current_node: Optional[dict] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QHBoxLayout()
        header.setContentsMargins(12, 10, 12, 10)

        lbl = QLabel("NODE INSPECTOR")
        lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        header.addWidget(lbl)
        header.addStretch()

        self.close_btn = QPushButton()
        self.close_btn.setIcon(icon("cross", Colors.TEXT_DIM))
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: #21262d; border-radius: 4px; }")
        header.addWidget(self.close_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        header_widget.setStyleSheet(f"background-color: {Colors.BG_RAISED}; border-bottom: 1px solid {Colors.BORDER};")
        layout.addWidget(header_widget)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(14, 12, 14, 12)
        self.content_layout.setSpacing(16)

        # --- ID Section ---
        self.id_section = self._section("Identity")

        # Color swatch + ID row
        id_row = QHBoxLayout()
        self._color_swatch = QLabel()
        self._color_swatch.setFixedSize(20, 20)
        self._color_swatch.setStyleSheet(
            f"background: {Colors.BORDER}; border-radius: 10px; border: 2px solid {Colors.BORDER};"
        )
        id_row.addWidget(self._color_swatch)

        self.id_label = QLabel("No node selected")
        self.id_label.setWordWrap(True)
        self.id_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.id_label.setStyleSheet(f"color: {Colors.TEXT}; font-size: 12px; font-family: monospace;")
        id_row.addWidget(self.id_label, stretch=1)

        self._copy_id_btn = QPushButton()
        self._copy_id_btn.setIcon(icon("copy", Colors.TEXT))
        self._copy_id_btn.setFixedSize(28, 28)
        self._copy_id_btn.setToolTip("Copy node ID")
        self._copy_id_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 4px; }}"
            f"QPushButton:hover {{ border-color: {Colors.ACCENT}; }}"
        )
        self._copy_id_btn.clicked.connect(self._copy_id)
        id_row.addWidget(self._copy_id_btn)

        self.id_section.layout().addLayout(id_row)
        self.content_layout.addWidget(self.id_section)

        # --- Metadata Section ---
        self.meta_section = self._section("Metadata")
        self.meta_table = QTableWidget()
        self.meta_table.setColumnCount(2)
        self.meta_table.setHorizontalHeaderLabels(["Key", "Value"])
        self.meta_table.horizontalHeader().setStretchLastSection(True)
        self.meta_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.meta_table.setAlternatingRowColors(False)
        self.meta_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.meta_table.setMaximumHeight(200)
        self.meta_table.verticalHeader().setVisible(False)
        self.meta_table.verticalHeader().setDefaultSectionSize(28)
        self.meta_section.layout().addWidget(self.meta_table)
        self.content_layout.addWidget(self.meta_section)

        # --- Vector Section ---
        self.vector_section = self._section("Vector")
        self.vector_info = QLabel("")
        self.vector_info.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        self.vector_section.layout().addWidget(self.vector_info)

        self.vector_display = QTextEdit()
        self.vector_display.setReadOnly(True)
        self.vector_display.setMaximumHeight(80)
        self.vector_display.setFont(QFont("monospace", 10))
        self.vector_display.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Colors.BG};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                color: {Colors.TEXT};
                padding: 6px;
            }}
        """)
        self.vector_section.layout().addWidget(self.vector_display)

        # Mini embedding bar chart (first 16 dims)
        self._embedding_bars = _EmbeddingBars()
        self._embedding_bars.setFixedHeight(48)
        self._embedding_bars.setStyleSheet("background: transparent;")
        self.vector_section.layout().addWidget(self._embedding_bars)

        self.content_layout.addWidget(self.vector_section)

        # --- Connections Section ---
        self.conn_section = self._section("Connections")

        # Connected-node chips row
        self._chips_row = QHBoxLayout()
        self._chips_row.setSpacing(4)
        self._chips_row.setContentsMargins(0, 0, 0, 4)
        self._chips_container = QWidget()
        self._chips_container.setLayout(self._chips_row)
        self._chips_container.setStyleSheet("background: transparent;")
        self.conn_section.layout().addWidget(self._chips_container)
        self.conn_table = QTableWidget()
        self.conn_table.setColumnCount(4)
        self.conn_table.setHorizontalHeaderLabels(["Target", "Score", "Distance", ""])
        self.conn_table.horizontalHeader().setStretchLastSection(True)
        self.conn_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.conn_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.conn_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.conn_table.setAlternatingRowColors(False)
        self.conn_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.conn_table.setMaximumHeight(200)
        self.conn_table.verticalHeader().setVisible(False)
        self.conn_section.layout().addWidget(self.conn_table)
        self.content_layout.addWidget(self.conn_section)

        # --- Files Section ---
        self.files_section = self._section("Attached Files")
        self.files_tree = QTreeWidget()
        self.files_tree.setHeaderLabels(["File", "Type", "Size", "Modified"])
        self.files_tree.header().setStretchLastSection(True)
        self.files_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.files_tree.setIndentation(16)
        self.files_tree.setMaximumHeight(160)
        self.files_section.layout().addWidget(self.files_tree)

        # File action buttons
        file_actions = QHBoxLayout()
        preview_btn = QPushButton("Preview")
        preview_btn.setIcon(icon("image", Colors.TEXT))
        preview_btn.clicked.connect(self._on_preview)
        file_actions.addWidget(preview_btn)

        open_btn = QPushButton("Open External")
        open_btn.setIcon(icon("link", Colors.TEXT))
        open_btn.clicked.connect(self._on_open_external)
        file_actions.addWidget(open_btn)
        file_actions.addStretch()
        self.files_section.layout().addLayout(file_actions)
        self.content_layout.addWidget(self.files_section)

        self.content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, stretch=1)

        self.setStyleSheet(f"background-color: {Colors.BG_RAISED};")

    def _section(self, title: str) -> QFrame:
        """Create a styled section frame with title header."""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Colors.BG};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 2px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QLabel(title.upper())
        header.setStyleSheet(f"""
            color: {Colors.ACCENT};
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.0px;
        """)
        layout.addWidget(header)
        return frame

    def load_node(self, node: dict):
        """Load full node data into the inspector."""
        self._current_node = node
        node_id = node.get("id", "unknown")

        # Color swatch from node color or hash
        color = node.get("color", None)
        if not color:
            hue = hash(node_id) % 360
            color = QColor.fromHsv(hue, 180, 220).name()
        self._color_swatch.setStyleSheet(
            f"background: {color}; border-radius: 10px; border: 2px solid {Colors.BORDER};"
        )

        # Identity
        meta = node.get("metadata", {})
        label = meta.get("text", meta.get("label", meta.get("title", node_id)))
        self.id_label.setText(f"ID: {node_id}\n{label}")

        # Metadata table
        self.meta_table.setRowCount(0)
        for key, value in meta.items():
            if key in ("text", "label", "title"):
                continue  # Shown in identity
            row = self.meta_table.rowCount()
            self.meta_table.insertRow(row)
            self.meta_table.setItem(row, 0, QTableWidgetItem(str(key)))
            val_text = str(value)
            if len(val_text) > 200:
                val_text = val_text[:200] + "..."
            self.meta_table.setItem(row, 1, QTableWidgetItem(val_text))

        # Vector
        vector = node.get("vector", [])
        dim = len(vector)
        self.vector_info.setText(f"Dimension: {dim}  |  Norm: {np_norm(vector):.4f}" if dim else "No vector data")
        if dim:
            preview = ", ".join(f"{v:.4f}" for v in vector[:20])
            if dim > 20:
                preview += f", ... ({dim - 20} more)"
            self.vector_display.setText(f"[{preview}]")
        else:
            self.vector_display.setText("—")

        # Mini embedding bars
        self._embedding_bars.set_vector(vector[:16] if vector else [])

        # Connections
        connections = node.get("connections", [])

        # Build clickable chips
        # Clear old chips
        clearLayout(self._chips_row)

        for conn in connections[:8]:  # Show max 8 chips
            tid = conn.get("id", "?")
            score = conn.get("score", 0)
            chip = QPushButton(tid[:8])
            chip.setFixedHeight(24)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setStyleSheet(
                f"QPushButton {{ background: {Colors.ACCENT_DARK}; color: {Colors.ACCENT}; "
                f"border: 1px solid {Colors.ACCENT}; border-radius: 12px; "
                f"padding: 0 8px; font-size: 10px; font-family: monospace; }}"
                f"QPushButton:hover {{ background: {Colors.ACCENT}; color: {Colors.BG}; }}"
            )
            chip.clicked.connect(lambda checked=False, t=tid: self.navigate_to_node.emit(t))
            self._chips_row.addWidget(chip)

        if len(connections) > 8:
            more = QLabel(f"+{len(connections) - 8} more")
            more.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px;")
            self._chips_row.addWidget(more)
        self._chips_row.addStretch()
        self.conn_table.setRowCount(0)
        for conn in connections:
            row = self.conn_table.rowCount()
            self.conn_table.insertRow(row)

            target_id = conn.get("id", "?")
            target_item = QTableWidgetItem(target_id)
            target_item.setToolTip(target_id)
            self.conn_table.setItem(row, 0, target_item)

            score = conn.get("score", 0)
            score_item = QTableWidgetItem(f"{score:.4f}")
            if score > 0.8:
                score_item.setForeground(QColor(Colors.SUCCESS))
            elif score > 0.5:
                score_item.setForeground(QColor(Colors.WARNING))
            else:
                score_item.setForeground(QColor(Colors.ERROR))
            self.conn_table.setItem(row, 1, score_item)

            dist = conn.get("distance", "")
            self.conn_table.setItem(row, 2, QTableWidgetItem(f"{dist:.4f}" if isinstance(dist, float) else str(dist)))

            # Navigate button
            nav_btn = QPushButton("Go")
            nav_btn.setFixedSize(30, 22)
            nav_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.ACCENT}; color: {Colors.BG};
                    border: none; border-radius: 4px; font-size: 10px; font-weight: 700;
                }}
                QPushButton:hover {{ background-color: {Colors.ACCENT_BRIGHT}; }}
            """)
            nav_btn.clicked.connect(lambda checked=False, tid=target_id: self.navigate_to_node.emit(tid))
            self.conn_table.setCellWidget(row, 3, nav_btn)

        # Files
        files = node.get("files", [])
        self.files_tree.clear()
        for fpath in files:
            p = Path(fpath)
            suffix = p.suffix.lower() if p.suffix else "—"
            size = ""
            if p.exists():
                sz = p.stat().st_size
                size = f"{sz / 1024:.1f}KB" if sz < 1024 * 1024 else f"{sz / (1024 * 1024):.1f}MB"
                mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            else:
                mtime = "not found"

            item = QTreeWidgetItem([p.name, suffix, size, mtime])
            item.setData(0, Qt.UserRole, str(fpath))
            self.files_tree.addTopLevelItem(item)

    def _on_preview(self):
        item = self.files_tree.currentItem()
        if item:
            fpath = item.data(0, Qt.UserRole)
            if fpath:
                self.preview_file_requested.emit(fpath)

    def _on_open_external(self):
        item = self.files_tree.currentItem()
        if item:
            fpath = item.data(0, Qt.UserRole)
            if fpath:
                self.open_file_requested.emit(fpath)

    def _copy_id(self):
        if self._current_node:
            node_id = self._current_node.get("id", "")
            clipboard = QApplication.clipboard()
            clipboard.setText(node_id)
            self._copy_id_btn.setIcon(icon("check", Colors.SUCCESS))
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1500, self._reset_copy_btn)

    def _reset_copy_btn(self):
        self._copy_id_btn.setIcon(icon("copy", Colors.TEXT))

    def clear(self):
        self.id_label.setText("No node selected")
        self.meta_table.setRowCount(0)
        self.vector_info.setText("")
        self.vector_display.setText("")
        self.conn_table.setRowCount(0)
        self.files_tree.clear()
        self._current_node = None


def np_norm(v: list) -> float:
    """Compute L2 norm without numpy dependency."""
    return sum(x * x for x in v) ** 0.5 if v else 0.0


class _EmbeddingBars(QWidget):
    """Mini bar chart showing first N embedding dimensions."""

    def __init__(self):
        super().__init__()
        self._values: list[float] = []

    def set_vector(self, values: list[float]):
        self._values = values
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def paintEvent(self, event):
        if not self._values:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        n = len(self._values)
        bar_w = max(2, (w - 4) / n - 1)
        gap = 1

        max_abs = max(abs(v) for v in self._values) or 1.0
        mid_y = h / 2

        for i, v in enumerate(self._values):
            x = 2 + i * (bar_w + gap)
            norm_v = v / max_abs  # -1 to 1

            # Color: positive = amber, negative = blue
            if norm_v >= 0:
                bar_h = norm_v * (mid_y - 2)
                grad = QLinearGradient(x, mid_y - bar_h, x, mid_y)
                grad.setColorAt(0, QColor(245, 158, 11, 200))
                grad.setColorAt(1, QColor(245, 158, 11, 80))
                painter.setBrush(grad)
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(int(x), int(mid_y - bar_h), int(bar_w), int(max(bar_h, 1)), 1, 1)
            else:
                bar_h = abs(norm_v) * (mid_y - 2)
                grad = QLinearGradient(x, mid_y, x, mid_y + bar_h)
                grad.setColorAt(0, QColor(96, 165, 250, 80))
                grad.setColorAt(1, QColor(96, 165, 250, 200))
                painter.setBrush(grad)
                painter.setPen(Qt.NoPen)
                painter.drawRoundedRect(int(x), int(mid_y), int(bar_w), int(max(bar_h, 1)), 1, 1)

        # Midline
        painter.setPen(QColor(255, 255, 255, 30))
        painter.drawLine(0, int(mid_y), w, int(mid_y))
        painter.end()
