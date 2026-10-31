"""The channel, as the server sees it: the automator's channel_inventory.csv.

No quota is spent. Thumbnails come from i.ytimg.com, which is free.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime

from .config import load

CHANNEL = "UCGS9j7B_prcJkbTNgzlGrKg"
PLAYLISTS = [
    {"id": "PLa-Nxr2f-qHY", "title": "Apostle Bryant Sanders — Messages"}, {"id": "PLeDfl1m-bAzo", "title": "Pastor Vanessa Sanders — Messages"},
    {"id": "PLYhdT3QigNmY", "title": "Glory Nights"}, {"id": "PLWJRS0iEv_vk", "title": "Conferences & Special Events"},
    {"id": "PLAUiV-2ZIEuI", "title": "Guest Ministers"}, {"id": "PLb-9QSfkRhnFuQ2axOL8I1Tz4pwZ1Th2n", "title": "Praise Team Songs"},
]
SAMPLE = [
    {"id": "QwF6-Sdrxoo", "title": "WHOSE HAND IS IT IN? | Minister Herbert Perry", "published": "2026-10-26", "kind": "Sunday Service", "speaker": "Minister Herbert Perry", "views": 412, "duration": "1:48:12"},
    {"id": "rKjR2PYdJUg", "title": "GLORY NIGHT | October 20, 2026", "published": "2026-10-20", "kind": "Glory Night", "speaker": "Apostle Bryant Sanders", "views": 188, "duration": "1:31:04"},
    {"id": "vjgfF0hdoyY", "title": "EXERCISING OUR SPIRITUAL SENSES | Apostle Bryant Sanders", "published": "2026-10-04", "kind": "Sunday Service", "speaker": "Apostle Bryant Sanders", "views": 530, "duration": "2:01:40"},
    {"id": "dhy1VW5ZnpQ", "title": "GLORY NIGHT | October 5, 2026", "published": "2026-10-05", "kind": "Glory Night", "speaker": "Pastor Vanessa Sanders", "views": 164, "duration": "1:26:55"},
    {"id": "GfTvURWWlLg", "title": "THE GOD KIND OF FAITH | Apostle Bryant Sanders", "published": "2026-09-27", "kind": "Sunday Service", "speaker": "Apostle Bryant Sanders", "views": 601, "duration": "1:55:18"},
    {"id": "MnXmccLS2p8", "title": "GLORY NIGHT | September 28, 2026", "published": "2026-09-28", "kind": "Glory Night", "speaker": "Apostle Bryant Sanders", "views": 142, "duration": "1:22:09"},
    {"id": "m_bDPBzAGUE", "title": "Declare: Last Year Was the Last Year I Lived Paycheck to Paycheck", "published": "2026-09-12", "kind": "Short", "speaker": "", "views": 2210, "duration": "0:48"},
    {"id": "BNCJUUBlRis", "title": "Don't Pick Battles God Didn't Give You", "published": "2026-09-11", "kind": "Short", "speaker": "", "views": 1740, "duration": "0:52"},
]


def _inventory_path() -> str:
    return os.path.join(load().automator.path, "channel_inventory.csv")


def _kind(title: str, duration: str) -> str:
    t = (title or "").lower()
    if "glory night" in t:
        return "Glory Night"
    if "conference" in t or "camp" in t:
        return "Conference"
    try:
        parts = [int(x) for x in (duration or "0:0").split(":")]
        secs = sum(p * 60 ** i for i, p in enumerate(reversed(parts)))
    except ValueError:
        secs = 0
    if secs and secs <= 180:
        return "Short"
    return "Sunday Service"


def videos(limit: int = 60) -> dict:
    cfg = load()
    p = _inventory_path()
    if cfg.demo or not os.path.exists(p):
        rows = SAMPLE
        return {"demo": True, "channel": CHANNEL, "handle": "@arisechurch4147", "count": 1022, "playlists": PLAYLISTS, "videos": rows[:limit], "source": "sample"}
    rows = []
    try:
        with open(p, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                vid = r.get("id") or r.get("video_id") or r.get("videoId") or ""
                if len(vid) != 11:
                    continue
                dur = r.get("duration") or r.get("length") or ""
                rows.append({"id": vid, "title": r.get("title", ""), "published": (r.get("published") or r.get("publishedAt") or "")[:10],
                             "kind": r.get("kind") or _kind(r.get("title", ""), dur), "speaker": r.get("speaker", ""), "views": int(r.get("views") or r.get("viewCount") or 0), "duration": dur, "privacy": r.get("privacy") or r.get("privacyStatus") or ""})
    except (OSError, csv.Error) as e:
        return {"demo": True, "error": str(e)[:200], "channel": CHANNEL, "handle": "@arisechurch4147", "playlists": PLAYLISTS, "videos": SAMPLE[:limit]}
    rows.sort(key=lambda x: x["published"], reverse=True)
    return {"demo": False, "channel": CHANNEL, "handle": "@arisechurch4147", "count": len(rows), "playlists": PLAYLISTS, "videos": rows[:limit],
            "source": p, "updated": datetime.fromtimestamp(os.path.getmtime(p)).isoformat(timespec="minutes")}
