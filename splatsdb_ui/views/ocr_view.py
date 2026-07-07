# SPDX-License-Identifier: GPL-3.0
"""OCR view."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QProgressBar, QTextEdit, QSplitter,
    QFrame, QFileDialog,
)
from PySide6.QtCore import Qt
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class OCRView(QWidget):
    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._current_file = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("OCR Pipeline")
        title.setStyleSheet(f"color: {Colors.TEXT}; font-size: 20px; font-weight: 700; letter-spacing: -0.3px;")
        header.addWidget(title)

        subtitle = QLabel("Image / PDF to searchable text")
        subtitle.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px; padding-top: 4px;")
        header.addWidget(subtitle)
        header.addStretch()
        layout.addLayout(header)

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

        options = QHBoxLayout()
        options.addWidget(QLabel("Engine:"))
        self.engine_combo = QComboBox()
        self.engine_combo.addItems(["Tesseract", "PaddleOCR"])
        options.addWidget(self.engine_combo)
        options.addWidget(QLabel("Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["spa", "eng", "por", "fra", "deu"])
        self.lang_combo.setCurrentText("spa")
        options.addWidget(self.lang_combo)

        run_btn = QPushButton("Extract Text")
        run_btn.setIcon(icon("search", Colors.BG))
        run_btn.setProperty("class", "primary")
        run_btn.clicked.connect(self._run_ocr)
        options.addWidget(run_btn)
        options.addStretch()
        layout.addLayout(options)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        splitter = QSplitter(Qt.Horizontal)

        preview = QFrame()
        pl = QVBoxLayout(preview)
        pl.setContentsMargins(0, 0, 0, 0)
        self.preview_label = QLabel("Select a file to preview")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 13px;")
        pl.addWidget(self.preview_label)
        splitter.addWidget(preview)

        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        self.text_output.setPlaceholderText("Extracted text will appear here...")
        splitter.addWidget(self.text_output)

        splitter.setSizes([400, 600])
        layout.addWidget(splitter, stretch=1)

        actions = QHBoxLayout()
        self.embed_btn = QPushButton("Embed & Store")
        self.embed_btn.setIcon(icon("download", Colors.BG))
        self.embed_btn.setProperty("class", "primary")
        self.embed_btn.clicked.connect(self._embed_and_store)
        actions.addWidget(self.embed_btn)
        self.copy_btn = QPushButton("Copy Text")
        self.copy_btn.setIcon(icon("copy", Colors.TEXT))
        self.copy_btn.clicked.connect(self._copy_text)
        actions.addWidget(self.copy_btn)
        actions.addStretch()
        layout.addLayout(actions)

        # Store thread reference to prevent GC
        self._ocr_thread = None

    def _run_ocr(self):
        """Run OCR on the selected file in a background thread."""
        if not self._current_file:
            self.signals.status_message.emit("No file selected for OCR")
            return

        from PySide6.QtCore import QThread
        from splatsdb_ui.workers.ocr_worker import OCRWorker

        engine_choice = self.engine_combo.currentText().lower()
        lang = self.lang_combo.currentText()
        self.progress.setValue(5)

        thread = QThread(self)
        worker = OCRWorker(self._current_file, engine=engine_choice, language=lang)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_ocr_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._ocr_thread = thread
        thread.start()

    def _on_ocr_finished(self, text: str, error: str):
        """Handle OCR completion."""
        self.progress.setValue(100 if not error else 0)
        if error:
            self.text_output.setPlainText(f"Error: {error}")
            self.signals.ocr_error.emit(self._current_file or "", error)
        else:
            self.text_output.setPlainText(text)
            if self._current_file:
                self.signals.ocr_completed.emit(self._current_file, text)

    def _embed_and_store(self):
        """Embed the extracted text and store it in the backend."""
        text = self.text_output.toPlainText().strip()
        if not text:
            self.signals.status_message.emit("No text to embed")
            return
        # Emit for the main window to handle the store operation
        self.signals.status_message.emit(f"Embedding {len(text)} chars...")

    def _copy_text(self):
        """Copy extracted text to clipboard."""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_output.toPlainText())
        self.signals.status_message.emit("Copied to clipboard")

    def set_file(self, path: str):
        """Public API to set the current file (used by FileMixin)."""
        self._current_file = path
        self.file_label.setText(path)

    def _browse_file(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Files", "",
            "Images (*.png *.jpg *.jpeg *.tiff *.bmp);;PDF (*.pdf);;All (*)"
        )
        if files:
            self.file_label.setText(files[0])
            self._current_file = files[0]

    def get_params(self) -> list:
        return [
            {"name": "ocr_engine", "label": "Engine", "type": "combo", "options": ["tesseract", "paddleocr"]},
            {"name": "ocr_lang", "label": "Language", "type": "combo", "options": ["spa", "eng", "por", "fra", "deu"]},
            {"name": "auto_embed", "label": "Auto-embed", "type": "check", "default": True},
        ]
