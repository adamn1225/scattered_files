import subprocess
from typing import Any
from pydantic import BaseModel, ConfigDict
from agents import FunctionTool, RunContextWrapper


class ShellCommandArgs(BaseModel):
    command: str

    model_config = ConfigDict(extra='forbid')


async def run_shell_command(ctx: RunContextWrapper[Any], args: str) -> str:
    parsed = ShellCommandArgs.model_validate_json(args)

    try:
        result = subprocess.run(
            parsed.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout.strip() or result.stderr.strip()
        return output or "Command completed with no output."
    except Exception as e:
        return f"[ERROR] {str(e)}"


LocalComputerTool = FunctionTool(
    name="run_shell_command",
    description="Runs a safe shell command on the local machine. Returns stdout or stderr.",
    params_json_schema=ShellCommandArgs.model_json_schema(),
    on_invoke_tool=run_shell_command,
)
