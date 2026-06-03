from shufflesync import manifest, itunesdb_reader, itunesdb


def test_manifest_roundtrip(tmp_path):
    m = manifest.Manifest({"Mix": {"track_ids": [5], "files": ["F00/T0001.mp3"]}})
    m.save(tmp_path)
    again = manifest.load(tmp_path)
    assert again.playlists == {"Mix": {"track_ids": [5], "files": ["F00/T0001.mp3"]}}


def test_load_missing_is_empty(tmp_path):
    assert manifest.load(tmp_path).playlists == {}


def test_reconcile_drops_ids_absent_from_db(tmp_path):
    blob = itunesdb.build_itunesdb(
        [itunesdb.TrackEntry(track_id=5, title="t", artist="", album="", genre="",
                             location=":x", size=1, duration_ms=1, bitrate=1,
                             sample_rate=44100, track_number=1, year=2000)], "Mix")
    db = itunesdb_reader.parse(blob)
    (tmp_path / "F00").mkdir()
    (tmp_path / "F00" / "T0001.mp3").write_bytes(b"x")
    m = manifest.Manifest({"Mix": {"track_ids": [5, 99],
                                   "files": ["F00/T0001.mp3", "F00/gone.mp3"]}})
    m.reconcile(db, tmp_path)
    assert m.playlists["Mix"]["track_ids"] == [5]
    assert m.playlists["Mix"]["files"] == ["F00/T0001.mp3"]
