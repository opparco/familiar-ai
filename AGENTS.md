# familiar-ai — Agent Guide

## Project Overview

familiar-ai is an embodied AI companion agent that perceives the real world through cameras, moves on a robot vacuum, speaks via TTS, and remembers what it sees. It runs a ReAct loop powered by multiple LLM backends (Anthropic Claude, Google Gemini, Moonshot Kimi, OpenAI).

The core concept is giving a language model a physical body with:
- **Eyes**: Wi-Fi PTZ camera (ONVIF/RTSP) or USB webcam
- **Neck**: Camera pan/tilt control
- **Legs**: Tuya robot vacuum for movement
- **Voice**: ElevenLabs TTS via camera speaker
- **Memory**: SQLite + multilingual-e5-small embeddings for semantic search
- **Desire system**: Autonomous behavior driven by internal drives (curiosity, exploration)

## Technology Stack

- **Language**: Python 3.10+
- **Package Manager**: [uv](https://docs.astral.sh/uv/) (modern Python package manager)
- **Build Backend**: hatchling
- **Key Dependencies**:
  - `anthropic`, `openai`, `google-genai` — LLM API clients
  - `onvif-zeep-async` — ONVIF camera control
  - `tinytuya` — Robot vacuum control
  - `sentence-transformers` — Embeddings for memory
  - `textual` — Terminal UI framework
  - `aiohttp` — Async HTTP client
- **Dev Tools**:
  - `ruff` — Linting and formatting (line length: 100)
  - `pytest`, `pytest-asyncio` — Testing
  - `pre-commit` — Git hooks

## Build and Test Commands

```bash
# Install dependencies
uv sync

# Run the application
./run.sh              # Textual TUI (default)
./run.sh --no-tui     # Plain REPL

# Or via uv
uv run familiar

# Linting and formatting
uv run ruff check .
uv run ruff format .

# Testing
uv run pytest -v

# Set up pre-commit hooks
uvx pre-commit install
```

## Code Style Guidelines

- **Python 3.10+** with type hints
- **Async-first**: Use `asyncio` for I/O-bound operations
- **Line length**: 100 characters (configured in `pyproject.toml`)
- **Formatter**: `ruff` (replaces black/isort)
- **Imports**: Grouped as stdlib → third-party → local

```python
"""Module docstring."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np

from .config import AgentConfig

if TYPE_CHECKING:
    from .agent import EmbodiedAgent
```

## Project Structure

```
src/familiar_agent/
├── __init__.py          # Package init
├── main.py              # CLI entry point, REPL loop
├── agent.py             # Core ReAct loop, EmbodiedAgent class
├── backend.py           # LLM backend abstraction (Anthropic, OpenAI, Gemini, Kimi)
├── config.py            # Environment-based configuration (dataclasses)
├── desires.py           # Autonomous desire system
├── tape.py              # TAPE-inspired planning (plan generation, adaptive replanning)
├── tui.py               # Textual terminal UI
├── _i18n.py             # Internationalization (6 languages)
└── tools/
    ├── __init__.py
    ├── camera.py        # ONVIF PTZ camera + RTSP capture
    ├── memory.py        # SQLite + embeddings memory system
    ├── mobility.py      # Tuya robot vacuum control
    ├── tts.py           # ElevenLabs TTS + go2rtc
    └── tom.py           # Theory of Mind tool

tests/
├── __init__.py
└── test_tape.py         # TAPE mechanism tests

docs/
└── technical.md         # Research background (ReAct, SayCan, Reflexion, Voyager)

persona-template/
├── en.md, ja.md, zh.md, zh-tw.md, fr.md, de.md  # Personality templates
```

## Key Architectural Decisions

1. **Camera and legs are separate physical devices**: The camera is fixed (e.g., on a shelf). Moving the robot vacuum does NOT change what the camera sees. The system prompt must always make this clear.

2. **Memory uses SQLite + numpy embeddings**: Not ChromaDB, for fast startup and lightweight deployment. Uses `multilingual-e5-small` model (~117MB, lazy loaded).

3. **Embeddings use CPU-only torch**: Configured via `pytorch-cpu` index. Do not switch to GPU builds without good reason.

4. **ME.md is gitignored**: Contains the user's personal persona. Never commit it.

5. **Multi-platform LLM support**: Backend abstraction in `backend.py` supports:
   - `anthropic` (default) — Native Anthropic SDK
   - `gemini` — Google Generative AI SDK
   - `kimi` — Moonshot AI (special handling for `reasoning_content`)
   - `openai` — OpenAI API or compatible endpoints (Ollama, vLLM, etc.)

## Testing Instructions

Tests use `pytest` with `pytest-asyncio`:

```bash
# Run all tests
uv run pytest -v

# Run specific test
uv run pytest tests/test_tape.py -v
```

- Use `_MockBackend` pattern for testing LLM-dependent code
- Mock external services (cameras, Tuya, ElevenLabs) in unit tests
- Tests should be async-compatible with `@pytest.mark.asyncio`

## Adding a New Tool

1. Implement in `src/familiar_agent/tools/<name>.py`
2. Add `get_tool_definitions()` returning list of tool schemas
3. Add `call(name, input)` method returning `(text, image_b64_or_None)`
4. Register in `agent.py` → `_init_tools()`, `_all_tool_defs`, `_execute_tool()`
5. Add the tool name to the system prompt description

Example tool schema:
```python
{
    "name": "my_tool",
    "description": "What this tool does",
    "input_schema": {
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "Parameter description"}
        },
        "required": ["param"]
    }
}
```

## Environment Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Required | Description |
|----------|----------|-------------|
| `PLATFORM` | Yes | `anthropic` \| `gemini` \| `openai` \| `kimi` |
| `API_KEY` | Yes | API key for chosen platform |
| `MODEL` | No | Model name (platform-specific defaults) |
| `AGENT_NAME` | No | Display name in TUI |
| `COMPANION_NAME` | No | Name of the user (for ToM) |
| `CAMERA_HOST` | No | ONVIF camera IP |
| `CAMERA_USERNAME` | No | Camera account username |
| `CAMERA_PASSWORD` | No | Camera account password |
| `ELEVENLABS_API_KEY` | No | For TTS voice |
| `TUYA_*` | No | Robot vacuum credentials |

## Git Workflow

**Always cut a feature branch before starting work.** Never commit directly to `main`.

```bash
git checkout -b feat/your-feature-name
# ... make changes and commits ...
# then open a PR to main
```

## Commit Messages

**Always in English.** Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add USB microphone support
fix: handle ONVIF reconnect on timeout
docs: update camera setup instructions
chore: bump anthropic to 0.42.0
```

## CI/CD

GitHub Actions workflows (`.github/workflows/`):
- `lint.yml`: Runs `ruff check` and `ruff format --check` on PRs and main
- `translate.yml`: Automated translation workflows

## Security Considerations

- **Never hardcode API keys or IP addresses** — always use environment variables
- **ME.md contains personal data** — it is gitignored by default
- **Camera credentials**: Use local camera accounts, not cloud credentials
- **Memory storage**: Local SQLite database in `~/.familiar_ai/` — no cloud storage

## Internationalization

The project supports 6 languages:
- English (`en`)
- Japanese (`ja`)
- Chinese Simplified (`zh`)
- Chinese Traditional (`zh-tw`)
- French (`fr`)
- German (`de`)

Add translations in `src/familiar_agent/_i18n.py` in the `_T` dictionary.

## Useful Resources

- [ReAct paper](https://arxiv.org/abs/2210.03629) — Core agent loop pattern
- [SayCan](https://say-can.github.io/) — Affordance grounding
- [Reflexion](https://arxiv.org/abs/2303.11366) — Memory and self-reflection
- [Voyager](https://arxiv.org/abs/2305.16291) — Skill learning and curiosity
- [TAPE](https://arxiv.org/abs/2602.19633) — Planning and replanning
