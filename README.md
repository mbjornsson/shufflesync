# spotishuffle

Download a Spotify playlist and mirror it onto a 2nd-generation iPod shuffle —
no iTunes required.

## Requirements
- macOS, Python 3.9+
- `spotdl` (`pip install spotdl`) and `ffmpeg` (`brew install ffmpeg`)
- A 2nd-gen iPod shuffle already initialized by iTunes once (has an
  `iPod_Control` folder), mounted under `/Volumes`.

## Install
On macOS, Homebrew's Python is "externally managed" (PEP 668) and `pip`
may not be on your PATH (use `pip3` or `python3 -m pip`). The cleanest install
is a virtualenv:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```
`spotishuffle` is then on your PATH whenever the venv is active; re-run
`source .venv/bin/activate` in any new terminal.

To install into Homebrew Python directly instead, use `pip3 install --user -e .`
(add `--break-system-packages` if it reports `externally-managed-environment`).

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
