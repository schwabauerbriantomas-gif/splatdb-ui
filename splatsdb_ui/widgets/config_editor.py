# SPDX-License-Identifier: GPL-3.0
"""Config Editor — full SplatsDB configuration editor.

Shows ALL 60+ config parameters grouped by category.
Supports preset loading, search, validation, and custom editing.
"""

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QFrame, QComboBox, QSpinBox,
    QDoubleSpinBox, QCheckBox, QLineEdit, QTabWidget,
    QFormLayout, QSizePolicy, QSplitter,
)
from PySide6.QtCore import Signal, Qt, QTimer, QPoint
from PySide6.QtGui import QToolTip

from splatsdb_ui.engine_manager import CONFIG_FIELDS, PRESETS
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class ConfigEditor(QWidget):
    """Full SplatsDB configuration editor — all parameters."""

    config_changed = Signal(dict)
    preset_selected = Signal(str)

    def __init__(self):
        super().__init__()
        self._values = {}
        self._widgets = {}
        self._initial_values = {}
        self._dirty = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ── Toolbar ──
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(200)
        for name, data in PRESETS.items():
            desc = data.get("description", "")
            self.preset_combo.addItem(f"{name} — {desc}", name)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        toolbar.addWidget(self.preset_combo, stretch=1)

        toolbar.addStretch()

        # Search
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search parameters… (Ctrl+F)")
        self._search_input.setFixedWidth(220)
        self._search_input.textChanged.connect(self._start_search_debounce)
        toolbar.addWidget(self._search_input)

        self._clear_search = QPushButton("✕")
        self._clear_search.setFixedSize(24, 24)
        self._clear_search.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {Colors.TEXT_DIM}; "
            f"border: none; font-size: 12px; }}"
            f"QPushButton:hover {{ color: {Colors.ACCENT}; }}"
        )
        self._clear_search.clicked.connect(lambda: self._search_input.clear())
        toolbar.addWidget(self._clear_search)

        # Debounce timer for search (300ms)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(
            lambda: self._on_search(self._search_input.text())
        )

        toolbar.addSpacing(12)

        # Save / Revert / Reset
        self._save_btn = QPushButton(" ✓ Save")
        self._save_btn.setStyleSheet(self._primary_btn())
        toolbar.addWidget(self._save_btn)

        self._revert_btn = QPushButton(" ↩ Revert")
        self._revert_btn.setStyleSheet(self._ghost_btn())
        self._revert_btn.setEnabled(False)
        toolbar.addWidget(self._revert_btn)

        self._reset_btn = QPushButton(" Reset to Default")
        self._reset_btn.setStyleSheet(self._ghost_btn())
        toolbar.addWidget(self._reset_btn)

        layout.addLayout(toolbar)

        # ── Validation banner ──
        self._validation = QLabel("")
        self._validation.setWordWrap(True)
        self._validation.setStyleSheet(
            f"background: #3b1219; color: #fca5a5; padding: 8px 12px; "
            f"border-radius: 4px; font-size: 12px;"
        )
        self._validation.hide()
        layout.addWidget(self._validation)

        # ── Scrollable config groups ──
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
        self._group_boxes = {}
        for group_name, fields in groups.items():
            group_box = QGroupBox(group_name)
            group_box.setStyleSheet(
                f"QGroupBox {{ font-weight: 600; color: {Colors.ACCENT}; "
                f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
                f"margin-top: 12px; padding-top: 16px; }}"
                f"QGroupBox::title {{ subcontrol-origin: margin; left: 12px; "
                f"padding: 0 6px; }}"
            )
            form = QFormLayout(group_box)
            form.setSpacing(6)
            form.setLabelAlignment(Qt.AlignRight)

            for field_name, meta in fields:
                widget = self._create_field_widget(field_name, meta)
                label_text = meta.get("label", field_name)
                desc = meta.get("description", "")

                # Wrap widget with optional "?" help button
                field_row = QWidget()
                field_layout = QHBoxLayout(field_row)
                field_layout.setContentsMargins(0, 0, 0, 0)
                field_layout.addWidget(widget, stretch=1)

                if desc:
                    widget.setToolTip(desc)
                    field_row.setToolTip(desc)
                    help_btn = QPushButton("?")
                    help_btn.setFixedSize(18, 18)
                    help_btn.setStyleSheet(
                        f"QPushButton {{ background: transparent; color: {Colors.TEXT_DIM}; "
                        f"border: 1px solid {Colors.BORDER}; border-radius: 9px; "
                        f"font-size: 10px; font-weight: bold; }}"
                        f"QPushButton:hover {{ color: {Colors.ACCENT}; border-color: {Colors.ACCENT}; }}"
                    )
                    help_btn.clicked.connect(
                        lambda checked, d=desc, b=help_btn: QToolTip.showText(
                            b.mapToGlobal(QPoint(0, b.height())), d, b
                        )
                    )
                    field_layout.addWidget(help_btn)

                form.addRow(f"{label_text}:", field_row)
                self._widgets[field_name] = widget

            self._form_layout.addWidget(group_box)
            self._group_boxes[group_name] = group_box

        self._form_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        # ── Status bar ──
        status_row = QHBoxLayout()
        self._dirty_indicator = QLabel("")
        self._dirty_indicator.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 11px;"
        )
        status_row.addWidget(self._dirty_indicator)
        status_row.addStretch()
        self._field_count = QLabel(f"{len(self._widgets)} parameters")
        self._field_count.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 11px;"
        )
        status_row.addWidget(self._field_count)
        layout.addLayout(status_row)

        # Store initial snapshot
        self._snapshot_initial()

        # Connections
        self._save_btn.clicked.connect(self._save)
        self._revert_btn.clicked.connect(self._revert)
        self._reset_btn.clicked.connect(self._reset_to_default)

    def _primary_btn(self):
        return (
            f"QPushButton {{ color: {Colors.BG}; background: {Colors.ACCENT}; "
            f"border: none; border-radius: 6px; padding: 6px 14px; font-size: 12px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {Colors.ACCENT_BRIGHT}; }}"
            f"QPushButton:disabled {{ background: {Colors.BORDER}; color: {Colors.TEXT_DIM}; }}"
        )

    def _ghost_btn(self):
        return (
            f"QPushButton {{ color: {Colors.TEXT}; background: transparent; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
            f"padding: 6px 14px; font-size: 12px; }}"
            f"QPushButton:hover {{ border-color: {Colors.ACCENT}; color: {Colors.ACCENT}; }}"
            f"QPushButton:disabled {{ color: {Colors.TEXT_DIM}; border-color: {Colors.BORDER}; }}"
        )

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

    # ── Value management ──

    def _on_value_changed(self, name: str, value):
        self._values[name] = value
        self._check_dirty()

    def _check_dirty(self):
        self._dirty = self._values != self._initial_values
        self._dirty_indicator.setText("● Unsaved changes" if self._dirty else "")
        self._revert_btn.setEnabled(self._dirty)

    def _snapshot_initial(self):
        self._initial_values = self._values.copy()

    # ── Search ──

    def _start_search_debounce(self, _text=""):
        """Restart the debounce timer on search input change."""
        self._search_timer.start()

    def _on_search(self, query: str):
        q = query.lower().strip()
        for group_name, group_box in self._group_boxes.items():
            if not q:
                group_box.show()
                continue
            # Check if any field in this group matches
            matches = False
            form = group_box.layout()
            for i in range(form.rowCount()):
                label_item = form.itemAt(i, QFormLayout.LabelRole)
                field_item = form.itemAt(i, QFormLayout.FieldRole)
                if label_item and label_item.widget():
                    label_text = label_item.widget().text().lower()
                    if q in label_text:
                        matches = True
                        break
                if field_item and field_item.widget():
                    tooltip = field_item.widget().toolTip().lower()
                    if q in tooltip:
                        matches = True
                        break
            group_box.setVisible(matches or q in group_name.lower())

    # ── Actions ──

    def _save(self):
        errors = self._validate()
        if errors:
            self._validation.setText("⚠ " + "; ".join(errors))
            self._validation.show()
            return
        self._validation.hide()
        self.config_changed.emit(self._values)
        self._snapshot_initial()
        self._check_dirty()

    def _revert(self):
        self.set_values(self._initial_values)
        self._dirty = False
        self._dirty_indicator.setText("")
        self._revert_btn.setEnabled(False)
        self._validation.hide()

    def _reset_to_default(self):
        defaults = {}
        for name, meta in CONFIG_FIELDS.items():
            if "default" in meta:
                defaults[name] = meta["default"]
        self.set_values(defaults)

    def _validate(self):
        errors = []
        for name, meta in CONFIG_FIELDS.items():
            if name not in self._values:
                continue
            val = self._values[name]
            ftype = meta.get("type", "text")
            label = meta.get("label", name)

            # Required field check
            if meta.get("required", False) and (val is None or val == ""):
                errors.append(f"{label}: required field is empty")
                continue

            # Type-specific validation
            if ftype == "spin":
                if not isinstance(val, (int, float)):
                    errors.append(f"{label}: expected integer, got {type(val).__name__}")
                    continue
                lo = meta.get("min", 0)
                hi = meta.get("max", 2147483647)
                if not (lo <= int(val) <= hi):
                    errors.append(f"{label}: must be {lo}–{hi}")
            elif ftype == "float":
                if not isinstance(val, (int, float)):
                    errors.append(f"{label}: expected number, got {type(val).__name__}")
                    continue
                lo = meta.get("min", 0.0)
                hi = meta.get("max", 99999.0)
                if not (lo <= float(val) <= hi):
                    errors.append(f"{label}: must be {lo}–{hi}")
            elif ftype == "text":
                if not isinstance(val, str):
                    errors.append(f"{label}: expected text, got {type(val).__name__}")

            # Special field validations
            if name == "port":
                try:
                    port_val = int(val)
                    if not (1 <= port_val <= 65535):
                        errors.append(f"{label}: must be 1–65535")
                except (ValueError, TypeError):
                    errors.append(f"{label}: must be a valid port number (1–65535)")

            if name == "latent_dim":
                try:
                    dim_val = int(val)
                    if dim_val <= 0:
                        errors.append(f"{label}: must be positive")
                except (ValueError, TypeError):
                    pass  # Already caught by type check above

        return errors

    # ── Preset ──

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

        # Explicit range checking with warning log
        meta = CONFIG_FIELDS.get(name, {})
        ftype = meta.get("type", "text")
        if ftype == "spin":
            lo = meta.get("min", 0)
            hi = meta.get("max", 2147483647)
            try:
                int_val = int(value)
                if not (lo <= int_val <= hi):
                    logging.warning(
                        "ConfigEditor: value %s for '%s' is out of range [%s, %s]",
                        int_val, name, lo, hi,
                    )
            except (ValueError, TypeError):
                logging.warning(
                    "ConfigEditor: invalid integer value '%s' for '%s'",
                    value, name,
                )
        elif ftype == "float":
            lo = meta.get("min", 0.0)
            hi = meta.get("max", 99999.0)
            try:
                float_val = float(value)
                if not (lo <= float_val <= hi):
                    logging.warning(
                        "ConfigEditor: value %s for '%s' is out of range [%s, %s]",
                        float_val, name, lo, hi,
                    )
            except (ValueError, TypeError):
                logging.warning(
                    "ConfigEditor: invalid float value '%s' for '%s'",
                    value, name,
                )

        # Block signals to avoid triggering dirty check for each value
        widget.blockSignals(True)
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
        widget.blockSignals(False)
        self._values[name] = value

    def get_values(self) -> dict:
        """Get current config as dict."""
        return self._values.copy()

    def keyPressEvent(self, event):
        """Ctrl+F to focus search."""
        if event.modifiers() & Qt.ControlModifier and event.key() == Qt.Key_F:
            self._search_input.setFocus()
            self._search_input.selectAll()
        else:
            super().keyPressEvent(event)
