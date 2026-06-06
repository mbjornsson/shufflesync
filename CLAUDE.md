# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync --extra dev      # install all dependencies including pytest
uv run pytest            # run all tests
uv run pytest tests/test_sync.py   # run a single test file
uv run pytest -k test_name         # run a single test by name
uv run shufflesync "https://open.spotify.com/playlist/<id>"  # run the tool
```

## Architecture

shufflesync is a CLI tool that downloads a Spotify playlist and writes it onto a physical iPod (no iTunes required). The pipeline is:

**`cli.py`** → parses args, selects sync mode, calls into `downloader` then `sync`.

**`downloader.py`** → shells out to `spotdl` to download the playlist. Uses a persistent cache at `~/.shufflesync/cache/<playlist_id>/`. Two non-obvious constraints: both `--output` and `--m3u` paths passed to spotdl **must be relative** (spotdl sanitizes absolute paths that contain hidden-dir components, e.g. `~/.shufflesync`, rewriting them incorrectly). Track order comes from the m3u spotdl writes, not from a directory glob.

**`device.py`** → detects what's mounted under `/Volumes`. Shuffle 2G: has `iTunesSD`. Nano 1-3G: has an `iTunesDB` with `mhbd` magic and an all-zero signature region (`0x58..0xA0`). Devices with a non-zero signature region (nano 4G+, classic, touch) are refused entirely — we cannot produce the required hardware signature.

**`sync.py`** → two sync modes:
- `mirror_sync`: wipes `iPod_Control/Music`, copies all files, writes the database. Used for the shuffle (always) and nano with `--wipe`.
- `add_sync`: nano-only. Backs up the existing DB, parses it, prunes the previous run of this playlist (by track IDs from the manifest), copies new tracks into `F90/`, reassembles the full DB blob, updates the manifest. Idempotent: re-running the same playlist replaces just that playlist's tracks, other playlists are untouched.

**`itunessd.py`** → big-endian binary serializer for the iPod shuffle `iTunesSD` format.

**`itunesdb.py`** → little-endian binary serializer for the iPod nano `iTunesDB` format (mhbd → mhsd → mhlt/mhlp → mhit/mhyp → mhod/mhip). String mhods are UTF-16-LE. The master playlist's name is the iPod's device name (preserved from the existing DB, never overwritten with a hardcoded string).

**`itunesdb_reader.py`** → parser for existing `iTunesDB` on the nano. Used by `add_sync` to read current tracks/playlists and by `sync.existing_content` to count tracks before a `--wipe` confirmation.

**`manifest.py`** → JSON sidecar (`.shufflesync.json`) stored in `iPod_Control/iTunes/` on the device. Tracks which track IDs and file paths each shufflesync-managed playlist owns, enabling idempotent adds and safe pruning without touching user-managed content.

**`metadata.py`** → reads audio metadata (title, artist, album, duration, bitrate, etc.) via `mutagen`, used when building iTunesDB track entries.

## Key invariants

- The signature check in `device.detect_family` is a safety gate; never bypass it. Writing an unsigned DB to a signed device corrupts the device's library.
- `add_sync` always backs up before any mutation, and parses the existing DB before copying any files — if parsing fails, it raises before touching the device.
- spotdl output filename template uses `{artists} - {title}` (stable across playlist reordering). Never add `{list-position}` — it changes when the playlist is reordered, breaking the incremental cache.
- New tracks added by `add_sync` go in `F90/` with collision-safe `S####` names. `mirror_sync` uses `F00`–`Fnn` with `T####` names.
