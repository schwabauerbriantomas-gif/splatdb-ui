# SPDX-License-Identifier: GPL-3.0
"""Search worker — runs search queries in a QThread."""

from PySide6.QtCore import QObject, Signal
from splatsdb_ui.utils.api_client import SplatsDBClient


class SearchWorker(QObject):
    """Executes a search query against the SplatsDB backend in a background thread."""
    finished = Signal(list)  # list[SearchResult]
    error = Signal(str)

    def __init__(self, query: str, top_k: int = 10, client_url: str = "", api_key: str = ""):
        super().__init__()
        self.query = query
        self.top_k = top_k
        self.client_url = client_url
        self.api_key = api_key

    def run(self):
        client = None
        try:
            client = SplatsDBClient(base_url=self.client_url, api_key=self.api_key)
            results = client.search(self.query, top_k=self.top_k)
            self.finished.emit(results.results)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if client is not None:
                client.close()
