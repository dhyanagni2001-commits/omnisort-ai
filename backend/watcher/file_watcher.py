# Core orchestrator — watches folders, runs the classification pipeline for every new file.

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
from backend.classifier.ml_classifier import MLClassifier
from backend.rules.rules_engine import RulesEngine
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
from backend.embeddings.embedding import embed_text

# Maps a type key to the set of extensions that belong to it.
SUPPORTED_EXTENSIONS = {
    "image":   {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"},
    "pdf":     {".pdf"},
    "docx":    {".docx", ".doc"},
    "text":    {".txt", ".csv", ".md"},
    "video":   {".mp4", ".mov", ".avi", ".mkv", ".m4v"},
    "audio":   {".mp3", ".wav", ".aac", ".flac", ".m4a"},
    "archive": {".zip", ".rar", ".tar", ".gz", ".7z"},
}

# Files with these extensions are browser download temps — never stable enough to process.
SKIP_SUFFIXES = {".crdownload", ".part", ".tmp", ".download", ".!ut"}

# Shared queue: _process_file puts events here; the WebSocket endpoint drains it.
event_queue = queue.Queue()

# Holds the open file descriptor for the process lock so the OS keeps it alive.
_lock_fd = None


def _load_config():
    # Merge settings.yaml with optional Docker environment variable overrides.
    config_path = os.path.join(os.path.dirname(__file__), "../../configs/settings.yaml")
    with open(os.path.abspath(config_path)) as f:
        config = yaml.safe_load(f)
    if os.environ.get("OMNISORT_WATCH_FOLDER"):
        config["watch_folders"] = [os.environ["OMNISORT_WATCH_FOLDER"]]
    if os.environ.get("OMNISORT_OUTPUT_FOLDER"):
        config["output_folder"] = os.environ["OMNISORT_OUTPUT_FOLDER"]
    return config


def _acquire_lock():
    # fcntl non-blocking exclusive lock on a pid file prevents two instances running at once.
    global _lock_fd
    _lock_fd = open("/tmp/omnisort.lock", "w")
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except IOError:
        return False


def _should_skip(file_path):
    # Reject browser temp files (.crdownload, .part …) and macOS metadata (. prefix).
    name = os.path.basename(file_path)
    _, ext = os.path.splitext(name)
    if ext.lower() in SKIP_SUFFIXES:
        return True
    # Covers .DS_Store, .com.brave.Browser.*, .com.google.Chrome.* etc.
    if name.startswith(".com.") or name.startswith("."):
        return True
    return False


class FileWatcher:
    """Watches one or more folders and runs the full pipeline for every incoming file."""

    def __init__(self, folder_path=None):
        self.config = _load_config()

        # Resolve watch folders: CLI arg > watch_folders list > legacy watch_folder key.
        if folder_path:
            self.watch_folders = [os.path.expanduser(folder_path)]
        elif "watch_folders" in self.config:
            self.watch_folders = [os.path.expanduser(f) for f in self.config["watch_folders"]]
        else:
            self.watch_folders = [os.path.expanduser(self.config["watch_folder"])]

        # Kept for backward compatibility with callers that read .folder_path.
        self.folder_path = self.watch_folders[0]
        self.timeout = self.config.get("file_ready_timeout", 30)

        # _processing tracks in-flight paths so concurrent watchdog events for the
        # same file don't trigger the pipeline twice.
        self._processing = set()
        self._lock = threading.Lock()

        # Bounded pool prevents a mass file-drop from spawning unbounded threads.
        self._executor = ThreadPoolExecutor(max_workers=4)

        # Per-hash locks make the duplicate-check + move + DB-write sequence atomic,
        # so two identical files processed simultaneously can't both slip past the
        # duplicate check before either has written to the database.
        self._hash_locks: dict = {}
        self._hash_locks_lock = threading.Lock()

        # Wire watchdog callbacks to our methods.
        self.event_handler = FileSystemEventHandler()
        self.event_handler.on_created = self.on_created
        self.event_handler.on_moved = self.on_moved
        self.observer = Observer()

        # Instantiate all pipeline components.
        self.image_classifier   = ImageClassifier()
        self.llm_classifier     = LLMClassifier()
        self.ml_classifier      = MLClassifier()
        self.rules_engine       = RulesEngine(self.config.get("custom_rules", []))
        self.ocr_extractor      = OCRExtractor(self.config.get("tesseract_path", "/usr/local/bin/tesseract"))
        self.pdf_processor      = PDFProcessor()
        self.docx_processor     = DocxProcessor()
        self.text_processor     = TextProcessor()
        self.sensitive_detector = SensitiveDetector()
        self.duplicate_detector = DuplicateDetector()
        self.policy_engine      = PolicyEngine()
        self.file_organizer     = FileOrganizer(os.path.expanduser(self.config["output_folder"]))
        self.logger             = Logger(self.config.get("log_file", "omnisort.log"))

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
        # Process files that already exist before the watcher started.
        threading.Thread(target=self._scan_existing, daemon=True).start()

    def stop(self):
        self.observer.stop()
        self.observer.join()
        # wait=False lets already-running tasks finish without blocking shutdown.
        self._executor.shutdown(wait=False)
        self.logger.log("Stopped watching")

    def _get_hash_lock(self, file_hash: str) -> threading.Lock:
        # Create the lock on first access; use _hash_locks_lock to guard the dict itself.
        with self._hash_locks_lock:
            if file_hash not in self._hash_locks:
                self._hash_locks[file_hash] = threading.Lock()
            return self._hash_locks[file_hash]

    def _scan_existing(self):
        # 1-second delay lets the watchdog observer settle before we walk the folder,
        # avoiding a race where on_created fires for the same file we're already processing.
        time.sleep(1)
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
                # Skip files that are already inside the output tree.
                if os.path.abspath(file_path).startswith(output_folder):
                    continue
                self.logger.log(f"Startup scan: {name}")
                self._process_file(file_path)

    def on_moved(self, event):
        # AirDrop writes a .part temp then renames to the final extension — this callback
        # catches that rename. on_created would miss AirDropped files entirely.
        if event.is_directory or _should_skip(event.dest_path):
            return
        output_folder = os.path.abspath(self.file_organizer.output_folder)
        if os.path.abspath(event.dest_path).startswith(output_folder):
            return
        self._executor.submit(self._process_file, event.dest_path)

    def on_created(self, event):
        # Handles normal file drops; AirDrop is handled by on_moved instead.
        if event.is_directory or _should_skip(event.src_path):
            return
        output_folder = os.path.abspath(self.file_organizer.output_folder)
        # Ignore events triggered by our own shutil.move calls into the output folder.
        if os.path.abspath(event.src_path).startswith(output_folder):
            return
        self._executor.submit(self._process_file, event.src_path)

    def _wait_for_file_ready(self, file_path):
        # Poll until the file size stops changing across two consecutive reads.
        # This handles browsers and download managers that write files incrementally.
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
        # Return the type key for a lowercased extension, or "other" if unrecognised.
        for ftype, exts in SUPPORTED_EXTENSIONS.items():
            if ext in exts:
                return ftype
        return "other"

    def _process_file(self, file_path):
        """Run the full 15-step classification and routing pipeline for one file."""
        real_path = os.path.abspath(file_path)

        # Guard against multiple watchdog events for the same file (e.g. on_created
        # fired during a slow copy that also triggers on_modified).
        with self._lock:
            if real_path in self._processing:
                return
            self._processing.add(real_path)

        try:
            # Step 1 — wait until the file is fully written before reading it.
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
                # Step 2 — check the filename itself for PII before opening the file.
                # A file named "john_SSN_123456789.pdf" goes to Sensitive/ without being read.
                filename_pii = self.sensitive_detector.detect_sensitive_info(
                    os.path.basename(real_path)
                )

                # Step 3 — extract text using the appropriate processor for the file type.
                if file_type == "image":
                    metadata["category"] = self.image_classifier.predict(real_path)
                    try:
                        metadata["text"] = self.ocr_extractor.extract_text(real_path)
                    except Exception:
                        metrics.record_ocr_failure()

                elif file_type == "pdf":
                    text, pdf_meta = self.pdf_processor.process(real_path)
                    # Step 4 — scanned PDFs have no text layer; fall back to OCR via PyMuPDF.
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

                # Step 5 — check extracted text for PII and merge with filename PII.
                # Both sources gate the same way: any match routes to Sensitive/ immediately.
                text = metadata.get("text", "")
                content_pii = self.sensitive_detector.detect_sensitive_info(text)
                sensitive_info = {**filename_pii, **content_pii}
                metadata["sensitive_info"] = sensitive_info

                # Steps 6–9 run only for text-bearing file types.
                if file_type in ("pdf", "docx", "text"):
                    _clf_start = time.perf_counter()

                    # Step 6 — custom rules: user-defined keyword → folder mappings.
                    # Skipped entirely when PII was found (sensitive files never hit rules or LLM).
                    rule_folder = (
                        self.rules_engine.match(text, os.path.basename(real_path))
                        if not sensitive_info else None
                    )

                    if rule_folder:
                        category = rule_folder
                    else:
                        # Step 7 — keyword NLP: fast, on-device, zero cost.
                        category = classify_document(text)

                        if category == "Documents" and not sensitive_info:
                            # Step 8 — DistilBERT zero-shot: catches Medical/Financial/Academic
                            # that keywords miss. Runs locally, no API call. Returns None when
                            # unavailable (Python 3.13 / no torch) so step 9 takes over.
                            ml_result = self.ml_classifier.classify(text)
                            if ml_result:
                                category = ml_result

                        if category == "Documents" and not sensitive_info:
                            # Step 9 — LLM fallback: only reached when all local stages
                            # returned "Documents". Sends first 2,000 chars to GPT-4o-mini.
                            _llm_start = time.perf_counter()
                            category = self.llm_classifier.classify(text)
                            metrics.record_llm_call((time.perf_counter() - _llm_start) * 1000)

                    metrics.record_classification((time.perf_counter() - _clf_start) * 1000)
                    metadata["category"] = category

                # Step 10 — SHA-256 hash for duplicate detection.
                file_hash = self.duplicate_detector.calculate_file_hash(real_path)

                # Steps 11–14 run under a per-hash lock so two threads processing identical
                # files can't both pass is_duplicate()=False before either writes to the DB.
                with self._get_hash_lock(file_hash):
                    metadata["duplicate"] = self.duplicate_detector.is_duplicate(file_hash)
                    metadata["file_hash"] = file_hash

                    # Step 11 — policy engine sets is_sensitive and is_duplicate flags.
                    self.policy_engine.apply_policies(real_path, metadata)

                    # Step 12 — move the file to its destination folder.
                    # The DB write happens after the move so a failed move never leaves a
                    # phantom DB record pointing to a file that was never actually sorted.
                    dest_path = self.file_organizer.organize_file(real_path, metadata)

                    is_duplicate = bool(metadata.get("is_duplicate"))
                    metrics.record_file_processed(is_duplicate=is_duplicate)

                    # Step 13 — generate a 384-dim embedding for semantic search.
                    # Returns [] gracefully when fastembed is unavailable; stored as NULL.
                    embedding = embed_text(metadata.get("text", ""))

                    record = {
                        "filename":       os.path.basename(file_path),
                        "original_path":  file_path,
                        "destination_path": dest_path,
                        "extension":      ext,
                        "category":       metadata.get("category", "Other"),
                        "file_size":      os.path.getsize(dest_path) if os.path.exists(dest_path) else 0,
                        "file_hash":      file_hash,
                        "is_duplicate":   1 if is_duplicate else 0,
                        "is_sensitive":   1 if metadata.get("is_sensitive") else 0,
                        "sensitive_types": metadata.get("sensitive_types", "[]"),
                        "embedding":      json.dumps(embedding) if embedding else None,
                    }

                    # Step 14 — write to SQLite. Isolated so a DB failure doesn't cause
                    # file loss; the file is already in its sorted destination at this point.
                    try:
                        db.insert_file(record)
                    except Exception as db_err:
                        self.logger.error(f"DB write failed for {record['filename']}: {db_err}")

                # Step 15 — broadcast a real-time event to connected WebSocket clients.
                event_queue.put({
                    "type":         "file_processed",
                    "filename":     record["filename"],
                    "category":     record["category"],
                    "is_duplicate": record["is_duplicate"],
                    "is_sensitive": record["is_sensitive"],
                })

                self.logger.log(f"Sorted: {record['filename']} → {record['category']}")

            except Exception as e:
                self.logger.error(f"Error processing {real_path}: {e}")
                event_queue.put({"type": "error", "filename": os.path.basename(file_path), "error": str(e)})

        finally:
            # Always release the in-progress lock, even if an exception occurred.
            with self._lock:
                self._processing.discard(real_path)
