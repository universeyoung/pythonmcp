from typing import Sequence
from urllib.parse import urlparse, urlunparse

import markdownify
import readabilipy.simple_json
from mcp.shared.exceptions import McpError
from mcp.types import (
    ErrorData,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    INVALID_PARAMS,
    INTERNAL_ERROR,
)
from protego import Protego
from pydantic import BaseModel, Field, AnyUrl

DEFAULT_USER_AGENT = "ModelContextProtocol/1.0 (+https://github.com/modelcontextprotocol/servers)"


def extract_content_from_html(html: str) -> str:
    ret = readabilipy.simple_json.simple_json_from_html_string(html, use_readability=True)
    if not ret["content"]:
        return "<error>Page failed to be simplified from HTML</error>"
    content = markdownify.markdownify(ret["content"], heading_style=markdownify.ATX)
    return content


def get_robots_txt_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))


async def check_may_fetch_url(url: str, user_agent: str) -> None:
    from httpx import AsyncClient, HTTPError

    robot_txt_url = get_robots_txt_url(url)
    async with AsyncClient() as client:
        try:
            response = await client.get(
                robot_txt_url,
                follow_redirects=True,
                headers={"User-Agent": user_agent},
            )
        except HTTPError:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"Failed to fetch robots.txt {robot_txt_url} due to a connection issue",
                )
            )
        if response.status_code in (401, 403):
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"When fetching robots.txt ({robot_txt_url}), received status {response.status_code} so assuming that fetching is not allowed",
                )
            )
        elif 400 <= response.status_code < 500:
            return
        robot_txt = response.text
    processed_robot_txt = "\n".join(
        line for line in robot_txt.splitlines() if not line.strip().startswith("#")
    )
    robot_parser = Protego.parse(processed_robot_txt)
    if not robot_parser.can_fetch(str(url), user_agent):
        raise McpError(
            ErrorData(
                code=INTERNAL_ERROR,
                message=f"The sites robots.txt ({robot_txt_url}) specifies that fetching of this page is not allowed",
            )
        )


async def fetch_url(url: str, user_agent: str, force_raw: bool = False) -> tuple[str, str]:
    from httpx import AsyncClient, HTTPError

    async with AsyncClient() as client:
        try:
            response = await client.get(
                url,
                follow_redirects=True,
                headers={"User-Agent": user_agent},
                timeout=30,
            )
        except HTTPError as e:
            raise McpError(ErrorData(code=INTERNAL_ERROR, message=f"Failed to fetch {url}: {e!r}"))
        if response.status_code >= 400:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"Failed to fetch {url} - status code {response.status_code}",
                )
            )
        page_raw = response.text

    content_type = response.headers.get("content-type", "")
    is_page_html = "<html" in page_raw[:100] or "text/html" in content_type or not content_type

    if is_page_html and not force_raw:
        return extract_content_from_html(page_raw), ""

    return (
        page_raw,
        f"Content type {content_type} cannot be simplified to markdown, but here is the raw content:\n",
    )


class FetchInput(BaseModel):
    url: AnyUrl = Field(description="URL to fetch")
    max_length: int = Field(default=5000, description="Maximum number of characters to return", gt=0, lt=1000000)
    start_index: int = Field(default=0, description="On return output starting at this character index", ge=0)
    raw: bool = Field(default=False, description="Get the actual HTML content without simplification")


def get_tools() -> list[Tool]:
    return [
        Tool(
            name="fetch",
            description="Fetches a URL from the internet and optionally extracts its contents as markdown. Grants internet access to fetch up-to-date information.",
            inputSchema=FetchInput.model_json_schema(),
        )
    ]


async def handle_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource] | None:
    if name != "fetch":
        return None

    try:
        args = FetchInput(**arguments)
    except ValueError as e:
        raise McpError(ErrorData(code=INVALID_PARAMS, message=str(e)))

    url = str(args.url)
    if not url:
        raise McpError(ErrorData(code=INVALID_PARAMS, message="URL is required"))

    user_agent = DEFAULT_USER_AGENT
    await check_may_fetch_url(url, user_agent)

    content, prefix = await fetch_url(url, user_agent, force_raw=args.raw)
    original_length = len(content)
    if args.start_index >= original_length:
        content = "<error>No more content available.</error>"
    else:
        truncated = content[args.start_index : args.start_index + args.max_length]
        if not truncated:
            content = "<error>No more content available.</error>"
        else:
            content = truncated
            actual_length = len(truncated)
            remaining = original_length - (args.start_index + actual_length)
            if actual_length == args.max_length and remaining > 0:
                next_start = args.start_index + actual_length
                content += f"\n\n<error>Content truncated. Call the fetch tool with a start_index of {next_start} to get more content.</error>"
    return [TextContent(type="text", text=f"{prefix}Contents of {url}:\n{content}")]