from pathlib import Path
from spotishuffle import itunessd

GOLDEN = Path(__file__).parent / "fixtures/golden_device/iTunes/iTunesSD"

def test_build_header_matches_golden():
    golden = GOLDEN.read_bytes()
    assert itunessd.build_header(11) == golden[:18]

def test_build_header_count_is_big_endian():
    assert itunessd.build_header(1)[:3] == b"\x00\x00\x01"
    assert itunessd.build_header(258)[:3] == b"\x00\x01\x02"
