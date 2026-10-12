# SPDX-License-Identifier: GPL-3.0
"""Search view — polished with loading state, empty state, result count, keyboard hints,
fade-in cards, smooth scroll animation."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QComboBox, QScrollArea, QFrame,
    QGraphicsOpacityEffect, QSizePolicy,
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QPropertyAnimation, QEasingCurve, Property,
)
from PySide6.QtGui import QFont, QKeyEvent, QColor, QPainter, QRadialGradient
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon
from splatsdb_ui.widgets.result_card import ResultCard


# ── Animated spinner widget ──────────────────────────────────────────────────

class SpinningSpinner(QLabel):
    """A simple text-based loading spinner that cycles through spinner chars."""

    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame = 0
        self._active = False
        self.setFont(QFont("", 28))
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"color: {Colors.ACCENT}; background: transparent;")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._frame = (self._frame + 1) % len(self._FRAMES)
        self.setText(self._FRAMES[self._frame])

    @Property(bool)
    def active(self):
        return self._active

    @active.setter
    def active(self, value: bool):
        self._active = value
        if value:
            self._frame = 0
            self.setText(self._FRAMES[0])
            self.show()
            self._timer.start(80)
        else:
            self._timer.stop()
            self.hide()


# ── Empty state illustration (painted) ──────────────────────────────────────

class EmptyStateWidget(QWidget):
    """Custom-painted empty state with a search illustration."""

    def __init__(self, title: str = "No results yet", desc: str = "", parent=None):
        super().__init__(parent)
        self._title = title
        self._desc = desc or "Type a query above and press Enter to search your collections."
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)

        # Painted illustration area
        self._canvas = QLabel()
        self._canvas.setFixedSize(120, 90)
        self._canvas.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._canvas, alignment=Qt.AlignCenter)

        title_lbl = QLabel(self._title)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: 16px; font-weight: 600;"
            f"background: transparent;"
        )
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(self._desc)
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)
        desc_lbl.setMaximumWidth(400)
        desc_lbl.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 13px; background: transparent;"
            f"line-height: 1.5;"
        )
        layout.addWidget(desc_lbl)

        # Hint about keyboard shortcuts
        hint = QLabel("↑↓ Navigate  ·  Enter Open  ·  Esc Clear")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(
            f"color: {Colors.TEXT_MUTED}; font-size: 11px; background: transparent;"
            f"margin-top: 4px;"
        )
        layout.addWidget(hint)

    # Keep setWindowTitle-like interface for dynamic updates
    def set_title(self, text: str):
        self._title = text
        # Update the title label (2nd item in layout after canvas)
        item = self.layout().itemAt(1)
        if item and item.widget():
            item.widget().setText(text)

    def set_description(self, text: str):
        item = self.layout().itemAt(2)
        if item and item.widget():
            item.widget().setText(text)


# ── Main search view ─────────────────────────────────────────────────────────

class SearchView(QWidget):
    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._is_searching = False
        self._has_results = False
        self._focused_result = -1  # keyboard nav index; -1 = no focus
        self._result_cards = []    # ordered list of ResultCard refs
        self._card_animations = [] # keep refs so they aren't GC'd
        self._build_ui()
        self._connect_signals()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Header row: title + result count badge ──────────────────────────
        header = QHBoxLayout()
        header.setSpacing(10)

        title = QLabel("Search")
        title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: 20px; font-weight: 700;"
            f"letter-spacing: -0.3px;"
        )
        header.addWidget(title)

        self.result_count_badge = QLabel("")
        self.result_count_badge.setAlignment(Qt.AlignCenter)
        self.result_count_badge.setFixedHeight(22)
        self.result_count_badge.setMinimumWidth(28)
        self.result_count_badge.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._style_badge(0)
        self.result_count_badge.hide()
        header.addWidget(self.result_count_badge)

        header.addStretch()
        layout.addLayout(header)

        # ── Controls row ────────────────────────────────────────────────────
        controls = QHBoxLayout()
        controls.setSpacing(10)

        # Search input with embedded keyboard hint
        input_container = QVBoxLayout()
        input_container.setSpacing(2)

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Enter search query...")
        self.query_input.setMinimumHeight(40)
        self.query_input.setFont(QFont("", 13))
        self.query_input.returnPressed.connect(self._on_search)
        input_container.addWidget(self.query_input)

        # Keyboard hint row
        hint_row = QHBoxLayout()
        hint_row.setSpacing(6)

        for text in ["⏎ Search", "·", "↑↓ Navigate results", "·", "Esc Clear"]:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color: {Colors.TEXT_MUTED}; font-size: 10px; background: transparent;"
            )
            hint_row.addWidget(lbl)

        input_container.addLayout(hint_row)
        controls.addLayout(input_container, stretch=1)

        top_k_label = QLabel("Top K:")
        top_k_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px;")
        controls.addWidget(top_k_label)
        self.top_k = QSpinBox()
        self.top_k.setRange(1, 1000)
        self.top_k.setValue(10)
        self.top_k.setFixedWidth(70)
        controls.addWidget(self.top_k)

        self.collection_combo = QComboBox()
        self.collection_combo.setMinimumWidth(160)
        controls.addWidget(self.collection_combo)

        self.search_btn = QPushButton(" Search")
        self.search_btn.setIcon(icon("search", Colors.BG))
        self.search_btn.setProperty("class", "primary")
        self.search_btn.setMinimumWidth(100)
        self.search_btn.clicked.connect(self._on_search)
        controls.addWidget(self.search_btn)

        layout.addLayout(controls)

        # ── Results area (scroll + overlay for states) ──────────────────────
        result_frame = QFrame()
        result_frame.setStyleSheet(f"background: transparent;")
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.results_widget = QWidget()
        self.results_layout = QVBoxLayout(self.results_widget)
        self.results_layout.setAlignment(Qt.AlignTop)
        self.results_layout.setSpacing(10)
        self.results_layout.setContentsMargins(0, 4, 0, 4)
        self.scroll.setWidget(self.results_widget)
        result_layout.addWidget(self.scroll)

        # Loading overlay
        self.loading_overlay = QWidget(self)
        self.loading_overlay.setStyleSheet("background: transparent;")
        lo_layout = QVBoxLayout(self.loading_overlay)
        lo_layout.setAlignment(Qt.AlignCenter)
        lo_layout.setSpacing(12)

        self.spinner = SpinningSpinner()
        lo_layout.addWidget(self.spinner, alignment=Qt.AlignCenter)

        self.loading_label = QLabel("Searching...")
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 13px; font-weight: 500; background: transparent;"
        )
        lo_layout.addWidget(self.loading_label, alignment=Qt.AlignCenter)
        self.loading_overlay.hide()

        # Empty state widget (custom painted)
        self.empty_state = EmptyStateWidget()
        self.empty_state.setStyleSheet("background: transparent;")
        self.empty_state.hide()

        # Stacking: overlays sit on top of scroll
        result_layout.addWidget(self.empty_state)

        layout.addWidget(result_frame, stretch=1)

        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 11px;"
        )
        layout.addWidget(self.status_label)

        # Show empty state initially
        self._show_empty_state()

    def _style_badge(self, count: int):
        """Style the result count badge with optional pop animation."""
        if count > 0:
            self.result_count_badge.setText(f" {count} ")
            self.result_count_badge.setStyleSheet(f"""
                QLabel {{
                    background-color: {Colors.ACCENT};
                    color: {Colors.BG};
                    font-size: 11px;
                    font-weight: 700;
                    border-radius: 11px;
                    padding: 2px 8px;
                }}
            """)
            self.result_count_badge.show()
            # Pop-in animation: scale from 0 → 1
            if not hasattr(self, '_badge_anim'):
                self._badge_anim = QPropertyAnimation(self.result_count_badge, b"geometry")
            geo = self.result_count_badge.geometry()
            center_x = geo.x() + geo.width() // 2
            center_y = geo.y() + geo.height() // 2
            small = geo.__class__(
                center_x - geo.width() // 4,
                center_y - geo.height() // 4,
                geo.width() // 2,
                geo.height() // 2,
            )
            self._badge_anim.setDuration(250)
            self._badge_anim.setStartValue(small)
            self._badge_anim.setEndValue(geo)
            self._badge_anim.setEasingCurve(QEasingCurve.OutBack)
            self._badge_anim.start()
        else:
            self.result_count_badge.hide()

    # ── State Management ─────────────────────────────────────────────────────

    def _show_empty_state(self):
        self._has_results = False
        self.empty_state.set_title("No results yet")
        self.empty_state.set_description(
            "Type a query above and press Enter to search your collections."
        )
        self.empty_state.show()
        self.spinner.active = False
        self.loading_overlay.hide()
        self._style_badge(0)

    def _show_loading(self, query: str):
        self._is_searching = True
        self._has_results = False
        self.empty_state.hide()
        self.loading_overlay.show()
        self.loading_label.setText(f'Searching for "{query}"...')
        self.spinner.active = True
        self.search_btn.setEnabled(False)
        self.search_btn.setText(" Searching...")
        self.status_label.setText(f"Searching: {query}...")

    def _show_results(self, results: list):
        self._is_searching = False
        self.spinner.active = False
        self.loading_overlay.hide()
        self.search_btn.setEnabled(True)
        self.search_btn.setText(" Search")

        # Clear previous results
        self._clear_results()

        count = len(results)
        if count == 0:
            self._show_no_results()
            return

        self._has_results = True
        self.empty_state.hide()

        self._result_cards.clear()
        self._focused_result = -1
        self._card_animations.clear()

        # Scroll to top smoothly before adding cards
        self._scroll_to_top()

        for i, r in enumerate(results):
            card = ResultCard(index=i, score=r.get("score", 0), metadata=r.get("text", ""))
            card.store_clicked.connect(self._on_card_store)
            card.explore_clicked.connect(self._on_card_explore)
            self.results_layout.addWidget(card)
            self._result_cards.append(card)

            # Staggered fade-in animation
            self._animate_card_fade_in(card, i)

        self._style_badge(count)
        self.status_label.setText(
            f"{count} result{'s' if count != 1 else ''} found"
        )

    def _show_no_results(self):
        """Show empty state with 'no results found' message."""
        self._has_results = False
        self.empty_state.set_title("No results found")
        self.empty_state.set_description(
            "Try adjusting your query, changing the collection, or increasing Top K."
        )
        self.empty_state.show()
        self._style_badge(0)
        self.status_label.setText("No results found")

    def _clear_results(self):
        """Remove all result cards from the layout."""
        self._result_cards.clear()
        self._card_animations.clear()
        self._focused_result = -1
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ── Animations ───────────────────────────────────────────────────────────

    def _animate_card_fade_in(self, card: ResultCard, index: int):
        """Staggered fade-in for a result card."""
        opacity_effect = QGraphicsOpacityEffect(card)
        opacity_effect.setOpacity(0.0)
        card.setGraphicsEffect(opacity_effect)

        anim = QPropertyAnimation(opacity_effect, b"opacity")
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        # Stagger: each card starts a bit later
        anim.setStartValue(0.0)
        QTimer.singleShot(min(index * 50, 500), anim.start)

        self._card_animations.append((opacity_effect, anim))

    def _scroll_to_top(self):
        """Smooth-scroll the results area to the top."""
        scrollbar = self.scroll.verticalScrollBar()
        if scrollbar.value() <= 0:
            return
        self._scroll_anim = QPropertyAnimation(scrollbar, b"value")
        self._scroll_anim.setDuration(250)
        self._scroll_anim.setStartValue(scrollbar.value())
        self._scroll_anim.setEndValue(0)
        self._scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._scroll_anim.start()

    # ── Signal Wiring ────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.signals.search_results.connect(self._on_search_results)

    def _on_search_results(self, results: list):
        """Handle search_results signal from the signal bus."""
        self._show_results(results)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_search(self):
        query = self.query_input.text().strip()
        if not query or self._is_searching:
            return
        self._show_loading(query)
        self.signals.search_requested.emit(query)

    def execute_search(self, query: str):
        """Set query text and trigger search — used by global search."""
        self.query_input.setText(query)
        self._on_search()

    # ── Keyboard Handling ────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        n = len(self._result_cards)

        if key == Qt.Key_Down and n:
            self._move_focus(1)
        elif key == Qt.Key_Up and n:
            self._move_focus(-1)
        elif key == Qt.Key_Enter or key == Qt.Key_Return:
            if self._focused_result >= 0:
                self._open_focused_result()
            # else: let returnPressed on QLineEdit fire _on_search
        elif key == Qt.Key_Escape:
            if self._focused_result >= 0:
                # First press: clear result focus, return to input
                self._clear_focus()
                self.query_input.setFocus()
            else:
                # Second press: clear query + results
                self.query_input.clear()
                self._clear_results()
                self._show_empty_state()
                self.status_label.setText("Ready")
                self.query_input.setFocus()
        else:
            super().keyPressEvent(event)

    # ── Focus Navigation Helpers ─────────────────────────────────────────────

    def _move_focus(self, delta: int):
        """Move keyboard focus by +delta (1 = down, -1 = up)."""
        n = len(self._result_cards)
        if n == 0:
            return

        # Unhighlight old card
        if 0 <= self._focused_result < n:
            self._result_cards[self._focused_result].set_focused(False)

        # Compute new index; start at 0 if nothing focused yet
        if self._focused_result < 0:
            new_idx = 0 if delta > 0 else n - 1
        else:
            new_idx = self._focused_result + delta

        # Clamp to valid range
        new_idx = max(0, min(n - 1, new_idx))
        self._focused_result = new_idx

        # Highlight new card and smoothly scroll to it
        card = self._result_cards[new_idx]
        card.set_focused(True)
        self._scroll_to_card(card)
        self.status_label.setText(
            f"Result {new_idx + 1} of {n}  —  Enter to open, Esc to deselect"
        )

    def _scroll_to_card(self, card: QWidget):
        """Smooth-scroll to ensure *card* is visible."""
        scrollbar = self.scroll.verticalScrollBar()
        # Compute target scroll value
        card_top = card.geometry().top()
        content_y = self.results_widget.geometry().top()
        # ensureWidgetVisible does not animate, so we animate manually
        target = scrollbar.value()
        card_abs_y = card.mapTo(self.scroll.viewport(), card.rect().topLeft()).y()
        viewport_h = self.scroll.viewport().height()

        if card_abs_y < 20:
            target = scrollbar.value() + card_abs_y - 20
        elif card_abs_y + card.height() > viewport_h - 20:
            target = scrollbar.value() + (card_abs_y + card.height()) - viewport_h + 20

        target = max(scrollbar.minimum(), min(scrollbar.maximum(), target))
        if target != scrollbar.value():
            self._nav_scroll_anim = QPropertyAnimation(scrollbar, b"value")
            self._nav_scroll_anim.setDuration(150)
            self._nav_scroll_anim.setStartValue(scrollbar.value())
            self._nav_scroll_anim.setEndValue(target)
            self._nav_scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._nav_scroll_anim.start()

    def _clear_focus(self):
        """Remove keyboard focus highlight from any result card."""
        n = len(self._result_cards)
        if 0 <= self._focused_result < n:
            self._result_cards[self._focused_result].set_focused(False)
        self._focused_result = -1
        if self._has_results:
            count = len(self._result_cards)
            self.status_label.setText(
                f"{count} result{'s' if count != 1 else ''} found"
            )

    def _open_focused_result(self):
        """Open the detail panel for the focused result card."""
        if 0 <= self._focused_result < len(self._result_cards):
            card = self._result_cards[self._focused_result]
            self.status_label.setText(f"Opening result #{card.index + 1}...")
            # Emit explore signal to open detail view
            self.signals.status_message.emit(
                f"Opened result #{card.index + 1} (score: {card.score:.1%})"
            )

    # ── Card Action Handlers ─────────────────────────────────────────────────

    def _on_card_store(self, index: int):
        self.signals.status_message.emit(f"Storing result #{index + 1}...")

    def _on_card_explore(self, index: int):
        self.signals.status_message.emit(f"Exploring connections for result #{index + 1}...")

    # ── Params (for parameter panel integration) ─────────────────────────────

    def get_params(self) -> list:
        return [
            {"name": "top_k", "label": "Top K", "type": "spin", "min": 1, "max": 1000, "default": 10},
            {"name": "threshold", "label": "Min Score", "type": "float", "min": 0.0, "max": 1.0, "step": 0.01},
        ]
