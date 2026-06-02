import hashlib
from backend.database import db

class DuplicateDetector:
    def calculate_file_hash(self, file_path):
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def is_duplicate(self, file_hash):
        conn = db.get_connection()
        row = conn.execute(
            "SELECT id FROM files WHERE file_hash = ?", (file_hash,)
        ).fetchone()
        conn.close()
        return row is not None
