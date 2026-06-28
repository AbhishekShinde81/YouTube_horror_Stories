"""
voice_gen.py
------------
Generates one audio clip PER LINE (narration or dialogue) using edge-tts
(Microsoft Edge's neural TTS — free, unlimited, no API key required).

- Character age/gender -> voice selection via config.yaml's voice_map.
- "Emotion"/"intensity" from the scene spec is approximated with rate/pitch/volume
  (edge-tts doesn't do full emotional acting like ElevenLabs; this is the honest
  free-tier ceiling — see README for the paid upgrade path).
- Captures word-boundary timestamps from edge-tts so video_assembler.py can render
  accurately timed burned-in captions (this part IS fully free and fully accurate,
  it's a real feature of the library, not an approximation).
"""
import asyncio
import json
import sys
from pathlib import Path

import edge_tts
import yaml

ROOT = Path(__file__).resolve().parent.parent

EMOTION_PROSODY = {
    # emotion -> (rate %, pitch Hz offset)
    "calm": (0, 0),
    "anxious": (8, 20),
    "fear": (12, 35),
    "menacing": (-8, -25),
    "anger": (10, 15),
    "weary": (-10, -15),
    "sad": (-8, -10),
    "default": (0, 0),
}


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def pick_voice(character: dict, cfg: dict) -> str:
    vp = character["voice_profile"]
    key = f"{vp['gender']}_{vp['age_band']}" if vp["age_band"] != "child" else "child"
    return cfg["voice"]["voice_map"].get(key, cfg["voice"]["narrator_voice"])


def prosody_for(emotion: str, intensity: int) -> tuple[str, str]:
    rate, pitch = EMOTION_PROSODY.get(emotion, EMOTION_PROSODY["default"])
    scale = max(intensity, 1) / 3.0
    rate = int(rate * scale)
    pitch = int(pitch * scale)
    rate_str = f"{'+' if rate >= 0 else ''}{rate}%"
    pitch_str = f"{'+' if pitch >= 0 else ''}{pitch}Hz"
    return rate_str, pitch_str


async def synth_line(text: str, voice: str, rate: str, pitch: str, out_path: Path) -> list[dict]:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    word_marks = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_marks.append({
                    "word": chunk["text"],
                    "start_s": chunk["offset"] / 10_000_000,
                    "duration_s": chunk["duration"] / 10_000_000,
                })
    return word_marks


async def run_async(story_path: str) -> Path:
    cfg = load_config()
    story = json.loads(Path(story_path).read_text())
    characters = {c["id"]: c for c in story["characters"]}

    out_dir = Path(story_path).parent / "audio" / "lines"
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = []

    for scene in story["scenes"]:
        sn = scene["scene_number"]
        line_idx = 0

        if scene.get("narration"):
            line_idx += 1
            fname = f"scene_{sn:02d}_line_{line_idx:02d}_narration.mp3"
            voice = cfg["voice"]["narrator_voice"]
            rate, pitch = prosody_for("calm", 2)
            words = await synth_line(scene["narration"], voice, rate, pitch, out_dir / fname)
            manifest.append({
                "scene_number": sn, "speaker": "narrator", "voice": voice,
                "text": scene["narration"], "file": str((out_dir / fname).relative_to(ROOT)),
                "words": words,
            })

        for d in scene.get("dialogue", []):
            line_idx += 1
            character = characters[d["character_id"]]
            voice = pick_voice(character, cfg)
            rate, pitch = prosody_for(d.get("emotion", "calm"), d.get("intensity", 3))
            fname = f"scene_{sn:02d}_line_{line_idx:02d}_{character['id']}.mp3"
            words = await synth_line(d["line"], voice, rate, pitch, out_dir / fname)
            manifest.append({
                "scene_number": sn, "speaker": character["id"], "voice": voice,
                "text": d["line"], "emotion": d.get("emotion"),
                "file": str((out_dir / fname).relative_to(ROOT)), "words": words,
            })

    manifest_path = out_dir.parent / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"[voice_gen] wrote {len(manifest)} lines, manifest at {manifest_path}")
    return manifest_path


def run(story_path: str) -> Path:
    return asyncio.run(run_async(story_path))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python voice_gen.py <path/to/story.json>")
        sys.exit(1)
    run(sys.argv[1])
