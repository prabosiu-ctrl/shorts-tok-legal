"""
Narrator — Kokoro TTS (primary, free, local CPU) with edge-tts fallback.

Kokoro: 82M parameter neural TTS, cinematic quality, runs on CPU.
  Install: pip install kokoro soundfile
  First run downloads model (~300MB) from HuggingFace automatically.
  Default voice: bm_george (British male, warm, storytelling)

edge-tts: free, no install required, Microsoft Neural voices.
  Used automatically if Kokoro is not installed.

Override voice:
  KOKORO_VOICE=bm_lewis in .env  (Kokoro)
  NARRATOR_VOICE=en-GB-RyanNeural in .env  (edge-tts)
"""

import os
import subprocess
import asyncio
from pathlib import Path

KOKORO_VOICE_DEFAULT = "bm_george"
EDGETTS_VOICE_DEFAULT = "en-GB-RyanNeural"


def generate_narration(script: str, output_path: str) -> None:
    if not _try_kokoro(script, output_path):
        _use_edgetts(script, output_path)


def _try_kokoro(script: str, output_path: str) -> bool:
    """Attempt narration with Kokoro. Returns True on success, False if not installed."""
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError:
        return False

    voice = os.environ.get("KOKORO_VOICE", KOKORO_VOICE_DEFAULT)
    lang_code = "b" if voice.startswith("b") else "a"  # b=British, a=American

    try:
        pipeline = KPipeline(lang_code=lang_code)
        chunks = []
        for _, _, audio in pipeline(script, voice=voice, speed=0.92):
            if audio is not None:
                chunks.append(audio)

        if not chunks:
            return False

        import numpy as np
        combined = np.concatenate(chunks)

        # Save as WAV first, then convert to MP3 via FFmpeg
        wav_path = str(output_path).replace(".mp3", "_tmp.wav")
        sf.write(wav_path, combined, 24000)

        result = subprocess.run([
            "ffmpeg", "-y",
            "-i", wav_path,
            "-b:a", "192k",
            output_path,
        ], capture_output=True)

        Path(wav_path).unlink(missing_ok=True)

        if result.returncode != 0:
            return False

        print(f"      Kokoro TTS: {voice}")
        return True

    except Exception as e:
        print(f"      Kokoro failed ({e}), falling back to edge-tts.")
        return False


def _use_edgetts(script: str, output_path: str) -> None:
    import edge_tts
    voice = os.environ.get("NARRATOR_VOICE", EDGETTS_VOICE_DEFAULT)
    asyncio.run(_edgetts_generate(script, output_path, voice))
    print(f"      edge-tts: {voice}")


async def _edgetts_generate(script: str, output_path: str, voice: str) -> None:
    import edge_tts
    communicate = edge_tts.Communicate(
        text=script,
        voice=voice,
        rate="-8%",
        volume="+0%",
        pitch="-5Hz",
    )
    await communicate.save(output_path)
