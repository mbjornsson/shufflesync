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
