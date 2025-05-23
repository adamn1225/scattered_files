from agents import Agent, Runner
import os
from tools.local_computer_tool import LocalComputerTool
from templates import match_template
from hot_commands import HOT_COMMANDS
import speech_recognition as sr
import openai
from datetime import datetime
from collections import Counter
import subprocess
import os
import glob
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ["OPENAI_API_KEY"]

def launch_application(app_name):
    # Try direct execution (for CLI apps)
    from shutil import which
    exe = which(app_name.lower())
    if exe:
        subprocess.Popen([exe])
        return f"Launching {app_name}..."

    # Try .desktop files for GUI apps
    desktop_dirs = [
        "/usr/share/applications/",
        os.path.expanduser("~/.local/share/applications/")
    ]
    for ddir in desktop_dirs:
        for desktop_file in glob.glob(os.path.join(ddir, "*.desktop")):
            with open(desktop_file, encoding="utf-8", errors="ignore") as f:
                content = f.read().lower()
                if app_name.lower() in content:
                    # Find the Exec line
                    for line in content.splitlines():
                        if line.startswith("exec="):
                            exec_cmd = line.split("=", 1)[1].split()[0]
                            subprocess.Popen([exec_cmd])
                            return f"Launching {app_name} via {exec_cmd}..."
    return f"Could not find application '{app_name}'."

def analyze_speech_log(top_n=10):
    if not os.path.exists(SPEECH_LOG_PATH):
        return []
    with open(SPEECH_LOG_PATH, "r") as f:
        lines = f.readlines()
    # Extract just the text part
    texts = [line.strip().split(" ", 1)[1] for line in lines if " " in line]
    # Simple phrase frequency analysis
    phrases = []
    for text in texts:
        words = text.split()
        phrases.extend([" ".join(words[i:i+3]) for i in range(len(words)-2)])
    return Counter(phrases).most_common(top_n)

SPEECH_LOG_PATH = os.path.expanduser("~/.workspace_agent_speech.log")

def log_transcribed_speech(text):
    with open(SPEECH_LOG_PATH, "a") as f:
        f.write(f"{datetime.now().isoformat()} {text}\n")

COMMAND_TEMPLATES = {
    "show disk usage": "du -sh ~",
    "list files": "ls -lah",
    "move pdfs to archive": "mkdir -p archive && mv *.pdf archive/",
    "create folder with readme": "mkdir project_folder && echo '# Project' > project_folder/README.md",
    "open chrome": "/snap/bin/chromium &",
    "launch chrome": "/snap/bin/chromium &",
    "open vscode": "code .",
    "open terminal": "gnome-terminal &",
    "open slack": "/usr/bin/slack &",
    "open file manager": "nautilus . &",
    "move images from downloads to pictures": "mkdir -p ~/Pictures/downloaded_images && mv ~/Downloads/*.{jpg,jpeg,png} ~/Pictures/downloaded_images/",
    "delete duplicate files": "rm ~/Downloads/*\\(1\\)* ~/Downloads/*\\(2\\)*"
}

def check_hot_command(user_input: str):
    for key, val in HOT_COMMANDS.items():
        if user_input.startswith(key):
            name = user_input.replace(key, "").strip()
            return val["script"], name
    return None, None

agent = Agent(
    name="Workspace Agent",
    instructions=(
        "You are a local assistant that receives natural language instructions and converts them into direct shell commands. "
        "When using the LocalComputerTool, pass only the raw shell command as input. Do not wrap it in text."
    ),
    tools=[LocalComputerTool],
)

def recognize_speech(callback, stop_flag):
    recognizer = sr.Recognizer()
    mic = sr.Microphone()
    with mic as source:
        recognizer.adjust_for_ambient_noise(source)
        while not stop_flag():
            try:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=10)
                text = recognizer.recognize_google(audio)
                callback(text)
            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                callback(None)
            except Exception as e:
                callback(f"ERROR: {e}")
                break

def transcribe_audio(file_path, api_key=None, model="whisper-1"):
    if api_key:
        openai.api_key = api_key
    with open(file_path, "rb") as audio_file:
        transcript = openai.audio.transcriptions.create(
            model=model,
            file=audio_file
        )
    return transcript.text

async def process_user_command(user_input, confirm_delete_callback=None):
    """
    Process a user command: check hot commands, templates, safety, and run agent.
    Optionally, provide a callback for confirming deletions (for GUI/CLI).
    Returns: (output_text, was_cancelled)
    """
    # Check for hot command first
    script, project_name = check_hot_command(user_input)
    if script:
        subprocess.run(["python", script, project_name])
        return f"🚀 Running hot command: {script} with project name '{project_name}'", False

    # Template override (if matched)
    template_command = match_template(user_input)
    if template_command:
        user_input = f"Run: {template_command}"

    # File deletion safety check
    if "rm " in user_input or "delete" in user_input.lower():
        if confirm_delete_callback:
            confirm = confirm_delete_callback()
        else:
            confirm = input("⚠️ This will delete files. Are you sure? (y/n): ")
        if confirm.lower() != "y":
            return "❌ Cancelled.", True

    # Now run agent if not a hot command
    result = await Runner.run(agent, user_input)
    return result.final_output, False