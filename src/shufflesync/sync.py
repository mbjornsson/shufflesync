"""Mirror a list of audio files onto an iPod: wipe, copy, write the database."""
import datetime
import shutil
from pathlib import Path
from typing import List

from . import itunessd, itunesdb, itunesdb_reader, manifest, metadata
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


def _existing_names(music: Path) -> set:
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
    """Add source_files as a named playlist WITHOUT erasing existing music.
    Idempotent per playlist: a previous run of the same name is pruned first."""
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

    # 5. Copy new files (collision-safe) into F90.
    music.mkdir(parents=True, exist_ok=True)
    taken = _existing_names(music)
    folder = music / "F90"
    folder.mkdir(exist_ok=True)
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

    # 6. Reassemble: type 1 (kept verbatim + new) + type 2 (rebuilt master +
    #    user/other-managed non-master verbatim + new managed playlist).
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
