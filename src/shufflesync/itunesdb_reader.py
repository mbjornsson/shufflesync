"""Parse an existing iTunesDB, keeping each record's bytes verbatim."""
import struct
from dataclasses import dataclass
from typing import List


def _u32(data: bytes, o: int) -> int:
    return struct.unpack_from("<I", data, o)[0]


@dataclass(frozen=True)
class RawTrack:
    track_id: int
    raw: bytes


@dataclass(frozen=True)
class RawPlaylist:
    name: str
    is_master: bool
    track_ids: List[int]
    raw: bytes


@dataclass
class ParsedDB:
    tracks: List[RawTrack]
    playlists: List[RawPlaylist]

    def max_track_id(self) -> int:
        return max((t.track_id for t in self.tracks), default=0)


def _string_mhod_text(data: bytes, o: int):
    mtype = _u32(data, o + 12)
    if mtype in (1, 2, 3, 4, 5):
        blen = _u32(data, o + 0x1C)
        return mtype, data[o + 40:o + 40 + blen].decode("utf-16-le", "replace")
    return mtype, None


def parse(data: bytes) -> ParsedDB:
    if data[0:4] != b"mhbd":
        raise ValueError("not an iTunesDB (missing mhbd header)")
    tracks: List[RawTrack] = []
    playlists: List[RawPlaylist] = []
    o = _u32(data, 4)
    for _ in range(_u32(data, 0x14)):
        if data[o:o + 4] != b"mhsd":
            break
        ds_total = _u32(data, o + 8)
        ds_type = _u32(data, o + 12)
        inner = o + _u32(data, o + 4)
        if ds_type == 1 and data[inner:inner + 4] == b"mhlt":
            count = _u32(data, inner + 8)
            t = inner + _u32(data, inner + 4)
            for _ in range(count):
                if data[t:t + 4] != b"mhit":
                    break
                total = _u32(data, t + 8)
                tracks.append(RawTrack(_u32(data, t + 0x10), data[t:t + total]))
                t += total
        elif ds_type == 2 and data[inner:inner + 4] == b"mhlp":
            count = _u32(data, inner + 8)
            p = inner + _u32(data, inner + 4)
            for _ in range(count):
                if data[p:p + 4] != b"mhyp":
                    break
                ptot = _u32(data, p + 8)
                nmhod = _u32(data, p + 12)
                nitems = _u32(data, p + 0x10)
                is_master = _u32(data, p + 0x14) == 1
                q = p + _u32(data, p + 4)
                name = ""
                for _ in range(nmhod):
                    if data[q:q + 4] != b"mhod":
                        break
                    mtype, text = _string_mhod_text(data, q)
                    if mtype == 1 and text is not None:
                        name = text
                    q += _u32(data, q + 8)
                track_ids = []
                for _ in range(nitems):
                    if data[q:q + 4] != b"mhip":
                        break
                    track_ids.append(_u32(data, q + 0x18))
                    q += _u32(data, q + 8)
                playlists.append(RawPlaylist(name, is_master, track_ids, data[p:p + ptot]))
                p += ptot
        o += ds_total
    return ParsedDB(tracks, playlists)
