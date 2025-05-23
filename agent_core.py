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
import shlex
import json
from memory import save_command

load_dotenv()
api_key = os.environ["OPENAI_API_KEY"]

def load_system_info():
    try:
        with open("system_info.json") as f:
            return json.load(f)
    except Exception:
        # Fallback: gather some info dynamically
        import platform, getpass, socket
        return {
            "os": platform.system(),
            "distro": " ".join(platform.linux_distribution()) if hasattr(platform, "linux_distribution") else "",
            "hostname": socket.gethostname(),
            "user": getpass.getuser(),
            "shell": os.environ.get("SHELL", ""),
            "home": os.path.expanduser("~"),
            "has_sudo": os.geteuid() == 0,
            "default_terminal": "gnome-terminal"
        }

SYSTEM_INFO = load_system_info()

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

def safe_execute_shell_command(command: str) -> tuple[bool, str]:
    """
    Executes a shell command safely. Returns (success, output).
    Handles complex commands (e.g. sleep, notify-send, pipes).
    """
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            check=False  # Let us handle error output ourselves
        )
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def maybe_execute_shell_command(output: str) -> bool:
    """
    Determines if a string looks like a shell command and tries to run it.
    Returns True if executed, False otherwise.
    """
    output = output.strip()
    shell_starters = [
        "sudo", "ls", "du", "mkdir", "mv", "rm", "notify-send",
        "nautilus", "code", "gnome-terminal", "/usr", "/snap", "(",
        "echo", "sleep", "curl", "wget", "python", "bash"
    ]

    if any(output.startswith(cmd) for cmd in shell_starters) or output.endswith("&"):
        success, msg = safe_execute_shell_command(output)
        if success:
            print(f"✅ Shell command executed:\n{msg}")
        else:
            print(f"❌ Shell command failed:\n{msg}")
        return True
    return False

def schedule_reminder(task, minutes_from_now=60):
    delay_seconds = minutes_from_now * 60
    command = f"(sleep {delay_seconds}; notify-send 'Reminder: {task}') &"
    return safe_execute_shell_command(command)[1]

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
    "delete duplicate files": "rm ~/Downloads/*\\(1\\)* ~/Downloads/*\\(2\\)*",
    "remind me to": "(sleep 3600; notify-send 'Reminder: {task}') &"
}

def check_hot_command(user_input: str):
    for key, val in HOT_COMMANDS.items():
        if user_input.startswith(key):
            name = user_input.replace(key, "").strip()
            return val["script"], name
    return None, None



agent = Agent(
    name="Workspace Agent GUI",
    instructions=(
        f"You are a local assistant running on {SYSTEM_INFO['os']} ({SYSTEM_INFO.get('distro','')}). "
        f"Hostname: {SYSTEM_INFO['hostname']}, User: {SYSTEM_INFO['user']}, Shell: {SYSTEM_INFO['shell']}. "
        "You receive natural language instructions and convert them into direct shell commands. "
        "When using the LocalComputerTool, pass only the raw shell command as input. Do not wrap it in text."
    ),
    tools=[LocalComputerTool],
)

def extract_followup_task(summary):
    # crude heuristic, upgrade later
    for line in summary.split("\n"):
        if any(word in line.lower() for word in ["follow", "remind", "send", "confirm"]):
            return line.strip()
    return None

def summarize_text(text):
    import openai
    client = openai.OpenAI()  # Uses OPENAI_API_KEY from environment
    prompt = f"Summarize the following phone call conversation. Highlight any tasks to follow up:\n\n{text}"
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You summarize call conversations for an agent."},
            {"role": "user", "content": prompt}
        ]
    )
    return response.choices[0].message.content.strip()

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
            file=audio_file,
            language="en"
        )
    return transcript.text

async def process_user_command(user_input, confirm_delete_callback=None):
        script, project_name = check_hot_command(user_input)
        if script:
            subprocess.run(["python", script, project_name])
            save_command(user_input, output=f"Ran hot command: {script}")
            return f"🚀 Running hot command: {script}", False

        template_command = match_template(user_input)
        if template_command:
            user_input = f"Run: {template_command}"

        if "rm " in user_input or "delete" in user_input.lower():
            if confirm_delete_callback:
                confirm = confirm_delete_callback()
            else:
                confirm = input("⚠️ This will delete files. Are you sure? (y/n): ")
            if confirm.lower() != "y":
                return "❌ Cancelled.", True

        result = await Runner.run(agent, user_input)
        output = result.final_output
        executed = maybe_execute_shell_command(output)

        # Optionally prompt for feedback
        feedback = input("💬 Was this helpful? (optional): ").strip() if os.isatty(0) else ""
        save_command(user_input, output, feedback)

        if executed:
            return f"✅ Executed: {output}", False
        return output, False

def schedule_reminder(task, minutes_from_now=60):
    import subprocess, shlex
    notify_cmd = f"notify-send 'Reminder: {task}'"
    at_time = f"now + {minutes_from_now} minutes"
    cmd = f"echo {shlex.quote(notify_cmd)} | at {shlex.quote(at_time)}"
    try:
        subprocess.run(cmd, shell=True, check=True)
        return f"⏰ Reminder scheduled for {minutes_from_now} minutes from now."
    except Exception as e:
        return f"❌ Failed to schedule reminder: {e}"
    
FILETYPE_APP_MAP = {
    'pdf': 'libreoffice',
    'txt': 'gedit',
    'jpg': 'eog',
    'png': 'eog',
    # Add more as needed
}

def open_file_with_default_app(filepath):
    ext = filepath.split('.')[-1].lower()
    app = FILETYPE_APP_MAP.get(ext)
    if app:
        subprocess.Popen([app, filepath])
        return f"Opening {filepath} with {app}."
    else:
        # fallback to xdg-open (Linux)
        subprocess.Popen(['xdg-open', filepath])
        return f"Opening {filepath} with default application."
    
def summarize_recent_speech(num_entries=5):
    if not os.path.exists(SPEECH_LOG_PATH):
        return ""
    try:
        with open(SPEECH_LOG_PATH, "r") as f:
            lines = f.readlines()[-num_entries:]
        text = " ".join([line.strip().split(" ", 1)[1] for line in lines if " " in line])
        prompt = (
            "Summarize this call into a one-line reminder if any actions are needed. "
            "If none, return an empty string.\n\nConversation:\n" + text
        )
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return completion.choices[0].message["content"].strip()
    except Exception as e:
        print(f"❌ Error summarizing call: {e}")
        return ""
    
