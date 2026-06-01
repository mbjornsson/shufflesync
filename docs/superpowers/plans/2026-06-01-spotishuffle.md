# spotishuffle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A one-command macOS CLI that downloads a Spotify playlist (via `spotdl`) and mirrors it onto a 2nd-gen iPod shuffle by writing the device's native `iTunesSD` database directly — no iTunes required.

**Architecture:** Three components with clear boundaries. `itunessd.py` serializes the binary database (validated byte-for-byte against a real-hardware golden fixture). `device.py` locates the mounted shuffle. `downloader.py` wraps `spotdl`. `sync.py` orchestrates mirror-sync (wipe → copy → write DB). `cli.py` wires it into one command.

**Tech Stack:** Python 3, `spotdl` (+ `yt-dlp`, `ffmpeg`) as external download engine, `pytest` for tests. Standard library only for the sync/serialization code.

---

## Reference: validated `iTunesSD` format (2nd-gen shuffle)

Confirmed against `tests/fixtures/golden_device/iTunes/iTunesSD` (11 tracks, 6156 bytes = 18 + 11×558).

**Header — 18 bytes:**
| Offset | Len | Meaning | Value |
|--------|-----|---------|-------|
| 0 | 3 | track count | big-endian uint24 |
| 3 | 15 | fixed constant | `01 08 00 00 00 12 00 00 00 00 00 00 00 00 00` |

**Entry — 558 bytes each:**
| Offset | Len | Meaning | Our value |
|--------|-----|---------|-----------|
| 0 | 3 | entry length | `00 02 2e` (558) |
| 3 | 26 | iTunes analysis/unknown bytes (shuffle ignores) | all zero |
| 29 | 1 | filetype | `01`=MP3, `02`=AAC |
| 30 | 1 | zero | `00` |
| 31 | 1 | filetype (mirror) | `01`=MP3, `02`=AAC |
| 32 | 522 | file path, UTF-16BE, NUL-padded | e.g. `/iPod_Control/Music/F00/T0001.mp3` |
| 554 | 1 | zero | `00` |
| 555 | 1 | "don't skip on shuffle" flag | `01` |
| 556 | 2 | zero | `00 00` |

> Note: iTunes writes nonzero "analysis" bytes in offsets 3–28 (e.g. `5a a5 01`, per-track `ff ff f9` gain). These derive from audio analysis we can't reproduce from a path and the shuffle does not require them — `shuffle-db`/libgpod zero them and playback works. We zero them too. The golden fixture therefore validates the **structural** bytes (offsets 0–2, 29–31, the path field, and 554–557), not the analysis bytes.

---

## File Structure

- Create: `pyproject.toml` — packaging + `spotishuffle` console script + pytest config
- Create: `src/spotishuffle/__init__.py`
- Create: `src/spotishuffle/itunessd.py` — `build_header`, `encode_path`, `build_entry`, `build_itunessd`
- Create: `src/spotishuffle/device.py` — `find_shuffles`, `select_shuffle`, `ShuffleDevice`
- Create: `src/spotishuffle/downloader.py` — `check_dependencies`, `download_playlist`
- Create: `src/spotishuffle/sync.py` — `mirror_sync`
- Create: `src/spotishuffle/cli.py` — `main`
- Create: `tests/test_itunessd.py`, `tests/test_device.py`, `tests/test_downloader.py`, `tests/test_sync.py`
- Existing: `tests/fixtures/golden_device/iTunes/iTunesSD` (golden fixture, already committed)
- Create: `README.md`

---

## Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/spotishuffle/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "spotishuffle"
version = "0.1.0"
description = "Download a Spotify playlist and mirror it onto a 2nd-gen iPod shuffle"
requires-python = ">=3.9"
dependencies = ["spotdl>=4"]

[project.scripts]
spotishuffle = "spotishuffle.cli:main"

[project.optional-dependencies]
dev = ["pytest>=7"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package + test init files**

```bash
mkdir -p src/spotishuffle tests
touch src/spotishuffle/__init__.py tests/__init__.py
```

- [ ] **Step 3: Verify pytest collects (zero tests is fine)**

Run: `python3 -m pytest -q`
Expected: `no tests ran` (exit ok), no import/config errors.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/spotishuffle/__init__.py tests/__init__.py
git commit -m "chore: scaffold spotishuffle package"
```

---

## Task 2: `iTunesSD` header

**Files:**
- Create: `src/spotishuffle/itunessd.py`
- Test: `tests/test_itunessd.py`

- [ ] **Step 1: Write the failing test (byte-exact vs golden header)**

```python
# tests/test_itunessd.py
from pathlib import Path
from spotishuffle import itunessd

GOLDEN = Path(__file__).parent / "fixtures/golden_device/iTunes/iTunesSD"

def test_build_header_matches_golden():
    golden = GOLDEN.read_bytes()
    # golden has 11 tracks; header is the first 18 bytes
    assert itunessd.build_header(11) == golden[:18]

def test_build_header_count_is_big_endian():
    assert itunessd.build_header(1)[:3] == b"\x00\x00\x01"
    assert itunessd.build_header(258)[:3] == b"\x00\x01\x02"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_itunessd.py -q`
Expected: FAIL — `AttributeError: module 'spotishuffle.itunessd' has no attribute 'build_header'`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/spotishuffle/itunessd.py
"""Serializer for the 2nd-gen iPod shuffle iTunesSD database.

Format validated byte-for-byte against a real-hardware golden fixture.
See docs/superpowers/plans/2026-06-01-spotishuffle.md for the field tables.
"""

HEADER_CONST = bytes.fromhex("010800000012000000000000000000")  # 15 bytes


def build_header(track_count: int) -> bytes:
    """18-byte iTunesSD header: 3-byte big-endian count + 15 fixed bytes."""
    return track_count.to_bytes(3, "big") + HEADER_CONST
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_itunessd.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spotishuffle/itunessd.py tests/test_itunessd.py
git commit -m "feat: iTunesSD header serialization"
```

---

## Task 3: `iTunesSD` path field encoding

**Files:**
- Modify: `src/spotishuffle/itunessd.py`
- Test: `tests/test_itunessd.py`

- [ ] **Step 1: Write the failing test (path field byte-exact vs golden)**

```python
# add to tests/test_itunessd.py

def _golden_entry(i):
    golden = GOLDEN.read_bytes()
    start = 18 + i * 558
    return golden[start:start + 558]

def test_encode_path_matches_golden_field():
    # entry 0 path is /iPod_Control/Music/F00/YZUB.m4a (offset 32, length 522)
    entry0 = _golden_entry(0)
    field = entry0[32:32 + 522]
    assert itunessd.encode_path("/iPod_Control/Music/F00/YZUB.m4a") == field

def test_encode_path_is_522_bytes_utf16be_nul_padded():
    field = itunessd.encode_path("/x.mp3")
    assert len(field) == 522
    assert field[:12] == "/x.mp3".encode("utf-16-be")
    assert field[12:] == b"\x00" * (522 - 12)

def test_encode_path_rejects_overlong():
    import pytest
    with pytest.raises(ValueError):
        itunessd.encode_path("/" + "a" * 261)  # 262 UTF-16 units > 261
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_itunessd.py -q`
Expected: FAIL — no attribute `encode_path`.

- [ ] **Step 3: Implement**

```python
# add to src/spotishuffle/itunessd.py

PATH_FIELD_LEN = 522  # 261 UTF-16 code units


def encode_path(device_path: str) -> bytes:
    """Encode a device-relative path as UTF-16BE, NUL-padded to 522 bytes.

    `device_path` uses forward slashes, e.g. '/iPod_Control/Music/F00/T0001.mp3'.
    """
    encoded = device_path.encode("utf-16-be")
    if len(encoded) > PATH_FIELD_LEN:
        raise ValueError(f"path too long for iTunesSD field: {device_path!r}")
    return encoded + b"\x00" * (PATH_FIELD_LEN - len(encoded))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_itunessd.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/spotishuffle/itunessd.py tests/test_itunessd.py
git commit -m "feat: iTunesSD path field encoding"
```

---

## Task 4: `iTunesSD` entry

**Files:**
- Modify: `src/spotishuffle/itunessd.py`
- Test: `tests/test_itunessd.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_itunessd.py

def test_build_entry_structural_bytes_match_golden():
    # We zero iTunes' audio-analysis bytes (3..28), so compare only the
    # structural regions that must match for playback.
    entry0 = _golden_entry(0)
    ours = itunessd.build_entry("/iPod_Control/Music/F00/YZUB.m4a", filetype="aac")
    assert len(ours) == 558
    assert ours[0:3] == entry0[0:3]          # entry length 0x00022e
    assert ours[29] == entry0[29]            # filetype byte == 0x02 (aac)
    assert ours[31] == entry0[31]            # filetype mirror == 0x02
    assert ours[32:554] == entry0[32:554]    # path field
    assert ours[554:558] == entry0[554:558]  # tail 00 01 00 00

def test_build_entry_filetype_mp3():
    ours = itunessd.build_entry("/iPod_Control/Music/F00/T0001.mp3", filetype="mp3")
    assert ours[29] == 0x01
    assert ours[31] == 0x01

def test_build_entry_analysis_bytes_zeroed():
    ours = itunessd.build_entry("/x.mp3", filetype="mp3")
    assert ours[3:29] == b"\x00" * 26
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_itunessd.py -q`
Expected: FAIL — no attribute `build_entry`.

- [ ] **Step 3: Implement**

```python
# add to src/spotishuffle/itunessd.py

ENTRY_LEN = 558
_FILETYPE = {"mp3": 0x01, "aac": 0x02, "wav": 0x04}


def build_entry(device_path: str, filetype: str) -> bytes:
    """Build one 558-byte iTunesSD track record.

    filetype: 'mp3' | 'aac' | 'wav'. Audio-analysis bytes are zeroed
    (the shuffle does not require them; see plan reference table).
    """
    if filetype not in _FILETYPE:
        raise ValueError(f"unsupported filetype: {filetype!r}")
    ftype = _FILETYPE[filetype]
    entry = bytearray(ENTRY_LEN)
    entry[0:3] = (ENTRY_LEN).to_bytes(3, "big")   # 0x00022e
    # bytes 3..28 left zero (iTunes analysis data, ignored by device)
    entry[29] = ftype
    entry[31] = ftype
    entry[32:32 + PATH_FIELD_LEN] = encode_path(device_path)
    entry[555] = 0x01  # do-not-skip-on-shuffle flag
    return bytes(entry)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_itunessd.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/spotishuffle/itunessd.py tests/test_itunessd.py
git commit -m "feat: iTunesSD track entry serialization"
```

---

## Task 5: full `iTunesSD` document

**Files:**
- Modify: `src/spotishuffle/itunessd.py`
- Test: `tests/test_itunessd.py`

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_itunessd.py

def test_build_itunessd_size_and_count():
    tracks = [("/iPod_Control/Music/F00/T%04d.mp3" % i, "mp3") for i in range(5)]
    data = itunessd.build_itunessd(tracks)
    assert len(data) == 18 + 5 * 558
    assert data[:3] == b"\x00\x00\x05"

def test_build_itunessd_empty():
    data = itunessd.build_itunessd([])
    assert data == itunessd.build_header(0)
    assert len(data) == 18

def test_build_itunessd_concatenates_entries_in_order():
    tracks = [("/a.mp3", "mp3"), ("/b.aac", "aac")]
    data = itunessd.build_itunessd(tracks)
    assert data[18:18 + 558] == itunessd.build_entry("/a.mp3", "mp3")
    assert data[18 + 558:18 + 2 * 558] == itunessd.build_entry("/b.aac", "aac")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_itunessd.py -q`
Expected: FAIL — no attribute `build_itunessd`.

- [ ] **Step 3: Implement**

```python
# add to src/spotishuffle/itunessd.py
from typing import Iterable, Tuple


def build_itunessd(tracks: Iterable[Tuple[str, str]]) -> bytes:
    """Serialize the full iTunesSD. `tracks` is an ordered iterable of
    (device_path, filetype) pairs."""
    tracks = list(tracks)
    out = bytearray(build_header(len(tracks)))
    for device_path, filetype in tracks:
        out += build_entry(device_path, filetype)
    return bytes(out)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_itunessd.py -q`
Expected: PASS (all itunessd tests).

- [ ] **Step 5: Commit**

```bash
git add src/spotishuffle/itunessd.py tests/test_itunessd.py
git commit -m "feat: full iTunesSD document serialization"
```

---

## Task 6: Device manager

**Files:**
- Create: `src/spotishuffle/device.py`
- Test: `tests/test_device.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_device.py
import pytest
from spotishuffle import device


def _make_ipod(tmp_path, name):
    root = tmp_path / name
    (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    (root / "iPod_Control" / "Music").mkdir(parents=True)
    return root


def test_find_shuffles_detects_ipod(tmp_path):
    root = _make_ipod(tmp_path, "SHUFFLE")
    (tmp_path / "NotAnIpod").mkdir()
    found = device.find_shuffles(volumes_dir=tmp_path)
    assert found == [root]


def test_select_shuffle_zero_raises(tmp_path):
    with pytest.raises(device.NoDeviceError):
        device.select_shuffle(volumes_dir=tmp_path)


def test_select_shuffle_one_returns_device(tmp_path):
    root = _make_ipod(tmp_path, "SHUFFLE")
    dev = device.select_shuffle(volumes_dir=tmp_path)
    assert dev.root == root
    assert dev.music_dir == root / "iPod_Control" / "Music"
    assert dev.itunessd_path == root / "iPod_Control" / "iTunes" / "iTunesSD"


def test_select_shuffle_many_uses_chooser(tmp_path):
    a = _make_ipod(tmp_path, "A")
    b = _make_ipod(tmp_path, "B")
    dev = device.select_shuffle(volumes_dir=tmp_path, chooser=lambda opts: opts[1])
    assert dev.root == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_device.py -q`
Expected: FAIL — cannot import `device` / missing attributes.

- [ ] **Step 3: Implement**

```python
# src/spotishuffle/device.py
"""Locate a mounted 2nd-gen iPod shuffle on macOS."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional


class NoDeviceError(Exception):
    pass


@dataclass(frozen=True)
class ShuffleDevice:
    root: Path

    @property
    def music_dir(self) -> Path:
        return self.root / "iPod_Control" / "Music"

    @property
    def itunessd_path(self) -> Path:
        return self.root / "iPod_Control" / "iTunes" / "iTunesSD"


def find_shuffles(volumes_dir: Path = Path("/Volumes")) -> List[Path]:
    """Return mounts that contain an iPod_Control directory."""
    if not volumes_dir.exists():
        return []
    return sorted(
        p for p in volumes_dir.iterdir()
        if (p / "iPod_Control").is_dir()
    )


def select_shuffle(
    volumes_dir: Path = Path("/Volumes"),
    chooser: Optional[Callable[[List[Path]], Path]] = None,
) -> ShuffleDevice:
    """Find exactly one shuffle, or use `chooser` to pick among several."""
    candidates = find_shuffles(volumes_dir)
    if not candidates:
        raise NoDeviceError(
            "No iPod shuffle found. Plug it in and make sure it is mounted "
            "(it should appear under /Volumes and contain an iPod_Control folder)."
        )
    if len(candidates) == 1:
        return ShuffleDevice(candidates[0])
    if chooser is None:
        chooser = _interactive_chooser
    return ShuffleDevice(chooser(candidates))


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

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_device.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spotishuffle/device.py tests/test_device.py
git commit -m "feat: shuffle device detection"
```

---

## Task 7: Downloader (spotdl wrapper)

**Files:**
- Create: `src/spotishuffle/downloader.py`
- Test: `tests/test_downloader.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_downloader.py
import pytest
from spotishuffle import downloader


def test_check_dependencies_reports_missing(monkeypatch):
    monkeypatch.setattr(downloader.shutil, "which", lambda name: None)
    missing = downloader.check_dependencies()
    assert set(missing) == {"spotdl", "ffmpeg"}


def test_check_dependencies_all_present(monkeypatch):
    monkeypatch.setattr(downloader.shutil, "which", lambda name: "/usr/bin/" + name)
    assert downloader.check_dependencies() == []


def test_download_playlist_invokes_spotdl_and_returns_mp3s(monkeypatch, tmp_path):
    calls = {}

    def fake_run(cmd, cwd, check):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        # simulate spotdl writing two files (and an unrelated file)
        (tmp_path / "01 - Song A.mp3").write_bytes(b"a")
        (tmp_path / "02 - Song B.mp3").write_bytes(b"b")
        (tmp_path / "cover.jpg").write_bytes(b"x")
        class R: returncode = 0
        return R()

    monkeypatch.setattr(downloader.subprocess, "run", fake_run)
    files = downloader.download_playlist("https://open.spotify.com/playlist/abc", tmp_path)
    assert calls["cmd"][0] == "spotdl"
    assert "https://open.spotify.com/playlist/abc" in calls["cmd"]
    assert "--output" in calls["cmd"]
    assert [f.name for f in files] == ["01 - Song A.mp3", "02 - Song B.mp3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_downloader.py -q`
Expected: FAIL — cannot import `downloader`.

- [ ] **Step 3: Implement**

```python
# src/spotishuffle/downloader.py
"""Download a Spotify playlist as MP3s using the external `spotdl` tool."""
import shutil
import subprocess
from pathlib import Path
from typing import List

REQUIRED = ("spotdl", "ffmpeg")


def check_dependencies() -> List[str]:
    """Return the names of required external tools that are not on PATH."""
    return [name for name in REQUIRED if shutil.which(name) is None]


def download_playlist(playlist_url: str, dest: Path) -> List[Path]:
    """Run spotdl to download `playlist_url` into `dest`; return MP3 paths sorted by name."""
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        "spotdl",
        "download",
        playlist_url,
        "--output",
        str(dest / "{list-position} - {title}.{output-ext}"),
        "--format",
        "mp3",
    ]
    subprocess.run(cmd, cwd=dest, check=True)
    return sorted(dest.glob("*.mp3"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_downloader.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spotishuffle/downloader.py tests/test_downloader.py
git commit -m "feat: spotdl download wrapper with dependency check"
```

---

## Task 8: Sync engine (mirror)

**Files:**
- Create: `src/spotishuffle/sync.py`
- Test: `tests/test_sync.py`

Behavior: wipe `Music/`, copy source files into `Music/F00, F01, …` (100 per folder) with generated ASCII names `T0001.mp3`…, fit to free space in order (warn + skip overflow), then write `iTunesSD`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sync.py
from pathlib import Path
from spotishuffle import sync, itunessd
from spotishuffle.device import ShuffleDevice


def _device(tmp_path):
    root = tmp_path / "SHUFFLE"
    (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    (root / "iPod_Control" / "Music" / "OLD").mkdir(parents=True)
    (root / "iPod_Control" / "Music" / "OLD" / "stale.mp3").write_bytes(b"old")
    return ShuffleDevice(root)


def _src(tmp_path, n, size=4):
    src = tmp_path / "src"
    src.mkdir()
    files = []
    for i in range(n):
        f = src / f"{i:02d} song.mp3"
        f.write_bytes(b"x" * size)
        files.append(f)
    return files


def test_mirror_wipes_old_music(tmp_path):
    dev = _device(tmp_path)
    files = _src(tmp_path, 2)
    sync.mirror_sync(dev, files)
    assert not (dev.music_dir / "OLD").exists()


def test_mirror_copies_files_with_generated_names(tmp_path):
    dev = _device(tmp_path)
    files = _src(tmp_path, 2)
    synced = sync.mirror_sync(dev, files)
    assert (dev.music_dir / "F00" / "T0001.mp3").exists()
    assert (dev.music_dir / "F00" / "T0002.mp3").exists()
    assert synced == 2


def test_mirror_writes_itunessd_matching_files(tmp_path):
    dev = _device(tmp_path)
    files = _src(tmp_path, 2)
    sync.mirror_sync(dev, files)
    data = dev.itunessd_path.read_bytes()
    assert data[:3] == b"\x00\x00\x02"
    expected = itunessd.build_itunessd([
        ("/iPod_Control/Music/F00/T0001.mp3", "mp3"),
        ("/iPod_Control/Music/F00/T0002.mp3", "mp3"),
    ])
    assert data == expected


def test_mirror_buckets_at_100_per_folder(tmp_path):
    dev = _device(tmp_path)
    files = _src(tmp_path, 101)
    sync.mirror_sync(dev, files)
    assert (dev.music_dir / "F00" / "T0100.mp3").exists()
    assert (dev.music_dir / "F01" / "T0101.mp3").exists()


def test_mirror_skips_overflow_when_capacity_exceeded(tmp_path, monkeypatch, capsys):
    dev = _device(tmp_path)
    files = _src(tmp_path, 3, size=100)
    # effective free = reported free - CAPACITY_MARGIN; set it so ~150 bytes
    # are usable -> only the first 100-byte file fits.
    free = sync.CAPACITY_MARGIN + 150
    monkeypatch.setattr(sync.shutil, "disk_usage",
                        lambda p: type("U", (), {"free": free})())
    synced = sync.mirror_sync(dev, files)
    assert synced == 1
    assert "Skipped 2" in capsys.readouterr().out
    assert dev.itunessd_path.read_bytes()[:3] == b"\x00\x00\x01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_sync.py -q`
Expected: FAIL — cannot import `sync`.

- [ ] **Step 3: Implement**

```python
# src/spotishuffle/sync.py
"""Mirror a list of audio files onto a shuffle: wipe, copy, write iTunesSD."""
import shutil
from pathlib import Path
from typing import List

from . import itunessd
from .device import ShuffleDevice

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


def mirror_sync(device: ShuffleDevice, source_files: List[Path]) -> int:
    """Replace the device's music with `source_files` (in order). Returns count synced."""
    music = device.music_dir
    if music.exists():
        shutil.rmtree(music)
    music.mkdir(parents=True)

    free = shutil.disk_usage(device.root).free - CAPACITY_MARGIN
    used = 0
    tracks = []
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
        tracks.append((f"/iPod_Control/Music/{folder}/{name}", _filetype(src)))
        used += size
        index += 1

    device.itunessd_path.parent.mkdir(parents=True, exist_ok=True)
    device.itunessd_path.write_bytes(itunessd.build_itunessd(tracks))

    if skipped:
        print(f"Skipped {skipped} track(s): not enough space on device.")
    return len(tracks)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_sync.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spotishuffle/sync.py tests/test_sync.py
git commit -m "feat: mirror sync engine (wipe, copy, write iTunesSD)"
```

---

## Task 9: CLI entry point

**Files:**
- Create: `src/spotishuffle/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from pathlib import Path
from spotishuffle import cli


def test_main_happy_path(monkeypatch, tmp_path, capsys):
    events = []

    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])
    fake_files = [tmp_path / "a.mp3"]

    def fake_download(url, dest):
        events.append(("download", url))
        return fake_files
    monkeypatch.setattr(cli.downloader, "download_playlist", fake_download)

    class FakeDevice:
        root = tmp_path
    monkeypatch.setattr(cli.device, "select_shuffle", lambda: FakeDevice())

    def fake_sync(dev, files):
        events.append(("sync", len(files)))
        return len(files)
    monkeypatch.setattr(cli.sync, "mirror_sync", fake_sync)

    rc = cli.main(["https://open.spotify.com/playlist/abc"])
    assert rc == 0
    assert ("download", "https://open.spotify.com/playlist/abc") in events
    assert ("sync", 1) in events


def test_main_missing_deps_errors(monkeypatch):
    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: ["spotdl"])
    rc = cli.main(["https://open.spotify.com/playlist/abc"])
    assert rc == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py -q`
Expected: FAIL — cannot import `cli`.

- [ ] **Step 3: Implement**

```python
# src/spotishuffle/cli.py
"""spotishuffle CLI: download a Spotify playlist and mirror it to a shuffle."""
import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import device, downloader, sync

CACHE_DIR = Path.home() / ".spotishuffle" / "cache"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spotishuffle",
        description="Download a Spotify playlist and mirror it onto a 2nd-gen iPod shuffle.",
    )
    parser.add_argument("playlist_url", help="Spotify playlist URL")
    args = parser.parse_args(argv)

    missing = downloader.check_dependencies()
    if missing:
        print("Missing required tools: " + ", ".join(missing), file=sys.stderr)
        print("Install with: pip install spotdl  and  brew install ffmpeg", file=sys.stderr)
        return 1

    playlist_id = args.playlist_url.rstrip("/").split("/")[-1].split("?")[0]
    dest = CACHE_DIR / playlist_id

    print(f"Downloading playlist into {dest} ...")
    files = downloader.download_playlist(args.playlist_url, dest)
    if not files:
        print("No tracks were downloaded.", file=sys.stderr)
        return 1

    try:
        dev = device.select_shuffle()
    except device.NoDeviceError as e:
        print(str(e), file=sys.stderr)
        return 1

    print(f"Syncing {len(files)} track(s) to {dev.root} ...")
    synced = sync.mirror_sync(dev, files)
    print(f"Done. {synced} track(s) on the shuffle. Eject before unplugging.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_cli.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/spotishuffle/cli.py tests/test_cli.py
git commit -m "feat: spotishuffle one-command CLI"
```

---

## Task 10: Install, README, and full-suite check

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m pytest -q`
Expected: PASS (all tests across the 5 modules).

- [ ] **Step 2: Editable install and smoke-test the console script**

Run:
```bash
python3 -m pip install -e .
spotishuffle --help
```
Expected: argparse help text for `spotishuffle` prints; exit 0.

- [ ] **Step 3: Write `README.md`**

````markdown
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
````

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add README"
```

---

## Task 11: On-device verification (manual)

This is the empirical end-to-end check the unit tests can't do.

- [ ] **Step 1:** Plug in the shuffle; confirm it mounts under `/Volumes`.
- [ ] **Step 2:** Run `spotishuffle "<a small public playlist URL>"`.
- [ ] **Step 3:** Confirm `iPod_Control/Music/F00/` contains `T0001.mp3`… and `iPod_Control/iTunes/iTunesSD` has size `18 + N*558`.
- [ ] **Step 4:** Eject, unplug, and confirm the shuffle plays the tracks in order.
- [ ] **Step 5:** If playback fails, capture the generated `iTunesSD`, diff structural bytes against the golden fixture, and open a fix task. (Most likely culprit: filetype byte or a flag — adjust `build_entry` and re-run Task 4 tests.)

---

## Notes for the implementer
- DRY/YAGNI/TDD throughout; commit after each green test.
- `itunessd.py` is pure/standard-library and fully unit-tested — treat the golden fixture as the source of truth for structural bytes.
- Never write to a real device in automated tests; always use a `tmp_path` fake that contains `iPod_Control/`.
