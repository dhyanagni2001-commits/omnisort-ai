import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "../../database/omnisort.db")

def get_connection():
    conn = sqlite3.connect(os.path.abspath(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            original_path TEXT NOT NULL,
            destination_path TEXT,
            extension TEXT,
            category TEXT,
            file_size INTEGER,
            file_hash TEXT,
            is_duplicate INTEGER DEFAULT 0,
            is_sensitive INTEGER DEFAULT 0,
            sensitive_types TEXT,
            processed_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

def insert_file(record: dict):
    conn = get_connection()
    conn.execute("""
        INSERT INTO files (filename, original_path, destination_path, extension,
            category, file_size, file_hash, is_duplicate, is_sensitive, sensitive_types)
        VALUES (:filename, :original_path, :destination_path, :extension,
            :category, :file_size, :file_hash, :is_duplicate, :is_sensitive, :sensitive_types)
    """, record)
    conn.commit()
    conn.close()

def get_files(limit=50, offset=0):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM files ORDER BY processed_at DESC LIMIT ? OFFSET ?",
        (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats():
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    duplicates = conn.execute("SELECT COUNT(*) FROM files WHERE is_duplicate=1").fetchone()[0]
    sensitive = conn.execute("SELECT COUNT(*) FROM files WHERE is_sensitive=1").fetchone()[0]
    by_category = conn.execute(
        "SELECT category, COUNT(*) as count FROM files GROUP BY category"
    ).fetchall()
    conn.close()
    return {
        "total": total,
        "duplicates": duplicates,
        "sensitive": sensitive,
        "by_category": {row["category"]: row["count"] for row in by_category}
    }
