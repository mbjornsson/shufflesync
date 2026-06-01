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
