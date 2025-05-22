from agents import Agent, Runner
from tools.local_computer_tool import LocalComputerTool
from templates import match_template
from hot_commands import HOT_COMMANDS
import speech_recognition as sr
import openai

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