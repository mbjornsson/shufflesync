# Track-count selection design

## Goal

Let the user limit how many tracks are downloaded from a Spotify playlist, and
optionally pick those tracks at random instead of taking the first N in playlist
order.

## CLI surface (`cli.py`)

- `-n / --count N` — maximum number of tracks to download. Omitted means the
  whole playlist (current behavior, unchanged).
- `--random` — pick the N tracks randomly. Without it, take the first N in
  playlist order. With no `--count`, this is a no-op (the whole playlist is
  downloaded either way); we note it rather than error.
- `count <= 0` is an error.

## Mechanism: save → trim → download

`spotdl` downloads the whole playlist by default, so we limit the download by
fetching metadata first:

1. `spotdl save <playlist_url> --save-file <file>` writes a JSON list of all
   tracks without downloading audio.
2. Select N tracks (first N, or `random.sample` of N).
3. Write a trimmed `.spotdl` file and run `spotdl download <trimmed-file>`.

This reuses spotdl's existing auth — no Spotify Web API credentials needed.

## `downloader.py`

- `fetch_track_list(playlist_url, dest) -> list[dict]` — runs `spotdl save`,
  returns the parsed track dicts.
- `select_tracks(tracks, count, randomize) -> list[dict]` — pure function.
  First-N or random-N. If `count >= len(tracks)`, returns all of them.
- `download_playlist(playlist_url, dest, count=None, randomize=False) -> list[Path]`
  — orchestrates. If `count` is None, the current direct download path is used
  unchanged. Otherwise: save → select → write trimmed file → download it.
  Returns sorted MP3 paths, as today.

## Edge cases

- `count` larger than the playlist: download everything available, no error.
- Random selection still copies files to the device in playlist order; only
  *which* tracks are chosen differs, not their on-device ordering.

## Testing

- Unit-test `select_tracks`: first-N, random-N (seeded), count-exceeds-length.
- Mock `subprocess.run` for the download/save paths, matching the existing
  `test_downloader.py` style.
