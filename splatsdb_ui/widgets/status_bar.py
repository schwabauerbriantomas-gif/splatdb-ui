# SPDX-License-Identifier: GPL-3.0
"""Status bar."""

from PySide6.QtWidgets import QStatusBar, QLabel
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class SplatDBStatusBar(QStatusBar):
    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        self.conn_icon = QLabel()
        self.conn_icon.setPixmap(icon("server", Colors.TEXT_DIM, 14).pixmap(14, 14))
        self.addWidget(self.conn_icon)

        self.conn_label = QLabel("Disconnected")
        self.conn_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        self.addWidget(self.conn_label)

        self._sep()

        self.model_icon = QLabel()
        self.model_icon.setPixmap(icon("cpu", Colors.TEXT_DIM, 14).pixmap(14, 14))
        self.addWidget(self.model_icon)

        self.model_label = QLabel("No engine")
        self.model_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        self.addWidget(self.model_label)

        self._sep()

        self.doc_label = QLabel("0 vectors")
        self.doc_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        self.addWidget(self.doc_label)

        self.gpu_icon = QLabel()
        self.gpu_icon.setPixmap(icon("zap", Colors.TEXT_DIM, 14).pixmap(14, 14))
        self.addPermanentWidget(self.gpu_icon)

        self.gpu_label = QLabel("CPU")
        self.gpu_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        self.addPermanentWidget(self.gpu_label)

    def _sep(self):
        s = QLabel("|")
        s.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 10px; margin: 0 6px;")
        self.addWidget(s)

    def set_connected(self, connected: bool, preset: str = ""):
        if connected:
            self.conn_icon.setPixmap(icon("server", Colors.SUCCESS, 14).pixmap(14, 14))
            self.conn_label.setText("Connected")
            self.conn_label.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 11px;")
        else:
            self.conn_icon.setPixmap(icon("server", Colors.TEXT_DIM, 14).pixmap(14, 14))
            self.conn_label.setText("Disconnected")
            self.conn_label.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")

    def set_model(self, name: str):
        self.model_label.setText(name or "No engine")

    def set_doc_count(self, count: int):
        self.doc_label.setText(f"{count:,} vectors")

    def set_gpu(self, info: str):
        self.gpu_label.setText(info)

    def show_message(self, msg: str, timeout: int = 4000):
        self.showMessage(msg, timeout)
