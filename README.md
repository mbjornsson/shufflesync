# spotishuffle

Download a Spotify playlist and mirror it onto a 2nd-generation iPod shuffle —
no iTunes required.

## Requirements
- macOS, Python 3.9+
- `spotdl` (`pip install spotdl`) and `ffmpeg` (`brew install ffmpeg`)
- A 2nd-gen iPod shuffle already initialized by iTunes once (has an
  `iPod_Control` folder), mounted under `/Volumes`.

## Install
```bash
pip install -e .
```

## Use
```bash
spotishuffle "https://open.spotify.com/playlist/<id>"
```
It downloads the playlist, finds your mounted shuffle, **replaces** its music
with the playlist (mirror sync), and writes the device database. Eject the
shuffle before unplugging.

## Notes
- Spotify audio is DRM-protected; like all such tools, `spotdl` matches each
  track and downloads audio from YouTube tagged with Spotify metadata.
- Mirror sync wipes existing music on the device every run.
- If the playlist exceeds device capacity, tracks are added in order until full
  and the rest are skipped with a warning.
