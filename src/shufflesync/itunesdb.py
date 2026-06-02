"""Serializer for the iPod nano (1-3G) iTunesDB database.

Little-endian (the iTunesSD format in itunessd.py is big-endian). Validated
against a real-hardware golden reference; see
docs/superpowers/plans/2026-06-02-nano-support.md for the field tables.
"""
import struct
from dataclasses import dataclass
from typing import List


def _u32(n: int) -> bytes:
    return struct.pack("<I", n)


def string_mhod(mhod_type: int, text: str) -> bytes:
    """A string mhod: title=1, location=2, album=3, artist=4, genre=5."""
    encoded = text.encode("utf-16-le")
    body = bytearray(40)
    body[0:4] = b"mhod"
    body[4:8] = _u32(24)                  # header_len
    body[8:12] = _u32(40 + len(encoded))  # total_len
    body[12:16] = _u32(mhod_type)
    body[0x18:0x1c] = _u32(1)             # position
    body[0x1c:0x20] = _u32(len(encoded))  # byte length
    return bytes(body) + encoded


MHIT_HEADER_LEN = 0x184
# Offsets confirmed empirically against the golden device DB (Task 0).
MHIT_OFFSETS = {"size": 0x24, "length_ms": 0x28, "sample_rate": 0x3c}


@dataclass(frozen=True)
class TrackEntry:
    track_id: int
    title: str
    artist: str
    album: str
    genre: str
    location: str          # colon path, e.g. ":iPod_Control:Music:F00:T0001.mp3"
    size: int
    duration_ms: int
    bitrate: int
    sample_rate: int
    track_number: int
    year: int


def track_mhit(entry: "TrackEntry") -> bytes:
    mhods = b"".join([
        string_mhod(1, entry.title),
        string_mhod(4, entry.artist),
        string_mhod(3, entry.album),
        string_mhod(5, entry.genre),
        string_mhod(2, entry.location),
    ])
    h = bytearray(MHIT_HEADER_LEN)
    h[0:4] = b"mhit"
    h[4:8] = _u32(MHIT_HEADER_LEN)
    h[8:12] = _u32(MHIT_HEADER_LEN + len(mhods))
    h[12:16] = _u32(5)                  # mhod count
    h[16:20] = _u32(entry.track_id)
    h[20:24] = _u32(1)                  # visible
    h[0x18:0x1c] = b"MP3 "[::-1]        # filetype marker
    h[0x1c] = 1                          # type1
    h[0x1d] = 1                          # type2
    h[MHIT_OFFSETS["size"]:MHIT_OFFSETS["size"] + 4] = _u32(entry.size)
    h[MHIT_OFFSETS["length_ms"]:MHIT_OFFSETS["length_ms"] + 4] = _u32(entry.duration_ms)
    h[0x2c:0x30] = _u32(entry.track_number)
    h[0x34:0x38] = _u32(entry.year)
    h[0x38:0x3a] = struct.pack("<H", entry.bitrate)
    h[MHIT_OFFSETS["sample_rate"]:MHIT_OFFSETS["sample_rate"] + 4] = _u32(entry.sample_rate << 16)
    return bytes(h) + mhods


def _mhsd(dataset_type: int, body: bytes) -> bytes:
    h = bytearray(96)
    h[0:4] = b"mhsd"
    h[4:8] = _u32(96)
    h[8:12] = _u32(96 + len(body))
    h[12:16] = _u32(dataset_type)
    return bytes(h) + body


def track_dataset(entries: List["TrackEntry"]) -> bytes:
    mhlt = bytearray(92)
    mhlt[0:4] = b"mhlt"
    mhlt[4:8] = _u32(92)
    mhlt[8:12] = _u32(len(entries))
    body = bytes(mhlt) + b"".join(track_mhit(e) for e in entries)
    return _mhsd(1, body)


def _position_mhod(position: int) -> bytes:
    body = bytearray(44)
    body[0:4] = b"mhod"
    body[4:8] = _u32(24)        # header_len
    body[8:12] = _u32(44)       # total_len
    body[12:16] = _u32(100)     # type 100 = playlist item position
    body[0x18:0x1c] = _u32(position)
    return bytes(body)


def playlist_item(track_id: int, position: int) -> bytes:
    child = _position_mhod(position)
    h = bytearray(76)
    h[0:4] = b"mhip"
    h[4:8] = _u32(76)
    h[8:12] = _u32(76 + len(child))
    h[12:16] = _u32(1)                  # mhod count
    h[0x18:0x1c] = _u32(track_id)
    return bytes(h) + child


def _mhyp(name: str, track_ids: List[int], is_master: bool) -> bytes:
    title = string_mhod(1, name)
    items = b"".join(playlist_item(t, i) for i, t in enumerate(track_ids))
    body = title + items
    h = bytearray(184)
    h[0:4] = b"mhyp"
    h[4:8] = _u32(184)
    h[8:12] = _u32(184 + len(body))
    h[12:16] = _u32(1)                  # mhod count (title only)
    h[16:20] = _u32(len(track_ids))     # item count
    h[20:24] = _u32(1 if is_master else 0)  # master flag
    return bytes(h) + body


def playlist_dataset(playlist_name: str, track_ids: List[int]) -> bytes:
    mhlp = bytearray(92)
    mhlp[0:4] = b"mhlp"
    mhlp[4:8] = _u32(92)
    mhlp[8:12] = _u32(2)                # master + one named playlist
    master = _mhyp("shufflesync", track_ids, is_master=True)
    named = _mhyp(playlist_name, track_ids, is_master=False)
    return _mhsd(2, bytes(mhlp) + master + named)


def _mhbd(dataset_count: int, body: bytes) -> bytes:
    h = bytearray(244)
    h[0:4] = b"mhbd"
    h[4:8] = _u32(244)
    h[8:12] = _u32(244 + len(body))
    h[12:16] = _u32(1)                  # unk1
    h[16:20] = _u32(0x13)               # db version (libgpod-compatible)
    h[20:24] = _u32(dataset_count)
    h[24:32] = b"shuffl\x00\x00"         # 8-byte library id (stable, arbitrary)
    h[0x46:0x48] = b"en"                # language
    return bytes(h) + body


def build_itunesdb(entries: List["TrackEntry"], playlist_name: str) -> bytes:
    """Serialize a full iTunesDB: one track dataset + one playlist dataset
    (master playlist + a named playlist) referencing every track."""
    track_ids = [e.track_id for e in entries]
    body = track_dataset(entries) + playlist_dataset(playlist_name, track_ids)
    return _mhbd(2, body)
