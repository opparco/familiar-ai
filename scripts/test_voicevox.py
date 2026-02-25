"""VOICEVOX TTS接続テストスクリプト（独立版）"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import urllib.request
import urllib.parse
from pathlib import Path
from abc import ABC, abstractmethod


def test_voicevox_connection(url: str = "http://localhost:50021") -> bool:
    """VOICEVOXエンジンが起動しているか確認"""
    print(f"🔍 Testing VOICEVOX connection at {url}...")
    
    try:
        req = urllib.request.Request(f"{url}/version", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            version = resp.read().decode('utf-8')
            print(f"✅ VOICEVOX is running! Version: {version}")
            return True
    except urllib.error.URLError as e:
        print(f"❌ Connection failed: {e}")
        print("\n💡 Tips:")
        print("   - VOICEVOXエンジンが起動しているか確認してください")
        print("   - デフォルトポートは50021です")
        print("   - ファイアウォールでブロックされていないか確認")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_speakers(url: str = "http://localhost:50021") -> None:
    """利用可能な話者一覧を取得"""
    print(f"\n🔍 Fetching available speakers from {url}...")
    
    try:
        req = urllib.request.Request(f"{url}/speakers", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            speakers = json.loads(resp.read())
            print(f"✅ Found {len(speakers)} speaker(s)")
            for speaker in speakers[:5]:  # 最初の5つだけ表示
                print(f"   - {speaker['name']} (ID: {speaker['speaker_uuid'][:8]}...)")
                for style in speaker.get('styles', []):
                    print(f"     Style: {style['name']} (ID: {style['id']})")
            if len(speakers) > 5:
                print(f"   ... and {len(speakers) - 5} more")
    except Exception as e:
        print(f"❌ Failed to fetch speakers: {e}")


class VoicevoxEngine:
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
        # Step 1: Generate audio query
        params = urllib.parse.urlencode({"text": text, "speaker": self.speaker})
        req = urllib.request.Request(
            f"{self.url}/audio_query?{params}",
            method="POST",
        )

        loop = asyncio.get_event_loop()
        query = await loop.run_in_executor(
            None, lambda: json.loads(urllib.request.urlopen(req, timeout=30).read())
        )

        # Step 2: Synthesize audio
        req = urllib.request.Request(
            f"{self.url}/synthesis?speaker={self.speaker}",
            data=json.dumps(query).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        wav_bytes = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=60).read()
        )

        return wav_bytes, "wav"


async def test_synthesize_simple(url: str = "http://localhost:50021", speaker: int = 3) -> None:
    """シンプルな音声合成テスト"""
    print(f"\n🔍 Testing synthesis with speaker ID {speaker}...")
    
    engine = VoicevoxEngine(url, speaker)
    
    if not engine.is_available():
        print("❌ VOICEVOX engine is not available")
        return
    
    test_text = "こんにちは、これはテストです。"
    print(f"   Text: '{test_text}'")
    
    try:
        audio_data, audio_format = await engine.synthesize(test_text)
        print(f"✅ Synthesis successful! Got {len(audio_data)} bytes of {audio_format}")
        
        # ファイルに保存して確認
        output_path = Path("test_output.wav")
        with open(output_path, "wb") as f:
            f.write(audio_data)
        print(f"💾 Saved to: {output_path.absolute()}")
        
        # 自動再生（Windows）
        import platform
        if platform.system() == "Windows":
            os.startfile(output_path)
            print("▶️  Started playback")
            
    except Exception as e:
        print(f"❌ Synthesis failed: {e}")
        import traceback
        traceback.print_exc()


async def test_tts_tool_like() -> None:
    """TTSToolのような使い方でテスト"""
    print("\n" + "="*50)
    print("🔍 Testing TTS-like integration")
    print("="*50)
    
    url = os.environ.get("VOICEVOX_URL", "http://localhost:50021")
    speaker = int(os.environ.get("VOICEVOX_SPEAKER", "3"))
    
    engine = VoicevoxEngine(url, speaker)
    print(f"✅ Engine initialized: {engine.engine_name}")
    
    if not engine.is_available():
        print("❌ Engine is not available")
        return
    
    test_text = "これはVOICEVOXを使ったテスト音声です。"
    print(f"\n📝 Saying: '{test_text}'")
    
    try:
        audio_data, audio_format = await engine.synthesize(test_text)
        print(f"✅ Synthesized {len(audio_data)} bytes")
        
        # 一時ファイルに保存
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as f:
            f.write(audio_data)
            tmp_path = f.name
        
        print(f"💾 Saved to: {tmp_path}")
        
        # ローカル再生を試行
        import subprocess
        players = [
            ["mpv", "--no-terminal", tmp_path],
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", tmp_path],
        ]
        
        for player_args in players:
            try:
                proc = await asyncio.create_subprocess_exec(
                    *player_args,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode == 0:
                    print(f"▶️  Playback started with {player_args[0]}")
                    break
            except FileNotFoundError:
                continue
        else:
            print("⚠️  No audio player found. File saved but not played.")
            
    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()


def main():
    """メインテスト関数"""
    print("="*50)
    print("VOICEVOX TTS Connection Test")
    print("="*50)
    
    # 環境変数からURLを取得（ない場合はデフォルト）
    url = os.environ.get("VOICEVOX_URL", "http://localhost:50021")
    speaker = int(os.environ.get("VOICEVOX_SPEAKER", "3"))
    
    print(f"Target URL: {url}")
    print(f"Speaker ID: {speaker}")
    
    # 接続テスト
    if not test_voicevox_connection(url):
        print("\n⚠️  VOICEVOX engine is not running!")
        print("\n🔧 To start VOICEVOX:")
        print("   1. Download from https://voicevox.hiroshiba.jp/")
        print("   2. Run the VOICEVOX application")
        print("   3. Wait for 'VOICEVOX ENGINE is ready' message")
        print("   4. Retry this test")
        return 1
    
    # 話者一覧取得
    test_speakers(url)
    
    # 非同期テスト
    asyncio.run(test_synthesize_simple(url, speaker))
    asyncio.run(test_tts_tool_like())
    
    print("\n" + "="*50)
    print("✅ All tests completed!")
    print("="*50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
