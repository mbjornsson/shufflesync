import pytest
from shufflesync import device


def _shuffle(tmp_path):
    root = tmp_path / "SHUFFLE"
    itunes = root / "iPod_Control" / "iTunes"
    itunes.mkdir(parents=True)
    (root / "iPod_Control" / "Music").mkdir(parents=True)
    (itunes / "iTunesSD").write_bytes(b"\x00" * 18)
    return root


def _nano(tmp_path):
    root = tmp_path / "NANO"
    itunes = root / "iPod_Control" / "iTunes"
    itunes.mkdir(parents=True)
    (root / "iPod_Control" / "Music").mkdir(parents=True)
    mhbd = bytearray(244)
    mhbd[0:4] = b"mhbd"
    (itunes / "iTunesDB").write_bytes(bytes(mhbd))
    return root


# --- detect_family ---

def test_detect_family_shuffle(tmp_path):
    assert device.detect_family(_shuffle(tmp_path)) == device.DeviceFamily.SHUFFLE_2G


def test_detect_family_nano(tmp_path):
    assert device.detect_family(_nano(tmp_path)) == device.DeviceFamily.NANO_1G_3G


def test_detect_family_unknown_when_no_database(tmp_path):
    root = tmp_path / "BARE"
    (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    assert device.detect_family(root) is None


def test_detect_family_unknown_when_db_not_mhbd(tmp_path):
    root = tmp_path / "WEIRD"
    itunes = root / "iPod_Control" / "iTunes"
    itunes.mkdir(parents=True)
    (itunes / "iTunesDB").write_bytes(b"junk" + b"\x00" * 240)
    assert device.detect_family(root) is None


# --- find_ipods ---

def test_find_ipods_detects_ipod(tmp_path):
    root = _shuffle(tmp_path)
    (tmp_path / "NotAnIpod").mkdir()
    found = device.find_ipods(volumes_dir=tmp_path)
    assert found == [root]


# --- select_ipod ---

def test_select_ipod_zero_raises(tmp_path):
    with pytest.raises(device.NoDeviceError):
        device.select_ipod(volumes_dir=tmp_path, mounter=lambda: None)


def test_select_ipod_mounts_then_finds(tmp_path):
    root = tmp_path / "NANO"

    def fake_mount():
        _nano(tmp_path)  # appears only after mounting

    dev = device.select_ipod(volumes_dir=tmp_path, mounter=fake_mount)
    assert dev.root == root


def test_select_ipod_one_returns_device(tmp_path):
    root = _shuffle(tmp_path)
    dev = device.select_ipod(volumes_dir=tmp_path)
    assert dev.root == root
    assert dev.music_dir == root / "iPod_Control" / "Music"
    assert dev.db_path == root / "iPod_Control" / "iTunes" / "iTunesSD"


def test_select_ipod_many_uses_chooser(tmp_path):
    _shuffle(tmp_path)
    b = _nano(tmp_path)
    # find_ipods sorts paths; NANO < SHUFFLE lexicographically, so opts[0] is NANO
    dev = device.select_ipod(volumes_dir=tmp_path, chooser=lambda opts: opts[0])
    assert dev.root == b


def test_select_ipod_returns_device_with_family(tmp_path):
    root = _nano(tmp_path)
    dev = device.select_ipod(volumes_dir=tmp_path)
    assert dev.root == root
    assert dev.family == device.DeviceFamily.NANO_1G_3G
    assert dev.db_path == root / "iPod_Control" / "iTunes" / "iTunesDB"


def test_select_ipod_unsupported_raises(tmp_path):
    (tmp_path / "X" / "iPod_Control" / "iTunes").mkdir(parents=True)
    with pytest.raises(device.UnsupportedDeviceError):
        device.select_ipod(volumes_dir=tmp_path)


# --- mount_external_disks ---

def test_mount_external_disks_mounts_every_identifier(monkeypatch):
    """Parse `diskutil list -plist` output and issue a mount for each whole disk
    and partition identifier."""
    import plistlib

    sample = {
        "AllDisksAndPartitions": [
            {"DeviceIdentifier": "disk4",
             "Partitions": [{"DeviceIdentifier": "disk4s1"}]},
            {"DeviceIdentifier": "disk5", "Partitions": []},
        ]
    }
    mounted = []

    def fake_run(cmd, capture_output, check=False):
        if "list" in cmd:
            class R: stdout = plistlib.dumps(sample)
            return R()
        if "mount" in cmd:
            mounted.append(cmd[-1])
            class R: pass
            return R()
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(device.subprocess, "run", fake_run)
    device.mount_external_disks()
    assert mounted == ["disk4", "disk4s1", "disk5"]
