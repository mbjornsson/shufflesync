import struct
from pathlib import Path
from shufflesync import itunesdb

GOLDEN = Path(__file__).parent / "fixtures" / "golden_nano" / "iTunesDB"


def _entries():
    return [
        itunesdb.TrackEntry(
            track_id=i, title=f"Test Track {i}", artist="Test Artist",
            album="Test Album", genre="Test",
            location=f":iPod_Control:Music:F00:T{i:04d}.mp3",
            size=1000 * i, duration_ms=2000 * i, bitrate=192, sample_rate=44100,
            track_number=i, year=2009,
        ) for i in (1, 2, 3)
    ]


def test_synthetic_golden_is_reproducible():
    assert itunesdb.build_itunesdb(_entries(), "Test Playlist") == GOLDEN.read_bytes()


def test_golden_has_two_datasets_and_playlist_name():
    db = GOLDEN.read_bytes()
    assert db[0:4] == b"mhbd"
    assert struct.unpack_from("<I", db, 0x14)[0] == 2
    assert "Test Playlist".encode("utf-16-le") in db
