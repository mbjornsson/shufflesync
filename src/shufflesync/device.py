"""Locate and classify a mounted iPod on macOS."""
import plistlib
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, List, Optional


class NoDeviceError(Exception):
    pass


class UnsupportedDeviceError(Exception):
    pass


class DeviceFamily(Enum):
    SHUFFLE_2G = "shuffle_2g"
    NANO_1G_3G = "nano_1g_3g"


@dataclass(frozen=True)
class IpodDevice:
    root: Path
    family: DeviceFamily

    @property
    def music_dir(self) -> Path:
        return self.root / "iPod_Control" / "Music"

    @property
    def db_path(self) -> Path:
        name = "iTunesSD" if self.family == DeviceFamily.SHUFFLE_2G else "iTunesDB"
        return self.root / "iPod_Control" / "iTunes" / name


def _itunes_dir(root: Path) -> Path:
    return root / "iPod_Control" / "iTunes"


def detect_family(root: Path) -> Optional[DeviceFamily]:
    """Classify a mounted iPod by its on-disk database.

    iTunesSD -> shuffle 2G. A valid iTunesDB (mhbd magic) -> nano 1-3G. Anything
    else -> None (unsupported). NOTE: this does not distinguish a nano 1-3G from
    a checksummed iTunesDB device (nano 4G+, classic, touch); writing our
    unsigned DB to those yields an empty library. This limitation is documented.
    """
    itunes = _itunes_dir(root)
    if (itunes / "iTunesSD").exists():
        return DeviceFamily.SHUFFLE_2G
    db = itunes / "iTunesDB"
    if db.exists() and db.read_bytes()[:4] == b"mhbd":
        return DeviceFamily.NANO_1G_3G
    return None


def find_ipods(volumes_dir: Path = Path("/Volumes")) -> List[Path]:
    """Return mounts that contain an iPod_Control directory."""
    if not volumes_dir.exists():
        return []
    return sorted(
        p for p in volumes_dir.iterdir() if (p / "iPod_Control").is_dir()
    )


def mount_external_disks() -> None:
    """Best-effort mount of unmounted external disks via `diskutil`."""
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


def select_ipod(
    volumes_dir: Path = Path("/Volumes"),
    chooser: Optional[Callable[[List[Path]], Path]] = None,
    mounter: Optional[Callable[[], None]] = None,
) -> IpodDevice:
    """Find one iPod and classify it, mounting unmounted disks if needed."""
    if mounter is None:
        mounter = mount_external_disks
    candidates = find_ipods(volumes_dir)
    if not candidates:
        mounter()
        candidates = find_ipods(volumes_dir)
    if not candidates:
        raise NoDeviceError(
            "No iPod found. Plug it in and make sure it is mounted (it should "
            "appear under /Volumes and contain an iPod_Control folder).\n"
            "If iTunes/Finder manages it, enable disk use. For an old nano that "
            "modern macOS won't manage, put it in disk mode on the device: hold "
            "the Hold switch on then off, reset with Menu+Select, then hold "
            "Select+Play to enter disk mode."
        )
    root = candidates[0] if len(candidates) == 1 else (chooser or _interactive_chooser)(candidates)
    family = detect_family(root)
    if family is None:
        raise UnsupportedDeviceError(
            f"The iPod at {root} is not supported. shufflesync supports the "
            "2nd-gen shuffle and the 1st-3rd gen nano (devices without a "
            "database signature)."
        )
    return IpodDevice(root, family)


def _interactive_chooser(options: List[Path]) -> Path:
    print("Multiple iPod devices found:")
    for i, opt in enumerate(options):
        print(f"  [{i}] {opt.name}")
    while True:
        choice = input("Choose device number: ").strip()
        if choice.isdigit() and 0 <= int(choice) < len(options):
            return options[int(choice)]
        print("Invalid choice.")
