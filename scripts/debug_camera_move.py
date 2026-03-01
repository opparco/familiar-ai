"""Debug script for CameraTool.move() — tests PTZ direction commands.

Usage:
    uv run python scripts/debug_camera_move.py [direction] [degrees]
    uv run python scripts/debug_camera_move.py           # interactive menu
    uv run python scripts/debug_camera_move.py left 30
    uv run python scripts/debug_camera_move.py --all     # cycle all 4 directions

Reads CAMERA_HOST / CAMERA_USERNAME / CAMERA_PASSWORD from .env (or env vars).
Captures a JPEG before and after each move, saved to ~/.familiar_ai/captures/.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("debug_camera_move")

# ── load .env ───────────────────────────────────────────────────────────────
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

CAMERA_HOST = os.environ.get("CAMERA_HOST", "")
CAMERA_USERNAME = os.environ.get("CAMERA_USERNAME", "admin")
CAMERA_PASSWORD = os.environ.get("CAMERA_PASSWORD", "")
CAMERA_PORT = int(os.environ.get("CAMERA_PORT", "2020"))

CAPTURE_DIR = Path.home() / ".familiar_ai" / "captures"

DIRECTIONS = ["left", "right", "up", "down"]

# ── helpers ─────────────────────────────────────────────────────────────────

def direction_delta(direction: str, degrees: int) -> tuple[float, float]:
    """Return (pan_delta, tilt_delta) for RelativeMove.
    Mirrors the logic in CameraTool.move() so we can inspect the values.
    Tapo C220: +x = physical LEFT, +y = physical UP.
    """
    pan_delta = tilt_delta = 0.0
    if direction == "left":
        pan_delta = degrees / 180.0
    elif direction == "right":
        pan_delta = -degrees / 180.0
    elif direction == "up":
        tilt_delta = -degrees / 90.0
    elif direction == "down":
        tilt_delta = degrees / 90.0
    return pan_delta, tilt_delta


async def capture_frame(host: str, username: str, password: str, label: str) -> Path | None:
    """Grab one RTSP frame with ffmpeg and save it."""
    stream_url = f"rtsp://{username}:{password}@{host}:554/stream1"
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = CAPTURE_DIR / f"debug_{label}_{ts}.jpg"

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        tmp = Path(f.name)

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-i", stream_url,
            "-vframes", "1",
            "-q:v", "3",
            "-vf", "scale=640:-1",
            "-y", str(tmp),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10.0)
        if tmp.exists() and tmp.stat().st_size > 0:
            tmp.rename(out_path)
            logger.info("Captured → %s", out_path)
            return out_path
        else:
            logger.warning("ffmpeg produced empty file")
            return None
    except asyncio.TimeoutError:
        logger.warning("RTSP capture timed out")
        return None
    except FileNotFoundError:
        logger.warning("ffmpeg not found — skipping capture")
        return None
    finally:
        tmp.unlink(missing_ok=True)


async def connect_ptz(host: str, username: str, password: str, port: int):
    """Return (ptz_service, profile_token) or raise."""
    import onvif
    from onvif import ONVIFCamera

    onvif_dir = os.path.dirname(onvif.__file__)
    wsdl_dir = os.path.join(onvif_dir, "wsdl")
    if not os.path.isdir(wsdl_dir):
        wsdl_dir = os.path.join(os.path.dirname(onvif_dir), "wsdl")

    logger.info("Connecting to ONVIF camera at %s:%s …", host, port)
    cam = ONVIFCamera(host, port, username, password, wsdl_dir=wsdl_dir)
    await cam.update_xaddrs()

    media = await cam.create_media_service()
    profiles = await media.GetProfiles()
    token = profiles[0].token if profiles else "Profile_1"
    logger.info("Connected. Profile token: %s", token)

    ptz = await cam.create_ptz_service()
    return ptz, token


async def do_move(ptz, token: str, direction: str, degrees: int) -> None:
    pan_delta, tilt_delta = direction_delta(direction, degrees)
    print(f"\n  direction={direction!r}  degrees={degrees}")
    print(f"  PanTilt x={pan_delta:+.4f}  y={tilt_delta:+.4f}")
    print("  Sending RelativeMove …")

    await ptz.RelativeMove(
        {
            "ProfileToken": token,
            "Translation": {
                "PanTilt": {"x": pan_delta, "y": tilt_delta},
            },
        }
    )
    await asyncio.sleep(0.4)
    print("  Done.")


# ── main ────────────────────────────────────────────────────────────────────

async def run_single(direction: str, degrees: int) -> None:
    if not CAMERA_HOST:
        print("ERROR: CAMERA_HOST not set. Check your .env or env vars.")
        sys.exit(1)

    print(f"\n=== debug_camera_move  {direction} {degrees}° ===")
    print(f"    host={CAMERA_HOST}  user={CAMERA_USERNAME}  port={CAMERA_PORT}\n")

    pan_delta, tilt_delta = direction_delta(direction, degrees)
    print(f"  ONVIF delta preview → PanTilt x={pan_delta:+.4f}  y={tilt_delta:+.4f}")

    ptz, token = await connect_ptz(CAMERA_HOST, CAMERA_USERNAME, CAMERA_PASSWORD, CAMERA_PORT)

    before = await capture_frame(CAMERA_HOST, CAMERA_USERNAME, CAMERA_PASSWORD, f"{direction}_before")
    await do_move(ptz, token, direction, degrees)
    after = await capture_frame(CAMERA_HOST, CAMERA_USERNAME, CAMERA_PASSWORD, f"{direction}_after")

    print("\n--- Result ---")
    if before:
        print(f"  Before : {before}")
    if after:
        print(f"  After  : {after}")
    print("  (open the files to verify the camera moved in the expected direction)")


async def run_all(degrees: int) -> None:
    if not CAMERA_HOST:
        print("ERROR: CAMERA_HOST not set.")
        sys.exit(1)

    print(f"\n=== debug_camera_move --all  {degrees}° each ===\n")
    ptz, token = await connect_ptz(CAMERA_HOST, CAMERA_USERNAME, CAMERA_PASSWORD, CAMERA_PORT)

    for direction in DIRECTIONS:
        input(f"\nPress ENTER to send '{direction}' {degrees}° …")
        before = await capture_frame(CAMERA_HOST, CAMERA_USERNAME, CAMERA_PASSWORD, f"{direction}_before")
        await do_move(ptz, token, direction, degrees)
        after = await capture_frame(CAMERA_HOST, CAMERA_USERNAME, CAMERA_PASSWORD, f"{direction}_after")
        print(f"  before={before}  after={after}")

    print("\nAll directions tested.")


async def interactive_menu() -> None:
    if not CAMERA_HOST:
        print("ERROR: CAMERA_HOST not set.")
        sys.exit(1)

    print("\n=== CameraTool move() debugger ===")
    print(f"Camera: {CAMERA_HOST}:{CAMERA_PORT}  user={CAMERA_USERNAME}\n")

    ptz, token = await connect_ptz(CAMERA_HOST, CAMERA_USERNAME, CAMERA_PASSWORD, CAMERA_PORT)

    while True:
        print("\nDirections: left / right / up / down  |  q = quit")
        raw = input("  > ").strip().lower()
        if raw in ("q", "quit", "exit"):
            break
        parts = raw.split()
        if not parts or parts[0] not in DIRECTIONS:
            print("  Unknown direction.")
            continue
        direction = parts[0]
        degrees = int(parts[1]) if len(parts) > 1 else 30

        before = await capture_frame(CAMERA_HOST, CAMERA_USERNAME, CAMERA_PASSWORD, f"{direction}_before")
        await do_move(ptz, token, direction, degrees)
        after = await capture_frame(CAMERA_HOST, CAMERA_USERNAME, CAMERA_PASSWORD, f"{direction}_after")
        print(f"  before={before}")
        print(f"  after ={after}")


def main() -> None:
    args = sys.argv[1:]

    if not args:
        asyncio.run(interactive_menu())
    elif args[0] == "--all":
        degrees = int(args[1]) if len(args) > 1 else 30
        asyncio.run(run_all(degrees))
    elif args[0] in DIRECTIONS:
        direction = args[0]
        degrees = int(args[1]) if len(args) > 1 else 30
        asyncio.run(run_single(direction, degrees))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
