"""
audio_mixer.py
--------------
Builds the FULL audio track for the video:
  - lays voice lines back-to-back per scene (timing drives video_assembler.py)
  - picks a background music bed by matching scene/story mood to filenames in
    assets/music/ (no live API call -> nothing here ever silently breaks or
    runs out of quota)
  - picks one-shot SFX per scene the same way, from assets/sfx/
  - ducks music under dialogue, loops/crossfades music to total length

Filename convention for your dropped-in assets (see assets/*/README.md):
  assets/music/dread_01.mp3, assets/music/tension_rising_02.mp3, ...
  assets/sfx/floorboard_creak.mp3, assets/sfx/distant_whisper.mp3, ...
The matcher does simple substring/keyword scoring against the scene's
`music_mood` and `sfx_cues` fields, so name your files descriptively.
"""
import json
import random
import re
import sys
from pathlib import Path

import yaml
from pydub import AudioSegment

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def tokenize(s: str) -> set[str]:
    return set(re.findall(r"[a-z]+", s.lower()))


def best_match(query: str, files: list[Path]) -> Path | None:
    if not files:
        return None
    q = tokenize(query)
    scored = []
    for f in files:
        score = len(q & tokenize(f.stem))
        scored.append((score, f))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_score = scored[0][0]
    candidates = [f for s, f in scored if s == top_score] if top_score > 0 else files
    return random.choice(candidates)


def load_audio_dir(dirpath: Path) -> list[Path]:
    if not dirpath.exists():
        return []
    return [p for p in dirpath.iterdir() if p.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a")]


def run(story_path: str, voice_manifest_path: str) -> Path:
    cfg = load_config()
    story = json.loads(Path(story_path).read_text())
    manifest = json.loads(Path(voice_manifest_path).read_text())

    music_files = load_audio_dir(ROOT / cfg["audio"]["music_dir"])
    sfx_files = load_audio_dir(ROOT / cfg["audio"]["sfx_dir"])
    if not music_files:
        print("[audio_mixer] WARNING: no files in assets/music/ — final video will have no score. "
              "See assets/music/README.md.")
    if not sfx_files:
        print("[audio_mixer] WARNING: no files in assets/sfx/ — final video will have no SFX. "
              "See assets/sfx/README.md.")

    out_dir = Path(story_path).parent / "audio"
    timeline = AudioSegment.silent(duration=0)
    scene_timing = []  # for video_assembler: (scene_number, start_ms, end_ms)

    lines_by_scene: dict[int, list[dict]] = {}
    for line in manifest:
        lines_by_scene.setdefault(line["scene_number"], []).append(line)

    gap_ms = 350  # small breathing room between lines/scenes
    captions = []  # absolute-time word list for video_assembler.py's burned-in captions

    for scene in story["scenes"]:
        sn = scene["scene_number"]
        scene_start = len(timeline)
        scene_audio = AudioSegment.silent(duration=0)

        for line in lines_by_scene.get(sn, []):
            line_abs_start_ms = scene_start + len(scene_audio)
            clip = AudioSegment.from_file(ROOT / line["file"])
            for w in line.get("words", []):
                w_start = line_abs_start_ms + w["start_s"] * 1000
                captions.append({
                    "scene_number": sn,
                    "word": w["word"],
                    "start_ms": w_start,
                    "end_ms": w_start + w["duration_s"] * 1000,
                })
            scene_audio += clip + AudioSegment.silent(duration=gap_ms)

        if sfx_files and scene.get("sfx_cues"):
            sfx_path = best_match(" ".join(scene["sfx_cues"]), sfx_files)
            if sfx_path:
                sfx_clip = AudioSegment.from_file(sfx_path)[:2500]
                scene_audio = scene_audio.overlay(sfx_clip, position=0, gain_during_overlay=-3)

        timeline += scene_audio
        scene_timing.append({"scene_number": sn, "start_ms": scene_start, "end_ms": len(timeline)})

    total_ms = max(len(timeline), 1000)

    if music_files:
        mood = story["scenes"][0].get("music_mood", "dread")
        music_path = best_match(mood, music_files)
        bed = AudioSegment.from_file(music_path)
        looped = AudioSegment.silent(duration=0)
        while len(looped) < total_ms:
            looped += bed
        looped = looped[:total_ms]
        ducked = looped + cfg["audio"]["music_duck_db"]
        final_mix = ducked.overlay(timeline)
    else:
        final_mix = timeline

    final_mix = final_mix + cfg["audio"]["master_volume_db"]
    out_path = out_dir / "final_mix.mp3"
    final_mix.export(out_path, format="mp3")

    timing_path = out_dir / "scene_timing.json"
    timing_path.write_text(json.dumps(scene_timing, indent=2))

    captions_path = out_dir / "captions.json"
    captions_path.write_text(json.dumps(captions, indent=2))

    print(f"[audio_mixer] wrote {out_path} ({total_ms / 1000:.1f}s), {timing_path}, {captions_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python audio_mixer.py <story.json> <audio/manifest.json>")
        sys.exit(1)
    run(sys.argv[1], sys.argv[2])
