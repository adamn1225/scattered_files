from pattern_learner import analyze_patterns
from datetime import datetime

patterns = analyze_patterns()
today = datetime.today().strftime("%A")

today_tasks = patterns.get(today, [])
if not today_tasks:
    print(f"✅ No routine tasks found for {today}.")
    exit()

print(f"🤖 Based on past logs, you usually do:")
seen = set()
for task in today_tasks:
    if task in seen:
        continue
    seen.add(task)
    print(f"  • {task}")

print("\n🧠 Want me to remind you about one of these or schedule it?")
