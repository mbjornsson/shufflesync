# iPod nano `--add` Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add an opt-in, nano-only `--add` mode that adds a Spotify playlist to the nano without erasing existing music, idempotent per playlist.

**Architecture:** A new `itunesdb_reader.py` parses the existing DB keeping every record verbatim; `itunesdb.py` gains assemblers that wrap raw records; `manifest.py` tracks what shufflesync owns; `sync.add_sync` merges (preserve user data, prune our previous run, append new). Spec: `docs/superpowers/specs/2026-06-03-nano-add-mode-design.md`.

**Tech Stack:** Python ≥3.9, `struct`, pytest. Builds on the existing `itunesdb.py` writer and `device.py`.

---

## File structure
- `src/shufflesync/itunesdb_reader.py` (new) — `parse`, `RawTrack`, `RawPlaylist`, `ParsedDB`.
- `src/shufflesync/itunesdb.py` (modify) — `track_dataset_from_records`, `playlist_dataset_from_records`, `master_playlist`; refactor `build_itunesdb`.
- `src/shufflesync/manifest.py` (new) — `load`, `Manifest.reconcile`, `Manifest.save`.
- `src/shufflesync/sync.py` (modify) — `add_sync`.
- `src/shufflesync/cli.py` (modify) — `--add`.
- Tests: `tests/test_itunesdb_reader.py`, `tests/test_manifest.py`, additions to `tests/test_itunesdb.py`, `tests/test_sync.py`, `tests/test_cli.py`.

---

## Task 1: iTunesDB reader

**Files:** Create `src/shufflesync/itunesdb_reader.py`, `tests/test_itunesdb_reader.py`.

- [ ] **Step 1: Failing test**
```python
import struct
from shufflesync import itunesdb, itunesdb_reader


def _entry(i):
    return itunesdb.TrackEntry(
        track_id=i, title=f"T{i}", artist="A", album="Al", genre="G",
        location=f":iPod_Control:Music:F00:T{i:04d}.mp3",
        size=1000, duration_ms=2000, bitrate=192, sample_rate=44100,
        track_number=i, year=2009,
    )


def test_parse_recovers_tracks_and_playlist():
    blob = itunesdb.build_itunesdb([_entry(7), _entry(9)], "My Mix")
    db = itunesdb_reader.parse(blob)
    assert [t.track_id for t in db.tracks] == [7, 9]
    assert db.max_track_id() == 9
    names = {p.name: p for p in db.playlists}
    assert "My Mix" in names
    assert names["My Mix"].track_ids == [7, 9]
    assert names["My Mix"].is_master is False
    master = [p for p in db.playlists if p.is_master]
    assert len(master) == 1
    assert master[0].track_ids == [7, 9]


def test_raw_track_bytes_are_verbatim_slices():
    blob = itunesdb.build_itunesdb([_entry(1)], "X")
    db = itunesdb_reader.parse(blob)
    assert db.tracks[0].raw[0:4] == b"mhit"
    assert db.tracks[0].raw in blob
```

- [ ] **Step 2: Run, confirm fail** — `.venv/bin/python -m pytest tests/test_itunesdb_reader.py -v`

- [ ] **Step 3: Implement `src/shufflesync/itunesdb_reader.py`**
```python
"""Parse an existing iTunesDB, keeping each record's bytes verbatim."""
import struct
from dataclasses import dataclass
from typing import List


def _u32(data: bytes, o: int) -> int:
    return struct.unpack_from("<I", data, o)[0]


@dataclass(frozen=True)
class RawTrack:
    track_id: int
    raw: bytes


@dataclass(frozen=True)
class RawPlaylist:
    name: str
    is_master: bool
    track_ids: List[int]
    raw: bytes


@dataclass
class ParsedDB:
    tracks: List[RawTrack]
    playlists: List[RawPlaylist]

    def max_track_id(self) -> int:
        return max((t.track_id for t in self.tracks), default=0)


def _string_mhod_text(data: bytes, o: int):
    """(type, text|None) for an mhod at offset o; text only for string types."""
    mtype = _u32(data, o + 12)
    if mtype in (1, 2, 3, 4, 5):
        blen = _u32(data, o + 0x1C)
        return mtype, data[o + 40:o + 40 + blen].decode("utf-16-le", "replace")
    return mtype, None


def parse(data: bytes) -> ParsedDB:
    if data[0:4] != b"mhbd":
        raise ValueError("not an iTunesDB (missing mhbd header)")
    tracks: List[RawTrack] = []
    playlists: List[RawPlaylist] = []
    o = _u32(data, 4)                       # past mhbd header
    for _ in range(_u32(data, 0x14)):       # dataset count
        if data[o:o + 4] != b"mhsd":
            break
        ds_total = _u32(data, o + 8)
        ds_type = _u32(data, o + 12)
        inner = o + _u32(data, o + 4)
        if ds_type == 1 and data[inner:inner + 4] == b"mhlt":
            count = _u32(data, inner + 8)
            t = inner + _u32(data, inner + 4)
            for _ in range(count):
                if data[t:t + 4] != b"mhit":
                    break
                total = _u32(data, t + 8)
                tracks.append(RawTrack(_u32(data, t + 0x10), data[t:t + total]))
                t += total
        elif ds_type == 2 and data[inner:inner + 4] == b"mhlp":
            count = _u32(data, inner + 8)
            p = inner + _u32(data, inner + 4)
            for _ in range(count):
                if data[p:p + 4] != b"mhyp":
                    break
                ptot = _u32(data, p + 8)
                nmhod = _u32(data, p + 12)
                nitems = _u32(data, p + 0x10)
                is_master = _u32(data, p + 0x14) == 1
                q = p + _u32(data, p + 4)
                name = ""
                for _ in range(nmhod):
                    if data[q:q + 4] != b"mhod":
                        break
                    mtype, text = _string_mhod_text(data, q)
                    if mtype == 1 and text is not None:
                        name = text
                    q += _u32(data, q + 8)
                track_ids = []
                for _ in range(nitems):
                    if data[q:q + 4] != b"mhip":
                        break
                    track_ids.append(_u32(data, q + 0x18))
                    q += _u32(data, q + 8)
                playlists.append(RawPlaylist(name, is_master, track_ids, data[p:p + ptot]))
                p += ptot
        o += ds_total
    return ParsedDB(tracks, playlists)
```

- [ ] **Step 4: Run, confirm pass.** **Step 5: Commit** `feat: iTunesDB reader (verbatim record parsing)`.

---

## Task 2: Assemblers from raw records

**Files:** Modify `src/shufflesync/itunesdb.py`, `tests/test_itunesdb.py`.

- [ ] **Step 1: Failing test**
```python
def test_assemblers_and_master_playlist():
    a = itunesdb.track_mhit(_entry(1))
    b = itunesdb.track_mhit(_entry(2))
    ds = itunesdb.track_dataset_from_records([a, b])
    assert ds[0:4] == b"mhsd" and _u32(ds, 0x0c) == 1
    assert _u32(ds[96:], 8) == 2                      # mhlt count
    m = itunesdb.master_playlist([1, 2])
    assert m[0:4] == b"mhyp" and _u32(m, 0x14) == 1   # master flag
    assert _u32(m, 0x10) == 2                          # item count
    pds = itunesdb.playlist_dataset_from_records([m])
    assert pds[0:4] == b"mhsd" and _u32(pds, 0x0c) == 2
    assert _u32(pds[96:], 8) == 1                      # one playlist
```
(`_entry` and `_u32` already exist in this test file.)

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Refactor `itunesdb.py`.** Add the assemblers and `master_playlist`, and rewrite the existing `track_dataset`, `playlist_dataset`, `build_itunesdb` to use them. Keep `_mhsd`, `_mhyp`, `string_mhod`, etc.
```python
def track_dataset_from_records(mhit_records):
    mhlt = bytearray(92)
    mhlt[0:4] = b"mhlt"
    mhlt[4:8] = _u32(92)
    mhlt[8:12] = _u32(len(mhit_records))
    return _mhsd(1, bytes(mhlt) + b"".join(mhit_records))


def playlist_dataset_from_records(mhyp_records):
    mhlp = bytearray(92)
    mhlp[0:4] = b"mhlp"
    mhlp[4:8] = _u32(92)
    mhlp[8:12] = _u32(len(mhyp_records))
    return _mhsd(2, bytes(mhlp) + b"".join(mhyp_records))


def master_playlist(track_ids, name="iPod"):
    return _mhyp(name, track_ids, is_master=True)


def named_playlist(name, track_ids):
    return _mhyp(name, track_ids, is_master=False)
```
Then:
```python
def track_dataset(entries):
    return track_dataset_from_records([track_mhit(e) for e in entries])


def playlist_dataset(playlist_name, track_ids):
    return playlist_dataset_from_records([
        master_playlist(track_ids, "shufflesync"),
        named_playlist(playlist_name, track_ids),
    ])
```
`build_itunesdb` is unchanged in behavior (still `track_dataset(entries) + playlist_dataset(name, ids)` wrapped in `_mhbd(2, ...)`).

- [ ] **Step 4: Run the FULL suite** — the existing `test_itunesdb_golden.py` round-trip MUST still pass (proves the refactor changed no bytes). **Step 5: Commit** `refactor: iTunesDB assemblers from raw records`.

---

## Task 3: Manifest

**Files:** Create `src/shufflesync/manifest.py`, `tests/test_manifest.py`.

- [ ] **Step 1: Failing test**
```python
from shufflesync import manifest, itunesdb_reader, itunesdb


def test_manifest_roundtrip(tmp_path):
    m = manifest.Manifest({"Mix": {"track_ids": [5], "files": ["F00/T0001.mp3"]}})
    m.save(tmp_path)
    again = manifest.load(tmp_path)
    assert again.playlists == {"Mix": {"track_ids": [5], "files": ["F00/T0001.mp3"]}}


def test_load_missing_is_empty(tmp_path):
    assert manifest.load(tmp_path).playlists == {}


def test_reconcile_drops_ids_absent_from_db(tmp_path):
    # DB has track 5 only; manifest also claims 99
    blob = itunesdb.build_itunesdb(
        [itunesdb.TrackEntry(track_id=5, title="t", artist="", album="", genre="",
                             location=":x", size=1, duration_ms=1, bitrate=1,
                             sample_rate=44100, track_number=1, year=2000)], "Mix")
    db = itunesdb_reader.parse(blob)
    (tmp_path / "F00").mkdir()
    (tmp_path / "F00" / "T0001.mp3").write_bytes(b"x")
    m = manifest.Manifest({"Mix": {"track_ids": [5, 99],
                                   "files": ["F00/T0001.mp3", "F00/gone.mp3"]}})
    m.reconcile(db, tmp_path)
    assert m.playlists["Mix"]["track_ids"] == [5]
    assert m.playlists["Mix"]["files"] == ["F00/T0001.mp3"]
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Implement `src/shufflesync/manifest.py`**
```python
"""Track which tracks/playlists shufflesync added to a device."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

FILENAME = ".shufflesync.json"


@dataclass
class Manifest:
    playlists: Dict[str, dict] = field(default_factory=dict)

    def reconcile(self, parsed_db, music_dir: Path) -> None:
        live_ids = {t.track_id for t in parsed_db.tracks}
        for name, info in list(self.playlists.items()):
            info["track_ids"] = [i for i in info.get("track_ids", []) if i in live_ids]
            info["files"] = [
                f for f in info.get("files", []) if (music_dir / f).exists()
            ]

    def save(self, itunes_dir: Path) -> None:
        (itunes_dir / FILENAME).write_text(json.dumps({"playlists": self.playlists}))


def load(itunes_dir: Path) -> Manifest:
    path = itunes_dir / FILENAME
    if not path.exists():
        return Manifest()
    data = json.loads(path.read_text())
    return Manifest(data.get("playlists", {}))
```
Note: `reconcile` takes `music_dir` for file existence checks; the spec's wording is satisfied (ids checked against the DB, files against disk).

- [ ] **Step 4: Run, confirm pass.** **Step 5: Commit** `feat: shufflesync device manifest`.

---

## Task 4: add_sync merge

**Files:** Modify `src/shufflesync/sync.py`, `tests/test_sync.py`.

- [ ] **Step 1: Failing test** (add to `tests/test_sync.py`; reuse the `_make_mp3` helper added earlier)
```python
from shufflesync import sync, device, itunesdb, itunesdb_reader, manifest


def _nano_with_library(tmp_path):
    """A nano whose DB already has one user track (id 1) and a user playlist."""
    root = tmp_path / "NANO"
    itunes = root / "iPod_Control" / "iTunes"
    itunes.mkdir(parents=True)
    music = root / "iPod_Control" / "Music" / "F00"
    music.mkdir(parents=True)
    (music / "USER.mp3").write_bytes(b"user-song")
    user = itunesdb.TrackEntry(
        track_id=1, title="User Song", artist="U", album="UA", genre="Rock",
        location=":iPod_Control:Music:F00:USER.mp3", size=9, duration_ms=1000,
        bitrate=192, sample_rate=44100, track_number=1, year=2000)
    # build a library DB: one track, master + a user playlist "Faves"
    blob = itunesdb._mhbd(2, itunesdb.track_dataset([user]) +
                          itunesdb.playlist_dataset_from_records([
                              itunesdb.master_playlist([1], "iPod"),
                              itunesdb.named_playlist("Faves", [1])]))
    (itunes / "iTunesDB").write_bytes(blob)
    return device.IpodDevice(root, device.DeviceFamily.NANO_1G_3G)


def test_add_sync_preserves_library_and_adds_playlist(tmp_path):
    dev = _nano_with_library(tmp_path)
    src = tmp_path / "src"; src.mkdir()
    a = src / "01 New.mp3"; _make_mp3(a)

    before = itunesdb_reader.parse(dev.db_path.read_bytes())
    user_raw_before = [t.raw for t in before.tracks if t.track_id == 1][0]

    sync.add_sync(dev, [a], playlist_name="Evening")

    db = itunesdb_reader.parse(dev.db_path.read_bytes())
    ids = {t.track_id for t in db.tracks}
    assert 1 in ids                       # user track preserved
    assert len(db.tracks) == 2            # user + 1 new
    names = {p.name for p in db.playlists}
    assert {"Faves", "Evening"}.issubset(names)
    master = [p for p in db.playlists if p.is_master][0]
    assert set(master.track_ids) == ids   # master lists everything
    # user's original track record kept byte-for-byte (verbatim preservation)
    user_raw_after = [t.raw for t in db.tracks if t.track_id == 1][0]
    assert user_raw_after == user_raw_before
    assert (dev.music_dir / "F00" / "USER.mp3").exists()  # user file untouched
```

```python
def test_add_sync_is_idempotent_per_playlist(tmp_path):
    dev = _nano_with_library(tmp_path)
    src = tmp_path / "src"; src.mkdir()
    a = src / "01 New.mp3"; _make_mp3(a)
    sync.add_sync(dev, [a], playlist_name="Evening")
    first = itunesdb_reader.parse(dev.db_path.read_bytes())
    sync.add_sync(dev, [a], playlist_name="Evening")   # re-run same playlist
    second = itunesdb_reader.parse(dev.db_path.read_bytes())
    # no duplicate pile-up: same track count both times
    assert len(second.tracks) == len(first.tracks)
    assert [p.name for p in second.playlists].count("Evening") == 1


def test_add_sync_writes_backup(tmp_path):
    dev = _nano_with_library(tmp_path)
    src = tmp_path / "src"; src.mkdir()
    a = src / "01 New.mp3"; _make_mp3(a)
    sync.add_sync(dev, [a], playlist_name="Evening")
    backups = list((dev.db_path.parent / "shufflesync-backup").glob("*/iTunesDB"))
    assert backups
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Implement `add_sync` in `sync.py`**
```python
import datetime
import json

from . import itunesdb, itunesdb_reader, manifest


def _existing_names(music: Path):
    return {p.name for p in music.rglob("*") if p.is_file()}


def _free_name(taken: set, index: int, suffix: str) -> str:
    name = f"S{index:04d}{suffix}"
    while name in taken:
        index += 1
        name = f"S{index:04d}{suffix}"
    taken.add(name)
    return name


def add_sync(device: IpodDevice, source_files: List[Path],
             playlist_name: str = "shufflesync") -> int:
    if device.family != DeviceFamily.NANO_1G_3G:
        raise ValueError("--add is only supported for the iPod nano")
    itunes = device.db_path.parent
    music = device.music_dir

    # 1. Back up before any mutation.
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = itunes / "shufflesync-backup" / stamp
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(device.db_path, backup / "iTunesDB")
    man_path = itunes / manifest.FILENAME
    if man_path.exists():
        shutil.copy2(man_path, backup / manifest.FILENAME)

    # 2. Parse (fail closed before any copy/delete).
    parsed = itunesdb_reader.parse(device.db_path.read_bytes())

    # 3. Load + reconcile manifest.
    man = manifest.load(itunes)
    man.reconcile(parsed, music)

    # 4. Prune previous run of this playlist.
    prev = man.playlists.pop(playlist_name, {"track_ids": [], "files": []})
    prune_ids = set(prev["track_ids"])
    for rel in prev["files"]:
        f = music / rel
        if f.exists():
            f.unlink()
    kept_tracks = [t for t in parsed.tracks if t.track_id not in prune_ids]

    # 5. Copy new files (collision-safe).
    music.mkdir(parents=True, exist_ok=True)
    taken = _existing_names(music)
    folder = music / "F90"; folder.mkdir(exist_ok=True)
    next_id = max([t.track_id for t in kept_tracks] + [0]) + 1
    new_records, new_ids, new_files = [], [], []
    for i, src in enumerate(source_files):
        name = _free_name(taken, i + 1, src.suffix.lower())
        shutil.copy2(src, folder / name)
        m = metadata.read_metadata(src)
        tid = next_id + i
        loc = f":iPod_Control:Music:F90:{name}"
        new_records.append(itunesdb.track_mhit(itunesdb.TrackEntry(
            track_id=tid, title=m.title, artist=m.artist, album=m.album,
            genre=m.genre, location=loc, size=m.size, duration_ms=m.duration_ms,
            bitrate=m.bitrate, sample_rate=m.sample_rate,
            track_number=m.track_number, year=m.year)))
        new_ids.append(tid)
        new_files.append(f"F90/{name}")

    # 6. Reassemble: tracks = kept (verbatim) + new; playlists = master(all) +
    #    user/other-managed non-master verbatim + new managed playlist.
    all_track_records = [t.raw for t in kept_tracks] + new_records
    all_ids = [t.track_id for t in kept_tracks] + new_ids
    kept_playlists = [p.raw for p in parsed.playlists
                      if not p.is_master and p.name != playlist_name]
    playlist_records = (
        [itunesdb.master_playlist(all_ids)]
        + kept_playlists
        + [itunesdb.named_playlist(playlist_name, new_ids)]
    )
    blob = itunesdb._mhbd(
        2,
        itunesdb.track_dataset_from_records(all_track_records)
        + itunesdb.playlist_dataset_from_records(playlist_records),
    )
    device.db_path.write_bytes(blob)

    # 7. Update + save manifest.
    man.playlists[playlist_name] = {"track_ids": new_ids, "files": new_files}
    man.save(itunes)
    return len(new_ids)
```
NOTE: `_mhbd`, `track_dataset_from_records`, etc. are in `itunesdb.py` (some are name-mangled-free module functions). `_mhbd` is module-private but importable as `itunesdb._mhbd`. If the implementer prefers, add a public `itunesdb.assemble(track_records, playlist_records)` wrapper instead of reaching for `_mhbd`; do that and use it in both `build_itunesdb` and here.

- [ ] **Step 4: Run, confirm pass** (all four add_sync tests). **Step 5: Run full suite.** **Step 6: Commit** `feat: nano --add merge (preserve library, idempotent per playlist)`.

---

## Task 5: CLI `--add`

**Files:** Modify `src/shufflesync/cli.py`, `tests/test_cli.py`.

- [ ] **Step 1: Failing test**
```python
def test_main_add_flag_calls_add_sync(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])
    monkeypatch.setattr(cli.downloader, "download_playlist",
                        lambda *a, **k: [tmp_path / "a.mp3"])
    class Dev:
        root = tmp_path
        family = cli.device.DeviceFamily.NANO_1G_3G
    monkeypatch.setattr(cli.device, "select_ipod", lambda: Dev())
    called = {}
    monkeypatch.setattr(cli.sync, "add_sync",
                        lambda dev, files, playlist_name: called.setdefault("add", True) or len(files))
    monkeypatch.setattr(cli.sync, "mirror_sync",
                        lambda *a, **k: called.setdefault("mirror", True) or 0)
    rc = cli.main(["https://open.spotify.com/playlist/abc", "--add"])
    assert rc == 0
    assert called == {"add": True}


def test_main_add_rejected_for_shuffle(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])
    monkeypatch.setattr(cli.downloader, "download_playlist",
                        lambda *a, **k: [tmp_path / "a.mp3"])
    class Dev:
        root = tmp_path
        family = cli.device.DeviceFamily.SHUFFLE_2G
    monkeypatch.setattr(cli.device, "select_ipod", lambda: Dev())
    rc = cli.main(["https://open.spotify.com/playlist/abc", "--add"])
    assert rc == 1
    assert "shuffle" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run, confirm fail.**

- [ ] **Step 3: Implement.** Add the argparse flag:
```python
    parser.add_argument(
        "--add", action="store_true",
        help="Add this playlist to the iPod without erasing existing music (iPod nano only).",
    )
```
After `dev = device.select_ipod()` succeeds, branch:
```python
    print(f"Syncing {len(files)} track(s) to {dev.root} ...")
    if args.add:
        if dev.family == device.DeviceFamily.SHUFFLE_2G:
            print("--add is only for the iPod nano; the shuffle is always a full mirror.",
                  file=sys.stderr)
            return 1
        synced = sync.add_sync(dev, files, playlist_name=playlist_name)
    else:
        synced = sync.mirror_sync(dev, files, playlist_name=playlist_name)
    print(f"Done. {synced} track(s) on the iPod. Eject before unplugging.")
    return 0
```

- [ ] **Step 4: Run, confirm pass.** **Step 5: Full suite.** **Step 6: Commit** `feat: --add CLI flag for non-destructive nano sync`.

---

## Task 6: README + real-device validation

- [ ] **Step 1:** Document `--add` in `README.md` (nano-only; adds without erasing; idempotent per playlist; backups written under `iPod_Control/iTunes/shufflesync-backup/`). Commit `docs: document nano --add mode`.
- [ ] **Step 2 (manual, user-run):** With the nano mounted, `uv run shufflesync --add "<small playlist>"`, eject, and confirm on the device that **both the existing music and the new playlist play**. Back up the device first. This is the real gate before relying on `--add`.

---

## Self-review notes
- **Spec coverage:** reader (T1) ✓; assemblers + master_playlist (T2) ✓; manifest load/save/reconcile (T3) ✓; add_sync merge with backup/prune/collision-safe copy/verbatim preserve/rebuilt master/drop extras (T4) ✓; CLI `--add` nano-only (T5) ✓; docs + manual validation (T6) ✓.
- **Type consistency:** `RawTrack`, `RawPlaylist`, `ParsedDB.max_track_id`, `Manifest.playlists`/`reconcile(parsed_db, music_dir)`/`save`/`load`, `track_dataset_from_records`, `playlist_dataset_from_records`, `master_playlist`, `named_playlist`, `add_sync(device, files, playlist_name)` are used consistently.
- **Risk:** the master-playlist rebuild and dropping datasets 3–9 are validated by the existing writer golden test + the manual on-device check (T6). Real-device validation is the gate before trusting `--add` with a real library.
