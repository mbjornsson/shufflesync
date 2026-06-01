from pathlib import Path
from shufflesync import sync, itunessd
from shufflesync.device import ShuffleDevice


def _device(tmp_path):
    root = tmp_path / "SHUFFLE"
    (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    (root / "iPod_Control" / "Music" / "OLD").mkdir(parents=True)
    (root / "iPod_Control" / "Music" / "OLD" / "stale.mp3").write_bytes(b"old")
    return ShuffleDevice(root)


def _src(tmp_path, n, size=4):
    src = tmp_path / "src"
    src.mkdir()
    files = []
    for i in range(n):
        f = src / f"{i:02d} song.mp3"
        f.write_bytes(b"x" * size)
        files.append(f)
    return files


def test_mirror_wipes_old_music(tmp_path):
    dev = _device(tmp_path)
    files = _src(tmp_path, 2)
    sync.mirror_sync(dev, files)
    assert not (dev.music_dir / "OLD").exists()


def test_mirror_copies_files_with_generated_names(tmp_path):
    dev = _device(tmp_path)
    files = _src(tmp_path, 2)
    synced = sync.mirror_sync(dev, files)
    assert (dev.music_dir / "F00" / "T0001.mp3").exists()
    assert (dev.music_dir / "F00" / "T0002.mp3").exists()
    assert synced == 2


def test_mirror_writes_itunessd_matching_files(tmp_path):
    dev = _device(tmp_path)
    files = _src(tmp_path, 2)
    sync.mirror_sync(dev, files)
    data = dev.itunessd_path.read_bytes()
    assert data[:3] == b"\x00\x00\x02"
    expected = itunessd.build_itunessd([
        ("/iPod_Control/Music/F00/T0001.mp3", "mp3"),
        ("/iPod_Control/Music/F00/T0002.mp3", "mp3"),
    ])
    assert data == expected


def test_mirror_buckets_at_100_per_folder(tmp_path):
    dev = _device(tmp_path)
    files = _src(tmp_path, 101)
    sync.mirror_sync(dev, files)
    assert (dev.music_dir / "F00" / "T0100.mp3").exists()
    assert (dev.music_dir / "F01" / "T0101.mp3").exists()


def test_mirror_skips_overflow_when_capacity_exceeded(tmp_path, monkeypatch, capsys):
    dev = _device(tmp_path)
    files = _src(tmp_path, 3, size=100)
    # effective free = reported free - CAPACITY_MARGIN; set it so ~150 bytes
    # are usable -> only the first 100-byte file fits.
    free = sync.CAPACITY_MARGIN + 150
    monkeypatch.setattr(sync.shutil, "disk_usage",
                        lambda p: type("U", (), {"free": free})())
    synced = sync.mirror_sync(dev, files)
    assert synced == 1
    assert "Skipped 2" in capsys.readouterr().out
    assert dev.itunessd_path.read_bytes()[:3] == b"\x00\x00\x01"
