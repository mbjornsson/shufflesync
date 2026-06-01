import pytest
from shufflesync import device


def _make_ipod(tmp_path, name):
    root = tmp_path / name
    (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    (root / "iPod_Control" / "Music").mkdir(parents=True)
    return root


def test_find_shuffles_detects_ipod(tmp_path):
    root = _make_ipod(tmp_path, "SHUFFLE")
    (tmp_path / "NotAnIpod").mkdir()
    found = device.find_shuffles(volumes_dir=tmp_path)
    assert found == [root]


def test_select_shuffle_zero_raises(tmp_path):
    with pytest.raises(device.NoDeviceError):
        device.select_shuffle(volumes_dir=tmp_path, mounter=lambda: None)


def test_select_shuffle_mounts_then_finds(tmp_path):
    root = tmp_path / "SHUFFLE"

    def fake_mount():
        _make_ipod(tmp_path, "SHUFFLE")  # appears only after mounting

    dev = device.select_shuffle(volumes_dir=tmp_path, mounter=fake_mount)
    assert dev.root == root


def test_select_shuffle_one_returns_device(tmp_path):
    root = _make_ipod(tmp_path, "SHUFFLE")
    dev = device.select_shuffle(volumes_dir=tmp_path)
    assert dev.root == root
    assert dev.music_dir == root / "iPod_Control" / "Music"
    assert dev.itunessd_path == root / "iPod_Control" / "iTunes" / "iTunesSD"


def test_select_shuffle_many_uses_chooser(tmp_path):
    a = _make_ipod(tmp_path, "A")
    b = _make_ipod(tmp_path, "B")
    dev = device.select_shuffle(volumes_dir=tmp_path, chooser=lambda opts: opts[1])
    assert dev.root == b
