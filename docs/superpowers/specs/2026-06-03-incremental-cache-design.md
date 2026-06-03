# Incremental download cache + correct playlist name design

## Goals

1. **Incremental caching:** re-running a playlist must reuse already-downloaded
   tracks and only fetch new ones, instead of wiping the cache and
   re-downloading everything.
2. **Correct playlist name:** the on-device (nano) playlist must be named after
   the real Spotify playlist, not the URL's base-62 id.

Both touch `download_playlist`, so they are one change.

## Background

Today `download_playlist` `rmtree`s the per-playlist cache dir
(`~/.shufflesync/cache/<playlist_id>`) every run, then `glob("*.mp3")`. The wipe
was added so a changed selection (e.g. a smaller `--count`, or a shrunk
playlist) wouldn't return stale leftover MP3s — but it also defeats caching.
And `cli.py` passes `playlist_name = playlist_id` because the real name wasn't
fetched. spotdl's default `overwrite = skip` reuses existing files, and each
saved song carries `list_name` (the playlist title), so both problems resolve by
fetching metadata, not wiping, and identifying this run's files via spotdl's own
`--m3u` manifest.

## Unified `download_playlist` flow

Returns a result object instead of a bare list:

```python
@dataclass(frozen=True)
class DownloadResult:
    files: list[Path]        # this run's tracks, in playlist order
    playlist_name: str       # real Spotify title (never empty)
```

Steps (one path; the count / no-count fork is removed):
1. `_reject_option_like(playlist_url)` (existing guard).
2. `dest.mkdir(parents=True, exist_ok=True)` — **no `rmtree`**.
3. `all_tracks = fetch_track_list(playlist_url, dest)` (`spotdl save`).
4. `playlist_name = all_tracks[0]["list_name"]` if present and non-empty, else
   `dest.name` (the playlist id) as a fallback.
5. `selected = all_tracks if count is None else select_tracks(all_tracks, count, randomize)`.
6. Write `selection.spotdl` (the selected songs).
7. Remove a stale `run.m3u` if present, then
   `spotdl download selection.spotdl --m3u run.m3u <output args>` with
   `cwd=dest`. spotdl skips files already present, so only new tracks download.
8. `files = _read_m3u(run.m3u, dest)` — this run's tracks, in order.
9. `_prune_orphans(dest, files)` — delete cached `*.mp3` not in `files` (bounds
   the cache; correctness comes from the m3u list, not the prune).
10. Return `DownloadResult(files, playlist_name)`.

### Helpers
- `_read_m3u(m3u: Path, dest: Path) -> list[Path]`: read the file, skip blank
  and `#` comment lines, resolve each entry (relative entries against `dest`),
  keep existing `.mp3` paths, preserving order.
- `_prune_orphans(dest: Path, keep: list[Path]) -> None`: delete `dest`'s
  top-level `*.mp3` files whose resolved path is not in `keep`.

`fetch_track_list` is unchanged (it already `spotdl save`s and returns the song
dicts).

## CLI wiring (`cli.py`)

- `result = downloader.download_playlist(...)`; use `result.files`.
- `playlist_name = result.playlist_name or playlist_id`.
- Pass `playlist_name` to `mirror_sync` / `add_sync` (replaces the old
  `playlist_name = playlist_id`). `playlist_id` is still derived for the cache
  dir and the validation guard.

## Caching behavior summary

- Re-running a grown playlist: existing tracks skipped (instant), only the new
  song downloads, m3u lists all current tracks → all sync.
- Smaller `--count` or shrunk playlist: m3u lists exactly the current selection;
  orphaned files pruned. No stale tracks returned (the bug the wipe fixed stays
  fixed).
- The cache dir persists across runs.

## Error handling

- `spotdl save`/`download` non-zero exit → `CalledProcessError` propagates; the
  CLI already catches it and exits 1 with a message.
- Missing/empty `run.m3u` → `files == []` → CLI's existing "No tracks were
  downloaded" path.
- Empty `list_name` → playlist name falls back to the playlist id (never blank).

## Testing

- `download_playlist` returns `DownloadResult` with files from the m3u (in order)
  and `playlist_name` from `list_name`; `subprocess.run` mocked to write the save
  file and the m3u + mp3s.
- **No-wipe:** a pre-existing cached mp3 survives a run (incremental behavior).
- **Prune:** a cached mp3 absent from the m3u is deleted after a run.
- **Name fallback:** empty/missing `list_name` → result name is the playlist id.
- `--count` path: selection trimmed; m3u-listed files returned.
- `_reject_option_like` still rejects flag-like URLs.
- `cli` passes `result.playlist_name` to sync (and falls back to the id when
  empty).

## Out of scope

Cross-playlist dedupe; cache size limits/TTL; changing the on-device file naming;
the `--add` merge logic (it consumes `download_playlist`'s files unchanged).
