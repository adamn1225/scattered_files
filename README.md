# Scattered Files

## Workspace Assistant Agent

# Features

- **Natural Language Command Runner:** Run shell commands or scripts using natural language.
- **Routine Pattern Analysis:** Learns your habits and routines from your task logs.
- **Task Logging:** Log tasks manually or automatically as you work.
- **Semantic Command Memory:** Remembers and suggests similar commands using AI embeddings.
- **Keystroke Logging:** (Optional) Records your keystrokes for phrase analysis and productivity insights.
- **Screenshot Capture:** (Optional) Periodically captures screenshots for activity review.
- **Voice Recognition:** (Optional) Transcribes audio from your microphone using OpenAI Whisper or GPT-4o.
- **Reminders & Nudges:** Reminds you of your routines and nudges you to stay on track.
- **Privacy-First:** All data is stored locally. No cloud sync or remote server.

## ⚠️ Privacy & Security Warnings

- **Keylogger:** This application includes a keylogger feature. It records all keystrokes when enabled.  
  **The keylogger is OFF by default** and must be explicitly toggled on in the UI.
- **Screen Capture:** The app can periodically take screenshots of your desktop.  
  **Screen capture is OFF by default** and must be enabled by the user.
- **Microphone Listener:** The app can record and transcribe audio from your microphone.  
  **Voice recognition is OFF by default** and must be toggled on in the UI.
- **Data Storage:** All logs (keystrokes, screenshots, audio transcriptions, commands) are stored locally on your machine.  
  **No data is sent to any remote server.**
- **Ethical Use:** Please use this application responsibly and only on machines you own or have explicit permission to monitor.  
  Recording keystrokes, audio, or screenshots without consent may be illegal in your jurisdiction.

## Installation

1. Clone this repository:
    ```bash
    git clone https://github.com/yourusername/WorkspaceAssistantAgent.git
    cd WorkspaceAssistantAgent
    ```

2. Create and activate a virtual environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4. (Optional) Install system dependencies for audio features:
    ```bash
    sudo apt-get install portaudio19-dev python3-pyaudio
    ```

## Usage

Start the desktop application:
```bash
python3 agent_noah.py
```

- Use the UI to run commands, log tasks, view stats, and enable/disable keylogger, screenshot, and mic features.
- All monitoring features (keylogger, screenshots, mic) are **OFF by default** and must be toggled on by the user.

## Contributing

Pull requests are welcome! Please open an issue first to discuss major changes.

## License

[MIT](LICENSE)

---

**By using this software, you acknowledge the privacy and ethical implications of enabling monitoring features. Use responsibly.**