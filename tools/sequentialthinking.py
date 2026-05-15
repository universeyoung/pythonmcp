import json
from typing import Sequence

from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from pydantic import BaseModel, Field


class SequentialThinkingInput(BaseModel):
    thought: str = Field(description="Your current thinking step")
    nextThoughtNeeded: bool = Field(description="Whether another thought step is needed")
    thoughtNumber: int = Field(description="Current thought number", ge=1)
    totalThoughts: int = Field(description="Estimated total thoughts needed", ge=1)
    isRevision: bool | None = Field(default=None, description="Whether this revises previous thinking")
    revisesThought: int | None = Field(default=None, description="Which thought is being reconsidered", ge=1)
    branchFromThought: int | None = Field(default=None, description="Branching point thought number", ge=1)
    branchId: str | None = Field(default=None, description="Branch identifier")
    needsMoreThoughts: bool | None = Field(default=None, description="If more thoughts are needed")


class SequentialThinkingServer:
    def __init__(self):
        self._thought_history: list[dict] = []
        self._branches: dict[str, list[dict]] = {}

    def process_thought(self, input_data: dict) -> dict:
        thought_number = input_data.get("thoughtNumber", 0)
        total_thoughts = input_data.get("totalThoughts", 0)

        if thought_number > total_thoughts:
            total_thoughts = thought_number
            input_data["totalThoughts"] = total_thoughts

        self._thought_history.append(input_data)

        branch_id = input_data.get("branchId")
        if input_data.get("branchFromThought") and branch_id:
            if branch_id not in self._branches:
                self._branches[branch_id] = []
            self._branches[branch_id].append(input_data)

        return {
            "thoughtNumber": thought_number,
            "totalThoughts": total_thoughts,
            "nextThoughtNeeded": input_data.get("nextThoughtNeeded", False),
            "branches": list(self._branches.keys()),
            "thoughtHistoryLength": len(self._thought_history),
        }


_thinking_server = SequentialThinkingServer()


def get_tools() -> list[Tool]:
    return [
        Tool(
            name="sequentialthinking",
            description="A detailed tool for dynamic and reflective problem-solving through thoughts. "
            "This tool helps analyze problems through a flexible thinking process that can adapt and evolve. "
            "Each thought can build on, question, or revise previous insights as understanding deepens.\n\n"
            "When to use this tool:\n"
            "- Breaking down complex problems into steps\n"
            "- Planning and design with room for revision\n"
            "- Analysis that might need course correction\n"
            "- Problems where the full scope might not be clear initially\n"
            "- Problems that require a multi-step solution\n"
            "- Tasks that need to maintain context over multiple steps\n"
            "- Situations where irrelevant information needs to be filtered out\n\n"
            "Key features:\n"
            "- You can adjust total_thoughts up or down as you progress\n"
            "- You can question or revise previous thoughts\n"
            "- You can add more thoughts even after reaching what seemed like the end\n"
            "- You can express uncertainty and explore alternative approaches\n"
            "- Not every thought needs to build linearly - you can branch or backtrack\n"
            "- Generates a solution hypothesis\n"
            "- Verifies the hypothesis based on the Chain of Thought steps\n"
            "- Repeats the process until satisfied\n"
            "- Provides a correct answer",
            inputSchema=SequentialThinkingInput.model_json_schema(),
        )
    ]


async def handle_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource] | None:
    if name != "sequentialthinking":
        return None

    try:
        result = _thinking_server.process_thought(arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=json.dumps({"error": str(e), "status": "failed"}, indent=2),
            )
        ]