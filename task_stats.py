import sqlite3
from collections import Counter
import os

DB_FILE = os.path.expanduser("~/.workspace_agent.db")

conn = sqlite3.connect(DB_FILE)
c = conn.cursor()

# Task frequency
c.execute("SELECT task FROM task_log")
tasks = [row[0] for row in c.fetchall()]
task_counts = Counter(tasks)

print("\n📊 Task Frequency:")
for task, count in task_counts.most_common():
    print(f"  • {task}: {count}x")

# Tag frequency
c.execute("SELECT tags FROM task_log")
tags = []
for row in c.fetchall():
    tags.extend([t.strip() for t in row[0].split(",") if t.strip()])
tag_counts = Counter(tags)

print("\n🏷️ Tag Frequency:")
for tag, count in tag_counts.most_common():
    print(f"  • #{tag}: {count}x")

# Success/failure breakdown
c.execute("SELECT success FROM task_log")
results = ["✅" if row[0] else "❌" for row in c.fetchall()]
result_counts = Counter(results)

print("\n📈 Success Stats:")
for result, count in result_counts.items():
    print(f"  • {result}: {count}x")