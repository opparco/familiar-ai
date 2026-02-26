"""CLI client for the familiar-ai WebSocket server."""

from __future__ import annotations

import asyncio
import json
import sys
import argparse

try:
    import aioconsole
except ImportError:
    print("aioconsole is not installed. Run: uv add aioconsole")
    sys.exit(1)

import websockets
from websockets.exceptions import ConnectionClosed

# ANSI color codes
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"


class FamiliarCLI:
    """Interactive CLI client for familiar-ai."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.agent_name = "FAMILIAR"
        self.companion_name = "YOU"
        # Signals that the current agent response is finished
        self._response_done = asyncio.Event()
        self._streaming = False  # True while agent text is streaming

    # ------------------------------------------------------------------
    # Receive loop
    # ------------------------------------------------------------------

    async def _receive_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        try:
            async for raw in ws:
                self._handle_message(json.loads(raw))
        except ConnectionClosed:
            print(f"\n{_DIM}[server closed the connection]{_RESET}")
            self._response_done.set()

    def _handle_message(self, msg: dict) -> None:
        msg_type: str = msg.get("type", "")
        data: dict = msg.get("data") or {}

        if msg_type == "connected":
            self.agent_name = data.get("agent_name", self.agent_name)
            print(f"{_DIM}[connected — agent: {self.agent_name}]{_RESET}", flush=True)

        elif msg_type == "text_chunk":
            chunk = data.get("chunk", "")
            if not self._streaming:
                # Print agent prefix before the first chunk
                print(f"\n{_CYAN}{_BOLD}{self.agent_name}>{_RESET} ", end="", flush=True)
                self._streaming = True
            print(chunk, end="", flush=True)

        elif msg_type == "action":
            icon = data.get("icon", "⚙️")
            label = data.get("label") or data.get("name", "")
            print(f"\n{_DIM}  {icon} {label}{_RESET}", end="", flush=True)

        elif msg_type == "response_complete":
            if self._streaming:
                print()  # newline after streamed text
                self._streaming = False
            self._response_done.set()

        elif msg_type == "error":
            if self._streaming:
                print()
                self._streaming = False
            print(f"\n{_RED}[error] {data.get('message', '')}{_RESET}", flush=True)
            self._response_done.set()

        elif msg_type == "history_cleared":
            print(f"{_DIM}[history cleared]{_RESET}", flush=True)
            self._response_done.set()

        elif msg_type == "status":
            print(f"\n{_DIM}{data.get('message', '')}{_RESET}", flush=True)

        else:
            # Unknown message — ignore silently
            pass

    # ------------------------------------------------------------------
    # Input loop
    # ------------------------------------------------------------------

    async def _input_loop(self, ws: websockets.WebSocketClientProtocol) -> None:
        prompt = f"{_YELLOW}{self.companion_name}>{_RESET} "
        print(
            f"{_DIM}Type a message and press Enter. /clear — clear history, /quit — exit.{_RESET}\n"
        )
        while True:
            try:
                line: str = await aioconsole.ainput(prompt)
            except EOFError:
                break

            line = line.strip()
            if not line:
                continue

            if line in ("/quit", "/exit", "/q"):
                break

            if line == "/clear":
                self._response_done.clear()
                await ws.send(json.dumps({"type": "clear_history", "data": None}))
                await self._response_done.wait()
                continue

            if line.startswith("/"):
                print(f"{_DIM}Unknown command: {line}. Try /clear or /quit.{_RESET}")
                continue

            # Regular chat message
            self._response_done.clear()
            await ws.send(json.dumps({"type": "chat", "data": {"message": line}}))
            await self._response_done.wait()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        print(f"Connecting to {self.url} …")
        try:
            async with websockets.connect(self.url, ping_interval=30) as ws:
                recv_task = asyncio.create_task(self._receive_loop(ws))
                input_task = asyncio.create_task(self._input_loop(ws))
                _done, pending = await asyncio.wait(
                    [recv_task, input_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for t in pending:
                    t.cancel()
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass
        except (ConnectionRefusedError, OSError) as e:
            print(f"{_RED}Could not connect: {e}{_RESET}")
            sys.exit(1)

        print(f"\n{_DIM}[disconnected]{_RESET}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="familiar-ai CLI client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--url", default=None, help="WebSocket URL (overrides --host/--port)")
    parser.add_argument("--host", default="localhost", help="Server hostname")
    parser.add_argument("--port", type=int, default=5000, help="Server port")
    args = parser.parse_args()

    url = args.url or f"ws://{args.host}:{args.port}/ws"
    client = FamiliarCLI(url)

    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        print(f"\n{_DIM}Bye!{_RESET}")
