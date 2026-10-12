# SPDX-License-Identifier: GPL-3.0
"""Search worker — runs search queries in a QThread."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, QThread


class SearchWorker(QObject):
    """Executes a search query against the SplatsDB backend in a background thread."""

    finished = Signal(list)       # list[SearchResult]
    progress = Signal(int)        # 0–100
    error = Signal(str)           # user-friendly error message

    def __init__(
        self,
        query: str,
        top_k: int = 10,
        client_url: str = "",
        api_key: str = "",
        *,
        thread: QThread | None = None,
    ):
        super().__init__()
        self.query = query
        self.top_k = top_k
        self.client_url = client_url
        self.api_key = api_key
        self._thread = thread  # for isInterruptionRequested()

    def run(self):
        """Execute the search query. Emits progress, then finished or error."""
        client = None
        try:
            self.progress.emit(0)

            if not self.query or not self.query.strip():
                self.error.emit("Search query is empty — please enter a search term.")
                self.finished.emit([])
                return

            self.progress.emit(10)

            if self._is_cancelled():
                self.finished.emit([])
                return

            from splatsdb_ui.utils.api_client import SplatsDBClient, SearchResult

            client = SplatsDBClient(base_url=self.client_url, api_key=self.api_key)
            self.progress.emit(30)

            if self._is_cancelled():
                self.finished.emit([])
                return

            results = client.search(self.query, top_k=self.top_k)
            self.progress.emit(90)

            if self._is_cancelled():
                self.finished.emit([])
                return

            self.progress.emit(100)
            self.finished.emit(results)

        except ConnectionError:
            msg = (
                "Could not connect to SplatsDB backend.\n"
                "Make sure the engine is running and accessible at "
                f"{self.client_url or 'http://127.0.0.1:8199'}."
            )
            self.error.emit(msg)
            self.finished.emit([])
        except TimeoutError:
            msg = (
                "Search timed out — the backend took too long to respond.\n"
                "Try again with a simpler query or a smaller top-k value."
            )
            self.error.emit(msg)
            self.finished.emit([])
        except PermissionError:
            msg = "Authentication failed — check your API key in engine settings."
            self.error.emit(msg)
            self.finished.emit([])
        except Exception as e:
            # Map common library errors to friendly messages
            err_str = str(e).lower()
            if "connection" in err_str or "refused" in err_str:
                msg = (
                    "Connection refused by backend.\n"
                    f"Is SplatsDB running at {self.client_url or 'http://127.0.0.1:8199'}?"
                )
            elif "timeout" in err_str:
                msg = "Search timed out. Try again or reduce top-k."
            elif "401" in err_str or "403" in err_str or "unauthorized" in err_str:
                msg = "Access denied — verify your API key."
            else:
                msg = f"Search failed: {e}"
            self.error.emit(msg)
            self.finished.emit([])
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    def _is_cancelled(self) -> bool:
        """Check whether the hosting QThread has been requested to stop."""
        if self._thread is not None:
            return self._thread.isInterruptionRequested()
        return False
