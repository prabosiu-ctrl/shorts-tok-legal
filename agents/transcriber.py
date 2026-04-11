from faster_whisper import WhisperModel
from pathlib import Path


def generate_captions(audio_path: str, output_path: str, model_size: str = "base") -> float:
    """
    Transcribes audio using faster-whisper and writes:
      - A word-level .srt file (fallback)
      - A word-highlight .ass file (TikTok-style karaoke, active word turns yellow)

    Returns audio duration in seconds.
    """
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, word_timestamps=True)

    words = []
    for segment in segments:
        if segment.words:
            for word in segment.words:
                words.append({
                    "word": word.word.strip(),
                    "start": word.start,
                    "end": word.end,
                })

    # Write SRT (fallback)
    srt_content = _words_to_srt(words, max_words_per_caption=4)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    # Write ASS with word highlighting
    ass_path = str(output_path).replace(".srt", ".ass")
    ass_content = _words_to_ass(words, max_words_per_caption=4)
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    return info.duration


def _words_to_srt(words: list, max_words_per_caption: int = 4) -> str:
    """Groups words into short captions for dynamic on-screen display."""
    if not words:
        return ""

    captions = []
    i = 0
    while i < len(words):
        group = words[i: i + max_words_per_caption]
        start = group[0]["start"]
        end = group[-1]["end"]
        text = " ".join(w["word"] for w in group)
        captions.append((start, end, text))
        i += max_words_per_caption

    lines = []
    for idx, (start, end, text) in enumerate(captions, 1):
        lines.append(f"{idx}\n{_fmt_srt(start)} --> {_fmt_srt(end)}\n{text}\n")

    return "\n".join(lines)


def _words_to_ass(words: list, max_words_per_caption: int = 4) -> str:
    """
    Generates an ASS subtitle file with karaoke word highlighting.
    Active word = yellow, inactive words in same group = white.
    """
    if not words:
        return ""

    header = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 576
PlayResY: 1024
WrapStyle: 1

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,30,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,20,20,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    # PrimaryColour &H0000FFFF = yellow (BGR: 00FF FF) — active word
    # SecondaryColour &H00FFFFFF = white — inactive words
    # OutlineColour &H00000000 = black outline
    # BackColour &H80000000 = 50% transparent black box

    lines = [header]
    i = 0
    while i < len(words):
        group = words[i: i + max_words_per_caption]
        line_start = group[0]["start"]
        line_end = group[-1]["end"]

        # Build karaoke text: {\kN}word for each word
        # N = duration in centiseconds
        parts = []
        for w in group:
            duration_cs = max(1, round((w["end"] - w["start"]) * 100))
            parts.append(f"{{\\k{duration_cs}}}{w['word']}")

        text = " ".join(parts)
        lines.append(
            f"Dialogue: 0,{_fmt_ass(line_start)},{_fmt_ass(line_end)},"
            f"Default,,0,0,0,,{text}"
        )
        i += max_words_per_caption

    return "\n".join(lines)


def _fmt_srt(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_ass(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"
