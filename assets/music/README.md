# Background music

Drop royalty-free horror/tension music beds (mp3/wav, ~1-3 min loopable tracks)
into this folder. `audio_mixer.py` matches them to each story's `music_mood`
field by filename keywords, so name files descriptively, e.g.:

    dread_drone_01.mp3
    tension_rising_strings_02.mp3
    quiet_unease_ambient_01.mp3
    sting_jumpscare_01.mp3
    release_calm_outro_01.mp3

Good free, commercial-use-friendly sources to pull from (check each track's
specific license/attribution requirement before use):
  - YouTube Audio Library (studio.youtube.com -> Audio Library) — built for
    exactly this, no attribution needed for most tracks.
  - Pixabay Music (pixabay.com/music) — free license, royalty-free.
  - Free Music Archive (freemusicarchive.org) — check per-track license.
  - incompetech.com (Kevin MacLeod) — free with attribution under most licenses.

This is a one-time manual step (10-20 tracks is plenty) precisely so the
pipeline doesn't depend on a live "free music API" that could change terms
or vanish later.
