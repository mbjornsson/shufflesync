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
