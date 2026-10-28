"""The channel catalogue: every video the automator repo's snapshots know, one record per id.

The snapshots are files the toolkit writes on the PC (docs/ARCHIVE.md lists them):

    cloud_workspace/_all_vids.json        YouTube API objects (id, snippet, status, liveStreamingDetails, ...)
    cloud_workspace/_channel_index.json   {id: {title, dur, date_ct, pub, privacy, desc}}
    channel_descriptions.json             [{video_id, title, published, type, description}]
    channel_inventory.csv                 video_id,type,title,published,duration,views,privacy,...

They are snapshots, not the live channel: a title can have changed since. The
dashboard says so and links to YouTube for what is there now. Read only; the
result is cached until a snapshot file changes.
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import Config

AUTOMATION = "arise-youtube-automation"
# Oldest-shaped first: a later source fills or replaces a field the earlier one had.
SOURCES = [
    ("channel_inventory.csv", "inventory"),
    ("channel_descriptions.json", "descriptions"),
    ("cloud_workspace/_channel_index.json", "index"),
    ("cloud_workspace/_all_vids.json", "api"),
]
ID_RE = re.compile(r"[A-Za-z0-9_-]{11}")
LINK_RE = re.compile(r"(?:youtu\.be/|youtube\.com/(?:live/|shorts/|watch\?v=|embed/))([A-Za-z0-9_-]{11})")

_cache: dict = {"key": None, "videos": {}}


def iso_seconds(d: str | None) -> int | None:
    """PT1H2M3S, P0D, or 1:02:03 / 4:07 -> seconds."""
    if not d:
        return None
    d = str(d).strip()
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", d)
    if m:
        days, h, mi, s = (int(x or 0) for x in m.groups())
        return days * 86400 + h * 3600 + mi * 60 + s
    if re.fullmatch(r"\d+(?::\d{1,2}){1,2}", d):
        n = 0
        for part in d.split(":"):
            n = n * 60 + int(part)
        return n
    return None


def central_date(ts: str | None) -> str | None:
    """An ISO timestamp -> the date in Pineville (America/Chicago)."""
    if not ts:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ts):
        return ts
    try:
        from zoneinfo import ZoneInfo
        t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(ZoneInfo("America/Chicago")).date().isoformat()
    except (ValueError, KeyError):
        return ts[:10] if re.match(r"\d{4}-\d{2}-\d{2}", ts) else None


def _put(rec: dict, k: str, v):
    if v not in (None, "", [], {}):
        rec[k] = v


def _from_api(v: dict) -> tuple[str, dict]:
    sn, st, cd, live = v.get("snippet") or {}, v.get("status") or {}, v.get("contentDetails") or {}, v.get("liveStreamingDetails") or {}
    r: dict = {}
    _put(r, "title", sn.get("title"))
    _put(r, "description", sn.get("description"))
    _put(r, "published", sn.get("publishedAt"))
    _put(r, "privacy", st.get("privacyStatus"))
    _put(r, "seconds", iso_seconds(cd.get("duration")) or None)
    _put(r, "views", int((v.get("statistics") or {}).get("viewCount") or 0) or None)
    if live:
        r["live"] = True
        _put(r, "started", live.get("actualStartTime") or live.get("scheduledStartTime"))
    if sn.get("liveBroadcastContent") in ("upcoming", "live"):
        r["upcoming"] = sn.get("liveBroadcastContent")
    return v.get("id"), r


def _from_index(vid: str, v: dict) -> dict:
    r: dict = {}
    _put(r, "title", v.get("title"))
    _put(r, "description", v.get("desc"))
    _put(r, "published", v.get("pub"))
    _put(r, "privacy", v.get("privacy"))
    _put(r, "seconds", iso_seconds(v.get("dur")) or None)
    _put(r, "service_date", v.get("date_ct"))
    return r


def _from_descriptions(v: dict) -> dict:
    r: dict = {}
    _put(r, "title", v.get("title"))
    _put(r, "description", v.get("description"))
    _put(r, "published", v.get("published"))
    _put(r, "type", v.get("type"))
    return r


def _from_inventory(row: dict) -> dict:
    r: dict = {}
    _put(r, "title", row.get("title"))
    _put(r, "published", row.get("published"))
    _put(r, "type", row.get("type"))
    _put(r, "privacy", row.get("privacy"))
    _put(r, "seconds", iso_seconds(row.get("duration")))
    try:
        _put(r, "views", int(row.get("views") or 0) or None)
    except ValueError:
        pass
    return r


def _read(path: Path, shape: str) -> list[tuple[str, dict]]:
    raw = path.read_bytes()
    if shape == "inventory":
        rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace")))
        return [(r.get("video_id") or "", _from_inventory(r)) for r in rows]
    data = json.loads(raw.decode("utf-8-sig", errors="replace"))
    if shape == "api":
        return [_from_api(v) for v in data if isinstance(v, dict)]
    if shape == "index":
        return [(k, _from_index(k, v)) for k, v in data.items() if isinstance(v, dict)]
    if shape == "descriptions":
        return [(v.get("video_id") or "", _from_descriptions(v)) for v in data if isinstance(v, dict)]
    return []


MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                     "september", "october", "november", "december"], 1)}
TITLE_DATE_RE = re.compile(r"\b(" + "|".join(MONTHS) + r")\s+(\d{1,2}),?\s+(20\d\d)\b", re.I)


def date_in_title(title: str | None) -> str | None:
    """'... | Glory Night October 19, 2026' -> 2026-10-19. The house title format names the service date."""
    m = TITLE_DATE_RE.search(title or "")
    if not m:
        return None
    try:
        return datetime(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).date().isoformat()
    except ValueError:
        return None


def finish(rec: dict) -> dict:
    """Derived fields: the service date (Central), the kind (service, short, video).
    A date in the title wins (a stream is often scheduled a week ahead), then the snapshot's
    service date, then when the stream started, then when it was published."""
    rec["date"] = (date_in_title(rec.get("title")) or rec.get("service_date") or central_date(rec.get("started"))
                   or central_date(rec.get("published")))
    if rec.get("upcoming") and not date_in_title(rec.get("title")):
        rec["date_note"] = "the snapshot was taken before this stream ran: the date is when it was scheduled"
    s = rec.get("seconds")
    t = (rec.get("type") or "").lower()
    if t == "short" or (not t and s and s <= 180 and not rec.get("live")):
        rec["kind"] = "short"
    elif rec.get("live"):
        rec["kind"] = "service"
    else:
        rec["kind"] = "video"
    return rec


def load(cfg: Config) -> dict[str, dict]:
    """{video_id: record}. Each record keeps the snapshot files it came from."""
    base = cfg.repo_dir(AUTOMATION)
    files = [(base / rel, rel, shape) for rel, shape in SOURCES]
    key = tuple((rel, p.stat().st_mtime_ns if p.exists() else 0) for p, rel, _ in files)
    if _cache["key"] == key:
        return _cache["videos"]
    out: dict[str, dict] = {}
    for p, rel, shape in files:
        if not p.exists():
            continue
        try:
            pairs = _read(p, shape)
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        for vid, r in pairs:
            if not vid or not ID_RE.fullmatch(vid):
                continue
            rec = out.setdefault(vid, {"id": vid, "sources": []})
            rec.update(r)
            rec["sources"].append(rel)
    for vid, rec in out.items():
        finish(rec)
    # Shorts and clips name their full service in the description: remember the parent.
    for vid, rec in out.items():
        for m in LINK_RE.finditer(rec.get("description") or ""):
            parent = m.group(1)
            if parent != vid and parent in out:
                rec.setdefault("parent", parent)
                out[parent].setdefault("children", []).append(vid)
                break
    _cache.update(key=key, videos=out)
    return out
