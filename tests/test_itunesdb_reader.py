import struct
from shufflesync import itunesdb, itunesdb_reader


def _entry(i):
    return itunesdb.TrackEntry(
        track_id=i, title=f"T{i}", artist="A", album="Al", genre="G",
        location=f":iPod_Control:Music:F00:T{i:04d}.mp3",
        size=1000, duration_ms=2000, bitrate=192, sample_rate=44100,
        track_number=i, year=2009,
    )


def test_parse_recovers_tracks_and_playlist():
    blob = itunesdb.build_itunesdb([_entry(7), _entry(9)], "My Mix")
    db = itunesdb_reader.parse(blob)
    assert [t.track_id for t in db.tracks] == [7, 9]
    assert db.max_track_id() == 9
    names = {p.name: p for p in db.playlists}
    assert "My Mix" in names
    assert names["My Mix"].track_ids == [7, 9]
    assert names["My Mix"].is_master is False
    master = [p for p in db.playlists if p.is_master]
    assert len(master) == 1
    assert master[0].track_ids == [7, 9]


def test_raw_track_bytes_are_verbatim_slices():
    blob = itunesdb.build_itunesdb([_entry(1)], "X")
    db = itunesdb_reader.parse(blob)
    assert db.tracks[0].raw[0:4] == b"mhit"
    assert db.tracks[0].raw in blob
