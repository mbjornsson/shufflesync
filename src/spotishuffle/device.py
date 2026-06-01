"""Locate a mounted 2nd-gen iPod shuffle on macOS."""
import plistlib
import subprocess
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


def mount_external_disks() -> None:
    """Best-effort: mount any unmounted external disks via `diskutil`.

    An attached iPod whose volume is not yet mounted won't appear under
    /Volumes; mounting brings it back so `find_shuffles` can see it. Errors
    (no diskutil, already-mounted, non-mountable whole disks) are ignored.
    """
    try:
        listing = subprocess.run(
            ["diskutil", "list", "-plist", "external", "physical"],
            capture_output=True, check=True,
        ).stdout
        info = plistlib.loads(listing)
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException):
        return
    for disk in info.get("AllDisksAndPartitions", []):
        idents = [disk.get("DeviceIdentifier")]
        idents += [p.get("DeviceIdentifier") for p in disk.get("Partitions", [])]
        for ident in filter(None, idents):
            subprocess.run(["diskutil", "mount", ident], capture_output=True)


def select_shuffle(
    volumes_dir: Path = Path("/Volumes"),
    chooser: Optional[Callable[[List[Path]], Path]] = None,
    mounter: Optional[Callable[[], None]] = None,
) -> ShuffleDevice:
    """Find exactly one shuffle, or use `chooser` to pick among several.

    If none is mounted, `mounter` (default: `mount_external_disks`) is invoked
    once to attach an iPod whose volume is present but unmounted.
    """
    if mounter is None:
        mounter = mount_external_disks
    candidates = find_shuffles(volumes_dir)
    if not candidates:
        mounter()
        candidates = find_shuffles(volumes_dir)
    if not candidates:
        raise NoDeviceError(
            "No iPod shuffle found. Plug it in and make sure it is mounted "
            "(it should appear under /Volumes and contain an iPod_Control folder).\n"
            "If the iPod is managed by Finder/Music, its disk stays unmounted "
            "until you enable disk use: select the iPod in Finder, turn on "
            "'Enable disk use' (or 'Manually manage music'), and click Apply."
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
