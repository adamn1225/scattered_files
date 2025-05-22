# screenshot_capture.py
import mss
import base64
from datetime import datetime
from io import BytesIO
from PIL import Image
import os
import sqlite3

DB_PATH = os.path.expanduser("~/.workspace_agent_screens.db")
TABLE_SQL = """
CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    monitor INTEGER,
    image_base64 TEXT
)
"""

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(TABLE_SQL)
    conn.commit()
    conn.close()

def capture_and_store_all_screens():
    with mss.mss() as sct:
        conn = sqlite3.connect(DB_PATH)
        now = datetime.now().isoformat()

        for i, monitor in enumerate(sct.monitors[1:], start=1):  # skip [0], it’s the full virtual screen
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            img_b64 = base64.b64encode(buffer.getvalue()).decode()

            conn.execute(
                "INSERT INTO screenshots (timestamp, monitor, image_base64) VALUES (?, ?, ?)",
                (now, i, img_b64)
            )

        conn.commit()
        conn.close()

if __name__ == "__main__":
    init_db()
    capture_and_store_all_screens()
