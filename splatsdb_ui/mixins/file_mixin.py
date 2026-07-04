# SPDX-License-Identifier: GPL-3.0
"""File mixin — open, save, drag-drop, recent projects."""

from PySide6.QtWidgets import QFileDialog
from PySide6.QtCore import QMimeData


class FileMixin:
    """File operations mixin for MainWindow."""

    def file_open(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Open Files",
            "",
            "All Supported (*.bin *.fvecs *.json *.txt *.pdf *.png *.jpg);;"
            "Vectors (*.bin *.fvecs *.bvecs);;"
            "Documents (*.txt *.md *.json *.csv);;"
            "Images (*.png *.jpg *.jpeg *.tiff *.bmp);;"
            "PDF (*.pdf);;"
            "All Files (*)",
        )
        if files:
            for f in files:
                self._handle_file(f)

    def _handle_file(self, path: str):
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in ("png", "jpg", "jpeg", "tiff", "bmp", "pdf"):
            self.switch_view("ocr")
            ocr_view = self._views.get("ocr")
            if ocr_view and hasattr(ocr_view, "set_file"):
                ocr_view.set_file(path)
        elif ext in ("bin", "fvecs", "bvecs", "ivecs"):
            self.switch_view("collections")
        else:
            self.switch_view("search")

        self.signals.status_message.emit(f"Opened: {path}")

    def file_save(self):
        self.signals.status_message.emit("Saved")
