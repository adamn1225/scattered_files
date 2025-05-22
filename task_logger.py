import sqlite3
from datetime import datetime
import os

DB_FILE = os.path.expanduser("~/.workspace_agent.db")

# Initialize DB
conn = sqlite3.connect(DB_FILE)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS task_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    task TEXT,
    tags TEXT,
    success INTEGER
)''')
conn.commit()

def log_task(task: str, tags: list[str] = None, success: bool = True):
    ts = datetime.now().isoformat()
    tag_str = ",".join(tags or [])
    c.execute("INSERT INTO task_log (timestamp, task, tags, success) VALUES (?, ?, ?, ?)",
              (ts, task, tag_str, int(success)))
    conn.commit()

if __name__ == "__main__":
    import sys
    task = " ".join(sys.argv[1:])
    log_task(task, tags=["manual"])
    print(f"✅ Logged: {task}")
