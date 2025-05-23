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

def match_template(user_input):
    for key, template in COMMAND_TEMPLATES.items():
        if user_input.lower().startswith(key):
            # Extract the task part
            task = user_input[len(key):].strip()
            # Optionally, handle time parsing here (e.g., "in one hour")
            return template.replace("{task}", task)
    return None