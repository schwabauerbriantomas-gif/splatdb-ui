#!/usr/bin/env python3
"""Take screenshots of SplatDB UI views."""

import sys
import os
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["SPLATSDB_NO_GL"] = "1"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer


def main():
    app = QApplication(sys.argv)
    from splatsdb_ui.utils.theme import load_theme
    app.setStyleSheet(load_theme())

    from splatsdb_ui.app import MainWindow

    window = MainWindow()
    window.show()

    # Correct tab indices (matches app.py order):
    # 0=explorer, 1=welcome, 2=search, 3=collections, 4=graph,
    # 5=spatial, 6=cluster, 7=ebm, 8=benchmark, 9=ocr, 10=config
    views = [
        (1, "welcome"),
        (2, "search"),
        (3, "collections"),
        (4, "graph"),
        (5, "spatial"),
        (6, "cluster"),
        (7, "ebm"),
        (8, "benchmark"),
        (9, "ocr"),
        (10, "config"),
    ]

    def capture():
        # Load inspector with demo data for explorer tab
        try:
            window.view_tabs.setCurrentIndex(0)
            app.processEvents()
            time.sleep(0.3)
            if "node_000" in window.splat3d._nodes:
                window.node_inspector.load_node(window.splat3d._nodes["node_000"])
                app.processEvents()
                time.sleep(0.2)
            pixmap = window.grab()
            pixmap.save("/tmp/splatsdb_ui_explorer.png")
            print(f"Screenshot explorer: {pixmap.width()}x{pixmap.height()}")
        except Exception as e:
            print(f"Explorer error: {e}")

        for idx, name in views:
            window.view_tabs.setCurrentIndex(idx)
            app.processEvents()
            time.sleep(0.4)
            pixmap = window.grab()
            path = f"/tmp/splatsdb_ui_{name}.png"
            pixmap.save(path)
            print(f"Screenshot {idx} ({name}): {pixmap.width()}x{pixmap.height()}")

        print("All screenshots taken!")
        app.quit()

    QTimer.singleShot(800, capture)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
