"""
director_agent.py
------------------
Writes the horror story + scene/character spec using Google Gemini API.
FREE tier (gemini-1.5-flash): 15 requests/minute, 1M tokens/day.
Get your free key at: aistudio.google.com -> "Get API Key" (no credit card needed).
Set it as GitHub secret: GEMINI_API_KEY
"""
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import google.genai as genai
from google.genai import types
import yaml

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
  "human_note": "one-line first-person aside for a pinned comment, casual and personal",
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
      "appearance_lock": "extremely specific, reusable visual description: face shape, hair, skin, clothing, distinguishing marks. This exact string will be reused in every scene prompt.",
      "image_seed": 0,
      "voice_profile": {
        "age_band": "child | young | adult | old",
        "gender": "male | female",
        "baseline_emotion": "calm | anxious | weary | menacing | etc",
        "accent_note": "optional"
      }
    }
  ],
  "scenes": [
    {
      "scene_number": 1,
      "setting": "concrete visual description of location/time/lighting",
      "characters_present": ["char_1"],
      "action": "what physically happens",
      "camera": "static wide | slow push in | handheld shake | slow pan | extreme close-up",
      "narration": "narrator line for this scene, or null if none",
      "dialogue": [
        {"character_id": "char_1", "line": "...", "emotion": "fear|anger|calm|...", "intensity": 3}
      ],
      "sfx_cues": ["floorboard creak", "distant whisper"],
      "music_mood": "dread | tension_rising | sting | quiet_unease | release",
      "estimated_duration_seconds": 7
    }
  ]
}

Rules:
- 5 to 7 scenes total. Total estimated_duration_seconds must sum to 40-58.
- image_seed must be a different random integer per character.
- appearance_lock strings must be identical every time that character appears.
- The hook (first 5 seconds) must be the most disturbing/curious moment — never a slow setup.
- Avoid premises listed under "avoid" below.
- End on a sharp unresolved cut — no moral, no summary.
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
    persona = cfg.get("creator_persona", {})
    persona_block = ""
    if persona.get("enabled"):
        persona_block = f"""
This channel has a consistent narrator persona (use sparingly, not every line):
  Name/identity: {persona.get('name')}
  Tone: {persona.get('tone')}
  Sign-off style: {persona.get('signoff')}
"""
    style_notes = d.get("style_notes", "")
    return f"""
You are a director and screenwriter for a viral YouTube Shorts horror channel.
Niche: {cfg['channel']['niche']}.
This episode's narrative framing: {framing}.
{persona_block}
{style_notes}

Target length: {d['min_scenes']}-{d['max_scenes']} scenes, total runtime
{cfg['channel']['target_duration_seconds'][0]}-{cfg['channel']['target_duration_seconds'][1]} seconds.

Premises/twists already used — do NOT reuse:
{json.dumps(avoid, indent=2) if avoid else "(none yet)"}

{SCHEMA_INSTRUCTIONS}
""".strip()


def call_gemini(cfg: dict, prompt: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set. "
                           "Get a free key at aistudio.google.com and add it as a GitHub secret.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=cfg["director"]["model"],
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=1.0,
            max_output_tokens=4000,
        ),
    )
    text = response.text.strip()
    # Strip markdown fences if the model adds them
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text)


def validate(story: dict, cfg: dict) -> None:
    assert story.get("scenes"), "no scenes returned"
    n = len(story["scenes"])
    assert cfg["director"]["min_scenes"] <= n <= cfg["director"]["max_scenes"], \
        f"scene count {n} out of range"
    total = sum(s["estimated_duration_seconds"] for s in story["scenes"])
    lo, hi = cfg["channel"]["target_duration_seconds"]
    if not (lo - 5 <= total <= hi + 10):
        print(f"[warn] total duration {total}s outside target {lo}-{hi}s, continuing")
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
            story = call_gemini(cfg, prompt)
            validate(story, cfg)
            break
        except Exception as e:
            last_err = e
            print(f"[director_agent] attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    else:
        raise RuntimeError(f"director_agent failed after 3 attempts: {last_err}")

    run_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "output" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    story["visual_style"] = random.choice(cfg["image"]["style_lock_options"])
    (out_dir / "story.json").write_text(json.dumps(story, indent=2))

    if cfg.get("human_touches", {}).get("generate_pinned_comment_draft") and story.get("human_note"):
        (out_dir / "pinned_comment_DRAFT.txt").write_text(
            story["human_note"] + "\n\n(^ draft — edit into your own words before pinning)\n"
        )

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
    except Exception as e:
        print(f"[director_agent] FATAL: {e}", file=sys.stderr)
        sys.exit(1)
