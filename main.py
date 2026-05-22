import sys
import os
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')
import argparse
import asyncio
import contextlib
import logging
from typing import AsyncIterator, Sequence

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

from tools import get_all_tools, handle_tool

logger = logging.getLogger(__name__)

_cached_tools: list[Tool] | None = None


def get_cached_tools() -> list[Tool]:
    global _cached_tools
    if _cached_tools is None:
        _cached_tools = get_all_tools()
    return _cached_tools


def create_server() -> Server:
    server = Server("pythonmcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return get_cached_tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        return await handle_tool(name, arguments)

    return server


async def serve_sse(host: str, port: int):
    from starlette.applications import Starlette
    from starlette.routing import Mount
    import uvicorn

    sse = SseServerTransport("/messages/")

    async def sse_asgi(scope, receive, send):
        async with sse.connect_sse(
            scope, receive, send
        ) as (read_stream, write_stream):
            server = create_server()
            await server.run(read_stream, write_stream, server.create_initialization_options())

    async def messages_asgi(scope, receive, send):
        await sse.handle_post_message(scope, receive, send)

    app = Starlette(
        routes=[
            Mount("/sse", app=sse_asgi),
            Mount("/messages/", app=messages_asgi),
        ]
    )

    # 新增 log_config=None
    config = uvicorn.Config(app, host=host, port=port, log_level="info", use_colors=False, log_config=None)
    http_server = uvicorn.Server(config)
    logger.info(f"SSE server listening on http://{host}:{port}/sse")
    await http_server.serve()


async def serve_streamable_http(host: str, port: int):
    from starlette.applications import Starlette
    from starlette.routing import Mount
    import uvicorn

    server = create_server()
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=False,
        request_timeout=300,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    async def mcp_asgi(scope, receive, send):
        await session_manager.handle_request(scope, receive, send)

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Mount("/mcp", app=mcp_asgi),
        ],
    )

    config = uvicorn.Config(
        app, 
        host=host, 
        port=port, 
        log_level="info", 
        use_colors=False, 
        log_config=None,
        timeout_keep_alive=60,
        limit_concurrency=100,
    )
    http_server = uvicorn.Server(config)
    logger.info(f"Streamable HTTP server listening on http://{host}:{port}/mcp")
    await http_server.serve()


async def serve_stdio():
    from mcp.server.stdio import stdio_server

    server = create_server()
    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        logger.info("STDIO server running")
        await server.run(read_stream, write_stream, options)


def main():
    parser = argparse.ArgumentParser(description="Python MCP Server with multiple tools")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="streamable-http",  # ✅ 只改了这一行！原来的stdio改成这个
        help="Transport method (default: streamable-http)",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("MCP_HOST", "0.0.0.0"),
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("MCP_PORT", "3001")),
        help="Port to bind to (default: 3001)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("MCP_LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )

    logger.info(f"Starting PythonMCP server with transport: {args.transport}")
    
    logger.info("Pre-loading tools...")
    tools = get_cached_tools()
    logger.info(f"Loaded {len(tools)} tools")

    if args.transport == "sse":
        asyncio.run(serve_sse(args.host, args.port))
    elif args.transport == "streamable-http":
        asyncio.run(serve_streamable_http(args.host, args.port))
    else:
        asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()