from . import coderunner
from . import everything
from . import fetch
from . import filesystem
from . import memory
from . import sequentialthinking
from . import websearch

_modules = [coderunner, everything, fetch, filesystem, memory, sequentialthinking, websearch]

_cached_tools: list | None = None


def get_all_tools() -> list:
    global _cached_tools
    if _cached_tools is None:
        _cached_tools = []
        for module in _modules:
            _cached_tools.extend(module.get_tools())
    return _cached_tools


async def handle_tool(name: str, arguments: dict):
    for module in _modules:
        result = await module.handle_tool(name, arguments)
        if result is not None:
            return result
    raise ValueError(f"Unknown tool: {name}")


__all__ = ["get_all_tools", "handle_tool"]
