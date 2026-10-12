# SPDX-License-Identifier: GPL-3.0
"""File Preview — inline preview for images, text, PDFs, audio."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QScrollArea, QFrame, QSizePolicy, QApplication,
)
from PySide6.QtCore import Signal, Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QImage, QFont, QPainter, QColor

from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon

_HAS_PYMUPDF = False
try:
    import fitz  # PyMuPDF
    _HAS_PYMUPDF = True
except ImportError:
    pass


class FilePreview(QWidget):
    """Inline file preview widget."""

    open_external_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self._current_file: str | None = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QHBoxLayout()
        header.setContentsMargins(12, 8, 12, 8)

        lbl = QLabel("FILE PREVIEW")
        lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 1.2px;")
        header.addWidget(lbl)
        header.addStretch()

        self.file_name = QLabel("No file")
        self.file_name.setStyleSheet(f"color: {Colors.TEXT}; font-size: 11px;")
        header.addWidget(self.file_name)

        ext_btn = QPushButton()
        ext_btn.setIcon(icon("link", Colors.TEXT_DIM))
        ext_btn.setFixedSize(24, 24)
        ext_btn.setToolTip("Open externally")
        ext_btn.setStyleSheet("QPushButton { background: transparent; border: none; } QPushButton:hover { background-color: #21262d; border-radius: 4px; }")
        ext_btn.clicked.connect(self._open_external)
        header.addWidget(ext_btn)

        header_widget = QWidget()
        header_widget.setLayout(header)
        header_widget.setStyleSheet(f"background-color: {Colors.BG_RAISED}; border-bottom: 1px solid {Colors.BORDER};")
        layout.addWidget(header_widget)

        # Zoom controls (created once, shown only for image previews)
        self._zoom_controls = QWidget()
        zr = QHBoxLayout(self._zoom_controls)
        zr.setAlignment(Qt.AlignCenter)
        zr.setSpacing(4)
        zr.setContentsMargins(0, 4, 0, 4)

        self._zoom_out_btn = QPushButton("−")
        self._zoom_out_btn.setFixedSize(28, 28)
        self._zoom_out_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG_RAISED}; color: {Colors.TEXT}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; font-size: 14px; }}"
            f"QPushButton:hover {{ border-color: {Colors.ACCENT}; }}"
        )
        self._zoom_out_btn.clicked.connect(lambda: self._apply_zoom(-0.2))
        zr.addWidget(self._zoom_out_btn)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 11px; min-width: 40px;"
        )
        self._zoom_label.setAlignment(Qt.AlignCenter)
        zr.addWidget(self._zoom_label)

        self._zoom_in_btn = QPushButton("+")
        self._zoom_in_btn.setFixedSize(28, 28)
        self._zoom_in_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG_RAISED}; color: {Colors.TEXT}; "
            f"border: 1px solid {Colors.BORDER}; border-radius: 4px; font-size: 14px; }}"
            f"QPushButton:hover {{ border-color: {Colors.ACCENT}; }}"
        )
        self._zoom_in_btn.clicked.connect(lambda: self._apply_zoom(0.2))
        zr.addWidget(self._zoom_in_btn)

        self._zoom_controls.hide()
        layout.addWidget(self._zoom_controls)

        # Content area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setAlignment(Qt.AlignCenter)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setAlignment(Qt.AlignCenter)

        # Placeholder
        self.placeholder = QLabel("Select a file to preview")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 14px;")
        self.content_layout.addWidget(self.placeholder)

        self.scroll.setWidget(self.content_widget)
        layout.addWidget(self.scroll, stretch=1)

        self.setMinimumHeight(200)
        self.setStyleSheet(f"FilePreview {{ background-color: {Colors.BG}; }}")

    def preview_file(self, file_path: str):
        """Preview a file based on its extension."""
        path = Path(file_path)
        self._current_file = file_path

        if not path.exists():
            self._show_message(f"File not found:\n{file_path}")
            self.file_name.setText(f"{path.name} (missing)")
            return

        self.file_name.setText(path.name)

        # Clear old content
        self._clear_content()

        suffix = path.suffix.lower()

        # Image formats
        if suffix in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".svg"):
            self._preview_image(path)
        # Text formats
        elif suffix in (".txt", ".md", ".py", ".js", ".ts", ".rs", ".json", ".yaml", ".yml", ".toml",
                        ".csv", ".html", ".css", ".xml", ".log", ".cfg", ".ini", ".sh", ".bash"):
            self._preview_text(path)
        # PDF
        elif suffix == ".pdf":
            self._preview_pdf(path)
        # Audio waveform info
        elif suffix in (".mp3", ".wav", ".ogg", ".flac", ".m4a"):
            self._preview_audio(path)
        # Video info
        elif suffix in (".mp4", ".avi", ".mkv", ".mov", ".webm"):
            self._preview_video(path)
        else:
            self._show_message(f"Preview not available for {suffix}\n{self._format_size(path)}")

    def _preview_image(self, path: Path):
        """Show image inline with zoom controls."""
        self._current_pixmap = QPixmap(str(path))
        if self._current_pixmap.isNull():
            self._show_message("Could not load image")
            return

        self._img_zoom = 1.0
        self._zoom_label.setText("100%")
        self._zoom_controls.show()

        # Image
        self._img_label = QLabel()
        self._update_scaled_image()
        self._img_label.setAlignment(Qt.AlignCenter)
        self.content_layout.addWidget(self._img_label)

        # Metadata
        stat = path.stat()
        from datetime import datetime
        meta_text = (
            f"{self._current_pixmap.width()} × {self._current_pixmap.height()}  |  "
            f"{self._format_size(path)}  |  "
            f"Modified: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')}"
        )
        info = QLabel(meta_text)
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px; padding: 6px;")
        self.content_layout.addWidget(info)

    def _apply_zoom(self, delta: float):
        if not hasattr(self, '_current_pixmap') or self._current_pixmap.isNull():
            return
        self._img_zoom = max(0.1, min(5.0, self._img_zoom + delta))
        self._zoom_label.setText(f"{int(self._img_zoom * 100)}%")
        self._update_scaled_image()

    def _update_scaled_image(self):
        if not hasattr(self, '_current_pixmap') or self._current_pixmap.isNull():
            return
        max_w = max(100, self.scroll.viewport().width() - 20)
        max_h = max(100, self.scroll.viewport().height() - 60)
        # Compute viewport-fit size, then apply zoom — single scale pass
        fit_size = self._current_pixmap.size().scaled(max_w, max_h, Qt.KeepAspectRatio)
        target_w = max(1, int(fit_size.width() * self._img_zoom))
        target_h = max(1, int(fit_size.height() * self._img_zoom))
        scaled = self._current_pixmap.scaled(
            target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._img_label.setPixmap(scaled)

    def _preview_text(self, path: Path):
        """Show text file with line numbers and metadata."""
        max_lines = 500
        lines = []
        truncated = False
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= max_lines:
                        truncated = True
                        break
                    lines.append(line.rstrip("\n\r"))
        except Exception as e:
            lines = [f"Error reading file: {e}"]

        # Add line numbers
        numbered_lines = []
        for i, line in enumerate(lines, 1):
            numbered_lines.append(f"{i:>4}  {line}")
        numbered_text = "\n".join(numbered_lines)
        if truncated:
            numbered_text += "\n\n... (more lines below)"

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("monospace", 11))
        text_edit.setText(numbered_text)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {Colors.BG};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                color: {Colors.TEXT};
                padding: 8px;
            }}
        """)
        self.content_layout.addWidget(text_edit)

        # Metadata
        stat = path.stat()
        from datetime import datetime
        line_count_str = f"{max_lines}+" if truncated else str(len(lines))
        meta_text = (
            f"{line_count_str} lines  |  {self._format_size(path)}  |  "
            f"Modified: {datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M')}"
        )
        info = QLabel(meta_text)
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px; padding: 4px;")
        self.content_layout.addWidget(info)

    def _preview_pdf(self, path: Path):
        """Show PDF info and first page if possible."""
        if not _HAS_PYMUPDF:
            self._show_message(
                f"PDF preview requires PyMuPDF\n\n{path.name}\n{self._format_size(path)}\n\nClick the link icon to open externally."
            )
            return
        try:
            doc = fitz.open(str(path))
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(img)

            img_label = QLabel()
            scaled = pixmap.scaled(
                self.scroll.viewport().width() - 20,
                self.scroll.viewport().height() - 40,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            img_label.setPixmap(scaled)
            img_label.setAlignment(Qt.AlignCenter)
            self.content_layout.addWidget(img_label)

            info = QLabel(f"{doc.page_count} pages  |  {self._format_size(path)}")
            info.setAlignment(Qt.AlignCenter)
            info.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px; padding: 4px;")
            self.content_layout.addWidget(info)
            doc.close()
        except Exception as e:
            self._show_message(f"Error loading PDF:\n{e}")

    def _preview_audio(self, path: Path):
        """Show audio file info."""
        info_lines = [
            f"Audio file: {path.name}",
            f"Size: {self._format_size(path)}",
            f"Format: {path.suffix.upper()[1:]}",
        ]
        self._show_message("\n".join(info_lines))

    def _preview_video(self, path: Path):
        """Show video file info."""
        info_lines = [
            f"Video file: {path.name}",
            f"Size: {self._format_size(path)}",
            f"Format: {path.suffix.upper()[1:]}",
        ]
        self._show_message("\n".join(info_lines))

    def _show_message(self, text: str):
        """Show a centered message."""
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px; padding: 20px;")
        self.content_layout.addWidget(lbl)

    def _clear_content(self):
        """Remove all content widgets."""
        self._zoom_controls.hide()
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.content_layout.invalidate()

    def _open_external(self):
        if self._current_file:
            self.open_external_requested.emit(self._current_file)

    @staticmethod
    def _format_size(path: Path) -> str:
        sz = path.stat().st_size
        if sz < 1024:
            return f"{sz}B"
        elif sz < 1024 * 1024:
            return f"{sz / 1024:.1f}KB"
        elif sz < 1024 * 1024 * 1024:
            return f"{sz / (1024 * 1024):.1f}MB"
        else:
            return f"{sz / (1024 * 1024 * 1024):.1f}GB"
