# Horror Shorts Agent

An end-to-end pipeline that writes a short horror story, generates
consistent-ish character images, generates voiced dialogue + narration,
mixes in music/SFX, assembles a vertical video, and uploads it to your
YouTube channel — on a schedule, via GitHub Actions (free).

**Read this whole file before turning on the schedule.** Three sections
below (Limitations, YouTube setup, Monetization risk) are not boilerplate —
they directly affect whether this works the way you expect.

---

## What's actually free here, and what isn't

| Component         | Tool                          | Free?                                   |
|--------------------|-------------------------------|------------------------------------------|
| Story/scene writing | Claude (Anthropic API)        | **Paid**, but cheap — a few cents/video |
| Character/scene images | Pollinations.ai              | Free, no key, no quota                  |
| Voice (TTS)        | edge-tts (Microsoft Edge TTS) | Free, unlimited, no key                 |
| Music/SFX          | Your own downloaded files     | Free (one-time manual download)         |
| Video assembly     | ffmpeg                        | Free                                    |
| Hosting/scheduling | GitHub Actions                | Free for public repos                   |
| YouTube upload     | YouTube Data API v3            | Free (well within daily quota at 2/day) |

The only recurring cost is Claude API calls for the script — at 2 videos/day
that's a small monthly cost, not zero. There is no free way to do the
writing step at "premium quality" with zero spend; the LLM call is what
makes the story good. Everything downstream of the script is genuinely free.

## Limitations you should know about (don't skip this)

1. **Character consistency is "pretty good," not "perfect."** Free
   text-to-image has no memory between calls. We fake consistency with a
   locked appearance description + a fixed seed per character. Expect
   minor drift across scenes, not pixel-identical faces. If/when you want
   true identity-locked video with lip-sync, swap `image_gen.py` /
   `video_assembler.py` for a reference-image-conditioned model (Kling
   Elements, Veo "Ingredients to Video," Seedance multi-reference) — the
   `story.json` schema already has everything (appearance_lock, image_seed,
   voice_profile) those tools want as input.
2. **The video layer is animated stills (Ken Burns pan/zoom), not generative
   motion.** This is a deliberate, honest choice for the free tier — there
   is currently no free, unlimited, commercially-usable generative video
   API. Plenty of successful horror/true-crime Shorts channels use exactly
   this format, so it's not a quality compromise so much as a different
   (and proven) style.
3. **edge-tts emotion is approximated** via rate/pitch, not full emotional
   performance like ElevenLabs. It's good, not "indistinguishable from a
   human actor."

## YouTube setup (one-time, must be done by you)

I (Claude) can't create Google credentials or authorize YouTube access on
your behalf — that's by design, for your account's security.

1. Go to console.cloud.google.com, create a project, enable the
   **YouTube Data API v3**.
2. Create OAuth credentials -> Application type **Desktop app** -> download
   the JSON, save it as `client_secret.json` at the project root.
3. On your own machine (needs a browser, just once):
   ```
   pip install -r requirements.txt
   python src/youtube_uploader.py --authorize
   ```
   This opens a browser, you log into the YouTube account you want to post
   to, and it writes `token.json`.
4. In your GitHub repo -> Settings -> Secrets and variables -> Actions, add:
   - `ANTHROPIC_API_KEY` — from console.anthropic.com
   - `YOUTUBE_TOKEN_JSON` — paste the entire contents of `token.json`

## First run — do this before turning on the schedule

```
pip install -r requirements.txt
# add a few files to assets/music/ and assets/sfx/ (see their README.md)
export ANTHROPIC_API_KEY=sk-ant-...
python src/youtube_uploader.py --authorize   # one-time
python src/pipeline.py
```
Watch the output video. Adjust `config.yaml` (style_notes, voice_map, etc.)
until you're happy. Only then push to GitHub and let the workflow run on
its schedule.

`config.yaml`'s `run.publish_mode: review` uploads as **unlisted** by
default, specifically so you can spot-check outputs before anyone sees them.
Switch it to `"public"` only once you trust the pipeline's output quality —
see the next section for why this matters for more than just quality control.

## Monetization risk — please read before you chase "revenue ASAP"

You asked for zero intervention, twice-daily uploads, same structure every
time, optimized purely for the first-5-seconds hook. I want to flag clearly:
**that exact pattern is what YouTube's "inauthentic content" policy
(renamed from "repetitious content" in July 2025, aggressively enforced
through 2026, with a wave of channel terminations in January 2026) is
designed to detect** — mass-produced, templated, AI-driven content with no
human creative input, even if every individual video is original. This is a
channel-level evaluation, not per-video, and the penalty is losing
monetization eligibility entirely (with a 30-day reapplication wait), not
just one flagged video.

This pipeline is built to reduce that risk, but the policy is ultimately
about *your* judgment, not the code's:
- `director_agent.py` rotates narrative framing and explicitly avoids
  reusing premises/twists — vary it further over time (new sub-niches,
  occasional different visual style, etc.).
- Default `publish_mode: review` keeps a human (you) in the loop before
  anything goes public.
- The synthetic-content disclosure checkbox is set automatically — don't
  turn that off; misrepresenting AI content as real is a separate, harsher
  policy violation.
- Realistically, plan to spend a few minutes a day actually watching what
  gets made, at least early on. "Zero intervention forever" is the
  highest-risk way to run this, both for monetization and for catching a
  bad/broken video before it publishes.

Separately: YPP eligibility itself needs 1,000 subscribers + (4,000 public
watch hours in 12 months OR 10M Shorts views in 90 days) for full ad
revenue — no pipeline shortcuts that; it's a platform threshold you grow
into. The early-access tier (500 subs + 3M Shorts views/90 days) unlocks
fan-funding tools sooner, but not ad revenue.

## Repo layout

```
config.yaml                  # all tunables
src/director_agent.py        # writes story + scene/character JSON spec
src/image_gen.py              # free text-to-image per scene
src/voice_gen.py               # free TTS per line, word-timestamps for captions
src/audio_mixer.py             # mixes voice + local music/SFX
src/video_assembler.py         # Ken Burns + captions + final mux (ffmpeg)
src/youtube_uploader.py        # uploads via YouTube Data API v3
src/pipeline.py                 # runs all of the above in order
.github/workflows/publish.yml  # cron schedule, twice a day
assets/music/, assets/sfx/     # you drop free royalty-free files here once
state/history.json              # auto-maintained, avoids repeating premises
output/<run_id>/                # story.json, images, audio, final_video.mp4
```
