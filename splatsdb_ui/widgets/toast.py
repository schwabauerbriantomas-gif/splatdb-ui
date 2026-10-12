# SPDX-License-Identifier: GPL-3.0
"""Toast notification system with fade animation.

Floating toasts appear at the top-right of the main window, show a message
for 3 seconds with smooth fade-in / fade-out, then auto-dismiss.
Multiple toasts stack vertically.

Usage::

    from splatsdb_ui.widgets.toast import Toast

    Toast.show('Saved successfully', type='success')
    Toast.show('Connection lost',    type='error')
    Toast.show('Refreshing…',        type='info')
    Toast.show('Low disk space',     type='warning')

Types: info (blue), success (green), warning (amber), error (red).
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QGraphicsOpacityEffect,
    QSizePolicy,
)
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, Signal,
)
from PySide6.QtGui import QPainter, QColor, QPaintEvent, QFont

# ── Palette per type ──────────────────────────────────────────────────

_TOAST_COLORS: dict[str, dict[str, str]] = {
    "info": {
        "bg":        "#1e3a5f",
        "border":    "#3b82f6",
        "accent":    "#60a5fa",
        "text":      "#dbeafe",
        "icon_char": "ℹ",
    },
    "success": {
        "bg":        "#14532d",
        "border":    "#22c55e",
        "accent":    "#4ade80",
        "text":      "#dcfce7",
        "icon_char": "✓",
    },
    "warning": {
        "bg":        "#422006",
        "border":    "#eab308",
        "accent":    "#facc15",
        "text":      "#fef9c3",
        "icon_char": "⚠",
    },
    "error": {
        "bg":        "#450a0a",
        "border":    "#ef4444",
        "accent":    "#f87171",
        "text":      "#fee2e2",
        "icon_char": "✕",
    },
}

# Timing constants (ms)
_FADE_IN_DURATION   = 250
_FADE_OUT_DURATION  = 350
_DISPLAY_DURATION   = 3000


class _ToastCard(QWidget):
    """A single toast card widget with rounded corners and fade animation."""

    dismissed = Signal()  # emitted when the card has finished fading out

    def __init__(self, message: str, toast_type: str = "info", parent=None,
                 duration: int = _DISPLAY_DURATION):
        super().__init__(parent)
        self._toast_type = toast_type
        self._duration = duration
        colors = _TOAST_COLORS.get(toast_type, _TOAST_COLORS["info"])

        # -- Widget setup ------------------------------------------------
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMinimumWidth(280)
        self.setMaximumWidth(420)

        # -- Opacity effect for fade -------------------------------------
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity_effect)

        # -- Layout ------------------------------------------------------
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        # Icon character
        icon_label = QLabel(colors["icon_char"])
        icon_label.setFixedSize(20, 20)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(f"""
            color: {colors['accent']};
            font-size: 16px;
            font-weight: bold;
            background: transparent;
        """)
        layout.addWidget(icon_label)

        # Message
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        msg_label.setStyleSheet(f"""
            color: {colors['text']};
            font-size: 13px;
            background: transparent;
            border: none;
        """)
        layout.addWidget(msg_label, stretch=1)

        self._base_style = (
            f"background-color: {colors['bg']}; "
            f"border: 1px solid {colors['border']}; "
            f"border-left: 3px solid {colors['accent']}; "
            f"border-radius: 8px; "
            f"padding: 2px;"
        )
        self.setStyleSheet(self._base_style + " background-color: transparent;")

        # -- Animations --------------------------------------------------
        self._anim_in = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim_in.setDuration(_FADE_IN_DURATION)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)
        self._anim_in.setEasingCurve(QEasingCurve.OutCubic)

        self._anim_out = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._anim_out.setDuration(_FADE_OUT_DURATION)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.setEasingCurve(QEasingCurve.InCubic)
        self._anim_out.finished.connect(self._on_fade_out_done)

        # -- Auto-dismiss timer ------------------------------------------
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._start_fade_out)

    # ── Painting (draw rounded bg behind the opacity effect) ───────────

    def paintEvent(self, event: QPaintEvent):
        colors = _TOAST_COLORS.get(self._toast_type, _TOAST_COLORS["info"])
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(self._opacity_effect.opacity())

        # Background fill
        p.setBrush(QColor(colors["bg"]))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)

        # Left accent bar
        accent_w = 3
        p.setBrush(QColor(colors["accent"]))
        p.drawRoundedRect(1, 1, accent_w + 2, self.height() - 2, 2, 2)

        # Border
        p.setBrush(Qt.NoBrush)
        p.setPen(QColor(colors["border"]))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 8, 8)

        p.end()

    # ── Public lifecycle ───────────────────────────────────────────────

    def show_toast(self):
        """Start the fade-in and schedule auto-dismiss."""
        self.show()
        self._anim_in.start()
        self._dismiss_timer.start(self._duration)

    def dismiss_now(self):
        """Skip the display timer and start fading out immediately."""
        if self._dismiss_timer.isActive():
            self._dismiss_timer.stop()
        self._start_fade_out()

    # ── Internals ──────────────────────────────────────────────────────

    def _start_fade_out(self):
        self._anim_out.start()

    def _on_fade_out_done(self):
        self.hide()
        self.dismissed.emit()
        self.deleteLater()


class ToastOverlay(QWidget):
    """Overlay that lives inside the main window and manages stacked toasts.

    Place one instance of this in the main window's central widget and call
    ``ToastOverlay.instance().show_toast(...)`` — or simply use the
    convenience class method ``Toast.show(...)``.
    """

    _instance: ToastOverlay | None = None

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        ToastOverlay._instance = self

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 12, 0)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignTop | Qt.AlignRight)

        self._cards: list[_ToastCard] = []

    @classmethod
    def instance(cls) -> ToastOverlay | None:
        return cls._instance

    # ── Public API ─────────────────────────────────────────────────────

    def show_toast(self, message: str, toast_type: str = "info",
                   duration: int = _DISPLAY_DURATION):
        """Create and show a new toast notification."""
        card = _ToastCard(message, toast_type, self, duration=duration)
        card.dismissed.connect(lambda: self._remove_card(card))

        self._cards.append(card)
        self._layout.addWidget(card)
        self._reposition()
        card.show_toast()

    def clear_all(self):
        """Dismiss all active toasts immediately."""
        for card in list(self._cards):
            card.dismiss_now()

    # ── Internals ──────────────────────────────────────────────────────

    def _remove_card(self, card: _ToastCard):
        if card in self._cards:
            self._cards.remove(card)
            self._layout.removeWidget(card)
            self._reposition()

    def _reposition(self):
        """Reposition the overlay to the top-right of the parent widget."""
        if not self.parent():
            return
        parent = self.parent()
        margin_top = 48  # below menu bar area
        # Restrict geometry to the actual card stack area (top-right)
        card_w = max(c.sizeHint().width() for c in self._cards) if self._cards else 280
        card_w = min(card_w, 420)
        card_h = sum(c.sizeHint().height() for c in self._cards) + len(self._cards) * 8
        right_margin = 12
        self.setGeometry(
            parent.width() - card_w - right_margin,
            margin_top,
            card_w + right_margin,
            max(card_h, 1),
        )

    def resizeEvent(self, event):
        self._reposition()
        super().resizeEvent(event)

    # ── Keep overlay the same size as parent ───────────────────────────

    def showEvent(self, event):
        self._reposition()
        super().showEvent(event)


class Toast:
    """Convenience accessor — call from anywhere in the application.

    Usage::

        Toast.show('Saved!', type='success')
        Toast.show('Something went wrong', type='error')
        Toast.show('Retrying in 5s', type='warning', duration=5000)
    """

    @staticmethod
    def show(message: str, *, type: str = "info", duration: int = _DISPLAY_DURATION):
        overlay = ToastOverlay.instance()
        if overlay is None:
            # Fallback: log warning if no overlay is set up
            logging.warning("[Toast:%s] %s", type, message)
            return
        overlay.show_toast(message, type, duration)

    @staticmethod
    def clear_all():
        overlay = ToastOverlay.instance()
        if overlay:
            overlay.clear_all()
