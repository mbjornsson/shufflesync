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
