"""Download a Spotify playlist as MP3s using the external `spotdl` tool."""
import json
import random
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

REQUIRED = ("spotdl", "ffmpeg")


def select_tracks(tracks: List[dict], count: int, randomize: bool) -> List[dict]:
    """Pick `count` tracks: first N in order, or a random sample (kept in order).

    If `count` is at least the number of tracks, all are returned unchanged.
    """
    if count >= len(tracks):
        return tracks
    if randomize:
        indexes = sorted(random.sample(range(len(tracks)), count))
        return [tracks[i] for i in indexes]
    return tracks[:count]


def check_dependencies() -> List[str]:
    """Return the names of required external tools that are not on PATH."""
    return [name for name in REQUIRED if shutil.which(name) is None]


def _output_args(dest: Path) -> List[str]:
    # Keep this template RELATIVE. spotdl sanitizes the --output path and strips
    # leading dots from every path component (formatter.create_path_object), so an
    # absolute template under a hidden dir like ~/.shufflesync gets rewritten to
    # ~/shufflesync and files download to the wrong place. We run spotdl with
    # cwd=dest, so a relative template resolves into dest untouched.
    return [
        "--output",
        "{list-position} - {title}.{output-ext}",
        "--format",
        "mp3",
    ]


def download_playlist(
    playlist_url: str,
    dest: Path,
    count: Optional[int] = None,
    randomize: bool = False,
) -> List[Path]:
    """Download `playlist_url` into `dest`; return MP3 paths sorted by name.

    With `count` set, only that many tracks are downloaded: the playlist
    metadata is fetched first, `count` tracks are selected (first N, or a random
    sample when `randomize` is true), and only those are downloaded.

    `dest` is emptied first so the returned files are exactly this run's
    download — otherwise MP3s from a previous (e.g. larger) run would leak in.
    """
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    if count is None:
        query = playlist_url
    else:
        all_tracks = fetch_track_list(playlist_url, dest)
        selected = select_tracks(all_tracks, count, randomize)
        trimmed = dest / "selection.spotdl"
        trimmed.write_text(json.dumps(selected))
        query = str(trimmed)

    # `--` ends option parsing so a leading-dash query can't be read as a flag.
    cmd = ["spotdl", "download", *_output_args(dest), "--", query]
    subprocess.run(cmd, cwd=dest, check=True)
    return sorted(dest.glob("*.mp3"))


def fetch_track_list(playlist_url: str, dest: Path) -> List[dict]:
    """Run `spotdl save` to fetch playlist metadata without downloading audio."""
    save_file = dest / "playlist.spotdl"
    cmd = ["spotdl", "save", "--save-file", str(save_file), "--", playlist_url]
    subprocess.run(cmd, cwd=dest, check=True)
    return json.loads(save_file.read_text())
