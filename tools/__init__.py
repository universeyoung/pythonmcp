<<<<<<< HEAD
=======
from . import coderunner
>>>>>>> feat-add-mcp-tools-hKdaHC
from . import everything
from . import fetch
from . import filesystem
from . import memory
from . import sequentialthinking
from . import websearch

<<<<<<< HEAD
_modules = [everything, fetch, filesystem, memory, sequentialthinking, websearch]
=======
_modules = [coderunner, everything, fetch, filesystem, memory, sequentialthinking, websearch]
>>>>>>> feat-add-mcp-tools-hKdaHC


def get_all_tools() -> list:
    tools = []
    for module in _modules:
        tools.extend(module.get_tools())
    return tools


async def handle_tool(name: str, arguments: dict):
    for module in _modules:
        result = await module.handle_tool(name, arguments)
        if result is not None:
            return result
    raise ValueError(f"Unknown tool: {name}")


<<<<<<< HEAD
__all__ = ["get_all_tools", "handle_tool"]
=======
__all__ = ["get_all_tools", "handle_tool"]
>>>>>>> feat-add-mcp-tools-hKdaHC
