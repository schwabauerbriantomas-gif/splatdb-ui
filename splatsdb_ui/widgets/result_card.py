# SPDX-License-Identifier: GPL-3.0
"""Result card."""

from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
from PySide6.QtCore import Signal
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class ResultCard(QFrame):
    store_clicked = Signal(int)
    explore_clicked = Signal(int)

    def __init__(self, index: int, score: float, metadata: str = ""):
        super().__init__()
        self.index = index
        # Clamp score to [0.0, 1.0] to handle out-of-range values from backend
        self.score = max(0.0, min(1.0, float(score or 0.0)))
        self.metadata = metadata
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"""
            ResultCard {{
                background-color: {Colors.BG_RAISED};
                border: 1px solid {Colors.BORDER};
                border-radius: 8px;
                padding: 10px 14px;
            }}
            ResultCard:hover {{ border-color: {Colors.ACCENT}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setContentsMargins(12, 10, 12, 10)

        header = QHBoxLayout()

        idx_label = QLabel(f"#{self.index}")
        idx_label.setStyleSheet(f"color: {Colors.ACCENT}; font-weight: 700; font-size: 12px;")
        header.addWidget(idx_label)

        score_label = QLabel(f"{self.score:.1%}")
        score_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px; font-weight: 600;")
        header.addWidget(score_label)
        header.addStretch()

        store_btn = QPushButton()
        store_btn.setIcon(icon("download", Colors.TEXT_DIM, 16))
        store_btn.setFixedSize(24, 24)
        store_btn.setToolTip("Store")
        store_btn.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: #21262d; border-radius: 4px; }")
        store_btn.clicked.connect(lambda: self.store_clicked.emit(self.index))
        header.addWidget(store_btn)

        explore_btn = QPushButton()
        explore_btn.setIcon(icon("link", Colors.TEXT_DIM, 16))
        explore_btn.setFixedSize(24, 24)
        explore_btn.setToolTip("Explore")
        explore_btn.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: #21262d; border-radius: 4px; }")
        explore_btn.clicked.connect(lambda: self.explore_clicked.emit(self.index))
        header.addWidget(explore_btn)

        layout.addLayout(header)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(self.score * 100))
        bar.setFixedHeight(4)
        bar.setTextVisible(False)
        layout.addWidget(bar)

        if self.metadata:
            preview = QLabel(str(self.metadata)[:200])
            preview.setWordWrap(True)
            preview.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px;")
            layout.addWidget(preview)
