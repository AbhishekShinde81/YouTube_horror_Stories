"""
director_agent.py
------------------
The "writer + director" of the pipeline.

Calls Claude to produce ONE complete short-horror-story spec as JSON:
  - title / hook / SEO metadata
  - a character bible (locked appearance + voice profile per character,
    used downstream by image_gen.py and voice_gen.py to stay consistent)
  - a scene-by-scene shot list (setting, action, camera, dialogue, emotion,
    sfx cues, music mood, duration)

It also reads state/history.json so it never repeats a premise/twist it has
already used, and keeps rotating the narrative *framing* (first-person,
folklore, found-footage...) so the channel doesn't look templated to
YouTube's inauthentic-content systems (see README "Monetization risk").
"""
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from anthropic import Anthropic

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
HISTORY_PATH = ROOT / "state" / "history.json"

FRAMINGS = [
    "first-person 'this happened to me' confession",
    "third-person narrated local folklore / urban legend",
    "found-footage / diary-entry style with timestamps",
    "true-crime-style narrated reconstruction",
    "second-person 'you are the one this happens to' framing",
]

SCHEMA_INSTRUCTIONS = """
Return ONLY valid JSON (no markdown fences, no commentary) matching exactly this shape:

{
  "title": "internal working title",
  "youtube_title": "SEO/curiosity title, <=70 chars, no clickbait lies",
  "description": "2-3 sentence YouTube description",
  "tags": ["...", "..."],
  "thumbnail_concept": "one sentence describing the thumbnail-worthy frozen moment",
  "framing": "which framing style you used",
  "hook": {
    "text": "the exact first line(s) spoken/narrated in the first ~5 seconds",
    "visual": "what's on screen during the hook"
  },
  "characters": [
    {
      "id": "char_1",
      "name": "...",
      "role": "protagonist | other | entity",
      "age": 0,
      "gender": "male | female | nonbinary | unspecified",
      "appearance_lock": "extremely specific, reusable visual description: face shape, hair, skin, clothing, distinguishing marks. This exact string will be reused in every scene's image prompt to keep the character consistent, so be concrete and visual, not poetic.",
      "image_seed": 0,
      "voice_profile": {
        "age_band": "child | young | adult | old",
        "gender": "male | female",
        "baseline_emotion": "calm | anxious | weary | menacing | etc",
        "accent_note": "optional, e.g. 'flat midwestern US'"
      }
    }
  ],
  "scenes": [
    {
      "scene_number": 1,
      "setting": "concrete visual description of location/time/lighting for image generation",
      "characters_present": ["char_1"],
      "action": "what physically happens, for the image prompt and camera direction",
      "camera": "static wide | slow push in | handheld shake | slow pan | extreme close-up",
      "narration": "narrator line for this scene, or null if none",
      "dialogue": [
        {"character_id": "char_1", "line": "...", "emotion": "fear|anger|calm|...", "intensity": 1-5}
      ],
      "sfx_cues": ["floorboard creak", "distant whisper"],
      "music_mood": "dread | tension_rising | sting | quiet_unease | release",
      "estimated_duration_seconds": 7
    }
  ]
}

Rules:
- 5 to 7 scenes total. Total estimated_duration_seconds across scenes must sum to 40-58.
- image_seed must be a different random-looking integer per character, fixed for the whole story.
- appearance_lock strings must stay byte-for-byte identical every time that character is referenced
  (image_gen.py will literally concatenate this string into every prompt for that character).
- The hook (first 5 seconds) must be the single most disturbing/curious image or line in the story,
  not the slowest. Do not "set the scene" before hooking.
- Avoid premises and twists listed under "avoid" below.
- End on a cut, not a moral or a summary — short-form horror should feel unresolved/sharp.
"""


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def load_history() -> dict:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text())
    return {"entries": []}


def save_history(history: dict, cfg: dict) -> None:
    window = cfg["run"]["avoid_repeat_window"]
    history["entries"] = history["entries"][-window:]
    HISTORY_PATH.parent.mkdir(exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=2))


def build_prompt(cfg: dict, history: dict) -> str:
    avoid = [e["premise"] for e in history["entries"][-cfg["run"]["avoid_repeat_window"]:]]
    framing = random.choice(FRAMINGS)
    d = cfg["director"]
    return f"""
You are a director and screenwriter for a viral YouTube Shorts horror channel.
Niche: {cfg['channel']['niche']}.
This episode's narrative framing: {framing}.

{d['style_notes']}

Target length: {d['min_scenes']}-{d['max_scenes']} scenes, total spoken/visual runtime
{cfg['channel']['target_duration_seconds'][0]}-{cfg['channel']['target_duration_seconds'][1]} seconds.

Premises/twists already used recently — do NOT reuse or lightly reskin these:
{json.dumps(avoid, indent=2) if avoid else "(none yet)"}

{SCHEMA_INSTRUCTIONS}
""".strip()


def call_claude(cfg: dict, prompt: str) -> dict:
    client = Anthropic()  # reads ANTHROPIC_API_KEY from env
    resp = client.messages.create(
        model=cfg["director"]["model"],
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def validate(story: dict, cfg: dict) -> None:
    assert story.get("scenes"), "no scenes returned"
    n = len(story["scenes"])
    assert cfg["director"]["min_scenes"] <= n <= cfg["director"]["max_scenes"], f"scene count {n} out of range"
    total = sum(s["estimated_duration_seconds"] for s in story["scenes"])
    lo, hi = cfg["channel"]["target_duration_seconds"]
    if not (lo - 5 <= total <= hi + 10):
        print(f"[warn] total duration {total}s is outside target {lo}-{hi}s, continuing anyway")
    char_ids = {c["id"] for c in story["characters"]}
    for s in story["scenes"]:
        for cid in s.get("characters_present", []):
            assert cid in char_ids, f"scene references unknown character {cid}"
    for c in story["characters"]:
        if not c.get("image_seed"):
            c["image_seed"] = random.randint(1, 2_147_483_647)


def run() -> Path:
    cfg = load_config()
    history = load_history()
    prompt = build_prompt(cfg, history)

    last_err = None
    for attempt in range(3):
        try:
            story = call_claude(cfg, prompt)
            validate(story, cfg)
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[director_agent] attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    else:
        raise RuntimeError(f"director_agent failed after 3 attempts: {last_err}")

    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "output" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "story.json").write_text(json.dumps(story, indent=2))

    history["entries"].append({
        "run_id": run_id,
        "title": story["title"],
        "premise": story.get("description", "")[:300],
        "framing": story.get("framing", ""),
    })
    save_history(history, cfg)

    print(f"[director_agent] wrote {out_dir / 'story.json'}")
    return out_dir / "story.json"


if __name__ == "__main__":
    try:
        path = run()
        print(path)
    except Exception as e:  # noqa: BLE001
        print(f"[director_agent] FATAL: {e}", file=sys.stderr)
        sys.exit(1)
