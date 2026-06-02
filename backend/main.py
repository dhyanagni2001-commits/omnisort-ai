import threading
import uvicorn
import yaml
import os

from backend.watcher.file_watcher import FileWatcher
from backend.api.api import app

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "../configs/settings.yaml")
    with open(os.path.abspath(config_path)) as f:
        return yaml.safe_load(f)

def run_api(host, port):
    uvicorn.run(app, host=host, port=port, log_level="warning")

if __name__ == "__main__":
    config = load_config()

    watcher = FileWatcher()
    watcher.start()

    api_thread = threading.Thread(
        target=run_api,
        args=(config.get("api_host", "127.0.0.1"), config.get("api_port", 8000)),
        daemon=True
    )
    api_thread.start()

    print(f"OmniSort AI running — watching {watcher.folder_path}")
    print(f"API at http://{config.get('api_host', '127.0.0.1')}:{config.get('api_port', 8000)}")

    try:
        watcher.observer.join()
    except KeyboardInterrupt:
        watcher.stop()
        print("Stopped.")
