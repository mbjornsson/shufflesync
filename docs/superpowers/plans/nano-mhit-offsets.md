# Confirmed mhit field offsets (little-endian u32)

Determined empirically from `device-backup-nano-20260602-204431/iTunes/iTunesDB`
using track ID 38 (`:iPod_Control:Music:F01:IIMR.mp3`).

## Key field offsets (relative to start of `mhit` marker)

| Offset  | Field                         | Value found      | Notes                              |
|---------|-------------------------------|------------------|------------------------------------|
| `0x04`  | header size                   | 624 (0x270)      | length of mhit header in bytes     |
| `0x08`  | total record size             | 1174 (0x496)     | includes all child mhod records    |
| `0x0c`  | child mhod count              | 7                |                                    |
| `0x10`  | track id                      | 38               | unique track identifier            |
| `0x18`  | type / codec tag              | 0x4d503320 ("MP3 ") | four-char codec identifier      |
| `0x24`  | **file size (bytes)**         | 46477771         | exact match to `ls -la` on device  |
| `0x28`  | **track length (ms)**         | 1931284          | exact match to mutagen duration    |
| `0x34`  | year                          | 2006             |                                    |
| `0x38`  | bitrate (kbps)                | 192              | matches mutagen ~192 kbps          |
| `0x3c`  | **sample rate (rate << 16)**  | 0xac440000       | high u16 = 44100 = 0xAC44         |

## Verification details

- **File size**: `ls -la /Volumes/IPOD/iPod_Control/Music/F01/IIMR.mp3` → 46477771 bytes.
  Exact match at offset `0x24`.

- **Track length**: `mutagen.mp3.MP3` reported `1931284 ms` (i.e. `int(length*1000)`).
  Exact match at offset `0x28`. No ±50 tolerance was needed.

- **Sample rate**: u32 at `0x3c` = `0xac440000`.
  High 16 bits = `0xAC44` = 44100 Hz — confirmed correct (mutagen reports `sample_rate=44100`).
  The value is stored as `sample_rate << 16`, so the low 16 bits are always 0.

## Full mhit header dump (offsets 0x00–0x7c)

```
+0x00  0x7469686d  ("mhit" marker)
+0x04         624  header size
+0x08        1174  total record size
+0x0c           7  child mhod count
+0x10          38  track id
+0x14           1  visible flag
+0x18  0x4d503320  codec tag ("MP3 ")
+0x1c       0x101  flags
+0x20  0xc8959ca0  timestamp (creation)
+0x24    46477771  ** file size (bytes) **
+0x28     1931284  ** track length (ms) **
+0x2c           1  track number
+0x30           2  disc number
+0x34        2006  year
+0x38         192  bitrate (kbps)
+0x3c  0xac440000  ** sample rate << 16 (44100 Hz) **
+0x40           0
+0x44           0
+0x48           0
+0x4c        1532  BPM or start/stop time field
+0x50           6  rating (0–100 scale, 6 stars?)
+0x54           6  compilation / media type
+0x58  0xcd1e8015  timestamp (last modified)
+0x5c           1
+0x60           1
+0x64           0
+0x68  0xc7b95ab0  timestamp
+0x6c           0
+0x70  0xfe3d6578
+0x74  0x3b32cc74
+0x78           0
+0x7c  0xffff0001
```

## Summary for implementation

When building a new `mhit` record, hard-code these offsets:

```python
MHIT_OFFSET_FILE_SIZE      = 0x24   # u32 LE — file size in bytes
MHIT_OFFSET_TRACK_LENGTH   = 0x28   # u32 LE — duration in milliseconds
MHIT_OFFSET_BITRATE        = 0x38   # u32 LE — bitrate in kbps
MHIT_OFFSET_SAMPLE_RATE    = 0x3c   # u32 LE — sample_rate << 16
```

Source track: `mhit` at byte offset 3032 in the golden DB, track ID 38.
