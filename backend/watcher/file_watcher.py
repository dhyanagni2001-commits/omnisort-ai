import os
import time
import json
import queue
import fcntl
import threading
import yaml
from concurrent.futures import ThreadPoolExecutor
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from backend.classifier.image_classifier import ImageClassifier, classify_document
from backend.classifier.llm_classifier import LLMClassifier
from backend.ocr.ocr_extractor import OCRExtractor
from backend.processor.pdf_process import PDFProcessor
from backend.processor.doc_process import DocxProcessor
from backend.processor.text_process import TextProcessor
from backend.sensitive_detection.sensitive import SensitiveDetector
from backend.duplicate_detection.duplicate_detector import DuplicateDetector
from backend.policy_engine.policy_engine import PolicyEngine
from backend.organizer.file_organizer import FileOrganizer
from backend.database import db
from backend.logger.logger import Logger
from backend.metrics.metrics import metrics

SUPPORTED_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"},
    "pdf": {".pdf"},
    "docx": {".docx", ".doc"},
    "text": {".txt", ".csv", ".md"},
    "video": {".mp4", ".mov", ".avi", ".mkv", ".m4v"},
    "audio": {".mp3", ".wav", ".aac", ".flac", ".m4a"},
    "archive": {".zip", ".rar", ".tar", ".gz", ".7z"},
}

# Temp/incomplete file suffixes — never process these
SKIP_SUFFIXES = {".crdownload", ".part", ".tmp", ".download", ".!ut"}

event_queue = queue.Queue()
_lock_fd = None

def _load_config():
    config_path = os.path.join(os.path.dirname(__file__), "../../configs/settings.yaml")
    with open(os.path.abspath(config_path)) as f:
        return yaml.safe_load(f)

def _acquire_lock():
    """Prevent multiple instances from running simultaneously."""
    global _lock_fd
    _lock_fd = open("/tmp/omnisort.lock", "w")
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except IOError:
        return False

def _should_skip(file_path):
    """Return True for browser temp/lock files that should never be processed."""
    name = os.path.basename(file_path)
    _, ext = os.path.splitext(name)
    if ext.lower() in SKIP_SUFFIXES:
        return True
    # Browser internal files: .com.brave.Browser.*, .DS_Store, etc.
    if name.startswith(".com.") or name.startswith("."):
        return True
    return False

class FileWatcher:
    def __init__(self, folder_path=None):
        self.config = _load_config()

        if folder_path:
            self.watch_folders = [os.path.expanduser(folder_path)]
        elif "watch_folders" in self.config:
            self.watch_folders = [os.path.expanduser(f) for f in self.config["watch_folders"]]
        else:
            self.watch_folders = [os.path.expanduser(self.config["watch_folder"])]

        self.folder_path = self.watch_folders[0]  # backward compat
        self.timeout = self.config.get("file_ready_timeout", 30)
        self._processing = set()
        self._lock = threading.Lock()
        # Fix 4: cap concurrent threads so 1000-file drops don't spawn 1000 threads
        self._executor = ThreadPoolExecutor(max_workers=4)
        # Fix 2: per-hash lock to prevent concurrent duplicate miss
        self._hash_locks: dict = {}
        self._hash_locks_lock = threading.Lock()

        self.event_handler = FileSystemEventHandler()
        self.event_handler.on_created = self.on_created
        self.event_handler.on_moved = self.on_moved
        self.observer = Observer()

        self.image_classifier = ImageClassifier()
        self.llm_classifier = LLMClassifier()
        self.ocr_extractor = OCRExtractor(self.config.get("tesseract_path", "/usr/local/bin/tesseract"))
        self.pdf_processor = PDFProcessor()
        self.docx_processor = DocxProcessor()
        self.text_processor = TextProcessor()
        self.sensitive_detector = SensitiveDetector()
        self.duplicate_detector = DuplicateDetector()
        self.policy_engine = PolicyEngine()
        self.file_organizer = FileOrganizer(os.path.expanduser(self.config["output_folder"]))
        self.logger = Logger(self.config.get("log_file", "omnisort.log"))

        db.init_db()

    def start(self):
        if not _acquire_lock():
            raise RuntimeError("Another OmniSort instance is already running.")

        for folder in self.watch_folders:
            if os.path.isdir(folder):
                self.observer.schedule(self.event_handler, folder, recursive=False)
                self.logger.log(f"Watching {folder}")
            else:
                self.logger.log(f"Skipping (not found): {folder}")

        self.observer.start()
        threading.Thread(target=self._scan_existing, daemon=True).start()

    def stop(self):
        self.observer.stop()
        self.observer.join()
        self._executor.shutdown(wait=False)
        self.logger.log("Stopped watching")

    def _get_hash_lock(self, file_hash: str) -> threading.Lock:
        with self._hash_locks_lock:
            if file_hash not in self._hash_locks:
                self._hash_locks[file_hash] = threading.Lock()
            return self._hash_locks[file_hash]

    def _scan_existing(self):
        """Process files already in any watch folder on startup."""
        time.sleep(1)  # let the observer settle first
        output_folder = os.path.abspath(self.file_organizer.output_folder)
        for folder in self.watch_folders:
            if not os.path.isdir(folder):
                continue
            for name in os.listdir(folder):
                file_path = os.path.join(folder, name)
                if not os.path.isfile(file_path):
                    continue
                if _should_skip(file_path):
                    continue
                if os.path.abspath(file_path).startswith(output_folder):
                    continue
                self.logger.log(f"Startup scan: {name}")
                self._process_file(file_path)

    def on_moved(self, event):
        if event.is_directory or _should_skip(event.dest_path):
            return
        output_folder = os.path.abspath(self.file_organizer.output_folder)
        if os.path.abspath(event.dest_path).startswith(output_folder):
            return
        self._executor.submit(self._process_file, event.dest_path)

    def on_created(self, event):
        if event.is_directory or _should_skip(event.src_path):
            return
        output_folder = os.path.abspath(self.file_organizer.output_folder)
        if os.path.abspath(event.src_path).startswith(output_folder):
            return
        self._executor.submit(self._process_file, event.src_path)

    def _wait_for_file_ready(self, file_path):
        start, last_size = time.time(), -1
        while time.time() - start < self.timeout:
            try:
                size = os.path.getsize(file_path)
            except OSError:
                time.sleep(0.5)
                continue
            if size == last_size and size > 0:
                return True
            last_size = size
            time.sleep(0.5)
        return False

    def _get_type(self, ext):
        for ftype, exts in SUPPORTED_EXTENSIONS.items():
            if ext in exts:
                return ftype
        return "other"

    def _process_file(self, file_path):
        real_path = os.path.abspath(file_path)

        # Deduplicate concurrent events for the same file
        with self._lock:
            if real_path in self._processing:
                return
            self._processing.add(real_path)

        try:
            if not self._wait_for_file_ready(real_path):
                self.logger.error(f"Timed out: {real_path}")
                return

            if not os.path.isfile(real_path):
                return

            _, ext = os.path.splitext(real_path)
            ext = ext.lower()
            file_type = self._get_type(ext)

            metadata = {"category": "Other", "text": ""}

            try:
                # Fix 5: check filename itself for PII before touching content
                filename_pii = self.sensitive_detector.detect_sensitive_info(
                    os.path.basename(real_path)
                )

                if file_type == "image":
                    metadata["category"] = self.image_classifier.predict(real_path)
                    try:
                        metadata["text"] = self.ocr_extractor.extract_text(real_path)
                    except Exception:
                        metrics.record_ocr_failure()

                elif file_type == "pdf":
                    text, pdf_meta = self.pdf_processor.process(real_path)
                    # Fix 1: scanned PDFs have no text layer — fall back to OCR
                    if not text.strip():
                        text = self.ocr_extractor.extract_text_from_pdf_page(real_path)
                    metadata["text"] = text
                    metadata.update({k: str(v) for k, v in (pdf_meta or {}).items()})

                elif file_type == "docx":
                    text, _ = self.docx_processor.process(real_path)
                    metadata["text"] = text

                elif file_type == "text":
                    text = self.text_processor.process(real_path)
                    metadata["text"] = text

                elif file_type == "video":
                    metadata["category"] = "Videos"

                elif file_type == "audio":
                    metadata["category"] = "Audio"

                elif file_type == "archive":
                    metadata["category"] = "Archives"

                # Fix 5: merge filename PII with content PII — both gate the LLM call
                text = metadata.get("text", "")
                content_pii = self.sensitive_detector.detect_sensitive_info(text)
                sensitive_info = {**filename_pii, **content_pii}
                metadata["sensitive_info"] = sensitive_info

                if file_type in ("pdf", "docx", "text"):
                    _clf_start = time.perf_counter()
                    category = classify_document(text)
                    if category == "Documents" and not sensitive_info:
                        _llm_start = time.perf_counter()
                        category = self.llm_classifier.classify(text)
                        metrics.record_llm_call((time.perf_counter() - _llm_start) * 1000)
                    metrics.record_classification((time.perf_counter() - _clf_start) * 1000)
                    metadata["category"] = category

                file_hash = self.duplicate_detector.calculate_file_hash(real_path)

                # Fix 2: per-hash lock — prevents two identical files processed simultaneously
                # from both passing is_duplicate() as False before either writes to DB
                with self._get_hash_lock(file_hash):
                    metadata["duplicate"] = self.duplicate_detector.is_duplicate(file_hash)
                    metadata["file_hash"] = file_hash

                    self.policy_engine.apply_policies(real_path, metadata)

                    # Fix 3: move first, then DB write — if move fails, DB is never touched
                    dest_path = self.file_organizer.organize_file(real_path, metadata)

                    is_duplicate = bool(metadata.get("is_duplicate"))
                    metrics.record_file_processed(is_duplicate=is_duplicate)

                    record = {
                        "filename": os.path.basename(file_path),
                        "original_path": file_path,
                        "destination_path": dest_path,
                        "extension": ext,
                        "category": metadata.get("category", "Other"),
                        "file_size": os.path.getsize(dest_path) if os.path.exists(dest_path) else 0,
                        "file_hash": file_hash,
                        "is_duplicate": 1 if is_duplicate else 0,
                        "is_sensitive": 1 if metadata.get("is_sensitive") else 0,
                        "sensitive_types": metadata.get("sensitive_types", "[]"),
                    }

                    # Fix 3: DB write isolated — failure logged but doesn't lose the sorted file
                    try:
                        db.insert_file(record)
                    except Exception as db_err:
                        self.logger.error(f"DB write failed for {record['filename']}: {db_err}")

                event_queue.put({
                    "type": "file_processed",
                    "filename": record["filename"],
                    "category": record["category"],
                    "is_duplicate": record["is_duplicate"],
                    "is_sensitive": record["is_sensitive"],
                })

                self.logger.log(f"Sorted: {record['filename']} → {record['category']}")

            except Exception as e:
                self.logger.error(f"Error processing {real_path}: {e}")
                event_queue.put({"type": "error", "filename": os.path.basename(file_path), "error": str(e)})

        finally:
            with self._lock:
                self._processing.discard(real_path)
