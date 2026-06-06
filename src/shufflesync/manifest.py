"""Track which tracks/playlists shufflesync added to a device."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

FILENAME = ".shufflesync.json"


@dataclass
class Manifest:
    playlists: Dict[str, dict] = field(default_factory=dict)

    def reconcile(self, parsed_db, music_dir: Path) -> None:
        live_ids = {t.track_id for t in parsed_db.tracks}
        for name, info in list(self.playlists.items()):
            if not isinstance(info, dict):
                self.playlists.pop(name)
                continue
            info["track_ids"] = [i for i in info.get("track_ids", []) if i in live_ids]
            info["files"] = [
                f for f in info.get("files", []) if (music_dir / f).exists()
            ]

    def save(self, itunes_dir: Path) -> None:
        (itunes_dir / FILENAME).write_text(json.dumps({"playlists": self.playlists}))


def load(itunes_dir: Path) -> "Manifest":
    path = itunes_dir / FILENAME
    if not path.exists():
        return Manifest()
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError):
        return Manifest()
    if not isinstance(data, dict):
        return Manifest()
    playlists = data.get("playlists", {})
    if not isinstance(playlists, dict):
        return Manifest()
    return Manifest(playlists)
