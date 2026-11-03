"""The sample server's memory: what a click changes in demo mode.

Demo mode used to answer every change with {"ok": true, "demo": true} and
change nothing, so a user created in the sample never appeared in the list
(Bradly, Oct 28: "some didn't work in the Artifact like user creation,
Enabling/Disabling"). Every module's demo branch now reads and writes the
lists here instead: deep copies of the seeds in demo.py, kept in memory for
the life of the process. Nothing is written to disk, so a sample server can
never touch /srv, /etc or the Synology.

POST /api/demo/reset (demo mode only) puts everything back.
"""
from __future__ import annotations

import copy
import threading

_lock = threading.RLock()
_store: dict = {}
_hooks: list = []


def get(key: str, seed):
    """The live copy for `key`, made from `seed` (a value or a callable) the first time."""
    with _lock:
        if key not in _store:
            _store[key] = copy.deepcopy(seed() if callable(seed) else seed)
        return _store[key]


def put(key: str, value):
    with _lock:
        _store[key] = value
        return value


def on_reset(fn):
    """Modules that keep their own sample dicts register a function that clears them."""
    if fn not in _hooks:
        _hooks.append(fn)
    return fn


def reset() -> dict:
    with _lock:
        _store.clear()
        for fn in list(_hooks):
            try:
                fn()
            except Exception:  # noqa: BLE001 - a reset must finish
                pass
    return {"ok": True, "demo": True, "out": "sample data put back"}
