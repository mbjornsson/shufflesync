"""Download a Spotify playlist as MP3s using the external `spotdl` tool."""
import json
import random
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

REQUIRED = ("spotdl", "ffmpeg")


@dataclass(frozen=True)
class DownloadResult:
    files: List[Path]        # this run's tracks, in playlist order
    playlist_name: str       # real Spotify title (never empty)


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


def _reject_option_like(value: str) -> None:
    """Guard against argument injection. spotdl does not support a `--`
    end-of-options separator (it errors on it), so we instead refuse a query
    that would be parsed as an option."""
    if value.startswith("-"):
        raise ValueError(f"refusing option-like argument for spotdl: {value!r}")


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


def _read_m3u(m3u: Path, dest: Path) -> List[Path]:
    """This run's track files from an m3u spotdl wrote, in playlist order."""
    if not m3u.exists():
        return []
    files = []
    for line in m3u.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        path = Path(line)
        if not path.is_absolute():
            path = dest / path
        if path.suffix.lower() == ".mp3" and path.exists():
            files.append(path)
    return files


def _prune_orphans(dest: Path, keep: List[Path]) -> None:
    """Delete cached top-level *.mp3 files not in `keep` (bounds the cache)."""
    keep_set = {p.resolve() for p in keep}
    for f in dest.glob("*.mp3"):
        if f.resolve() not in keep_set:
            f.unlink()


def download_playlist(
    playlist_url: str,
    dest: Path,
    count: Optional[int] = None,
    randomize: bool = False,
) -> DownloadResult:
    """Download `playlist_url` into `dest`; return this run's MP3s + the name.

    The cache dir is kept across runs: spotdl's default `skip` reuses files
    already present, so only new tracks download. This run's files are taken from
    the m3u spotdl writes (not a directory glob), so a changed selection or a
    shrunk playlist never returns stale tracks; orphaned files are pruned.
    """
    _reject_option_like(playlist_url)
    dest.mkdir(parents=True, exist_ok=True)

    all_tracks = fetch_track_list(playlist_url, dest)
    playlist_name = (all_tracks[0].get("list_name") if all_tracks else "") or dest.name
    selected = all_tracks if count is None else select_tracks(all_tracks, count, randomize)

    selection = dest / "selection.spotdl"
    selection.write_text(json.dumps(selected))
    m3u = dest / "run.m3u"
    if m3u.exists():
        m3u.unlink()

    cmd = ["spotdl", "download", str(selection), "--m3u", str(m3u), *_output_args(dest)]
    subprocess.run(cmd, cwd=dest, check=True)

    files = _read_m3u(m3u, dest)
    _prune_orphans(dest, files)
    return DownloadResult(files, playlist_name)


def fetch_track_list(playlist_url: str, dest: Path) -> List[dict]:
    """Run `spotdl save` to fetch playlist metadata without downloading audio."""
    _reject_option_like(playlist_url)
    save_file = dest / "playlist.spotdl"
    cmd = ["spotdl", "save", playlist_url, "--save-file", str(save_file)]
    subprocess.run(cmd, cwd=dest, check=True)
    return json.loads(save_file.read_text())
