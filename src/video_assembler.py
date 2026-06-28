"""
video_assembler.py
-------------------
Takes:
  - output/<run_id>/images/scene_NN.jpg   (one still per scene)
  - output/<run_id>/audio/scene_timing.json (start/end ms per scene)
  - output/<run_id>/audio/captions.json     (absolute word timestamps)
  - output/<run_id>/audio/final_mix.mp3     (full audio track)
and produces output/<run_id>/final_video.mp4 — a 1080x1920 vertical video
with a slow Ken Burns zoom/pan per scene and burned-in word-highlight
captions, muxed to the final audio.

This is the "free, unlimited" video layer: no generative video model, no
per-second cost, no quota. When you're ready to spend a little budget on
true generative motion / lip-sync, swap this module for a call to a
reference-image-conditioned video API — director_agent.py's story.json
and the character appearance_lock / image_seed fields are already shaped
to feed straight into those tools (Kling Elements, Veo Ingredients-to-Video,
Seedance multi-reference, etc.).
"""
import json
import subprocess
import sys
from pathlib import Path

CANVAS_W, CANVAS_H = 1080, 1920
FPS = 30


def build_caption_filters(captions: list[dict], scene_start_ms: float, scene_end_ms: float) -> str:
    """drawtext filters for words whose timestamp falls inside this scene's clip."""
    filters = []
    for c in captions:
        if scene_start_ms <= c["start_ms"] < scene_end_ms:
            start_s = (c["start_ms"] - scene_start_ms) / 1000
            end_s = (c["end_ms"] - scene_start_ms) / 1000 + 0.05
            word = c["word"].replace("'", r"\'").replace(":", r"\:")
            filters.append(
                "drawtext=text='%s':fontcolor=white:fontsize=64:font='DejaVu Sans Bold':"
                "borderw=4:bordercolor=black:x=(w-text_w)/2:y=h-340:"
                "enable='between(t,%.3f,%.3f)'" % (word, start_s, end_s)
            )
    return ",".join(filters)


def make_scene_clip(image_path: Path, duration_s: float, caption_filters: str, out_path: Path) -> None:
    zoom_frames = int(duration_s * FPS)
    zoompan = (
        f"zoompan=z='min(zoom+0.0008,1.15)':d={zoom_frames}:s={CANVAS_W}x{CANVAS_H}:fps={FPS}"
    )
    vf = f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,crop={CANVAS_W}:{CANVAS_H},{zoompan}"
    if caption_filters:
        vf += "," + caption_filters
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
        "-vf", vf, "-t", str(duration_s),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def concat_clips(clip_paths: list[Path], out_path: Path) -> None:
    list_file = out_path.parent / "concat_list.txt"
    list_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths))
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def mux_audio(video_path: Path, audio_path: Path, out_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def run(story_path: str) -> Path:
    run_dir = Path(story_path).parent
    story = json.loads(Path(story_path).read_text())
    timing = json.loads((run_dir / "audio" / "scene_timing.json").read_text())
    captions = json.loads((run_dir / "audio" / "captions.json").read_text())

    work_dir = run_dir / "video_tmp"
    work_dir.mkdir(exist_ok=True)
    clip_paths = []

    for scene, t in zip(story["scenes"], timing):
        sn = scene["scene_number"]
        duration_s = max((t["end_ms"] - t["start_ms"]) / 1000, 1.5)
        image_path = run_dir / "images" / f"scene_{sn:02d}.jpg"
        caption_filters = build_caption_filters(captions, t["start_ms"], t["end_ms"])
        clip_path = work_dir / f"scene_{sn:02d}.mp4"
        print(f"[video_assembler] rendering scene {sn} ({duration_s:.1f}s)")
        make_scene_clip(image_path, duration_s, caption_filters, clip_path)
        clip_paths.append(clip_path)

    silent_video = work_dir / "silent_full.mp4"
    concat_clips(clip_paths, silent_video)

    final_path = run_dir / "final_video.mp4"
    mux_audio(silent_video, run_dir / "audio" / "final_mix.mp3", final_path)

    print(f"[video_assembler] wrote {final_path}")
    return final_path


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python video_assembler.py <path/to/story.json>")
        sys.exit(1)
    run(sys.argv[1])
