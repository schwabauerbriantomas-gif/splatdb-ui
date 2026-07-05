# SPDX-License-Identifier: GPL-3.0
"""Config Editor — full SplatDB configuration editor.

Shows ALL 60+ config parameters grouped by category.
Supports preset loading and custom editing.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QFrame, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QLineEdit, QTabWidget,
    QFormLayout, QSizePolicy, QSplitter,
)
from PySide6.QtCore import Signal, Qt

from splatsdb_ui.engine_manager import CONFIG_FIELDS, PRESETS


class ConfigEditor(QWidget):
    """Full SplatDB configuration editor — all parameters."""

    config_changed = Signal(dict)
    preset_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self._values = {}
        self._widgets = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Preset selector bar
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        for name, data in PRESETS.items():
            desc = data.get("description", "")
            self.preset_combo.addItem(f"{name} — {desc}", name)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        preset_row.addWidget(self.preset_combo, stretch=1)
        layout.addLayout(preset_row)

        # Scrollable config groups
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        self._form_layout = QVBoxLayout(container)
        self._form_layout.setSpacing(12)

        # Group fields by group name
        groups = {}
        for field_name, meta in CONFIG_FIELDS.items():
            group_name = meta.get("group", "Other")
            if group_name not in groups:
                groups[group_name] = []
            groups[group_name].append((field_name, meta))

        # Build group boxes
        for group_name, fields in groups.items():
            group_box = QGroupBox(group_name)
            group_box.setStyleSheet("""
                QGroupBox {
                    font-weight: 600;
                    color: #f9a825;
                    border: 1px solid #313244;
                    border-radius: 6px;
                    margin-top: 12px;
                    padding-top: 16px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    padding: 0 6px;
                }
            """)
            form = QFormLayout(group_box)
            form.setSpacing(6)
            form.setLabelAlignment(Qt.AlignRight)

            for field_name, meta in fields:
                widget = self._create_field_widget(field_name, meta)
                label_text = meta.get("label", field_name)
                form.addRow(f"{label_text}:", widget)
                self._widgets[field_name] = widget

            self._form_layout.addWidget(group_box)

        self._form_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

    def _create_field_widget(self, name: str, meta: dict) -> QWidget:
        ftype = meta.get("type", "text")
        if ftype == "spin":
            w = QSpinBox()
            max_val = min(meta.get("max", 99999), 2147483647)
            w.setRange(meta.get("min", 0), max_val)
            w.setSingleStep(meta.get("step", 1))
            w.valueChanged.connect(lambda v, n=name: self._on_value_changed(n, v))
        elif ftype == "float":
            w = QDoubleSpinBox()
            w.setRange(meta.get("min", 0.0), meta.get("max", 99999.0))
            w.setDecimals(4)
            w.setSingleStep(meta.get("step", 0.01))
            w.valueChanged.connect(lambda v, n=name: self._on_value_changed(n, v))
        elif ftype == "combo":
            w = QComboBox()
            w.addItems(meta.get("options", []))
            w.currentTextChanged.connect(lambda v, n=name: self._on_value_changed(n, v))
        elif ftype == "check":
            w = QCheckBox()
            w.stateChanged.connect(lambda v, n=name: self._on_value_changed(n, bool(v)))
        else:
            w = QLineEdit()
            w.textChanged.connect(lambda v, n=name: self._on_value_changed(n, v))
        return w

    def _on_value_changed(self, name: str, value):
        self._values[name] = value

    def _on_preset_changed(self, index: int):
        preset_name = self.preset_combo.currentData()
        if preset_name:
            self.load_preset(preset_name)
            self.preset_selected.emit(preset_name)

    def load_preset(self, preset_name: str):
        """Load a preset configuration into the editor."""
        preset_data = PRESETS.get(preset_name, {})
        for name, value in preset_data.items():
            if name == "description":
                continue
            self.set_value(name, value)

    def set_values(self, values: dict):
        """Set multiple values at once."""
        for name, value in values.items():
            self.set_value(name, value)

    def set_value(self, name: str, value):
        """Set a single field value."""
        widget = self._widgets.get(name)
        if not widget:
            return
        if isinstance(widget, QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(value))
        elif isinstance(widget, QComboBox):
            idx = widget.findText(str(value))
            if idx >= 0:
                widget.setCurrentIndex(idx)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))
        self._values[name] = value

    def get_values(self) -> dict:
        """Get current config as dict."""
        return self._values.copy()
