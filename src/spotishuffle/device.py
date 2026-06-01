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
