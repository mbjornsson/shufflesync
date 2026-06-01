from pathlib import Path
from spotishuffle import itunessd

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
