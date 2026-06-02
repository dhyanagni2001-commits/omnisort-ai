"""Integration tests for the full file watcher pipeline."""
import os
import sys
import time
import shutil
import sqlite3
import threading
import tempfile
import pytest
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.watcher.file_watcher import FileWatcher, _should_skip
from backend.database import db

# ─── Helpers ────────────────────────────────────────────────────────────────

def write_text_file(path, content=""):
    with open(path, "w") as f:
        f.write(content)

def write_image(path, size=(800, 600)):
    Image.new("RGB", size, (120, 180, 90)).save(path)

def write_pdf(path, content=""):
    # Minimal valid PDF with embedded text
    lines = content.strip().split("\n") if content else [""]
    text_stream = "\n".join(f"BT /F1 12 Tf 50 {700 - i*20} Td ({line}) Tj ET"
                            for i, line in enumerate(lines))
    stream = f"""\
%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>>endobj
4 0 obj<</Length {len(text_stream)}>>
stream
{text_stream}
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000274 00000 n
trailer<</Size 5/Root 1 0 R>>
startxref
{400 + len(text_stream)}
%%EOF"""
    with open(path, "w") as f:
        f.write(stream)

@pytest.fixture
def env(tmp_path, monkeypatch):
    """
    Provide isolated watch_folder + output_folder + DB for each test.
    Patches the config so FileWatcher uses temp dirs instead of ~/Downloads.
    """
    watch_dir = tmp_path / "watch"
    out_dir = tmp_path / "omni"
    db_path = tmp_path / "test.db"
    watch_dir.mkdir()
    out_dir.mkdir()

    # Patch db path
    monkeypatch.setattr(db, "DB_PATH", str(db_path))
    db.init_db()

    # Prevent model download during tests — embeddings degrade gracefully to []
    import backend.embeddings.embedding as _emb
    monkeypatch.setattr(_emb, "embed_text", lambda text: [])

    # Build watcher pointed at our temp dirs
    watcher = FileWatcher.__new__(FileWatcher)
    watcher.config = {
        "watch_folders": [str(watch_dir)],
        "output_folder": str(out_dir),
        "file_ready_timeout": 10,
        "tesseract_path": None,
        "log_file": "test_omnisort.log",
    }
    watcher.watch_folders = [str(watch_dir)]
    watcher.folder_path = str(watch_dir)
    watcher.timeout = 10
    watcher._processing = set()
    watcher._lock = threading.Lock()
    watcher._hash_locks = {}
    watcher._hash_locks_lock = threading.Lock()
    from concurrent.futures import ThreadPoolExecutor
    watcher._executor = ThreadPoolExecutor(max_workers=2)

    from backend.classifier.image_classifier import ImageClassifier
    from backend.ocr.ocr_extractor import OCRExtractor
    from backend.processor.pdf_process import PDFProcessor
    from backend.processor.doc_process import DocxProcessor
    from backend.processor.text_process import TextProcessor
    from backend.sensitive_detection.sensitive import SensitiveDetector
    from backend.duplicate_detection.duplicate_detector import DuplicateDetector
    from backend.policy_engine.policy_engine import PolicyEngine
    from backend.organizer.file_organizer import FileOrganizer
    from backend.logger.logger import Logger

    from backend.rules.rules_engine import RulesEngine

    class _StubLLMClassifier:
        def classify(self, text):
            return "Documents"

    watcher.image_classifier = ImageClassifier()
    watcher.rules_engine = RulesEngine([])
    watcher.llm_classifier = _StubLLMClassifier()
    watcher.ocr_extractor = OCRExtractor()
    watcher.pdf_processor = PDFProcessor()
    watcher.docx_processor = DocxProcessor()
    watcher.text_processor = TextProcessor()
    watcher.sensitive_detector = SensitiveDetector()
    watcher.duplicate_detector = DuplicateDetector()
    watcher.policy_engine = PolicyEngine()
    watcher.file_organizer = FileOrganizer(str(out_dir))
    watcher.logger = Logger("test_omnisort.log")

    return watcher, watch_dir, out_dir, db_path

def sorted_files(out_dir):
    """Return {category: [filename, ...]} of everything under out_dir."""
    result = {}
    for cat in os.listdir(str(out_dir)):
        cat_path = os.path.join(str(out_dir), cat)
        if os.path.isdir(cat_path):
            result[cat] = sorted(os.listdir(cat_path))
    return result

def db_records(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = [dict(r) for r in conn.execute("SELECT * FROM files").fetchall()]
    conn.close()
    return rows

# ─── _should_skip ────────────────────────────────────────────────────────────

class TestShouldSkip:
    def test_crdownload_skipped(self):
        assert _should_skip("/tmp/Unconfirmed 123.crdownload") is True

    def test_part_skipped(self):
        assert _should_skip("/tmp/photo.jpg.part") is True

    def test_tmp_skipped(self):
        assert _should_skip("/tmp/something.tmp") is True

    def test_brave_browser_skipped(self):
        assert _should_skip("/tmp/.com.brave.Browser.abc123") is True

    def test_dotfile_skipped(self):
        assert _should_skip("/tmp/.DS_Store") is True

    def test_pdf_not_skipped(self):
        assert _should_skip("/tmp/report.pdf") is False

    def test_jpg_not_skipped(self):
        assert _should_skip("/tmp/photo.jpg") is False

    def test_docx_not_skipped(self):
        assert _should_skip("/tmp/resume.docx") is False


# ─── Pipeline integration ────────────────────────────────────────────────────

class TestPipeline:
    def test_image_goes_to_photos(self, env):
        watcher, watch_dir, out_dir, db_path = env
        img = str(watch_dir / "photo.jpg")
        write_image(img)
        watcher._process_file(img)
        cats = sorted_files(out_dir)
        assert "photo.jpg" in cats.get("Photos", [])

    def test_screenshot_by_filename(self, env):
        watcher, watch_dir, out_dir, db_path = env
        img = str(watch_dir / "Screenshot 2025-01-01.png")
        write_image(img)
        watcher._process_file(img)
        cats = sorted_files(out_dir)
        assert "Screenshot 2025-01-01.png" in cats.get("Screenshots", [])

    def test_screenshot_by_resolution(self, env):
        watcher, watch_dir, out_dir, db_path = env
        img = str(watch_dir / "capture.png")
        write_image(img, size=(1920, 1080))
        watcher._process_file(img)
        cats = sorted_files(out_dir)
        assert "capture.png" in cats.get("Screenshots", [])

    def test_pdf_goes_to_documents(self, env):
        watcher, watch_dir, out_dir, db_path = env
        pdf = str(watch_dir / "report.pdf")
        write_pdf(pdf, "This is a quarterly business report.")
        watcher._process_file(pdf)
        cats = sorted_files(out_dir)
        assert "report.pdf" in cats.get("Documents", [])

    def test_invoice_pdf(self, env):
        watcher, watch_dir, out_dir, db_path = env
        pdf = str(watch_dir / "inv.pdf")
        write_pdf(pdf, "Invoice #100\nTotal amount due: $250\nDue date: 2025-02-01")
        watcher._process_file(pdf)
        cats = sorted_files(out_dir)
        assert "inv.pdf" in cats.get("Invoices", [])

    def test_resume_pdf(self, env):
        watcher, watch_dir, out_dir, db_path = env
        pdf = str(watch_dir / "cv.pdf")
        write_pdf(pdf, "Resume\nWork Experience\nEducation\nSkills\nReferences available")
        watcher._process_file(pdf)
        cats = sorted_files(out_dir)
        assert "cv.pdf" in cats.get("Resumes", [])

    def test_txt_goes_to_documents(self, env):
        watcher, watch_dir, out_dir, db_path = env
        f = str(watch_dir / "notes.txt")
        write_text_file(f, "Meeting notes from Monday.")
        watcher._process_file(f)
        cats = sorted_files(out_dir)
        assert "notes.txt" in cats.get("Documents", [])

    def test_unsupported_extension_goes_to_other(self, env):
        watcher, watch_dir, out_dir, db_path = env
        f = str(watch_dir / "data.xyz")
        write_text_file(f, "some content")
        watcher._process_file(f)
        cats = sorted_files(out_dir)
        assert "data.xyz" in cats.get("Other", [])

    def test_filename_with_spaces(self, env):
        watcher, watch_dir, out_dir, db_path = env
        f = str(watch_dir / "My Report 2025.pdf")
        write_pdf(f, "Annual business report")
        watcher._process_file(f)
        cats = sorted_files(out_dir)
        assert "My Report 2025.pdf" in cats.get("Documents", [])

    def test_sensitive_file_with_email(self, env):
        watcher, watch_dir, out_dir, db_path = env
        f = str(watch_dir / "contact.txt")
        write_text_file(f, "Contact: john.doe@example.com\nPhone: 555-867-5309")
        watcher._process_file(f)
        cats = sorted_files(out_dir)
        assert "contact.txt" in cats.get("Sensitive", [])

    def test_sensitive_file_with_ssn(self, env):
        watcher, watch_dir, out_dir, db_path = env
        f = str(watch_dir / "record.txt")
        write_text_file(f, "SSN: 123-45-6789")
        watcher._process_file(f)
        cats = sorted_files(out_dir)
        assert "record.txt" in cats.get("Sensitive", [])

    def test_duplicate_file(self, env):
        watcher, watch_dir, out_dir, db_path = env
        # First copy
        f1 = str(watch_dir / "doc.pdf")
        write_pdf(f1, "Duplicate test document content")
        watcher._process_file(f1)
        # Second copy with different name but same content
        f2 = str(watch_dir / "doc_copy.pdf")
        write_pdf(f2, "Duplicate test document content")
        watcher._process_file(f2)
        cats = sorted_files(out_dir)
        assert "doc_copy.pdf" in cats.get("Duplicates", [])

    def test_first_file_not_marked_duplicate(self, env):
        watcher, watch_dir, out_dir, db_path = env
        f = str(watch_dir / "original.pdf")
        write_pdf(f, "Unique content abc123")
        watcher._process_file(f)
        records = db_records(db_path)
        assert records[0]["is_duplicate"] == 0

    def test_empty_file_handled_gracefully(self, env):
        watcher, watch_dir, out_dir, db_path = env
        f = str(watch_dir / "empty.txt")
        write_text_file(f, "")
        # Should not crash — empty files can't be processed by _wait_for_file_ready (size=0)
        # so they are skipped silently
        watcher._process_file(f)  # no exception

    def test_db_record_created(self, env):
        watcher, watch_dir, out_dir, db_path = env
        f = str(watch_dir / "test.txt")
        write_text_file(f, "hello world content")
        watcher._process_file(f)
        records = db_records(db_path)
        assert len(records) == 1
        assert records[0]["filename"] == "test.txt"
        assert records[0]["category"] == "Documents"

    def test_db_stores_hash(self, env):
        watcher, watch_dir, out_dir, db_path = env
        f = str(watch_dir / "hashme.txt")
        write_text_file(f, "content to hash")
        watcher._process_file(f)
        records = db_records(db_path)
        assert records[0]["file_hash"] is not None
        assert len(records[0]["file_hash"]) == 64  # sha256 hex

    def test_concurrent_same_file_not_double_processed(self, env):
        watcher, watch_dir, out_dir, db_path = env
        f = str(watch_dir / "concurrent.txt")
        write_text_file(f, "concurrent test content")
        threads = [threading.Thread(target=watcher._process_file, args=(f,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # Should be in exactly one folder, with exactly one DB record
        records = db_records(db_path)
        assert len(records) == 1

    def test_file_not_in_output_folder_reprocessed(self, env):
        """Files already in the output folder must not trigger reprocessing."""
        watcher, watch_dir, out_dir, db_path = env
        output_folder = os.path.abspath(str(out_dir))
        internal_file = os.path.join(output_folder, "Documents", "already_sorted.pdf")
        # Simulate on_created firing for a file inside the output folder
        from watchdog.events import FileCreatedEvent
        event = FileCreatedEvent(internal_file)
        watcher.on_created(event)
        records = db_records(db_path)
        assert len(records) == 0  # nothing processed

    def test_custom_rule_routes_to_custom_folder(self, env):
        from backend.rules.rules_engine import RulesEngine
        watcher, watch_dir, out_dir, db_path = env
        watcher.rules_engine = RulesEngine([
            {"folder": "Bank", "keywords": ["account number", "transaction history"]}
        ])
        f = str(watch_dir / "statement.pdf")
        write_pdf(f, "Account number: ACC-XYZ\nTransaction history for March 2025")
        watcher._process_file(f)
        cats = sorted_files(out_dir)
        assert "statement.pdf" in cats.get("Bank", [])

    def test_pii_overrides_custom_rule(self, env):
        from backend.rules.rules_engine import RulesEngine
        watcher, watch_dir, out_dir, db_path = env
        watcher.rules_engine = RulesEngine([
            {"folder": "Bank", "keywords": ["account number"]}
        ])
        f = str(watch_dir / "statement.pdf")
        write_pdf(f, "Account number: 987654321\nSSN: 123-45-6789")
        watcher._process_file(f)
        cats = sorted_files(out_dir)
        # PII (SSN) must win over the custom rule
        assert "statement.pdf" in cats.get("Sensitive", [])
