"""The church Macs (round 6; docs/MACS.md): the server as the Macs' Active Directory.

* The text protocol, the account lines and the file lists are pure functions.
* The checked removal compares against real files in a temp homes folder.
* Enrolment, the Mac key, the check-in, a service's HOLD, offboarding's removals and the
  secrets file run in real mode against a temp state folder (no samba-tool, no Mac here).
* The admin routes and the helper's own door go through the API in sample mode.
* The helper scripts pass bash -n, and the LaunchDaemon parses with plistlib.
"""
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from arise_server import config, demo_state, macs  # noqa: E402

USERS = [{"name": "jane.doe", "enabled": True}, {"name": "john.smith", "enabled": True}, {"name": "old.timer", "enabled": False},
         {"name": "administrator", "enabled": True}, {"name": "arise-rescue", "enabled": True}, {"name": "kristina.robinson", "enabled": True}]
ACCOUNTS = ("jane.doe|mobile|1104|0|/Users/jane.doe|0|Jane Doe|\n"
            "old.timer|mobile|1105|0|/Users/old.timer|0|Old Timer|\n"
            "kristina|local|501|1|/Users/kristina|0|Kristina Robinson|\n"
            "guest|local|502|0|/Users/guest|1|Guest|\n"
            "bad line\n")


@contextmanager
def real_mode(tmp: Path, extra: str = ""):
    conf = tmp / "arise.toml"
    conf.write_text(f'[system]\ndata_root = "{tmp}/data"\n[web]\nadmin_user = "bradly"\n[directory]\nenabled = true\nhomes_path = "{tmp}/homes"\n'
                    f'[paths]\nstate_dir = "{tmp}/state"\nlog_dir = "{tmp}/state"\n' + extra)
    old = {k: os.environ.get(k) for k in ("ARISE_CONFIG", "ARISE_DEMO", "ARISE_MACS_SECRETS")}
    os.environ["ARISE_CONFIG"] = str(conf)
    os.environ["ARISE_MACS_SECRETS"] = str(tmp / "secrets" / "macs")
    os.environ.pop("ARISE_DEMO", None)
    config.load(force=True)
    try:
        with mock.patch.object(macs, "_directory_users", return_value=USERS), \
             mock.patch("arise_server.church.in_service_now", return_value=None), \
             mock.patch.object(macs, "ca_fingerprint", return_value=None):
            yield
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        config.load(force=True)


def tasks_of(line_list):
    """TASK lines -> (kind, {k: v}) the way the helper reads them."""
    out = []
    for ln in line_list:
        w = ln.split(" ")
        if w[0] == "TASK":
            out.append((w[2], {kv.split("=", 1)[0]: unquote(kv.split("=", 1)[1]) for kv in w[3:]}))
    return out


class Pure(unittest.TestCase):
    def test_task_lines_survive_spaces_and_bars(self):
        line = macs.task_line({"id": "t7", "kind": "remove_profile", "args": {"user": "jane.doe", "bases": "/srv/arise/homes/john smith/From Jane (2026-10-29)|/srv/x"}})
        self.assertEqual(line.split(" ")[:3], ["TASK", "t7", "remove_profile"])
        self.assertEqual(len(line.split(" ")), 5)                           # one word per k=v: bash's `for kv in $rest` works
        self.assertEqual(tasks_of([line])[0][1]["bases"], "/srv/arise/homes/john smith/From Jane (2026-10-29)|/srv/x")

    def test_account_lines(self):
        a = macs.parse_accounts(ACCOUNTS)
        self.assertEqual([x["user"] for x in a], ["jane.doe", "old.timer", "kristina", "guest"])
        k = a[2]
        self.assertEqual((k["kind"], k["admin"], k["uid"], k["realname"], k["signed_in"]), ("local", True, 501, "Kristina Robinson", False))
        self.assertTrue(a[3]["signed_in"])

    def test_manifest_drops_escapes(self):
        m = macs.parse_manifest("Desktop/a.txt\t10\t100.0\n../../etc/passwd\t1\t1\n/abs/ok.txt\t2\t2\nDocuments/x/../../y\t1\t1\nbroken\n")
        self.assertEqual([r for r, _, _ in m], ["Desktop/a.txt", "abs/ok.txt"])

    def test_suggestion_is_only_a_suggestion(self):
        self.assertEqual(macs.suggest_user("kristina", "Kristina Robinson", USERS), "kristina.robinson")
        self.assertEqual(macs.suggest_user("JANE.DOE", "", USERS), "jane.doe")
        self.assertEqual(macs.suggest_user("media", "Media Team", USERS), "media.team")   # not on the server: shown as new
        self.assertIsNone(macs.suggest_user("guest", "Guest", USERS))

    def test_plan_makes_and_removes_only_mobile_accounts(self):
        m = {"accounts": macs.parse_accounts(ACCOUNTS), "choices": {}}
        plan = macs.plan_accounts(m, USERS, ["john.smith"], [])
        self.assertIn(("add_account", {"user": "kristina.robinson"}), plan)
        self.assertNotIn(("add_account", {"user": "jane.doe"}), plan)            # already there
        self.assertNotIn(("add_account", {"user": "john.smith"}), plan)          # [macs] exclude
        self.assertFalse([p for p in plan if p[1]["user"] in ("administrator", "arise-rescue")])   # never, whatever the config
        self.assertIn(("remove_profile", {"user": "old.timer"}), plan)          # disabled, has a profile here
        self.assertFalse([p for p in plan if p[1]["user"] in ("kristina", "guest")])   # local accounts wait for a choice
        # a conversion in progress is not also made as a fresh account
        m["choices"] = {"kristina": {"action": "convert", "user": "kristina.robinson"}}
        self.assertNotIn(("add_account", {"user": "kristina.robinson"}), macs.plan_accounts(m, USERS, [], []))
        # an open task is not queued twice
        open_t = [{"kind": "remove_profile", "state": "sent", "args": {"user": "old.timer"}}]
        self.assertNotIn(("remove_profile", {"user": "old.timer"}), macs.plan_accounts(m, USERS, [], open_t))


class Checked(unittest.TestCase):
    """The checked removal against real files: same size, and not newer on the Mac."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)
        self.home = self.tmp / "homes" / "jane.doe"
        (self.home / "Desktop").mkdir(parents=True); (self.home / "Documents" / "Sub").mkdir(parents=True)
        (self.home / "Desktop" / "notes.txt").write_text("hello")
        (self.home / "Documents" / "Sub" / "plan.docx").write_bytes(b"x" * 300)
        self.t = (self.home / "Desktop" / "notes.txt").stat().st_mtime

    def test_all_there(self):
        r = macs.verify_manifest([("Desktop/notes.txt", 5, self.t), ("Documents/Sub/plan.docx", 300, self.t - 100)], [str(self.home)])
        self.assertTrue(r["ok"]); self.assertEqual(r["checked"], 2)

    def test_missing_newer_and_changed_refuse(self):
        r = macs.verify_manifest([("Desktop/notes.txt", 5, self.t + 60),        # edited on the Mac after the last sync
                                  ("Desktop/new.txt", 3, self.t),               # never reached the server
                                  ("Documents/Sub/plan.docx", 301, self.t)], [str(self.home)])
        self.assertFalse(r["ok"])
        self.assertEqual(r["missing"], ["Desktop/new.txt"])
        self.assertEqual(sorted(r["newer"]), ["Desktop/notes.txt", "Documents/Sub/plan.docx"])

    def test_second_base_counts(self):
        moved = self.tmp / "homes" / "john.smith" / "From jane.doe (2026-10-29)"
        (moved / "Desktop").mkdir(parents=True); (moved / "Desktop" / "only-here.txt").write_text("abc")
        r = macs.verify_manifest([("Desktop/only-here.txt", 3, time.time() - 100), ("Desktop/notes.txt", 5, self.t)], [str(moved), str(self.home)])
        self.assertTrue(r["ok"], r)


class RealMode(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)

    def enrol(self):
        tok = macs.enrol_token("bradly", "OFFICE-MAC-02")
        self.assertIn("--token " + tok["token"], tok["command"])
        self.assertIn("--name OFFICE-MAC-02", tok["command"])
        r = macs.enrol(tok["token"], {"name": "OFFICE-MAC-02", "serial": "C02X", "model": "MacBook Air", "macos": "15.3", "accounts": ACCOUNTS})
        self.assertTrue(r["ok"], r)
        return tok, r

    def test_token_is_one_time_and_expires(self):
        with real_mode(self.tmp):
            tok, r = self.enrol()
            self.assertFalse(macs.enrol(tok["token"], {"name": "AGAIN"})["ok"])               # once
            t2 = macs.enrol_token("bradly")
            with mock.patch.object(macs.time, "time", return_value=time.time() + macs.TOKEN_TTL + 5):
                self.assertFalse(macs.enrol(t2["token"], {"name": "LATE"})["ok"])             # an hour
            self.assertFalse(macs.enrol("made-up", {})["ok"])
            state = (self.tmp / "state" / "macs" / "macs.json").read_text()
            self.assertNotIn(r["key"], state)                                                  # only the hash is kept
            self.assertNotIn(tok["token"], state)

    def test_key_church_owned_and_the_plan(self):
        with real_mode(self.tmp):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            self.assertTrue(m and m["church_owned"])
            self.assertIsNone(macs.agent_auth(f"{r['mac_id']}:wrong"))
            self.assertIsNone(macs.agent_auth("mac-000000000000:" + r["key"]))
            got = tasks_of(macs.checkin(m, {"accounts": ACCOUNTS}))
            kinds = [k for k, _ in got]
            for k in ("certificate", "login_window", "ariseadmin", "filevault", "printers", "bookmarks", "tailscale", "add_account", "remove_profile"):
                self.assertIn(k, kinds)
            adds = {a["user"] for k, a in got if k == "add_account"}
            self.assertEqual(adds, {"john.smith", "kristina.robinson"})
            rm = next(a for k, a in got if k == "remove_profile")
            self.assertEqual(rm["user"], "old.timer")
            self.assertTrue(rm["bases"].endswith("/homes/old.timer"))
            self.assertNotIn("convert_local", kinds)                                           # nothing automatic for local accounts
            self.assertEqual(tasks_of(macs.checkin(m, {"accounts": ACCOUNTS})), [])            # sent once, not again at once
            # a personal Mac is never listed: only enrolled ones are
            self.assertEqual([x["name"] for x in macs.listing()["macs"]], ["OFFICE-MAC-02"])

    def test_hold_during_a_service(self):
        with real_mode(self.tmp):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            with mock.patch("arise_server.church.in_service_now", return_value={"name": "Sunday Service"}):
                out = macs.checkin(m, {})
            self.assertEqual(out, ["HOLD Sunday%20Service"])
            self.assertTrue(tasks_of(macs.checkin(m, {})))                                     # after the service they flow

    def test_rotation_and_overnight_updates(self):
        with real_mode(self.tmp):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            got = tasks_of(macs.checkin(m, {}, now=datetime(2026, 11, 3, 2, 30)))
            self.assertIn("updates", [k for k, _ in got])
            self.assertEqual([k for k, _ in got].count("ariseadmin"), 1)                       # the enrolment's, not a second
            later = tasks_of(macs.checkin(m, {}, now=datetime(2026, 11, 3, 12, 0)))
            self.assertNotIn("ariseadmin", [k for k, _ in later])                               # still open: not queued again
            again = tasks_of(macs.checkin(m, {}, now=datetime(2026, 11, 3, 3, 30)))
            self.assertNotIn("updates", [k for k, _ in again])                                  # once a night

    def test_check_uses_the_servers_bases_and_needs_a_removal(self):
        with real_mode(self.tmp):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            home = self.tmp / "homes" / "old.timer" / "Desktop"; home.mkdir(parents=True)
            (home / "a.txt").write_text("12345")
            mt = (home / "a.txt").stat().st_mtime
            man = f"Desktop/a.txt\t5\t{mt}\n"
            self.assertFalse(macs.check(m, "old.timer", "", man)["ok"])                       # no removal waiting yet
            macs.checkin(m, {"accounts": ACCOUNTS})                                            # queues the removal
            self.assertTrue(macs.check(m, "old.timer", "/etc|/", man)["ok"])                  # the Mac's bases are ignored
            self.assertFalse(macs.check(m, "jane.doe", "", man)["ok"])                         # not someone else's folders
            self.assertFalse(macs.check(m, "old.timer", "", man + "Desktop/b.txt\t1\t1\n")["ok"])

    def test_offboarding_queues_removals_with_the_moved_folder_first(self):
        with real_mode(self.tmp):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            macs.checkin(m, {"accounts": ACCOUNTS})
            moved = str(self.tmp / "homes" / "john.smith" / "From jane.doe (2026-10-29)")
            q = macs.queue_removals("jane.doe", by="test", moved_to=moved)
            self.assertEqual(q["queued"], ["OFFICE-MAC-02"])
            t = next(t for t in macs._read()["tasks"][r["mac_id"]] if t["kind"] == "remove_profile" and t["args"]["user"] == "jane.doe")
            self.assertEqual(t["args"]["bases"].split("|")[0], moved)
            self.assertEqual(macs.queue_removals("jane.doe", by="test")["queued"], [])         # not twice
            self.assertEqual(macs.queue_removals("nobody.here", by="test")["queued"], [])      # only where they have a profile

    def test_secrets_file_is_0600_and_reveal_is_audited(self):
        with real_mode(self.tmp):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            self.assertFalse(macs.reveal(r["mac_id"], "filevault", "bradly")["ok"])          # not escrowed yet
            self.assertTrue(macs.store_secret(m, "filevault", "ABCD-EFGH-IJKL-MNOP-QRST-UVWX")["ok"])
            p = self.tmp / "secrets" / "macs" / f"{r['mac_id']}.json"
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(p.parent.stat().st_mode), 0o700)
            self.assertNotIn("ABCD-EFGH", (self.tmp / "state" / "macs" / "macs.json").read_text())
            self.assertEqual(macs.reveal(r["mac_id"], "filevault", "bradly")["value"], "ABCD-EFGH-IJKL-MNOP-QRST-UVWX")
            audit_log = (self.tmp / "state" / "audit.jsonl").read_text()
            self.assertIn("macs.reveal.filevault", audit_log)
            self.assertNotIn("ABCD-EFGH", audit_log)
            self.assertFalse(macs.store_secret(m, "token", "x")["ok"])

    def test_retire_waits_for_every_choice_and_cut_off_kills_the_key(self):
        with real_mode(self.tmp):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            macs.checkin(m, {"accounts": ACCOUNTS})
            self.assertFalse(macs.retire(r["mac_id"], "wrong", "bradly")["ok"])
            no = macs.retire(r["mac_id"], "OFFICE-MAC-02", "bradly")
            self.assertFalse(no["ok"]); self.assertIn("kristina", no["err"])
            for local in ("kristina", "guest"):
                self.assertTrue(macs.choose_local(r["mac_id"], local, "leave", "", "bradly")["ok"])
            self.assertTrue(macs.retire(r["mac_id"], "OFFICE-MAC-02", "bradly")["ok"])
            with mock.patch("arise_server.util.run", return_value={"ok": True}) as run:
                c = macs.cut_off(r["mac_id"], "OFFICE-MAC-02", "bradly")
            self.assertTrue(c["ok"]); self.assertTrue(c["also"])
            self.assertEqual(run.call_args[0][0], ["samba-tool", "user", "disable", "OFFICE-MAC-02$"])
            self.assertIsNone(macs.agent_auth(f"{r['mac_id']}:{r['key']}"))                    # the key is dead
            self.assertTrue(all(t["state"] not in ("queued", "sent") for t in macs._read()["tasks"][r["mac_id"]]))

    def test_choices(self):
        with real_mode(self.tmp):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            macs.checkin(m, {"accounts": ACCOUNTS})
            self.assertFalse(macs.choose_local(r["mac_id"], "guest", "convert", "jane.doe", "bradly")["ok"])   # signed in
            self.assertFalse(macs.choose_local(r["mac_id"], "nobody", "link", "jane.doe", "bradly")["ok"])
            self.assertFalse(macs.choose_local(r["mac_id"], "kristina", "convert", "Not A Name", "bradly")["ok"])
            self.assertFalse(macs.choose_local(r["mac_id"], "kristina", "erase", "", "bradly")["ok"])
            ok = macs.choose_local(r["mac_id"], "kristina", "convert", "kristina.robinson", "bradly")
            self.assertTrue(ok["ok"]); self.assertIsNone(ok["made"])                             # already on the server
            got = tasks_of(macs.checkin(m, {}))
            conv = next(a for k, a in got if k == "convert_local")
            self.assertEqual(conv, {"local": "kristina", "user": "kristina.robinson", "admin": "1"})   # she was an admin there
            self.assertEqual(next(a for k, a in got if k == "nextcloud"), {"user": "kristina.robinson", "local": "kristina.robinson"})
            self.assertTrue(macs.choose_local(r["mac_id"], "kristina", "undo", "", "bradly")["ok"])
            self.assertIn("unconvert", [k for k, _ in tasks_of(macs.checkin(m, {}))])
            # Link: the account stays; the files sync as the server user
            self.assertTrue(macs.choose_local(r["mac_id"], "kristina", "link", "jane.doe", "bradly")["ok"])
            got = tasks_of(macs.checkin(m, {}))
            self.assertEqual(next(a for k, a in got if k == "link_local")["admin"], "0")
            self.assertEqual(next(a for k, a in got if k == "nextcloud"), {"user": "jane.doe", "local": "kristina"})


class Api(unittest.TestCase):
    """The admin routes and the helper's door, in sample mode."""

    def setUp(self):
        os.environ["ARISE_DEMO"] = "1"
        os.environ["ARISE_STAFF_ACCESS"] = "portal"
        self.addCleanup(os.environ.pop, "ARISE_STAFF_ACCESS", None)
        config.load(force=True)
        demo_state.reset()
        from fastapi.testclient import TestClient
        from arise_server.main import app
        self.TC, self.app = TestClient, app
        self.admin = TestClient(app)

    def member(self):
        c = self.TC(self.app)
        self.assertEqual(c.post("/api/auth/login", json={"user": "office", "password": "anything"}).json()["role"], "member")
        return c

    def test_admins_only(self):
        mem = self.member()
        for method, path, body in (("GET", "/api/macs", None), ("POST", "/api/macs/enrol-token", {"name": "X"}),
                                   ("GET", "/api/macs/mac-0000000000b2", None),
                                   ("POST", "/api/macs/mac-0000000000b2/local", {"local": "kristina", "action": "leave"}),
                                   ("POST", "/api/macs/mac-0000000000a1/reveal", {"kind": "filevault"})):
            self.assertEqual(mem.request(method, path, json=body).status_code, 403, path)

    def test_list_detail_and_a_choice_that_makes_a_user(self):
        a = self.admin
        names = [m["name"] for m in a.get("/api/macs").json()["macs"]]
        self.assertEqual(names, ["KIDS-MAC", "MEDIA-MAC-01", "OFFICE-MAC-01"])
        d = a.get("/api/macs/mac-0000000000b2").json()
        k = next(x for x in d["accounts"] if x["user"] == "kristina")
        self.assertEqual((k["state"], k["suggest"], k["suggest_exists"]), ("waiting for your choice", "kristina.robinson", False))
        r = a.post("/api/macs/mac-0000000000b2/local", json={"local": "kristina", "action": "convert", "user": "kristina.robinson", "display": "Kristina Robinson"}).json()
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["made"]["user"], "kristina.robinson")                                # made first, temporary password
        self.assertTrue(r["made"]["temporary_password"])
        self.assertIn("kristina.robinson", [u["name"] for u in a.get("/api/directory/users").json()["users"]])
        d = a.get("/api/macs/mac-0000000000b2").json()
        self.assertEqual(next(x for x in d["accounts"] if x["user"] == "kristina")["state"], "converting to kristina.robinson")
        self.assertIn("convert_local", [t["kind"] for t in d["tasks"]])
        tok = a.post("/api/macs/enrol-token", json={"name": "OFFICE MAC 2"}).json()
        self.assertIn("sudo bash -s -- --token", tok["command"]); self.assertIn("--name OFFICE-MAC-2", tok["command"])

    def test_helper_door(self):
        a = self.admin
        self.assertEqual(a.post("/api/macs/agent/checkin", data={"helper": "1.0.0"}).status_code, 401)        # no key
        self.assertEqual(a.post("/api/macs/agent/checkin", headers={"X-Arise-Mac": "mac-0000000000a1:guess"}).status_code, 401)
        tok = a.post("/api/macs/enrol-token", json={"name": "NEW-MAC"}).json()["token"]
        r = a.post("/api/macs/agent/enrol", data={"token": tok, "name": "NEW-MAC", "serial": "C02NEW", "accounts": ACCOUNTS})
        self.assertEqual(r.status_code, 200); self.assertTrue(r.headers["content-type"].startswith("text/plain"))
        kv = dict(ln.split("=", 1) for ln in r.text.splitlines())
        hdr = {"X-Arise-Mac": f"{kv['MAC_ID']}:{kv['KEY']}"}
        self.assertEqual(a.post("/api/macs/agent/enrol", data={"token": tok}).status_code, 403)                 # used
        with mock.patch("arise_server.church.in_service_now", return_value=None):
            out = a.post("/api/macs/agent/checkin", headers=hdr, data={"helper": "1.0.0", "accounts": ACCOUNTS}).text
        lines = [ln for ln in out.splitlines() if ln.startswith("TASK ")]
        self.assertTrue(lines)
        tid = lines[0].split(" ")[1]
        self.assertEqual(a.post("/api/macs/agent/result", headers=hdr, data={"id": tid, "state": "done", "detail": "ok"}).text.strip(), "OK")
        self.assertEqual(a.post("/api/macs/agent/result", headers=hdr, data={"id": tid, "state": "maybe"}).status_code, 400)
        cfg = a.get("/api/macs/agent/config", headers=hdr).text
        self.assertTrue(cfg.startswith("LOGIN faces"))
        self.assertIn("BOOKMARK", cfg)
        self.assertEqual(a.get("/api/macs/agent/config").status_code, 401)
        self.assertIn(kv["MAC_ID"], [m["id"] for m in a.get("/api/macs").json()["macs"]])

    def test_scripts_are_served_and_nothing_else(self):
        a = self.admin
        r = a.get("/mac/enrol.sh")
        self.assertEqual(r.status_code, 200); self.assertTrue(r.text.startswith("#!/bin/bash"))
        self.assertEqual(a.get("/mac/bind-mac.sh").status_code, 200)
        for bad in ("/mac/..%2F..%2Fserver%2Farise_server%2Fmacs.py", "/mac/macs.py", "/mac/arise.toml"):
            r = a.get(bad)
            self.assertNotIn("church_owned", r.text, bad)                                       # never the server's own files
            self.assertTrue(r.status_code == 404 or r.text.lstrip().lower().startswith("<!doctype html"), bad)


class Scripts(unittest.TestCase):
    def test_bash_syntax(self):
        for f in ("mac/helper/arise-mac-helper", "mac/helper/enrol.sh", "mac/bind-mac.sh", "mac/migrate-mac-user.sh", "mac/arise-home-sync.sh"):
            r = subprocess.run(["bash", "-n", str(ROOT / f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f + r.stderr)

    def test_launch_daemon(self):
        with open(ROOT / "mac" / "helper" / "com.arisechurch.helper.plist", "rb") as f:
            p = plistlib.load(f)
        self.assertEqual(p["Label"], "com.arisechurch.helper")
        self.assertEqual(p["ProgramArguments"], ["/usr/local/arise/helper/arise-mac-helper"])
        self.assertTrue(p["RunAtLoad"]); self.assertEqual(p["StartInterval"], 300)
        self.assertNotIn("UserName", p)                                                         # root: a LaunchDaemon

    def test_helper_never_deletes_outside_users_and_knows_every_kind(self):
        src = (ROOT / "mac" / "helper" / "arise-mac-helper").read_text()
        for kind in macs.KINDS:
            self.assertIn(f"t_{kind}()", src, kind)
        self.assertIn('/Users/?*) ;;', src)                                                     # the rm -rf guard
        self.assertNotIn("eraseinstall", src); self.assertNotIn("diskutil erase", src)
        self.assertNotIn(". \"$CONF\"", src)                                                    # helper.conf is read, never sourced


if __name__ == "__main__":
    unittest.main()
