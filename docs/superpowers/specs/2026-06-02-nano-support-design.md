# iPod nano (1st–3rd gen) support design

## Goal

Let `shufflesync` mirror a Spotify playlist onto a 1st–3rd generation iPod nano,
in addition to the existing 2nd-gen shuffle support. The same command auto-
detects which device is attached and writes the correct on-device database.

Scope is the **nano 1G–3G** specifically: these use the `iTunesDB` format with
**no cryptographic checksum**, so a third party can write a valid database.
nano 4G+ (checksum), iPod classic/touch, artwork, and the paused GUI effort are
out of scope.

## Why this is feasible (and bounded)

- nano 1–3G stores its library in `iPod_Control/iTunes/iTunesDB`, a documented
  chunked binary format. Unlike nano 4G+, there is no signature to forge.
- libgpod (the mature C implementation) is **not** a practical dependency here:
  it is gone from Homebrew and has no working Python bindings on Apple Silicon,
  so it would mean building a deprecated C library plus Python 2-era SWIG
  bindings from source. We instead hand-roll the writer in pure Python, the same
  approach already proven for `itunessd.py`.
- The device is physically available, so the exact byte layout is pinned against
  a golden `iTunesDB` captured from the real nano.

## Module architecture

```
device.py     (modified)  detect + classify device -> IpodDevice(root, family)
itunessd.py   (unchanged) shuffle 2G database, big-endian
itunesdb.py   (new)       nano 1-3G database, little-endian
metadata.py   (new)       read ID3 tags + duration from MP3s via mutagen
sync.py       (modified)  shared file copy + capacity, dispatch by family
cli.py        (modified)  same flow; works for whichever device is attached
```

Each module has one job and a small interface, so the nano path can be tested
independently of device hardware (except the manual end-to-end check).

## Device detection & dispatch (`device.py`)

- Add `class DeviceFamily(Enum)` with members `SHUFFLE_2G` and `NANO_1G_3G`
  (the latter covering nano 1st through 3rd gen).
- `detect_family(root) -> DeviceFamily | None`: read
  `iPod_Control/Device/SysInfoExtended` (XML plist; key `ModelNumStr`), falling
  back to the plain-text `iPod_Control/Device/SysInfo` (`ModelNumStr: ...`). Map
  the model string to a family via a small lookup of known nano 1–3G and
  shuffle 2G model numbers. Unknown model → `None`.
- Replace `ShuffleDevice` with `IpodDevice`:
  - `root: Path`, `family: DeviceFamily`
  - `music_dir` → `root / "iPod_Control" / "Music"` (same for both)
  - `db_path` → `iPod_Control/iTunes/iTunesSD` for the shuffle,
    `iPod_Control/iTunes/iTunesDB` for the nano.
- `select_shuffle()` is renamed `select_ipod()` and returns an `IpodDevice`
  (still raising `NoDeviceError` when none is found; still mounting unmounted
  external disks first). `find_shuffles()` becomes `find_ipods()` (still keys on
  the presence of an `iPod_Control` directory).
- An attached but unsupported model (nano 4G+, classic, touch) raises a clear
  error naming the detected model and the supported set.

## iTunesDB writer (`itunesdb.py`)

Pure-Python serializer, **little-endian** (note: `itunessd.py` is big-endian),
following the documented chunk layout. All offsets/fields are pinned against the
golden fixture during implementation.

- `mhbd` (database header) containing two `mhsd` sections.
- **Track list**: `mhsd(type 1) -> mhlt -> N x (mhit + child mhod entries)`.
  - `mhit`: track id, total time (ms), file size (bytes), bitrate, sample rate,
    track number, year, and the child-mhod count.
  - child `mhod` string entries: title (1), location (2), album (3), artist (4),
    genre (5). The **location** is colon-separated with a leading colon, e.g.
    `:iPod_Control:Music:F00:T0001.mp3`. Strings are UTF-16LE.
- **Playlists**: `mhsd(type 2) -> mhlp -> (master mhyp + named mhyp)`.
  - master `mhyp` (master flag set) with a name `mhod` and one `mhip` per track
    referencing the track id; lists every synced track.
  - named `mhyp` titled after the source playlist, listing the same tracks.
- Public API: `build_itunesdb(tracks: list[TrackEntry], playlist_name: str) -> bytes`,
  where `TrackEntry` carries the metadata plus the on-device path and a stable
  track id (assigned 1..N in sync order).

## Metadata (`metadata.py`)

- New dependency: **mutagen** (small, pure-Python, maintained).
- `read_metadata(path: Path) -> TrackMeta` reads title, artist, album, genre,
  track number, year (ID3) and duration-ms + bitrate/sample-rate (MP3 info).
- Missing tags fall back to sensible defaults (title → file stem; numeric fields
  → 0). spotdl tags its downloads, so this is normally fully populated.

## Sync changes (`sync.py`)

`mirror_sync(device: IpodDevice, source_files)` keeps the shared behavior:
wipe `iPod_Control/Music`, capacity check with the existing margin, copy files
into `F{nn}/T{nnnn}.ext` folders (100 files per folder). Then it dispatches on
`device.family`:

- `SHUFFLE_2G`: build track tuples and call `itunessd.build_itunessd(...)` as
  today; write to `db_path`.
- `NANO_1G_3G`: for each copied file, `metadata.read_metadata(...)`, assemble
  `TrackEntry` records (with on-device colon paths and ids 1..N), call
  `itunesdb.build_itunesdb(tracks, playlist_name)`, write to `db_path`.

The destructive wipe and capacity logic are unchanged. `mirror_sync` gains a
`playlist_name` argument (used only by the nano path; the CLI derives it from the
playlist, falling back to a default).

## Error handling

- No device / not in disk mode: existing `NoDeviceError` guidance plus a
  nano-specific hint — modern macOS Music may not manage a nano 1–3G, but the
  device's own disk mode mounts it as USB mass storage (toggle Hold; reset with
  Menu+Select; enter disk mode with Select+Play).
- Unsupported model: explicit message naming the model and supported devices.
- Unreadable or oversized metadata: use defaults and continue; note it.

## Testing

- **Prerequisite (step 0):** with the nano in disk mode, capture its real
  `iTunesDB` to `tests/fixtures/golden_nano/iTunesDB`, used both to reverse-check
  field offsets and as a test reference.
- `itunesdb.py`: golden-fixture structural tests mirroring `test_itunessd.py` —
  chunk identifiers and sizes, mhod strings (UTF-16LE), track count, and the
  presence/content of the master and named playlists. Build a DB for a known
  small track set and assert byte-level structure at verified offsets.
- `device.py`: `detect_family` tests with sample `SysInfoExtended` plists (a
  nano and a shuffle) and an unknown model; `find_ipods` unchanged-behavior
  tests.
- `metadata.py`: read tags from a tiny tagged fixture MP3.
- `sync.py`: dispatch test (nano family → calls `build_itunesdb` with the right
  track ids/paths; shuffle family → calls `build_itunessd`), using fakes.
- Real-device validation (write to the nano and confirm it plays) is manual.

## Out of scope

nano 4G+ and any checksummed device; iPod classic/touch; album artwork; on-device
playlists beyond the single named playlist; the GUI (separate, paused effort);
two-way sync or preserving existing on-device content (this remains a one-way
mirror that replaces the device's music).
