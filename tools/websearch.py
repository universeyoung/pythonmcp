from typing import Sequence

from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from pydantic import BaseModel, Field


class WebSearchInput(BaseModel):
    query: str = Field(description="Search query string")
    max_results: int = Field(default=10, description="Maximum number of results to return", ge=1, le=20)


class WebFetchInput(BaseModel):
    url: str = Field(description="URL to fetch content from")
    max_length: int = Field(default=5000, description="Maximum number of characters to return", ge=100, le=50000)


def _search_duckduckgo(query: str, max_results: int = 10) -> list[dict]:
    try:
        from duckduckgo_search import DDGS

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(
                    {
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", ""),
                    }
                )
        return results
    except ImportError:
        raise ImportError(
            "duckduckgo-search package is required. Install with: pip install duckduckgo-search"
        )
    except Exception as e:
        raise RuntimeError(f"Search failed: {e}")


def get_tools() -> list[Tool]:
    return [
        Tool(
            name="web_search",
            description="Search the web using DuckDuckGo and return relevant results. "
            "Use this tool to find current information, documentation, news, and other online content. "
            "Returns title, URL, and snippet for each result.",
            inputSchema=WebSearchInput.model_json_schema(),
        ),
        Tool(
            name="web_fetch",
            description="Fetch and read the content of a web page by URL. "
            "Returns the text content of the page. Useful for reading documentation, "
            "articles, or any web page after finding it via web_search.",
            inputSchema=WebFetchInput.model_json_schema(),
        ),
    ]


async def handle_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource] | None:
    match name:
        case "web_search":
            args = WebSearchInput(**arguments)
            results = _search_duckduckgo(args.query, args.max_results)
            if not results:
                return [TextContent(type="text", text=f"No results found for: {args.query}")]
            formatted = []
            for i, r in enumerate(results, 1):
                formatted.append(f"{i}. {r['title']}\n   URL: {r['href']}\n   {r['body']}")
            return [TextContent(type="text", text="\n\n".join(formatted))]

        case "web_fetch":
            args = WebFetchInput(**arguments)
            from httpx import AsyncClient, HTTPError

            async with AsyncClient() as client:
                try:
                    response = await client.get(
                        args.url,
                        follow_redirects=True,
                        headers={"User-Agent": "MCP-WebSearch/1.0"},
                        timeout=30,
                    )
                except HTTPError as e:
                    return [TextContent(type="text", text=f"Failed to fetch {args.url}: {e!r}")]

                if response.status_code >= 400:
                    return [
                        TextContent(
                            type="text",
                            text=f"Failed to fetch {args.url} - status code {response.status_code}",
                        )
                    ]

                content_type = response.headers.get("content-type", "")
                text = response.text

                if "text/html" in content_type or "<html" in text[:200].lower():
                    try:
                        import markdownify
                        import readabilipy.simple_json

                        ret = readabilipy.simple_json.simple_json_from_html_string(
                            text, use_readability=True
                        )
                        if ret.get("content"):
                            text = markdownify.markdownify(
                                ret["content"], heading_style=markdownify.ATX
                            )
                    except Exception:
                        pass

                if len(text) > args.max_length:
                    text = text[: args.max_length] + "\n\n<content truncated>"

                return [TextContent(type="text", text=f"Contents of {args.url}:\n\n{text}")]

        case _:
            return None