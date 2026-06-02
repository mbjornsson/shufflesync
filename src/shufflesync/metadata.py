"""Read ID3 tags and duration from an MP3 for the iTunesDB."""
from dataclasses import dataclass
from pathlib import Path

from mutagen.mp3 import MP3


@dataclass(frozen=True)
class TrackMeta:
    title: str
    artist: str
    album: str
    genre: str
    track_number: int
    year: int
    duration_ms: int
    bitrate: int
    sample_rate: int
    size: int


def _first(tags, key: str) -> str:
    value = tags.get(key)
    return str(value.text[0]) if value and value.text else ""


def _int_prefix(text: str) -> int:
    """'3/12' or '2021-05' -> leading integer, else 0."""
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        else:
            break
    return int(digits) if digits else 0


def read_metadata(path: Path) -> TrackMeta:
    audio = MP3(path)
    tags = audio.tags
    title = _first(tags, "TIT2") if tags else ""
    return TrackMeta(
        title=title or path.stem,
        artist=_first(tags, "TPE1") if tags else "",
        album=_first(tags, "TALB") if tags else "",
        genre=_first(tags, "TCON") if tags else "",
        track_number=_int_prefix(_first(tags, "TRCK")) if tags else 0,
        year=_int_prefix(_first(tags, "TDRC")) if tags else 0,
        duration_ms=int(audio.info.length * 1000),
        bitrate=int(audio.info.bitrate // 1000),
        sample_rate=int(audio.info.sample_rate),
        size=path.stat().st_size,
    )
