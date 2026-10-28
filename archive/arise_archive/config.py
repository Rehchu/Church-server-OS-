"""Where the archive lives. Environment overrides exist for tests and for a second node."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPOS = {
    "arise-youtube-automation": "git@github.com:Rehchu/arise-youtube-automation.git",
    "ProjectBackups": "git@github.com:Rehchu/ProjectBackups.git",
}


@dataclass
class Config:
    root: Path = field(default_factory=lambda: Path(os.environ.get("ARISE_ARCHIVE_ROOT", "/srv/arise/archive")))
    state: Path = field(default_factory=lambda: Path(os.environ.get("ARISE_ARCHIVE_STATE", "/var/lib/arise/archive")))
    repos: dict = field(default_factory=lambda: dict(REPOS))

    @property
    def index(self) -> Path:
        return self.state / "index.sqlite"

    @property
    def build_log(self) -> Path:
        return self.state / "build.log"

    @property
    def status_file(self) -> Path:
        return self.state / "status.json"

    @property
    def assembled(self) -> Path:
        return self.root / "media-assembled"

    def repo_dir(self, name: str) -> Path:
        return self.root / name
