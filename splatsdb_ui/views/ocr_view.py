# SPDX-License-Identifier: GPL-3.0
"""OCR view — enhanced with drag-and-drop, progress bar, fade transitions, and results panel."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QProgressBar, QPlainTextEdit, QSplitter,
    QFrame, QFileDialog, QSizePolicy, QApplication,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QMimeData, Signal, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QDragEnterEvent, QDragLeaveEvent, QDropEvent, QPixmap, QPainter, QFont,
    QColor, QTextCharFormat, QTextCursor,
)
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


# ── Drag-and-drop zone ───────────────────────────────────────────────────────

class _DropZone(QFrame):
    """Drag-and-drop target with dashed amber border that glows on dragEnter."""

    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(180)
        self._has_file = False
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # Empty-state icon (a large OCR-style icon)
        self._icon_label = QLabel()
        pm = self._make_empty_icon()
        self._icon_label.setPixmap(pm)
        self._icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._icon_label, alignment=Qt.AlignCenter)

        self._text_label = QLabel("Drop image or PDF here\nor click Browse above")
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 14px; font-weight: 500;"
        )
        layout.addWidget(self._text_label, alignment=Qt.AlignCenter)

        self._apply_default_style()

    def _make_empty_icon(self) -> QPixmap:
        """Draw a simple document-scan placeholder icon."""
        size = 64
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        # Document body
        from PySide6.QtGui import QPen
        pen = QPen(QColor(Colors.TEXT_DIM), 2.0)
        p.setPen(pen)
        p.drawRoundedRect(10, 6, 44, 52, 4, 4)
        # Text lines inside document
        pen.setStyle(Qt.PenStyle.SolidLine)
        pen.setColor(QColor(Colors.TEXT_MUTED))
        pen.setWidth(2)
        p.setPen(pen)
        for y in (22, 32, 42):
            p.drawLine(18, y, 46, y)
        # Magnifier hint
        pen.setColor(QColor(Colors.ACCENT))
        pen.setWidth(2.5)
        p.setPen(pen)
        p.drawEllipse(36, 12, 14, 14)
        p.drawLine(46, 26, 54, 34)
        p.end()
        return pm

    def _apply_default_style(self):
        self.setStyleSheet(
            f"""
            _DropZone, QFrame {{
                background-color: {Colors.BG_RAISED};
                border: 2px dashed {Colors.ACCENT_DARK};
                border-radius: 12px;
            }}
            """
        )

    def _apply_hover_style(self):
        self.setStyleSheet(
            f"""
            _DropZone, QFrame {{
                background-color: rgba(245, 158, 11, 0.06);
                border: 2px dashed {Colors.ACCENT};
                border-radius: 12px;
            }}
            """
        )

    # ── Public API ────────────────────────────────────────────────

    def set_file(self, path: str):
        self._has_file = True
        name = path.split("/")[-1].split("\\")[-1]
        self._text_label.setText(f"Loaded: {name}")
        self._text_label.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 13px; font-weight: 600;"
        )
        self._apply_default_style()

    def reset(self):
        self._has_file = False
        self._text_label.setText("Drop image or PDF here\nor click Browse above")
        self._text_label.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 14px; font-weight: 500;"
        )
        self._apply_default_style()

    # ── Drag events ───────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._apply_hover_style()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        if not self._has_file:
            self._apply_default_style()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path:
                self.set_file(path)
                self.file_dropped.emit(path)
        self._apply_default_style()


# ── Main OCR view ─────────────────────────────────────────────────────────────

class OCRView(QWidget):
    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._current_file = None
        self._fade_opacity = 1.0
        self._highlight_regions = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Header row ────────────────────────────────────────────
        header = QHBoxLayout()
        title = QLabel("OCR Pipeline")
        title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: 18px; font-weight: 700;"
        )
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # ── File row (browse + path) ──────────────────────────────
        file_row = QHBoxLayout()
        self.file_label = QLineEdit()
        self.file_label.setPlaceholderText("Select image or PDF...")
        self.file_label.setReadOnly(True)
        file_row.addWidget(self.file_label, stretch=1)

        browse_btn = QPushButton("Browse")
        browse_btn.setIcon(icon("folder", Colors.TEXT))
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)
        layout.addLayout(file_row)

        # ── Drag-and-drop zone ────────────────────────────────────
        self.drop_zone = _DropZone(self)
        self.drop_zone.file_dropped.connect(self._on_file_dropped)
        layout.addWidget(self.drop_zone, stretch=0)

        # ── Options row ──────────────────────────────────────────
        options = QHBoxLayout()
        options.setSpacing(12)

        engine_lbl = QLabel("Engine:")
        engine_lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-weight: 500;")
        options.addWidget(engine_lbl)
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["Tesseract", "PaddleOCR"])
        self.engine_combo.setMinimumWidth(120)
        options.addWidget(self.engine_combo)

        lang_lbl = QLabel("Language:")
        lang_lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-weight: 500;")
        options.addWidget(lang_lbl)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["spa", "eng", "spa+eng", "fra", "deu", "por"])
        self.lang_combo.setCurrentText("spa")
        self.lang_combo.setMinimumWidth(110)
        options.addWidget(self.lang_combo)

        self.run_btn = QPushButton("Extract Text")
        self.run_btn.setIcon(icon("search", Colors.BG))
        self.run_btn.setProperty("class", "primary")
        options.addWidget(self.run_btn)
        options.addStretch()
        layout.addLayout(options)

        # ── Progress bar + spinner label ─────────────────────────
        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)

        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 11px; font-weight: 600;"
        )
        self._progress_label.setFixedWidth(60)
        self._progress_label.hide()
        progress_row.addWidget(self._progress_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.setVisible(False)
        progress_row.addWidget(self.progress, stretch=1)
        layout.addLayout(progress_row)

        # ── Splitter: preview | results ──────────────────────────
        splitter = QSplitter(Qt.Horizontal)

        # Left: image preview frame
        preview = QFrame()
        pl = QVBoxLayout(preview)
        pl.setContentsMargins(0, 0, 0, 0)
        self.preview_label = QLabel("No file loaded")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        pl.addWidget(self.preview_label)
        splitter.addWidget(preview)

        # Right: results panel with copy buttons
        results_container = QWidget()
        results_layout = QVBoxLayout(results_container)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(6)

        # Results header row with title + copy buttons
        results_header = QHBoxLayout()
        results_title = QLabel("Extracted Text")
        results_title.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 12px; font-weight: 600;"
        )
        results_header.addWidget(results_title)
        results_header.addStretch()

        # Highlight toggle button
        self._highlight_btn = QPushButton("Highlight")
        self._highlight_btn.setCheckable(True)
        self._highlight_btn.setIcon(icon("search", Colors.ACCENT))
        self._highlight_btn.setFixedHeight(28)
        self._highlight_btn.setStyleSheet(self._small_btn_style())
        self._highlight_btn.setToolTip("Toggle text highlighting of detected regions")
        self._highlight_btn.clicked.connect(self._toggle_highlight)
        results_header.addWidget(self._highlight_btn)

        # Copy All button
        self.copy_all_btn = QPushButton("Copy All")
        self.copy_all_btn.setIcon(icon("copy", Colors.ACCENT))
        self.copy_all_btn.setFixedHeight(28)
        self.copy_all_btn.setStyleSheet(self._small_btn_style())
        self.copy_all_btn.setToolTip("Copy all extracted text to clipboard")
        self.copy_all_btn.clicked.connect(self._copy_all_results)
        results_header.addWidget(self.copy_all_btn)

        # Copy button (selection)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.setIcon(icon("copy", Colors.ACCENT))
        self.copy_btn.setFixedHeight(28)
        self.copy_btn.setStyleSheet(self._small_btn_style())
        self.copy_btn.setToolTip("Copy selected text to clipboard")
        self.copy_btn.clicked.connect(self._copy_results)
        results_header.addWidget(self.copy_btn)
        results_layout.addLayout(results_header)

        # Results text area (QPlainTextEdit with improved layout)
        self.text_output = QPlainTextEdit()
        self.text_output.setReadOnly(True)
        self.text_output.setPlaceholderText("Extracted text will appear here...")
        self.text_output.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.text_output.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {Colors.BG_RAISED};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 10px;
                color: {Colors.TEXT};
                font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
                font-size: 13px;
                selection-background-color: {Colors.ACCENT};
                selection-color: {Colors.BG};
            }}
            """
        )
        # Set improved line spacing via block format
        doc = self.text_output.document()
        fmt = doc.defaultBlockFormat()
        fmt.setLineHeight(140, QTextCharFormat.ProportionalHeight)
        fmt.setTopMargin(2)
        fmt.setBottomMargin(2)
        doc.setDefaultBlockFormat(fmt)

        # Opacity effect for fade transitions
        self._opacity_effect = QGraphicsOpacityEffect(self.text_output)
        self._opacity_effect.setOpacity(1.0)
        self.text_output.setGraphicsEffect(self._opacity_effect)

        results_layout.addWidget(self.text_output)
        splitter.addWidget(results_container)

        splitter.setSizes([400, 600])
        layout.addWidget(splitter, stretch=1)

        # ── Bottom actions row ───────────────────────────────────
        actions = QHBoxLayout()
        embed_btn = QPushButton("Embed & Store")
        embed_btn.setIcon(icon("download", Colors.BG))
        embed_btn.setProperty("class", "primary")
        actions.addWidget(embed_btn)
        actions.addStretch()
        layout.addLayout(actions)

    # ── Style helpers ─────────────────────────────────────────────

    def _small_btn_style(self) -> str:
        """Shared style for small action buttons in the results header."""
        return (
            f"QPushButton {{"
            f"  background-color: {Colors.BG_OVERLAY};"
            f"  border: 1px solid {Colors.BORDER_LITE};"
            f"  border-radius: 6px;"
            f"  padding: 4px 12px;"
            f"  color: {Colors.ACCENT};"
            f"  font-weight: 600;"
            f"  font-size: 11px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {Colors.BG_HOVER};"
            f"  border-color: {Colors.ACCENT};"
            f"}}"
            f"QPushButton:checked {{"
            f"  background-color: {Colors.ACCENT_DARK};"
            f"  border-color: {Colors.ACCENT};"
            f"}}"
        )

    def _success_btn_style(self) -> str:
        """Green success state for copy buttons."""
        return (
            f"QPushButton {{"
            f"  background-color: rgba(34, 197, 94, 0.15);"
            f"  border: 1px solid {Colors.SUCCESS};"
            f"  border-radius: 6px;"
            f"  padding: 4px 12px;"
            f"  color: {Colors.SUCCESS};"
            f"  font-weight: 600;"
            f"  font-size: 11px;"
            f"}}"
        )

    # ── Slots ─────────────────────────────────────────────────────

    def _browse_file(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Files", "",
            "Images (*.png *.jpg *.jpeg *.tiff *.bmp);;PDF (*.pdf);;All (*)"
        )
        if files:
            self._set_file(files[0])

    def _on_file_dropped(self, path: str):
        self._set_file(path)

    def _set_file(self, path: str):
        self._current_file = path
        self.file_label.setText(path)
        self.drop_zone.set_file(path)

    def _copy_results(self):
        """Copy selected text (or all text if no selection) to clipboard."""
        text = self.text_output.textCursor().selectedText()
        if not text:
            text = self.text_output.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._flash_copy_btn(self.copy_btn)

    def _copy_all_results(self):
        """Copy all extracted text to clipboard."""
        text = self.text_output.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self._flash_copy_btn(self.copy_all_btn)
            self._flash_copy_btn(self.copy_btn)

    def _flash_copy_btn(self, btn: QPushButton):
        """Flash a copy button to show success state."""
        original_text = btn.text()
        btn.setText("Copied!")
        btn.setStyleSheet(self._success_btn_style())
        QTimer.singleShot(2000, lambda: self._reset_copy_btn(btn, original_text))

    def _reset_copy_btn(self, btn: QPushButton, text: str = "Copy"):
        """Reset a copy button to its default style."""
        btn.setText(text)
        btn.setStyleSheet(self._small_btn_style())

    def _toggle_highlight(self, checked: bool):
        """Toggle highlighting of detected OCR regions."""
        if checked:
            self._apply_highlights()
        else:
            self._clear_highlights()

    def _apply_highlights(self):
        """Apply amber highlight to detected text regions."""
        cursor = self.text_output.textCursor()
        cursor.select(QTextCursor.Document)

        fmt = QTextCharFormat()
        fmt.setBackground(QColor(Colors.ACCENT_DARK))
        fmt.setForeground(QColor(Colors.ACCENT_BRIGHT))

        cursor.mergeCharFormat(fmt)
        self._highlight_regions = True

    def _clear_highlights(self):
        """Clear all highlights, restoring default text formatting."""
        cursor = self.text_output.textCursor()
        cursor.select(QTextCursor.Document)

        fmt = QTextCharFormat()
        fmt.setBackground(QColor(Colors.BG_RAISED))
        fmt.setForeground(QColor(Colors.TEXT))

        cursor.mergeCharFormat(fmt)
        self._highlight_regions = False

    # ── Fade transition ──────────────────────────────────────────

    def _fade_in(self):
        """Animate opacity from 0 to 1 for smooth result appearance."""
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(350)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._fade_anim.start()

    def _fade_out(self):
        """Animate opacity from 1 to 0."""
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(200)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._fade_anim.start()

    # ── Public helpers ────────────────────────────────────────────

    def show_progress(self, visible: bool = True):
        """Show/hide the progress bar and percentage label."""
        self.progress.setVisible(visible)
        self._progress_label.setVisible(visible)
        if visible:
            self.progress.setValue(0)
            self._progress_label.setText("0%")

    def set_progress(self, value: int):
        """Update progress bar and percentage label."""
        clamped = max(0, min(100, value))
        self.progress.setValue(clamped)
        self._progress_label.setText(f"{clamped}%")
        if clamped >= 100:
            QTimer.singleShot(800, lambda: self.show_progress(False))

    def set_result(self, text: str):
        """Set OCR result text with a smooth fade transition."""
        # Fade out old content, set new, fade in
        self._fade_out()
        # Wait for fade-out, then update and fade in
        QTimer.singleShot(220, lambda: self._set_result_text(text))

    def _set_result_text(self, text: str):
        """Actually set the result text and trigger fade-in."""
        self.text_output.setPlainText(text)
        # Restore line spacing after setting plain text
        doc = self.text_output.document()
        fmt = doc.defaultBlockFormat()
        fmt.setLineHeight(140, QTextCharFormat.ProportionalHeight)
        fmt.setTopMargin(2)
        fmt.setBottomMargin(2)
        doc.setDefaultBlockFormat(fmt)
        self._fade_in()

    def get_params(self) -> list:
        return [
            {"name": "ocr_engine", "label": "Engine", "type": "combo",
             "options": ["tesseract", "paddleocr"]},
            {"name": "ocr_lang", "label": "Language", "type": "combo",
             "options": ["spa", "eng", "spa+eng", "por", "fra", "deu"]},
            {"name": "auto_embed", "label": "Auto-embed", "type": "check",
             "default": True},
        ]
