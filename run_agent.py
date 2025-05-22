import asyncio
import sys
from agents import Agent, Runner
from tools.local_computer_tool import LocalComputerTool
from templates import match_template
from hot_commands import HOT_COMMANDS
import subprocess
from agent_core import agent, check_hot_command, match_template

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


async def main():
    if len(sys.argv) == 2 and sys.argv[1] == "-h":
        print(HELP_TEXT)
        return

    user_input = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("What should the agent do?\n> ")

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

