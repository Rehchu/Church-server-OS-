"""Sign-in PINs (round 7, rows 160 to 162; docs/ANSWERS.md).

Bradly, Oct 29: "Can we setup pin codes for the dashboard? so we don't have to do a full
login?" Each person sets their own PIN, 4 to 8 digits, after typing their full password.

- Admins (160): the PIN signs in anywhere the dashboard answers (church Wi-Fi, Tailscale).
- Staff (162): the PIN is for the phone checklist page, on the phone they set it on: a
  random device mark (a cookie) is bound to it, and a PIN session reaches the checklist only.
- Never by PIN (161): the password-again clicks still ask for the real password. A PIN
  session carries no "recently typed the password" stamp, and /api/auth/reauth checks the
  password, never a PIN.

Guessing: the device that guesses waits (auth.too_many, by address, as for passwords), and
ten wrong PINs for one account, from any devices, switch that account's PIN off until its
next full-password sign-in. The password always keeps working: no lockout (round 4, 27).
A password change, a reset, disabling or deleting the account switches the PIN off too.

On disk: /var/lib/arise/pins.json, 0600, a bcrypt hash per person and the device marks'
sha256. Never the PIN, never logged, never in an answer.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

from .config import load

PIN_RE = re.compile(r"^\d{4,8}$")
WRONG_MAX = 10           # wrong PINs for one account, any devices, before its PIN switches off
ROUNDS = 10              # bcrypt cost: about 80 to 100 ms a check on the OptiPlex
DEVICE_COOKIE = "arise_pin_device"
DEVICE_DAYS = 400
_lock = threading.Lock()
# The PINs people choose most often (and the keypad's columns), refused whatever the rules below say.
COMMON = {"1234", "1111", "1212", "7777", "1004", "2000", "4444", "2222", "6969", "9999", "3333", "5555",
          "6666", "1122", "1313", "8888", "4321", "2001", "1010", "2580", "0852", "1470", "0741", "3690", "0963",
          "1379", "9731", "123456", "654321", "121212", "112233", "147258", "159753", "123123", "696969"}
# A dummy hash so a name with no PIN costs the same time as one with a wrong PIN.
_DUMMY = None


def _path() -> Path:
    return Path(load().state_dir) / "pins.json"


def _read() -> dict:
    import json
    try:
        return json.loads(_path().read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def _write(d: dict) -> None:
    import json
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ----- the rules (pure) -------------------------------------------------------------------
def _runs(pin: str) -> bool:
    """Every digit one more (or one less) than the last: 1234, 4321, 0123, 34567."""
    d = [int(c) for c in pin]
    steps = {d[i + 1] - d[i] for i in range(len(d) - 1)}
    return steps in ({1}, {-1})


def _repeats(pin: str) -> bool:
    """One digit, or one short chunk again and again: 1111, 1212, 121212, 123123."""
    if len(set(pin)) == 1:
        return True
    for n in (1, 2, 3, 4):
        if len(pin) % n == 0 and len(pin) > n and pin == pin[:n] * (len(pin) // n):
            return True
    return False


def weak_reason(pin: str, birthday: str = "", mobile: str = "") -> str:
    """Pure: why this PIN is refused, or "" when it is fine."""
    pin = str(pin or "")
    if not PIN_RE.match(pin):
        return "A PIN is 4 to 8 digits, nothing else."
    if _repeats(pin):
        return "That PIN repeats itself (like 1111 or 1212). Choose digits that don't follow a pattern."
    if _runs(pin):
        return "That PIN counts up or down (like 1234). Choose digits that don't follow a pattern."
    if pin in COMMON:
        return "That is one of the PINs people choose most often. Choose another."
    m = re.match(r"^(\d{1,2})-(\d{1,2})$", str(birthday or "").strip())
    if m:
        mm, dd = f"{int(m.group(1)):02d}", f"{int(m.group(2)):02d}"
        if pin in (mm + dd, dd + mm):
            return "That PIN is your birthday. Choose something people can't look up."
    digits = re.sub(r"\D", "", str(mobile or ""))
    if len(digits) >= 4 and pin == digits[-len(pin):]:
        return "That PIN is the end of your mobile number. Choose something people can't look up."
    return ""


def _hash(pin: str) -> str:
    import bcrypt
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=ROUNDS)).decode()


def _check(pin: str, hashed: str) -> bool:
    import bcrypt
    try:
        return bcrypt.checkpw(str(pin or "").encode(), hashed.encode())
    except ValueError:
        return False


def _dummy_check(pin: str) -> None:
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = _hash("".join(secrets.choice("0123456789") for _ in range(6)))
    _check(pin, _DUMMY)


def _dev_hash(mark: str) -> str:
    return hashlib.sha256(("arise-pin-device:" + (mark or "")).encode()).hexdigest()


# ----- what a person sees ------------------------------------------------------------------
def status(user: str, device_mark: str = "") -> dict:
    """Never the hash: whether a PIN is set, its reach, and whether it is switched off."""
    r = _read().get((user or "").lower())
    if not r:
        return {"set": False}
    out = {"set": True, "scope": r.get("scope", "full"), "since": r.get("set"), "off": bool(r.get("off")),
           "reason": r.get("reason", "") if r.get("off") else "", "wrong": int(r.get("wrong", 0))}
    if r.get("scope") == "checklist":
        out["this_device"] = bool(device_mark) and hmac.compare_digest(_dev_hash(device_mark), r.get("device", ""))
    return out


def set_pin(user: str, pin: str, scope: str, birthday: str = "", mobile: str = "") -> dict:
    """Set or change. scope "full" (an admin) or "checklist" (staff: bound to this device).
    Returns the device mark to put in a cookie for a checklist PIN; never the PIN."""
    user = (user or "").strip().lower()
    why = weak_reason(pin, birthday, mobile)
    if why:
        return {"ok": False, "err": why}
    if scope not in ("full", "checklist"):
        return {"ok": False, "err": "scope is full or checklist"}
    rec = {"hash": _hash(pin), "scope": scope, "set": _now(), "wrong": 0, "off": False}
    mark = ""
    if scope == "checklist":
        mark = secrets.token_urlsafe(24)
        rec["device"] = _dev_hash(mark)
    with _lock:
        d = _read()
        d[user] = rec
        _write(d)
    from . import audit
    audit.record(user, "auth.pin.set", detail=f"{scope}{' (this phone)' if scope == 'checklist' else ''}")
    return {"ok": True, "scope": scope, "device_mark": mark}


def remove(user: str, by: str = "") -> dict:
    user = (user or "").strip().lower()
    with _lock:
        d = _read()
        had = d.pop(user, None)
        if had is not None:
            _write(d)
    from . import audit
    audit.record(by or user, "auth.pin.remove", user if by and by != user else "", ok=had is not None,
                 detail="removed by an admin" if by and by != user else "")
    return {"ok": True, "removed": had is not None}


def switch_off(user: str, reason: str) -> None:
    """A password change, a reset, a disabled account: the PIN waits for a full sign-in."""
    user = (user or "").strip().lower()
    with _lock:
        d = _read()
        r = d.get(user)
        if not r or r.get("off"):
            return
        r["off"], r["reason"] = True, reason
        _write(d)


def full_signin(user: str) -> None:
    """A full-password sign-in clears the wrong count and switches the PIN back on."""
    user = (user or "").strip().lower()
    with _lock:
        d = _read()
        r = d.get(user)
        if not r or (not r.get("off") and not r.get("wrong")):
            return
        r["off"], r["wrong"], r["reason"] = False, 0, ""
        _write(d)


def verify(user: str, pin: str, device_mark: str = "") -> dict:
    """{ok, scope} or {ok: False, err, off?}. Counts a wrong PIN against the account; the tenth
    switches its PIN off (and tells Bradly). Constant time against a name with no PIN."""
    user = (user or "").strip().lower()
    generic = {"ok": False, "err": "Wrong PIN, or no PIN is set for that name. Your password always works."}
    rec = _read().get(user)
    if not rec or not PIN_RE.match(str(pin or "")):
        _dummy_check(str(pin or "-"))
        return generic
    if rec.get("off"):
        _dummy_check(pin)
        return {"ok": False, "off": True, "err": f"The PIN for {user} is switched off ({rec.get('reason') or 'too many wrong PINs'}). Sign in with your password; that switches it back on."}
    good = _check(pin, rec.get("hash", ""))
    if good and rec.get("scope") == "checklist":
        good = bool(device_mark) and hmac.compare_digest(_dev_hash(device_mark), rec.get("device", ""))
        if not good:
            return {"ok": False, "err": "This PIN works on the phone it was set on. Sign in with your password here."}
    if good:
        if rec.get("wrong"):
            with _lock:
                d = _read()
                if user in d:
                    d[user]["wrong"] = 0
                    _write(d)
        return {"ok": True, "scope": rec.get("scope", "full")}
    tripped = False
    with _lock:
        d = _read()
        r = d.get(user)
        if r:
            r["wrong"] = int(r.get("wrong", 0)) + 1
            if r["wrong"] >= WRONG_MAX and not r.get("off"):
                r["off"], r["reason"], tripped = True, f"{WRONG_MAX} wrong PINs", True
            _write(d)
    if tripped:
        _tell(user)
        return {"ok": False, "off": True, "err": f"{WRONG_MAX} wrong PINs: the PIN for {user} is switched off. Sign in with your password; that switches it back on."}
    return generic


def _tell(user: str) -> None:
    """The tenth wrong PIN: Discord #alerts and a push to Bradly. Never blocks the answer."""
    from . import audit
    audit.record(user, "auth.pin.off", ok=False, detail=f"{WRONG_MAX} wrong PINs; the PIN waits for a password sign-in")
    try:
        from . import accounts
        accounts.alert(f"🔢 {WRONG_MAX} wrong PINs for {user}: their PIN is switched off until they sign in with their password. "
                       f"If that wasn't them, someone on church Wi-Fi or Tailscale was guessing.")
        accounts.tell_bradly("PIN switched off", f"{WRONG_MAX} wrong PINs for {user}. Their PIN is off until their next password sign-in.")
    except Exception:  # noqa: BLE001
        pass


def everyone() -> dict:
    """For Directory: who has a PIN, its reach, whether it is off. Names only."""
    return {u: {"scope": r.get("scope", "full"), "off": bool(r.get("off")), "since": r.get("set")} for u, r in _read().items()}
