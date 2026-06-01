from pathlib import Path
from shufflesync import cli


def test_main_happy_path(monkeypatch, tmp_path, capsys):
    events = []

    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])
    fake_files = [tmp_path / "a.mp3"]

    def fake_download(url, dest):
        events.append(("download", url))
        return fake_files
    monkeypatch.setattr(cli.downloader, "download_playlist", fake_download)

    class FakeDevice:
        root = tmp_path
    monkeypatch.setattr(cli.device, "select_shuffle", lambda: FakeDevice())

    def fake_sync(dev, files):
        events.append(("sync", len(files)))
        return len(files)
    monkeypatch.setattr(cli.sync, "mirror_sync", fake_sync)

    rc = cli.main(["https://open.spotify.com/playlist/abc"])
    assert rc == 0
    assert ("download", "https://open.spotify.com/playlist/abc") in events
    assert ("sync", 1) in events


def test_main_missing_deps_errors(monkeypatch):
    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: ["spotdl"])
    rc = cli.main(["https://open.spotify.com/playlist/abc"])
    assert rc == 1
