# Structured logger — writes to both a file in ~/  and stdout simultaneously.

import logging
import os


class Logger:
    """Thin wrapper around stdlib logging with dual FileHandler + StreamHandler output."""

    def __init__(self, log_file="omnisort.log"):
        # Write the log file to the user's home directory so it's easy to find.
        log_path = os.path.join(os.path.expanduser("~"), log_file)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(log_path),
                logging.StreamHandler(),
            ],
        )
        self._logger = logging.getLogger("omnisort")

    def log(self, message):
        """Log an informational message (normal pipeline events)."""
        self._logger.info(message)

    def error(self, message):
        """Log an error (processing failures, DB write errors, OCR exceptions)."""
        self._logger.error(message)

    def warn(self, message):
        """Log a warning (soft failures and recoverable conditions)."""
        self._logger.warning(message)
