# SPDX-License-Identifier: GPL-3.0
"""OCR worker — extracts text from images/PDFs in a QThread."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, QThread


class OCRWorker(QObject):
    """Runs OCR text extraction in a background thread."""

    finished = Signal(str, str)  # (text, error)
    progress = Signal(int)       # 0–100

    def __init__(
        self,
        file_path: str,
        engine: str = "auto",
        language: str = "spa+eng",
        *,
        thread: QThread | None = None,
    ):
        super().__init__()
        self.file_path = file_path
        self.engine = engine
        self.language = language
        self._thread = thread  # for isInterruptionRequested()

    def run(self):
        """Run OCR extraction with progress reporting and cancellation."""
        try:
            self.progress.emit(0)

            if self._is_cancelled():
                self.finished.emit("", "Cancelled")
                return

            ext = self.file_path.rsplit(".", 1)[-1].lower()

            if ext == "pdf":
                text = self._ocr_pdf()
            else:
                self.progress.emit(20)
                text = self._ocr_image()

            if self._is_cancelled():
                self.finished.emit("", "Cancelled")
                return

            self.progress.emit(100)
            self.finished.emit(text, "")
        except FileNotFoundError:
            self.finished.emit("", f"File not found: {self.file_path}")
        except PermissionError:
            self.finished.emit("", f"Permission denied: {self.file_path}")
        except Exception as e:
            err = str(e).lower()
            if "memory" in err:
                msg = (
                    f"Out of memory processing {self.file_path}.\n"
                    "The file may be too large — try a smaller image or lower DPI."
                )
            elif "import" in err or "no module" in err or "no ocr" in err:
                msg = str(e)  # Already user-friendly from _ocr_image
            else:
                msg = f"OCR failed on {self.file_path}: {e}"
            self.finished.emit("", msg)

    def _ocr_image(self) -> str:
        """Extract text from an image file."""
        if self.engine in ("auto", "tesseract"):
            try:
                return self._tesseract_ocr(self.file_path)
            except ImportError:
                pass

        if self._is_cancelled():
            return ""

        if self.engine in ("auto", "paddleocr"):
            try:
                return self._paddle_ocr(self.file_path)
            except ImportError:
                pass

        raise RuntimeError(
            "No OCR engine available. Install pytesseract or paddleocr:\n"
            "  pip install pytesseract  (requires Tesseract OCR)\n"
            "  pip install paddleocr paddlepaddle"
        )

    def _ocr_pdf(self) -> str:
        """Extract text from a PDF (OCR if needed)."""
        import fitz  # PyMuPDF
        doc = fitz.open(self.file_path)
        total_pages = len(doc)
        text_parts = []
        try:
            for page_idx, page in enumerate(doc):
                if self._is_cancelled():
                    break

                # Progress: 20–90% scaled by page index
                pct = int(20 + 70 * (page_idx / max(total_pages, 1)))
                self.progress.emit(pct)

                page_text = page.get_text()
                if page_text.strip():
                    text_parts.append(page_text)
                else:
                    # Page has no text — needs OCR
                    pix = page.get_pixmap(dpi=300)
                    img_path = f"/tmp/splatsdb_ocr_page_{page.number}.png"
                    pix.save(img_path)
                    ocr_text = self._ocr_image_file(img_path)
                    text_parts.append(ocr_text)
        finally:
            doc.close()
        return "\n\n".join(text_parts)

    def _tesseract_ocr(self, image_path: str) -> str:
        """Use Tesseract for OCR."""
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        return pytesseract.image_to_string(img, lang=self.language.replace("+", "+"))

    def _paddle_ocr(self, image_path: str) -> str:
        """Use PaddleOCR for OCR."""
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang=self.language.split("+")[0])
        result = ocr.ocr(image_path, cls=True)
        texts = []
        for line in result[0]:
            texts.append(line[1][0])
        return "\n".join(texts)

    def _is_cancelled(self) -> bool:
        """Check whether the hosting QThread has been requested to stop."""
        if self._thread is not None:
            return self._thread.isInterruptionRequested()
        return False
