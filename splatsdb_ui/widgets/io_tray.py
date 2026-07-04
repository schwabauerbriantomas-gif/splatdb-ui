# SPDX-License-Identifier: GPL-3.0
"""IO Tray."""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QFrame,
)
from PySide6.QtCore import Qt
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class IOTray(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)

        header = QHBoxLayout()
        lbl = QLabel("IO TRAY")
        lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 1.0px;")
        header.addWidget(lbl)
        header.addStretch()
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setFixedWidth(60)
        self.clear_btn.clicked.connect(self.clear)
        header.addWidget(self.clear_btn)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.items_widget = QWidget()
        self.items_layout = QHBoxLayout(self.items_widget)
        self.items_layout.setAlignment(Qt.AlignLeft)
        self.scroll.setWidget(self.items_widget)
        layout.addWidget(self.scroll)

        self.setStyleSheet(f"background-color: {Colors.BG_RAISED}; border-top: 1px solid {Colors.BORDER};")

    def add_item(self, widget: QWidget):
        """Add a widget item to the tray."""
        self.items_layout.addWidget(widget)

    def clear(self):
        """Remove all items from the tray."""
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
