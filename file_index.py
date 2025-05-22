import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.expanduser("~/.workspace_file_index.db")
WATCH_DIRS = [os.path.expanduser("~/Downloads"), os.path.expanduser("~/Documents")]

def init_file_index_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS file_index (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT,
        filename TEXT,
        extension TEXT,
        modified TEXT,
        size INTEGER
    )
    """)
    c.execute("DELETE FROM file_index")  # fresh each scan
    for dir in WATCH_DIRS:
        for root, _, files in os.walk(dir):
            for f in files:
                try:
                    full = os.path.join(root, f)
                    stat = os.stat(full)
                    c.execute("INSERT INTO file_index (path, filename, extension, modified, size) VALUES (?, ?, ?, ?, ?)",
                        (full, f, os.path.splitext(f)[1], datetime.fromtimestamp(stat.st_mtime).isoformat(), stat.st_size))
                except Exception:
                    continue
    conn.commit()
    conn.close()
