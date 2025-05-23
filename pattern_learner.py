import sqlite3
from collections import defaultdict
from datetime import datetime
import os

DB_FILE = os.path.expanduser("~/.workspace_agent.db")

conn = sqlite3.connect(DB_FILE)
c = conn.cursor()

def group_by_day(entries):
    patterns = defaultdict(list)
    for ts, task in entries:
        day = datetime.fromisoformat(ts).strftime("%A")
        patterns[day].append(task)
    return patterns

def analyze_patterns():
    c.execute("""
        SELECT task_log.timestamp, task_log.task, command_memory.feedback
        FROM task_log
        LEFT JOIN command_memory ON task_log.task = command_memory.command
        WHERE success=1
    """)
    entries = [(ts, task) for ts, task, fb in c.fetchall() if not fb or "no" not in fb.lower()]
    return group_by_day(entries)

if __name__ == "__main__":
    patterns = analyze_patterns()
    for day, tasks in patterns.items():
        print(f"\n📅 {day}:")
        for task in set(tasks):
            print(f"  • {task} ({tasks.count(task)}x)")
