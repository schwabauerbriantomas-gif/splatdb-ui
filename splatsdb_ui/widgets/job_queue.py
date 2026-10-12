# SPDX-License-Identifier: GPL-3.0
"""Job queue panel."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame,
    QPushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class JobItem(QFrame):
    def __init__(self, job_id: str, description: str):
        super().__init__()
        self.job_id = job_id
        self._finished = False
        self._build_ui(description)

    def _build_ui(self, description: str):
        layout = QHBoxLayout(self)
        desc_label = QLabel(description)
        desc_label.setStyleSheet(f"color: {Colors.TEXT}; font-size: 12px;")
        layout.addWidget(desc_label)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMinimumWidth(120)
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress, stretch=1)

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


_MAX_DISPLAY_JOBS = 10


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

        self._clear_btn = QPushButton("Clear completed")
        self._clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Colors.BG_OVERLAY}; color: {Colors.ACCENT};
                border: 1px solid {Colors.ACCENT}; border-radius: 4px;
                padding: 3px 8px; font-weight: 600; font-size: 10px;
            }}
            QPushButton:hover {{
                background: {Colors.ACCENT}; color: {Colors.BG};
            }}
        """)
        self._clear_btn.clicked.connect(self._clear_completed)
        header.addWidget(self._clear_btn)
        self._layout.addLayout(header)

        self._jobs_layout = QVBoxLayout()
        self._layout.addLayout(self._jobs_layout)
        self.setStyleSheet(f"background-color: {Colors.BG_RAISED};")

    def _refresh_count(self):
        active = sum(1 for item in self._jobs.values() if not item._finished)
        self.count_label.setText(f"{active} active")

    def add_job(self, job_id: str, description: str):
        # Remove oldest completed jobs when limit is reached
        finished_ids = [jid for jid, item in self._jobs.items() if item._finished]
        while len(self._jobs) >= _MAX_DISPLAY_JOBS and finished_ids:
            oldest_id = finished_ids.pop(0)
            self.remove_job(oldest_id)

        item = JobItem(job_id, description)
        self._jobs[job_id] = item
        self._jobs_layout.addWidget(item)
        self._refresh_count()

    def remove_job(self, job_id: str):
        """Remove a job item from the panel by its ID."""
        item = self._jobs.pop(job_id, None)
        if item:
            self._jobs_layout.removeWidget(item)
            item.setParent(None)
            item.deleteLater()
            self._refresh_count()

    def _clear_completed(self):
        """Remove all finished/failed jobs."""
        finished_ids = [jid for jid, item in self._jobs.items() if item._finished]
        for jid in finished_ids:
            self.remove_job(jid)

    def finish_job(self, job_id: str, success: bool):
        item = self._jobs.get(job_id)
        if item:
            item._finished = True
            if success:
                item.progress.setValue(100)
                item.status_label.setText("Done")
                item.status_label.setStyleSheet(f"color: {Colors.SUCCESS}; font-size: 11px;")
            else:
                # Keep current progress value on failure
                item.status_label.setText("Failed")
                item.status_label.setStyleSheet(f"color: {Colors.ERROR}; font-size: 11px;")
            self._refresh_count()

    def update_job(self, job_id: str, progress: int):
        item = self._jobs.get(job_id)
        if item:
            item.progress.setValue(progress)
