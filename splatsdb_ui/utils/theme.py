# SPDX-License-Identifier: GPL-3.0
"""Dark theme — refined professional palette.

Base: deep blue-gray (not purple)
Accent: warm amber
Style: JetBrains / Linear / Vercel inspired
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen, QBrush, QLinearGradient, QRadialGradient

DARK_QSS = """
/* ── Global ────────────────────────────────────────────────── */
QWidget {
    background-color: #0f1117;
    color: #d1d5db;
    font-family: "Inter", "Segoe UI", "SF Pro", sans-serif;
    font-size: 13px;
    selection-background-color: #f59e0b;
    selection-color: #0f1117;
}

QMainWindow {
    background-color: #0f1117;
}

/* ── Menu Bar ──────────────────────────────────────────────── */
QMenuBar {
    background-color: #161b22;
    border-bottom: 1px solid #21262d;
    padding: 2px 8px;
    font-size: 12px;
}
QMenuBar::item {
    padding: 4px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background-color: #21262d;
}
QMenu {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #f59e0b;
    color: #0f1117;
}
QMenu::separator {
    height: 1px;
    background: #21262d;
    margin: 4px 8px;
}

/* ── Tab Bar ───────────────────────────────────────────────── */
QTabWidget::pane {
    border: 1px solid #21262d;
    border-top: none;
    border-radius: 0 0 8px 8px;
    background-color: #0f1117;
    padding: 4px;
}
QTabBar {
    background-color: #161b22;
    border-bottom: 1px solid #21262d;
}
QTabBar::tab {
    background-color: transparent;
    padding: 8px 20px;
    margin-right: 2px;
    color: #6b7280;
    border: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.3px;
}
QTabBar::tab:selected {
    color: #f59e0b;
    background-color: rgba(245, 158, 11, 0.06);
    border-bottom: 2px solid #f59e0b;
}
QTabBar::tab:hover:!selected {
    color: #d1d5db;
    background-color: rgba(255,255,255,0.04);
    border-bottom: 2px solid #30363d;
}
QTabBar::tab:!selected {
    margin-top: 2px;
}
QTabBar::tab:selected {
    margin-top: 0px;
}
QTabBar::tab:scrolled {
    color: #484f58;
}

/* ── Buttons ───────────────────────────────────────────────── */
QPushButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 14px;
    color: #d1d5db;
    font-weight: 500;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #484f58;
}
QPushButton:pressed {
    background-color: #161b22;
}
QPushButton:disabled {
    color: #484f58;
    background-color: #161b22;
}
QToolButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 14px;
    color: #d1d5db;
    font-weight: 500;
    font-size: 12px;
}
QToolButton:hover {
    background-color: #30363d;
    border-color: #484f58;
}
QToolButton:pressed {
    background-color: #161b22;
}
QToolButton:disabled {
    color: #484f58;
    background-color: #161b22;
}
QPushButton[primary="true"],
QPushButton[class="primary"] {
    background-color: #f59e0b;
    border-color: #d97706;
    color: #0f1117;
    font-weight: 600;
}
QPushButton[primary="true"]:hover,
QPushButton[class="primary"]:hover {
    background-color: #fbbf24;
}
QPushButton[danger="true"] {
    background-color: #991b1b;
    border-color: #dc2626;
    color: #fca5a5;
}
QPushButton[danger="true"]:hover {
    background-color: #b91c1c;
}

/* ── Input ─────────────────────────────────────────────────── */
QLineEdit {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 6px;
    padding: 6px 12px;
    color: #d1d5db;
    selection-background-color: #f59e0b;
    selection-color: #0f1117;
}
QLineEdit:focus {
    border-color: #f59e0b;
}

QTextEdit, QPlainTextEdit {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 6px;
    padding: 8px;
    color: #d1d5db;
}
QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #f59e0b;
}

/* ── Spin / Combo ──────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 6px;
    padding: 4px 8px;
    color: #d1d5db;
    min-height: 24px;
}
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #30363d;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #f59e0b;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    border: none;
    border-left: 1px solid #21262d;
    border-top-right-radius: 5px;
    background: transparent;
    width: 20px;
    height: 12px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {
    background-color: rgba(245, 158, 11, 0.1);
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    width: 8px;
    height: 8px;
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid #6b7280;
}
QSpinBox::up-button:hover QSpinBox::up-arrow,
QSpinBox::up-button:hover QDoubleSpinBox::up-arrow,
QDoubleSpinBox::up-button:hover QDoubleSpinBox::up-arrow {
    border-bottom-color: #f59e0b;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    border: none;
    border-left: 1px solid #21262d;
    border-bottom-right-radius: 5px;
    background: transparent;
    width: 20px;
    height: 12px;
}
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: rgba(245, 158, 11, 0.1);
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    width: 8px;
    height: 8px;
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #6b7280;
}
QSpinBox::down-button:hover QSpinBox::down-arrow,
QSpinBox::down-button:hover QDoubleSpinBox::down-arrow,
QDoubleSpinBox::down-button:hover QDoubleSpinBox::down-arrow {
    border-top-color: #f59e0b;
}

QComboBox {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 6px;
    padding: 4px 12px;
    color: #d1d5db;
    min-height: 24px;
}
QComboBox:hover {
    border-color: #484f58;
}
QComboBox:focus {
    border-color: #f59e0b;
}
QComboBox:on {
    border-color: #f59e0b;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    border: none;
    border-left: 1px solid #21262d;
    width: 24px;
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
}
QComboBox::down-arrow {
    width: 0;
    height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #6b7280;
}
QComboBox:hover::down-arrow {
    border-top-color: #d1d5db;
}
QComboBox:on::down-arrow {
    border-top-color: #f59e0b;
}
QComboBox QAbstractItemView {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    selection-background-color: rgba(245, 158, 11, 0.15);
    selection-color: #f59e0b;
    outline: none;
    padding: 4px;
}
QComboBox QAbstractItemView::item {
    padding: 6px 12px;
    min-height: 24px;
    border-radius: 4px;
}
QComboBox QAbstractItemView::item:hover {
    background-color: rgba(255,255,255,0.04);
}
QComboBox QAbstractItemView::item:selected {
    background-color: rgba(245, 158, 11, 0.15);
    color: #f59e0b;
}

/* ── Checkbox ──────────────────────────────────────────────── */
QCheckBox {
    spacing: 8px;
    color: #d1d5db;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #30363d;
    background-color: #161b22;
}
QCheckBox::indicator:hover {
    border-color: #484f58;
}
QCheckBox::indicator:unchecked {
    background-color: #161b22;
    border-color: #30363d;
}
QCheckBox::indicator:checked {
    background-color: #f59e0b;
    border-color: #d97706;
}

/* ── Slider ────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 4px;
    background: #21262d;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    background: #f59e0b;
    border-radius: 7px;
    margin: -5px 0;
}

/* ── Group Box ─────────────────────────────────────────────── */
QGroupBox {
    font-weight: 600;
    color: #9ca3af;
    border: 1px solid #21262d;
    border-radius: 8px;
    margin-top: 16px;
    padding: 18px 12px 10px 12px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}
QGroupBox:hover {
    border-color: #30363d;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    top: -1px;
    padding: 0 8px;
    color: #6b7280;
}
QGroupBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #30363d;
    background-color: #161b22;
    margin-right: 6px;
}
QGroupBox::indicator:checked {
    background-color: #f59e0b;
    border-color: #d97706;
}
QGroupBox::indicator:hover {
    border-color: #484f58;
}

/* ── Scroll Area ───────────────────────────────────────────── */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: #21262d;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #f59e0b;
}
QScrollBar::handle:vertical:pressed {
    background: #d97706;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}
QScrollBar::up-arrow:vertical, QScrollBar::down-arrow:vertical {
    width: 0;
    height: 0;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 2px 4px;
}
QScrollBar::handle:horizontal {
    background: #21262d;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background: #f59e0b;
}
QScrollBar::handle:horizontal:pressed {
    background: #d97706;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}
QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal {
    width: 0;
    height: 0;
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}

/* ── Progress Bar ──────────────────────────────────────────── */
QProgressBar {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
    font-size: 0px;
}
QProgressBar::chunk {
    background-color: #f59e0b;
    border-radius: 3px;
}

/* ── Splitter ──────────────────────────────────────────────── */
QSplitter::handle {
    background: #21262d;
}
QSplitter::handle:horizontal {
    width: 1px;
}
QSplitter::handle:vertical {
    height: 1px;
}
QSplitter::handle:hover {
    background: #f59e0b;
}

/* ── Tree / List ───────────────────────────────────────────── */
QTableWidget {
    gridline-color: #21262d;
    alternate-background-color: rgba(255,255,255,0.02);
}
QTreeWidget, QListView {
    background-color: #0f1117;
    border: none;
    color: #d1d5db;
    outline: none;
}
QTreeWidget::item, QListView::item {
    padding: 4px 8px;
    border-radius: 4px;
}
QTreeWidget::item:selected, QListView::item:selected {
    background-color: rgba(245, 158, 11, 0.12);
    color: #f59e0b;
}
QTreeWidget::item:hover, QListView::item:hover {
    background-color: rgba(255,255,255,0.03);
}
QHeaderView::section {
    background-color: #161b22;
    border: none;
    border-bottom: 1px solid #21262d;
    padding: 6px 12px;
    color: #6b7280;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ── Status Bar ────────────────────────────────────────────── */
QStatusBar {
    background-color: #161b22;
    border-top: 1px solid #21262d;
    color: #6b7280;
    font-size: 11px;
    padding: 2px 8px;
}

/* ── Tooltip ───────────────────────────────────────────────── */
QToolTip {
    background-color: #161b22;
    border: 1px solid #30363d;
    color: #d1d5db;
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 12px;
}

/* ── Frame / Card ──────────────────────────────────────────── */
QFrame[class="card"] {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 8px;
    padding: 12px;
}
QFrame[class="card"] QLabel {
    background: transparent;
}
"""

# Color palette constants for programmatic use
class Colors:
    BG          = "#0f1117"
    BG_RAISED   = "#161b22"
    BG_OVERLAY  = "#21262d"
    BG_HOVER    = "#30363d"
    BORDER      = "#21262d"
    BORDER_LITE = "#30363d"

    TEXT        = "#d1d5db"
    TEXT_DIM    = "#6b7280"
    TEXT_MUTED  = "#484f58"

    ACCENT      = "#f59e0b"
    ACCENT_BRIGHT = "#fbbf24"
    ACCENT_DARK = "#d97706"

    SUCCESS     = "#22c55e"
    WARNING     = "#eab308"
    ERROR       = "#ef4444"
    INFO        = "#3b82f6"

    # Semantic palette
    CONFIDENCE_HIGH = "#22c55e"    # green
    CONFIDENCE_MOD  = "#f59e0b"    # amber
    CONFIDENCE_LOW  = "#ef4444"    # red

    # Thermal heatmap anchor colors
    THERMAL_COLD    = "#0a1450"    # deep blue
    THERMAL_TEAL    = "#1e5078"    # dark teal
    THERMAL_GREEN   = "#1ea050"    # green
    THERMAL_AMBER   = "#f0a020"    # amber/orange
    THERMAL_HOT     = "#f03020"    # crimson

    # 3D axis colors
    AXIS_X = "#ef4444"
    AXIS_Y = "#22c55e"
    AXIS_Z = "#3b82f6"

    # FPS indicator colors
    FPS_GOOD    = "#22c55e"
    FPS_OK      = "#facc15"
    FPS_BAD     = "#ef4444"

    # Celestial background gradient
    CELESTIAL_TOP    = "#0a0e1a"
    CELESTIAL_BOTTOM = "#0f1117"

    @staticmethod
    def for_status(status: str) -> str:
        return {
            "running": Colors.SUCCESS,
            "starting": Colors.WARNING,
            "stopped": Colors.TEXT_MUTED,
            "error": Colors.ERROR,
        }.get(status, Colors.TEXT_DIM)

    # ── Color manipulation helpers ──────────────────────────────

    @staticmethod
    def lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
        """Linear interpolation between two colors, clamped to valid range."""
        t = max(0.0, min(1.0, t))
        return QColor(
            max(0, min(255, int(c1.red()   + (c2.red()   - c1.red())   * t))),
            max(0, min(255, int(c1.green() + (c2.green() - c1.green()) * t))),
            max(0, min(255, int(c1.blue()  + (c2.blue()  - c1.blue())  * t))),
            max(0, min(255, int(c1.alpha() + (c2.alpha() - c1.alpha()) * t))),
        )

    @staticmethod
    def with_alpha(color: QColor, alpha: int) -> QColor:
        """Return a copy of *color* with the given alpha (0-255, clamped)."""
        c = QColor(color)
        c.setAlpha(max(0, min(255, alpha)))
        return c

    @staticmethod
    def alpha(color_str: str, alpha_int: int = 255) -> QColor:
        """Return a QColor from a hex string with the given alpha (0–255)."""
        c = QColor(color_str)
        c.setAlpha(alpha_int)
        return c

    @staticmethod
    def pen(color_str: str, width: float = 1.0,
            style=Qt.PenStyle.SolidLine) -> QPen:
        """Create a QPen from a hex colour string."""
        return QPen(QColor(color_str), width, style)

    @staticmethod
    def brush(color_str: str, alpha: int = 255) -> QBrush:
        """Create a QBrush from a hex colour string with optional alpha."""
        c = QColor(color_str)
        c.setAlpha(alpha)
        return QBrush(c)

    @staticmethod
    def linear_gradient(x1: float, y1: float, x2: float, y2: float,
                        *stops: tuple) -> QLinearGradient:
        """Create a QLinearGradient.

        *stops* are (position: float, color_str: str) pairs, e.g.
        ``Colors.linear_gradient(0, 0, 1, 0, (0.0, "#f59e0b"), (1.0, "#d97706"))``
        """
        g = QLinearGradient(x1, y1, x2, y2)
        for pos, col in stops:
            g.setColorAt(pos, QColor(col))
        return g

    @staticmethod
    def radial_gradient(cx: float, cy: float, radius: float,
                        *stops: tuple) -> QRadialGradient:
        """Create a QRadialGradient.

        *stops* are (position: float, color_str: str) pairs.
        """
        g = QRadialGradient(cx, cy, radius)
        for pos, col in stops:
            g.setColorAt(pos, QColor(col))
        return g


def load_theme() -> str:
    return DARK_QSS
