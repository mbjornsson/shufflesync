# iPod nano (1–3G) Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `shufflesync` mirror a Spotify playlist onto a 1st–3rd generation iPod nano by hand-writing its `iTunesDB`, auto-detecting shuffle vs nano.

**Architecture:** A new pure-Python `itunesdb.py` serializer (little-endian, the inverse of the existing big-endian `itunessd.py`) plus a `metadata.py` ID3 reader. `device.py` grows model detection and returns a generalized `IpodDevice`; `sync.py` copies files (shared) then dispatches to the right database builder by device family.

**Tech Stack:** Python ≥3.9, `struct`, `mutagen` (new dep), pytest. Spec: `docs/superpowers/specs/2026-06-02-nano-support-design.md`.

**Reference material (local, git-ignored):** the real nano database is captured at `device-backup-nano-*/iTunes/iTunesDB`; the device is mounted at `/Volumes/IPOD`. The repo is public, so the real DB is NEVER committed (it embeds personal library metadata).

---

## File structure

- `src/shufflesync/itunesdb.py` (new) — iTunesDB chunk builders + `build_itunesdb`.
- `src/shufflesync/metadata.py` (new) — `read_metadata(path) -> TrackMeta` via mutagen.
- `src/shufflesync/device.py` (modify) — `DeviceFamily`, `detect_family`, `IpodDevice`, `find_ipods`, `select_ipod`.
- `src/shufflesync/sync.py` (modify) — `mirror_sync` gains `playlist_name`; dispatch by family.
- `src/shufflesync/cli.py` (modify) — call `select_ipod`, pass a playlist name.
- `pyproject.toml` (modify) — add `mutagen` dependency.
- Tests: `tests/test_itunesdb.py`, `tests/test_metadata.py`, updates to `tests/test_device.py`, `tests/test_sync.py`, `tests/test_cli.py`.
- `tests/fixtures/golden_nano/iTunesDB` (new, synthetic — created in Task 9, NOT the real device DB).

---

## Confirmed on-disk layout (from the golden file)

All integers little-endian. Offsets are within each chunk.

- **mhbd** (db header): `header_len=244`, `0x08` total_len, `0x0c` unk=1, `0x10` version, `0x14` dataset count, `0x18` 8-byte library id, `"en"` language at `0x46`.
- **mhsd** (dataset): `header_len=96`, `0x08` total_len, `0x0c` type (1=tracks, 2=playlists).
- **mhlt** (track list): `header_len=92`, `0x08` track count. Tracks follow.
- **mhit** (track): `header_len` (we use 0x184=388), `0x08` total_len, `0x0c` mhod count, `0x10` track id, `0x14` visible=1, `0x18` filetype 4 bytes, `0x1c` type1(u8)=1, `0x1d` type2(u8)=1, `0x1e` compilation(u8), `0x1f` rating(u8), `0x2c` track number, `0x30` total tracks, `0x34` year, `0x38` bitrate (u16). **Offsets for file size, track length (ms), sample rate, and dates are confirmed empirically in Task 0.**
- **mhod** (string: title=1, album=3, artist=4, genre=5, location=2): `header_len=24`, `0x08` total_len = `40 + len(utf16le)`, `0x0c` type, `0x18` position=1, `0x1c` byte length, `0x20`/`0x24` zero, `0x28` UTF-16LE bytes. Location string is colon-separated with a leading colon: `:iPod_Control:Music:F00:T0001.mp3`.
- **mhlp** (playlist list): `header_len=92`, `0x08` playlist count.
- **mhyp** (playlist): `header_len=184`, `0x08` total_len, `0x0c` mhod count=1, `0x10` item count, `0x14` master flag (1=master, 0=named). One title `mhod` then the items.
- **mhip** (playlist item): `header_len=76`, `0x08` total_len, `0x0c` mhod count=1, `0x18` track id. Followed by one 44-byte position `mhod` (type 100).

---

## Task 0: Pin the empirical mhit field offsets

**Files:**
- Create: `docs/superpowers/plans/nano-mhit-offsets.md` (a short findings table the later tasks reference)

- [ ] **Step 1: Read a known track's real size from the device**

Run:
```bash
ls -la "/Volumes/IPOD/iPod_Control/Music/F01/IIMR.mp3"
```
Note the byte size (call it `SIZE`). `IIMR.mp3` is the location of track id 38 seen in the golden file; if absent, pick any file under `/Volumes/IPOD/iPod_Control/Music/` and find the matching `mhit` by its location `mhod` instead.

- [ ] **Step 2: Compute that track's duration in ms**

Run:
```bash
cp "/Volumes/IPOD/iPod_Control/Music/F01/IIMR.mp3" /tmp/probe.mp3
.venv/bin/python -c "from mutagen.mp3 import MP3; print(int(MP3('/tmp/probe.mp3').info.length*1000))"
```
(Install mutagen first if needed: `uv add mutagen` — done properly in Task 1; for this probe `.venv/bin/pip install mutagen` is fine.) Note the value (call it `MS`).

- [ ] **Step 3: Locate that track's mhit and scan its first 0x60 bytes for SIZE and MS**

Run:
```bash
DB=$(ls device-backup-nano-*/iTunes/iTunesDB | head -1)
.venv/bin/python - "$DB" "$SIZE" "$MS" <<'PY'
import sys, struct
data=open(sys.argv[1],"rb").read(); size=int(sys.argv[2]); ms=int(sys.argv[3])
i=data.find(b"mhit")
while i!=-1:
    tid=struct.unpack_from("<I",data,i+16)[0]
    fields={off:struct.unpack_from("<I",data,i+off)[0] for off in range(0x20,0x60,4)}
    hits={hex(o):v for o,v in fields.items() if v in (size,ms)}
    if hits: print("mhit@",i,"trackid",tid,"matches",hits)
    i=data.find(b"mhit",i+4)
PY
```
Expected: the offset reporting `size` is the **file size** field; the offset reporting `ms` is the **track length** field.

- [ ] **Step 4: Record the findings**

Write `docs/superpowers/plans/nano-mhit-offsets.md` with the confirmed offsets, e.g.:
```markdown
# Confirmed mhit field offsets (little-endian u32)
- file size:   0xNN
- track length (ms): 0xNN
- sample rate (stored as rate<<16): 0x3c  (verify: high u16 == 44100)
- date fields: 0x20, 0x24 (mac HFS timestamps; left 0 by our writer)
```
These offsets are used by `MHIT_OFFSETS` in Task 3.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/nano-mhit-offsets.md
git commit -m "docs: pin nano mhit field offsets from golden iTunesDB"
```

---

## Task 1: Add mutagen + metadata reader

**Files:**
- Modify: `pyproject.toml`
- Create: `src/shufflesync/metadata.py`
- Test: `tests/test_metadata.py`

- [ ] **Step 1: Add the dependency**

In `pyproject.toml`, change the dependencies line to:
```toml
dependencies = ["spotdl>=4", "mutagen>=1.47"]
```
Then run: `uv sync`

- [ ] **Step 2: Write the failing test**

```python
# tests/test_metadata.py
from pathlib import Path
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TRCK, TDRC
from mutagen.mp3 import MP3
from shufflesync import metadata


def _make_mp3(path: Path):
    # a minimal valid silent MP3 frame so mutagen can read .info.length
    # (one 26 ms MPEG1 Layer3 frame at 128kbps/44.1kHz, padded)
    frame = bytes.fromhex("fffb9064") + b"\x00" * 414
    path.write_bytes(frame * 40)  # ~1s of frames
    tags = ID3()
    tags.add(TIT2(encoding=3, text="My Title"))
    tags.add(TPE1(encoding=3, text="My Artist"))
    tags.add(TALB(encoding=3, text="My Album"))
    tags.add(TCON(encoding=3, text="My Genre"))
    tags.add(TRCK(encoding=3, text="3"))
    tags.add(TDRC(encoding=3, text="2021"))
    tags.save(path)


def test_read_metadata_extracts_tags_and_duration(tmp_path):
    p = tmp_path / "song.mp3"
    _make_mp3(p)
    m = metadata.read_metadata(p)
    assert m.title == "My Title"
    assert m.artist == "My Artist"
    assert m.album == "My Album"
    assert m.genre == "My Genre"
    assert m.track_number == 3
    assert m.year == 2021
    assert m.duration_ms > 0
    assert m.size == p.stat().st_size


def test_read_metadata_defaults_when_untagged(tmp_path):
    p = tmp_path / "bare.mp3"
    frame = bytes.fromhex("fffb9064") + b"\x00" * 414
    p.write_bytes(frame * 40)
    m = metadata.read_metadata(p)
    assert m.title == "bare"          # falls back to file stem
    assert m.artist == ""
    assert m.track_number == 0
    assert m.year == 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_metadata.py -v`
Expected: FAIL (`ModuleNotFoundError: shufflesync.metadata`).

- [ ] **Step 4: Implement `metadata.py`**

```python
# src/shufflesync/metadata.py
"""Read ID3 tags and duration from an MP3 for the iTunesDB."""
from dataclasses import dataclass
from pathlib import Path

from mutagen.mp3 import MP3


@dataclass(frozen=True)
class TrackMeta:
    title: str
    artist: str
    album: str
    genre: str
    track_number: int
    year: int
    duration_ms: int
    bitrate: int
    sample_rate: int
    size: int


def _first(tags, key: str) -> str:
    value = tags.get(key)
    return str(value.text[0]) if value and value.text else ""


def _int_prefix(text: str) -> int:
    """'3/12' or '2021-05' -> leading integer, else 0."""
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else 0


def read_metadata(path: Path) -> TrackMeta:
    audio = MP3(path)
    tags = audio.tags
    title = _first(tags, "TIT2") if tags else ""
    return TrackMeta(
        title=title or path.stem,
        artist=_first(tags, "TPE1") if tags else "",
        album=_first(tags, "TALB") if tags else "",
        genre=_first(tags, "TCON") if tags else "",
        track_number=_int_prefix(_first(tags, "TRCK")) if tags else 0,
        year=_int_prefix(_first(tags, "TDRC")) if tags else 0,
        duration_ms=int(audio.info.length * 1000),
        bitrate=int(audio.info.bitrate // 1000),
        sample_rate=int(audio.info.sample_rate),
        size=path.stat().st_size,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_metadata.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/shufflesync/metadata.py tests/test_metadata.py
git commit -m "feat: add mutagen-based MP3 metadata reader"
```

---

## Task 2: iTunesDB mhod string builders

**Files:**
- Create: `src/shufflesync/itunesdb.py`
- Test: `tests/test_itunesdb.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_itunesdb.py
import struct
from shufflesync import itunesdb


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def test_string_mhod_layout():
    m = itunesdb.string_mhod(1, "Hi")  # type 1 = title
    assert m[0:4] == b"mhod"
    assert _u32(m, 4) == 24                      # header_len
    assert _u32(m, 8) == len(m)                  # total_len
    assert _u32(m, 8) == 40 + len("Hi".encode("utf-16-le"))
    assert _u32(m, 12) == 1                       # type
    assert _u32(m, 0x18) == 1                     # position
    assert _u32(m, 0x1c) == 4                     # byte length (2 chars utf-16)
    assert m[40:].decode("utf-16-le") == "Hi"


def test_location_mhod_uses_colon_path():
    m = itunesdb.string_mhod(2, ":iPod_Control:Music:F00:T0001.mp3")
    assert _u32(m, 12) == 2
    assert m[40:].decode("utf-16-le") == ":iPod_Control:Music:F00:T0001.mp3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_itunesdb.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the module start + `string_mhod`**

```python
# src/shufflesync/itunesdb.py
"""Serializer for the iPod nano (1-3G) iTunesDB database.

Little-endian (the iTunesSD format in itunessd.py is big-endian). Validated
against a real-hardware golden reference; see
docs/superpowers/plans/2026-06-02-nano-support.md for the field tables.
"""
import struct
from dataclasses import dataclass
from typing import List


def _u32(n: int) -> bytes:
    return struct.pack("<I", n)


def string_mhod(mhod_type: int, text: str) -> bytes:
    """A string mhod: title=1, location=2, album=3, artist=4, genre=5."""
    encoded = text.encode("utf-16-le")
    body = bytearray(40)
    body[0:4] = b"mhod"
    body[4:8] = _u32(24)                 # header_len
    body[8:12] = _u32(40 + len(encoded))  # total_len
    body[12:16] = _u32(mhod_type)
    body[0x18:0x1c] = _u32(1)            # position
    body[0x1c:0x20] = _u32(len(encoded))  # byte length
    return bytes(body) + encoded
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_itunesdb.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/shufflesync/itunesdb.py tests/test_itunesdb.py
git commit -m "feat: iTunesDB string mhod serialization"
```

---

## Task 3: iTunesDB track record (mhit)

**Files:**
- Modify: `src/shufflesync/itunesdb.py`
- Test: `tests/test_itunesdb.py`

Use the offsets confirmed in Task 0. The constants below assume the common
layout (size at `0x28`, track length at `0x24`); **replace them with the Task 0
findings if they differ.**

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_itunesdb.py
def test_track_entry_to_mhit_fields():
    entry = itunesdb.TrackEntry(
        track_id=7, title="T", artist="A", album="Al", genre="G",
        location=":iPod_Control:Music:F00:T0007.mp3",
        size=123456, duration_ms=98000, bitrate=192, sample_rate=44100,
        track_number=7, year=2009,
    )
    m = itunesdb.track_mhit(entry)
    assert m[0:4] == b"mhit"
    assert _u32(m, 4) == 0x184                 # header_len
    assert _u32(m, 8) == len(m)                # total_len
    assert _u32(m, 12) == 5                    # mhod count (title/artist/album/genre/location)
    assert _u32(m, 16) == 7                    # track id
    assert _u32(m, 20) == 1                    # visible
    assert m[0x18:0x1c] == b"MP3 "[::-1]       # filetype
    assert m[0x1c] == 1 and m[0x1d] == 1       # type1, type2
    assert _u32(m, itunesdb.MHIT_OFFSETS["size"]) == 123456
    assert _u32(m, itunesdb.MHIT_OFFSETS["length_ms"]) == 98000
    assert _u32(m, 0x2c) == 7                  # track number
    assert _u32(m, 0x34) == 2009               # year
    # the five mhods are appended after the 0x184-byte header
    assert m[0x184:0x184 + 4] == b"mhod"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_itunesdb.py::test_track_entry_to_mhit_fields -v`
Expected: FAIL (`AttributeError: TrackEntry`).

- [ ] **Step 3: Implement `TrackEntry`, `MHIT_OFFSETS`, `track_mhit`**

```python
# add to src/shufflesync/itunesdb.py
MHIT_HEADER_LEN = 0x184
# Offsets confirmed in Task 0 — update if the probe disagrees.
MHIT_OFFSETS = {"size": 0x28, "length_ms": 0x24, "sample_rate": 0x3c}


@dataclass(frozen=True)
class TrackEntry:
    track_id: int
    title: str
    artist: str
    album: str
    genre: str
    location: str          # colon path, e.g. ":iPod_Control:Music:F00:T0001.mp3"
    size: int
    duration_ms: int
    bitrate: int
    sample_rate: int
    track_number: int
    year: int


def track_mhit(entry: "TrackEntry") -> bytes:
    mhods = b"".join([
        string_mhod(1, entry.title),
        string_mhod(4, entry.artist),
        string_mhod(3, entry.album),
        string_mhod(5, entry.genre),
        string_mhod(2, entry.location),
    ])
    h = bytearray(MHIT_HEADER_LEN)
    h[0:4] = b"mhit"
    h[4:8] = _u32(MHIT_HEADER_LEN)
    h[8:12] = _u32(MHIT_HEADER_LEN + len(mhods))
    h[12:16] = _u32(5)                  # mhod count
    h[16:20] = _u32(entry.track_id)
    h[20:24] = _u32(1)                  # visible
    h[0x18:0x1c] = b"MP3 "[::-1]        # filetype marker
    h[0x1c] = 1                          # type1
    h[0x1d] = 1                          # type2
    h[MHIT_OFFSETS["size"]:MHIT_OFFSETS["size"] + 4] = _u32(entry.size)
    h[MHIT_OFFSETS["length_ms"]:MHIT_OFFSETS["length_ms"] + 4] = _u32(entry.duration_ms)
    h[0x2c:0x30] = _u32(entry.track_number)
    h[0x34:0x38] = _u32(entry.year)
    h[0x38:0x3a] = struct.pack("<H", entry.bitrate)
    h[MHIT_OFFSETS["sample_rate"]:MHIT_OFFSETS["sample_rate"] + 4] = _u32(entry.sample_rate << 16)
    return bytes(h) + mhods
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_itunesdb.py -v`
Expected: PASS. If the `size`/`length_ms` asserts fail, fix `MHIT_OFFSETS` to the Task 0 values.

- [ ] **Step 5: Commit**

```bash
git add src/shufflesync/itunesdb.py tests/test_itunesdb.py
git commit -m "feat: iTunesDB track record (mhit)"
```

---

## Task 4: Track list dataset (mhlt + mhsd type 1)

**Files:**
- Modify: `src/shufflesync/itunesdb.py`
- Test: `tests/test_itunesdb.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_itunesdb.py
def _entry(i):
    return itunesdb.TrackEntry(
        track_id=i, title=f"T{i}", artist="A", album="Al", genre="G",
        location=f":iPod_Control:Music:F00:T{i:04d}.mp3",
        size=1000, duration_ms=2000, bitrate=192, sample_rate=44100,
        track_number=i, year=2009,
    )


def test_track_dataset_wraps_all_mhits():
    ds = itunesdb.track_dataset([_entry(1), _entry(2)])
    assert ds[0:4] == b"mhsd"
    assert _u32(ds, 0x0c) == 1                 # dataset type 1 = tracks
    assert _u32(ds, 8) == len(ds)              # total_len
    inner = ds[96:]
    assert inner[0:4] == b"mhlt"
    assert _u32(inner, 8) == 2                  # track count
    assert inner[92:96] == b"mhit"             # first track follows the 92-byte mhlt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_itunesdb.py::test_track_dataset_wraps_all_mhits -v`
Expected: FAIL (`AttributeError: track_dataset`).

- [ ] **Step 3: Implement `_mhsd`, `mhlt`, `track_dataset`**

```python
# add to src/shufflesync/itunesdb.py
def _mhsd(dataset_type: int, body: bytes) -> bytes:
    h = bytearray(96)
    h[0:4] = b"mhsd"
    h[4:8] = _u32(96)
    h[8:12] = _u32(96 + len(body))
    h[12:16] = _u32(dataset_type)
    return bytes(h) + body


def track_dataset(entries: List["TrackEntry"]) -> bytes:
    mhlt = bytearray(92)
    mhlt[0:4] = b"mhlt"
    mhlt[4:8] = _u32(92)
    mhlt[8:12] = _u32(len(entries))
    body = bytes(mhlt) + b"".join(track_mhit(e) for e in entries)
    return _mhsd(1, body)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_itunesdb.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/shufflesync/itunesdb.py tests/test_itunesdb.py
git commit -m "feat: iTunesDB track dataset (mhlt + mhsd)"
```

---

## Task 5: Playlists dataset (mhip + mhyp + mhlp + mhsd type 2)

**Files:**
- Modify: `src/shufflesync/itunesdb.py`
- Test: `tests/test_itunesdb.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_itunesdb.py
def test_playlist_dataset_has_master_and_named():
    ds = itunesdb.playlist_dataset("Evening Chill", [1, 2, 3])
    assert ds[0:4] == b"mhsd"
    assert _u32(ds, 0x0c) == 2                  # dataset type 2 = playlists
    inner = ds[96:]
    assert inner[0:4] == b"mhlp"
    assert _u32(inner, 8) == 2                  # two playlists (master + named)
    master = inner[92:]
    assert master[0:4] == b"mhyp"
    assert _u32(master, 0x10) == 3              # item count
    assert _u32(master, 0x14) == 1             # master flag
    # named playlist's title mhod contains the name somewhere in the dataset
    assert "Evening Chill".encode("utf-16-le") in ds


def test_playlist_item_references_track_id():
    item = itunesdb.playlist_item(track_id=42, position=0)
    assert item[0:4] == b"mhip"
    assert _u32(item, 0x0c) == 1                # one child mhod
    assert _u32(item, 0x18) == 42              # track id
    assert item[76:80] == b"mhod"             # position mhod follows the 76-byte header
    assert _u32(item, 8) == len(item)          # total_len includes child mhod
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_itunesdb.py::test_playlist_dataset_has_master_and_named tests/test_itunesdb.py::test_playlist_item_references_track_id -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Implement position mhod, `playlist_item`, `_mhyp`, `playlist_dataset`**

```python
# add to src/shufflesync/itunesdb.py
def _position_mhod(position: int) -> bytes:
    body = bytearray(44)
    body[0:4] = b"mhod"
    body[4:8] = _u32(24)        # header_len
    body[8:12] = _u32(44)       # total_len
    body[12:16] = _u32(100)     # type 100 = playlist item position
    body[0x18:0x1c] = _u32(position)
    return bytes(body)


def playlist_item(track_id: int, position: int) -> bytes:
    child = _position_mhod(position)
    h = bytearray(76)
    h[0:4] = b"mhip"
    h[4:8] = _u32(76)
    h[8:12] = _u32(76 + len(child))
    h[12:16] = _u32(1)                  # mhod count
    h[0x18:0x1c] = _u32(track_id)
    return bytes(h) + child


def _mhyp(name: str, track_ids: List[int], is_master: bool) -> bytes:
    title = string_mhod(1, name)
    items = b"".join(playlist_item(t, i) for i, t in enumerate(track_ids))
    body = title + items
    h = bytearray(184)
    h[0:4] = b"mhyp"
    h[4:8] = _u32(184)
    h[8:12] = _u32(184 + len(body))
    h[12:16] = _u32(1)                  # mhod count (title only)
    h[16:20] = _u32(len(track_ids))     # item count
    h[20:24] = _u32(1 if is_master else 0)  # master flag
    return bytes(h) + body


def playlist_dataset(playlist_name: str, track_ids: List[int]) -> bytes:
    mhlp = bytearray(92)
    mhlp[0:4] = b"mhlp"
    mhlp[4:8] = _u32(92)
    mhlp[8:12] = _u32(2)                # master + one named playlist
    master = _mhyp("shufflesync", track_ids, is_master=True)
    named = _mhyp(playlist_name, track_ids, is_master=False)
    return _mhsd(2, bytes(mhlp) + master + named)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_itunesdb.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/shufflesync/itunesdb.py tests/test_itunesdb.py
git commit -m "feat: iTunesDB playlists dataset (mhyp/mhip/mhlp)"
```

---

## Task 6: Top-level database (mhbd + build_itunesdb)

**Files:**
- Modify: `src/shufflesync/itunesdb.py`
- Test: `tests/test_itunesdb.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_itunesdb.py
def test_build_itunesdb_full_structure():
    db = itunesdb.build_itunesdb([_entry(1), _entry(2)], "Evening Chill")
    assert db[0:4] == b"mhbd"
    assert _u32(db, 4) == 244                   # mhbd header_len
    assert _u32(db, 8) == len(db)               # total_len spans whole file
    assert _u32(db, 0x14) == 2                  # two datasets (tracks + playlists)
    assert db[0x46:0x48] == b"en"              # language
    # first dataset is tracks (type 1), second is playlists (type 2)
    first = db[244:]
    assert first[0:4] == b"mhsd" and _u32(first, 0x0c) == 1
    second = first[_u32(first, 8):]
    assert second[0:4] == b"mhsd" and _u32(second, 0x0c) == 2


def test_build_itunesdb_empty_playlist():
    db = itunesdb.build_itunesdb([], "Empty")
    assert db[0:4] == b"mhbd"
    assert _u32(db, 0x14) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_itunesdb.py::test_build_itunesdb_full_structure -v`
Expected: FAIL (`AttributeError: build_itunesdb`).

- [ ] **Step 3: Implement `_mhbd` and `build_itunesdb`**

```python
# add to src/shufflesync/itunesdb.py
def _mhbd(dataset_count: int, body: bytes) -> bytes:
    h = bytearray(244)
    h[0:4] = b"mhbd"
    h[4:8] = _u32(244)
    h[8:12] = _u32(244 + len(body))
    h[12:16] = _u32(1)                  # unk1
    h[16:20] = _u32(0x13)               # db version (libgpod-compatible)
    h[20:24] = _u32(dataset_count)
    h[24:32] = b"shuffl\x00\x00"         # 8-byte library id (stable, arbitrary)
    h[0x46:0x48] = b"en"                # language
    return bytes(h) + body


def build_itunesdb(entries: List["TrackEntry"], playlist_name: str) -> bytes:
    """Serialize a full iTunesDB: one track dataset + one playlist dataset
    (master playlist + a named playlist) referencing every track."""
    track_ids = [e.track_id for e in entries]
    body = track_dataset(entries) + playlist_dataset(playlist_name, track_ids)
    return _mhbd(2, body)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_itunesdb.py -v`
Expected: PASS (all itunesdb tests).

- [ ] **Step 5: Commit**

```bash
git add src/shufflesync/itunesdb.py tests/test_itunesdb.py
git commit -m "feat: iTunesDB top-level assembly (mhbd + build_itunesdb)"
```

---

## Task 7: Device detection & generalization (`device.py`)

**Files:**
- Modify: `src/shufflesync/device.py`
- Modify: `src/shufflesync/cli.py`
- Test: `tests/test_device.py`

> **Detection note (divergence from spec):** the spec proposed gating on the
> `mhbd` checksum field. With only one (un-checksummed) device sample, that
> field's offset cannot be located reliably, and the obvious guess (`0x46`)
> collides with the `"en"` language bytes — which would falsely reject the real
> nano. So detection is downgraded to a robust file-based signal: `iTunesSD` →
> shuffle; a valid `iTunesDB` (`mhbd` magic) → nano. The checksummed-device
> limitation is documented instead (Task 10). Reconcile this with the spec.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_device.py
from shufflesync import device


def _shuffle(tmp_path):
    root = tmp_path / "SHUFFLE"
    itunes = root / "iPod_Control" / "iTunes"
    itunes.mkdir(parents=True)
    (root / "iPod_Control" / "Music").mkdir(parents=True)
    (itunes / "iTunesSD").write_bytes(b"\x00" * 18)
    return root


def _nano(tmp_path):
    root = tmp_path / "NANO"
    itunes = root / "iPod_Control" / "iTunes"
    itunes.mkdir(parents=True)
    (root / "iPod_Control" / "Music").mkdir(parents=True)
    mhbd = bytearray(244)
    mhbd[0:4] = b"mhbd"
    (itunes / "iTunesDB").write_bytes(bytes(mhbd))
    return root


def test_detect_family_shuffle(tmp_path):
    assert device.detect_family(_shuffle(tmp_path)) == device.DeviceFamily.SHUFFLE_2G


def test_detect_family_nano(tmp_path):
    assert device.detect_family(_nano(tmp_path)) == device.DeviceFamily.NANO_1G_3G


def test_detect_family_unknown_when_no_database(tmp_path):
    root = tmp_path / "BARE"
    (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    assert device.detect_family(root) is None


def test_detect_family_unknown_when_db_not_mhbd(tmp_path):
    root = tmp_path / "WEIRD"
    itunes = root / "iPod_Control" / "iTunes"
    itunes.mkdir(parents=True)
    (itunes / "iTunesDB").write_bytes(b"junk" + b"\x00" * 240)
    assert device.detect_family(root) is None


def test_select_ipod_returns_device_with_family(tmp_path):
    root = _nano(tmp_path)
    dev = device.select_ipod(volumes_dir=tmp_path)
    assert dev.root == root
    assert dev.family == device.DeviceFamily.NANO_1G_3G
    assert dev.db_path == root / "iPod_Control" / "iTunes" / "iTunesDB"


def test_select_ipod_unsupported_raises(tmp_path):
    # an iPod_Control with no recognizable database
    (tmp_path / "X" / "iPod_Control" / "iTunes").mkdir(parents=True)
    with pytest.raises(device.UnsupportedDeviceError):
        device.select_ipod(volumes_dir=tmp_path)
```

Also update the existing tests in this file: the shuffle/nano helpers above
replace `_make_ipod`, and rename calls `find_shuffles`→`find_ipods`,
`select_shuffle`→`select_ipod`. The existing `test_select_shuffle_*` tests become
`test_select_ipod_*` and must create a real DB file (use `_nano`/`_shuffle`) so
detection succeeds; `dev.root` assertions stay the same.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_device.py -v`
Expected: FAIL (`AttributeError: DeviceFamily` / `detect_family`).

- [ ] **Step 3: Rewrite `device.py`**

```python
# src/shufflesync/device.py
"""Locate and classify a mounted iPod on macOS."""
import plistlib
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional


class NoDeviceError(Exception):
    pass


class UnsupportedDeviceError(Exception):
    pass


class DeviceFamily(Enum):
    SHUFFLE_2G = "shuffle_2g"
    NANO_1G_3G = "nano_1g_3g"


@dataclass(frozen=True)
class IpodDevice:
    root: Path
    family: DeviceFamily

    @property
    def music_dir(self) -> Path:
        return self.root / "iPod_Control" / "Music"

    @property
    def db_path(self) -> Path:
        name = "iTunesSD" if self.family == DeviceFamily.SHUFFLE_2G else "iTunesDB"
        return self.root / "iPod_Control" / "iTunes" / name


def _itunes_dir(root: Path) -> Path:
    return root / "iPod_Control" / "iTunes"


def detect_family(root: Path) -> Optional[DeviceFamily]:
    """Classify a mounted iPod by its on-disk database.

    iTunesSD -> shuffle 2G. A valid iTunesDB (mhbd magic) -> nano 1-3G. Anything
    else -> None (unsupported). NOTE: this does not distinguish a nano 1-3G from
    a checksummed iTunesDB device (nano 4G+, classic, touch); writing our
    unsigned DB to those yields an empty library. This limitation is documented;
    see the detection note in the plan.
    """
    itunes = _itunes_dir(root)
    if (itunes / "iTunesSD").exists():
        return DeviceFamily.SHUFFLE_2G
    db = itunes / "iTunesDB"
    if db.exists() and db.read_bytes()[:4] == b"mhbd":
        return DeviceFamily.NANO_1G_3G
    return None


def find_ipods(volumes_dir: Path = Path("/Volumes")) -> List[Path]:
    """Return mounts that contain an iPod_Control directory."""
    if not volumes_dir.exists():
        return []
    return sorted(
        p for p in volumes_dir.iterdir() if (p / "iPod_Control").is_dir()
    )


def mount_external_disks() -> None:
    """Best-effort mount of unmounted external disks via `diskutil`."""
    try:
        listing = subprocess.run(
            ["diskutil", "list", "-plist", "external", "physical"],
            capture_output=True, check=True,
        ).stdout
        info = plistlib.loads(listing)
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException):
        return
    for disk in info.get("AllDisksAndPartitions", []):
        idents = [disk.get("DeviceIdentifier")]
        idents += [p.get("DeviceIdentifier") for p in disk.get("Partitions", [])]
        for ident in filter(None, idents):
            subprocess.run(["diskutil", "mount", ident], capture_output=True)


def select_ipod(
    volumes_dir: Path = Path("/Volumes"),
    chooser: Optional[Callable[[List[Path]], Path]] = None,
    mounter: Optional[Callable[[], None]] = None,
) -> IpodDevice:
    """Find one iPod and classify it, mounting unmounted disks if needed."""
    if mounter is None:
        mounter = mount_external_disks
    candidates = find_ipods(volumes_dir)
    if not candidates:
        mounter()
        candidates = find_ipods(volumes_dir)
    if not candidates:
        raise NoDeviceError(
            "No iPod found. Plug it in and make sure it is mounted (it should "
            "appear under /Volumes and contain an iPod_Control folder).\n"
            "If iTunes/Finder manages it, enable disk use. For an old nano that "
            "modern macOS won't manage, put it in disk mode on the device: hold "
            "the Hold switch on then off, reset with Menu+Select, then hold "
            "Select+Play to enter disk mode."
        )
    root = candidates[0] if len(candidates) == 1 else (chooser or _interactive_chooser)(candidates)
    family = detect_family(root)
    if family is None:
        raise UnsupportedDeviceError(
            f"The iPod at {root} is not supported. shufflesync supports the "
            "2nd-gen shuffle and the 1st-3rd gen nano (devices without a "
            "database signature)."
        )
    return IpodDevice(root, family)


def _interactive_chooser(options: List[Path]) -> Path:
    print("Multiple iPod devices found:")
    for i, opt in enumerate(options):
        print(f"  [{i}] {opt.name}")
    while True:
        choice = input("Choose device number: ").strip()
        if choice.isdigit() and 0 <= int(choice) < len(options):
            return options[int(choice)]
        print("Invalid choice.")
```

- [ ] **Step 4: Update `cli.py` to use `select_ipod`**

In `src/shufflesync/cli.py`, change the device block:
```python
    try:
        dev = device.select_ipod()
    except (device.NoDeviceError, device.UnsupportedDeviceError) as e:
        print(str(e), file=sys.stderr)
        return 1
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_device.py tests/test_cli.py -v`
Expected: PASS (update any remaining `select_shuffle`/`find_shuffles` references in tests).

- [ ] **Step 6: Commit**

```bash
git add src/shufflesync/device.py src/shufflesync/cli.py tests/test_device.py
git commit -m "feat: detect device family (shuffle vs nano) and generalize device"
```

---

## Task 8: Sync dispatch by family (`sync.py` + `cli.py`)

**Files:**
- Modify: `src/shufflesync/sync.py`
- Modify: `src/shufflesync/cli.py`
- Test: `tests/test_sync.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_sync.py
from shufflesync import sync, device, itunesdb


def _nano_device(tmp_path):
    root = tmp_path / "NANO"
    (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    return device.IpodDevice(root, device.DeviceFamily.NANO_1G_3G)


def test_mirror_sync_nano_writes_itunesdb(tmp_path, monkeypatch):
    # two real tiny mp3s with tags so metadata.read_metadata works
    from tests.test_metadata import _make_mp3
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    a, b = src_dir / "01 A.mp3", src_dir / "02 B.mp3"
    _make_mp3(a); _make_mp3(b)

    dev = _nano_device(tmp_path)
    count = sync.mirror_sync(dev, [a, b], playlist_name="My List")
    assert count == 2

    db = dev.db_path.read_bytes()
    assert db[0:4] == b"mhbd"
    assert "My List".encode("utf-16-le") in db
    # files copied into the iPod Music tree
    assert (dev.music_dir / "F00" / "T0001.mp3").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_sync.py::test_mirror_sync_nano_writes_itunesdb -v`
Expected: FAIL (`mirror_sync() got an unexpected keyword argument 'playlist_name'`).

- [ ] **Step 3: Refactor `sync.py`**

Replace the body of `mirror_sync` so it shares the copy loop and dispatches by
family. Full new file:

```python
# src/shufflesync/sync.py
"""Mirror a list of audio files onto an iPod: wipe, copy, write the database."""
import shutil
from pathlib import Path
from typing import List

from . import itunessd, itunesdb, metadata
from .device import DeviceFamily, IpodDevice

FILES_PER_FOLDER = 100
CAPACITY_MARGIN = 1 * 1024 * 1024  # leave 1 MiB headroom


def _filetype(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".mp3":
        return "mp3"
    if ext in (".m4a", ".aac"):
        return "aac"
    if ext == ".wav":
        return "wav"
    return "mp3"


def _device_path(folder: str, name: str, colon: bool) -> str:
    parts = ["iPod_Control", "Music", folder, name]
    return (":" + ":".join(parts)) if colon else ("/" + "/".join(parts))


def mirror_sync(
    device: IpodDevice, source_files: List[Path], playlist_name: str = "shufflesync"
) -> int:
    """Replace the device's music with `source_files` (in order). Returns count."""
    music = device.music_dir
    if music.exists():
        shutil.rmtree(music)
    music.mkdir(parents=True)

    free = shutil.disk_usage(device.root).free - CAPACITY_MARGIN
    used = 0
    copied = []  # (folder, name, src) in order
    skipped = 0
    index = 0

    for src in source_files:
        size = src.stat().st_size
        if used + size > free:
            skipped += 1
            continue
        folder = f"F{index // FILES_PER_FOLDER:02d}"
        name = f"T{index + 1:04d}{src.suffix.lower()}"
        (music / folder).mkdir(exist_ok=True)
        shutil.copy2(src, music / folder / name)
        copied.append((folder, name, src))
        used += size
        index += 1

    device.db_path.parent.mkdir(parents=True, exist_ok=True)
    if device.family == DeviceFamily.SHUFFLE_2G:
        tracks = [
            (_device_path(f, n, colon=False), _filetype(s)) for f, n, s in copied
        ]
        device.db_path.write_bytes(itunessd.build_itunessd(tracks))
    else:
        entries = []
        for i, (f, n, s) in enumerate(copied, start=1):
            m = metadata.read_metadata(s)
            entries.append(itunesdb.TrackEntry(
                track_id=i, title=m.title, artist=m.artist, album=m.album,
                genre=m.genre, location=_device_path(f, n, colon=True),
                size=m.size, duration_ms=m.duration_ms, bitrate=m.bitrate,
                sample_rate=m.sample_rate, track_number=m.track_number, year=m.year,
            ))
        device.db_path.write_bytes(itunesdb.build_itunesdb(entries, playlist_name))

    if skipped:
        print(f"Skipped {skipped} track(s): not enough space on device.")
    return len(copied)
```

- [ ] **Step 4: Pass a playlist name from the CLI**

In `src/shufflesync/cli.py`, derive a name and pass it. After computing
`playlist_id` and before syncing, change the sync call:
```python
    playlist_name = playlist_id  # best-effort; spotdl save names are not exposed here
    print(f"Syncing {len(files)} track(s) to {dev.root} ...")
    synced = sync.mirror_sync(dev, files, playlist_name=playlist_name)
```
(Existing `test_cli.py` `fake_sync` signature must accept `playlist_name`; update
`def fake_sync(dev, files, playlist_name=...)`.)

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_sync.py tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/shufflesync/sync.py src/shufflesync/cli.py tests/test_sync.py tests/test_cli.py
git commit -m "feat: dispatch mirror sync by device family (shuffle/nano)"
```

---

## Task 9: Real-device validation + synthetic committed fixture

**Files:**
- Create: `tests/fixtures/golden_nano/iTunesDB` (synthetic)
- Create: `tests/test_itunesdb_golden.py`

- [ ] **Step 1: Sync a few real tracks to the nano**

With the nano mounted at `/Volumes/IPOD`, run a small sync end-to-end:
```bash
.venv/bin/shufflesync --count 3 "https://open.spotify.com/playlist/<a small public playlist>"
```
Eject, unplug, and confirm on the device: the tracks appear under Music and under
Playlists → the playlist name, and they play. If the library shows empty,
re-check Task 0 offsets and the `mhbd` version/hash-scheme fields.

- [ ] **Step 2: Generate a synthetic golden fixture (no personal data)**

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from shufflesync import itunesdb
entries = [
    itunesdb.TrackEntry(
        track_id=i, title=f"Test Track {i}", artist="Test Artist",
        album="Test Album", genre="Test", location=f":iPod_Control:Music:F00:T{i:04d}.mp3",
        size=1000 * i, duration_ms=2000 * i, bitrate=192, sample_rate=44100,
        track_number=i, year=2009,
    ) for i in (1, 2, 3)
]
out = Path("tests/fixtures/golden_nano"); out.mkdir(parents=True, exist_ok=True)
(out / "iTunesDB").write_bytes(itunesdb.build_itunesdb(entries, "Test Playlist"))
print("wrote", out / "iTunesDB")
PY
```

- [ ] **Step 3: Write a golden round-trip test**

```python
# tests/test_itunesdb_golden.py
import struct
from pathlib import Path
from shufflesync import itunesdb

GOLDEN = Path(__file__).parent / "fixtures" / "golden_nano" / "iTunesDB"


def test_synthetic_golden_is_reproducible():
    entries = [
        itunesdb.TrackEntry(
            track_id=i, title=f"Test Track {i}", artist="Test Artist",
            album="Test Album", genre="Test",
            location=f":iPod_Control:Music:F00:T{i:04d}.mp3",
            size=1000 * i, duration_ms=2000 * i, bitrate=192, sample_rate=44100,
            track_number=i, year=2009,
        ) for i in (1, 2, 3)
    ]
    assert itunesdb.build_itunesdb(entries, "Test Playlist") == GOLDEN.read_bytes()


def test_golden_has_two_datasets_and_playlist_name():
    db = GOLDEN.read_bytes()
    assert db[0:4] == b"mhbd"
    assert struct.unpack_from("<I", db, 0x14)[0] == 2
    assert "Test Playlist".encode("utf-16-le") in db
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_itunesdb_golden.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/golden_nano/iTunesDB tests/test_itunesdb_golden.py
git commit -m "test: synthetic golden iTunesDB fixture + round-trip test"
```

---

## Task 10: Docs

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document nano support**

Add a short section to `README.md` noting that shufflesync now auto-detects and
supports the 1st–3rd gen iPod nano in addition to the 2nd-gen shuffle, including
the manual disk-mode hint for old nanos that modern macOS won't manage. State
the limitation clearly: **only the 2nd-gen shuffle and 1st–3rd gen nano are
supported.** Checksummed iPods (nano 4G+, classic, touch) are not — syncing to
them would replace their music and leave an empty library.

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: note iPod nano (1-3G) support"
```

---

## Self-review notes

- **Spec coverage:** `IpodDevice`/dispatch (Tasks 7–8) ✓; itunesdb writer little-endian with master+named playlist (Tasks 2–6) ✓; mutagen metadata (Task 1) ✓; privacy — synthetic committed fixture, real DB git-ignored (Task 9) ✓; error handling for unsupported/no device (Task 7) ✓; nano disk-mode hint (Task 7) ✓. **Divergence:** the spec's mhbd-checksum-based refusal is downgraded to file-based detection + documented limitation (see the detection note in Task 7), because the checksum-field offset can't be located from a single un-checksummed sample. Reconcile with the spec before/after implementation.
- **Empirical unknowns are tasks, not placeholders:** Task 0 pins `MHIT_OFFSETS` (size/length_ms). If Task 0 disagrees with the assumed `0x28`/`0x24`, update that constant in `itunesdb.py` — the tests assert via the named constant so they stay consistent.
- **Type consistency:** `TrackEntry`, `TrackMeta`, `IpodDevice`, `DeviceFamily`, `MHIT_OFFSETS`, `build_itunesdb(entries, playlist_name)`, `mirror_sync(device, files, playlist_name=...)` are used consistently across tasks.
