from pathlib import Path
from shufflesync import cli


def test_main_happy_path(monkeypatch, tmp_path, capsys):
    events = []

    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])
    fake_files = [tmp_path / "a.mp3"]

    def fake_download(url, dest, count=None, randomize=False):
        events.append(("download", url, count, randomize))
        return cli.downloader.DownloadResult(fake_files, "Evening Chill")
    monkeypatch.setattr(cli.downloader, "download_playlist", fake_download)

    class FakeDevice:
        root = tmp_path
    monkeypatch.setattr(cli.device, "select_ipod", lambda: FakeDevice())

    def fake_sync(dev, files, playlist_name="shufflesync"):
        events.append(("sync", len(files), playlist_name))
        return len(files)
    monkeypatch.setattr(cli.sync, "mirror_sync", fake_sync)

    rc = cli.main(["https://open.spotify.com/playlist/abc"])
    assert rc == 0
    assert ("download", "https://open.spotify.com/playlist/abc", None, False) in events
    # the real playlist name (not the URL id) is passed to sync
    assert ("sync", 1, "Evening Chill") in events


def test_main_passes_count_and_random_flags(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])

    def fake_download(url, dest, count=None, randomize=False):
        captured["count"] = count
        captured["randomize"] = randomize
        return cli.downloader.DownloadResult([tmp_path / "a.mp3"], "Mix")
    monkeypatch.setattr(cli.downloader, "download_playlist", fake_download)

    class FakeDevice:
        root = tmp_path
    monkeypatch.setattr(cli.device, "select_ipod", lambda: FakeDevice())
    monkeypatch.setattr(cli.sync, "mirror_sync", lambda dev, files, playlist_name=None: len(files))

    rc = cli.main(["https://open.spotify.com/playlist/abc", "--count", "5", "--random"])
    assert rc == 0
    assert captured == {"count": 5, "randomize": True}


def test_main_rejects_non_positive_count(monkeypatch):
    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])
    rc = cli.main(["https://open.spotify.com/playlist/abc", "--count", "0"])
    assert rc == 1


def test_main_rejects_malformed_playlist_url(monkeypatch):
    """A URL whose trailing segment isn't a plain id must be rejected before it
    is used as a cache path component (path traversal defense)."""
    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])
    called = []
    monkeypatch.setattr(
        cli.downloader, "download_playlist", lambda *a, **k: called.append(1) or []
    )
    rc = cli.main(["https://open.spotify.com/playlist/.."])
    assert rc == 1
    assert called == []  # bailed out before downloading


def test_main_handles_download_failure_without_traceback(monkeypatch, capsys):
    """A failed spotdl run should give a clean message and exit 1, not a
    CalledProcessError traceback."""
    import subprocess as sp

    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])

    def boom(*a, **k):
        raise sp.CalledProcessError(1, ["spotdl"])
    monkeypatch.setattr(cli.downloader, "download_playlist", boom)

    rc = cli.main(["https://open.spotify.com/playlist/abc"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert err.strip()  # some message was printed


def test_main_missing_deps_errors(monkeypatch):
    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: ["spotdl"])
    rc = cli.main(["https://open.spotify.com/playlist/abc"])
    assert rc == 1


def test_main_add_flag_calls_add_sync(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])
    monkeypatch.setattr(cli.downloader, "download_playlist",
                        lambda *a, **k: cli.downloader.DownloadResult([tmp_path / "a.mp3"], "Mix"))
    class Dev:
        root = tmp_path
        family = cli.device.DeviceFamily.NANO_1G_3G
    monkeypatch.setattr(cli.device, "select_ipod", lambda: Dev())
    called = {}
    monkeypatch.setattr(cli.sync, "add_sync",
                        lambda dev, files, playlist_name: called.setdefault("add", True) or len(files))
    monkeypatch.setattr(cli.sync, "mirror_sync",
                        lambda *a, **k: called.setdefault("mirror", True) or 0)
    rc = cli.main(["https://open.spotify.com/playlist/abc", "--add"])
    assert rc == 0
    assert called == {"add": True}


def test_main_add_rejected_for_shuffle(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.downloader, "check_dependencies", lambda: [])
    monkeypatch.setattr(cli.downloader, "download_playlist",
                        lambda *a, **k: cli.downloader.DownloadResult([tmp_path / "a.mp3"], "Mix"))
    class Dev:
        root = tmp_path
        family = cli.device.DeviceFamily.SHUFFLE_2G
    monkeypatch.setattr(cli.device, "select_ipod", lambda: Dev())
    rc = cli.main(["https://open.spotify.com/playlist/abc", "--add"])
    assert rc == 1
    assert "shuffle" in capsys.readouterr().err.lower()
