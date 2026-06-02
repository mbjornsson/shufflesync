"""Mirror a list of audio files onto a shuffle: wipe, copy, write iTunesSD."""
import shutil
from pathlib import Path
from typing import List

from . import itunessd
from .device import IpodDevice

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


def mirror_sync(device: IpodDevice, source_files: List[Path]) -> int:
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

    device.db_path.parent.mkdir(parents=True, exist_ok=True)
    device.db_path.write_bytes(itunessd.build_itunessd(tracks))

    if skipped:
        print(f"Skipped {skipped} track(s): not enough space on device.")
    return len(tracks)
