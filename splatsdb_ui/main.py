# SPDX-License-Identifier: GPL-3.0
"""Application entry point."""

import sys
import os
import argparse
import logging


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="splatsdb-ui",
        description="SplatsDB — Vector Database Desktop UI",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Enable debug mode: FPS counters, debug overlays, verbose logging.",
    )
    parser.add_argument(
        "--theme",
        type=str,
        default="dark",
        choices=["dark", "light"],
        help="UI theme to use (default: dark). Light theme is experimental.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable verbose (DEBUG-level) logging.",
    )
    return parser


def run():
    """Launch the SplatsDB UI application."""
    parser = build_parser()
    args = parser.parse_args()

    # ── Logging ──
    log_level = logging.DEBUG if (args.debug or args.verbose) else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("splatsdb_ui")
    log.debug("Debug mode: %s  |  Theme: %s", args.debug, args.theme)

    # High DPI support
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon

    from splatsdb_ui import __app_name__
    from splatsdb_ui.app import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("SplatsDB")
    app.setApplicationVersion("0.1.0")

    # Store flags as application properties so any component can read them
    app.setProperty("debug_mode", args.debug)
    app.setProperty("theme_name", args.theme)

    # Load theme
    from splatsdb_ui.utils.theme import load_theme
    app.setStyleSheet(load_theme())

    window = MainWindow()

    # ── Debug overlays ──
    if args.debug:
        try:
            from splatsdb_ui.utils.debug import enable_debug_overlays
            enable_debug_overlays(window)
            log.debug("Debug overlays enabled")
        except ImportError:
            log.warning("debug utils not available — skipping overlays")

    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
