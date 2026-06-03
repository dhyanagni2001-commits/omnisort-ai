# Content-based duplicate detection using SHA-256.
# Works across filenames — doc.pdf and doc_copy.pdf with identical bytes are the same file.
# Both methods must be called inside the per-hash threading.Lock in file_watcher to
# prevent a TOCTOU race where two identical files both pass is_duplicate()=False.

import hashlib
from backend.database import db


class DuplicateDetector:
    """Hashes file content and checks the database for prior occurrences."""

    def calculate_file_hash(self, file_path):
        # Stream in 4 KB chunks to avoid loading large files entirely into memory.
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def is_duplicate(self, file_hash):
        # A True result means this exact content was already sorted and recorded.
        conn = db.get_connection()
        row = conn.execute(
            "SELECT id FROM files WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        conn.close()
        return row is not None
