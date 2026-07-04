# SPDX-License-Identifier: GPL-3.0
"""Job queue panel."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class JobItem(QFrame):
    def __init__(self, job_id: str, description: str):
        super().__init__()
        self.job_id = job_id
        self._build_ui(description)

    def _build_ui(self, description: str):
        layout = QHBoxLayout(self)
        desc_label = QLabel(description)
        desc_label.setStyleSheet(f"color: {Colors.TEXT}; font-size: 12px;")
        layout.addWidget(desc_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFixedWidth(180)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        self.status_label = QLabel("Running")
        self.status_label.setStyleSheet(f"color: {Colors.WARNING}; font-size: 11px;")
        layout.addWidget(self.status_label)

        self.setStyleSheet(f"""
            JobItem {{
                background-color: {Colors.BG_RAISED};
                border: 1px solid {Colors.BORDER};
                border-radius: 6px;
                padding: 4px 10px;
            }}
        """)


class JobQueuePanel(QWidget):
    def __init__(self):
        super().__init__()
        self._jobs = {}
        self._build_ui()

    def _build_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 4, 10, 4)

        header = QHBoxLayout()
        lbl = QLabel("JOBS")
        lbl.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 10px; font-weight: 700; letter-spacing: 1.0px;")
        header.addWidget(lbl)
        header.addStretch()
        self.count_label = QLabel("0 active")
        self.count_label.setStyleSheet(f"color: {Colors.TEXT_MUTED}; font-size: 11px;")
        header.addWidget(self.count_label)
        self._layout.addLayout(header)

        self._jobs_layout = QVBoxLayout()
        self._layout.addLayout(self._jobs_layout)
        self.setStyleSheet(f"background-color: {Colors.BG_RAISED};")

    def add_job(self, job_id: str, description: str):
        item = JobItem(job_id, description)
        self._jobs[job_id] = item
        self._jobs_layout.addWidget(item)
        self.count_label.setText(f"{len(self._jobs)} active")

    def finish_job(self, job_id: str, success: bool):
        """Mark a job as finished and remove it from the panel.

        The job item is deleted to prevent memory leaks from accumulating
        completed jobs.
        """
        item = self._jobs.pop(job_id, None)
        if item:
            if success:
                item.status_label.setText("Done")
                item.status_label.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 11px;")
            else:
                item.status_label.setText("Failed")
                item.status_label.setStyleSheet(f"color: {Colors.ERROR}; font-size: 11px;")
            # Remove widget from layout and schedule deletion
            self._jobs_layout.removeWidget(item)
            item.deleteLater()
        self.count_label.setText(f"{len(self._jobs)} active")

    def update_job(self, job_id: str, progress: int):
        item = self._jobs.get(job_id)
        if item:
            item.progress.setValue(progress)
