"""shufflesync CLI: download a Spotify playlist and mirror it to a shuffle."""
import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import device, downloader, sync

CACHE_DIR = Path.home() / ".shufflesync" / "cache"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shufflesync",
        description="Download a Spotify playlist and mirror it onto a 2nd-gen iPod shuffle.",
    )
    parser.add_argument("playlist_url", help="Spotify playlist URL")
    args = parser.parse_args(argv)

    missing = downloader.check_dependencies()
    if missing:
        print("Missing required tools: " + ", ".join(missing), file=sys.stderr)
        print("Run `uv sync` to install spotdl, and `brew install ffmpeg`.", file=sys.stderr)
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
