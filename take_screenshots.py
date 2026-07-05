#!/usr/bin/env python3
"""Take screenshots of SplatDB UI views."""

import sys
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["SPLATSDB_NO_GL"] = "1"  # Disable 3D for headless

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer


def main():
    app = QApplication(sys.argv)
    from splatsdb_ui.utils.theme import load_theme
    load_theme()

    from splatsdb_ui.app import MainWindow

    window = MainWindow()
    window.show()

    views = [
        (0, "explorer"),
        (1, "welcome"),
        (2, "search"),
        (3, "collections"),
        (4, "graph"),
        (5, "spatial"),
        (6, "cluster"),
        (7, "benchmark"),
        (8, "ocr"),
        (9, "config"),
    ]

    def capture():
        import time

        # Load inspector with demo data for explorer tab screenshot
        try:
            if "node_000" in window.splat3d._nodes:
                window.node_inspector.load_node(window.splat3d._nodes["node_000"])
                window.file_preview.preview_file(
                    "/mnt/d/splatsdb-ui/splatsdb_ui/resources/icons/search.svg")
                time.sleep(0.2)
        except Exception:
            pass

        for idx, name in views:
            window.view_tabs.setCurrentIndex(idx)
            time.sleep(0.15)
            pixmap = window.grab()
            path = f"/tmp/splatsdb_ui_{name}.png"
            pixmap.save(path)
            print(f"Screenshot {idx} ({name}): {pixmap.width()}x{pixmap.height()}")

        print("All screenshots taken!")
        app.quit()

    QTimer.singleShot(500, capture)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
