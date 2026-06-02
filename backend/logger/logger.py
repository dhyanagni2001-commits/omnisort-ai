import logging
import os

class Logger:
    def __init__(self, log_file="omnisort.log"):
        log_path = os.path.join(os.path.expanduser("~"), log_file)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(log_path),
                logging.StreamHandler()
            ]
        )
        self._logger = logging.getLogger("omnisort")

    def log(self, message):
        self._logger.info(message)

    def error(self, message):
        self._logger.error(message)

    def warn(self, message):
        self._logger.warning(message)
