from pathlib import Path
from shufflesync import sync, itunessd, itunesdb, itunesdb_reader, manifest, device
from shufflesync.device import IpodDevice, DeviceFamily
from mutagen.id3 import ID3, TIT2, TPE1, TALB
from mutagen.mp3 import MP3


def _make_mp3(path):
    frame = bytes.fromhex("fffb9064") + b"\x00" * 413  # one MPEG1 L3 128k/44.1k frame
    path.write_bytes(frame * 40)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=path.stem))
    tags.add(TPE1(encoding=3, text="Artist"))
    tags.add(TALB(encoding=3, text="Album"))
    tags.save(path)


def _device(tmp_path):
    root = tmp_path / "SHUFFLE"
    (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    (root / "iPod_Control" / "Music" / "OLD").mkdir(parents=True)
    (root / "iPod_Control" / "Music" / "OLD" / "stale.mp3").write_bytes(b"old")
    return IpodDevice(root, DeviceFamily.SHUFFLE_2G)


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
    data = dev.db_path.read_bytes()
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
    assert dev.db_path.read_bytes()[:3] == b"\x00\x00\x01"


def test_mirror_sync_nano_writes_itunesdb(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    a, b = src_dir / "01 A.mp3", src_dir / "02 B.mp3"
    _make_mp3(a); _make_mp3(b)

    root = tmp_path / "NANO"
    (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    dev = device.IpodDevice(root, device.DeviceFamily.NANO_1G_3G)

    count = sync.mirror_sync(dev, [a, b], playlist_name="My List")
    assert count == 2

    db = dev.db_path.read_bytes()
    assert db[0:4] == b"mhbd"
    assert "My List".encode("utf-16-le") in db
    assert (dev.music_dir / "F00" / "T0001.mp3").exists()


def _nano_with_library(tmp_path):
    """A nano whose DB already has one user track (id 1) and a user playlist."""
    root = tmp_path / "NANO"
    itunes = root / "iPod_Control" / "iTunes"
    itunes.mkdir(parents=True)
    music = root / "iPod_Control" / "Music" / "F00"
    music.mkdir(parents=True)
    (music / "USER.mp3").write_bytes(b"user-song")
    user = itunesdb.TrackEntry(
        track_id=1, title="User Song", artist="U", album="UA", genre="Rock",
        location=":iPod_Control:Music:F00:USER.mp3", size=9, duration_ms=1000,
        bitrate=192, sample_rate=44100, track_number=1, year=2000)
    blob = itunesdb._mhbd(2, itunesdb.track_dataset([user]) +
                          itunesdb.playlist_dataset_from_records([
                              itunesdb.master_playlist([1], "iPod"),
                              itunesdb.named_playlist("Faves", [1])]))
    (itunes / "iTunesDB").write_bytes(blob)
    return device.IpodDevice(root, device.DeviceFamily.NANO_1G_3G)


def test_add_sync_preserves_library_and_adds_playlist(tmp_path):
    dev = _nano_with_library(tmp_path)
    src = tmp_path / "src"; src.mkdir()
    a = src / "01 New.mp3"; _make_mp3(a)

    before = itunesdb_reader.parse(dev.db_path.read_bytes())
    user_raw_before = [t.raw for t in before.tracks if t.track_id == 1][0]

    sync.add_sync(dev, [a], playlist_name="Evening")

    db = itunesdb_reader.parse(dev.db_path.read_bytes())
    ids = {t.track_id for t in db.tracks}
    assert 1 in ids
    assert len(db.tracks) == 2
    names = {p.name for p in db.playlists}
    assert {"Faves", "Evening"}.issubset(names)
    master = [p for p in db.playlists if p.is_master][0]
    assert set(master.track_ids) == ids
    user_raw_after = [t.raw for t in db.tracks if t.track_id == 1][0]
    assert user_raw_after == user_raw_before
    assert (dev.music_dir / "F00" / "USER.mp3").exists()


def test_add_sync_is_idempotent_per_playlist(tmp_path):
    dev = _nano_with_library(tmp_path)
    src = tmp_path / "src"; src.mkdir()
    a = src / "01 New.mp3"; _make_mp3(a)
    sync.add_sync(dev, [a], playlist_name="Evening")
    first = itunesdb_reader.parse(dev.db_path.read_bytes())
    sync.add_sync(dev, [a], playlist_name="Evening")
    second = itunesdb_reader.parse(dev.db_path.read_bytes())
    assert len(second.tracks) == len(first.tracks)
    assert [p.name for p in second.playlists].count("Evening") == 1


def test_add_sync_second_playlist_coexists(tmp_path):
    dev = _nano_with_library(tmp_path)
    src = tmp_path / "src"; src.mkdir()
    a = src / "01 A.mp3"; _make_mp3(a)
    b = src / "02 B.mp3"; _make_mp3(b)
    sync.add_sync(dev, [a], playlist_name="Evening")
    sync.add_sync(dev, [b], playlist_name="Workout")
    db = itunesdb_reader.parse(dev.db_path.read_bytes())
    names = {p.name for p in db.playlists}
    assert {"Faves", "Evening", "Workout"}.issubset(names)
    assert len(db.tracks) == 3  # user + 2 added


def test_add_sync_writes_backup(tmp_path):
    dev = _nano_with_library(tmp_path)
    src = tmp_path / "src"; src.mkdir()
    a = src / "01 New.mp3"; _make_mp3(a)
    sync.add_sync(dev, [a], playlist_name="Evening")
    backups = list((dev.db_path.parent / "shufflesync-backup").glob("*/iTunesDB"))
    assert backups


def test_add_sync_rejects_shuffle(tmp_path):
    root = tmp_path / "SH"; (root / "iPod_Control" / "iTunes").mkdir(parents=True)
    dev = device.IpodDevice(root, device.DeviceFamily.SHUFFLE_2G)
    import pytest
    with pytest.raises(ValueError):
        sync.add_sync(dev, [], playlist_name="X")
