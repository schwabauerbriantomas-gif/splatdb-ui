# SPDX-License-Identifier: GPL-3.0
"""Parameter panel — right sidebar that adapts to the active view.

Each view defines get_params() -> list[dict]. When the user switches tabs,
MainWindow calls param_panel.set_params_from_view(view) to populate it.
Apply emits a signal with collected values; Reset restores defaults.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QSlider, QLineEdit,
    QScrollArea, QFrame,
)
from PySide6.QtCore import Qt, Signal
from splatsdb_ui.utils.theme import Colors


class ParamWidget(QFrame):
    """A single labeled parameter control."""

    def __init__(self, definition: dict):
        super().__init__()
        self.definition = definition
        self._default = definition.get("default")
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(f"""
            ParamWidget {{
                background-color: transparent;
                border: none;
                border-bottom: 1px solid {Colors.BG_RAISED};
                padding: 2px 0;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(4)

        # Label row
        label_text = self.definition.get("label", self.definition["name"])
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase;")
        layout.addWidget(label)

        # Control row
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setSpacing(8)

        ptype = self.definition.get("type", "text")

        if ptype == "spin":
            self.control = QSpinBox()
            self.control.setRange(self.definition.get("min", 0), self.definition.get("max", 9999))
            self.control.setValue(self.definition.get("default", 0))
            ctrl_layout.addWidget(self.control, stretch=1)

        elif ptype == "float":
            self.control = QDoubleSpinBox()
            self.control.setRange(self.definition.get("min", 0.0), self.definition.get("max", 1.0))
            self.control.setSingleStep(self.definition.get("step", 0.01))
            self.control.setDecimals(self.definition.get("decimals", 2))
            self.control.setValue(self.definition.get("default", 0.0))
            ctrl_layout.addWidget(self.control, stretch=1)

        elif ptype == "combo":
            self.control = QComboBox()
            self.control.addItems(self.definition.get("options", []))
            default = self.definition.get("default")
            if default and isinstance(default, str):
                idx = self.control.findText(default)
                if idx >= 0:
                    self.control.setCurrentIndex(idx)
            ctrl_layout.addWidget(self.control, stretch=1)

        elif ptype == "check":
            self.control = QCheckBox()
            self.control.setChecked(self.definition.get("default", False))
            label2 = QLabel("Enabled")
            label2.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
            ctrl_layout.addWidget(self.control)
            ctrl_layout.addWidget(label2)
            ctrl_layout.addStretch()

        elif ptype == "slider":
            self.control = QSlider(Qt.Horizontal)
            self.control.setRange(self.definition.get("min", 0), self.definition.get("max", 100))
            self.control.setValue(self.definition.get("default", 50))
            self._value_label = QLabel(str(self.control.value()))
            self._value_label.setFixedWidth(36)
            self._value_label.setStyleSheet(f"color: {Colors.ACCENT}; font-size: 11px; font-weight: 600;")
            self._value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.control.valueChanged.connect(lambda v: self._value_label.setText(str(v)))
            ctrl_layout.addWidget(self.control, stretch=1)
            ctrl_layout.addWidget(self._value_label)

        else:  # text
            self.control = QLineEdit()
            self.control.setPlaceholderText(str(self.definition.get("default", "")))
            ctrl_layout.addWidget(self.control, stretch=1)

        layout.addLayout(ctrl_layout)

    def value(self):
        """Get current value from the control."""
        from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QSlider, QLineEdit
        if isinstance(self.control, (QSpinBox, QSlider)):
            return self.control.value()
        elif isinstance(self.control, QDoubleSpinBox):
            return self.control.value()
        elif isinstance(self.control, QComboBox):
            return self.control.currentText()
        elif isinstance(self.control, QCheckBox):
            return self.control.isChecked()
        elif isinstance(self.control, QLineEdit):
            return self.control.text()
        return None

    def reset(self):
        """Reset control to default value."""
        from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QSlider, QLineEdit
        default = self._default
        if isinstance(self.control, (QSpinBox, QSlider)):
            self.control.setValue(default if default is not None else self.control.minimum())
        elif isinstance(self.control, QDoubleSpinBox):
            self.control.setValue(default if default is not None else 0.0)
        elif isinstance(self.control, QComboBox):
            if isinstance(default, str):
                idx = self.control.findText(default)
                if idx >= 0:
                    self.control.setCurrentIndex(idx)
        elif isinstance(self.control, QCheckBox):
            self.control.setChecked(bool(default))
        elif isinstance(self.control, QLineEdit):
            self.control.setText("")


class EmptyState(QFrame):
    """A centered empty-state placeholder with icon, title, and subtitle."""

    def __init__(self, title: str = "Nothing here yet", subtitle: str = ""):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        icon_label = QLabel("⌖")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(f"font-size: 36px; color: {Colors.TEXT_MUTED};")
        layout.addWidget(icon_label)

        t = QLabel(title)
        t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet(f"color: {Colors.TEXT}; font-size: 14px; font-weight: 600;")
        layout.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setAlignment(Qt.AlignCenter)
            s.setWordWrap(True)
            s.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px;")
            layout.addWidget(s)


class ParamPanel(QWidget):
    """Right sidebar parameter panel that adapts to the active view."""

    params_applied = Signal(dict)  # view_id -> {param_name: value}

    def __init__(self):
        super().__init__()
        self._current_view_id: str = ""
        self._param_widgets: dict[str, ParamWidget] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(10)

        self.header = QLabel("PARAMETERS")
        self.header.setStyleSheet(f"""
            color: {Colors.ACCENT};
            font-weight: 700;
            font-size: 10px;
            letter-spacing: 1.2px;
        """)
        layout.addWidget(self.header)

        self.view_label = QLabel("No view selected")
        self.view_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px; padding-bottom: 4px;")
        layout.addWidget(self.view_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}")

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.params_layout = QVBoxLayout(self.container)
        self.params_layout.setAlignment(Qt.AlignTop)
        self.params_layout.setSpacing(2)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, stretch=1)

        # Apply + Reset in a row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.clicked.connect(self._on_reset)
        btn_row.addWidget(self.reset_btn)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setProperty("class", "primary")
        self.apply_btn.clicked.connect(self._on_apply)
        btn_row.addWidget(self.apply_btn)

        layout.addLayout(btn_row)

        self.setStyleSheet(f"""
            ParamPanel {{
                background-color: {Colors.BG_RAISED};
                border-left: 1px solid {Colors.BORDER};
            }}
        """)

    def set_params_from_view(self, view_id: str, view=None):
        """Populate parameters from a view's get_params() method."""
        self._current_view_id = view_id
        self._param_widgets.clear()

        # Clear previous widgets safely
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get params from the view
        params = []
        if view is not None and hasattr(view, "get_params"):
            try:
                params = view.get_params() or []
            except Exception:
                params = []

        if not params:
            empty = QLabel("No parameters for this view")
            empty.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px; padding: 20px;")
            empty.setAlignment(Qt.AlignCenter)
            self.params_layout.addWidget(empty)
            self.view_label.setText(view_id.title() if view_id else "")
            self.params_layout.addStretch()
            return

        # Title-case view name
        self.view_label.setText(view_id.replace("_", " ").title())

        for definition in params:
            name = definition.get("name", definition.get("label", "param"))
            widget = ParamWidget(definition)
            self._param_widgets[name] = widget
            self.params_layout.addWidget(widget)

        self.params_layout.addStretch()

    def collect_values(self) -> dict:
        """Collect all current parameter values."""
        return {name: widget.value() for name, widget in self._param_widgets.items()}

    def _on_apply(self):
        """Emit collected parameter values."""
        values = self.collect_values()
        if self._current_view_id:
            self.params_applied.emit({self._current_view_id: values})

    def _on_reset(self):
        """Reset all parameters to defaults."""
        for widget in self._param_widgets.values():
            widget.reset()
