#!/usr/bin/env python3
"""
MCM Cobalt Tablo - Main Entry Point
Initializes the application, sets up logging, and launches the GUI.
"""

import sys
import logging
from pathlib import Path

# Configure logging
def setup_logging(log_dir: Path = None) -> None:
    if log_dir is None:
        log_dir = Path.cwd() / "logs"
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "mcm_cobalt_tablo.log"

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.info("MCM Cobalt Tablo application started")


def main() -> int:
    """Application entry point."""
    try:
        setup_logging()

        from gui.interface import MCMCobaltApp

        app = MCMCobaltApp()
        return app.run()

    except Exception as e:
        logging.exception(f"Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
