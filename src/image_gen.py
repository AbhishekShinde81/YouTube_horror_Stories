"""
image_gen.py
------------
Generates one keyframe image per scene using Pollinations.ai's free,
no-API-key text-to-image endpoint.

HONEST LIMITATION (read this):
Free text-to-image has no real "memory" of a character's face between calls.
The only free levers we have for consistency are:
  1. Reusing the exact same `appearance_lock` description text every time
     a character appears (director_agent.py guarantees this string is
     identical across scenes).
  2. Reusing the exact same numeric seed per character.
This gets you "recognizably the same character" most of the time, not
pixel-perfect identity. If/when you're ready to spend a little budget,
swap this module for a reference-image-conditioned model (Kling Elements,
Veo "Ingredients to Video", Seedance multi-reference, etc.) — the rest of
the pipeline (voice_gen, audio_mixer, video_assembler) doesn't need to change,
since they just consume image files from output/<run_id>/images/.
"""
import sys
import time
import urllib.parse
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def build_prompt(scene: dict, characters: dict, cfg: dict) -> str:
    cfg_img = cfg["image"]
    char_descs = []
    for cid in scene.get("characters_present", []):
        c = characters[cid]
        char_descs.append(f"{c['name']}: {c['appearance_lock']}")
    parts = [
        cfg_img["style_lock"],
        scene["setting"],
        scene["action"],
        "; ".join(char_descs),
        f"camera: {scene.get('camera', 'static wide')}",
        "vertical 9:16 composition",
    ]
    return ", ".join(p for p in parts if p)


def seed_for_scene(scene: dict, characters: dict) -> int:
    # Use the first character's locked seed for the whole scene so the
    # protagonist stays as visually stable as possible across shots.
    present = scene.get("characters_present", [])
    if present:
        return characters[present[0]]["image_seed"]
    return 42


def generate_image(prompt: str, seed: int, cfg: dict, out_path: Path) -> None:
    cfg_img = cfg["image"]
    encoded = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={cfg_img['width']}&height={cfg_img['height']}"
        f"&seed={seed}&nologo=true"
    )
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=90)
            r.raise_for_status()
            out_path.write_bytes(r.content)
            return
        except Exception as e:  # noqa: BLE001
            print(f"[image_gen] attempt {attempt + 1} failed for {out_path.name}: {e}")
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"image_gen: all attempts failed for {out_path}")


def run(story_path: str) -> Path:
    import json
    cfg = load_config()
    story = json.loads(Path(story_path).read_text())
    characters = {c["id"]: c for c in story["characters"]}

    out_dir = Path(story_path).parent / "images"
    out_dir.mkdir(exist_ok=True)

    for scene in story["scenes"]:
        prompt = build_prompt(scene, characters, cfg)
        seed = seed_for_scene(scene, characters)
        out_path = out_dir / f"scene_{scene['scene_number']:02d}.jpg"
        print(f"[image_gen] scene {scene['scene_number']}: {prompt[:90]}...")
        generate_image(prompt, seed, cfg, out_path)

    print(f"[image_gen] wrote images to {out_dir}")
    return out_dir


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python image_gen.py <path/to/story.json>")
        sys.exit(1)
    run(sys.argv[1])
