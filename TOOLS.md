# Tools & Stack

## Current Pipeline

| Tool | Role in Pipeline | Why We Use It | Alternatives | What They'd Improve |
|------|-----------------|---------------|--------------|---------------------|
| **Gemini 3.1 Pro Preview** | Script writing | Free via AI Studio, strong creative writing, reliable JSON output, good at following structural rules | Claude Sonnet/Opus | Better character voice, more consistent arc discipline, stronger prose — but costs ~$0.015/1K tokens |
| **Gemini 3.1 Pro Preview** | Scene direction (shot briefs) | Same free API call, understands cinematic language, returns structured JSON with camera/lighting/motion | Claude, GPT-4o | More precise shot composition rules, less repetition in prompts — same cost tradeoff |
| **edge-tts** | Narration (voiceover) | Completely free, Microsoft Neural voices, runs locally, no quota | ElevenLabs | Dramatically more natural delivery, emotion, pacing — costs ~$0.30/1K chars. Currently at quota limit |
| | | | OpenAI TTS | Good quality, consistent, reliable API — costs $0.015/1K chars |
| | | | Kokoro TTS | Free, local, surprisingly good — requires Python setup |
| **faster-whisper** | Word-level captions | Free, runs on CPU, accurate word timestamps, no API calls | OpenAI Whisper API | Slightly more accurate — costs $0.006/min |
| | | | AssemblyAI | Best accuracy + speaker detection — costs $0.01/min |
| **HuggingFace FLUX.1-schnell** | Image generation | Free with HF account, FLUX produces cinematic quality, handles lighting prompts well | Midjourney | Best image quality on the market, consistent style — costs $10/month subscription, no API |
| | | | Replicate (FLUX) | Same FLUX model, reliable API, resumable — costs ~$0.003/image (~$0.02/video) |
| | | | DALL-E 3 | Better text rendering, follows prompts literally — costs $0.04/image ($0.32/video) |
| | | | Stable Diffusion local | Free, unlimited, full control — requires GPU (you don't have one) |
| **FFmpeg zoompan** | Ken Burns motion per clip | Free, industry standard, runs locally, precise control over zoom/pan curves | Adobe Premiere / DaVinci | Visual keyframe editing — but no CLI automation possible |
| **FFmpeg concat + mux** | Video + audio assembly | Free, fast, lossless copy where possible, handles all container formats | MoviePy | Easier Python API — but significantly slower and lossy by default |
| **FFmpeg subtitles filter** | Caption burning | Free, hardsubs baked into video (no separate file needed for social upload) | Remotion | Animated captions, word-highlight effects — requires Node.js, much more setup |

## Cost Per Video (Current Stack)

| Step | Tool | Cost |
|------|------|------|
| Script + Scene Direction | Gemini 3.1 Pro Preview | $0.00 (free via AI Studio) |
| Narration | edge-tts | $0.00 (free, local) |
| Captions | faster-whisper | $0.00 (free, local CPU) |
| Image generation (8 images) | HuggingFace FLUX.1-schnell | $0.00 (free tier) |
| Video assembly | FFmpeg | $0.00 (free, local) |
| **Total per video** | | **$0.00** |

> Free tier limits apply to HuggingFace — high volume may require a paid plan.

## Cost Per Video (Upgraded Stack)

| Step | Tool | Cost |
|------|------|------|
| Script + Scene Direction | Gemini 3.1 Pro Preview | $0.00 |
| Narration | ElevenLabs (Creator plan $22/mo) | ~$0.04 per video at ~100 videos/month |
| Captions | faster-whisper | $0.00 |
| Image generation (8 images) | Replicate FLUX.1-schnell | ~$0.02 (8 × $0.003) |
| Video assembly | FFmpeg | $0.00 |
| **Total per video** | | **~$0.06** |

## Recommended Upgrades (Priority Order)

1. **ElevenLabs** (narration) — once quota resets or on a paid plan. The voice carries the emotion for 57 seconds straight. Biggest impact on viewer retention.
2. **Replicate FLUX** (images) — ~$0.02/video. Removes HuggingFace free tier dependency, reliable API, consistent results.
3. **Remotion** (captions) — animated word-highlight captions significantly boost engagement on short-form. Higher setup cost but visible retention improvement.
