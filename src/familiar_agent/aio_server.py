"""Lightweight aiohttp server with WebSocket support."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Callable

from aiohttp import web, WSMsgType
from aiohttp.client_exceptions import ClientConnectionResetError

from .agent import EmbodiedAgent
from .config import AgentConfig
from .desires import DesireSystem
from ._i18n import _t

logger = logging.getLogger(__name__)

# Static files directory
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"


def get_action_icon(name: str) -> str:
    """Get icon for action name."""
    icons = {
        "see": "👀",
        "look_left": "◀️",
        "look_right": "▶️",
        "look_up": "🔼",
        "look_down": "🔽",
        "look_around": "🔄",
        "walk": "🚶",
        "say": "💬",
        "recall": "🧠",
        "remember": "📝",
    }
    return icons.get(name, "⚙️")


def format_action(name: str, tool_input: dict) -> str:
    """Format action for display."""
    if name in ("look_left", "look_right", "look_up", "look_down"):
        deg = tool_input.get("degrees", "")
        return f"{name}({deg}°)"
    if name == "say":
        text = tool_input.get("text", "")[:50]
        return f'「{text}…」'
    if name == "walk":
        direction = tool_input.get("direction", "?")
        duration = tool_input.get("duration", "")
        if duration:
            return f"{direction} {duration}s"
        return direction
    if name == "see":
        return "looking..."
    return name


class FamiliarServer:
    """Lightweight aiohttp server."""

    def __init__(
        self,
        agent: EmbodiedAgent,
        desires: DesireSystem,
        host: str = "0.0.0.0",
        port: int = 5000,
    ):
        self.agent = agent
        self.desires = desires
        self.host = host
        self.port = port
        self.app = web.Application()
        self.clients: set[web.WebSocketResponse] = set()
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup HTTP and WebSocket routes."""
        # Static files
        self.app.router.add_static("/static", STATIC_DIR, name="static")
        
        # Routes
        self.app.router.add_get("/", self.index_handler)
        self.app.router.add_get("/ws", self.websocket_handler)

    async def index_handler(self, request: web.Request) -> web.Response:
        """Serve the main HTML page."""
        try:
            html = (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")

            # Values for plain HTML parts
            avatar_full_name = self.agent.config.agent_name
            avatar_name_upper = avatar_full_name.upper()

            # Values for JavaScript config object
            app_config = {
                "typewriterDelay": 30,
                "avatarName": self.agent.config.agent_name,
                "companionName": self.agent.config.companion_name or "USER",
            }

            # Simple placeholder substitution
            html = html.replace("{{ avatar_full_name }}", avatar_full_name)
            html = html.replace("{{ avatar_name_upper }}", avatar_name_upper)
            html = html.replace("{{ app_config_json }}", json.dumps(app_config))

            return web.Response(text=html, content_type="text/html")
        except Exception as e:
            logger.error(f"Error serving index: {e}")
            return web.Response(text=f"Error: {e}", status=500)

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse(
            heartbeat=30.0,
            autoping=True,
        )
        await ws.prepare(request)
        
        self.clients.add(ws)
        logger.info(f"WebSocket client connected: {request.remote}")
        
        try:
            # Send connection confirmation
            await self._send_message(
                ws,
                "connected",
                {"status": "ok", "agent_name": self.agent.config.agent_name},
            )

            try:
                async for msg in ws:
                    if msg.type == WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            msg_type = data.get("type", "")
                            msg_data = data.get("data")
                            await self._handle_message(ws, msg_type, msg_data)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON: {msg.data}")
                            await self._send_error(ws, "Invalid JSON")
                        except Exception as e:
                            logger.error(f"Error handling message: {e}")
                            await self._send_error(ws, str(e))
                    elif msg.type == WSMsgType.ERROR:
                        logger.error(f"WebSocket error: {ws.exception()}")
            except (ClientConnectionResetError, ConnectionResetError):
                pass  # client disconnected abruptly while server sent ping/pong

        finally:
            self.clients.discard(ws)
            logger.info(f"WebSocket client disconnected: {request.remote}")

        return ws

    async def _handle_message(
        self, ws: web.WebSocketResponse, msg_type: str, data: dict | None
    ) -> None:
        """Handle incoming WebSocket message."""
        logger.debug(f"Received {msg_type}: {data}")

        if msg_type == "chat":
            await self._handle_chat(ws, data)
        elif msg_type == "clear_history":
            await self._handle_clear_history(ws)
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_chat(self, ws: web.WebSocketResponse, data: dict | None) -> None:
        """Handle chat message."""
        if not data:
            await self._send_error(ws, "No data provided")
            return

        user_input = data.get("message", "").strip()
        if not user_input:
            await self._send_error(ws, "Empty message")
            return

        # Broadcast user message to all clients
        await self._broadcast(
            "user_message",
            {"sender": self.agent.config.companion_name, "message": user_input},
        )

        # Process with agent
        try:
            actions_log = []
            text_buffer = []

            def on_action(name: str, tool_input: dict) -> None:
                """Callback when agent uses a tool."""
                icon = get_action_icon(name)
                label = format_action(name, tool_input)
                asyncio.create_task(
                    self._broadcast(
                        "action",
                        {"name": name, "icon": icon, "label": label, "input": tool_input},
                    )
                )
                actions_log.append({"name": name, "input": tool_input})

            def on_text(chunk: str) -> None:
                """Callback for streaming text."""
                text_buffer.append(chunk)
                asyncio.create_task(
                    self._broadcast("text_chunk", {"chunk": chunk})
                )

            await self.agent.run(
                user_input,
                on_action=on_action,
                on_text=on_text,
                desires=self.desires,
            )

            # Signal completion
            await self._broadcast(
                "response_complete",
                {"full_text": "".join(text_buffer), "actions": actions_log},
            )

            # Update desires
            if self.desires.curiosity_target:
                await self._broadcast(
                    "status",
                    {"message": f"[気になること: {self.desires.curiosity_target}]"},
                )
            self.desires.satisfy("greet_companion")

        except Exception as e:
            logger.error(f"Agent error: {e}")
            await self._send_error(ws, str(e))

    async def _handle_clear_history(self, ws: web.WebSocketResponse) -> None:
        """Handle clear history request."""
        try:
            self.agent.clear_history()
            await self._broadcast("history_cleared", {})
        except Exception as e:
            logger.error(f"Error clearing history: {e}")
            await self._send_error(ws, str(e))

    async def _send_message(
        self, ws: web.WebSocketResponse, msg_type: str, data: dict
    ) -> None:
        """Send message to specific client."""
        try:
            message = json.dumps({"type": msg_type, "data": data})
            await ws.send_str(message)
        except Exception as e:
            logger.error(f"Error sending message: {e}")

    async def _broadcast(self, msg_type: str, data: dict) -> None:
        """Broadcast message to all connected clients."""
        if not self.clients:
            return

        message = json.dumps({"type": msg_type, "data": data})
        disconnected: set[web.WebSocketResponse] = set()

        for ws in list(self.clients):
            try:
                # Skip sockets that are already closed or closing
                if ws.closed or ws.close_code is not None:
                    disconnected.add(ws)
                    continue

                await ws.send_str(message)
            except Exception as e:
                # Connection may close while we're broadcasting; that's expected.
                if "Cannot write to closing transport" in str(e):
                    logger.debug(f"Ignoring broadcast to closing transport: {e}")
                else:
                    logger.error(f"Error broadcasting: {e}")
                disconnected.add(ws)

        self.clients -= disconnected

    async def _send_error(self, ws: web.WebSocketResponse, message: str) -> None:
        """Send error message to client."""
        await self._send_message(ws, "error", {"message": message})

    async def start(self) -> None:
        """Start the server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info(f"🌐 Server started at http://{self.host}:{self.port}")
        logger.info(f"   WebSocket: ws://{self.host}:{self.port}/ws")

        # Keep running
        while True:
            await asyncio.sleep(3600)


def run_aio_server(
    host: str = "0.0.0.0",
    port: int = 5000,
    debug: bool = False,
) -> None:
    """Create and start aiohttp server."""
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    config = AgentConfig()
    if not config.api_key:
        raise RuntimeError("API_KEY not set in environment")

    agent = EmbodiedAgent(config)
    desires = DesireSystem()

    server = FamiliarServer(agent, desires, host, port)
    
    print(f"\n🌐 Server: http://{host}:{port}")
    print(f"   WebSocket: ws://{host}:{port}/ws")
    print("   Press Ctrl+C to stop\n")

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n\nShutting down...")
