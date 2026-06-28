"""
pipeline.py
-----------
Runs the full chain for ONE video, end to end:
  director_agent -> image_gen -> voice_gen -> audio_mixer -> video_assembler -> youtube_uploader

Called by .github/workflows/publish.yml twice a day. Can also be run by hand:
    python src/pipeline.py
"""
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import director_agent  # noqa: E402
import image_gen  # noqa: E402
import voice_gen  # noqa: E402
import audio_mixer  # noqa: E402
import video_assembler  # noqa: E402
import youtube_uploader  # noqa: E402


def main() -> None:
    t0 = time.time()
    log = []

    def step(name, fn, *args):
        print(f"\n=== {name} ===")
        s = time.time()
        result = fn(*args)
        log.append({"step": name, "seconds": round(time.time() - s, 1)})
        return result

    try:
        story_path = step("director_agent", director_agent.run)
        step("image_gen", image_gen.run, str(story_path))
        manifest_path = step("voice_gen", voice_gen.run, str(story_path))
        step("audio_mixer", audio_mixer.run, str(story_path), str(manifest_path))
        video_path = step("video_assembler", video_assembler.run, str(story_path))
        video_id = step("youtube_uploader", youtube_uploader.run, str(story_path), str(video_path))

        print(f"\n[pipeline] DONE in {time.time() - t0:.1f}s -> https://youtu.be/{video_id}")
        for l in log:
            print(f"  - {l['step']}: {l['seconds']}s")

    except Exception:
        print("\n[pipeline] FAILED")
        traceback.print_exc()
        # Exit nonzero so the GitHub Actions run is visibly marked failed —
        # deliberately does NOT retry-with-different-content automatically,
        # since a silent retry loop is exactly the "no human ever looks at this"
        # pattern that creates risk (see README "Monetization risk").
        sys.exit(1)


if __name__ == "__main__":
    main()
