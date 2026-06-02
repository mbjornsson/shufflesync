import struct
from shufflesync import itunesdb


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def test_string_mhod_layout():
    m = itunesdb.string_mhod(1, "Hi")  # type 1 = title
    assert m[0:4] == b"mhod"
    assert _u32(m, 4) == 24                      # header_len
    assert _u32(m, 8) == len(m)                  # total_len
    assert _u32(m, 8) == 40 + len("Hi".encode("utf-16-le"))
    assert _u32(m, 12) == 1                       # type
    assert _u32(m, 0x18) == 1                     # position
    assert _u32(m, 0x1c) == 4                     # byte length (2 chars utf-16)
    assert m[40:].decode("utf-16-le") == "Hi"


def test_location_mhod_uses_colon_path():
    m = itunesdb.string_mhod(2, ":iPod_Control:Music:F00:T0001.mp3")
    assert _u32(m, 12) == 2
    assert m[40:].decode("utf-16-le") == ":iPod_Control:Music:F00:T0001.mp3"
