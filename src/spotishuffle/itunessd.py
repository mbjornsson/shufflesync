"""Serializer for the 2nd-gen iPod shuffle iTunesSD database.

Format validated byte-for-byte against a real-hardware golden fixture.
See docs/superpowers/plans/2026-06-01-spotishuffle.md for the field tables.
"""

from typing import Iterable, Tuple

HEADER_CONST = bytes.fromhex("010800000012000000000000000000")  # 15 bytes


def build_header(track_count: int) -> bytes:
    """18-byte iTunesSD header: 3-byte big-endian count + 15 fixed bytes."""
    return track_count.to_bytes(3, "big") + HEADER_CONST


PATH_FIELD_LEN = 522  # 261 UTF-16 code units


def encode_path(device_path: str) -> bytes:
    """Encode a device-relative path as UTF-16BE, NUL-padded to 522 bytes.

    `device_path` uses forward slashes, e.g. '/iPod_Control/Music/F00/T0001.mp3'.
    """
    encoded = device_path.encode("utf-16-be")
    if len(encoded) > PATH_FIELD_LEN:
        raise ValueError(f"path too long for iTunesSD field: {device_path!r}")
    return encoded + b"\x00" * (PATH_FIELD_LEN - len(encoded))


ENTRY_LEN = 558
_FILETYPE = {"mp3": 0x01, "aac": 0x02, "wav": 0x04}


def build_entry(device_path: str, filetype: str) -> bytes:
    """Build one 558-byte iTunesSD track record.

    filetype: 'mp3' | 'aac' | 'wav'. Audio-analysis bytes are zeroed
    (the shuffle does not require them; see plan reference table).
    """
    if filetype not in _FILETYPE:
        raise ValueError(f"unsupported filetype: {filetype!r}")
    ftype = _FILETYPE[filetype]
    entry = bytearray(ENTRY_LEN)
    entry[0:3] = (ENTRY_LEN).to_bytes(3, "big")
    entry[29] = ftype
    entry[31] = ftype
    entry[32:32 + PATH_FIELD_LEN] = encode_path(device_path)
    entry[555] = 0x01
    return bytes(entry)


def build_itunessd(tracks: Iterable[Tuple[str, str]]) -> bytes:
    """Serialize the full iTunesSD. `tracks` is an ordered iterable of
    (device_path, filetype) pairs."""
    tracks = list(tracks)
    out = bytearray(build_header(len(tracks)))
    for device_path, filetype in tracks:
        out += build_entry(device_path, filetype)
    return bytes(out)
