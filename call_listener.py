# call_listener.py (new module)
import os
import speech_recognition as sr
from datetime import datetime
from memory import save_call_summary  # You’ll add this
from agent_core import summarize_text, schedule_reminder, extract_followup_task  # Existing or to be implemented

CALL_LOG_PATH = os.path.expanduser("~/.workspace_agent_calls.log")

class CallSessionLogger:
    def __init__(self):
        self.is_recording = False
        self.session_text = []

    def toggle_recording(self, state: bool):
        if state:
            self.is_recording = True
            self.session_text = []
        else:
            self.is_recording = False
            self._finalize_session()

    def record_snippet(self, text):
        if self.is_recording and text:
            self.session_text.append(text)

    def _finalize_session(self):
        if not self.session_text:
            return
        full_text = " ".join(self.session_text)
        timestamp = datetime.now().isoformat()
        summary = summarize_text(full_text)  # You implement this
        reminder = extract_followup_task(summary)  # Also implement
        
        # Save
        save_call_summary(timestamp, full_text, summary, reminder)

        # Optional: Auto-schedule
        if reminder:
            schedule_reminder(reminder, minutes_from_now=30)

        with open(CALL_LOG_PATH, "a") as f:
            f.write(f"[{timestamp}] {summary}\n")


