# SPDX-License-Identifier: GPL-3.0
"""Refined dark theme — high-contrast professional palette.

Design system:
  Base:   deep slate (#0B0F1A) — OLED-friendly, neutral (not purple)
  Raised: #131825 — cards, inputs
  Accent: emerald-cyan (#10B981) — calm, technical, high-contrast on dark
  Text:   #E2E8F0 primary, #94A3B8 secondary (WCAG AA on base)
  Style:  Linear / Vercel / Supabase inspired
"""

DARK_QSS = """
/* ── Global ────────────────────────────────────────────────── */
QWidget {
    background-color: #0B0F1A;
    color: #E2E8F0;
    font-family: "Inter", "SF Pro Display", "Segoe UI", sans-serif;
    font-size: 13px;
    selection-background-color: #10B981;
    selection-color: #0B0F1A;
}

QMainWindow {
    background-color: #0B0F1A;
}

/* ── Menu Bar ──────────────────────────────────────────────── */
QMenuBar {
    background-color: #0F1320;
    border-bottom: 1px solid #1E2433;
    padding: 2px 8px;
    font-size: 12px;
    color: #94A3B8;
}
QMenuBar::item {
    padding: 5px 12px;
    border-radius: 6px;
    color: #94A3B8;
}
QMenuBar::item:selected {
    background-color: #1A2030;
    color: #E2E8F0;
}
QMenu {
    background-color: #131825;
    border: 1px solid #1E2433;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 28px;
    border-radius: 6px;
    color: #CBD5E1;
}
QMenu::item:selected {
    background-color: #10B981;
    color: #0B0F1A;
    font-weight: 600;
}
QMenu::separator {
    height: 1px;
    background: #1E2433;
    margin: 4px 8px;
}

/* ── Tab Bar ───────────────────────────────────────────────── */
QTabWidget::pane {
    border: none;
    background-color: #0B0F1A;
}
QTabBar {
    background-color: #0F1320;
    border-bottom: 1px solid #1E2433;
    qproperty-drawBase: 0;
}
QTabBar::tab {
    background-color: transparent;
    padding: 10px 18px;
    margin-right: 0px;
    margin-bottom: 0px;
    color: #64748B;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.3px;
}
QTabBar::tab:selected {
    color: #10B981;
    border-bottom: 2px solid #10B981;
    background-color: rgba(16, 185, 129, 0.04);
}
QTabBar::tab:hover:!selected {
    color: #CBD5E1;
    background-color: rgba(255, 255, 255, 0.03);
}

/* ── Buttons ───────────────────────────────────────────────── */
QPushButton {
    background-color: #1A2030;
    border: 1px solid #2A3041;
    border-radius: 8px;
    padding: 7px 16px;
    color: #CBD5E1;
    font-weight: 500;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #242B3D;
    border-color: #3B4356;
    color: #E2E8F0;
}
QPushButton:pressed {
    background-color: #131825;
}
QPushButton:disabled {
    color: #475569;
    background-color: #131825;
    border-color: #1E2433;
}
QPushButton[primary="true"],
QPushButton[class="primary"] {
    background-color: #10B981;
    border-color: #059669;
    color: #0B0F1A;
    font-weight: 600;
}
QPushButton[primary="true"]:hover,
QPushButton[class="primary"]:hover {
    background-color: #34D399;
    border-color: #10B981;
}
QPushButton[primary="true"]:pressed,
QPushButton[class="primary"]:pressed {
    background-color: #059669;
}
QPushButton[danger="true"] {
    background-color: #7F1D1D;
    border-color: #991B1B;
    color: #FCA5A5;
}
QPushButton[danger="true"]:hover {
    background-color: #991B1B;
    border-color: #DC2626;
    color: #FEE2E2;
}

/* ── Input ─────────────────────────────────────────────────── */
QLineEdit {
    background-color: #0F1320;
    border: 1px solid #1E2433;
    border-radius: 8px;
    padding: 8px 12px;
    color: #E2E8F0;
    selection-background-color: #10B981;
    selection-color: #0B0F1A;
}
QLineEdit:hover {
    border-color: #2A3041;
}
QLineEdit:focus {
    border-color: #10B981;
    background-color: #131825;
}
QLineEdit:disabled {
    color: #475569;
    background-color: #0B0F1A;
}

QTextEdit, QPlainTextEdit {
    background-color: #0F1320;
    border: 1px solid #1E2433;
    border-radius: 8px;
    padding: 10px;
    color: #E2E8F0;
}
QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #10B981;
}

/* ── Spin / Combo ──────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {
    background-color: #0F1320;
    border: 1px solid #1E2433;
    border-radius: 8px;
    padding: 6px 10px;
    color: #E2E8F0;
    min-height: 20px;
}
QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: #2A3041;
}
QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #10B981;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    border: none;
    background: transparent;
    width: 22px;
    subcontrol-position: top right;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    border: none;
    background: transparent;
    width: 22px;
    subcontrol-position: bottom right;
}
QSpinBox::up-arrow {
    width: 8px; height: 8px;
    image: none;
}
QSpinBox::down-arrow {
    width: 8px; height: 8px;
    image: none;
}

QComboBox {
    background-color: #0F1320;
    border: 1px solid #1E2433;
    border-radius: 8px;
    padding: 6px 12px;
    color: #E2E8F0;
    min-height: 20px;
}
QComboBox:hover {
    border-color: #2A3041;
}
QComboBox:focus {
    border-color: #10B981;
}
QComboBox::drop-down {
    border: none;
    width: 28px;
    border-left: 1px solid #1E2433;
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: transparent;
}
QComboBox::drop-down:hover {
    background-color: #1A2030;
}
QComboBox QAbstractItemView {
    background-color: #131825;
    border: 1px solid #2A3041;
    border-radius: 8px;
    selection-background-color: #10B981;
    selection-color: #0B0F1A;
    outline: none;
    padding: 4px;
}

/* ── Checkbox ──────────────────────────────────────────────── */
QCheckBox {
    spacing: 10px;
    color: #CBD5E1;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1.5px solid #2A3041;
    background-color: #0F1320;
}
QCheckBox::indicator:hover {
    border-color: #3B4356;
}
QCheckBox::indicator:checked {
    background-color: #10B981;
    border-color: #059669;
}

/* ── Slider ────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 6px;
    background: #1E2433;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #10B981;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    width: 18px;
    height: 18px;
    background: #10B981;
    border: 3px solid #0B0F1A;
    border-radius: 9px;
    margin: -7px 0;
}
QSlider::handle:horizontal:hover {
    background: #34D399;
}

/* ── Group Box ─────────────────────────────────────────────── */
QGroupBox {
    font-weight: 600;
    color: #94A3B8;
    border: 1px solid #1E2433;
    border-radius: 12px;
    margin-top: 16px;
    padding: 20px 14px 10px 14px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: #64748B;
}

/* ── Scroll Area ───────────────────────────────────────────── */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: #2A3041;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #3B4356;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px 4px;
}
QScrollBar::handle:horizontal {
    background: #2A3041;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background: #3B4356;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

/* ── Progress Bar ──────────────────────────────────────────── */
QProgressBar {
    background-color: #0F1320;
    border: 1px solid #1E2433;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #10B981;
    border-radius: 3px;
}

/* ── Splitter ──────────────────────────────────────────────── */
QSplitter::handle {
    background: #131825;
}
QSplitter::handle:horizontal {
    width: 2px;
}
QSplitter::handle:vertical {
    height: 2px;
}
QSplitter::handle:hover {
    background: #10B981;
}

/* ── Tree / Table / List ───────────────────────────────────── */
QTreeWidget, QTableWidget, QListView {
    background-color: #0B0F1A;
    border: 1px solid #1E2433;
    border-radius: 8px;
    color: #CBD5E1;
    outline: none;
    gridline-color: #131825;
}
QTreeWidget::item, QListView::item {
    padding: 6px 10px;
    border-bottom: 1px solid #0F1320;
}
QTreeWidget::item:selected, QListView::item:selected,
QTableWidget::item:selected {
    background-color: rgba(16, 185, 129, 0.12);
    color: #34D399;
}
QTreeWidget::item:hover, QListView::item:hover,
QTableWidget::item:hover {
    background-color: rgba(255, 255, 255, 0.03);
}
QHeaderView::section {
    background-color: #0F1320;
    border: none;
    border-bottom: 1px solid #1E2433;
    border-right: 1px solid #0B0F1A;
    padding: 8px 12px;
    color: #64748B;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ── Status Bar ────────────────────────────────────────────── */
QStatusBar {
    background-color: #0F1320;
    border-top: 1px solid #1E2433;
    color: #64748B;
    font-size: 11px;
    padding: 2px 8px;
}
QStatusBar::item {
    border: none;
}

/* ── Tooltip ───────────────────────────────────────────────── */
QToolTip {
    background-color: #131825;
    border: 1px solid #2A3041;
    color: #E2E8F0;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 12px;
}

/* ── Frame / Card ──────────────────────────────────────────── */
QFrame[class="card"] {
    background-color: #0F1320;
    border: 1px solid #1E2433;
    border-radius: 12px;
    padding: 16px;
}
"""

# Color palette constants for programmatic use
class Colors:
    BG          = "#0B0F1A"
    BG_RAISED   = "#0F1320"
    BG_OVERLAY  = "#131825"
    BG_INSET    = "#080B14"
    BG_HOVER    = "#1A2030"

    BORDER      = "#1E2433"
    BORDER_LITE = "#2A3041"
    BORDER_FOCUS= "#10B981"

    TEXT        = "#E2E8F0"
    TEXT_DIM    = "#94A3B8"
    TEXT_MUTED  = "#64748B"
    TEXT_FAINT  = "#475569"

    ACCENT      = "#10B981"
    ACCENT_BRIGHT = "#34D399"
    ACCENT_DARK = "#059669"

    SUCCESS     = "#10B981"
    WARNING     = "#F59E0B"
    ERROR       = "#EF4444"
    INFO        = "#3B82F6"

    def for_status(status: str) -> str:
        return {
            "running": Colors.SUCCESS,
            "starting": Colors.WARNING,
            "stopped": Colors.TEXT_MUTED,
            "error": Colors.ERROR,
        }.get(status, Colors.TEXT_DIM)


def load_theme() -> str:
    return DARK_QSS
