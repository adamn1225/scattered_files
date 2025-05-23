import asyncio
import sys
import os
from agents import Agent, Runner
from tools.local_computer_tool import LocalComputerTool
from templates import match_template
from hot_commands import HOT_COMMANDS
import subprocess
from agent_core import agent, check_hot_command, match_template, maybe_execute_shell_command
import whisper
import sounddevice as sd
import scipy.io.wavfile
from dotenv import load_dotenv
from agent_core import process_user_command
import json
from file_index import init_file_index_db

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

HELP_TEXT = """
Usage: run_agent.py [task]

Examples:
  python run_agent.py "List all files"
  python run_agent.py "Show disk usage"
  python run_agent.py -h     # this help menu

Common commands:
  • List all files
  • Show disk usage
  • Move PDFs to archive
  • Create folder with README
  • Open Chrome
  • Launch Chrome
  • Open VSCode
  • Open Slack
  • Open file manager
  • Move images from downloads to pictures
  • Delete duplicate files

Hot commands:
  • Scaffold a Next.js + Tailwind project
  • Scaffold a Golang + GORM backend project
• Scaffold fullstack Next.js + Golang project
"""

agent = Agent(
    name="Workspace Agent",
    instructions=(
    "You are a local assistant that receives natural language instructions and converts them into direct shell commands. "
    "When using the LocalComputerTool, pass only the raw shell command as input. Do not wrap it in text."
    ),
    tools=[LocalComputerTool],
)

def check_hot_command(user_input: str):
    for key, val in HOT_COMMANDS.items():
        if user_input.startswith(key):
            name = user_input.replace(key, "").strip()
            return val["script"], name
    return None, None

def record_and_transcribe():
    fs = 16000
    seconds = 5
    print("🎤 Speak now...")
    recording = sd.rec(int(seconds * fs), samplerate=fs, channels=1)
    sd.wait()
    wav_path = "voice_input.wav"
    scipy.io.wavfile.write(wav_path, fs, recording)
    model = whisper.load_model("base")
    result = model.transcribe(wav_path)
    print(f"🗣️ You said: {result['text']}")
    return result['text']


async def main():
    init_file_index_db()
    if len(sys.argv) == 2 and sys.argv[1] == "-h":
        print(HELP_TEXT)
        return
    
    if "--mic" in sys.argv:
        user_input = record_and_transcribe()
    else:
        user_input = " ".join(arg for arg in sys.argv[1:] if arg != "--mic") if len(sys.argv) > 1 else input("What should the agent do?\n> ")

    output, cancelled = await process_user_command(user_input)
    if not cancelled:
        from task_logger import log_task
        log_task(user_input, tags=["agent"], success=True)
    print("\n=== Agent Output ===")
    print(output)

    # Check for hot command first
    script, project_name = check_hot_command(user_input)
    if script:
        print(f"🚀 Running hot command: {script} with project name '{project_name}'")
        subprocess.run(["python", script, project_name])
        return

    # Template override (if matched)
    template_command = match_template(user_input)
    if template_command:
        print(f"[Matched Template] ➜ {template_command}")
        user_input = f"Run: {template_command}"

    # File deletion safety check
    if "rm " in user_input or "delete" in user_input.lower():
        confirm = input("⚠️ This will delete files. Are you sure? (y/n): ")
        if confirm.lower() != "y":
            print("❌ Cancelled.")
            return

    # Now run agent if not a hot command
    result = await Runner.run(agent, user_input)
    from task_logger import log_task
    log_task(user_input, tags=["agent"], success=True)

    print("\n=== Agent Output ===")
    print(result.final_output)
    print(output)
    maybe_execute_shell_command(output)

