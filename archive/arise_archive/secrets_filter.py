"""What is never indexed (13.3). Skipped files are logged by path only, never by content."""
from __future__ import annotations

import fnmatch
import re

PATH_PATTERNS = ("token*.json", "*token*.json", "client_secret*.json", "deploy_key*", "*.pem", "*.key")
# Real credential shapes. A document that only names the prefixes does not match,
# so SERVER_HANDOFF.md (which names them) stays searchable.
CONTENT_PATTERNS = [re.compile(p) for p in (rb"1//0[A-Za-z0-9_-]{20,}", rb"GOCSPX-[A-Za-z0-9_-]{20,}", rb"ya29\.[A-Za-z0-9_-]{20,}")]
PART_RE = re.compile(r"\.part\d+$", re.I)
SCAN_LIMIT = 10 * 1024 * 1024   # files above this (video, big archives) are not content-scanned


def path_reason(path: str) -> str | None:
    """Why a path is never indexed, or None."""
    base = path.rsplit("/", 1)[-1].lower()
    if path.startswith(".git/") or "/.git/" in path:
        return "repository internals"
    for pat in PATH_PATTERNS:
        if fnmatch.fnmatch(base, pat):
            return "credential file name"
    if PART_RE.search(base):
        return "split piece (the assembled file is indexed instead)"
    return None


def content_has_credential(data: bytes) -> bool:
    return any(p.search(data) for p in CONTENT_PATTERNS)
