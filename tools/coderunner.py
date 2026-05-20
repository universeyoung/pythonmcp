import asyncio
import tempfile
import uuid
import os
import sys
import shutil
from typing import Sequence

from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from pydantic import BaseModel, Field


class RunCodeInput(BaseModel):
    code: str = Field(description="Python code to execute")
    timeout: int = Field(default=30, description="Timeout in seconds", ge=1, le=300)


class RunShellInput(BaseModel):
    command: str = Field(description="Shell command to execute")
    timeout: int = Field(default=30, description="Timeout in seconds", ge=1, le=300)


def get_tools() -> list[Tool]:
    return [
        Tool(
            name="run_code",
            description="Execute Python code and return the output. "
            "Useful for running Python scripts, performing calculations, "
            "or testing code snippets. stdout and stderr are captured and returned.",
            inputSchema=RunCodeInput.model_json_schema(),
        ),
        Tool(
            name="run_shell",
            description="Execute a shell command and return the output. "
            "Supports Windows PowerShell/cmd commands. "
            "Use with caution as it executes arbitrary system commands.",
            inputSchema=RunShellInput.model_json_schema(),
        ),
    ]


async def handle_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource] | None:
    match name:
        case "run_code":
            return await _run_python_code(arguments)
        case "run_shell":
            return await _run_shell_command(arguments)
        case _:
            return None


async def _run_python_code(arguments: dict) -> Sequence[TextContent]:
    args = RunCodeInput(**arguments)
    
    python_exe = sys.executable
    if not python_exe or not os.path.exists(python_exe):
        python_exe = "python"
    
    temp_file = None
    try:
        temp_id = uuid.uuid4().hex[:8]
        temp_dir = tempfile.gettempdir()
        temp_file = os.path.join(temp_dir, f"mcp_code_{temp_id}.py")
        
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(args.code)
        
        proc = await asyncio.create_subprocess_exec(
            python_exe, temp_file,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), 
                timeout=args.timeout
            )
            stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
            stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return [
                TextContent(
                    type="text",
                    text=f"Execution timed out after {args.timeout} seconds"
                )
            ]
        
        output_parts = []
        
        if stdout:
            output_parts.append(f"[stdout]\n{stdout}")
        
        if stderr:
            output_parts.append(f"[stderr]\n{stderr}")
        
        if not output_parts:
            output_parts.append("(No output produced)")
        
        output_parts.append(f"\n[Exit code: {proc.returncode}]")
        
        return [TextContent(type="text", text="".join(output_parts))]
    
    except FileNotFoundError:
        return [
            TextContent(
                type="text",
                text="Python is not installed or not found in PATH. Please install Python to use the run_code tool."
            )
        ]
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error executing code: {str(e)}"
            )
        ]
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except:
                pass


async def _run_shell_command(arguments: dict) -> Sequence[TextContent]:
    args = RunShellInput(**arguments)
    command = args.command
    
    is_windows = sys.platform == 'win32'
    
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), 
                timeout=args.timeout
            )
            stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ""
            stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ""
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return [
                TextContent(
                    type="text",
                    text=f"Command timed out after {args.timeout} seconds"
                )
            ]
        
        output_parts = []
        
        if stdout:
            output_parts.append(f"[stdout]\n{stdout}")
        
        if stderr:
            output_parts.append(f"[stderr]\n{stderr}")
        
        if not output_parts:
            output_parts.append("(No output produced)")
        
        output_parts.append(f"\n[Exit code: {proc.returncode}]")
        
        return [TextContent(type="text", text="".join(output_parts))]
    
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error executing command: {str(e)}"
            )
        ]
