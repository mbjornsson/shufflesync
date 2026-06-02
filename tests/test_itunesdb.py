import struct
from shufflesync import itunesdb


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def test_string_mhod_layout():
    m = itunesdb.string_mhod(1, "Hi")  # type 1 = title
    assert m[0:4] == b"mhod"
    assert _u32(m, 4) == 24                      # header_len
    assert _u32(m, 8) == len(m)                  # total_len
    assert _u32(m, 8) == 40 + len("Hi".encode("utf-16-le"))
    assert _u32(m, 12) == 1                       # type
    assert _u32(m, 0x18) == 1                     # position
    assert _u32(m, 0x1c) == 4                     # byte length (2 chars utf-16)
    assert m[40:].decode("utf-16-le") == "Hi"


def test_location_mhod_uses_colon_path():
    m = itunesdb.string_mhod(2, ":iPod_Control:Music:F00:T0001.mp3")
    assert _u32(m, 12) == 2
    assert m[40:].decode("utf-16-le") == ":iPod_Control:Music:F00:T0001.mp3"


def test_track_entry_to_mhit_fields():
    entry = itunesdb.TrackEntry(
        track_id=7, title="T", artist="A", album="Al", genre="G",
        location=":iPod_Control:Music:F00:T0007.mp3",
        size=123456, duration_ms=98000, bitrate=192, sample_rate=44100,
        track_number=7, year=2009,
    )
    m = itunesdb.track_mhit(entry)
    assert m[0:4] == b"mhit"
    assert _u32(m, 4) == 0x184                 # header_len
    assert _u32(m, 8) == len(m)                # total_len
    assert _u32(m, 12) == 5                    # mhod count
    assert _u32(m, 16) == 7                    # track id
    assert _u32(m, 20) == 1                    # visible
    assert m[0x18:0x1c] == b"MP3 "[::-1]       # filetype
    assert m[0x1c] == 1 and m[0x1d] == 1       # type1, type2
    assert _u32(m, itunesdb.MHIT_OFFSETS["size"]) == 123456
    assert _u32(m, itunesdb.MHIT_OFFSETS["length_ms"]) == 98000
    assert _u32(m, 0x2c) == 7                  # track number
    assert _u32(m, 0x34) == 2009               # year
    assert m[0x184:0x184 + 4] == b"mhod"


def _entry(i):
    return itunesdb.TrackEntry(
        track_id=i, title=f"T{i}", artist="A", album="Al", genre="G",
        location=f":iPod_Control:Music:F00:T{i:04d}.mp3",
        size=1000, duration_ms=2000, bitrate=192, sample_rate=44100,
        track_number=i, year=2009,
    )


def test_track_dataset_wraps_all_mhits():
    ds = itunesdb.track_dataset([_entry(1), _entry(2)])
    assert ds[0:4] == b"mhsd"
    assert _u32(ds, 0x0c) == 1                 # dataset type 1 = tracks
    assert _u32(ds, 8) == len(ds)              # total_len
    inner = ds[96:]
    assert inner[0:4] == b"mhlt"
    assert _u32(inner, 8) == 2                  # track count
    assert inner[92:96] == b"mhit"


def test_playlist_dataset_has_master_and_named():
    ds = itunesdb.playlist_dataset("Evening Chill", [1, 2, 3])
    assert ds[0:4] == b"mhsd"
    assert _u32(ds, 0x0c) == 2                  # dataset type 2 = playlists
    inner = ds[96:]
    assert inner[0:4] == b"mhlp"
    assert _u32(inner, 8) == 2                  # two playlists (master + named)
    master = inner[92:]
    assert master[0:4] == b"mhyp"
    assert _u32(master, 0x10) == 3              # item count
    assert _u32(master, 0x14) == 1             # master flag
    assert "Evening Chill".encode("utf-16-le") in ds


def test_playlist_item_references_track_id():
    item = itunesdb.playlist_item(track_id=42, position=0)
    assert item[0:4] == b"mhip"
    assert _u32(item, 0x0c) == 1                # one child mhod
    assert _u32(item, 0x18) == 42              # track id
    assert item[76:80] == b"mhod"             # position mhod follows the 76-byte header
    assert _u32(item, 8) == len(item)          # total_len includes child mhod


def test_build_itunesdb_full_structure():
    db = itunesdb.build_itunesdb([_entry(1), _entry(2)], "Evening Chill")
    assert db[0:4] == b"mhbd"
    assert _u32(db, 4) == 244                   # mhbd header_len
    assert _u32(db, 8) == len(db)               # total_len spans whole file
    assert _u32(db, 0x14) == 2                  # two datasets
    assert db[0x46:0x48] == b"en"              # language
    first = db[244:]
    assert first[0:4] == b"mhsd" and _u32(first, 0x0c) == 1
    second = first[_u32(first, 8):]
    assert second[0:4] == b"mhsd" and _u32(second, 0x0c) == 2


def test_build_itunesdb_empty_playlist():
    db = itunesdb.build_itunesdb([], "Empty")
    assert db[0:4] == b"mhbd"
    assert _u32(db, 0x14) == 2
