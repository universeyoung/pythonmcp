import argparse
import asyncio
import contextlib
import logging
import os
import sys
from typing import AsyncIterator, Sequence

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

from tools import get_all_tools, handle_tool

logger = logging.getLogger(__name__)


def create_server() -> Server:
    server = Server("pythonmcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return get_all_tools()

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
        return await handle_tool(name, arguments)

    return server


async def serve_sse(host: str, port: int):
    from starlette.applications import Starlette
    from starlette.routing import Route
    import uvicorn

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            server = create_server()
            await server.run(read_stream, write_stream, server.create_initialization_options())

    async def handle_messages(request):
        await sse.handle_post_message(request.scope, request.receive, request._send)

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
        ]
    )

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    http_server = uvicorn.Server(config)
    logger.info(f"SSE server listening on http://{host}:{port}/sse")
    await http_server.serve()


async def serve_streamable_http(host: str, port: int):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.responses import Response
    import uvicorn

    server = create_server()
    session_manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=False,
    )

    @contextlib.asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    async def handle_mcp(request):
        await session_manager.handle_request(
            request.scope, request.receive, request._send
        )

    app = Starlette(
        lifespan=lifespan,
        routes=[
            Route("/mcp", endpoint=handle_mcp, methods=["POST", "GET", "DELETE"]),
        ],
    )

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
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
        default="stdio",
        help="Transport method (default: stdio)",
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

    if args.transport == "sse":
        asyncio.run(serve_sse(args.host, args.port))
    elif args.transport == "streamable-http":
        asyncio.run(serve_streamable_http(args.host, args.port))
    else:
        asyncio.run(serve_stdio())


if __name__ == "__main__":
    main()