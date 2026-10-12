# SPDX-License-Identifier: GPL-3.0
"""Parameter panel — right sidebar with collapsible sections, tooltips, and reset buttons."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QComboBox, QCheckBox, QSlider, QLineEdit,
    QScrollArea, QFrame, QToolButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class ParamWidget(QWidget):
    """Single parameter row with label, widget, description tooltip, and reset button."""

    value_changed = Signal(str, object)  # param_name, new_value

    def __init__(self, definition: dict):
        super().__init__()
        self._definition = definition
        self._name = definition.get("name", "")
        self._default = definition.get("default")
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        # Label
        label = QLabel(self._definition.get("label", self._name))
        label.setFixedWidth(100)
        label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px;")
        # Add description tooltip
        desc = self._definition.get("description", self._definition.get("tooltip", ""))
        if desc:
            label.setToolTip(desc)
        layout.addWidget(label)

        # Parameter widget
        ptype = self._definition.get("type", "text")
        if ptype == "spin":
            self._widget = QSpinBox()
            self._widget.setRange(
                self._definition.get("min", 0),
                self._definition.get("max", 9999)
            )
            self._widget.setValue(self._definition.get("default", 0))
            self._widget.valueChanged.connect(
                lambda v: self.value_changed.emit(self._name, v)
            )
        elif ptype == "combo":
            self._widget = QComboBox()
            self._widget.addItems(self._definition.get("options", []))
            self._widget.currentTextChanged.connect(
                lambda v: self.value_changed.emit(self._name, v)
            )
        elif ptype == "check":
            self._widget = QCheckBox()
            self._widget.setChecked(self._definition.get("default", False))
            self._widget.stateChanged.connect(
                lambda v: self.value_changed.emit(self._name, bool(v))
            )
        elif ptype == "slider":
            self._widget = self._make_slider_with_spinbox()
        else:
            self._widget = QLineEdit()
            self._widget.setPlaceholderText(str(self._definition.get("default", "")))
            self._widget.textChanged.connect(
                lambda v: self.value_changed.emit(self._name, v)
            )

        if ptype != "slider":
            layout.addWidget(self._widget, stretch=1)

        # Reset-to-default button
        self._reset_btn = QToolButton()
        self._reset_btn.setText("↺")
        self._reset_btn.setFixedSize(20, 20)
        self._reset_btn.setToolTip(f"Reset to default: {self._default}")
        self._reset_btn.setStyleSheet(
            f"QToolButton {{"
            f"  background: transparent;"
            f"  border: 1px solid {Colors.BORDER};"
            f"  border-radius: 4px;"
            f"  color: {Colors.TEXT_MUTED};"
            f"  font-size: 11px;"
            f"}}"
            f"QToolButton:hover {{"
            f"  border-color: {Colors.ACCENT};"
            f"  color: {Colors.ACCENT};"
            f"}}"
        )
        self._reset_btn.clicked.connect(self._reset_to_default)
        layout.addWidget(self._reset_btn)

    def _make_slider_with_spinbox(self) -> QWidget:
        """Create a coupled slider + spinbox with smooth sync."""
        container = QWidget()
        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(6)

        slider = QSlider(Qt.Horizontal)
        spinbox = QSpinBox()

        min_val = self._definition.get("min", 0)
        max_val = self._definition.get("max", 100)
        default_val = self._definition.get("default", 50)

        slider.setRange(min_val, max_val)
        slider.setValue(default_val)
        spinbox.setRange(min_val, max_val)
        spinbox.setValue(default_val)
        spinbox.setFixedWidth(60)
        spinbox.setStyleSheet(
            f"QSpinBox {{ padding: 2px 4px; font-size: 11px; }}"
        )

        # Bidirectional sync with smooth coupling
        slider.valueChanged.connect(spinbox.setValue)
        spinbox.valueChanged.connect(slider.setValue)

        # Forward value changes
        slider.valueChanged.connect(
            lambda v: self.value_changed.emit(self._name, v)
        )

        # Store references for reset
        self._slider = slider
        self._spinbox = spinbox

        h_layout.addWidget(slider, stretch=1)
        h_layout.addWidget(spinbox)

        # Replace the reset btn's parent layout position
        parent_layout = self.layout()
        if parent_layout:
            parent_layout.insertWidget(1, container, stretch=1)

        return container

    def _reset_to_default(self):
        """Reset parameter to its default value."""
        ptype = self._definition.get("type", "text")
        if ptype == "slider":
            if hasattr(self, '_slider'):
                self._slider.setValue(self._default or 50)
            if hasattr(self, '_spinbox'):
                self._spinbox.setValue(self._default or 50)
        elif ptype == "spin":
            self._widget.setValue(self._default or 0)
        elif ptype == "combo":
            idx = self._widget.findText(str(self._default or ""))
            if idx >= 0:
                self._widget.setCurrentIndex(idx)
        elif ptype == "check":
            self._widget.setChecked(bool(self._default))
        elif ptype == "text":
            self._widget.setText(str(self._default or ""))

    def value(self):
        """Get the current parameter value."""
        ptype = self._definition.get("type", "text")
        if ptype == "slider" and hasattr(self, '_slider'):
            return self._slider.value()
        elif ptype == "spin":
            return self._widget.value()
        elif ptype == "combo":
            return self._widget.currentText()
        elif ptype == "check":
            return self._widget.isChecked()
        else:
            return self._widget.text()


class _CollapsibleSection(QWidget):
    """Collapsible parameter group section with header."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._expanded = True
        self._animation = None
        self._build_ui(title)

    def _build_ui(self, title: str):
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # Header button
        self._header_btn = QPushButton(f"  {title}")
        self._header_btn.setFixedHeight(28)
        self._header_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: transparent;"
            f"  border: none;"
            f"  border-bottom: 1px solid {Colors.BORDER};"
            f"  color: {Colors.TEXT_DIM};"
            f"  font-size: 11px;"
            f"  font-weight: 600;"
            f"  text-transform: uppercase;"
            f"  letter-spacing: 0.5px;"
            f"  text-align: left;"
            f"  padding: 4px 6px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  color: {Colors.TEXT};"
            f"  border-bottom-color: {Colors.ACCENT_DARK};"
            f"}}"
        )
        self._header_btn.clicked.connect(self._toggle)
        self._main_layout.addWidget(self._header_btn)

        # Content area
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 6, 4, 6)
        self._content_layout.setSpacing(4)
        self._content_layout.setAlignment(Qt.AlignTop)
        self._main_layout.addWidget(self._content)

    def _toggle(self):
        """Toggle expanded/collapsed with smooth animation."""
        self._expanded = not self._expanded
        if self._expanded:
            self._animate_expand()
        else:
            self._animate_collapse()

    def _animate_expand(self):
        """Smoothly show content."""
        self._content.show()
        self._content.setMaximumHeight(0)
        # Animate to full height
        target = self._content.sizeHint().height()
        self._animation = QPropertyAnimation(self._content, b"maximumHeight")
        self._animation.setDuration(200)
        self._animation.setStartValue(0)
        self._animation.setEndValue(target)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._animation.finished.connect(lambda: self._content.setMaximumHeight(16777215))
        self._animation.start()

    def _animate_collapse(self):
        """Smoothly hide content."""
        current = self._content.height()
        self._animation = QPropertyAnimation(self._content, b"maximumHeight")
        self._animation.setDuration(200)
        self._animation.setStartValue(current)
        self._animation.setEndValue(0)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._animation.finished.connect(self._content.hide)
        self._animation.start()

    def content_layout(self):
        return self._content_layout

    def add_widget(self, widget: QWidget):
        self._content_layout.addWidget(widget)


class ParamPanel(QWidget):
    """Right sidebar parameter panel with collapsible sections and reset buttons."""

    def __init__(self):
        super().__init__()
        self._param_widgets = {}
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
        self.params_layout.setSpacing(8)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setProperty("class", "primary")
        btn_row.addWidget(self.apply_btn, stretch=1)

        self.reset_all_btn = QPushButton("Reset All")
        self.reset_all_btn.setToolTip("Reset all parameters to defaults")
        btn_row.addWidget(self.reset_all_btn, stretch=1)

        layout.addLayout(btn_row)

    def set_params(self, params: list):
        """Clear existing params and build new parameter widgets, grouped by section."""
        # Clear existing
        for child in self.params_layout.children():
            w = child.widget()
            if w:
                w.deleteLater()
        self._param_widgets.clear()

        # Group params by section
        sections = {}
        ungrouped = []
        for p in params:
            group = p.get("group")
            if group:
                sections.setdefault(group, []).append(p)
            else:
                ungrouped.append(p)

        # Build sections
        for group_name, group_params in sections.items():
            section = _CollapsibleSection(group_name)
            for p in group_params:
                pw = ParamWidget(p)
                section.add_widget(pw)
                self._param_widgets[p["name"]] = pw
            self.params_layout.addWidget(section)

        # Build ungrouped params
        if ungrouped:
            for p in ungrouped:
                pw = ParamWidget(p)
                self.params_layout.addWidget(pw)
                self._param_widgets[p["name"]] = pw

        self.params_layout.addStretch()

    def get_values(self) -> dict:
        """Get all parameter values as a dict."""
        return {name: pw.value() for name, pw in self._param_widgets.items()}

    def reset_all(self):
        """Reset all parameters to their defaults."""
        for pw in self._param_widgets.values():
            pw._reset_to_default()
