# SPDX-License-Identifier: GPL-3.0
"""IO Tray."""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class _TrayItem(QFrame):
    """A single file/document item in the IO tray."""

    def __init__(self, item_id: str, label: str, icon_name: str | None = None):
        super().__init__()
        self.item_id = item_id
        self._build(label, icon_name)

    def _build(self, label: str, icon_name: str | None):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        if icon_name:
            ico = icon(icon_name, color=Colors.ACCENT, size=14)
            ico_lbl = QLabel()
            ico_lbl.setPixmap(ico.pixmap(14, 14))
            layout.addWidget(ico_lbl)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {Colors.TEXT}; font-size: 11px;")
        layout.addWidget(lbl)

        self.setStyleSheet(f"""
            _TrayItem {{
                background-color: {Colors.BG_OVERLAY};
                border: 1px solid {Colors.BORDER};
                border-radius: 4px;
            }}
        """)


class IOTray(QWidget):
    def __init__(self):
        super().__init__()
        self._items: dict[str, _TrayItem] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)

        header = QHBoxLayout()
        lbl = QLabel("IO TRAY")
        lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 1.0px;")
        header.addWidget(lbl)
        header.addStretch()

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_OVERLAY}; color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT}; border-radius: 4px;
                padding: 3px 8px; font-weight: 600; font-size: 10px;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT}; color: {Colors.BG};
            }}
        """)
        self._clear_btn.clicked.connect(self._clear_all)
        header.addWidget(self._clear_btn)
        layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.items_widget = QWidget()
        self.items_layout = QHBoxLayout(self.items_widget)
        self.items_layout.setAlignment(Qt.AlignLeft)
        self.items_layout.addStretch()
        self.scroll.setWidget(self.items_widget)
        layout.addWidget(self.scroll)

        self.setStyleSheet(f"background-color: {Colors.BG_RAISED};")

    def add_item(self, item_id: str, label: str, icon_name: str | None = None):
        """Add a file/document item to the tray with an optional icon."""
        if item_id in self._items:
            return
        tray_item = _TrayItem(item_id, label, icon_name)
        self._items[item_id] = tray_item
        # Insert before the trailing stretch
        count = self.items_layout.count()
        self.items_layout.insertWidget(count - 1, tray_item)

    def remove_item(self, item_id: str):
        """Remove a file/document item from the tray by its ID."""
        item = self._items.pop(item_id, None)
        if item:
            self.items_layout.removeWidget(item)
            item.setParent(None)
            item.deleteLater()

    def _clear_all(self):
        """Remove all items from the tray."""
        for item_id in list(self._items.keys()):
            self.remove_item(item_id)
