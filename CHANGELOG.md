# Changelog

## [1.0.0] - 2026-04-09
### Added
- **Veo 2 video generation** — replaced FLUX image generation + Ken Burns zoompan with Google Veo 2 (`veo-2.0-generate-001`). Generates real 8-second cinematic video clips per shot. Free via GOOGLE_API_KEY. Clips download automatically after polling.
- **Cross-dissolve transitions** — 0.4s dissolve between every clip via FFmpeg `xfade` filter. Falls back to plain concat if xfade fails.
- **Cinematic colour grade** — FFmpeg `colorbalance` post-process applied per ending type: sad (cool/blue), happy (warm/golden), bittersweet (cool shadows + warm highlights). Chained into the caption-burn step.
- **Word-highlight captions (ASS karaoke)** — `transcriber.py` now outputs both `.srt` (fallback) and `.ass` with `{\k}` karaoke tags. Active word renders in yellow, inactive words in white. `assemble_video()` prefers `.ass` automatically.
- **Background music** — `agents/music_selector.py` picks the best track from `assets/music/*.mp3` using Gemini based on script tone. FFmpeg mixes music at 12% volume under narration (`amix`). Skipped gracefully if no tracks present. `assets/music/README.md` documents free sources.
- **Kokoro TTS** — `agents/narrator.py` rewritten to use Kokoro (82M neural TTS, local CPU, British male `bm_george`) as primary voice. Falls back to edge-tts if `kokoro` package not installed. First run auto-downloads model from HuggingFace.
- **Scene director — Veo 2 edition** — `agents/scene_director.py` fully rewritten. New system prompt directs 8-second video clips (not stills). Structured prompt format: shot type + subject with full description + action over 8s + location + light source + camera movement + cinematic style. Accepts `character_anchor` parameter so series parts share one locked character description.
- **Series pipeline character lock** — `series_run.py` passes `character_anchor` from `series_scriptwriter.py` into `direct_scenes()` for each part. All 5 parts use the same verbatim character description.
- **GitHub Actions automation** — `.github/workflows/weekly.yml` generates a new series every Sunday at 02:00 UTC. `.github/workflows/publish_part.yml` publishes one Short per day Mon–Sat at 15:00 UTC.
- **Queue system** — `series_publish.py` writes `queue.json` after upload. `scripts/schedule_publish.py` pops the next entry and makes it public via YouTube API. GitHub Actions commits queue state back to repo.
- **Theme rotation** — `themes.txt` (15 curated story premises). `scripts/rotate_theme.py` consumes the top line each run and removes it.
- **Helper scripts** — `scripts/encode_token.py` base64-encodes `youtube_token.pickle` for GitHub Secrets.
- `requirements.txt` updated: `google-genai>=1.70.0`, `kokoro>=0.9.0`, `soundfile>=0.12.0`

### Changed
- `assemble_video()` signature: added `script: str = ""` (for music selection) and `ending: str = ""` (for colour grade)
- `generate_video()` signature: added `ending: str = ""`, propagated from `run.py`
- `run_part()` in `series_run.py`: added `ending` and `character_anchor` parameters, removed image generation step entirely
- `run.py` step 4 label updated to reflect Veo 2

### Removed
- FLUX image generation from main pipeline (`generate_images()` no longer called in `run.py` or `series_run.py`)
- Ken Burns `process_images_to_clips()` from main pipeline
- `prompt_core` concept from scene director (no more URL length constraints)

## [0.3.0] - 2026-04-04
### Added
- `publish.py` — publisher orchestrator, currently handles YouTube
- `agents/youtube_publisher.py` — uploads final.mp4 to YouTube as private Short, auto-generates title/description/tags via Gemini, includes AI content disclosure flag
- `auth_youtube.py` — one-time OAuth flow to authorize YouTube channel, saves `youtube_token.pickle`

## [0.2.0] - 2026-04-04
### Added
- `colab/video_generator.ipynb` — Colab notebook (T4 GPU) that reads job files from Drive, generates 6 video clips with LTX-Video, slows them 2.5x, upscales to 1080x1920, assembles with FFmpeg + audio + captions, saves `final.mp4` back to Drive
- `upload_job.py` — uploads local job folder to Google Drive using OAuth (not service account); first run opens browser for authorization, subsequent runs are silent
- `oauth_client.json` support + `token.pickle` caching for Drive OAuth
- `fix_notebook.py` — one-time utility to patch notebook cell (can be deleted)

### Fixed
- Switched Drive upload from service account to OAuth — service accounts have no storage quota on personal Drive
- Enabled Google Drive API on project 758500091136

## [0.1.0] - 2026-04-04
### Added
- `main.py` — local pipeline orchestrator: script → narration → captions → saves job folder
- `agents/scriptwriter.py` — generates 120-140 word cinematic story script + 6 scene prompts via Gemini 3.1 Pro Preview; enforces no AI-isms via system prompt
- `agents/narrator.py` — converts script to audio via ElevenLabs (`eleven_multilingual_v2`), configurable voice and expressiveness settings
- `agents/transcriber.py` — transcribes audio to SRT captions via faster-whisper (CPU, `base` model)
- `.env` — credentials file (ElevenLabs, Gemini, YouTube, TikTok, Instagram placeholders)
- `.gitignore` — protects credentials and output
- `requirements.txt`

### Fixed
- Migrated from deprecated `google-generativeai` to `google-genai` SDK
- Updated model from retired `gemini-2.0-flash` to `gemini-3.1-pro-preview`
- Fixed Windows `cp1252` encoding error on Unicode characters in print statements
- Fixed malformed notebook JSON (trailing quote from Write tool)
- Fixed Colab `cp` shell command unreliability — replaced with Python `shutil.copy2`
- Fixed Colab PyTorch namespace conflict — added `os.kill` restart after pip install in Cell 1

## Platforms Status
| Platform | Status |
|---|---|
| YouTube Shorts | Ready |
| TikTok | Pending app review (submitted) |
| Instagram Reels | Planned — needs cloud storage intermediary |

## Architecture (v1.0.0)
```
run.py / series_run.py  (one-click pipeline)
├── agents/scriptwriter.py / series_scriptwriter.py  — Gemini, 3-act arc
├── agents/narrator.py          — Kokoro TTS (local) → edge-tts fallback
├── agents/transcriber.py       — faster-whisper, word-level SRT + ASS karaoke
├── agents/scene_director.py    — Gemini → Veo 2 shot briefs (8s video clips)
├── agents/video_generator.py
│   ├── generate_clips_veo()    — Veo 2 API → 8s cinematic clips per shot
│   └── assemble_video()        — xfade dissolve + audio + music + captions + grade
├── agents/music_selector.py    — Gemini picks track from assets/music/
│
├── series_publish.py           — uploads longform (public) + parts (private) → queue.json
├── scripts/schedule_publish.py — makes next queued part public
│
└── .github/workflows/
    ├── weekly.yml              — Sunday: generate series → publish
    └── publish_part.yml        — Mon–Sat: publish one Short per day
```
