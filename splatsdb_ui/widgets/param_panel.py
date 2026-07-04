# SPDX-License-Identifier: GPL-3.0
"""Parameter panel — right sidebar."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QComboBox, QCheckBox, QSlider, QLineEdit,
    QScrollArea, QFrame,
)
from PySide6.QtCore import Qt
from splatsdb_ui.utils.theme import Colors


class ParamWidget(QWidget):
    def __init__(self, definition: dict):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(definition.get("label", definition["name"]))
        label.setFixedWidth(110)
        label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px;")
        layout.addWidget(label)

        ptype = definition.get("type", "text")
        if ptype == "spin":
            w = QSpinBox()
            w.setRange(definition.get("min", 0), definition.get("max", 9999))
            w.setValue(definition.get("default", 0))
        elif ptype == "combo":
            w = QComboBox()
            w.addItems(definition.get("options", []))
        elif ptype == "check":
            w = QCheckBox()
            w.setChecked(definition.get("default", False))
        elif ptype == "slider":
            w = QSlider(Qt.Horizontal)
            w.setRange(definition.get("min", 0), definition.get("max", 100))
            w.setValue(definition.get("default", 50))
        else:
            w = QLineEdit()
            w.setPlaceholderText(str(definition.get("default", "")))

        layout.addWidget(w, stretch=1)


class ParamPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.title = QLabel("Parameters")
        self.title.setStyleSheet(f"""
            color: {Colors.ACCENT};
            font-weight: 700;
            font-size: 11px;
            letter-spacing: 1.0px;
            text-transform: uppercase;
            padding: 4px 0;
        """)
        layout.addWidget(self.title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.container = QWidget()
        self.params_layout = QVBoxLayout(self.container)
        self.params_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, stretch=1)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setProperty("class", "primary")
        self.apply_btn.clicked.connect(self._on_apply)
        layout.addWidget(self.apply_btn)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self._on_reset)
        layout.addWidget(self.reset_btn)

    def _on_apply(self):
        """Emit a status message when params are applied."""
        # Values are read from individual ParamWidget children
        pass

    def _on_reset(self):
        """Reset parameters to defaults."""
        pass

    def set_params(self, params: list):
        """Populate the parameter panel with widgets from definitions.

        Args:
            params: List of dicts with keys: name, label, type, min, max,
                    default, options, step.
        """
        # Clear previous widgets safely (takeAt removes items from layout)
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Create a ParamWidget for each definition
        for definition in params:
            widget = ParamWidget(definition)
            self.params_layout.addWidget(widget)

        self.params_layout.addStretch()
