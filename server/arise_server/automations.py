"""Automations: every arise-* timer, live. Next run, last run and its result,
pause and resume, in plain words (round 3, 8). The real automator run stays
refused while its timer is on (CLAUDE.md rule 3); Preview is the dry run."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from .config import load
from .util import run, which

# What each unit does, for people. The timer name is the key.
WHAT = {
    "arise-automator.timer": ("The nightly YouTube job", "02:05: tidies descriptions, tags, chapters and playlists on the channel within the day's quota. Preview is the dry run; the real run is this timer's alone."),
    "arise-backup.timer": ("Backups to the Synology", "03:00: every restic job in backups.yaml, then prune to 30 daily, 12 weekly, 24 monthly."),
    "arise-mirror.timer": ("GitHub mirror", "04:00: refreshes the bare mirrors of the church's repositories under /srv/arise/backups/github-mirror."),
    "arise-notify.timer": ("The daily note", "07:00: a Discord/Slack note of what needs you. Off until a webhook is set (Bradly: no daily note)."),
    "arise-devices.timer": ("The network scan", "Hourly: who is on the switch; new devices show in the Network app. Does not run in staging."),
    "arise-drill.timer": ("The restore drill", "Monthly: one random file restored from last night's backup to a scratch folder and compared."),
    "arise-update.timer": ("Software updates", "Saturday 03:30: installs what Bradly queued in Software Update, after a system snapshot; reboots only if the kernel asks and no service is on."),
    "arise-monitor-off.timer": ("Monitor off", "23:00: the closet panel goes to sleep."),
    "arise-monitor-on.timer": ("Monitor on", "06:00: the closet panel wakes."),
    "arise-trash.timer": ("Empty old Trash", "Daily: anything in a share's Trash older than 30 days is removed."),
    "arise-weekly.timer": ("The Monday report", "Monday 07:30: backups, storage, Macs, sign-ins, updates and the channel's numbers to Discord #weekly."),
    "arise-lyrics-inbox.timer": ("The Lyrics inbox", "Every 15 minutes: lyrics files dropped into Nextcloud's Lyrics inbox go into the Songs tab."),
    "arise-ccli.timer": ("The CCLI report", "Each quarter: what was sung and how often, from the set lists, for CCLI."),
    "arise-channel-copy.timer": ("The channel copy", "04:45: a copy of the channel's titles, descriptions and thumbnails, from the automator's own files (no quota)."),
    "arise-speedtest.timer": ("Internet speed", "Hourly: the line's speed, charted in Activity Monitor → Network; never during a service."),
    "arise-idle-apps.timer": ("Idle desktop apps", "Every 15 minutes: a desktop program from the Store (GIMP, LibreOffice...) nobody has used for an hour is stopped to free its memory."),
    "arise-clamscan.timer": ("Virus scan", "Sunday night: ClamAV over the shares; anything found is quarantined and reported."),
    "fstrim.timer": ("SSD trim", "Weekly: tells the SSD which blocks are free."),
    "apt-daily-upgrade.timer": ("Security patches", "Daily: unattended-upgrades installs security updates only, never a reboot."),
}
NEVER = "Never during a service: Sundays 10:30 (Pineville) and 10:00 (Alexandria), Mondays 19:00 Glory Night."


def available() -> bool:
    return bool(which("systemctl")) and not load().demo


def parse_timers_json(text: str) -> list[dict]:
    """`systemctl list-timers --all --output=json` → rows we keep (arise-* and the two system ones)."""
    try:
        rows = json.loads(text or "[]")
    except json.JSONDecodeError:
        return []
    out = []
    for r in rows:
        unit = r.get("unit", "")
        if not (unit.startswith("arise-") or unit in ("fstrim.timer", "apt-daily-upgrade.timer")):
            continue
        out.append({"timer": unit, "service": r.get("activates") or unit.replace(".timer", ".service"),
                    "next": _us(r.get("next")), "last": _us(r.get("last")), "left": r.get("left"), "passed": r.get("passed")})
    return out


def _us(v):
    """systemd gives microseconds since the epoch (or null/0/'n/a')."""
    if not v or v in ("n/a", "-"):
        return None
    try:
        return datetime.fromtimestamp(int(v) / 1_000_000).isoformat(timespec="seconds")
    except (ValueError, TypeError, OSError):
        return None


def describe(timer: str) -> tuple[str, str]:
    return WHAT.get(timer, (timer.replace(".timer", "").replace("arise-", "").replace("-", " ").capitalize(), "A timer on this box."))


def list_automations() -> dict:
    if not available():
        from . import demo_state
        return {"demo": True, "never": NEVER, "timers": demo_state.get("timers", _demo)}
    r = run(["systemctl", "list-timers", "--all", "--no-pager", "--output=json"], timeout=15)
    rows = parse_timers_json(r["out"])
    out = []
    for row in rows:
        name, what = describe(row["timer"])
        en = run(["systemctl", "is-enabled", row["timer"]], timeout=5)["out"].strip()
        act = run(["systemctl", "is-active", row["timer"]], timeout=5)["out"].strip()
        sh = run(["systemctl", "show", row["service"], "-p", "Result,ExecMainStatus,ExecMainExitTimestamp,ActiveState,SubState", "--no-pager"], timeout=10)
        props = dict(l.partition("=")[::2] for l in sh["out"].splitlines() if "=" in l)
        out.append({**row, "name": name, "what": what, "enabled": en in ("enabled", "static"), "state": en or "unknown", "active": act,
                    "result": props.get("Result", ""), "exit": props.get("ExecMainStatus", ""), "running": props.get("ActiveState") == "active",
                    "last_ok": (props.get("Result") == "success") if row["last"] else None})
    return {"demo": False, "never": NEVER, "timers": out}


def pause(timer: str, on: bool, confirm: str) -> dict:
    """Pause = disable --now; Resume = enable --now. Only arise-* timers, and the confirm word is the timer name."""
    if not timer.startswith("arise-") or not timer.endswith(".timer") or "/" in timer:
        return {"ok": False, "err": "only arise-* timers can be paused here"}
    if confirm != timer:
        return {"ok": False, "err": "type the timer name to confirm"}
    if not available():
        from . import demo_state
        t = next((x for x in demo_state.get("timers", _demo) if x["timer"] == timer), None)
        if not t:
            return {"ok": False, "err": f"no timer called {timer}"}
        t.update({"enabled": bool(on), "state": "enabled" if on else "disabled", "active": "active" if on else "inactive"})
        if not on:
            t["next"] = None
        return {"ok": True, "demo": True, "enabled": bool(on), "out": f"(sample) {timer} {'resumed' if on else 'paused'}"}
    r = run(["systemctl", "enable" if on else "disable", "--now", timer], timeout=30)
    if not r["ok"]:
        return {"ok": False, "err": f"systemctl {'enable' if on else 'disable'} --now {timer}: " + ((r["err"] or r["out"]).strip()[:300] or f"exit {r['code']}")}
    return {"ok": True, "enabled": bool(on), "out": f"{timer} {'resumed' if on else 'paused'}"}


def _demo() -> list[dict]:
    now = datetime.now()
    def at(h, m, days=0):
        d = now.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=days)
        return d.isoformat(timespec="seconds")
    def last(h, m):
        d = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if d > now:
            d -= timedelta(days=1)
        return d.isoformat(timespec="seconds")
    rows = []
    for timer, h, m, ok in (("arise-automator.timer", 2, 5, True), ("arise-backup.timer", 3, 0, True), ("arise-mirror.timer", 4, 0, True), ("arise-devices.timer", (now.hour + 1) % 24, 0, True), ("arise-notify.timer", 7, 0, None), ("arise-drill.timer", 3, 30, True), ("arise-update.timer", 3, 30, True), ("arise-monitor-off.timer", 23, 0, True), ("arise-monitor-on.timer", 6, 0, True), ("fstrim.timer", 0, 0, True), ("apt-daily-upgrade.timer", 6, 20, True)):
        name, what = describe(timer)
        nxt = at(h, m, 1 if now.replace(hour=h, minute=m) <= now else 0)
        if timer == "arise-update.timer":
            nxt = (now + timedelta(days=(5 - now.weekday()) % 7 or 7)).replace(hour=3, minute=30, second=0, microsecond=0).isoformat(timespec="seconds")
        if timer == "arise-drill.timer":
            nxt = (now.replace(day=1) + timedelta(days=32)).replace(day=1, hour=3, minute=30, second=0, microsecond=0).isoformat(timespec="seconds")
        rows.append({"timer": timer, "service": timer.replace(".timer", ".service"), "name": name, "what": what, "next": nxt, "last": None if ok is None else last(h, m),
                     "enabled": ok is not None, "state": "enabled" if ok is not None else "disabled", "active": "active" if ok is not None else "inactive", "result": "success" if ok else "", "exit": "0" if ok else "", "running": False, "last_ok": ok})
    return rows
