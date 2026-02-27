# familiar-ai — WebSocket fork

This branch replaces the original Flask/SocketIO web server with a lightweight
**aiohttp + native WebSocket** stack, and adds a terminal CLI client.
It also adds **VOICEVOX** as a local TTS alternative to ElevenLabs.

> **Base:** `baseline-20260225` (upstream `main` as of 2026-02-25)

---

## What changed from upstream

| Area | Change |
|------|--------|
| Web server | Flask + Flask-SocketIO → **aiohttp + WebSocket** (`aio_server.py`) |
| JS client | `app.js` / `chat.js` → `app_ws.js` / `chat_ws.js` (native WebSocket API) |
| CLI client | New `familiar-client` command — terminal interface to the WebSocket server |
| TTS | Added **VOICEVOX** engine alongside ElevenLabs (`TTS_ENGINE=voicevox`) |
| Dependencies | Removed `flask`, `flask-socketio`, `python-socketio`; added `aiohttp`, `aioconsole` |

---

## Running modes

```bash
uv run familiar              # Textual TUI (unchanged from upstream)
uv run familiar --no-tui     # Plain REPL (unchanged from upstream)
uv run familiar --web        # WebSocket server on :5000  ← new default web mode
```

### Browser client

Open `http://localhost:5000` — the bundled web UI connects via WebSocket automatically.

### Terminal CLI client

```bash
uv run familiar-client                    # connect to localhost:5000
uv run familiar-client --host 192.168.1.x # remote server
uv run familiar-client --port 5001        # custom port
uv run familiar-client --url ws://host:port/ws  # full URL override
```

**Commands inside the client:**

| Input | Action |
|-------|--------|
| Any text + Enter | Send message to agent |
| `/clear` | Clear conversation history |
| `/quit` / `/exit` / `/q` | Exit |
| Ctrl-C | Exit |

The client **auto-reconnects** on disconnect with exponential backoff (1 s → 2 s → … → 30 s max).
Messages typed while disconnected are held until the connection is restored.

---

## WebSocket protocol

All frames are JSON.

### Client → Server

```jsonc
// Send a chat message
{ "type": "chat", "data": { "message": "Hello!" } }

// Clear conversation history
{ "type": "clear_history", "data": null }
```

### Server → Client

```jsonc
// Sent immediately after connection
{ "type": "connected", "data": { "status": "ok", "agent_name": "Yukine" } }

// Streaming text chunk
{ "type": "text_chunk", "data": { "chunk": "Hello" } }

// Tool call in progress
{ "type": "action", "data": { "name": "see", "icon": "👀", "label": "looking...", "input": {} } }

// Agent finished responding
{ "type": "response_complete", "data": { "full_text": "...", "actions": [...] } }

// History was cleared
{ "type": "history_cleared", "data": {} }

// Status / info message
{ "type": "status", "data": { "message": "..." } }

// Error
{ "type": "error", "data": { "message": "..." } }
```

---

## VOICEVOX TTS

[VOICEVOX](https://voicevox.hiroshiba.jp/) is a free, locally-running Japanese TTS engine.
Unlike ElevenLabs it requires no API key and audio plays back locally (no go2rtc needed).

**Setup:**

1. Download and launch the VOICEVOX engine (GUI app or engine-only build).
2. Set in `.env`:

```env
TTS_ENGINE=voicevox
VOICEVOX_URL=http://localhost:50021   # default VOICEVOX port
VOICEVOX_SPEAKER=3                    # speaker ID (3 = Zundamon normal)
```

Speaker IDs can be browsed at `http://localhost:50021/speakers` once the engine is running.

**ElevenLabs** is still the default (`TTS_ENGINE=elevenlabs`).
Switch to VOICEVOX for a fully offline, Japanese-optimised voice.

---

## Configuration reference

All settings via `.env` (copy from `.env.example`).

### Core (required)

| Variable | Default | Description |
|----------|---------|-------------|
| `PLATFORM` | `anthropic` | `anthropic` \| `gemini` \| `openai` \| `kimi` |
| `API_KEY` | — | API key for the chosen platform |

### Web server

| Variable | Default | Description |
|----------|---------|-------------|
| `WEB_HOST` | `0.0.0.0` | Bind address |
| `WEB_PORT` | `5000` | Listen port |

### TTS

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_ENGINE` | `elevenlabs` | `elevenlabs` \| `voicevox` |
| `ELEVENLABS_API_KEY` | — | ElevenLabs key |
| `ELEVENLABS_VOICE_ID` | *(default voice)* | ElevenLabs voice ID |
| `VOICEVOX_URL` | `http://localhost:50021` | VOICEVOX engine URL |
| `VOICEVOX_SPEAKER` | `3` | VOICEVOX speaker ID |

### Camera / hardware

| Variable | Description |
|----------|-------------|
| `CAMERA_HOST` | ONVIF camera IP |
| `CAMERA_USERNAME` / `CAMERA_PASSWORD` | Camera credentials |
| `CAMERA_ONVIF_PORT` | ONVIF port (default `2020`) |
| `TUYA_*` | Robot vacuum credentials (see `.env.example`) |

---

## Architecture notes

### aiohttp WebSocket server (`aio_server.py`)

- Single-file server; `FamiliarServer` holds agent + desire system + connected client set.
- All outbound messages go through `_broadcast()` which skips already-closed sockets gracefully.
- `ClientConnectionResetError` from abrupt client disconnect (during heartbeat ping/pong) is
  caught silently to avoid noisy error logs.
- Heartbeat: 30 s (`heartbeat=30.0, autoping=True`).

### CLI client (`cli_client.py`)

- `_input_loop` runs for the lifetime of the process (survives reconnects).
- `_receive_loop` is per-connection; cancelled and recreated on each reconnect.
- `self._ws` shared between loops; set to `None` while disconnected so the input loop
  can detect the gap and wait rather than crash.

---

## Quick start (web mode)

```bash
git clone <this-repo>
cd familiar-ai
cp .env.example .env
# fill in API_KEY, optionally TTS_ENGINE, CAMERA_HOST, …

uv sync
uv run familiar --web          # start WebSocket server

# in another terminal:
uv run familiar-client         # connect CLI client
# or open http://localhost:5000 in a browser
```
