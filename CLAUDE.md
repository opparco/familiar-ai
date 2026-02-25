# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

familiar-ai is an embodied AI companion agent that perceives the real world through cameras, moves on a robot vacuum, speaks via TTS, and remembers what it sees. It runs a ReAct loop powered by multi-platform LLM backends (Anthropic, Gemini, OpenAI/OpenRouter, Kimi).

## Build & development commands

```bash
uv sync                          # Install dependencies
uv run familiar                  # Run (TUI mode, default)
uv run familiar --no-tui         # Run (plain REPL)
uv run familiar --web            # Run (WebSocket server on :5000)
uv run ruff check .              # Lint
uv run ruff format .             # Format
uv run pytest                    # Run all tests
uv run pytest tests/test_tape.py # Run a single test file
```

## Git workflow

**Always cut a feature branch.** Never commit directly to `main`. Commit messages in English, Conventional Commits format (`feat:`, `fix:`, `docs:`, `chore:`).

## Code style

- Python 3.10+, async-first (`asyncio`)
- Formatted with `ruff` (line length: 100)
- Run `uv run ruff check . && uv run ruff format .` before committing

## Architecture

### Core loop: ReAct + TAPE planning

`agent.py` (`EmbodiedAgent`) runs a ReAct loop (max 50 iterations per turn):

1. **TAPE plan generation** (`tape.py`) — before the loop, generates a 2-4 step plan injected into the system prompt. Skipped for desire-driven turns.
2. **THINK → ACT → OBSERVE** — agent calls tools, observes results.
3. **Adaptive replanning** — after each tool call, checks if the observation contradicts the plan. If blocked, generates a revised step appended to the tool result. Only triggers on semantic contradictions, NOT technical errors.

### Multi-platform LLM backends (`backend.py`)

`create_backend(config)` factory returns one of: `AnthropicBackend`, `GeminiBackend`, `OpenAICompatibleBackend`, `KimiBackend`. All implement:
- `stream_turn(system, messages, tools, max_tokens, on_text)` → `(TurnResult, raw_content)`
- `complete(prompt, max_tokens)` → `str` (for utility calls like TAPE planning)
- Message factories: `make_user_message()`, `make_assistant_message()`, `make_tool_results()`

**Backend quirks to know:**
- **Kimi**: Must round-trip `reasoning_content` field across turns or API rejects tool calls.
- **OpenAICompatible**: Two modes — `tools_mode="native"` (function calling API) vs `"prompt"` (injects tool descriptions, parses `<tool_call>` XML tags). Also strips Gemini `THOUGHT\n` prefix from output.
- **Gemini native**: Thinking tokens explicitly disabled (`thinking_budget=0`).

### Tool interface pattern

All tools in `src/familiar_agent/tools/` follow this interface:
```python
class SomeTool:
    def get_tool_definitions(self) -> list[dict]:  # Anthropic-style tool schema
        ...
    async def call(self, tool_name: str, tool_input: dict) -> tuple[str, str | None]:
        # Returns (text_result, base64_image_or_None)
```

Tools are registered in `agent.py` → `_init_tools()`, aggregated in `_all_tool_defs` property, dispatched in `_execute_tool()`.

### Desire system (`desires.py`)

Autonomous motivation system with growth rates and trigger thresholds:
- Desires (`look_around`, `explore`, `greet_companion`, `rest`) grow over time via `tick()`.
- When a desire reaches threshold (0.6), it fires as an inner-voice prompt injected into `agent.run()`.
- State persisted to `~/.familiar_ai/desires.json` across restarts.
- Cooldown: 90s between desire-driven turns. Integration lives in `main.py` (REPL) and `tui.py` (TUI).
- Curiosity targets carry across sessions via memory (`kind='curiosity'`).

### Memory (`tools/memory.py`)

SQLite + `multilingual-e5-small` embeddings (CPU-only torch). Two tables: `observations` + `obs_embeddings`.

**Memory kinds:** `observation`, `conversation`, `feeling`, `self_model`, `curiosity`.

- Embedding model is **lazy-loaded** on first `save()`/`recall()`.
- Recall: vector similarity → LIKE keyword fallback → recency fallback.
- Past memories injected into the **user message** (not system prompt) on each turn.
- Image thumbnails (320x240 JPEG) stored as base64 in DB.

### Agent non-obvious behaviors

- **Morning reconstruction** (`_morning_reconstruction()`): Only on first turn of a session — loads past self-model, curiosities, recent feelings to create continuity.
- **Interoception** (`_interoception()`): Generates "felt sense" from uptime/time-of-day/conversation density, silently injected into system prompt.
- **Auto-say**: Tracks whether agent called `say()`. After 2 tool calls without speaking, injects a reminder. If agent finishes without ever calling `say()`, auto-speaks the first 150 chars.
- **Interrupts**: User can type while agent is busy; input is injected mid-loop as `[User interrupted]`.
- **Self-model updates** (`_update_self_model()`): After emotional responses, extracts self-insight via LLM and stores as `kind='self_model'` memory.

### Key architectural constraint

**Camera and legs are separate physical devices.** The camera is fixed (e.g., on a shelf). Moving the robot vacuum does NOT change what the camera sees. The system prompt must always make this clear.

## Adding a new tool

1. Implement in `src/familiar_agent/tools/<name>.py` following the `get_tool_definitions()` + `call()` pattern.
2. Register in `agent.py` → `_init_tools()`, `_all_tool_defs`, `_execute_tool()`.
3. Add the tool name to the system prompt description.

## Adding a new LLM backend

1. Implement in `backend.py` — `stream_turn()`, `complete()`, and message factories.
2. Add to `create_backend()` factory.

## Environment variables

All configuration via env vars (see `.env.example`). Key vars:
- `PLATFORM` (`anthropic`|`gemini`|`openai`|`kimi`), `API_KEY`, `MODEL`, `BASE_URL`, `TOOLS_MODE`
- `CAMERA_HOST`, `CAMERA_USERNAME`, `CAMERA_PASSWORD` — ONVIF camera
- `TTS_ENGINE` (`elevenlabs`|`voicevox`) + engine-specific vars
- `ME.md` — persona file, gitignored, never commit.

## I18n

`_i18n.py` handles multilingual strings (ja/zh/zh-tw/fr/de/en). All user-facing text (prompts, banners, desire murmurs) goes through `_t("key")`. Locale auto-detected from system.
