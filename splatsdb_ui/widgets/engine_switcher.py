# SPDX-License-Identifier: GPL-3.0
"""Engine Switcher — LM Studio-style backend selector."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox
from PySide6.QtCore import Signal, QPropertyAnimation, QEasingCurve

from splatsdb_ui.engine_manager import EngineStatus
from splatsdb_ui.utils.icons import icon, icon_accent, icon_error, icon_success
from splatsdb_ui.utils.theme import Colors


DOT_COLORS = {
    EngineStatus.STOPPED:  Colors.TEXT_MUTED,
    EngineStatus.STARTING: Colors.WARNING,
    EngineStatus.RUNNING:  Colors.SUCCESS,
    EngineStatus.ERROR:    Colors.ERROR,
}


_DOT_STYLE_TEMPLATE = """
    QLabel {{
        background-color: {color};
        border-radius: 5px;
    }}
"""


class EngineSwitcher(QWidget):
    engine_selected = Signal(str)
    start_requested = Signal(str)
    stop_requested = Signal(str)
    add_requested = Signal()
    settings_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(44)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)
        layout.setSpacing(10)

        # Status dot (colored circle via QFrame)
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(10, 10)
        self._set_dot_color(Colors.TEXT_MUTED)
        layout.addWidget(self.status_dot)

        # Pulsing animation for STARTING status
        self._dot_anim = QPropertyAnimation(self.status_dot, b"windowOpacity")
        self._dot_anim.setDuration(1000)
        self._dot_anim.setStartValue(1.0)
        self._dot_anim.setEndValue(0.3)
        self._dot_anim.setEasingCurve(QEasingCurve.InOutSine)
        self._dot_anim.setLoopCount(-1)  # infinite

        # Engine combo
        self.engine_combo = QComboBox()
        self.engine_combo.setMinimumWidth(220)
        self.engine_combo.currentTextChanged.connect(self._on_engine_changed)
        layout.addWidget(self.engine_combo)

        # Type label
        self.type_label = QLabel("")
        self.type_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px; letter-spacing: 0.5px;")
        layout.addWidget(self.type_label)
        layout.addStretch()

        # Power button
        self.power_btn = QPushButton()
        self.power_btn.setFixedSize(30, 30)
        self.power_btn.setToolTip("Start / Stop engine")
        self.power_btn.clicked.connect(self._on_power)
        self._style_power(False)
        layout.addWidget(self.power_btn)

        # Add engine
        self.add_btn = QPushButton()
        self.add_btn.setIcon(icon("plus", Colors.TEXT_DIM))
        self.add_btn.setFixedSize(30, 30)
        self.add_btn.setToolTip("Add engine")
        self.add_btn.clicked.connect(self.add_requested.emit)
        self.add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background-color: {Colors.BG_OVERLAY}; }}
        """)
        layout.addWidget(self.add_btn)

        # Settings
        self.gear_btn = QPushButton()
        self.gear_btn.setIcon(icon("config", Colors.TEXT_DIM))
        self.gear_btn.setFixedSize(30, 30)
        self.gear_btn.setToolTip("Engine config")
        self.gear_btn.clicked.connect(lambda: self.settings_requested.emit(
            self.engine_combo.currentText()))
        self.gear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none; border-radius: 6px;
            }}
            QPushButton:hover {{ background-color: {Colors.BG_OVERLAY}; }}
        """)
        layout.addWidget(self.gear_btn)

        self.setStyleSheet(f"""
            QWidget {{ background-color: {Colors.BG_RAISED}; border-bottom: 1px solid {Colors.BORDER}; }}
        """)

    def _set_dot_color(self, color: str):
        self.status_dot.setStyleSheet(_DOT_STYLE_TEMPLATE.format(color=color))

    def _style_power(self, running: bool):
        if running:
            self.power_btn.setIcon(icon("stop", "#fca5a5"))
            self.power_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #991b1b; border: none;
                    border-radius: 6px;
                }}
                QPushButton:hover {{ background-color: #b91c1c; }}
            """)
        else:
            self.power_btn.setIcon(icon("play", Colors.BG))
            self.power_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {Colors.ACCENT}; border: none;
                    border-radius: 6px;
                }}
                QPushButton:hover {{ background-color: {Colors.ACCENT_BRIGHT}; }}
            """)

    def update_engines(self, engines: list, active_name: str = None):
        self.engine_combo.blockSignals(True)
        self.engine_combo.clear()
        for eng in engines:
            display = f"{eng.name}  ({eng.engine_type})"
            self.engine_combo.addItem(display, eng.name)
        if active_name:
            for i in range(self.engine_combo.count()):
                if self.engine_combo.itemData(i) == active_name:
                    self.engine_combo.setCurrentIndex(i)
                    break
        self.engine_combo.blockSignals(False)

    def update_status(self, name: str, status: EngineStatus):
        color = DOT_COLORS.get(status, Colors.TEXT_DIM)
        self._set_dot_color(color)
        self._style_power(status == EngineStatus.RUNNING)
        self.power_btn.setEnabled(status != EngineStatus.STARTING)
        if status == EngineStatus.STARTING:
            self._dot_anim.start()
        else:
            self._dot_anim.stop()
            self.status_dot.setWindowOpacity(1.0)

    def _on_engine_changed(self, text: str):
        idx = self.engine_combo.currentIndex()
        name = self.engine_combo.itemData(idx)
        if name:
            self.engine_selected.emit(name)

    def _on_power(self):
        idx = self.engine_combo.currentIndex()
        name = self.engine_combo.itemData(idx)
        if name:
            self.start_requested.emit(name)
