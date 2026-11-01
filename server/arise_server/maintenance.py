"""Cross-process exclusion for backups, app changes and software updates."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

from .config import load

_local = threading.local()


class MaintenanceBusy(RuntimeError):
    pass


@contextmanager
def exclusive(kind: str):
    """Reentrant in the same thread; other processes/threads fail without waiting."""
    cfg = load()
    if cfg.demo:
        yield
        return
    if getattr(_local, "owner", None) == (os.getpid(), str(cfg.state_dir)):
        yield
        return
    import fcntl
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    with (cfg.state_dir / "maintenance.lock").open("a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise MaintenanceBusy(f"{kind} deferred: another backup, app change or update is running") from e
        _local.owner = (os.getpid(), str(cfg.state_dir))
        try:
            yield
        finally:
            _local.owner = None
            fcntl.flock(f, fcntl.LOCK_UN)


def guarded(kind: str):
    def decorate(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                with exclusive(kind):
                    return fn(*args, **kwargs)
            except MaintenanceBusy as e:
                return {"ok": False, "err": str(e), "summary": str(e), "deferred": True}
        return wrapper
    return decorate


def backup_budget(max_seconds: int = 6 * 3600, now: datetime | None = None) -> int:
    """Leave ten minutes for cleanup/app restart before the next service.

    Running restic is allowed to finish up to this deadline, then its normal
    timeout aborts it and the caller's finally restarts apps. Never SIGSTOP a
    backup with databases stopped. A new calendar change cannot retroactively
    change an already running subprocess timeout.
    """
    from . import church, calendar
    now = now or datetime.now()
    if church.in_service_now(now):
        raise MaintenanceBusy("backup deferred: a service is running")
    starts = []
    nxt = church.next_service(now)
    if nxt:
        starts.append(datetime.fromisoformat(nxt["at"]))
    for event in calendar.events():
        if not event.get("is_service"):
            continue
        try:
            start = datetime.fromisoformat(event["start"])
            if start.tzinfo is not None:
                start = start.astimezone().replace(tzinfo=None)
            if start > now:
                starts.append(start)
        except (KeyError, ValueError, TypeError):
            continue
    seconds = min([max_seconds] + [int((start - now).total_seconds()) - 600 for start in starts])
    if seconds < 1800:
        raise MaintenanceBusy("backup deferred: fewer than 30 minutes remain before service cleanup time")
    return seconds


def main(argv=None):
    """systemd unattended-upgrade wrapper: no shell and no automatic retries."""
    from .church import in_service_now
    command = list(sys.argv[1:] if argv is None else argv)
    if not command:
        print("a maintenance command is required", file=sys.stderr)
        return 2
    if in_service_now():
        print("maintenance deferred: a service is running", file=sys.stderr)
        return 1
    try:
        with exclusive("system maintenance"):
            return subprocess.run(command, check=False).returncode
    except MaintenanceBusy as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
