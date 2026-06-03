# SQLite data layer — all database interaction lives here.
# Each function opens its own connection and closes it immediately; no connection pool needed.

import sqlite3
import json
import os
from datetime import datetime

# Path resolved relative to this file so it works regardless of working directory.
DB_PATH = os.path.join(os.path.dirname(__file__), "../../database/omnisort.db")


def get_connection():
    """Open and return a SQLite connection with row_factory set to sqlite3.Row
    so fetchall() returns dict-like objects instead of plain tuples."""
    conn = sqlite3.connect(os.path.abspath(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Create the files table if it does not exist.
    Also runs a migration to add the embedding column to databases created before
    that column existed — the try/except makes it safe to call multiple times.
    """
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            filename         TEXT NOT NULL,
            original_path    TEXT NOT NULL,
            destination_path TEXT,
            extension        TEXT,
            category         TEXT,
            file_size        INTEGER,
            file_hash        TEXT,
            is_duplicate     INTEGER DEFAULT 0,
            is_sensitive     INTEGER DEFAULT 0,
            sensitive_types  TEXT,
            embedding        TEXT,
            processed_at     TEXT DEFAULT (datetime('now'))
        )
    """)
    # Migration: add embedding column to DBs that predate it.
    try:
        conn.execute("ALTER TABLE files ADD COLUMN embedding TEXT")
    except Exception:
        pass  # Column already exists — safe to ignore.
    conn.commit()
    conn.close()


def insert_file(record: dict):
    """Insert one processed file record. Uses named parameters to prevent SQL injection."""
    conn = get_connection()
    conn.execute("""
        INSERT INTO files (filename, original_path, destination_path, extension,
            category, file_size, file_hash, is_duplicate, is_sensitive,
            sensitive_types, embedding)
        VALUES (:filename, :original_path, :destination_path, :extension,
            :category, :file_size, :file_hash, :is_duplicate, :is_sensitive,
            :sensitive_types, :embedding)
    """, record)
    conn.commit()
    conn.close()


def get_files(limit=50, offset=0):
    """Return paginated file records ordered by most recently processed first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM files ORDER BY processed_at DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_files_with_embeddings():
    """Return all files that have a stored embedding vector.
    Used by the semantic search endpoint to get candidates for cosine similarity ranking."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM files WHERE embedding IS NOT NULL ORDER BY processed_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats():
    """Return aggregate counts used by the dashboard stats cards."""
    conn = get_connection()
    total      = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    duplicates = conn.execute("SELECT COUNT(*) FROM files WHERE is_duplicate=1").fetchone()[0]
    sensitive  = conn.execute("SELECT COUNT(*) FROM files WHERE is_sensitive=1").fetchone()[0]
    by_category = conn.execute(
        "SELECT category, COUNT(*) as count FROM files GROUP BY category"
    ).fetchall()
    conn.close()
    return {
        "total":       total,
        "duplicates":  duplicates,
        "sensitive":   sensitive,
        "by_category": {row["category"]: row["count"] for row in by_category},
    }
