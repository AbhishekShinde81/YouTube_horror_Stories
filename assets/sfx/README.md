# Sound effects

Drop short (1-4 second) royalty-free SFX clips here. `audio_mixer.py` matches
them to each scene's `sfx_cues` list by filename keywords, e.g.:

    floorboard_creak.mp3
    distant_whisper.mp3
    door_slam.mp3
    static_burst.mp3
    heartbeat_thump.mp3
    silence_drop.mp3

Good free sources:
  - freesound.org (CC0 / CC-BY tracks — filter by license, attribute if required)
  - Pixabay Sound Effects (pixabay.com/sound-effects) — free license
  - YouTube Audio Library's sound effects tab

Same reasoning as assets/music/README.md: a one-time manual pull of ~20-30
clips keeps the pipeline from depending on a live API.
