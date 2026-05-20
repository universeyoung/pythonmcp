import json
import os
import pathlib
from typing import Sequence

from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from pydantic import BaseModel, Field


def _get_allowed_directories() -> list[str]:
    dirs = os.environ.get("MCP_ALLOWED_DIRECTORIES", "")
    if dirs:
        return [d.strip() for d in dirs.split(";") if d.strip()]
    default_dirs = [
        str(pathlib.Path.home()),
        r"C:\Users",
        r"D:\chenqi",
    ]
    existing = [d for d in default_dirs if pathlib.Path(d).exists()]
    return existing if existing else [str(pathlib.Path.home())]


def _validate_path(requested_path: str, allowed_dirs: list[str]) -> pathlib.Path:
    path = pathlib.Path(requested_path).expanduser().resolve()
    for allowed in allowed_dirs:
        allowed_path = pathlib.Path(allowed).expanduser().resolve()
        try:
            path.relative_to(allowed_path)
            return path
        except ValueError:
            continue
    raise ValueError(f"Access denied - path outside allowed directories: {path}")


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


class ReadFileInput(BaseModel):
    path: str = Field(description="Path to the file to read")
    tail: int | None = Field(default=None, description="Return only the last N lines")
    head: int | None = Field(default=None, description="Return only the first N lines")


class ReadMultipleFilesInput(BaseModel):
    paths: list[str] = Field(description="Array of file paths to read", min_length=1)


class WriteFileInput(BaseModel):
    path: str = Field(description="Path to the file to write")
    content: str = Field(description="Content to write to the file")


class EditOperation(BaseModel):
    oldText: str = Field(description="Text to search for - must match exactly")
    newText: str = Field(description="Text to replace with")


class EditFileInput(BaseModel):
    path: str = Field(description="Path to the file to edit")
    edits: list[EditOperation] = Field(description="List of edit operations")
    dryRun: bool = Field(default=False, description="Preview changes without applying")


class CreateDirectoryInput(BaseModel):
    path: str = Field(description="Path to the directory to create")


class ListDirectoryInput(BaseModel):
    path: str = Field(description="Path to the directory to list")


class DirectoryTreeInput(BaseModel):
    path: str = Field(description="Path to the root directory")
    excludePatterns: list[str] = Field(default_factory=list, description="Patterns to exclude")


class SearchFilesInput(BaseModel):
    path: str = Field(description="Root path to search from")
    pattern: str = Field(description="Glob pattern to match")
    excludePatterns: list[str] = Field(default_factory=list, description="Patterns to exclude")


class MoveFileInput(BaseModel):
    source: str = Field(description="Source path")
    destination: str = Field(description="Destination path")


class GetFileInfoInput(BaseModel):
    path: str = Field(description="Path to the file or directory")


def get_tools() -> list[Tool]:
    return [
        Tool(
            name="read_text_file",
            description="Read the complete contents of a file as text. Use 'head' for first N lines or 'tail' for last N lines. Only works within allowed directories.",
            inputSchema=ReadFileInput.model_json_schema(),
        ),
        Tool(
            name="read_multiple_files",
            description="Read the contents of multiple files simultaneously. More efficient than reading one by one.",
            inputSchema=ReadMultipleFilesInput.model_json_schema(),
        ),
        Tool(
            name="write_file",
            description="Create a new file or completely overwrite an existing file. Only works within allowed directories.",
            inputSchema=WriteFileInput.model_json_schema(),
        ),
        Tool(
            name="edit_file",
            description="Make line-based edits to a text file. Each edit replaces exact text with new content. Returns a diff of changes.",
            inputSchema=EditFileInput.model_json_schema(),
        ),
        Tool(
            name="create_directory",
            description="Create a new directory or ensure a directory exists. Creates nested directories in one operation.",
            inputSchema=CreateDirectoryInput.model_json_schema(),
        ),
        Tool(
            name="list_directory",
            description="Get a detailed listing of all files and directories in a specified path.",
            inputSchema=ListDirectoryInput.model_json_schema(),
        ),
        Tool(
            name="directory_tree",
            description="Get a recursive tree view of files and directories as a JSON structure.",
            inputSchema=DirectoryTreeInput.model_json_schema(),
        ),
        Tool(
            name="search_files",
            description="Recursively search for files and directories matching a glob pattern.",
            inputSchema=SearchFilesInput.model_json_schema(),
        ),
        Tool(
            name="move_file",
            description="Move or rename files and directories. Both source and destination must be within allowed directories.",
            inputSchema=MoveFileInput.model_json_schema(),
        ),
        Tool(
            name="get_file_info",
            description="Retrieve detailed metadata about a file or directory.",
            inputSchema=GetFileInfoInput.model_json_schema(),
        ),
        Tool(
            name="list_allowed_directories",
            description="Returns the list of directories that this server is allowed to access.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


async def handle_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource] | None:
    allowed_dirs = _get_allowed_directories()

    match name:
        case "read_text_file":
            args = ReadFileInput(**arguments)
            valid_path = _validate_path(args.path, allowed_dirs)
            if not valid_path.is_file():
                raise ValueError(f"Not a file: {args.path}")
            content = valid_path.read_text(encoding="utf-8")
            if args.tail:
                lines = content.splitlines()
                content = "\n".join(lines[-args.tail :])
            elif args.head:
                lines = content.splitlines()
                content = "\n".join(lines[: args.head])
            return [TextContent(type="text", text=content)]

        case "read_multiple_files":
            args = ReadMultipleFilesInput(**arguments)
            results = []
            for file_path in args.paths:
                try:
                    valid_path = _validate_path(file_path, allowed_dirs)
                    content = valid_path.read_text(encoding="utf-8")
                    results.append(f"{file_path}:\n{content}\n")
                except Exception as e:
                    results.append(f"{file_path}: Error - {e}")
            return [TextContent(type="text", text="\n---\n".join(results))]

        case "write_file":
            args = WriteFileInput(**arguments)
            valid_path = _validate_path(args.path, allowed_dirs)
            valid_path.parent.mkdir(parents=True, exist_ok=True)
            valid_path.write_text(args.content, encoding="utf-8")
            return [TextContent(type="text", text=f"Successfully wrote to {args.path}")]

        case "edit_file":
            args = EditFileInput(**arguments)
            valid_path = _validate_path(args.path, allowed_dirs)
            if not valid_path.is_file():
                raise ValueError(f"Not a file: {args.path}")
            content = valid_path.read_text(encoding="utf-8")
            original = content
            for edit in args.edits:
                if edit.oldText in content:
                    content = content.replace(edit.oldText, edit.newText, 1)
                else:
                    raise ValueError(f"Could not find text to replace:\n{edit.oldText}")
            diff_lines = []
            old_lines = original.splitlines()
            new_lines = content.splitlines()
            max_len = max(len(old_lines), len(new_lines))
            for i in range(max_len):
                old = old_lines[i] if i < len(old_lines) else None
                new = new_lines[i] if i < len(new_lines) else None
                if old != new:
                    diff_lines.append(f"  Line {i+1}:")
                    if old is not None:
                        diff_lines.append(f"  - {old}")
                    if new is not None:
                        diff_lines.append(f"  + {new}")
            diff_text = "\n".join(diff_lines) if diff_lines else "No changes"
            if not args.dryRun:
                valid_path.write_text(content, encoding="utf-8")
            return [TextContent(type="text", text=f"```diff\n{diff_text}\n```")]

        case "create_directory":
            args = CreateDirectoryInput(**arguments)
            valid_path = _validate_path(args.path, allowed_dirs)
            valid_path.mkdir(parents=True, exist_ok=True)
            return [TextContent(type="text", text=f"Successfully created directory {args.path}")]

        case "list_directory":
            args = ListDirectoryInput(**arguments)
            valid_path = _validate_path(args.path, allowed_dirs)
            if not valid_path.is_dir():
                raise ValueError(f"Not a directory: {args.path}")
            entries = []
            for entry in sorted(valid_path.iterdir()):
                prefix = "[DIR]" if entry.is_dir() else "[FILE]"
                entries.append(f"{prefix} {entry.name}")
            return [TextContent(type="text", text="\n".join(entries) or "(empty)")]

        case "directory_tree":
            args = DirectoryTreeInput(**arguments)
            root = _validate_path(args.path, allowed_dirs)

            def build_tree(current: pathlib.Path, exclude_patterns: list[str]) -> list[dict]:
                result = []
                try:
                    for entry in sorted(current.iterdir()):
                        rel = str(entry.relative_to(root))
                        if any(entry.match(p) or rel.startswith(p.rstrip("/")) for p in exclude_patterns):
                            continue
                        node = {"name": entry.name, "type": "directory" if entry.is_dir() else "file"}
                        if entry.is_dir():
                            node["children"] = build_tree(entry, exclude_patterns)
                        result.append(node)
                except PermissionError:
                    pass
                return result

            tree = build_tree(root, args.excludePatterns)
            return [TextContent(type="text", text=json.dumps(tree, indent=2))]

        case "search_files":
            args = SearchFilesInput(**arguments)
            root = _validate_path(args.path, allowed_dirs)
            results = []
            for match in root.rglob(args.pattern):
                results.append(str(match))
            return [TextContent(type="text", text="\n".join(results) or "No matches found")]

        case "move_file":
            args = MoveFileInput(**arguments)
            source = _validate_path(args.source, allowed_dirs)
            dest = _validate_path(args.destination, allowed_dirs)
            source.rename(dest)
            return [TextContent(type="text", text=f"Successfully moved {args.source} to {args.destination}")]

        case "get_file_info":
            args = GetFileInfoInput(**arguments)
            valid_path = _validate_path(args.path, allowed_dirs)
            stat = valid_path.stat()
            info = {
                "path": str(valid_path),
                "size": _format_size(stat.st_size),
                "size_bytes": stat.st_size,
                "is_directory": valid_path.is_dir(),
                "is_file": valid_path.is_file(),
                "created": stat.st_ctime,
                "modified": stat.st_mtime,
                "accessed": stat.st_atime,
            }
            return [TextContent(type="text", text=json.dumps(info, indent=2))]

        case "list_allowed_directories":
            return [TextContent(type="text", text="Allowed directories:\n" + "\n".join(allowed_dirs))]

        case _:
            return None