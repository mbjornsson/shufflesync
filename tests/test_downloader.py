import json
import random
from pathlib import Path

import pytest
from shufflesync import downloader


def _save_tracks(n, list_name="My Mix"):
    return [{"name": f"Song {i}", "url": f"https://track/{i}", "list_name": list_name,
             "list_position": i + 1, "list_length": n} for i in range(n)]


def _fake_spotdl(save_tracks, downloaded, m3u_names):
    """Fake subprocess.run: `save` writes the save file; `download` creates the
    given mp3s and writes an m3u listing m3u_names (relative to cwd=dest)."""
    def run(cmd, cwd, check):
        if "save" in cmd:
            Path(cmd[cmd.index("--save-file") + 1]).write_text(json.dumps(save_tracks))
        else:
            dest = Path(cwd)
            for name in downloaded:
                (dest / name).write_bytes(b"x")
            m3u = Path(cmd[cmd.index("--m3u") + 1])
            if not m3u.is_absolute():           # spotdl resolves it against cwd=dest
                m3u = dest / m3u
            m3u.write_text("#EXTM3U\n" + "\n".join(m3u_names) + "\n")
        class R: returncode = 0
        return R()
    return run


def test_check_dependencies_reports_missing(monkeypatch):
    monkeypatch.setattr(downloader.shutil, "which", lambda name: None)
    missing = downloader.check_dependencies()
    assert set(missing) == {"spotdl", "ffmpeg"}


def test_check_dependencies_all_present(monkeypatch):
    monkeypatch.setattr(downloader.shutil, "which", lambda name: "/usr/bin/" + name)
    assert downloader.check_dependencies() == []


def test_download_playlist_returns_files_and_real_name(monkeypatch, tmp_path):
    dest = tmp_path / "PID"
    monkeypatch.setattr(downloader.subprocess, "run", _fake_spotdl(
        _save_tracks(2, list_name="Evening Chill"),
        downloaded=["01 - A.mp3", "02 - B.mp3"],
        m3u_names=["01 - A.mp3", "02 - B.mp3"]))
    result = downloader.download_playlist("https://open.spotify.com/playlist/abc", dest)
    assert [f.name for f in result.files] == ["01 - A.mp3", "02 - B.mp3"]
    assert result.playlist_name == "Evening Chill"


def test_download_playlist_reuses_cached_files_no_wipe(monkeypatch, tmp_path):
    """Incremental: a previously-downloaded file is not wiped; spotdl skips it
    and only new tracks download. The m3u lists the full current selection."""
    dest = tmp_path / "PID"
    dest.mkdir()
    (dest / "01 - A.mp3").write_bytes(b"cached")          # from a previous run
    monkeypatch.setattr(downloader.subprocess, "run", _fake_spotdl(
        _save_tracks(2),
        downloaded=["02 - B.mp3"],                        # only the new one
        m3u_names=["01 - A.mp3", "02 - B.mp3"]))
    result = downloader.download_playlist("https://open.spotify.com/playlist/abc", dest)
    assert (dest / "01 - A.mp3").read_bytes() == b"cached"  # not re-downloaded
    assert {f.name for f in result.files} == {"01 - A.mp3", "02 - B.mp3"}


def test_download_playlist_prunes_orphans(monkeypatch, tmp_path):
    """A cached file not in this run's m3u (e.g. playlist shrank) is pruned and
    not returned."""
    dest = tmp_path / "PID"
    dest.mkdir()
    (dest / "99 - Stale.mp3").write_bytes(b"old")
    monkeypatch.setattr(downloader.subprocess, "run", _fake_spotdl(
        _save_tracks(1), downloaded=["01 - New.mp3"], m3u_names=["01 - New.mp3"]))
    result = downloader.download_playlist("https://open.spotify.com/playlist/abc", dest)
    assert [f.name for f in result.files] == ["01 - New.mp3"]
    assert not (dest / "99 - Stale.mp3").exists()


def test_download_playlist_count_trims_selection_and_uses_m3u(monkeypatch, tmp_path):
    dest = tmp_path / "PID"
    cmds = []
    save = _save_tracks(5)

    def run(cmd, cwd, check):
        cmds.append(cmd)
        if "save" in cmd:
            Path(cmd[cmd.index("--save-file") + 1]).write_text(json.dumps(save))
        else:
            (Path(cwd) / "01 - A.mp3").write_bytes(b"a")
            (Path(cwd) / "02 - B.mp3").write_bytes(b"b")
            m3u = Path(cmd[cmd.index("--m3u") + 1])
            if not m3u.is_absolute():
                m3u = Path(cwd) / m3u
            m3u.write_text("01 - A.mp3\n02 - B.mp3\n")
        class R: returncode = 0
        return R()

    monkeypatch.setattr(downloader.subprocess, "run", run)
    result = downloader.download_playlist(
        "https://open.spotify.com/playlist/abc", dest, count=2)
    save_cmd, download_cmd = cmds
    assert save_cmd[:2] == ["spotdl", "save"]
    assert download_cmd[:2] == ["spotdl", "download"]
    assert "--m3u" in download_cmd
    selection = Path(download_cmd[2])
    assert json.loads(selection.read_text()) == save[:2]
    assert [f.name for f in result.files] == ["01 - A.mp3", "02 - B.mp3"]


def test_download_uses_relative_m3u_path(monkeypatch, tmp_path):
    """--m3u must be relative: an absolute path under ~/.shufflesync is
    mis-written by spotdl (cwd=dest), landing the m3u in dest/Users/... so no
    tracks are found."""
    dest = tmp_path / "PID"
    cmds = []

    def run(cmd, cwd, check):
        cmds.append(cmd)
        if "save" in cmd:
            Path(cmd[cmd.index("--save-file") + 1]).write_text(json.dumps(_save_tracks(1)))
        else:
            (Path(cwd) / "A.mp3").write_bytes(b"a")
            (Path(cwd) / cmd[cmd.index("--m3u") + 1]).write_text("A.mp3\n")
        class R: returncode = 0
        return R()

    monkeypatch.setattr(downloader.subprocess, "run", run)
    result = downloader.download_playlist("https://open.spotify.com/playlist/abc", dest)
    download_cmd = cmds[1]
    assert not Path(download_cmd[download_cmd.index("--m3u") + 1]).is_absolute()
    assert [f.name for f in result.files] == ["A.mp3"]


def test_output_template_is_position_independent():
    """The cache filename must not include the playlist position, or reordering
    the playlist would change names and re-download everything."""
    args = downloader._output_args(Path("/x"))
    template = args[args.index("--output") + 1]
    assert "{list-position}" not in template


def test_download_playlist_name_falls_back_to_id(monkeypatch, tmp_path):
    dest = tmp_path / "37i9PID"
    untagged = [{"name": "x", "url": "u"}]                # no list_name
    monkeypatch.setattr(downloader.subprocess, "run", _fake_spotdl(
        untagged, downloaded=["01 - x.mp3"], m3u_names=["01 - x.mp3"]))
    result = downloader.download_playlist("https://open.spotify.com/playlist/37i9PID", dest)
    assert result.playlist_name == "37i9PID"


def test_download_rejects_option_like_url(monkeypatch, tmp_path):
    """A URL that looks like a flag is rejected rather than passed to spotdl
    (argument-injection guard, replacing the unsupported `--` separator)."""
    monkeypatch.setattr(downloader.subprocess, "run",
                        lambda *a, **k: pytest.fail("spotdl should not be called"))
    with pytest.raises(ValueError):
        downloader.download_playlist("--delete-everything", tmp_path)


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
