# Entry point — starts the file watcher and the FastAPI server as parallel processes.

import threading
import uvicorn
import yaml
import os

from backend.watcher.file_watcher import FileWatcher
from backend.api.api import app


def load_config():
    # Resolve the config path relative to this file so it works from any cwd.
    config_path = os.path.join(os.path.dirname(__file__), "../configs/settings.yaml")
    with open(os.path.abspath(config_path)) as f:
        return yaml.safe_load(f)


def run_api(host, port):
    # log_level="warning" suppresses per-request access noise in the terminal.
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    config = load_config()

    # Start the watchdog observer (blocks on observer.join at the bottom).
    watcher = FileWatcher()
    watcher.start()

    # Run the API in a daemon thread so it exits when the main process exits.
    api_thread = threading.Thread(
        target=run_api,
        args=(config.get("api_host", "127.0.0.1"), config.get("api_port", 8000)),
        daemon=True,
    )
    api_thread.start()

    print(f"OmniSort AI running — watching {watcher.folder_path}")
    print(f"API at http://{config.get('api_host', '127.0.0.1')}:{config.get('api_port', 8000)}")

    try:
        # Block the main thread until the user presses Ctrl-C.
        watcher.observer.join()
    except KeyboardInterrupt:
        watcher.stop()
        print("Stopped.")
