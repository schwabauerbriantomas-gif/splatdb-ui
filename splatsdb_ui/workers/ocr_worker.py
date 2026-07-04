# SPDX-License-Identifier: GPL-3.0
"""OCR worker — extracts text from images/PDFs in a QThread."""

import os
import tempfile

from PySide6.QtCore import QObject, Signal


class OCRWorker(QObject):
    """Runs OCR text extraction in a background thread."""
    finished = Signal(str, str)  # (text, error)
    progress = Signal(int)

    def __init__(self, file_path: str, engine: str = "auto", language: str = "spa+eng"):
        super().__init__()
        self.file_path = file_path
        self.engine = engine
        self.language = language

    def run(self):
        try:
            ext = self.file_path.rsplit(".", 1)[-1].lower()

            if ext == "pdf":
                text = self._ocr_pdf()
            else:
                text = self._ocr_image(self.file_path)

            self.finished.emit(text, "")
        except Exception as e:
            self.finished.emit("", str(e))

    def _ocr_image(self, image_path: str = "") -> str:
        """Extract text from an image file.

        Args:
            image_path: Path to image. Defaults to self.file_path if empty.
        """
        path = image_path or self.file_path

        if self.engine in ("auto", "tesseract"):
            try:
                return self._tesseract_ocr(path)
            except ImportError:
                pass

        if self.engine in ("auto", "paddleocr"):
            try:
                return self._paddle_ocr(path)
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
        temp_files = []
        text_parts = []
        try:
            for page in doc:
                page_text = page.get_text()
                if page_text.strip():
                    text_parts.append(page_text)
                else:
                    # Page has no text — needs OCR
                    pix = page.get_pixmap(dpi=300)
                    # Use unique temp file to avoid collisions between concurrent workers
                    fd, img_path = tempfile.mkstemp(
                        suffix=f"_page_{page.number}.png",
                        prefix="splatsdb_ocr_",
                    )
                    os.close(fd)
                    temp_files.append(img_path)
                    pix.save(img_path)
                    ocr_text = self._ocr_image(img_path)
                    text_parts.append(ocr_text)
        finally:
            doc.close()
            # Clean up temp files
            for f in temp_files:
                try:
                    os.unlink(f)
                except OSError:
                    pass

        return "\n\n".join(text_parts)

    def _tesseract_ocr(self, image_path: str) -> str:
        """Use Tesseract for OCR."""
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        return pytesseract.image_to_string(img, lang=self.language)

    def _paddle_ocr(self, image_path: str) -> str:
        """Use PaddleOCR for OCR."""
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang=self.language.split("+")[0])
        result = ocr.ocr(image_path, cls=True)
        texts = []
        if result and result[0]:
            for line in result[0]:
                texts.append(line[1][0])
        return "\n".join(texts)
