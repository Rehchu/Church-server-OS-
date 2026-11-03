"""Why? (round 8, Q124): one Needs-you item, explained.

For an item on the Overview's Needs-you list this gives the doctor's sentence (what it means and
what to do, in plain words), the last lines of the journal of the unit involved, the audit entries
that match it, and the one fix the dashboard may offer (restart that service, re-run that backup
job, clear that item) where one exists. The fix is only a description of an endpoint that already
exists, with the confirm it already needs; the endpoint keeps its own checks (recent sign-in, never
during a service). Nothing here changes anything.

Rules kept:
  - the journal is read as root only (`journalctl -u <unit> -n 20`), through util.run; never a file,
    never a secret file's content, and a line that looks like `password=...` has its value hidden;
  - the automator never gets a fix: its apply run is the 02:05 timer's alone (CLAUDE.md rule 3);
  - a restart is offered only for the units the Services app manages (services.UNITS).
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Callable

LOG_LINES = 20
AUDIT_LIMIT = 6

# Restarting these two asks for the word first, as the power menu does (restartUnit in app.js).
CONFIRM_WORD = {"samba-ad-dc.service": "domain", "arise-web.service": "dashboard"}

_SECRET_RE = re.compile(r"(?i)\b(pass(?:word|wd|phrase)?|secret|token|api[_-]?key|authorization|cookie)(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)")
_BEARER_RE = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")


def _units() -> dict:
    from . import services
    return dict(services.UNITS)


def _fix_restart(unit: str, label: str = "") -> dict | None:
    units = _units()
    if unit not in units:
        return None
    fix = {"kind": "restart", "label": f"Restart {label or units[unit]}", "method": "POST",
           "path": f"/api/services/{unit}/restart", "body": None}
    if unit in CONFIRM_WORD:
        fix["confirm"] = CONFIRM_WORD[unit]
        fix["note"] = ("The dashboard goes away for a few seconds and the page reloads itself." if unit == "arise-web.service"
                       else "Macs signed in keep working on cached accounts; a sign-in during the restart fails once. About twenty seconds. Refused during a service.")
    return fix


def _backup_job_id(name: str, jobs: list[dict] | None) -> str | None:
    """A backup row names the job by its display name; the run endpoint wants its id."""
    name = (name or "").strip()
    for j in jobs or []:
        if name and name in (j.get("id"), j.get("name")):
            return j.get("id")
    return None


def classify(text: str, jobs: list[dict] | None = None) -> dict:
    """Pure: what an attention line is about. Returns {key, kind, title, unit, sentence, fix, open, audit_q}."""
    t = (text or "").strip()
    out = {"key": "", "kind": "other", "title": "Needs you", "unit": None, "sentence": "", "fix": None, "open": None, "audit_q": ""}

    def put(**kw):
        out.update(kw)
        return out

    m = re.match(r"^(\S+\.(?:service|timer)) is not running\.", t)
    if m:
        unit = m.group(1)
        return put(key=f"service:{unit}", kind="service", title="A service stopped", unit=unit, audit_q=unit, open="services",
                   sentence=f"systemd says {unit} is not active. The last lines of its journal (below) usually say why it stopped; "
                            "a restart is the first thing to try, and if it stops again the journal is the next stop. "
                            "`sudo arisectl doctor` lists it in the same words.",
                   fix=_fix_restart(unit))
    m = re.match(r"^Backup '(.+?)' failed", t)
    if m:
        name = m.group(1)
        job = _backup_job_id(name, jobs)
        return put(key=f"backup:{job or name}", kind="backup", title="A backup failed", unit="arise-backup.service", audit_q="backups", open="backups",
                   sentence=f"The backup job '{name}' ended with an error. The error is in the line above and the journal below; "
                            "a Synology that dropped off the network is the usual cause. Re-running the one job is safe: restic "
                            "picks up where it stopped and nothing already saved is touched.",
                   fix={"kind": "rerun", "label": f"Re-run {name}", "method": "POST", "path": f"/api/backups/run/{job}", "body": None} if job else None)
    if t.startswith("No backup ran last night"):
        return put(key="backup-missed", kind="backup", title="No backup last night", unit="arise-backup.service", audit_q="backups", open="backups",
                   sentence="arise-backup.timer did not leave a result for last night: the box was off, the timer was paused, or the run "
                            "never started. Running every job now is the fix; the 03:00 timer carries on as usual afterwards.",
                   fix={"kind": "rerun", "label": "Run the backup now", "method": "POST", "path": "/api/backups/run", "body": None})
    if t.startswith("Last night's backup didn't reach"):
        rest = t.split(":", 1)[1] if ":" in t else ""
        first = rest.strip().split(" ", 1)[0].strip(",.") if rest.strip() else ""
        job = _backup_job_id(first, jobs) or (first or None)
        return put(key="backup-stale", kind="backup", title="A backup job was missed", unit="arise-backup.service", audit_q="backups", open="backups",
                   sentence="The night ran, but at least one job in backups.yaml has no good snapshot since. Backups shows the error "
                            "for each; re-running the job is safe.",
                   fix={"kind": "rerun", "label": f"Re-run {job}", "method": "POST", "path": f"/api/backups/run/{job}", "body": None} if job else None)
    if t.startswith("Last automator run had failures"):
        return put(key="automator", kind="automator", title="The nightly YouTube job", unit="arise-automator.service", audit_q="automator", open="automator",
                   sentence="The 02:05 run finished with failures; the report in Automator names each one. It tries again tonight on its "
                            "own. Nothing here re-runs it: the apply run is the timer's alone, and Preview is the plan-only run.")
    if "token.json" in t or "YouTube sign-in" in t:
        return put(key="ytauth", kind="automator", title="YouTube sign-in", unit="arise-automator.service", audit_q="automator", open="automator",
                   sentence="The automator signs in to the channel with token.json. It is renewed from the Media Mac (Automator → Sign-in), "
                            "never typed or pasted here. Until it is, the 02:05 job can't read or change the channel.")
    if t.startswith("Synology not mounted"):
        return put(key="nas", kind="nas", title="The Synology", unit="arise-nas-mount.service", audit_q="nas", open="backups",
                   sentence="/mnt/synology is not mounted, so tonight's backup has nowhere to go. Restarting the mount service tries "
                            "the share again; if it fails, the journal says whether the Synology is off, asleep or refusing the password.",
                   fix=_fix_restart("arise-nas-mount.service", "the Synology mount"))
    if t.startswith("Directory:"):
        return put(key="directory", kind="directory", title="The domain", unit="samba-ad-dc.service", audit_q="directory", open="directory",
                   sentence="The domain controller did not answer the way it should. Macs keep working on cached accounts meanwhile. "
                            "The journal below is the domain's; a restart is the one fix offered here, and it is refused during a service.",
                   fix=_fix_restart("samba-ad-dc.service", "the domain"))
    if t.startswith("No admin password set"):
        return put(key="admin-password", kind="setup", title="Sign-in", unit="arise-web.service", audit_q="auth",
                   sentence="The dashboard has no administrator password yet. It is set at the server itself: sudo arisectl admin set-password.")
    if t.startswith("STAGING"):
        return put(key="staging", kind="setup", title="This box", unit=None, audit_q="",
                   sentence="The box is not at the church yet (--staging): the domain listens on this box only and no network scan runs. "
                            "That is on purpose. install.sh at the church relocates it; nothing to fix here.")
    if t.startswith("No config at"):
        return put(key="config", kind="setup", title="This box", unit="arise-web.service", audit_q="settings",
                   sentence="There is no /etc/arise/arise.toml, so the dashboard runs on defaults and sample data. The installer writes it.")
    if t.startswith("The Mac helper is in watch mode"):
        return put(key="macs-watch", kind="macs", title="The Mac helper", unit="arise-web.service", audit_q="macs", open="macs",
                   sentence="The church Macs report in, but the helper only watches: the tasks queued for them wait until you read "
                            "them in Macs and press Switch on (it asks the password again). Nothing runs on a Mac before that.")
    m = re.match(r"^(.+?)'s disk is (\d+)% full", t)
    if m:
        return put(key=f"mac-disk:{m.group(1)}", kind="macs", title="A church Mac's disk", unit="arise-web.service", audit_q="macs", open="macs",
                   sentence=f"{m.group(1)} told the helper its disk is {m.group(2)}% full. The Mac starts to struggle past 90%: "
                            "emptying its Trash and Downloads on the Mac itself is the fix. Nothing here deletes a file on a Mac.")
    m = re.match(r"^(.+?) (?:has not|hasn't) checked in", t)
    if m:
        return put(key=f"mac-silent:{m.group(1)}", kind="macs", title="A silent Mac", unit="arise-web.service", audit_q="macs", open="macs",
                   sentence=f"{m.group(1)} has not called in. It is off, asleep, away from the church network and Tailscale, or gone; "
                            "if it is gone for good, Retire it in Macs.")
    m = re.match(r"^(.+?): the helper has no Full Disk Access", t)
    if m:
        return put(key=f"mac-fda:{m.group(1)}", kind="macs", title="Full Disk Access", unit="arise-web.service", audit_q="macs", open="macs",
                   sentence=f"The helper on {m.group(1)} cannot read the profile folders until it has Full Disk Access: on that Mac, "
                            "System Settings → Privacy & Security → Full Disk Access → turn on arise-helper.")
    m = re.match(r"^(/\S*) is (\d+)% full", t)
    if m:
        return put(key=f"disk:{m.group(1)}", kind="disk", title="A disk filling up", unit=None, audit_q="storage", open="storage",
                   sentence=f"{m.group(1)} is {m.group(2)}% full. Storage shows what is eating it; past 90% backups and uploads start failing.")
    if t.startswith("Replace the disk"):
        return put(key="disk-health", kind="disk", title="A disk to replace", unit="smartd.service", audit_q="storage", open="storage",
                   sentence="SMART says this disk is wearing out. The nightly backups are the safety net until it is replaced; "
                            "order the replacement now rather than after it dies.")
    if t.startswith("The CPU is at"):
        return put(key="cpu-hot", kind="hardware", title="The CPU is hot", unit=None, audit_q="",
                   sentence="The processor is running hot. Check the closet door is not shut on it, the fans turn and the vents are clear.")
    if t.startswith("Audit log write failed"):
        return put(key="audit-write", kind="audit", title="The audit log", unit="arise-web.service", audit_q="",
                   sentence="The dashboard could not write to the audit log. Check the disk is not full and the arise-web journal below.")
    return put(key="item:" + hashlib.sha1(t.encode("utf-8")).hexdigest()[:10], kind="other", title="Needs you",
               sentence="This line comes from a part of the server without its own explanation yet. `sudo arisectl doctor` gives the same line with its context.")


# The preview's journals: believable, and nobody's real log (sample mode only).
SAMPLE_LOGS = {
    "macs": "\n".join([
        "2026-11-03T08:01:12-06:00 arise-server arise-web[812]: INFO macs: MEDIA-MAC checked in (helper 0.8.2, disk 54%, watch mode)",
        "2026-11-03T08:03:40-06:00 arise-server arise-web[812]: INFO macs: OFFICE-MAC checked in (helper 0.8.2, disk 61%, watch mode)",
        "2026-11-03T08:05:02-06:00 arise-server arise-web[812]: INFO macs: KIDS-MAC checked in (helper 0.8.2, disk 91%, watch mode)",
        "2026-11-03T08:05:02-06:00 arise-server arise-web[812]: WARNING macs: KIDS-MAC: no Full Disk Access; profile removal held",
        "2026-11-03T08:05:03-06:00 arise-server arise-web[812]: INFO macs: 4 task(s) queued, held by watch mode",
        "2026-11-03T08:06:12-06:00 arise-server arise-web[812]: INFO macs: MEDIA-MAC checked in (helper 0.8.2, disk 54%, watch mode)",
        "2026-11-03T08:08:40-06:00 arise-server arise-web[812]: INFO macs: OFFICE-MAC checked in (helper 0.8.2, disk 61%, watch mode)",
        "2026-11-03T08:10:02-06:00 arise-server arise-web[812]: INFO macs: KIDS-MAC checked in (helper 0.8.2, disk 91%, watch mode)",
    ]),
    "backup": "\n".join([
        "2026-11-03T03:00:01-06:00 arise-server systemd[1]: Starting arise-backup.service - Arise backups to the Synology...",
        "2026-11-03T03:00:02-06:00 arise-server arise-backup[20311]: job homes: restic backup /srv/arise/homes",
        "2026-11-03T03:09:44-06:00 arise-server arise-backup[20311]: job homes: snapshot 4be1c0a2 saved (1,204 new files)",
        "2026-11-03T03:09:45-06:00 arise-server arise-backup[20311]: job shares: restic backup /srv/arise/shares",
        "2026-11-03T03:11:02-06:00 arise-server arise-backup[20311]: job shares: Fatal: unable to open repository at /mnt/synology/restic: no such file or directory",
        "2026-11-03T03:11:02-06:00 arise-server arise-backup[20311]: job shares: failed (exit 1)",
        "2026-11-03T03:11:03-06:00 arise-server systemd[1]: arise-backup.service: Main process exited, code=exited, status=1/FAILURE",
    ]),
    "service": "\n".join([
        "2026-11-03T06:41:10-06:00 arise-server systemd[1]: Stopping the service...",
        "2026-11-03T06:41:12-06:00 arise-server systemd[1]: Main process exited, code=killed, status=9/KILL",
        "2026-11-03T06:41:12-06:00 arise-server systemd[1]: Failed with result 'signal'.",
    ]),
}


def redact(line: str) -> str:
    """Pure: hide the value after anything that looks like a credential's name."""
    line = _BEARER_RE.sub(lambda m: f"{m.group(1)} •••", line or "")
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}•••", line)


def journal_tail(unit: str | None, run: Callable | None = None, root: bool | None = None, demo: bool = False,
                 lines: int = LOG_LINES, kind: str = "") -> tuple[list[str], str]:
    """The last lines of the unit's journal and a note. Root only; never a file."""
    if not unit:
        return [], "No single service is behind this one, so there is no journal to show."
    from . import services
    if unit not in _units() and not services.READABLE_RE.match(unit):
        return [], f"{unit} is not a unit the dashboard reads."
    if demo:
        from . import demo as _demo
        text = SAMPLE_LOGS.get(kind) or _demo.LOGS.get(unit) or ""
        got = [redact(x) for x in text.splitlines() if x.strip()][-lines:]
        return got, "" if got else f"(sample) no journal lines for {unit} in the preview."
    if root is None:
        root = hasattr(os, "geteuid") and os.geteuid() == 0
    if not root:
        return [], "The journal is read as root only; this dashboard is not running as root, so `journalctl -u " + unit + "` on the box shows it."
    if run is None:
        from .util import run as run
    r = run(["journalctl", "-u", unit, "-n", str(int(lines)), "--no-pager", "-o", "short-iso"], timeout=15)
    text = r.get("out") or ""
    got = [redact(x) for x in text.splitlines() if x.strip() and not x.startswith("-- ")][-lines:]
    if not got:
        return [], (r.get("err") or "").strip()[:200] or f"journalctl had nothing for {unit}."
    return got, ""


def audit_matches(q: str, search: Callable | None = None, limit: int = AUDIT_LIMIT) -> list[dict]:
    if not q:
        return []
    if search is None:
        from . import audit
        search = audit.recent
    try:
        rows = search(limit=limit, q=q).get("events", [])
    except Exception:  # noqa: BLE001 - the audit log is a nice-to-have here, never a reason to fail
        return []
    return [{k: e.get(k) for k in ("t", "who", "action", "target", "ok")} for e in rows[:limit]]


def summary(items: list[dict], jobs: list[dict] | None = None) -> list[dict]:
    """Pure: the Needs-you list with each item's key and title, for the client."""
    out = []
    for it in items:
        c = classify(it.get("text", ""), jobs)
        out.append({"key": c["key"], "level": it.get("level", "warn"), "text": it.get("text", ""), "title": c["title"],
                    "kind": c["kind"], "unit": c["unit"], "has_fix": bool(c["fix"])})
    return out


def explain(key: str, items: list[dict], *, jobs: list[dict] | None = None, run: Callable | None = None,
            root: bool | None = None, search: Callable | None = None, demo: bool = False) -> dict:
    """GET /api/why?key=...: the item whose key (or text) is `key`, explained. No key: the list with keys."""
    if not key:
        return {"ok": True, "demo": demo, "items": summary(items, jobs)}
    for it in items:
        c = classify(it.get("text", ""), jobs)
        if key in (c["key"], it.get("text")):
            log, note = journal_tail(c["unit"], run=run, root=root, demo=demo, kind=c["kind"])
            return {"ok": True, "demo": demo, "key": c["key"], "level": it.get("level", "warn"), "text": it.get("text", ""),
                    "title": c["title"], "kind": c["kind"], "sentence": c["sentence"], "unit": c["unit"],
                    "log": log, "log_note": note, "audit": audit_matches(c["audit_q"], search), "fix": c["fix"], "open": c["open"]}
    return {"ok": False, "demo": demo, "key": key, "err": "That item is not on the Needs-you list any more: it may have cleared itself. Reopen Overview to see the list as it is now."}
