"""
Narrator — voice synthesis pipeline

Priority:
  1. Gemini 2.5 Flash TTS  (primary — API-based, best prosody, 100 RPD free)
  2. Kokoro                 (local CPU fallback — 82M neural TTS, no API needed)
  3. edge-tts               (final fallback — Microsoft Neural voices, free)

Voice config:
  GEMINI_TTS_VOICE=Charon   in .env  (default: deep resonant male)
  KOKORO_VOICE=bm_george    in .env  (British male, storytelling)
  NARRATOR_VOICE=en-GB-RyanNeural  in .env  (edge-tts)

Available Gemini voices (male, story-appropriate):
  Charon — deep, resonant    Fenrir — strong, clear
  Orus   — warm, measured    Achird — smooth, authoritative
"""

import os
import subprocess
import asyncio
from pathlib import Path


GEMINI_TTS_VOICE_DEFAULT = "Charon"
KOKORO_VOICE_DEFAULT      = "bm_george"
EDGETTS_VOICE_DEFAULT     = "en-GB-RyanNeural"


def generate_narration(script: str, output_path: str) -> None:
    if _try_gemini_tts(script, output_path):
        return
    if _try_kokoro(script, output_path):
        return
    _use_edgetts(script, output_path)


# ── Gemini 2.5 Flash TTS ──────────────────────────────────────────────────────

def _try_gemini_tts(script: str, output_path: str) -> bool:
    """Primary: Gemini 2.5 Flash TTS via Google GenAI API."""
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        return False

    try:
        from google import genai
        from google.genai import types

        client     = genai.Client(api_key=api_key)
        voice_name = os.environ.get("GEMINI_TTS_VOICE", GEMINI_TTS_VOICE_DEFAULT)

        response = client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=script,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name,
                        )
                    )
                ),
            ),
        )

        audio_part  = response.candidates[0].content.parts[0]
        audio_bytes = audio_part.inline_data.data
        mime_type   = audio_part.inline_data.mime_type  # e.g. "audio/pcm;rate=24000"

        # Parse sample rate from MIME type
        sample_rate = 24000
        if "rate=" in (mime_type or ""):
            try:
                sample_rate = int(mime_type.split("rate=")[1].split(";")[0])
            except (IndexError, ValueError):
                pass

        # Save raw PCM → convert to MP3 via FFmpeg
        pcm_path = str(output_path).replace(".mp3", "_gemini.pcm")
        Path(pcm_path).write_bytes(audio_bytes)

        result = subprocess.run([
            "ffmpeg", "-y",
            "-f", "s16le",           # 16-bit signed little-endian PCM
            "-ar", str(sample_rate),
            "-ac", "1",              # mono
            "-i", pcm_path,
            "-b:a", "192k",
            output_path,
        ], capture_output=True)

        Path(pcm_path).unlink(missing_ok=True)

        if result.returncode != 0:
            print(f"      Gemini TTS PCM→MP3 failed, trying Kokoro.")
            return False

        print(f"      Gemini TTS: {voice_name}")
        return True

    except Exception as e:
        print(f"      Gemini TTS failed ({e}), trying Kokoro.")
        return False


# ── Kokoro (local CPU) ────────────────────────────────────────────────────────

def _try_kokoro(script: str, output_path: str) -> bool:
    """Fallback: Kokoro local neural TTS. Returns True on success."""
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError:
        return False

    voice     = os.environ.get("KOKORO_VOICE", KOKORO_VOICE_DEFAULT)
    lang_code = "b" if voice.startswith("b") else "a"

    try:
        pipeline = KPipeline(lang_code=lang_code)
        chunks   = []
        for _, _, audio in pipeline(script, voice=voice, speed=0.92):
            if audio is not None:
                chunks.append(audio)

        if not chunks:
            return False

        combined = np.concatenate(chunks)
        wav_path = str(output_path).replace(".mp3", "_kokoro.wav")
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


# ── edge-tts (final fallback) ─────────────────────────────────────────────────

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
