"""shufflesync CLI: download a Spotify playlist and mirror it to a shuffle."""
import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from . import device, downloader, sync

CACHE_DIR = Path.home() / ".shufflesync" / "cache"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="shufflesync",
        description="Download a Spotify playlist and mirror it onto an iPod (2nd-gen shuffle or 1st-3rd gen nano).",
        epilog=(
            'Quote the URL — it usually contains "?si=..." and the shell will '
            "otherwise mangle it:\n"
            '  shufflesync "https://open.spotify.com/playlist/<id>?si=..."'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "playlist_url",
        help='Spotify playlist URL (quote it, e.g. "https://open.spotify.com/playlist/<id>")',
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=None,
        help="Download at most this many tracks (default: the whole playlist).",
    )
    parser.add_argument(
        "--random",
        dest="randomize",
        action="store_true",
        help="With --count, pick the tracks at random instead of the first N.",
    )
    parser.add_argument(
        "--add", action="store_true",
        help="Add this playlist to the iPod nano, keeping existing music "
             "(this is the default for the nano).",
    )
    parser.add_argument(
        "--wipe", action="store_true",
        help="Erase ALL music and playlists on the iPod nano and replace them "
             "with just this playlist. (The shuffle is always fully replaced.)",
    )
    args = parser.parse_args(argv)

    if args.count is not None and args.count <= 0:
        print("--count must be a positive number.", file=sys.stderr)
        return 1

    if args.add and args.wipe:
        print("Use either --add or --wipe, not both.", file=sys.stderr)
        return 1

    missing = downloader.check_dependencies()
    if missing:
        print("Missing required tools: " + ", ".join(missing), file=sys.stderr)
        print("Run `uv sync` to install spotdl, and `brew install ffmpeg`.", file=sys.stderr)
        return 1

    playlist_id = args.playlist_url.rstrip("/").split("/")[-1].split("?")[0]
    # Used as a cache path component, so reject anything that isn't a plain id.
    if not re.fullmatch(r"[A-Za-z0-9]+", playlist_id):
        print(
            'That does not look like a Spotify playlist URL. Expected something '
            'like "https://open.spotify.com/playlist/<id>".',
            file=sys.stderr,
        )
        return 1
    dest = CACHE_DIR / playlist_id

    print(f"Downloading playlist into {dest} ...")
    try:
        result = downloader.download_playlist(
            args.playlist_url, dest, count=args.count, randomize=args.randomize
        )
    except FileNotFoundError as e:
        print(f"Could not run spotdl: {e}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError:
        print(
            "Download failed. Check the playlist URL and your internet connection.",
            file=sys.stderr,
        )
        return 1
    files = result.files
    if not files:
        print("No tracks were downloaded.", file=sys.stderr)
        return 1

    try:
        dev = device.select_ipod()
    except (device.NoDeviceError, device.UnsupportedDeviceError) as e:
        print(str(e), file=sys.stderr)
        return 1

    playlist_name = result.playlist_name or playlist_id
    is_shuffle = dev.family == device.DeviceFamily.SHUFFLE_2G
    if args.add and is_shuffle:
        print("--add is only for the iPod nano; the shuffle is always replaced.",
              file=sys.stderr)
        return 1

    # The nano keeps existing music by default; only --wipe replaces everything.
    # The shuffle has no library, so it is always a full replace.
    wipe = is_shuffle or args.wipe
    if wipe and not is_shuffle:
        tracks, playlists = sync.existing_content(dev)
        if tracks and sys.stdin.isatty():
            answer = input(
                f"--wipe will erase all {tracks} track(s) and {playlists} "
                "playlist(s) on the iPod. Continue? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                print("Aborted.", file=sys.stderr)
                return 1

    if wipe:
        print(f"Replacing everything on {dev.root} with {len(files)} track(s) ...")
        synced = sync.mirror_sync(dev, files, playlist_name=playlist_name)
    else:
        print(f'Adding "{playlist_name}" to {dev.root} '
              f"({len(files)} track(s); existing music kept) ...")
        synced = sync.add_sync(dev, files, playlist_name=playlist_name)
    print(f"Done. {synced} track(s) on the iPod. Eject before unplugging.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
