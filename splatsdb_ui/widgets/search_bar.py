# SPDX-License-Identifier: GPL-3.0
"""Global search bar."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon

# ── Brand label theme constants ───────────────────────────────────
_BRAND_FONT_SIZE = 10
_BRAND_FONT_WEIGHT = 700
_BRAND_LETTER_SPACING = 1.5
_BRAND_MIN_WIDTH = 90  # generous minimum, no fixed clipping


class GlobalSearchBar(QWidget):
    search_requested = Signal(str)
    search_cleared = Signal()  # emitted when user clears the search

    def __init__(self):
        super().__init__()
        self.setFixedHeight(48)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 6, 16, 6)
        layout.setSpacing(10)

        # Brand label — styled via theme constants, not hardcoded inline values
        brand = QLabel("SPLATSDB")
        brand_font = brand.font()
        brand_font.setPixelSize(_BRAND_FONT_SIZE)
        brand_font.setWeight(QFont.Weight(_BRAND_FONT_WEIGHT))
        brand_font.setLetterSpacing(QFont.Spacing.AbsolutePointSize, _BRAND_LETTER_SPACING)
        brand.setFont(brand_font)
        brand.setStyleSheet(f"color: {Colors.TEXT_DIM};")
        brand.setMinimumWidth(_BRAND_MIN_WIDTH)
        layout.addWidget(brand)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Search vectors...  Ctrl+K")
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self._on_search)
        self.input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.input, stretch=1)

        self.btn = QPushButton()
        self.btn.setIcon(icon("search", Colors.BG))  # dark icon on amber bg
        self.btn.setFixedSize(34, 34)
        self.btn.clicked.connect(self._on_search)
        self.btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {Colors.ACCENT}; border: none;
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background-color: {Colors.ACCENT_BRIGHT};
                icon-size: 18px;
            }}
        """)
        layout.addWidget(self.btn)

        # Use class-name selector instead of QWidget to avoid style leaks
        self.setStyleSheet(f"""
            GlobalSearchBar {{
                background-color: {Colors.BG_RAISED};
                border-bottom: 1px solid {Colors.BORDER};
            }}
        """)

    def _on_search(self):
        text = self.input.text().strip()
        if text:
            self.search_requested.emit(text)
        else:
            self.search_cleared.emit()

    def _on_text_changed(self, text: str):
        """Detect when the user clears the field (e.g. via the clear button)."""
        if not text.strip():
            self.search_cleared.emit()

    def focus_search(self):
        self.input.setFocus()
        self.input.selectAll()

    def clear_search(self):
        self.input.clear()
