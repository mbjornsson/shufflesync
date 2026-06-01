from pathlib import Path
from shufflesync import itunessd

GOLDEN = Path(__file__).parent / "fixtures/golden_device/iTunes/iTunesSD"

def test_build_header_matches_golden():
    golden = GOLDEN.read_bytes()
    assert itunessd.build_header(11) == golden[:18]

def test_build_header_count_is_big_endian():
    assert itunessd.build_header(1)[:3] == b"\x00\x00\x01"
    assert itunessd.build_header(258)[:3] == b"\x00\x01\x02"

def _golden_entry(i):
    golden = GOLDEN.read_bytes()
    start = 18 + i * 558
    return golden[start:start + 558]

def test_encode_path_matches_golden_field():
    entry0 = _golden_entry(0)
    field = entry0[32:32 + 522]
    assert itunessd.encode_path("/iPod_Control/Music/F00/YZUB.m4a") == field

def test_encode_path_is_522_bytes_utf16be_nul_padded():
    field = itunessd.encode_path("/x.mp3")
    assert len(field) == 522
    assert field[:12] == "/x.mp3".encode("utf-16-be")
    assert field[12:] == b"\x00" * (522 - 12)

def test_encode_path_rejects_overlong():
    import pytest
    with pytest.raises(ValueError):
        itunessd.encode_path("/" + "a" * 261)

def test_build_entry_structural_bytes_match_golden():
    entry0 = _golden_entry(0)
    ours = itunessd.build_entry("/iPod_Control/Music/F00/YZUB.m4a", filetype="aac")
    assert len(ours) == 558
    assert ours[0:3] == entry0[0:3]
    assert ours[29] == entry0[29]
    assert ours[31] == entry0[31]
    assert ours[32:554] == entry0[32:554]
    assert ours[554:558] == entry0[554:558]

def test_build_entry_filetype_mp3():
    ours = itunessd.build_entry("/iPod_Control/Music/F00/T0001.mp3", filetype="mp3")
    assert ours[29] == 0x01
    assert ours[31] == 0x01

def test_build_entry_analysis_bytes_zeroed():
    ours = itunessd.build_entry("/x.mp3", filetype="mp3")
    assert ours[3:29] == b"\x00" * 26

def test_build_itunessd_size_and_count():
    tracks = [("/iPod_Control/Music/F00/T%04d.mp3" % i, "mp3") for i in range(5)]
    data = itunessd.build_itunessd(tracks)
    assert len(data) == 18 + 5 * 558
    assert data[:3] == b"\x00\x00\x05"

def test_build_itunessd_empty():
    data = itunessd.build_itunessd([])
    assert data == itunessd.build_header(0)
    assert len(data) == 18

def test_build_itunessd_concatenates_entries_in_order():
    tracks = [("/a.mp3", "mp3"), ("/b.aac", "aac")]
    data = itunessd.build_itunessd(tracks)
    assert data[18:18 + 558] == itunessd.build_entry("/a.mp3", "mp3")
    assert data[18 + 558:18 + 2 * 558] == itunessd.build_entry("/b.aac", "aac")
