# SPDX-License-Identifier: GPL-3.0
"""Search mixin — global search handling with QThread worker."""

from PySide6.QtCore import QThread

from splatsdb_ui.workers.search_worker import SearchWorker


class SearchMixin:
    """Search behavior mixin for MainWindow.

    Wires search bar → QThread → backend → results display.
    Breaks the infinite recursion that existed when execute_search re-emitted
    the same signal that triggered it.
    """

    def execute_global_search(self, query: str):
        """Called when user submits a search query.

        Runs the search in a background QThread and feeds results back to
        SearchView.show_results() — does NOT re-emit search_requested.
        """
        view = self._views.get("search")
        if view is None:
            return
        view.set_loading(True)

        # Get connection params from active engine
        engine = self.engine_manager.active_engine()
        url = engine.url if engine else self.state.connection.url
        api_key = engine.api_key if engine else self.state.connection.api_key
        top_k = view.top_k.value()

        # Create thread + worker
        thread = QThread(self)
        worker = SearchWorker(query, top_k=top_k, client_url=url, api_key=api_key)
        worker.moveToThread(thread)

        # Wire lifecycle
        thread.started.connect(worker.run)
        worker.finished.connect(view.show_results)
        worker.finished.connect(lambda: view.set_loading(False))
        worker.error.connect(self._on_search_error)
        worker.error.connect(lambda: view.set_loading(False))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Store references to prevent GC
        if not hasattr(self, "_search_threads"):
            self._search_threads = []
        self._search_threads.append(thread)

        thread.start()

    def _on_search_error(self, msg: str):
        """Handle search errors."""
        self.signals.status_message.emit(f"Search error: {msg}")
