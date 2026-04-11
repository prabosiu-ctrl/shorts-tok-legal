# Future Ideas

## GitHub Actions — Daily Automated Publishing

### Concept
Run the full pipeline automatically every day at a set time via GitHub Actions. Zero manual intervention — new video published to YouTube (and eventually TikTok/Instagram) on a schedule.

### How it works
1. Push the project to a private GitHub repo
2. Add all API keys as GitHub Actions Secrets (GOOGLE_API_KEY, HF_TOKEN, YOUTUBE credentials)
3. A workflow file (`.github/workflows/daily.yml`) runs `python run.py` on a cron schedule
4. The GitHub Actions runner (Ubuntu, free tier) generates the video and publishes it
5. Output files are either uploaded as artifacts or pushed back to the repo

### Schedule options
- Daily at a fixed time: `cron: '0 9 * * *'` (9am UTC)
- Weekdays only: `cron: '0 9 * * 1-5'`
- Can also trigger manually via `workflow_dispatch`

### Considerations
- GitHub Actions free tier: 2,000 minutes/month — one video run takes ~5-10 min, plenty of headroom
- faster-whisper runs on CPU (no GPU needed) — works on Actions runners
- HuggingFace image generation is remote API — no local GPU needed
- YouTube OAuth token needs to be stored as a secret (the pickle file serialised to base64)
- Theme rotation: maintain a `themes.txt` file, pop one theme per run, commit the updated file back

### Weekly Series Schedule (GitHub Actions)
- **Monday**: Upload long-form to YouTube (public)
- **Tuesday**: Publish Part 1 Short (public)
- **Wednesday**: Publish Part 2 Short (public)
- **Thursday**: Publish Part 3 Short (public)
- **Friday**: Publish Part 4 Short (public)
- **Saturday**: Publish Part 5 Short (public)
- **Sunday**: Generate next week's series (runs pipeline, uploads all as private, ready for Monday)

### Files to build
- `.github/workflows/weekly.yml` — generates series on Sunday, publishes on schedule Mon-Sat
- `.github/workflows/publish_part.yml` — triggered daily, changes one video from private to public
- `scripts/rotate_theme.py` — reads next theme from themes.txt, passes to series_run.py
- `scripts/encode_token.py` — helper to base64-encode youtube_token.pickle for GitHub Secrets
- `scripts/schedule_publish.py` — sets a queued video from private → public via YouTube API

---

## 10-Part Story Series (Shorts + Long-Form)

### Concept
A single story told across **10 x 1-minute episodes**, each a standalone short, that also assembles into one **10-minute long-form video** uploaded to YouTube.

### Distribution Strategy
- **TikTok / Instagram Reels / YouTube Shorts**: 10 episodes released daily (or every other day) — builds audience across the week, each part ends on a hook
- **YouTube long-form**: Full 10-minute video uploaded on the final day as the complete story — captures the watch-time and subscriber audience that prefers longer content
- Same channel. Two formats. One production run.

### Story Arc Mapping (10 parts × ~140 words each)
Each episode covers roughly one arc beat, expanded to fill a full minute:

| Episode | Arc Beat          | Function                                      |
|---------|-------------------|-----------------------------------------------|
| 1       | Stasis            | Establish world and character. End on a hint. |
| 2       | Trigger           | The inciting incident lands. End on shock.    |
| 3       | Quest             | Protagonist commits to action. End on resolve.|
| 4       | Surprise (part 1) | First complication surfaces. End on doubt.    |
| 5       | Surprise (part 2) | Complication deepens. End on crisis.          |
| 6       | Critical Choice   | The dark night of the soul. End mid-decision. |
| 7       | Climax (build)    | Everything converges. Tension peaks.          |
| 8       | Climax (break)    | The irreversible action. End on consequence.  |
| 9       | Reversal          | Fortune shifts. New reality begins to settle. |
| 10      | Resolution        | The new stasis. Final image. Door closes.     |

### Technical Requirements (to build when ready)
- `series_scriptwriter.py` — generates 10 connected scripts with consistent characters, world, and arc continuity
- `series_runner.py` — runs the full pipeline 10 times, numbering outputs sequentially
- `assembler.py` — concatenates all 10 final videos into the long-form version with chapter markers
- YouTube upload: 10 individual Shorts + 1 long-form, auto-scheduled for daily release
- Series title card per episode: "Part 1 of 10 — [Series Name]" burned into first 3 seconds

### Notes
- Characters and visual style (STYLE_PREFIX) must be locked across all 10 parts — same character anchor, same lighting language
- Each episode must end with a micro-cliffhanger or unresolved image (not a full resolution) until episode 10
- Long-form video benefits from YouTube's algorithm differently — higher RPM, chapter navigation, eligible for mid-roll ads
