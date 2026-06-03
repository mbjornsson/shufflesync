# iPod nano `--add` mode design

## Goal

Add an opt-in `--add` mode (nano 1–3G only) that mirrors a Spotify playlist onto
the nano **without erasing existing music**. It preserves the user's library,
adds the playlist as its own named playlist, and is **idempotent per playlist**:
re-running the same playlist refreshes it (pruning the tracks that run added)
rather than duplicating. Multiple added playlists accumulate independently.

Default behavior is unchanged: without `--add`, sync is a full mirror (wipe +
replace). `--add` is rejected for the 2nd-gen shuffle (always a full mirror).

## Why this is safe to attempt

The risk is corrupting the user's real library. The design mitigates it by:
1. Preserving every existing track and user playlist **verbatim** (raw bytes) —
   we never re-emit the user's records through our lossy writer, so ratings,
   play counts, dates, and persistent ids survive.
2. Writing a **timestamped backup** of `iTunesDB` (+ manifest) on the device
   before every `--add` write.
3. **Failing closed**: if the existing DB can't be parsed, we abort *before*
   copying or deleting anything.

## Module architecture

```
itunesdb_reader.py (new)  parse existing iTunesDB -> verbatim records + index
itunesdb.py        (mod)  assemblers from raw records; build_itunesdb reuses them
manifest.py        (new)  read/write/reconcile .shufflesync.json on the device
sync.py            (mod)  add_sync(device, files, playlist_name) beside mirror_sync
cli.py             (mod)  --add flag (nano only)
```

### `itunesdb_reader.py`

`parse(data: bytes) -> ParsedDB` where `ParsedDB` exposes:
- `tracks: list[RawTrack]` — each `RawTrack(track_id: int, raw: bytes)` is the
  exact `mhit` chunk bytes (verbatim).
- `playlists: list[RawPlaylist]` — each `RawPlaylist(name: str, is_master: bool,
  track_ids: list[int], raw: bytes)`.
- `max_track_id() -> int`.

It walks `mhbd → mhsd` datasets, reads the type-1 track list (`mhlt` + `mhit`s,
slicing each by its `total_len`) and the type-2 playlist list (`mhlp` + `mhyp`s,
reading each playlist's name `mhod`, master flag at `0x14`, and `mhip` track
ids). It ignores other dataset types. Track id is read at `mhit+0x10`.

### `itunesdb.py` additions

- `track_dataset_from_records(raw_mhits: list[bytes]) -> bytes` — wrap verbatim
  + new `mhit` byte-records in `mhlt` (count) + `mhsd` type 1.
- `playlist_dataset_from_records(raw_mhyps: list[bytes]) -> bytes` — wrap
  `mhyp` byte-records in `mhlp` (count) + `mhsd` type 2.
- `build_itunesdb(...)` is refactored to call these (no behavior change).
- `master_playlist(track_ids, name="iPod") -> bytes` — build a master `mhyp`
  (master flag set) listing every id. Reused by both full-mirror and add paths.

### `manifest.py`

JSON at `<device>/iPod_Control/iTunes/.shufflesync.json`:
```json
{"playlists": {"Evening Chill": {"track_ids": [501, 502],
                                 "files": ["F90/T0001.mp3", "F90/T0002.mp3"]}}}
```
- `load(itunes_dir) -> Manifest` (empty if absent).
- `Manifest.reconcile(parsed_db)` — drop any recorded track id not present in
  `parsed_db.tracks` (e.g. user deleted it via iTunes), and drop file entries
  whose file is missing on disk. Never delete based on stale data.
- `save(itunes_dir)`.

## The merge algorithm (`add_sync`)

`add_sync(device, source_files, playlist_name)` (nano only):

1. **Back up** `iTunesDB` and `.shufflesync.json` to
   `iPod_Control/iTunes/shufflesync-backup/<timestamp>/` on the device.
2. **Parse** the existing DB (`itunesdb_reader.parse`). On failure, abort
   (nothing copied/deleted yet).
3. **Load + reconcile** the manifest against the parsed DB.
4. **Prune** the previous run of `playlist_name`, if any: from the manifest,
   the set of track ids + files it owns. Remove those `RawTrack`s (by id) from
   the parsed track set; delete those files from `Music`; drop the manifest
   entry. (Each managed playlist exclusively owns its files/ids, so this never
   affects the user's tracks or another managed playlist.)
5. **Copy** the new `source_files` into `Music` with **collision-checked** names
   (scan existing files; pick folder/names that don't exist; never overwrite).
6. **Assign** new track ids `max_track_id()+1 … +N` (computed after pruning,
   over the union of remaining ids to guarantee uniqueness).
7. **Build records:** new `mhit`s (via the existing writer) and a new managed
   `mhyp` for `playlist_name` referencing the new ids.
8. **Reassemble** the DB as **type 1 + type 2 only**:
   - type 1: kept verbatim `RawTrack.raw` (user + other managed) + new `mhit`s.
   - type 2: a **rebuilt master playlist** listing all current track ids; the
     user's non-master playlists kept **verbatim** (`RawPlaylist.raw`); the
     other managed playlists kept verbatim; the new managed `mhyp`.
   - Optional index datasets (types 3–9) are **dropped**; the device rebuilds
     them. (This is exactly the type-1+2 shape the writer already produces and
     validates.)
9. **Write** the merged DB and the updated manifest.

Capacity: only this run's new files count against free space (existing content
already fits); apply the existing margin and skip-with-warning behavior.

## CLI

- `--add` flag. With it, the CLI calls `sync.add_sync` instead of
  `sync.mirror_sync`, passing the playlist name (currently the playlist id; a
  human name is a possible later improvement).
- `--add` with a detected shuffle → error: "the iPod shuffle is always a full
  mirror; --add is only for the iPod nano."

## Error handling

- Unparseable existing DB → abort before any mutation, clear message.
- Backup write failure → abort (don't proceed without a backup).
- Manifest/DB drift → reconcile silently (ignore stale entries).
- Capacity exceeded → copy until full, skip the rest with a warning (as today).

## Testing

- `itunesdb_reader`: parse DBs produced by our writer; assert track ids,
  playlist names, master flag, `max_track_id`. **Round-trip:** for a DB built by
  our assemblers, `parse` then reassemble from the same records is byte-identical
  (proves verbatim preservation).
- `itunesdb` assemblers: `track_dataset_from_records` / `playlist_dataset_from_records`
  produce correct `mhlt`/`mhlp` counts and `mhsd` types; `build_itunesdb` output
  is unchanged from before the refactor (golden test still passes).
- `manifest`: load/save round-trip; reconcile drops stale ids/files.
- `add_sync` (temp device pre-loaded with a writer-built "user library" + a
  user playlist):
  - existing tracks + user playlist preserved (verbatim bytes intact); master
    updated to include new ids; new playlist present.
  - re-running the same playlist refreshes it (same count, no duplicate files,
    old files deleted).
  - adding a second playlist leaves the first intact.
  - a backup file is written before the change.
- Real-device validation (manual): add a small playlist to the real nano,
  confirm existing music AND the new playlist both play. Additive, but back up
  first.

## Out of scope

Dedup against the user's own library; preserving index datasets 3–9; merging
concurrent iTunes playlist edits into managed playlists; `--add` on the shuffle;
a GUI.
