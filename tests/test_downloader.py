import random
from pathlib import Path

import pytest
from shufflesync import downloader


def test_check_dependencies_reports_missing(monkeypatch):
    monkeypatch.setattr(downloader.shutil, "which", lambda name: None)
    missing = downloader.check_dependencies()
    assert set(missing) == {"spotdl", "ffmpeg"}


def test_check_dependencies_all_present(monkeypatch):
    monkeypatch.setattr(downloader.shutil, "which", lambda name: "/usr/bin/" + name)
    assert downloader.check_dependencies() == []


def test_download_playlist_invokes_spotdl_and_returns_mp3s(monkeypatch, tmp_path):
    calls = {}

    def fake_run(cmd, cwd, check):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        (tmp_path / "01 - Song A.mp3").write_bytes(b"a")
        (tmp_path / "02 - Song B.mp3").write_bytes(b"b")
        (tmp_path / "cover.jpg").write_bytes(b"x")
        class R: returncode = 0
        return R()

    monkeypatch.setattr(downloader.subprocess, "run", fake_run)
    files = downloader.download_playlist("https://open.spotify.com/playlist/abc", tmp_path)
    assert calls["cmd"][0] == "spotdl"
    assert "https://open.spotify.com/playlist/abc" in calls["cmd"]
    assert "--output" in calls["cmd"]
    assert [f.name for f in files] == ["01 - Song A.mp3", "02 - Song B.mp3"]


def test_download_playlist_with_count_saves_selects_then_downloads(monkeypatch, tmp_path):
    import json

    cmds = []

    def fake_run(cmd, cwd, check):
        cmds.append(cmd)
        if "save" in cmd:
            save_file = Path(cmd[cmd.index("--save-file") + 1])
            save_file.write_text(json.dumps(_tracks(5)))
        else:  # download
            (tmp_path / "01 - Song A.mp3").write_bytes(b"a")
            (tmp_path / "02 - Song B.mp3").write_bytes(b"b")
        class R: returncode = 0
        return R()

    monkeypatch.setattr(downloader.subprocess, "run", fake_run)
    files = downloader.download_playlist(
        "https://open.spotify.com/playlist/abc", tmp_path, count=2, randomize=False
    )

    save_cmd, download_cmd = cmds
    assert save_cmd[:2] == ["spotdl", "save"]
    assert download_cmd[:2] == ["spotdl", "download"]
    # download runs against the trimmed save file holding exactly 2 tracks,
    # passed after the `--` end-of-options separator
    trimmed = Path(download_cmd[download_cmd.index("--") + 1])
    assert json.loads(trimmed.read_text()) == _tracks(5)[:2]
    assert [f.name for f in files] == ["01 - Song A.mp3", "02 - Song B.mp3"]


def test_download_playlist_clears_stale_files_from_previous_run(monkeypatch, tmp_path):
    """A previous, larger run's MP3s must not leak into this run's result, or a
    later `--count N` would sync more than N tracks."""
    dest = tmp_path / "cache"
    dest.mkdir()
    (dest / "99 - Old Track.mp3").write_bytes(b"old")

    def fake_run(cmd, cwd, check):
        (dest / "01 - New Track.mp3").write_bytes(b"new")
        class R: returncode = 0
        return R()

    monkeypatch.setattr(downloader.subprocess, "run", fake_run)
    files = downloader.download_playlist("https://open.spotify.com/playlist/abc", dest)
    assert [f.name for f in files] == ["01 - New Track.mp3"]


def test_download_passes_url_after_end_of_options_separator(monkeypatch, tmp_path):
    """The playlist URL goes after `--` so a leading-dash string can't be
    interpreted by spotdl as an option (argument injection)."""
    calls = {}

    def fake_run(cmd, cwd, check):
        calls["cmd"] = cmd
        (tmp_path / "01 - Song A.mp3").write_bytes(b"a")
        class R: returncode = 0
        return R()

    monkeypatch.setattr(downloader.subprocess, "run", fake_run)
    url = "https://open.spotify.com/playlist/abc"
    downloader.download_playlist(url, tmp_path)
    cmd = calls["cmd"]
    assert "--" in cmd
    assert cmd[cmd.index("--") + 1] == url


def test_output_template_survives_spotdl_path_sanitization(tmp_path):
    """spotdl sanitizes the --output template and strips leading dots from each
    path component (see spotdl.utils.formatter.create_path_object), so an
    absolute template under a hidden dir like ~/.shufflesync gets rewritten to
    ~/shufflesync and downloads land in the wrong place. The template must be
    relative so spotdl resolves it against cwd=dest instead.
    """
    from spotdl.utils.formatter import create_path_object

    dest = tmp_path / ".shufflesync" / "cache" / "PID"
    args = downloader._output_args(dest)
    template = args[args.index("--output") + 1]

    # Mirror what spotdl does: sanitize the template, then resolve it the way the
    # downloader does (relative paths are written under the process cwd = dest).
    resolved = (dest / create_path_object(template)).resolve()
    assert dest.resolve() in resolved.parents


def _tracks(n):
    return [{"name": f"Song {i}", "url": f"https://track/{i}"} for i in range(n)]


def test_select_tracks_takes_first_n_in_order():
    selected = downloader.select_tracks(_tracks(5), count=3, randomize=False)
    assert [t["name"] for t in selected] == ["Song 0", "Song 1", "Song 2"]


def test_select_tracks_random_picks_n_distinct_tracks():
    tracks = _tracks(5)
    random.seed(0)
    selected = downloader.select_tracks(tracks, count=3, randomize=True)
    assert len(selected) == 3
    names = [t["name"] for t in selected]
    assert len(set(names)) == 3
    assert all(t in tracks for t in selected)
    # not simply the first three, given this seed
    assert names != ["Song 0", "Song 1", "Song 2"]


def test_select_tracks_count_exceeds_length_returns_all():
    tracks = _tracks(2)
    assert downloader.select_tracks(tracks, count=10, randomize=False) == tracks
    assert downloader.select_tracks(tracks, count=10, randomize=True) == tracks
