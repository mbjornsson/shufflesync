import glob
import struct
from pathlib import Path

import pytest
from shufflesync import itunesdb, itunesdb_reader

_REAL_DBS = sorted(glob.glob("device-backup-nano-*/iTunes/iTunesDB"))


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


def test_parse_skips_unknown_datasets():
    """The reader walks by length fields, so it must step over dataset types it
    doesn't care about (the real device has album/podcast/etc. datasets)."""
    base = itunesdb.build_itunesdb([_entry(5)], "Mix")
    body = b"\x00" * 8
    ds = bytearray(96)
    ds[0:4] = b"mhsd"
    struct.pack_into("<I", ds, 4, 96)
    struct.pack_into("<I", ds, 8, 96 + len(body))
    struct.pack_into("<I", ds, 12, 4)            # type 4 (album list) — ignored
    extra = bytes(ds) + body
    hdrlen = struct.unpack_from("<I", base, 4)[0]
    injected = bytearray(base)
    struct.pack_into("<I", injected, 0x14, 3)    # dataset count 2 -> 3
    struct.pack_into("<I", injected, 8, len(base) + len(extra))  # total_len
    injected[hdrlen:hdrlen] = extra              # insert right after mhbd header
    db = itunesdb_reader.parse(bytes(injected))
    assert [t.track_id for t in db.tracks] == [5]
    assert any(p.name == "Mix" for p in db.playlists)


@pytest.mark.skipif(not _REAL_DBS, reason="no real-device iTunesDB backup present")
def test_parse_real_device_db():
    """Parse an actual nano iTunesDB (multi-dataset, 624-byte mhits): recover
    tracks + master, confirm the mhip track-id offset on real hardware, and
    that verbatim records round-trip."""
    db = itunesdb_reader.parse(Path(_REAL_DBS[0]).read_bytes())
    ids = {t.track_id for t in db.tracks}
    assert len(ids) > 0
    master = [p for p in db.playlists if p.is_master]
    assert master, "real DB should have a master playlist"
    # every master/playlist entry references a real track -> mhip offset correct
    assert set(master[0].track_ids).issubset(ids)
    # verbatim records reassemble and re-parse identically
    reassembled = itunesdb._mhbd(
        2,
        itunesdb.track_dataset_from_records([t.raw for t in db.tracks])
        + itunesdb.playlist_dataset_from_records(
            [itunesdb.master_playlist(sorted(ids))]
            + [p.raw for p in db.playlists if not p.is_master]),
    )
    db2 = itunesdb_reader.parse(reassembled)
    assert [t.raw for t in db2.tracks] == [t.raw for t in db.tracks]
