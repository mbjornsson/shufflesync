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
