# shufflesync

Download a Spotify playlist and mirror it onto an iPod — no iTunes required.
shufflesync auto-detects the attached device and writes the right database
format for it.

## Supported devices
- **2nd-gen iPod shuffle** — writes the `iTunesSD` database.
- **iPod nano, 1st–3rd gen** — writes the `iTunesDB` database, including a
  playlist named after the source Spotify playlist.

**Not supported:** checksummed iPods (nano 4th gen and later, iPod classic, iPod
touch). Their database requires a hardware signature shufflesync cannot produce.
shufflesync detects these and **refuses them with an error** — it won't touch
their music.

## Requirements
- macOS, Python 3.9+
- [`uv`](https://docs.astral.sh/uv/) (`brew install uv`)
- `ffmpeg` (`brew install ffmpeg`) — `spotdl` itself is installed for you by `uv`
- A supported iPod already initialized by iTunes once (has an `iPod_Control`
  folder), mounted under `/Volumes`.
- **Disk use enabled.** If Finder/Music manages the iPod, its disk stays
  unmounted (it only appears for a moment during a Finder sync). Select the
  iPod in Finder, turn on **"Enable disk use"** (or **"Manually manage
  music"**), and click **Apply** so the volume stays mounted under `/Volumes`.
  This is a one-time, on-device setting. shufflesync will try to mount an
  attached-but-unmounted iPod automatically, but it cannot toggle this setting.
- **Old nano that modern macOS won't manage?** Put it into disk mode on the
  device itself so it mounts as a USB drive: toggle the **Hold** switch on then
  off, reset with **Menu+Select**, then immediately hold **Select+Play** to
  enter disk mode.

## Install
From the project directory:
```bash
uv sync
```
That's it. `uv` creates a `.venv`, installs Python (if needed), and installs
shufflesync plus its dependencies from the pinned `uv.lock` — no manual
virtualenv or `pip` to deal with.

## Use
Run the command with `uv run` (no need to activate anything):
```bash
uv run shufflesync "https://open.spotify.com/playlist/<id>"
```
Prefer a bare `shufflesync`? Activate the venv once per terminal with
`source .venv/bin/activate`, then:
```bash
shufflesync "https://open.spotify.com/playlist/<id>"
```
It downloads the playlist, finds your mounted iPod, **replaces** its music
with the playlist (mirror sync), and writes the device database. Eject the
iPod before unplugging.

### Limiting how many tracks
By default the whole playlist is downloaded. To download only some of it:
```bash
uv run shufflesync "https://open.spotify.com/playlist/<id>" --count 25
```
That takes the first 25 tracks in playlist order. Add `--random` to pick 25 at
random instead:
```bash
uv run shufflesync "https://open.spotify.com/playlist/<id>" --count 25 --random
```
If `--count` is larger than the playlist, the whole playlist is downloaded.

### Adding to the nano without erasing (`--add`)
By default a sync **replaces** everything on the device. On the **iPod nano**
you can instead *add* a playlist while keeping your existing music:
```bash
uv run shufflesync "https://open.spotify.com/playlist/<id>" --add
```
This preserves your existing library and adds the playlist as its own entry
under Playlists. It is **idempotent per playlist**: running `--add` again for the
same playlist refreshes it (removing the tracks the previous run added) instead
of piling up duplicates, and different playlists accumulate independently.

Before each `--add`, the current database is backed up on the device under
`iPod_Control/iTunes/shufflesync-backup/<timestamp>/`. `--add` is nano-only —
the shuffle is always a full mirror.

## Develop
```bash
uv sync --extra dev   # install test dependencies
uv run pytest         # run the tests
uv add <package>      # add a dependency (updates pyproject.toml + uv.lock)
```

## Notes
- Spotify audio is DRM-protected; like all such tools, `spotdl` matches each
  track and downloads audio from YouTube tagged with Spotify metadata.
- Mirror sync wipes existing music on the device every run.
- If the playlist exceeds device capacity, tracks are added in order until full
  and the rest are skipped with a warning.
