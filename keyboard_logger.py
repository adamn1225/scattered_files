from pynput import keyboard
from datetime import datetime
import os
import sqlite3
import threading

DB_PATH = os.path.expanduser("~/.workspace_agent_typing.db")
TABLE_INIT = """
CREATE TABLE IF NOT EXISTS keystrokes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    key TEXT,
    window TEXT DEFAULT "",
    is_modifier INTEGER DEFAULT 0
);
"""

# Initialize DB
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute(TABLE_INIT)
conn.commit()
conn.close()

MODIFIER_KEYS = {
    keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
    keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
    keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
    keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
    keyboard.Key.esc, keyboard.Key.tab, keyboard.Key.caps_lock
}

logger_enabled = False
listener = None
listener_thread = None

def log_key(key):
    if not logger_enabled:
        return
    try:
        is_modifier = int(key in MODIFIER_KEYS)
        key_str = key.char if hasattr(key, 'char') else str(key)
        timestamp = datetime.now().isoformat()

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO keystrokes (timestamp, key, is_modifier) VALUES (?, ?, ?)",
                  (timestamp, key_str, is_modifier))
        conn.commit()
        conn.close()

    except Exception as e:
        print(f"[Error logging key]: {e}")

def start_logger():
    global listener, logger_enabled, listener_thread
    if not listener:
        logger_enabled = True
        listener = keyboard.Listener(on_press=log_key)
        listener_thread = threading.Thread(target=listener.start)
        listener_thread.start()
        print("🔴 Keyboard logger started.")

def stop_logger():
    global listener, logger_enabled
    logger_enabled = False
    if listener:
        listener.stop()
        listener = None
        print("🟢 Keyboard logger stopped.")

def is_logger_running():
    return logger_enabled

if __name__ == "__main__":
    print("🎹 Keyboard logger toggleable. Use start_logger() / stop_logger() to control it.")
    start_logger()
    try:
        while True:
            pass  # Keep the main thread alive
    except KeyboardInterrupt:
        stop_logger()
