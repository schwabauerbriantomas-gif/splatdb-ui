# SPDX-License-Identifier: GPL-3.0
"""Node Inspector — full node audit panel.

Shows: metadata, raw vector, connections table, attached files.
Splitter layout: Inspector (left) | File Preview (right).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSplitter, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QHeaderView, QTableWidget, QTableWidgetItem,
    QSizePolicy,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

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
        self.close_btn.setStyleSheet(f"QPushButton {{ background: transparent; border: none; border-radius: 6px; }} QPushButton:hover {{ background-color: {Colors.BG_OVERLAY}; }}")
        self.close_btn.clicked.connect(self.hide)
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
        self.id_label = QLabel("No node selected")
        self.id_label.setWordWrap(True)
        self.id_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.id_label.setStyleSheet(f"color: {Colors.TEXT}; font-size: 12px; font-family: monospace;")
        self.id_section.layout().addWidget(self.id_label)
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
        self.content_layout.addWidget(self.vector_section)

        # --- Connections Section ---
        self.conn_section = self._section("Connections")
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
        """Create a collapsible section frame."""
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

        # Connections
        connections = node.get("connections", [])
        # Clean up previous cell widgets to prevent memory leaks
        for r in range(self.conn_table.rowCount()):
            w = self.conn_table.cellWidget(r, 3)
            if w:
                w.deleteLater()
        self.conn_table.setRowCount(0)
        for conn in connections:
            row = self.conn_table.rowCount()
            self.conn_table.insertRow(row)

            target_id = conn.get("id", "?")
            target_item = QTableWidgetItem(target_id[:16])
            self.conn_table.setItem(row, 0, target_item)

            score = conn.get("score", 0)
            score_item = QTableWidgetItem(f"{score:.4f}")
            if score > 0.8:
                score_item.setForeground(Qt.green)
            elif score > 0.5:
                score_item.setForeground(Qt.yellow)
            else:
                score_item.setForeground(Qt.red)
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
                from datetime import datetime
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
