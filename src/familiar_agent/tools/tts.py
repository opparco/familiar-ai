"""TTS tool - voice of the embodied agent (ElevenLabs / VOICEVOX + go2rtc camera speaker)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import tempfile
import traceback
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import TTSConfig

logger = logging.getLogger(__name__)

# Debug log file for detailed troubleshooting
_DEBUG_LOG = Path("debug.log")


def _debug_log(msg: str) -> None:
    """Write debug message to debug.log with timestamp."""
    timestamp = datetime.now().isoformat()
    try:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception:
        pass


def _log_exception(context: str) -> None:
    """Log full exception traceback to debug.log."""
    exc_info = sys.exc_info()
    tb_str = "".join(traceback.format_exception(*exc_info))
    _debug_log(f"EXCEPTION in {context}:\n{tb_str}")

_GO2RTC_CACHE = Path.home() / ".cache" / "embodied-claude" / "go2rtc"
_GO2RTC_BIN = _GO2RTC_CACHE / "go2rtc"
_GO2RTC_CONFIG = _GO2RTC_CACHE / "go2rtc.yaml"


def _ensure_go2rtc(api_url: str) -> None:
    """Start go2rtc if it's not already running."""
    try:
        urllib.request.urlopen(f"{api_url}/api", timeout=2)
        return  # already running
    except Exception:
        pass

    if not _GO2RTC_BIN.exists():
        logger.warning("go2rtc binary not found at %s", _GO2RTC_BIN)
        return
    if not _GO2RTC_CONFIG.exists():
        logger.warning("go2rtc config not found at %s", _GO2RTC_CONFIG)
        return

    logger.info("Starting go2rtc...")
    subprocess.Popen(
        [str(_GO2RTC_BIN), "-config", str(_GO2RTC_CONFIG)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    import time

    for _ in range(10):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"{api_url}/api", timeout=1)
            logger.info("go2rtc started")
            return
        except Exception:
            continue
    logger.warning("go2rtc did not start in time")


class TTSEngine(ABC):
    """Abstract base class for TTS engines."""

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Return the engine name."""
        ...

    @abstractmethod
    async def synthesize(self, text: str) -> tuple[bytes, str]:
        """Synthesize text to audio bytes.

        Returns:
            Tuple of (audio_bytes, audio_format) where format is e.g. 'mp3', 'wav'.
        """
        ...

    def is_available(self) -> bool:
        """Check if the engine is available and configured."""
        return True


class ElevenLabsEngine(TTSEngine):
    """ElevenLabs TTS engine."""

    def __init__(self, api_key: str, voice_id: str) -> None:
        self.api_key = api_key
        self.voice_id = voice_id

    @property
    def engine_name(self) -> str:
        return "elevenlabs"

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def synthesize(self, text: str) -> tuple[bytes, str]:
        """Synthesize text using ElevenLabs API."""
        import aiohttp

        _debug_log(f"ElevenLabs synthesize: voice_id={self.voice_id}, text='{text[:50]}...'")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    _debug_log(f"ElevenLabs API error: status={resp.status}, error={err[:200]}")
                    raise RuntimeError(f"ElevenLabs API failed ({resp.status}): {err[:80]}")
                audio_data = await resp.read()

        _debug_log(f"ElevenLabs synthesis complete: {len(audio_data)} bytes")
        return audio_data, "mp3"


class VoicevoxEngine(TTSEngine):
    """VOICEVOX TTS engine (local HTTP API)."""

    def __init__(self, url: str = "http://localhost:50021", speaker: int = 3) -> None:
        self.url = url.rstrip("/")
        self.speaker = speaker

    @property
    def engine_name(self) -> str:
        return "voicevox"

    def is_available(self) -> bool:
        """Check if VOICEVOX engine is running."""
        try:
            req = urllib.request.Request(f"{self.url}/version", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                resp.read()
            return True
        except Exception:
            return False

    async def synthesize(self, text: str) -> tuple[bytes, str]:
        """Synthesize text using VOICEVOX 2-step API."""
        import urllib.parse

        _debug_log(f"VOICEVOX synthesize: url={self.url}, speaker={self.speaker}, text='{text[:50]}...'")

        # Step 1: Generate audio query
        params = urllib.parse.urlencode({"text": text, "speaker": self.speaker})
        req = urllib.request.Request(
            f"{self.url}/audio_query?{params}",
            method="POST",
        )

        loop = asyncio.get_event_loop()
        try:
            query = await loop.run_in_executor(
                None, lambda: json.loads(urllib.request.urlopen(req, timeout=30).read())
            )
            _debug_log(f"VOICEVOX audio_query success")
        except Exception:
            _log_exception("VOICEVOX audio_query")
            raise

        # Step 2: Synthesize audio
        req = urllib.request.Request(
            f"{self.url}/synthesis?speaker={self.speaker}",
            data=json.dumps(query).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            wav_bytes = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(req, timeout=60).read()
            )
            _debug_log(f"VOICEVOX synthesis complete: {len(wav_bytes)} bytes")
        except Exception:
            _log_exception("VOICEVOX synthesis")
            raise

        return wav_bytes, "wav"


class TTSTool:
    """Text-to-speech using configurable engine.

    Audio output:
    - ElevenLabs: tries go2rtc (camera speaker) first, falls back to local playback
    - VOICEVOX: uses local playback directly (no go2rtc needed)
    """

    def __init__(self, config: TTSConfig) -> None:
        self.config = config
        self.go2rtc_url = config.go2rtc_url
        self.go2rtc_stream = config.go2rtc_stream

        # Initialize the appropriate engine
        engine_name = config.engine.lower()
        if engine_name == "voicevox":
            self._engine: TTSEngine = VoicevoxEngine(config.voicevox_url, config.voicevox_speaker)
            # VOICEVOX is local-only, no need for go2rtc
            self._use_go2rtc = False
        else:
            self._engine = ElevenLabsEngine(config.elevenlabs_api_key, config.voice_id)
            # ElevenLabs may use camera speaker via go2rtc
            self._use_go2rtc = True
            _ensure_go2rtc(self.go2rtc_url)

    @property
    def engine(self) -> TTSEngine:
        """Return the current TTS engine."""
        return self._engine

    async def say(self, text: str, target: str = "myself") -> str:
        """Speak text aloud via configured TTS engine.

        target: "myself" = camera speaker (go2rtc, ElevenLabs only),
               "speaker" = PC local speaker.
        """
        _debug_log(f"TTS say() called: engine={self._engine.engine_name}, text='{text[:50]}...'")

        if len(text) > 200:
            text = text[:197] + "..."

        try:
            audio_data, audio_format = await self._engine.synthesize(text)
            _debug_log(f"Synthesis successful: {len(audio_data)} bytes, format={audio_format}")
        except Exception as e:
            _log_exception("TTSTool.say() synthesis")
            return f"TTS synthesis failed: {e}"

        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as f:
            f.write(audio_data)
            tmp_path = f.name

        try:
            # Only use go2rtc for ElevenLabs; VOICEVOX uses local playback
            if target != "speaker" and self._use_go2rtc:
                _debug_log(f"Trying go2rtc playback: url={self.go2rtc_url}, stream={self.go2rtc_stream}")
                ok, msg = await asyncio.to_thread(
                    _play_via_go2rtc, tmp_path, self.go2rtc_url, self.go2rtc_stream
                )
                _debug_log(f"go2rtc result: ok={ok}, msg={msg}")
                if ok:
                    return f"Said: {text[:50]}..."
                logger.warning("go2rtc playback failed: %s — falling back to local", msg)

            # Local player (used directly for "speaker", or as fallback for "myself")
            _debug_log(f"Starting local playback for: {tmp_path}")
            for player_args in (
                ["mpv", "--no-terminal", "--ao=pulse", tmp_path],
                ["mpv", "--no-terminal", tmp_path],
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", tmp_path],
            ):
                _debug_log(f"Trying player: {player_args[0]}")
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *player_args,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await proc.communicate()
                    if proc.returncode == 0:
                        _debug_log(f"Player {player_args[0]} succeeded")
                        return f"Said: {text[:50]}..."
                    err = stderr.decode(errors="replace").strip()
                    _debug_log(f"Player {player_args[0]} failed (exit {proc.returncode}): {err[:200]}")
                    logger.warning(
                        "%s failed (exit %d): %s", player_args[0], proc.returncode, err[:120]
                    )
                except Exception as e:
                    _debug_log(f"Player {player_args[0]} exception: {e}")
                    _log_exception(f"Player {player_args[0]}")

            _debug_log("All players failed")
            return "TTS playback failed (all players failed)"
        finally:
            try:
                os.unlink(tmp_path)
                _debug_log(f"Cleaned up temp file: {tmp_path}")
            except OSError as e:
                _debug_log(f"Failed to cleanup temp file {tmp_path}: {e}")

    def get_tool_definitions(self) -> list[dict]:
        engine_desc = (
            "VOICEVOX (Japanese optimized)"
            if self._engine.engine_name == "voicevox"
            else "ElevenLabs (supports audio tags like [cheerful], [warmly])"
        )
        return [
            {
                "name": "say",
                "description": (
                    f"Speak text aloud through your camera speaker using {engine_desc}. "
                    "Use this to communicate with people in the room."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text to speak.",
                        },
                    },
                    "required": ["text"],
                },
            },
        ]

    async def call(self, tool_name: str, tool_input: dict) -> tuple[str, None]:
        if tool_name == "say":
            result = await self.say(tool_input["text"], "myself")
            return result, None
        return f"Unknown tool: {tool_name}", None


def _play_via_go2rtc(file_path: str, go2rtc_url: str, stream_name: str) -> tuple[bool, str]:
    """Play audio file through camera speaker via go2rtc backchannel (sync, run in thread)."""
    from urllib.parse import quote

    _debug_log(f"_play_via_go2rtc: file={file_path}, url={go2rtc_url}, stream={stream_name}")

    try:
        abs_path = os.path.abspath(file_path)
        src = f"ffmpeg:{abs_path}#audio=pcma#input=file"
        url = (
            f"{go2rtc_url}/api/streams?dst={quote(stream_name, safe='')}&src={quote(src, safe='')}"
        )
        req = urllib.request.Request(url, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())

        # Check if a sender was established (camera supports backchannel)
        has_sender = any(consumer.get("senders") for consumer in body.get("consumers", []))
        if not has_sender:
            return False, "go2rtc: no audio sender (camera may not support backchannel)"

        # Find ffmpeg producer ID to poll for completion
        ffmpeg_producer_id = None
        for p in body.get("producers", []):
            if "ffmpeg" in p.get("source", ""):
                ffmpeg_producer_id = p.get("id")
                break

        if ffmpeg_producer_id:
            import time

            for _ in range(60):
                time.sleep(0.5)
                try:
                    with urllib.request.urlopen(f"{go2rtc_url}/api/streams", timeout=5) as r:
                        streams = json.loads(r.read())
                    stream = streams.get(stream_name, {})
                    still_playing = any(
                        p.get("id") == ffmpeg_producer_id for p in stream.get("producers", [])
                    )
                    if not still_playing:
                        break
                except Exception:
                    break

        _debug_log(f"go2rtc playback successful: {stream_name}")
        return True, f"played via go2rtc → {stream_name}"
    except Exception as exc:
        _debug_log(f"go2rtc error: {exc}")
        _log_exception("_play_via_go2rtc")
        return False, f"go2rtc error: {exc}"
