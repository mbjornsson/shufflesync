# Nano add-by-default + `--wipe` design

## Goal

Make the **non-destructive** action the default on the iPod nano, so a user who
forgets a flag can't accidentally erase their library. The destructive full
replace moves behind an explicit, clearly-named `--wipe` flag with a
confirmation prompt. The shuffle is unchanged (always a full replace).

## Behavior

- **Nano, no flags → add** (preserve existing music; idempotent per playlist).
- **Nano `--wipe` → replace everything** (erase all music + playlists, leaving
  just this playlist), after a confirmation prompt when the nano is non-empty.
- **Shuffle → always replace** (it has no library). `--wipe` on a shuffle is a
  redundant no-op (accepted); `--add` on a shuffle is an error.
- The CLI **announces the mode** every run.
- `--add` and `--wipe` together → error (contradictory).
- `--add` is kept as an accepted explicit alias for the nano default, so the
  previously-shipped usage/docs keep working.

## Decision logic (`cli.py`)

```
is_shuffle = dev.family == SHUFFLE_2G
if args.add and args.wipe: error
if args.add and is_shuffle: error ("--add is only for the nano")
wipe = is_shuffle or args.wipe        # nano wipes only with --wipe
if wipe and not is_shuffle:           # confirm before erasing a real library
    tracks, playlists = sync.existing_content(dev)
    if tracks and sys.stdin.isatty():
        if input("--wipe will erase all <tracks> track(s) and <playlists> "
                 "playlist(s) on the iPod. Continue? [y/N] ") not in yes:
            print("Aborted."); return 1
if wipe: sync.mirror_sync(...)        # announce "Replacing everything ..."
else:    sync.add_sync(...)           # announce 'Adding "<name>" ... existing kept'
```

- The confirmation only prompts when interactive (`stdin.isatty()`) and the nano
  is non-empty. Non-interactive (scripts): `--wipe` is already explicit intent,
  so proceed without prompting (never hang).

## New helper (`sync.py`)

```python
def existing_content(device: IpodDevice) -> tuple[int, int]:
    """(track_count, playlist_count) currently on the device; (0, 0) if none or
    the database can't be read."""
```
Reads `device.db_path` via `itunesdb_reader`; counts tracks and non-master
playlists. Used by the CLI for the confirmation prompt (and the count shown).

## CLI surface

- Add `--wipe` (store_true): "Erase ALL music and playlists on the iPod nano and
  replace them with just this playlist (the nano keeps your music by default)."
- `--add` help updated: "Add this playlist to the iPod nano, keeping existing
  music (this is the default for the nano)."

## Error handling

- `--add` + `--wipe` → message + exit 1.
- `--add` on shuffle → existing message + exit 1.
- Wipe declined at the prompt → "Aborted." + exit 1 (nothing synced).

## Testing

- Nano, no flags → `add_sync` called, `mirror_sync` not.
- Nano `--wipe`, empty device → `mirror_sync` called, no prompt.
- Nano `--wipe`, non-empty + interactive + "n" → exit 1, neither sync called.
- Nano `--wipe`, non-empty + interactive + "y" → `mirror_sync` called.
- Shuffle, no flags → `mirror_sync` called.
- Shuffle `--add` → exit 1. `--add` + `--wipe` → exit 1.
- `sync.existing_content`: counts tracks/playlists from a built DB; (0,0) for a
  missing/unreadable DB.

## Out of scope

Changing shuffle behavior; per-playlist removal commands; a GUI surface for the
mode.
