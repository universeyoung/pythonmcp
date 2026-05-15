import json
import os
import asyncio
from typing import Sequence

from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from pydantic import BaseModel, Field


class EchoInput(BaseModel):
    message: str = Field(description="The message to echo back")


class GetSumInput(BaseModel):
    a: float = Field(description="First number")
    b: float = Field(description="Second number")


class AnnotatedMessageInput(BaseModel):
    message: str = Field(description="The message to annotate")
    audience: list[str] = Field(default_factory=lambda: ["user"], description="Target audience roles")


class StructuredContentInput(BaseModel):
    content_type: str = Field(default="json", description="Type of structured content to return")


class LongRunningOperationInput(BaseModel):
    duration: float = Field(default=5.0, description="Duration in seconds for the simulated operation")


def get_tools() -> list[Tool]:
    return [
        Tool(
            name="echo",
            description="Echo back the input message. Useful for testing connectivity.",
            inputSchema=EchoInput.model_json_schema(),
        ),
        Tool(
            name="get_sum",
            description="Add two numbers together and return the sum.",
            inputSchema=GetSumInput.model_json_schema(),
        ),
        Tool(
            name="get_annotated_message",
            description="Return a message with audience annotations for role-based content.",
            inputSchema=AnnotatedMessageInput.model_json_schema(),
        ),
        Tool(
            name="get_env",
            description="Get environment variables. Returns all or specific ones.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific env var keys to retrieve. If empty, returns all.",
                    }
                },
            },
        ),
        Tool(
            name="get_structured_content",
            description="Return structured content in various formats.",
            inputSchema=StructuredContentInput.model_json_schema(),
        ),
        Tool(
            name="get_tiny_image",
            description="Return a tiny 1x1 pixel PNG image as base64.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="trigger_long_running_operation",
            description="Simulate a long-running operation with progress updates.",
            inputSchema=LongRunningOperationInput.model_json_schema(),
        ),
    ]


async def handle_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    match name:
        case "echo":
            args = EchoInput(**arguments)
            return [TextContent(type="text", text=f"Echo: {args.message}")]

        case "get_sum":
            args = GetSumInput(**arguments)
            result = args.a + args.b
            return [TextContent(type="text", text=str(result))]

        case "get_annotated_message":
            args = AnnotatedMessageInput(**arguments)
            content = {
                "message": args.message,
                "audience": args.audience,
            }
            return [TextContent(type="text", text=json.dumps(content, indent=2))]

        case "get_env":
            keys = arguments.get("keys", [])
            env_data = {}
            if keys:
                for key in keys:
                    env_data[key] = os.environ.get(key, "<not set>")
            else:
                env_data = dict(os.environ)
            return [TextContent(type="text", text=json.dumps(env_data, indent=2))]

        case "get_structured_content":
            args = StructuredContentInput(**arguments)
            match args.content_type:
                case "json":
                    data = {
                        "title": "Structured Content Example",
                        "items": [
                            {"id": 1, "name": "Item One", "value": 100},
                            {"id": 2, "name": "Item Two", "value": 200},
                            {"id": 3, "name": "Item Three", "value": 300},
                        ],
                        "metadata": {"total": 3, "version": "1.0"},
                    }
                case "table":
                    data = {
                        "headers": ["ID", "Name", "Value"],
                        "rows": [
                            [1, "Item One", 100],
                            [2, "Item Two", 200],
                            [3, "Item Three", 300],
                        ],
                    }
                case _:
                    data = {"message": f"Unknown content type: {args.content_type}"}
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        case "get_tiny_image":
            tiny_png_base64 = (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
            )
            return [
                ImageContent(type="image", data=tiny_png_base64, mimeType="image/png")
            ]

        case "trigger_long_running_operation":
            args = LongRunningOperationInput(**arguments)
            await asyncio.sleep(args.duration)
            return [
                TextContent(
                    type="text",
                    text=f"Long-running operation completed after {args.duration} seconds",
                )
            ]

        case _:
            return None