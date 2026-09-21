import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVERS_DIR = Path(__file__).parent

SERVER_SCRIPTS = {
    "flights": SERVERS_DIR / "flights_server.py",
    "hotels": SERVERS_DIR / "hotels_server.py",
    "guides": SERVERS_DIR / "guides_server.py",
}


class MCPToolClient:
    """Spawns each provider's MCP server as its own subprocess (stdio transport) and
    keeps a persistent ClientSession per server for the app's lifetime — the graph
    nodes call tools by name through this client rather than importing provider
    functions directly, matching "the AI simply calls tools, no hardcoding."
    """

    def __init__(self):
        self._stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}

    async def start(self):
        for server_name, script_path in SERVER_SCRIPTS.items():
            # Pass the environment through so the servers see .env keys and WAYFINDER_OFFLINE
            params = StdioServerParameters(command=sys.executable, args=[str(script_path)], env=dict(os.environ))
            read, write = await self._stack.enter_async_context(stdio_client(params))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[server_name] = session

    async def call(self, server_name: str, tool_name: str, arguments: dict) -> dict:
        session = self._sessions[server_name]
        result = await session.call_tool(tool_name, arguments=arguments)
        if result.isError:
            text = result.content[0].text if result.content else "unknown MCP tool error"
            raise RuntimeError(f"MCP tool '{tool_name}' on '{server_name}' failed: {text}")
        return json.loads(result.content[0].text)

    async def stop(self):
        await self._stack.aclose()
