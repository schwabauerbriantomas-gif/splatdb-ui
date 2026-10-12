# SPDX-License-Identifier: GPL-3.0
"""Global signal bus — decoupled communication between components."""

from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """Central signal hub. All components communicate through this bus
    to avoid tight coupling between views, workers, and the main window."""

    # ── Navigation ──────────────────────────────────────────────────
    view_changed = Signal(str)              # view name
    search_requested = Signal(str)          # query text

    # ── Data operations ─────────────────────────────────────────────
    vectors_imported = Signal(str, int)     # collection_name, count
    search_results = Signal(list)           # list of SearchResult
    document_stored = Signal(str)           # doc_id
    document_deleted = Signal(str)          # doc_id
    collection_created = Signal(str)        # collection name
    collection_deleted = Signal(str)        # collection name
    data_exported = Signal(str)             # export file path
    data_imported = Signal(str, int)        # source path, item count

    # ── Embedding engine ────────────────────────────────────────────
    model_loaded = Signal(str)              # model_name
    model_loading = Signal(str, int)        # model_name, progress %
    model_unloaded = Signal(str)            # model_name
    embedding_generated = Signal(int)       # count

    # ── OCR ─────────────────────────────────────────────────────────
    ocr_completed = Signal(str, str)        # file_path, extracted_text
    ocr_error = Signal(str, str)            # file_path, error_msg
    ocr_progress = Signal(str, int)         # file_path, progress %

    # ── Job queue ───────────────────────────────────────────────────
    job_started = Signal(str, str)          # job_id, description
    job_finished = Signal(str, bool)        # job_id, success
    job_progress = Signal(str, int)         # job_id, progress %
    job_cancelled = Signal(str)             # job_id

    # ── Cluster ─────────────────────────────────────────────────────
    node_joined = Signal(str)               # node_id
    node_left = Signal(str)                 # node_id
    cluster_status = Signal(dict)           # status dict

    # ── Search ──────────────────────────────────────────────────────
    search_progress = Signal(int)           # progress %
    search_error = Signal(str)              # error message

    # ── Status ──────────────────────────────────────────────────────
    status_message = Signal(str)            # status bar message
    toast_requested = Signal(str, str)      # message, type (info/success/warning/error)
    gpu_info = Signal(dict)                 # GPU stats
    vram_usage = Signal(float, float)       # used_gb, total_gb

    # ── Settings ────────────────────────────────────────────────────
    theme_changed = Signal(str)             # theme name
    settings_changed = Signal(str, object)  # key, new_value
