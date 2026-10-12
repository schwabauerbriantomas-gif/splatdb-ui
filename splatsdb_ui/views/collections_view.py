# SPDX-License-Identifier: GPL-3.0
"""Collections view — manage SplatsDB vector collections."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QFrame,
    QInputDialog, QMessageBox, QSizePolicy, QMenu, QLineEdit,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QColor
from splatsdb_ui.utils.theme import Colors
from splatsdb_ui.utils.icons import icon


class CollectionsView(QWidget):
    """Full-featured collections manager with list, detail panel, CRUD."""

    collection_renamed = Signal(str, str)   # old_name, new_name
    collections_reordered = Signal(list)     # new order of names

    def __init__(self, signals, state):
        super().__init__()
        self.signals = signals
        self.state = state
        self._collections = []
        self._build_ui()
        self._connect_signals()
        # Auto-load on start
        QTimer.singleShot(500, self._refresh)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ── Header ──
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("Collections")
        title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: 18px; font-weight: 700;"
        )
        header.addWidget(title)

        self._count_badge = QLabel("")
        self._count_badge.setFixedHeight(22)
        self._count_badge.setAlignment(Qt.AlignCenter)
        self._count_badge.setStyleSheet(
            f"background: {Colors.ACCENT_DARK}; color: {Colors.ACCENT}; "
            f"border-radius: 11px; padding: 0 8px; font-size: 11px; font-weight: 600;"
        )
        self._count_badge.hide()
        header.addWidget(self._count_badge)
        header.addStretch()

        self._import_btn = QPushButton(" Import")
        self._import_btn.setIcon(icon("upload", Colors.TEXT))
        self._import_btn.setStyleSheet(self._btn_style(ghost=True))
        header.addWidget(self._import_btn)

        self._refresh_btn = QPushButton()
        self._refresh_btn.setIcon(icon("refresh", Colors.TEXT_DIM))
        self._refresh_btn.setFixedSize(32, 32)
        self._refresh_btn.setStyleSheet(self._icon_btn_style())
        self._refresh_btn.setToolTip("Refresh collections")
        header.addWidget(self._refresh_btn)

        self._add_btn = QPushButton()
        self._add_btn.setIcon(icon("plus", Colors.BG))
        self._add_btn.setFixedSize(32, 32)
        self._add_btn.setStyleSheet(
            f"background: {Colors.ACCENT}; border-radius: 6px; border: none;"
        )
        self._add_btn.setToolTip("Create collection")
        header.addWidget(self._add_btn)

        self._del_btn = QPushButton()
        self._del_btn.setIcon(icon("trash", "#fca5a5"))
        self._del_btn.setFixedSize(32, 32)
        self._del_btn.setStyleSheet(self._icon_btn_style())
        self._del_btn.setToolTip("Delete selected collection")
        self._del_btn.setEnabled(False)
        header.addWidget(self._del_btn)

        layout.addLayout(header)

        # ── Search / Filter bar ──
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Filter collections...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedHeight(30)
        self._search_input.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {Colors.BG_RAISED};"
            f"  border: 1px solid {Colors.BORDER};"
            f"  border-radius: 6px;"
            f"  padding: 4px 10px;"
            f"  color: {Colors.TEXT};"
            f"  font-size: 12px;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border-color: {Colors.ACCENT};"
            f"}}"
        )
        self._search_input.textChanged.connect(self._filter_collections)
        search_row.addWidget(self._search_input, stretch=1)
        layout.addLayout(search_row)

        # ── Splitter: tree + detail ──
        splitter_layout = QHBoxLayout()
        splitter_layout.setSpacing(12)

        # Tree with drag-and-drop enabled
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Vectors", "Dimension", "Size", "Modified"])
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setAlternatingRowColors(True)
        self.tree.setDragDropMode(QTreeWidget.InternalMove)
        self.tree.setDefaultDropAction(Qt.MoveAction)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setAnimated(True)
        self.tree.setIndentation(16)
        self.tree.setStyleSheet(
            f"QTreeWidget {{ background: {Colors.BG_RAISED}; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 6px; }}"
            f"QTreeWidget::item:alternate {{ background: {Colors.BG}; }}"
            f"QTreeWidget::item:selected {{ background: {Colors.ACCENT_DARK}; color: {Colors.TEXT}; }}"
        )
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.model().rowsMoved.connect(self._on_rows_moved)
        splitter_layout.addWidget(self.tree, stretch=3)

        # Detail panel with opacity effect for smooth expand/collapse
        self._detail = QFrame()
        self._opacity_effect = QGraphicsOpacityEffect(self._detail)
        self._opacity_effect.setOpacity(1.0)
        self._detail.setGraphicsEffect(self._opacity_effect)
        self._detail.setStyleSheet(
            f"background: {Colors.BG_RAISED}; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 8px; padding: 16px;"
        )
        detail_layout = QVBoxLayout(self._detail)
        detail_layout.setSpacing(8)

        self._detail_title = QLabel("Select a collection")
        self._detail_title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: 15px; font-weight: 600;"
        )
        detail_layout.addWidget(self._detail_title)

        self._detail_info = QLabel("")
        self._detail_info.setWordWrap(True)
        self._detail_info.setStyleSheet(
            f"color: {Colors.TEXT_DIM}; font-size: 12px; line-height: 1.5;"
        )
        detail_layout.addWidget(self._detail_info)

        # Stats badge row inside detail
        self._detail_stats = QLabel("")
        self._detail_stats.setWordWrap(True)
        self._detail_stats.setStyleSheet(
            f"color: {Colors.ACCENT}; font-size: 11px; font-weight: 600;"
            f"background: {Colors.ACCENT_DARK};"
            f"border-radius: 6px; padding: 6px 10px;"
        )
        self._detail_stats.hide()
        detail_layout.addWidget(self._detail_stats)

        detail_layout.addStretch()

        splitter_layout.addWidget(self._detail, stretch=2)
        layout.addLayout(splitter_layout, stretch=1)

        # ── Empty state ──
        self._empty = QWidget()
        empty_layout = QVBoxLayout(self._empty)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_icon = QLabel("📁")
        empty_icon.setStyleSheet("font-size: 48px;")
        empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_icon)
        empty_title = QLabel("No collections yet")
        empty_title.setStyleSheet(
            f"color: {Colors.TEXT}; font-size: 16px; font-weight: 600;"
        )
        empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)
        empty_sub = QLabel("Create your first collection to get started.")
        empty_sub.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 12px;")
        empty_sub.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_sub)
        layout.addWidget(self._empty, stretch=1)
        self._empty.hide()

        # Status bar
        self.status = QLabel("Ready")
        self.status.setStyleSheet(f"color: {Colors.TEXT_DIM}; font-size: 11px;")
        layout.addWidget(self.status)

    def _btn_style(self, ghost=False):
        if ghost:
            return (
                f"QPushButton {{ color: {Colors.TEXT}; background: transparent; "
                f"border: 1px solid {Colors.BORDER}; border-radius: 6px; "
                f"padding: 6px 14px; font-size: 12px; }}"
                f"QPushButton:hover {{ border-color: {Colors.ACCENT}; color: {Colors.ACCENT}; }}"
            )
        return (
            f"QPushButton {{ color: {Colors.BG}; background: {Colors.ACCENT}; "
            f"border: none; border-radius: 6px; padding: 6px 14px; }}"
        )

    def _icon_btn_style(self):
        return (
            f"QPushButton {{ background: transparent; border: 1px solid {Colors.BORDER}; "
            f"border-radius: 6px; }}"
            f"QPushButton:hover {{ border-color: {Colors.ACCENT}; background: {Colors.ACCENT_DARK}; }}"
            f"QPushButton:disabled {{ opacity: 0.4; }}"
        )

    def _connect_signals(self):
        self._refresh_btn.clicked.connect(self._refresh)
        self._add_btn.clicked.connect(self._create_collection)
        self._del_btn.clicked.connect(self._delete_collection)
        if hasattr(self.signals, "collections_loaded"):
            self.signals.collections_loaded.connect(self._on_collections_loaded)

    # ── Refresh & populate ────────────────────────────────────────

    def _refresh(self):
        self.status.setText("Refreshing...")
        if hasattr(self.signals, "refresh_collections"):
            self.signals.refresh_collections.emit()

    def _on_collections_loaded(self, collections):
        self._collections = collections if isinstance(collections, list) else []
        self._populate_tree()

    def _populate_tree(self):
        self.tree.clear()
        for col in self._collections:
            name = col.get("name", col.get("collection", "unknown"))
            vectors = str(col.get("vectors", col.get("count", 0)))
            item = QTreeWidgetItem([
                name,
                vectors,
                str(col.get("dimension", "—")),
                str(col.get("size", "—")),
                str(col.get("modified", "—")),
            ])
            item.setData(0, Qt.UserRole, col)
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.tree.addTopLevelItem(item)

        count = len(self._collections)
        if count > 0:
            self._empty.hide()
            self.tree.show()
            self._detail.show()
            self._count_badge.setText(str(count))
            self._count_badge.show()
        else:
            self._empty.show()
            self.tree.hide()
            self._detail.hide()
            self._count_badge.hide()
        self.status.setText(f"{count} collection{'s' if count != 1 else ''}")

    # ── Search / filter ──────────────────────────────────────────

    def _filter_collections(self, text: str):
        """Show/hide tree items based on search text."""
        search = text.lower().strip()
        root = self.tree.invisibleRootItem()
        visible_count = 0
        for i in range(root.childCount()):
            item = root.child(i)
            name = item.text(0).lower()
            if not search or search in name:
                item.setHidden(False)
                visible_count += 1
            else:
                item.setHidden(True)
        # Show status with filter count
        total = root.childCount()
        if search and total > 0:
            self.status.setText(f"Showing {visible_count} of {total} collections")
        elif not search:
            self.status.setText(f"{total} collection{'s' if total != 1 else ''}")

    # ── Item interactions ─────────────────────────────────────────

    def _on_item_clicked(self, item, _col):
        self._del_btn.setEnabled(True)
        col = item.data(0, Qt.UserRole) or {}
        name = col.get("name", col.get("collection", "unknown"))
        self._detail_title.setText(name)
        lines = []
        for key, label in [("vectors", "Vectors"), ("dimension", "Dimension"),
                           ("size", "Size"), ("modified", "Modified"),
                           ("distance", "Distance"), ("status", "Status")]:
            val = col.get(key, "—")
            lines.append(f"<b>{label}:</b> {val}")
        self._detail_info.setText("<br>".join(lines))

        # Show collection stats badge
        vectors = col.get("vectors", col.get("count", 0))
        dim = col.get("dimension", "—")
        self._detail_stats.setText(f"  {vectors} vectors  |  dim: {dim}  ")
        self._detail_stats.show()

        # Smooth fade-in for detail panel
        self._fade_detail_in()

    def _on_item_double_clicked(self, item, _col):
        """Start inline rename on double-click."""
        self.tree.editItem(item, 0)

    def _on_rows_moved(self, *args):
        """Handle drag-and-drop reordering."""
        names = []
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            col = item.data(0, Qt.UserRole) or {}
            names.append(col.get("name", col.get("collection", "")))
        self.collections_reordered.emit(names)
        self.status.setText("Collections reordered")

    # ── Context menu ──────────────────────────────────────────────

    def _show_context_menu(self, pos):
        """Show right-click context menu on tree items."""
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background-color: {Colors.BG_RAISED}; "
            f"border: 1px solid {Colors.BORDER_LITE}; "
            f"border-radius: 8px; padding: 4px; }}"
            f"QMenu::item {{ padding: 6px 20px; border-radius: 4px; "
            f"color: {Colors.TEXT}; }}"
            f"QMenu::item:selected {{ background-color: {Colors.ACCENT_DARK}; "
            f"color: {Colors.ACCENT}; }}"
            f"QMenu::separator {{ height: 1px; background: {Colors.BORDER}; "
            f"margin: 4px 8px; }}"
        )

        if item:
            col_data = item.data(0, Qt.UserRole) or {}
            name = col_data.get("name", col_data.get("collection", ""))

            rename_action = menu.addAction("Rename")
            rename_action.setIcon(icon("edit", Colors.TEXT_DIM))
            rename_action.triggered.connect(lambda: self._rename_collection(item))

            duplicate_action = menu.addAction("Duplicate")
            duplicate_action.setIcon(icon("copy", Colors.TEXT_DIM))
            duplicate_action.triggered.connect(lambda: self._duplicate_collection(item))

            menu.addSeparator()

            delete_action = menu.addAction("Delete")
            delete_action.setIcon(icon("trash", Colors.ERROR))
            delete_action.triggered.connect(lambda: self._delete_specific(item))
        else:
            create_action = menu.addAction("Create Collection")
            create_action.setIcon(icon("plus", Colors.BG))
            create_action.triggered.connect(self._create_collection)

            menu.addSeparator()

            refresh_action = menu.addAction("Refresh")
            refresh_action.setIcon(icon("refresh", Colors.TEXT_DIM))
            refresh_action.triggered.connect(self._refresh)

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # ── Detail panel animation ────────────────────────────────────

    def _fade_detail_in(self):
        """Smooth fade-in animation for the detail panel."""
        self._detail_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._detail_anim.setDuration(250)
        self._detail_anim.setStartValue(0.3)
        self._detail_anim.setEndValue(1.0)
        self._detail_anim.setEasingCurve(QEasingCurve.InOutCubic)
        self._detail_anim.start()

    # ── CRUD operations ───────────────────────────────────────────

    def _create_collection(self):
        name, ok = QInputDialog.getText(
            self, "Create Collection", "Collection name:",
        )
        if ok and name.strip():
            self.status.setText(f"Creating '{name}'...")
            if hasattr(self.signals, "create_collection"):
                self.signals.create_collection.emit(name.strip())
            QTimer.singleShot(1000, self._refresh)

    def _delete_collection(self):
        item = self.tree.currentItem()
        if not item:
            return
        self._delete_specific(item)

    def _delete_specific(self, item):
        col = item.data(0, Qt.UserRole) or {}
        name = col.get("name", col.get("collection", ""))
        reply = QMessageBox.question(
            self, "Delete Collection",
            f"Delete collection '{name}'?\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.status.setText(f"Deleting '{name}'...")
            if hasattr(self.signals, "delete_collection"):
                self.signals.delete_collection.emit(name)
            QTimer.singleShot(1000, self._refresh)

    def _rename_collection(self, item):
        """Trigger inline rename on the given item."""
        col = item.data(0, Qt.UserRole) or {}
        old_name = col.get("name", col.get("collection", ""))
        self.tree.editItem(item, 0)
        # Connect to capture the finished edit
        self.tree.itemChanged.connect(lambda changed_item, col_idx:
            self._on_rename_finished(changed_item, old_name))

    def _on_rename_finished(self, item, old_name: str):
        """Handle completed inline rename."""
        new_name = item.text(0).strip()
        if new_name and new_name != old_name:
            self.status.setText(f"Renamed '{old_name}' to '{new_name}'")
            self.collection_renamed.emit(old_name, new_name)
            # Update stored data
            col = item.data(0, Qt.UserRole) or {}
            col["name"] = new_name
            item.setData(0, Qt.UserRole, col)
        # Disconnect to avoid double-firing
        try:
            self.tree.itemChanged.disconnect()
        except RuntimeError:
            pass

    def _duplicate_collection(self, item):
        """Duplicate a collection with a new name."""
        col = item.data(0, Qt.UserRole) or {}
        name = col.get("name", col.get("collection", ""))
        new_name, ok = QInputDialog.getText(
            self, "Duplicate Collection",
            f"New name for duplicate of '{name}':",
            text=f"{name}_copy",
        )
        if ok and new_name.strip():
            self.status.setText(f"Duplicating '{name}' as '{new_name}'...")
            if hasattr(self.signals, "create_collection"):
                self.signals.create_collection.emit(new_name.strip())
            QTimer.singleShot(1000, self._refresh)

    def get_params(self) -> list:
        return [
            {"name": "dimension", "label": "Dimension", "type": "spin",
             "min": 1, "max": 8192, "default": 640},
            {"name": "distance", "label": "Distance", "type": "combo",
             "options": ["cosine", "l2", "ip"]},
        ]
