"""Serializer for the 2nd-gen iPod shuffle iTunesSD database.

Format validated byte-for-byte against a real-hardware golden fixture.
See docs/superpowers/plans/2026-06-01-spotishuffle.md for the field tables.
"""

from typing import Iterable, Tuple

HEADER_CONST = bytes.fromhex("010800000012000000000000000000")  # 15 bytes


def build_header(track_count: int) -> bytes:
    """18-byte iTunesSD header: 3-byte big-endian count + 15 fixed bytes."""
    return track_count.to_bytes(3, "big") + HEADER_CONST
