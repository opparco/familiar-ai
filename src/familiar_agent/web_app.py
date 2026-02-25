"""Web UI for familiar-ai - Flask + SocketIO version."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from threading import Thread

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

from .agent import EmbodiedAgent
from .config import AgentConfig
from .desires import DesireSystem
from ._i18n import _t

logger = logging.getLogger(__name__)

# Flask app setup - use local templates and static files
template_dir = Path(__file__).parent / "templates"
static_dir = Path(__file__).parent / "static"

app = Flask(
    __name__,
    template_folder=str(template_dir),
    static_folder=str(static_dir),
    static_url_path="/static"
)
app.config["SECRET_KEY"] = "familiar-ai-secret"  # SocketIO requires this
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Global agent instance (initialized on first request)
_agent: EmbodiedAgent | None = None
_desires: DesireSystem | None = None
_config: AgentConfig | None = None


def get_agent() -> tuple[EmbodiedAgent, DesireSystem]:
    """Get or initialize agent and desires."""
    global _agent, _desires, _config
    if _agent is None:
        _config = AgentConfig()
        if not _config.api_key:
            raise RuntimeError("API_KEY not set in environment")
        _agent = EmbodiedAgent(_config)
        _desires = DesireSystem()
    return _agent, _desires


@app.route("/")
def index():
    """Main page with avatar UI."""
    try:
        config = AgentConfig()
        return render_template(
            "index.html",
            config={
                "avatar_name": config.agent_name,
                "avatar_full_name": config.agent_name,
                "companion_name": config.companion_name,
                "typewriter_delay": 30,  # ms - faster for familiar-ai
                "beep_frequency": 800,
                "beep_duration": 30,
                "beep_volume": 0.05,
                "beep_volume_end": 0.01,
            }
        )
    except Exception as e:
        logger.error(f"Error rendering index: {e}")
        return f"Error: {e}", 500


@socketio.on("connect")
def handle_connect():
    """Handle client connection."""
    logger.info("Client connected")
    emit("connected", {"status": "ok", "agent_name": _config.agent_name if _config else "AI"})


@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection."""
    logger.info("Client disconnected")


@socketio.on("chat")
def handle_chat(data):
    """Handle chat message from user."""
    user_input = data.get("message", "").strip()
    if not user_input:
        return

    try:
        agent, desires = get_agent()
    except RuntimeError as e:
        emit("error", {"message": str(e)})
        return

    # Emit user message to display
    emit("user_message", {
        "sender": agent.config.companion_name,
        "message": user_input
    }, broadcast=True)

    # Run agent in background thread to not block
    def run_agent():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        actions_log = []
        text_buffer = []

        def on_action(name: str, tool_input: dict) -> None:
            """Callback when agent uses a tool."""
            icon = _get_action_icon(name)
            label = _format_action(name, tool_input)
            socketio.emit("action", {
                "name": name,
                "icon": icon,
                "label": label,
                "input": tool_input
            })
            actions_log.append({"name": name, "input": tool_input})

        def on_text(chunk: str) -> None:
            """Callback for streaming text."""
            text_buffer.append(chunk)
            socketio.emit("text_chunk", {"chunk": chunk})

        try:
            loop.run_until_complete(agent.run(
                user_input,
                on_action=on_action,
                on_text=on_text,
                desires=desires,
            ))
            # Signal completion
            socketio.emit("response_complete", {
                "full_text": "".join(text_buffer),
                "actions": actions_log
            })
            # Update desires
            if desires.curiosity_target:
                socketio.emit("status", {
                    "message": f"[気になること: {desires.curiosity_target}]"
                })
            desires.satisfy("greet_companion")
        except Exception as e:
            logger.error(f"Agent error: {e}")
            socketio.emit("error", {"message": f"Error: {str(e)}"})
        finally:
            loop.close()

    # Start agent in background thread
    thread = Thread(target=run_agent)
    thread.daemon = True
    thread.start()


@socketio.on("clear_history")
def handle_clear():
    """Clear conversation history."""
    try:
        agent, _ = get_agent()
        agent.clear_history()
        emit("history_cleared", {})
    except Exception as e:
        emit("error", {"message": str(e)})


def _get_action_icon(name: str) -> str:
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


def _format_action(name: str, tool_input: dict) -> str:
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


def run_web_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Run the web server."""
    # Initialize agent on startup to catch config errors early
    try:
        get_agent()
        print(f"\n🌐 Web UI: http://{host}:{port}")
        print("Press Ctrl+C to stop\n")
    except RuntimeError as e:
        print(f"\n❌ Error: {e}")
        print("Please set API_KEY and PLATFORM in your .env file\n")
        raise

    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    run_web_server(debug=True)
