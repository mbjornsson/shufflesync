from pathlib import Path
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TCON, TRCK, TDRC
from mutagen.mp3 import MP3
from shufflesync import metadata


def _make_mp3(path: Path):
    # a minimal valid silent MP3 frame so mutagen can read .info.length
    # Frame size for MPEG1 Layer3 128kbps 44100Hz: (144*128000)//44100 = 417 bytes
    # = 4-byte header + 413 bytes of payload
    frame = bytes.fromhex("fffb9064") + b"\x00" * 413
    path.write_bytes(frame * 40)  # ~1s of frames
    tags = ID3()
    tags.add(TIT2(encoding=3, text="My Title"))
    tags.add(TPE1(encoding=3, text="My Artist"))
    tags.add(TALB(encoding=3, text="My Album"))
    tags.add(TCON(encoding=3, text="My Genre"))
    tags.add(TRCK(encoding=3, text="3"))
    tags.add(TDRC(encoding=3, text="2021"))
    tags.save(path)


def test_read_metadata_extracts_tags_and_duration(tmp_path):
    p = tmp_path / "song.mp3"
    _make_mp3(p)
    m = metadata.read_metadata(p)
    assert m.title == "My Title"
    assert m.artist == "My Artist"
    assert m.album == "My Album"
    assert m.genre == "My Genre"
    assert m.track_number == 3
    assert m.year == 2021
    assert m.duration_ms > 0
    assert m.size == p.stat().st_size


def test_read_metadata_defaults_when_untagged(tmp_path):
    p = tmp_path / "bare.mp3"
    frame = bytes.fromhex("fffb9064") + b"\x00" * 413
    p.write_bytes(frame * 40)
    m = metadata.read_metadata(p)
    assert m.title == "bare"          # falls back to file stem
    assert m.artist == ""
    assert m.track_number == 0
    assert m.year == 0
