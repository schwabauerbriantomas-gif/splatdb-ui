# SPDX-License-Identifier: GPL-3.0
"""Shared widget builders to DRY the sidebar/controls/toolbar pattern across views.

Every view (EBM, Cluster, Benchmark, Spatial) builds its own toolbar,
sidebar, and info bar with nearly identical QSS and layout code.
This module provides reusable builders that standardize the look using
the project's Colors palette from splatsdb_ui.utils.theme.

Usage examples at the bottom of the file.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QComboBox, QCheckBox, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

from splatsdb_ui.utils.theme import Colors


# ---------------------------------------------------------------------------
# Stylesheet templates
# ---------------------------------------------------------------------------

_TOOLBAR_STYLE = (
    f"background-color: {Colors.BG_RAISED};"
    f" border-bottom: 1px solid {Colors.BORDER};"
)

_TOOLBAR_WIDGET_STYLE = (
    f"QLabel {{ color: {Colors.TEXT_DIM}; font-size: 11px; }}"
    f"QCheckBox {{ color: {Colors.TEXT}; font-size: 11px; }}"
    f"QPushButton {{ background: {Colors.BG_OVERLAY}; color: {Colors.TEXT};"
    f" border: 1px solid {Colors.BORDER}; border-radius: 4px; padding: 4px 10px; }}"
    f"QPushButton:hover {{ background: {Colors.BG_HOVER}; }}"
)

_INFO_BAR_STYLE = (
    f"color: {Colors.TEXT_DIM}; font-size: 11px; padding: 6px 12px;"
    f" background-color: {Colors.BG_RAISED}; border-top: 1px solid {Colors.BORDER};"
)

_SIDEBAR_STYLE = (
    f"background-color: {Colors.BG_RAISED};"
    f" QLabel {{ color: {Colors.TEXT}; font-size: 11px; }}"
)

_SIDEBAR_TITLE_STYLE = (
    f"color: {Colors.ACCENT}; font-size: 10px; font-weight: 700;"
    f" letter-spacing: 1px;"
)

_ACCENT_BUTTON_STYLE = f"""
    QPushButton {{
        background-color: {Colors.ACCENT}; color: {Colors.BG};
        border: none; border-radius: 6px; padding: 8px; font-weight: 700;
    }}
    QPushButton:hover {{ background-color: {Colors.ACCENT}CC; }}
"""

_OUTLINED_BUTTON_STYLE = f"""
    QPushButton {{
        background: {Colors.BG_OVERLAY}; color: {Colors.ACCENT};
        border: 1px solid {Colors.ACCENT}; border-radius: 4px;
        padding: 4px 10px; font-weight: 600;
    }}
    QPushButton:hover {{ background: {Colors.ACCENT}; color: {Colors.BG}; }}
"""


# ---------------------------------------------------------------------------
# Toolbar builder
# ---------------------------------------------------------------------------

def build_toolbar(
    title: str,
    subtitle: str | None = None,
    title_style: str | None = None,
) -> tuple[QWidget, QHBoxLayout]:
    """Build a standardised top toolbar bar.

    Returns (toolbar_widget, layout) so the caller can add their own
    controls to the layout before adding the toolbar to the parent.

    Parameters
    ----------
    title : str
        Main title text (e.g. "Benchmark Dashboard").
    subtitle : str, optional
        Secondary descriptive text shown after the title.
    title_style : str, optional
        Override the default title stylesheet.
    """
    tb = QHBoxLayout()
    tb.setContentsMargins(12, 8, 12, 8)
    tb.setSpacing(10)

    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        title_style
        or f"color: {Colors.TEXT}; font-size: 14px; font-weight: 700;"
    )
    tb.addWidget(title_lbl)

    if subtitle:
        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px;")
        if len(subtitle) > 30:
            sub_lbl.setStyleSheet(
                f"color: {Colors.TEXT_DIM}; font-size: 10px; font-family: monospace;"
            )
        tb.addWidget(sub_lbl)

    tb.addStretch()

    tb_w = QWidget()
    tb_w.setLayout(tb)
    tb_w.setStyleSheet(_TOOLBAR_STYLE + _TOOLBAR_WIDGET_STYLE)
    return tb_w, tb


# ---------------------------------------------------------------------------
# Info bar builder
# ---------------------------------------------------------------------------

def build_info_bar(text: str = "") -> QLabel:
    """Build a standardised bottom info/status bar.

    Parameters
    ----------
    text : str
        Initial text to display.
    """
    label = QLabel(text)
    label.setStyleSheet(_INFO_BAR_STYLE)
    return label


# ---------------------------------------------------------------------------
# Control panel (sidebar) builder
# ---------------------------------------------------------------------------

def build_control_panel(
    title: str,
    controls: list[dict],
    *,
    width: int = 260,
    accent_button: str | None = None,
    accent_callback=None,
    stretch_at_end: bool = True,
    info_text: str = "",
) -> QWidget:
    """Build a standardised sidebar control panel.

    Creates a QVBoxLayout with an optional section title, a list of controls,
    an optional accent-coloured primary action button, and an info label at
    the bottom.

    Parameters
    ----------
    title : str
        Section heading displayed at the top (e.g. "PARAMETERS").
    controls : list[dict]
        Each dict describes one control row.  Supported schemas:

        ``{"type": "slider", "label": str, "min": int, "max": int,
          "default": int, "id": str}``

        ``{"type": "combo", "label": str, "items": list[str],
          "default": str|int, "id": str}``

        ``{"type": "checkbox", "label": str, "checked": bool, "id": str}``

        ``{"type": "button", "label": str, "checkable": bool,
          "id": str}``

        ``{"type": "label", "text": str, "id": str}``

        The ``id`` key is used to store a reference on the returned
        widget as an attribute, e.g.  ``panel.k_slider`` when
        ``id="k_slider"``.

    width : int
        Fixed width for the panel (default 260).
    accent_button : str, optional
        If provided, creates a primary action button with this label.
    accent_callback : callable, optional
        Callback for the accent button ``clicked`` signal.
    stretch_at_end : bool
        Whether to add a stretch spacer before the info label.
    info_text : str
        Text for the bottom info label.

    Returns
    -------
    QWidget
        The fully constructed panel.  Control widgets are accessible as
        attributes named after their ``id`` values.
    """
    panel = QWidget()
    panel.setFixedWidth(width)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    # --- Section title ---
    title_lbl = QLabel(title.upper())
    title_lbl.setStyleSheet(_SIDEBAR_TITLE_STYLE)
    layout.addWidget(title_lbl)

    # --- Controls ---
    for spec in controls:
        ctrl_type = spec.get("type", "label")
        ctrl_id = spec.get("id")

        widget = None

        if ctrl_type == "slider":
            label = QLabel(spec.get("label", ""))
            layout.addWidget(label)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(spec.get("min", 0), spec.get("max", 100))
            slider.setValue(spec.get("default", 50))
            layout.addWidget(slider)

            # Optional value display label
            val_lbl = QLabel(str(spec.get("default", 50)))
            val_lbl.setStyleSheet(f"color: {Colors.ACCENT};")
            layout.addWidget(val_lbl)
            slider.valueChanged.connect(
                lambda v, lbl=val_lbl: lbl.setText(str(v))
            )

            widget = slider
            # Also store the value label for convenience
            if ctrl_id:
                val_id = f"{ctrl_id}_value_label"
                _set_attr(panel, val_id, val_lbl)

        elif ctrl_type == "combo":
            label = QLabel(spec.get("label", ""))
            layout.addWidget(label)

            combo = QComboBox()
            combo.addItems(spec.get("items", []))
            default = spec.get("default")
            if default is not None:
                combo.setCurrentText(str(default))
            layout.addWidget(combo)

            widget = combo

        elif ctrl_type == "checkbox":
            cb = QCheckBox(spec.get("label", ""))
            cb.setChecked(spec.get("checked", False))
            layout.addWidget(cb)

            widget = cb

        elif ctrl_type == "button":
            btn = QPushButton(spec.get("label", ""))
            btn.setCheckable(spec.get("checkable", False))
            if spec.get("outlined"):
                btn.setStyleSheet(_OUTLINED_BUTTON_STYLE)
            layout.addWidget(btn)

            widget = btn

        elif ctrl_type == "label":
            lbl = QLabel(spec.get("text", ""))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                spec.get("style", f"color: {Colors.TEXT_DIM}; font-size: 10px;")
            )
            layout.addWidget(lbl)

            widget = lbl

        # Store reference on the panel widget
        if ctrl_id and widget is not None:
            _set_attr(panel, ctrl_id, widget)

    # --- Accent (primary) button ---
    if accent_button:
        btn = QPushButton(accent_button)
        btn.setStyleSheet(_ACCENT_BUTTON_STYLE)
        if accent_callback:
            btn.clicked.connect(accent_callback)
        layout.addWidget(btn)
        _set_attr(panel, "_accent_button", btn)

    # --- Spacer ---
    if stretch_at_end:
        layout.addStretch()

    # --- Bottom info label ---
    if info_text:
        info = QLabel(info_text)
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px;")
        layout.addWidget(info)
        _set_attr(panel, "info_label", info)

    # --- Panel-wide stylesheet ---
    panel.setStyleSheet(_SIDEBAR_STYLE)

    return panel


# ---------------------------------------------------------------------------
# Convenience: styled QPushButton factory
# ---------------------------------------------------------------------------

def make_button(
    label: str,
    *,
    outlined: bool = False,
    accent: bool = False,
    checkable: bool = False,
    callback=None,
) -> QPushButton:
    """Create a pre-styled QPushButton.

    Parameters
    ----------
    label : str
        Button text.
    outlined : bool
        Use amber-outlined style instead of default.
    accent : bool
        Use filled accent (amber) style.
    checkable : bool
        Make the button checkable / toggleable.
    callback : callable, optional
        Connect to ``clicked`` signal.
    """
    btn = QPushButton(label)
    btn.setCheckable(checkable)
    if accent:
        btn.setStyleSheet(_ACCENT_BUTTON_STYLE)
    elif outlined:
        btn.setStyleSheet(_OUTLINED_BUTTON_STYLE)
    if callback:
        btn.clicked.connect(callback)
    return btn


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def clearLayout(layout):
    """Remove and delete all items/widgets from a QLayout.

    Handles nested layouts recursively — child layouts are cleared first,
    then their widgets are removed.  Spacer items are also removed.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        else:
            child_layout = item.layout()
            if child_layout is not None:
                clearLayout(child_layout)
                # Reparent child layout's widget (if any) to avoid orphans
                child_widget = child_layout.parentWidget()
                if child_widget and child_widget.layout() is child_layout:
                    child_widget.setLayout(None)
            # SpacerItem or other — just drop it


def apply_shadow(
    widget: QWidget,
    color: str = Colors.BORDER,
    radius: int = 8,
    offset: int = 2,
):
    """Apply a consistent drop-shadow effect to *widget*.

    Parameters
    ----------
    widget : QWidget
        Target widget (typically a card or panel).
    color : str
        Shadow colour in hex (default ``Colors.BORDER``).
    radius : int
        Blur radius in pixels.
    offset : int
        X/Y offset in pixels.
    """
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(radius)
    shadow.setOffset(offset, offset)
    shadow.setColor(QColor(color))
    widget.setGraphicsEffect(shadow)


def _set_attr(widget: QWidget, name: str, value):
    """Safely set a dynamic attribute on a QWidget instance."""
    try:
        setattr(widget, name, value)
    except AttributeError:
        # Shouldn't happen for plain QWidget subclasses but just in case
        object.__setattr__(widget, name, value)


# ---------------------------------------------------------------------------
# Usage examples
# ---------------------------------------------------------------------------

# Example: Spatial view controls
# -------------------------------
# panel = build_control_panel(
#     "Parameters",
#     [
#         {"type": "slider", "label": "Rooms (K):", "min": 2, "max": 12,
#          "default": 5, "id": "k_slider"},
#         {"type": "slider", "label": "Corridor curvature:", "min": 0,
#          "max": 50, "default": 20, "id": "curve_slider"},
#         {"type": "slider", "label": "Wing threshold:", "min": 10,
#          "max": 90, "default": 50, "id": "wing_slider"},
#         {"type": "button", "label": "Show Flow", "checkable": True,
#          "id": "flow_btn"},
#     ],
#     accent_button="Regenerate",
#     accent_callback=self._regenerate,
#     info_text="",
# )
# # Access controls:  panel.k_slider, panel.curve_slider, etc.
#
#
# Example: Toolbar
# ----------------
# toolbar, tb_layout = build_toolbar("EBM Energy Landscape",
#                                     subtitle="E(x) = -ln(...)")
# # Add custom widgets to tb_layout:
# tb_layout.addWidget(QLabel("Contours:"))
# self.contour_slider = QSlider(Qt.Horizontal)
# tb_layout.addWidget(self.contour_slider)
# layout.addWidget(toolbar)
#
#
# Example: Info bar
# -----------------
# info = build_info_bar("Hover splats to inspect")
# layout.addWidget(info)
# # Update later:  info.setText("New status message")
