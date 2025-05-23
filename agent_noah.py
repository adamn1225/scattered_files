import sys
import asyncio
import sqlite3
import os
from datetime import datetime, timedelta
from collections import Counter
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QComboBox, QMessageBox, QFileDialog, QDialog, QTableWidget, QTableWidgetItem, QTabWidget, QHBoxLayout, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QPalette, QColor, QPixmap, QIcon
from agents import Agent, Runner
from tools.local_computer_tool import LocalComputerTool
from hot_commands import HOT_COMMANDS
import subprocess
from keyboard_logger import start_logger, stop_logger, is_logger_running
from screenshot_capture import capture_and_store_all_screens, init_db as screenshot_init_db
from memory import init_memory_db, save_command, retrieve_similar
from pattern_learner import analyze_patterns
from task_logger import log_task
import threading
import sounddevice as sd
import numpy as np
import scipy.io.wavfile
import speech_recognition as sr
from agent_core import agent, check_hot_command, analyze_speech_log, recognize_speech, transcribe_audio, log_transcribed_speech, process_user_command, maybe_execute_shell_command, schedule_reminder, open_file_with_default_app, summarize_recent_speech, schedule_reminder
from templates import COMMAND_TEMPLATES, match_template
from calendar_integration import get_upcoming_events
from call_listener import CallSessionLogger
import threading
from dotenv import load_dotenv
load_dotenv()
api_key = os.environ["OPENAI_API_KEY"]

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

        self.prev_button = QPushButton("Previous Screenshot")
        self.prev_button.clicked.connect(self.load_prev_image)
        self.layout.addWidget(self.prev_button)

# Add this method:
    def load_prev_image(self):
        if not self.image_files:
            self.image_label.setText("No screenshots found.")
            return
        if self.current_index <= 1:
            self.image_label.setText("Start of screenshots.")
            return
        self.current_index -= 2  # Go back two, since load_next_image will increment by one
        self.load_next_image()

        self.setLayout(self.layout)

        self.screenshot_dir = os.path.expanduser("~/.workspace_screens")
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir)
        self.image_files = sorted([
            f for f in os.listdir(self.screenshot_dir)
            if f.endswith(".png")
        ], reverse=True)
        self.current_index = 0

        if self.image_files:
            self.load_next_image()
        else:
            self.image_label.setText("No screenshots found.")

    def load_next_image(self):
        if not self.image_files:
            self.image_label.setText("No screenshots found.")
            return
        if self.current_index >= len(self.image_files):
            self.image_label.setText("End of screenshots.")
            return

        path = os.path.join(self.screenshot_dir, self.image_files[self.current_index])
        if not os.path.exists(path):
            self.image_label.setText("Image file not found.")
            return
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
        try:
            conn = sqlite3.connect(KEYLOG_DB_FILE)
            c = conn.cursor()
            c.execute("SELECT key FROM keystrokes WHERE is_modifier = 0 ORDER BY id DESC LIMIT 500")
            keys = [row[0] for row in c.fetchall()]
            conn.close()
        except Exception as e:
            self.output.append(f"❌ Could not load keystrokes: {e}")
            return

        # Filter out None values
        keys = [k for k in keys if k is not None]
        text = "".join(k for k in keys if len(k) == 1 or k.startswith("'") or k.isalnum())
        words = text.split()
        phrases = [" ".join(words[i:i+3]) for i in range(len(words)-2)]
        common = Counter(phrases).most_common(10)

        self.output.append("Top common 3-word phrases:")
        for phrase, count in common:
            self.output.append(f"{phrase} — {count}x")

class AgentRunnerApp(QWidget):
    output_signal = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.logger_running = is_logger_running()
        self.init_ui() 
        self.awaiting_reply = False
        self.last_agent_message = ""
        self.check_reminders()
        self.output_signal.connect(self.output_box.append)
        self.last_command = ""
        self.last_output = ""
        self.call_logger = CallSessionLogger()
        self.listening = False
        self.listen_thread = None

    def init_ui(self):
        self.setWindowTitle("Scattered Files")
        self.setWindowIcon(QIcon("icon.png"))
        self.setGeometry(400, 400, 800, 800)
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
        self.setStyleSheet("""
        QWidget { background-color: #1e293b; color: white; }
        QTabWidget::pane { background: #1e293b; }
        QTabBar::tab { background: #334155; color: white; }
        QTabBar::tab:selected { background: #3b82f6; }
        QLabel { color: white; }
        QPushButton { background-color: #334155; color: white; border: none; padding: 6px; }
        QPushButton:hover { background-color: #3b82f6; }
    """)

        tabs = QTabWidget()

        # --- Agent Tab ---
        agent_tab = QWidget()
        agent_layout = QVBoxLayout()

        input_row = QHBoxLayout()
        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("What should the agent do?")
        self.command_input.textChanged.connect(self.suggest_similar_commands)

        self.mic_button = QPushButton()
        self.mic_button.setIcon(QIcon("mic.png"))
        self.mic_button.setIconSize(QSize(28, 28))  # Adjust as needed
        self.mic_button.setToolTip("Speak command")
        self.mic_button.setFixedSize(40, 40)
        self.mic_button.setStyleSheet("padding: 0px; margin: 0px; border: none;")
        self.mic_button.pressed.connect(self.start_command_recording)
        self.mic_button.released.connect(self.stop_command_recording)
        self.mic_button.setToolTip("Record and run a spoken command")

        input_row.addWidget(self.command_input)
        input_row.addWidget(self.mic_button)

        agent_layout.addWidget(QLabel("Enter Command:"))
        agent_layout.addLayout(input_row)

        self.template_command_box = QComboBox()
        self.template_command_box.addItem("-- Choose template command --")
        for key in COMMAND_TEMPLATES:
            self.template_command_box.addItem(key)
        self.template_command_box.currentIndexChanged.connect(self.load_template_command)
        agent_layout.addWidget(self.template_command_box)

        self.hot_command_box = QComboBox()
        self.hot_command_box.addItem("-- Choose hot command --")
        for key in HOT_COMMANDS:
            self.hot_command_box.addItem(key)
        self.hot_command_box.currentIndexChanged.connect(self.load_hot_command)
        agent_layout.addWidget(self.hot_command_box)

        self.run_button = QPushButton("Run Agent")
        self.run_button.clicked.connect(self.run_agent)
        agent_layout.addWidget(self.run_button)

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setStyleSheet("background-color: #121c2b; color: white;")
        agent_layout.addWidget(QLabel("Agent Output:"))
        agent_layout.addWidget(self.output_box)

        feedback_row = QHBoxLayout()

        self.thumbs_up_button = QPushButton("👍")
        self.thumbs_down_button = QPushButton("👎")
        self.learn_checkbox = QPushButton("💡 Learn this")
        self.learn_checkbox.setCheckable(True)

        self.thumbs_up_button.clicked.connect(lambda: self.save_feedback("up"))
        self.thumbs_down_button.clicked.connect(lambda: self.save_feedback("down"))

        feedback_row.addWidget(self.thumbs_up_button)
        feedback_row.addWidget(self.thumbs_down_button)
        feedback_row.addWidget(self.learn_checkbox)

        agent_layout.addLayout(feedback_row)

        self.awaiting_reply = False
        self.last_agent_message = ""

        self.save_button = QPushButton("Save Output to File")
        self.save_button.setToolTip("Save the agent output to a file")
        self.save_button.clicked.connect(self.save_output)
        agent_layout.addWidget(self.save_button)
        # --- Settings Buttons Group ---
        from PyQt6.QtWidgets import QGroupBox

        settings_group = QGroupBox("Controls")
        settings_layout = QVBoxLayout()

        self.toggle_logger_button = QPushButton()
        self.toggle_logger_button.clicked.connect(self.toggle_logger)
        self.toggle_logger_button.setToolTip("Start or stop the keyboard logger")
        settings_layout.addWidget(self.toggle_logger_button)
        self.update_logger_button()

        self.calendar_button = QPushButton("📅 Show Next Calendar Event")
        self.calendar_button.clicked.connect(self.show_next_calendar_event)
        self.calendar_button.setToolTip("Show your next calendar event")
        settings_layout.addWidget(self.calendar_button)

        self.log_listen_button = QPushButton("📝 Log Speech")
        self.log_listen_button.setCheckable(True)
        self.log_listen_button.clicked.connect(self.toggle_log_listen)
        self.log_listen_button.setToolTip("Transcribe and log speech (does not execute)")
        settings_layout.addWidget(self.log_listen_button)
        
        self.listen_button = QPushButton("🎧 Toggle Listen Mode")
        self.listen_button.clicked.connect(self.toggle_listen_mode)
        settings_layout.addWidget(self.listen_button)


        settings_group.setLayout(settings_layout)
        agent_layout.addWidget(settings_group)

        agent_tab.setLayout(agent_layout)
        tabs.addTab(agent_tab, "Agent")

        # --- Logs Tab ---
        logs_tab = QWidget()
        logs_layout = QVBoxLayout()

        self.log_view_button = QPushButton("View Keystroke Log")
        self.log_view_button.clicked.connect(self.show_keystroke_log)
        logs_layout.addWidget(self.log_view_button, alignment=Qt.AlignmentFlag.AlignTop)

        self.summary_button = QPushButton("🧠 Summarize Phrases")
        self.summary_button.clicked.connect(self.show_phrase_summary)
        logs_layout.addWidget(self.summary_button, alignment=Qt.AlignmentFlag.AlignTop)

        self.view_screenshots_button = QPushButton("🖼️ View Screenshots")
        self.view_screenshots_button.clicked.connect(self.show_screenshots)
        logs_layout.addWidget(self.view_screenshots_button, alignment=Qt.AlignmentFlag.AlignTop)

        logs_layout.addStretch()  
        logs_tab.setLayout(logs_layout)
        tabs.addTab(logs_tab, "Logs")

        # --- Stats Tab ---
        stats_tab = QWidget()
        stats_layout = QVBoxLayout()

        self.pattern_button = QPushButton("📊 Show Routine Patterns")
        self.pattern_button.clicked.connect(self.show_patterns)
        stats_layout.addWidget(self.pattern_button, alignment=Qt.AlignmentFlag.AlignTop)

        self.nudge_button = QPushButton("🤖 Nudge Me (Today's Routine)")
        self.nudge_button.clicked.connect(self.show_nudge)
        stats_layout.addWidget(self.nudge_button, alignment=Qt.AlignmentFlag.AlignTop)

        self.log_task_button = QPushButton("📝 Log Task Manually")
        self.log_task_button.clicked.connect(self.show_log_task)
        stats_layout.addWidget(self.log_task_button, alignment=Qt.AlignmentFlag.AlignTop)

        self.stats_button = QPushButton("📈 Show Task Stats")
        self.stats_button.clicked.connect(self.show_task_stats)
        stats_layout.addWidget(self.stats_button, alignment=Qt.AlignmentFlag.AlignTop)

        self.check_reminders_button = QPushButton("🔔 Check Reminders")
        self.check_reminders_button.clicked.connect(self.check_reminders)
        stats_layout.addWidget(self.check_reminders_button, alignment=Qt.AlignmentFlag.AlignTop)
        stats_layout.addStretch()
        stats_tab.setLayout(stats_layout)
        tabs.addTab(stats_tab, "Stats")

        # --- Main Layout ---
        main_layout = QVBoxLayout()
        main_layout.addWidget(tabs)
        self.setLayout(main_layout)

    def start_command_recording(self):
        self.recording = True
        self.mic_button.setIcon(QIcon("mic-on.png"))  # Use a red or "on" icon
        self.output_box.append("🎤 Hold to speak your command...")
        self.command_audio = []
        self.record_thread = threading.Thread(target=self._record_command_audio, daemon=True)
        self.record_thread.start()

    def stop_command_recording(self):
        self.recording = False
        self.mic_button.setIcon(QIcon("mic.png"))  # Revert to normal icon
        self.output_box.append("🛑 Processing command...")
        if hasattr(self, 'record_thread'):
            self.record_thread.join()
        self._process_command_audio()
        self.mic_button.clearFocus()

    def _record_command_audio(self):
        import sounddevice as sd
        import numpy as np
        fs = 16000
        self.command_audio = []
        with sd.InputStream(samplerate=fs, channels=1, dtype='float32') as stream:
            while self.recording:
                chunk, _ = stream.read(int(fs * 0.1))
                self.command_audio.append(chunk)
        self.command_audio = np.vstack(self.command_audio) if self.command_audio else np.empty((0, 1), dtype=np.float32)

    def _process_command_audio(self):
        import scipy.io.wavfile
        fs = 16000
        if self.command_audio is not None and len(self.command_audio) > 0:
            scipy.io.wavfile.write("output.wav", fs, (self.command_audio * 32767).astype(np.int16))
            try:
                text = transcribe_audio("output.wav")
                self.output_box.append(f"🗣️ Whisper: {text}")
                log_transcribed_speech(text)
                if text.strip():
                    asyncio.run(self.run_agent_command(text.strip()))
            except Exception as e:
                self.output_box.append(f"❌ Transcription error: {e}")
        else:
            self.output_box.append("No audio recorded.")

    def show_next_calendar_event(self):
        events = get_upcoming_events(1)
        if events:
            next_event = events[0]
            start = next_event['start'].get('dateTime', next_event['start'].get('date'))
            self.output_box.append(f"📅 Next meeting: {next_event['summary']} at {start}")
        else:
            self.output_box.append("No upcoming meetings found.")

    def show_patterns(self):
        patterns = analyze_patterns()
        dlg = QDialog(self)
        dlg.setWindowTitle("Routine Patterns")
        dlg.resize(1000, 750)
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

    def toggle_listen_mode(self):
        if not self.listening:
            self.listen_thread = threading.Thread(target=self.listen_loop, daemon=True)
            self.listening = True
            self.call_logger.toggle_recording(True)
            self.listen_thread.start()
            self.show_notification("Listening started", "Call transcription has begun.")
        else:
            self.listening = False
            self.call_logger.toggle_recording(False)
            self.show_notification("Listening stopped", "Call transcription ended and summary saved.")

    def listen_loop(self):
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        mic = sr.Microphone()
        with mic as source:
            recognizer.adjust_for_ambient_noise(source)
            while self.listening:
                try:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
                    text = recognizer.recognize_google(audio)
                    if text:
                        self.call_logger.record_snippet(text)
                except sr.WaitTimeoutError:
                    continue
                except sr.UnknownValueError:
                    continue
                except Exception as e:
                    print(f"[listen_loop error] {e}")
                    break
                
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
            

    def toggle_log_listen(self):
        if self.log_listen_button.isChecked():
            self.log_listen_button.setText("🛑 Logging...")
            self.log_listen_button.setIcon(QIcon("mic-on.png"))
            self.log_listening = True  # <-- use log_listening
            self.log_listen_thread = threading.Thread(target=self.listen_to_log, daemon=True)
            self.log_listen_thread.start()
        else:
            self.log_listen_button.setText("📝 Log Speech")
            self.log_listen_button.setIcon(QIcon("mic.png"))
            self.log_listening = False  # <-- use log_listening

    # Passive log mic (in controls)
    def listen_to_log(self):
        fs = 16000
        seconds = 5

        self.output_box.append("🎤 Recording for log...")
        recording = np.empty((0, 1), dtype=np.float32)
        chunk_size = int(fs * 0.1)
        total_samples = int(fs * seconds)
        samples_recorded = 0

        with sd.InputStream(samplerate=fs, channels=1, dtype='float32') as stream:
            while samples_recorded < total_samples and self.log_listening:
                chunk, _ = stream.read(chunk_size)
                recording = np.vstack((recording, chunk))
                samples_recorded += chunk.shape[0]

        if not self.log_listening:
            self.output_box.append("🛑 Recording stopped.")
            return

        scipy.io.wavfile.write("output.wav", fs, (recording * 32767).astype(np.int16))

        try:
            text = transcribe_audio("output.wav")
            self.output_box.append(f"📝 Log: {text}")
            log_transcribed_speech(text)
        except Exception as e:
            self.output_box.append(f"❌ Transcription error: {e}")

        summary = summarize_recent_speech()
        if summary and len(summary) > 5:
            self.output_box.append(f"📌 Call Summary Suggestion: {summary}")
            confirm = QMessageBox.question(
                self, "Set Reminder?",
                f"Set a reminder based on this call?\n\n{summary}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if confirm == QMessageBox.StandardButton.Yes:
                result = schedule_reminder(summary, 30)
                self.output_box.append(result)

    def callback(self, text):
        if text:
            self.output_box.append(f"🗣️ {text}")
            log_transcribed_speech(text)
        try:
            text = transcribe_audio("output.wav")
            self.output_box.append(f"🗣️ Whisper: {text}")
            self.log_transcribed_speech(text)
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
    # In start_continuous_recognition's callback:
    top_phrases = analyze_speech_log()
    for phrase, count in top_phrases:
        print(f"{phrase} — {count}x")

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

        if self.awaiting_reply:
            # Combine last agent message and user reply for context
            command = f"{self.last_agent_message}\nUser: {command}"

        asyncio.run(self.run_agent_command(command))

    def some_method(self):
        # Schedule a reminder for 30 minutes from now
        result = schedule_reminder("Check the oven", 30)
        self.output_box.append(result)

        # Open a PDF file
        result = open_file_with_default_app("/home/adam-noah/Documents/file.pdf")
        self.output_box.append(result)

    async def run_agent_command(self, user_input):
        def gui_confirm():
            reply = QMessageBox.question(
                self, "Confirm Delete",
                "⚠️ This will delete files. Are you sure?",
                QMessageBox.Yes | QMessageBox.No
            )
            return "y" if reply == QMessageBox.Yes else "n"

        output, cancelled = await process_user_command(user_input, confirm_delete_callback=gui_confirm)

        if cancelled:
            self.output_box.append("❌ Command cancelled by user.")
            self.awaiting_reply = False
            self.last_agent_message = ""
            self.command_input.setPlaceholderText("What should the agent do?")
            return

        # ✅ Save command and output for learning/memory
        save_command(user_input, output)
        self.last_command = user_input
        self.last_output = output
        self.learn_checkbox.setChecked(False)

        # Show output
        if "❌" in output or "error" in output.lower():
            self.output_box.append(f"<span style='color:red;'>{output}</span>")
        else:
            self.output_box.append(output)

        if output.strip().endswith("?"):
            self.awaiting_reply = True
            self.last_agent_message = output
            self.command_input.setPlaceholderText("Reply to agent...")
        else:
            self.awaiting_reply = False
            self.last_agent_message = ""
            self.command_input.setPlaceholderText("What should the agent do?")


    async def execute_agent(self, command):
        self.output_box.clear()

        def confirm_gui_delete():
            confirm = QMessageBox.question(self, "Confirm Deletion",
                                        "This command may delete files. Are you sure?",
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            return "y" if confirm == QMessageBox.StandardButton.Yes else "n"

        output_text, was_cancelled = await process_user_command(command, confirm_delete_callback=confirm_gui_delete)

        if not was_cancelled:
            self.output_box.append(output_text)

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



        self.show_notification("Agent completed", "Task finished successfully!")

    def get_user_feedback(self):
        text, ok = QInputDialog.getText(self, "Feedback", "Was this helpful?")
        return text if ok else ""

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
    c.execute("""
        CREATE TABLE IF NOT EXISTS speech_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            text TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS command_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            command TEXT,
            output TEXT,
            rating TEXT,
            learn INTEGER
        )
    """)
    # ADD THIS:
    c.execute("""
        CREATE TABLE IF NOT EXISTS command_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            command TEXT,
            output TEXT,
            feedback TEXT,
            embedding BLOB
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
