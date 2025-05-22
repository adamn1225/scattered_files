import sys
import asyncio
import sqlite3
import os
from datetime import datetime, timedelta
from collections import Counter
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QMessageBox, QFileDialog, QDialog, QTableWidget, QTableWidgetItem
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPalette, QColor, QPixmap
from agents import Agent, Runner
from tools.local_computer_tool import LocalComputerTool
from templates import match_template
from hot_commands import HOT_COMMANDS
import subprocess
from keyboard_logger import start_logger, stop_logger, is_logger_running
from screenshot_capture import capture_and_store_all_screens, init_db as screenshot_init_db
from memory import init_memory_db, save_command, retrieve_similar
from pattern_learner import analyze_patterns
from task_logger import log_task
import threading
import speech_recognition as sr
from agent_core import agent, check_hot_command, match_template, recognize_speech, transcribe_audio
from templates import COMMAND_TEMPLATES

DB_FILE = os.path.expanduser("~/.workspace_agent.db")
KEYLOG_DB_FILE = os.path.expanduser("~/.workspace_agent_typing.db")


agent = Agent(
    name="Workspace Agent GUI",
    instructions=(
        "You are a local assistant that receives natural language instructions and converts them into direct shell commands. "
        "When using the LocalComputerTool, pass only the raw shell command as input. Do not wrap it in text."
    ),
    tools=[LocalComputerTool],
)



class KeystrokeLogViewer(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Keystroke Log Viewer")
        self.resize(600, 400)
        layout = QVBoxLayout()

        self.table = QTableWidget()
        layout.addWidget(self.table)

        self.setLayout(layout)
        self.load_logs()

    def load_logs(self):
        conn = sqlite3.connect(KEYLOG_DB_FILE)
        c = conn.cursor()
        c.execute("SELECT timestamp, key FROM keystrokes ORDER BY id DESC LIMIT 100")
        rows = c.fetchall()
        conn.close()

        self.table.setRowCount(len(rows))
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Timestamp", "Key"])

        for row_idx, (timestamp, key) in enumerate(rows):
            self.table.setItem(row_idx, 0, QTableWidgetItem(timestamp))
            self.table.setItem(row_idx, 1, QTableWidgetItem(key))

class ScreenshotViewer(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Screenshot Viewer")
        self.resize(800, 600)
        self.layout = QVBoxLayout()
        self.image_label = QLabel("No image loaded.")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.image_label)

        self.load_button = QPushButton("Load Next Screenshot")
        self.load_button.clicked.connect(self.load_next_image)
        self.layout.addWidget(self.load_button)


        self.setLayout(self.layout)

        self.screenshot_dir = os.path.expanduser("~/.workspace_screens")
        self.image_files = sorted([
            f for f in os.listdir(self.screenshot_dir)
            if f.endswith(".png")
        ], reverse=True)
        self.current_index = 0

        if self.image_files:
            self.load_next_image()

    def load_next_image(self):
        if not self.image_files:
            self.image_label.setText("No screenshots found.")
            return
        if self.current_index >= len(self.image_files):
            self.image_label.setText("End of screenshots.")
            return

        path = os.path.join(self.screenshot_dir, self.image_files[self.current_index])
        pixmap = QPixmap(path).scaled(760, 540, Qt.AspectRatioMode.KeepAspectRatio)
        self.image_label.setPixmap(pixmap)
        self.current_index += 1

class PhraseSummaryViewer(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Common Phrases Summary")
        self.resize(500, 300)
        layout = QVBoxLayout()

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        self.setLayout(layout)
        self.generate_summary()

    def generate_summary(self):
        conn = sqlite3.connect(KEYLOG_DB_FILE)
        c = conn.cursor()
        c.execute("SELECT key FROM keystrokes WHERE is_modifier = 0 ORDER BY id DESC LIMIT 500")
        keys = [row[0] for row in c.fetchall()]
        conn.close()

        text = "".join(k for k in keys if len(k) == 1 or k.startswith("'") or k.isalnum())
        words = text.split()
        phrases = [" ".join(words[i:i+3]) for i in range(len(words)-2)]
        common = Counter(phrases).most_common(10)

        self.output.append("Top common 3-word phrases:")
        for phrase, count in common:
            self.output.append(f"{phrase} — {count}x")

class AgentRunnerApp(QWidget):
    def __init__(self):
        super().__init__()
        self.logger_running = is_logger_running()
        self.init_ui()
        self.check_reminders()

    def init_ui(self):
        self.setWindowTitle("Scattered Files")
        self.setGeometry(300, 300, 600, 600)
        self.timer = QTimer(self)
        self.timer.timeout.connect(capture_and_store_all_screens)
        self.timer.start(10 * 60 * 1000)
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1e293b"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#121c2b"))
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, QColor("#334155"))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        self.setPalette(palette)
        self.setStyleSheet("QLabel { color: white; } QPushButton { background-color: #334155; color: white; border: none; padding: 6px; } QPushButton:hover { background-color: #3b82f6; }")

        layout = QVBoxLayout()

        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("What should the agent do?")
        self.command_input.textChanged.connect(self.suggest_similar_commands)
        layout.addWidget(QLabel("Enter Command:"))
        layout.addWidget(self.command_input)

        self.template_command_box = QComboBox()
        self.template_command_box.addItem("-- Choose template command --")
        for key in COMMAND_TEMPLATES:
            self.template_command_box.addItem(key)
        self.template_command_box.currentIndexChanged.connect(self.load_template_command)
        layout.addWidget(self.template_command_box)

        self.hot_command_box = QComboBox()
        self.hot_command_box.addItem("-- Choose hot command --")
        for key in HOT_COMMANDS:
            self.hot_command_box.addItem(key)
        self.hot_command_box.currentIndexChanged.connect(self.load_hot_command)
        layout.addWidget(self.hot_command_box)

        self.run_button = QPushButton("Run Agent")
        self.run_button.clicked.connect(self.run_agent)
        layout.addWidget(self.run_button)

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setStyleSheet("background-color: #121c2b; color: white;")
        layout.addWidget(QLabel("Agent Output:"))
        layout.addWidget(self.output_box)

        self.save_button = QPushButton("Save Output to File")
        self.save_button.clicked.connect(self.save_output)
        layout.addWidget(self.save_button)

        self.toggle_logger_button = QPushButton()
        self.toggle_logger_button.clicked.connect(self.toggle_logger)
        layout.addWidget(self.toggle_logger_button)
        self.update_logger_button()

        self.log_view_button = QPushButton("View Keystroke Log")
        self.log_view_button.clicked.connect(self.show_keystroke_log)
        layout.addWidget(self.log_view_button)

        self.summary_button = QPushButton("🧠 Summarize Phrases")
        self.summary_button.clicked.connect(self.show_phrase_summary)
        layout.addWidget(self.summary_button)

        self.view_screenshots_button = QPushButton("🖼️ View Screenshots")
        self.view_screenshots_button.clicked.connect(self.show_screenshots)
        layout.addWidget(self.view_screenshots_button)

        self.pattern_button = QPushButton("📊 Show Routine Patterns")
        self.pattern_button.clicked.connect(self.show_patterns)
        layout.addWidget(self.pattern_button)

        self.nudge_button = QPushButton("🤖 Nudge Me (Today's Routine)")
        self.nudge_button.clicked.connect(self.show_nudge)
        layout.addWidget(self.nudge_button)

        self.log_task_button = QPushButton("📝 Log Task Manually")
        self.log_task_button.clicked.connect(self.show_log_task)
        layout.addWidget(self.log_task_button)

        self.stats_button = QPushButton("📈 Show Task Stats")
        self.stats_button.clicked.connect(self.show_task_stats)
        layout.addWidget(self.stats_button)

        self.listen_button = QPushButton("🎤 Start Listening")
        self.listen_button.setCheckable(True)
        self.listen_button.clicked.connect(self.toggle_listen)
        layout.addWidget(self.listen_button)

        self.setLayout(layout)

    def show_patterns(self):
        patterns = analyze_patterns()
        dlg = QDialog(self)
        dlg.setWindowTitle("Routine Patterns")
        dlg.resize(600, 400)
        layout = QVBoxLayout()
        output = QTextEdit()
        output.setReadOnly(True)
        for day, tasks in patterns.items():
            output.append(f"\n📅 {day}:")
            for task in set(tasks):
                output.append(f"  • {task} ({tasks.count(task)}x)")
        layout.addWidget(output)
        dlg.setLayout(layout)
        dlg.exec()

    def toggle_logger(self):
        if is_logger_running():
            stop_logger()
        else:
            start_logger()
        self.update_logger_button()

    def update_logger_button(self):
        if is_logger_running():
            self.toggle_logger_button.setText("🛑 Stop Keyboard Logger")
        else:
            self.toggle_logger_button.setText("🎹 Start Keyboard Logger")

    def toggle_listen(self):
        if self.listen_button.isChecked():
            self.listen_button.setText("🛑 Stop Listening")
            self.listening = True
            self.listen_thread = threading.Thread(target=self.listen_to_mic, daemon=True)
            self.listen_thread.start()
        else:
            self.listen_button.setText("🎤 Start Listening")
            self.listening = False

    def listen_to_mic(self):
        import sounddevice as sd
        import scipy.io.wavfile

        fs = 16000  # Sample rate
        seconds = 5  # Duration of recording

        self.output_box.append("🎤 Recording...")
        recording = sd.rec(int(seconds * fs), samplerate=fs, channels=1)
        sd.wait()  # Wait until recording is finished
        scipy.io.wavfile.write("output.wav", fs, recording)

        # Now transcribe
        try:
            text = transcribe_audio("output.wav")
            self.output_box.append(f"🗣️ Whisper: {text}")
        except Exception as e:
            self.output_box.append(f"❌ Transcription error: {e}")

    def save_output(self):
        text = self.output_box.toPlainText()
        if not text.strip():
            QMessageBox.information(self, "No Output", "There is no output to save.")
            return
        filepath, _ = QFileDialog.getSaveFileName(self, "Save Output", os.path.expanduser("~/agent_output.txt"), "Text Files (*.txt)")
        if filepath:
            with open(filepath, "w") as f:
                f.write(text)
            QMessageBox.information(self, "Saved", f"Output saved to {filepath}")

    def show_notification(self, title, message):
        subprocess.Popen(['notify-send', title, message])

    def show_screenshots(self):
        dlg = ScreenshotViewer()
        dlg.exec()

    def show_keystroke_log(self):
        dlg = KeystrokeLogViewer()
        dlg.exec()

    def show_phrase_summary(self):
        dlg = PhraseSummaryViewer()
        dlg.exec()

    def load_hot_command(self, index):
        if index > 0:
            command = self.hot_command_box.itemText(index)
            self.command_input.setText(command)

    def load_template_command(self, index):
        if index > 0:
            command = self.template_command_box.itemText(index)
            self.command_input.setText(command)

    def run_agent(self):
        command = self.command_input.text().strip()
        if not command:
            QMessageBox.warning(self, "Warning", "You must enter a command.")
            return
        asyncio.run(self.execute_agent(command))

    def show_nudge(self):
        from pattern_learner import analyze_patterns
        from datetime import datetime

        patterns = analyze_patterns()
        today = datetime.today().strftime("%A")
        today_tasks = patterns.get(today, [])
        dlg = QDialog(self)
        dlg.setWindowTitle("Today's Routine Nudge")
        dlg.resize(400, 200)
        layout = QVBoxLayout()
        output = QTextEdit()
        output.setReadOnly(True)
        if not today_tasks:
            output.append(f"✅ No routine tasks found for {today}.")
        else:
            output.append(f"🤖 Based on past logs, you usually do:")
        seen = set()
        for task in today_tasks:
            if task in seen:
                continue
            seen.add(task)
            output.append(f"  • {task}")
        output.append("\n🧠 Want me to remind you about one of these or schedule it?")
        layout.addWidget(output)
        dlg.setLayout(layout)
        dlg.exec()

    def show_log_task(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Log a Task")
        dlg.resize(400, 200)
        layout = QVBoxLayout()
        task_input = QLineEdit()
        task_input.setPlaceholderText("Task description")
        tags_input = QLineEdit()
        tags_input.setPlaceholderText("Comma-separated tags (optional)")
        success_box = QComboBox()
        success_box.addItems(["Success", "Failure"])
        log_btn = QPushButton("Log Task")
        output = QLabel()
        layout.addWidget(QLabel("Task:"))
        layout.addWidget(task_input)
        layout.addWidget(QLabel("Tags:"))
        layout.addWidget(tags_input)
        layout.addWidget(QLabel("Result:"))
        layout.addWidget(success_box)
        layout.addWidget(log_btn)
        layout.addWidget(output)
        dlg.setLayout(layout)

        def do_log():
            task = task_input.text().strip()
            tags = [t.strip() for t in tags_input.text().split(",") if t.strip()]
            success = success_box.currentText() == "Success"
            if not task:
                output.setText("❌ Please enter a task.")
                return
            log_task(task, tags=tags, success=success)
            output.setText("✅ Task logged!")

        log_btn.clicked.connect(do_log)
        dlg.exec()

    async def execute_agent(self, command):
            self.output_box.clear()

            result = await Runner.run(agent, command)
            self.output_box.append(f"=== Output ===\n{result.final_output}")

            save_command(command) 

            script, project_name = check_hot_command(command)
            if script:
                self.output_box.append(f"🚀 Running hot command: {script} with project '{project_name}'")
                subprocess.run(["python", script, project_name])
                return

            template_command = match_template(command)
            if template_command:
                command = template_command

            if "rm " in command or "delete" in command.lower():
                confirm = QMessageBox.question(self, "Confirm Deletion",
                                            "This command may delete files. Are you sure?",
                                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                if confirm != QMessageBox.StandardButton.Yes:
                    self.output_box.append("❌ Cancelled.")
                    return

            result = await Runner.run(agent, command)
            self.output_box.append(f"=== Output ===\n{result.final_output}")

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            ts = datetime.now().isoformat()
            c.execute("INSERT INTO task_log (timestamp, task, tags, success) VALUES (?, ?, ?, ?)",
                    (ts, command, "gui", 1))
            conn.commit()
            conn.close()

            self.show_notification("Agent completed", "Task finished successfully!")

    def show_task_stats(self):
        import sqlite3
        from collections import Counter

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Task frequency
        c.execute("SELECT task FROM task_log")
        tasks = [row[0] for row in c.fetchall()]
        task_counts = Counter(tasks)

        # Tag frequency
        c.execute("SELECT tags FROM task_log")
        tags = []
        for row in c.fetchall():
            tags.extend([t.strip() for t in row[0].split(",") if t.strip()])
        tag_counts = Counter(tags)

        # Success/failure breakdown
        c.execute("SELECT success FROM task_log")
        results = ["✅" if row[0] else "❌" for row in c.fetchall()]
        result_counts = Counter(results)

        conn.close()

        dlg = QDialog(self)
        dlg.setWindowTitle("Task Stats")
        dlg.resize(400, 400)
        layout = QVBoxLayout()
        output = QTextEdit()
        output.setReadOnly(True)

        output.append("📊 Task Frequency:")
        for task, count in task_counts.most_common():
            output.append(f"  • {task}: {count}x")

        output.append("\n🏷️ Tag Frequency:")
        for tag, count in tag_counts.most_common():
            output.append(f"  • #{tag}: {count}x")

        output.append("\n📈 Success Stats:")
        for result, count in result_counts.items():
            output.append(f"  • {result}: {count}x")

        layout.addWidget(output)
        dlg.setLayout(layout)
        dlg.exec()

    def save_output(self):
            text = self.output_box.toPlainText()
            if not text.strip():
                QMessageBox.information(self, "No Output", "There is no output to save.")
                return
            filepath, _ = QFileDialog.getSaveFileName(self, "Save Output", os.path.expanduser("~/agent_output.txt"), "Text Files (*.txt)")
            if filepath:
                with open(filepath, "w") as f:
                    f.write(text)
                QMessageBox.information(self, "Saved", f"Output saved to {filepath}")

    def show_notification(self, title, message):
            subprocess.Popen(['notify-send', title, message])

    def check_reminders(self):
            if not os.path.exists(DB_FILE):
                return
            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                one_hour_ago = datetime.now() - timedelta(hours=1)
                c.execute("SELECT task FROM task_log WHERE timestamp >= ? ORDER BY timestamp DESC", (one_hour_ago.isoformat(),))
                rows = c.fetchall()
                if rows:
                    self.show_notification("Reminder", f"You recently ran: {rows[0][0]}")
                conn.close()
            except Exception as e:
                print("Reminder check failed:", e)

    def toggle_logger(self):
            if is_logger_running():
                stop_logger()
            else:
                start_logger()
            self.update_logger_button()

    def update_logger_button(self):
            if is_logger_running():
                self.toggle_logger_button.setText("🛑 Stop Keyboard Logger")
            else:
                self.toggle_logger_button.setText("🎹 Start Keyboard Logger")



    def check_reminders(self):
            if not os.path.exists(DB_FILE):
                return
            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                one_hour_ago = datetime.now() - timedelta(hours=1)
                c.execute("SELECT task FROM task_log WHERE timestamp >= ? ORDER BY timestamp DESC", (one_hour_ago.isoformat(),))
                rows = c.fetchall()
                if rows:
                    self.show_notification("Reminder", f"You recently ran: {rows[0][0]}")
                conn.close()
            except Exception as e:
                print("Reminder check failed:", e)

    def save_output(self):
            text = self.output_box.toPlainText()
            if not text.strip():
                QMessageBox.information(self, "No Output", "There is no output to save.")
                return
            filepath, _ = QFileDialog.getSaveFileName(self, "Save Output", os.path.expanduser("~/agent_output.txt"), "Text Files (*.txt)")
            if filepath:
                with open(filepath, "w") as f:
                    f.write(text)
                QMessageBox.information(self, "Saved", f"Output saved to {filepath}")

    def suggest_similar_commands(self):
        text = self.command_input.text().strip()
        if not text:
            return
        suggestions = retrieve_similar(text)
        if suggestions:
            self.output_box.append("💡 Similar past commands:")
            for cmd, score in suggestions:
                self.output_box.append(f"  {cmd} ({score:.2f})")

def init_db():
    if not os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS task_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                task TEXT,
                tags TEXT,
                success INTEGER
            )
        """)
        conn.commit()
        conn.close()
    init_memory_db()

def main():
    try:
        init_db()
        screenshot_init_db()
        app = QApplication(sys.argv)
        app.setApplicationName("Scattered Files")
        window = AgentRunnerApp()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print("Fatal error:", e)

if __name__ == "__main__":
    main()
