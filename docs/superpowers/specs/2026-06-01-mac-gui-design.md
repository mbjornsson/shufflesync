# Mac GUI design

## Goal

Give non-technical users a clickable macOS app that does what the `shufflesync`
CLI does: paste a Spotify playlist URL, optionally cap the number of tracks
(and pick them at random), download them, and mirror them onto an attached
2nd-gen iPod shuffle — with no Terminal use.

Scope is **macOS-only and personal distribution** (just the author and a few
friends). Cross-platform support, code signing/notarization, a track picker,
and custom Spotify auth are explicitly out of scope for v1.

## Architecture

A thin GUI sits on top of the existing core, with one new orchestration seam so
the CLI and GUI share identical logic and cannot drift.

```
gui.py        (new)  Tkinter window; no domain logic
cli.py        (mod)  argparse front-end
   \                /
    pipeline.py   (new)  run(request, on_progress) -> result
       |                  download -> find device -> mirror sync
   downloader.py (mod)  spotdl Python API wrapper
   device.py     (as-is) macOS shuffle detection
   sync.py       (as-is) mirror copy + iTunesSD
   itunessd.py   (as-is) binary serialization
```

### `pipeline.py` (new)

The single entry point both front-ends call.

- `@dataclass SyncRequest`: `playlist_url: str`, `count: int | None`,
  `randomize: bool`.
- `@dataclass SyncResult`: `synced: int`, `device_root: Path`.
- `run(request: SyncRequest, on_progress: Callable[[str], None]) -> SyncResult`
  - Resolves the cache dir from the playlist id (validated — see Security)
    under a **dot-free base** (see Cache location).
  - Calls the downloader, then `device.select_shuffle()`, then
    `sync.mirror_sync()`.
  - Emits human-readable lines via `on_progress(...)` at each step boundary
    ("Downloading…", "Found iPod at /Volumes/NONAME", "Copying 5 tracks…",
    "Done — 5 tracks on the shuffle").
  - Raises typed errors the front-ends format (see Error handling). It performs
    no printing and knows nothing about Tkinter or argparse.

`cli.py` is refactored to build a `SyncRequest` and call `run(...)` with
`on_progress=print`. Its existing flags, validation, and exit codes are
preserved.

### `gui.py` (new)

A single Tkinter window. It contains layout and event wiring only — all work
goes through `pipeline.run`.

Widgets (top to bottom):
- Playlist URL entry.
- Track count spinbox (blank = whole playlist) + "random" checkbox.
- Device indicator: a dot + label ("iPod connected (NONAME)" /
  "No iPod connected").
- Sync button (disabled while running or when no device is present).
- Scrolling read-only text log + a status label (Idle / Setting up / Working /
  Done / Error).

## spotdl integration (downloader.py)

`downloader.py` switches from shelling out to the `spotdl` CLI to calling
spotdl's **Python API in-process**, so the frozen `.app` needs no external
`spotdl` binary or system Python on `PATH`.

- Construct `Spotdl(...)` reusing spotdl's bundled default Spotify credentials
  (`spotdl.utils.config.DEFAULT_CONFIG["client_id"]` / `["client_secret"]`).
- `songs = spotdl.search([playlist_url])` returns the full track list.
- Apply the existing `select_tracks(songs, count, randomize)` to slice first-N
  or a random sample. This replaces the CLI-era save → trim → download dance and
  makes `--count` simpler.
- `spotdl.download_songs(selected)` downloads to the cache dir.
- `downloader_settings`:
  - `output`: an **absolute** template rooted at the cache dir,
    `"<cache_dir>/{list-position} - {title}.{output-ext}"`. The in-process API
    has no per-call working directory, so the subprocess-era "relative template +
    cwd" trick does not apply. An absolute template is safe here only because the
    cache base is dot-free (see Cache location); spotdl's path sanitizer strips
    leading dots from path components, which is exactly what broke the old
    `~/.shufflesync` path.
  - `format`: `"mp3"`.
  - `simple_tui`: `True`, so spotdl emits plain log lines instead of a rich
    progress bar.
  - `ffmpeg`: resolved path (see ffmpeg).

### Progress capture

Attach a `logging.Handler` to the `"spotdl"` logger; each emitted record is
forwarded to the pipeline's `on_progress` callback. The pipeline also emits its
own step lines. This gives the GUI a live log without parsing spotdl's exact
output format.

## Cache location

The cache moves from `~/.shufflesync/cache/<id>` to the macOS-standard,
dot-free `~/Library/Caches/shufflesync/<id>`. This is a deliberate change: the
in-process spotdl API writes to an absolute output template, and a dot-free
base eliminates the leading-dot sanitization bug class entirely rather than
working around it. The pipeline owns this path so the CLI and GUI stay
identical. No automatic migration of any existing `~/.shufflesync/cache`
contents — it is just a download cache and can be re-fetched (and removed by
the user).

## ffmpeg

ffmpeg is **not bundled** (~100 MB, architecture-specific). On first launch, if
ffmpeg is not already present in spotdl's config dir, call spotdl's own
`download_ffmpeg()` to install it there, showing a one-time "Setting up (first
run)…" status. Subsequent launches detect it and skip the step. The resolved
path is passed to `downloader_settings["ffmpeg"]`.

## Threading & progress

- The Sync button starts the work on a **background thread**; the UI thread
  never blocks.
- The worker's `on_progress` pushes lines onto a `queue.Queue`. The Tkinter
  main loop drains the queue on a timer (`root.after(~100ms, …)`), appends lines
  to the log, and updates the status label.
- Completion/failure is signalled through the same queue (a sentinel), which
  re-enables the Sync button and sets the final status.
- spotdl's async work runs inside the worker thread with its own event loop;
  it does not touch the Tkinter loop.

## Device indicator

A light poll on the UI timer (every ~2 s via `root.after`) calls
`device.find_shuffles()` and updates the indicator label and Sync button
enabled-state. No mounting is attempted by the poll; mounting still happens
inside `select_shuffle()` when a sync runs.

## Error handling

`pipeline.run` raises typed errors; each front-end formats them.

- **No device**: reuse `device.NoDeviceError` and its existing guidance text
  ("plug it in, enable disk use…"). GUI shows it in the log, status = Error.
- **No tracks downloaded**: friendly "Nothing was downloaded — check the
  playlist URL."
- **ffmpeg setup failed** (needs network): "Couldn't set up the audio
  converter; check your internet connection and try again."
- **Bad/empty URL**: validated up front (see Security).
- Unexpected exceptions: surfaced in the log with status = Error; the app stays
  open and the Sync button is re-enabled.

## Security (applies to both front-ends)

- The playlist id (last URL path segment) is validated against
  `^[A-Za-z0-9]+$` before being used as a cache path component, preventing path
  traversal from a crafted URL. (Already applied in the CLI; the pipeline owns
  this so the GUI inherits it.)
- The URL is handled as data only; the in-process API takes no shell, so there
  is no command- or argument-injection surface in the GUI path.

## Packaging & build

- `py2app` builds `shufflesync.app`, bundling the Tkinter app plus spotdl and
  its dependencies.
- A build step wraps the `.app` into a `.dmg` (`hdiutil` or `create-dmg`).
- Unsigned: the README and a first-run hint document the one-time
  **right-click → Open** to clear Gatekeeper's "unidentified developer" prompt.
- Add a `[project.optional-dependencies] gui` group (py2app) and a build
  script/Makefile target. The existing `shufflesync` console entry point is
  unchanged; add a `shufflesync-gui` entry point for `gui.main`.

## Testing

- `pipeline.run`: unit-tested with fakes for downloader/device/sync — asserts
  step ordering, the `on_progress` lines emitted, and error propagation.
- `downloader` (API version): tested with the spotdl API mocked — asserts
  search → `select_tracks` → `download_songs` wiring, relative output template,
  and `simple_tui`/format settings.
- `select_tracks`: already covered; behavior unchanged.
- `cli.py`: existing tests updated to the `pipeline.run` seam.
- `gui.py`: kept logic-free; at most a smoke test that the window constructs.
  Real validation is manual, with a shuffle attached.

## Out of scope (v1)

Code signing/notarization; Windows/Linux; a track-by-track picker; custom
Spotify OAuth; auto-update; bundling ffmpeg.
