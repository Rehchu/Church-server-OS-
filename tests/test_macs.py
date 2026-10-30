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
def real_mode(tmp: Path, extra: str = "", watch: bool = False):
    """Real mode against a temp folder. The helper is switched on (watch = false) unless a test
    is about watch mode (round 7, 4)."""
    conf = tmp / "arise.toml"
    conf.write_text(f'[system]\ndata_root = "{tmp}/data"\n[web]\nadmin_user = "bradly"\n[directory]\nenabled = true\nhomes_path = "{tmp}/homes"\n'
                    f'[paths]\nstate_dir = "{tmp}/state"\nlog_dir = "{tmp}/state"\n[macs]\nwatch = {"true" if watch else "false"}\n' + extra)
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

    def test_default_link_plan(self):
        """Round 7, 23 and Bradly's follow-up: a clear match links; no clear match makes first.last
        (first.last2 when the name is someone else's), then links; a one-word name waits."""
        users = [u for u in USERS if u["name"] != "john.smith"] + [{"name": "john.smith", "enabled": True, "display": "Johnny Smithers"}]
        acc = ("kristina|local|501|1|/Users/kristina|0|Kristina Robinson|\n"
               "jane.doe|local|502|0|/Users/jane.doe|0|J D|\n"
               "jsmith|local|503|0|/Users/jsmith|0|John Smith|\n"
               "levi|local|504|0|/Users/levi|0|Levi Mercer|\n"
               "media|local|505|0|/Users/media|0|Media|\n"
               "guest|local|506|0|/Users/guest|0|Guest|\n"
               "done|local|507|0|/Users/done|0|Done Already|\n"
               "old.timer|mobile|1105|0|/Users/old.timer|0|Old Timer|\n")
        m = {"accounts": macs.parse_accounts(acc), "choices": {"done": {"action": "leave"}}}
        plan = {p["local"]: p for p in macs.plan_links(m, users)}
        self.assertEqual(plan["kristina"], {"local": "kristina", "user": "kristina.robinson", "make": False})   # first.last, no display on file
        self.assertEqual((plan["jane.doe"]["user"], plan["jane.doe"]["make"]), ("jane.doe", False))              # the same short name
        self.assertEqual((plan["jsmith"]["user"], plan["jsmith"]["make"]), ("john.smith2", True))                # someone else's name: the next one
        self.assertEqual((plan["levi"]["user"], plan["levi"]["make"], plan["levi"]["display"]), ("levi.mercer", True, "Levi Mercer"))
        self.assertIsNone(plan["media"]["user"])                                                                  # one word: by hand
        for gone in ("guest", "old.timer", "done"):
            self.assertNotIn(gone, plan)
        self.assertEqual(macs.would_text(plan["levi"]), "would make levi.mercer and link levi to it")
        self.assertEqual(macs.would_text(plan["kristina"]), "would link kristina to kristina.robinson")
        self.assertTrue(macs.would_text(plan["media"]).startswith("would leave media waiting"))
        self.assertNotIn("levi", {p["local"] for p in macs.plan_links(m, users, exclude=["levi"])})
        # a linked account gets no second (mobile) account on that Mac (round 7, 25)
        m2 = {"accounts": macs.parse_accounts(acc), "choices": {}}
        self.assertNotIn(("add_account", {"user": "kristina.robinson"}), macs.plan_accounts(m2, USERS, [], [], linking={"kristina.robinson"}))
        m2["choices"] = {"kristina": {"action": "link", "user": "kristina.robinson"}}
        self.assertNotIn(("add_account", {"user": "kristina.robinson"}), macs.plan_accounts(m2, USERS, [], []))

    def test_names(self):
        self.assertEqual(macs.unique_name("john.smith", {"jane.doe"}), "john.smith")
        self.assertEqual(macs.unique_name("john.smith", {"john.smith", "john.smith2"}), "john.smith3")
        self.assertEqual(macs.ad_name("Office Mac 2"), "Office-Mac-2")
        self.assertEqual(len(macs.ad_name("A very long Mac name indeed")), 15)
        self.assertEqual(macs.ad_name("!!!"), "MAC")
        self.assertEqual([macs.parse_disk(v) for v in ("87%", "90", "", "x", "101", None)], [87, 90, None, None, None, None])

    def test_a_failing_task_backs_off_and_old_tasks_are_pruned(self):
        from datetime import datetime, timedelta
        now = datetime(2026, 11, 3, 12, 0)
        iso = lambda **kw: (now - timedelta(**kw)).isoformat(timespec="seconds")
        m = {"accounts": macs.parse_accounts(ACCOUNTS), "choices": {}}
        fail = lambda ago: {"kind": "add_account", "state": "failed", "args": {"user": "kristina.robinson"}, "finished": iso(minutes=ago)}
        add = ("add_account", {"user": "kristina.robinson"})
        self.assertNotIn(add, macs.plan_accounts(m, USERS, [], [fail(5)], now))          # failed 5 minutes ago: waits
        self.assertIn(add, macs.plan_accounts(m, USERS, [], [fail(20)], now))            # 15 minutes after one failure: again
        three = [fail(200), fail(100), fail(50)]                                          # three in a row: waits an hour
        self.assertNotIn(add, macs.plan_accounts(m, USERS, [], three, now))
        self.assertIn(add, macs.plan_accounts(m, USERS, [], [fail(200), fail(100), fail(70)], now))
        many = [fail(60 * 24 * 2 + i) for i in range(20)]                                 # never more than a day
        self.assertIn(add, macs.plan_accounts(m, USERS, [], many, now))
        ok_after = three + [{"kind": "add_account", "state": "done", "args": {"user": "kristina.robinson"}, "finished": iso(minutes=10)}]
        self.assertFalse(macs.backing_off(ok_after, "add_account", "kristina.robinson", now))   # a success resets it
        kept = macs.prune([{"state": "done", "finished": iso(days=31)}, {"state": "done", "finished": iso(days=2)}, {"state": "queued"}], now)
        self.assertEqual(len(kept), 2)


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
            self.assertEqual(adds, {"john.smith"})                                             # Kristina has a linked local account (round 7, 25)
            self.assertEqual(next(a for k, a in got if k == "link_local"), {"local": "kristina", "user": "kristina.robinson", "admin": "0"})
            self.assertIn({"user": "kristina.robinson", "local": "kristina"}, [a for k, a in got if k == "nextcloud"])
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
            man = f"Desktop/a.txt\t5\t{mt}\n#folder\tDesktop\tread\t1\t0\n#folder\tDocuments\tabsent\t0\t0\n"
            self.assertFalse(macs.check(m, "old.timer", "", man)["ok"])                       # no removal waiting yet
            macs.checkin(m, {"accounts": ACCOUNTS})                                            # queues the removal
            self.assertTrue(macs.check(m, "old.timer", "/etc|/", man)["ok"])                  # the Mac's bases are ignored
            self.assertFalse(macs.check(m, "jane.doe", "", man)["ok"])                         # not someone else's folders
            self.assertFalse(macs.check(m, "old.timer", "", man + "Desktop/b.txt\t1\t1\n")["ok"])
            # a listing that proves nothing is refused, however empty it is
            self.assertFalse(macs.check(m, "old.timer", "", "")["ok"])                                       # no summary
            r = macs.check(m, "old.timer", "", "#folder\tDesktop\tunreadable\t0\t0\n")
            self.assertFalse(r["ok"]); self.assertIn("Full Disk Access", r["err"])
            self.assertFalse(macs.check(m, "old.timer", "", "#folder\tDesktop\tread\t1\t0\n")["ok"])       # items, no files
            self.assertFalse(macs.check(m, "old.timer", "", man.replace("read\t1\t0", "read\t1\t2"))["ok"])  # odd names
            self.assertTrue(macs.check(m, "old.timer", "", "#folder\tDesktop\tread\t0\t0\n")["ok"])        # empty really is empty

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
            self.assertFalse(no["ok"]); self.assertIn("guest", no["err"])
            self.assertNotIn("kristina", no["err"])                                           # linked by default: chosen already
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
            # the default's link to kristina.robinson was replaced, not left to run as well
            old = [t for t in macs._read()["tasks"][r["mac_id"]] if t["kind"] == "link_local" and t["args"]["user"] == "kristina.robinson"]
            self.assertTrue(old and all(t["state"] == "cancelled" for t in old))

    def test_watch_mode_reports_and_hands_out_nothing(self):
        """Round 7, 4: the helper checks in, the plan is made, nothing but a notice goes out."""
        with real_mode(self.tmp, watch=True):
            self.assertTrue(macs.watch_mode())
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            with mock.patch("arise_server.directory.add_user") as add:
                out = macs.checkin(m, {"accounts": ACCOUNTS + "levi|local|503|0|/Users/levi|0|Levi Mercer|\n", "disk_used": "93%"})
            add.assert_not_called()                                                             # nobody is made in watch mode
            self.assertEqual(out[0].split(" ")[0], "WATCH"); self.assertGreater(int(out[0].split(" ")[1]), 5)
            self.assertEqual([k for k, _ in tasks_of(out)], ["notice"])                       # the disk notice only
            cur = macs._read()["macs"][r["mac_id"]]
            self.assertIn("would make levi.mercer and link levi to it", cur["would"])
            self.assertIn("would link kristina to kristina.robinson", cur["would"])
            self.assertNotIn("kristina", cur.get("choices") or {})
            lines = [a["text"] for a in macs.attention()]
            self.assertTrue(any("watch mode" in t for t in lines)); self.assertTrue(any("93% full" in t for t in lines))
            with mock.patch("arise_server.church.in_service_now", return_value={"name": "Glory Night"}):
                self.assertEqual(tasks_of(macs.checkin(m, {})), [])                            # not even a notice during a service
            self.assertTrue(macs.set_live(True, "bradly")["ok"])
            self.assertFalse(macs.watch_mode())
            self.assertIn("macs.live", (self.tmp / "state" / "audit.jsonl").read_text())
            self.assertIn("link_local", [k for k, _ in tasks_of(macs.checkin(m, {}))])
            macs.set_live(False, "bradly")
            self.assertTrue(macs.watch_mode())

    def test_live_default_link_makes_the_user_and_shows_the_password_once(self):
        with real_mode(self.tmp):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            acc = ACCOUNTS + "levi|local|503|0|/Users/levi|0|Levi Mercer|\n"
            with mock.patch("arise_server.directory.add_user", return_value={"ok": True}) as add, \
                 mock.patch("arise_server.profiles.temp_password", return_value="Temp-Pass-1234"):
                got = tasks_of(macs.checkin(m, {"accounts": acc}))
            add.assert_called_once()
            self.assertEqual(add.call_args[0][:2], ("levi.mercer", "Temp-Pass-1234"))
            self.assertTrue(add.call_args[1]["temporary"]); self.assertEqual(add.call_args[1]["display"], "Levi Mercer")
            self.assertIn({"local": "levi", "user": "levi.mercer", "admin": "0"}, [a for k, a in got if k == "link_local"])
            self.assertNotIn("Temp-Pass-1234", (self.tmp / "state" / "macs" / "macs.json").read_text())
            d = macs.detail(r["mac_id"])
            self.assertIn("levi.mercer", d["temp_waiting"])
            t = macs.temp_take(r["mac_id"], "levi.mercer", "bradly")
            self.assertEqual(t["temporary_password"], "Temp-Pass-1234")
            self.assertFalse(macs.temp_take(r["mac_id"], "levi.mercer", "bradly")["ok"])          # once
            audit_log = (self.tmp / "state" / "audit.jsonl").read_text()
            self.assertIn("macs.temp_password.shown", audit_log); self.assertNotIn("Temp-Pass-1234", audit_log)
            # the choice is recorded as the default, and the Mac is now one of Levi's
            self.assertEqual(macs._read()["macs"][r["mac_id"]]["choices"]["levi"]["by"], "the default (round 7, 23)")
            self.assertIn((r["mac_id"], "levi"), macs.macs_of_person("levi.mercer"))
            # a failed make links nothing
            with mock.patch("arise_server.directory.add_user", return_value={"ok": False, "err": "no"}):
                got = tasks_of(macs.checkin(m, {"accounts": acc + "amy|local|504|0|/Users/amy|0|Amy Lane|\n"}))
            self.assertNotIn("amy", [a.get("local") for k, a in got if k == "link_local"])

    def test_disk_notice_once_a_week_and_person_notices(self):
        with real_mode(self.tmp):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            macs.checkin(m, {"accounts": ACCOUNTS})
            with mock.patch("arise_server.notices.alert_admins") as alert:
                got = tasks_of(macs.checkin(m, {"disk_used": "91"}, now=datetime(2026, 11, 3, 12, 0)))
                self.assertEqual(next(a for k, a in got if k == "notice")["user"], "")             # whoever is signed in
                alert.assert_called_once()
                self.assertIn("91% full", alert.call_args[0][0])
                self.assertFalse(tasks_of(macs.checkin(m, {"disk_used": "92"}, now=datetime(2026, 11, 4, 12, 0))))
                self.assertTrue(tasks_of(macs.checkin(m, {"disk_used": "92"}, now=datetime(2026, 11, 11, 12, 0))))
            self.assertEqual(macs._read()["macs"][r["mac_id"]]["disk_used"], 92)
            # a notice reaches every Mac where the person has an account: mobile, or a linked local one
            self.assertEqual(macs.queue_notice("jane.doe", "Hello", "Body"), ["OFFICE-MAC-02"])
            self.assertEqual(macs.queue_notice("kristina.robinson", "Hi", "x"), ["OFFICE-MAC-02"])
            self.assertEqual(macs.queue_notice("nobody.here", "Hi", "x"), [])
            n = [t["args"] for t in macs._read()["tasks"][r["mac_id"]] if t["kind"] == "notice" and t["args"]["title"] == "Hi"]
            self.assertEqual(n, [{"user": "kristina", "title": "Hi", "body": "x", "kind": "info"}])
            from arise_server import notices
            with mock.patch.object(notices, "personal_email", return_value="jane@example.org"), \
                 mock.patch("arise_server.mail.send_one", return_value={"ok": True}) as send:
                out = notices.notify_person("Jane.Doe", "Your password", "It changes Friday.", kind="warn")
            self.assertEqual(send.call_args[0][:2], ("jane@example.org", "Your password"))
            self.assertEqual((out["ok"], out["email"]["ok"], out["macs"]), (True, True, ["OFFICE-MAC-02"]))
            with mock.patch.object(notices, "personal_email", return_value=None):
                out = notices.notify_person("jane.doe", "T", "B", kind="nonsense")
            self.assertFalse(out["email"]["ok"]); self.assertEqual(out["macs"], ["OFFICE-MAC-02"])
            self.assertFalse(notices.notify_person("", "T", "B")["ok"])
            # Bradly's alert goes once per key, and never shows the webhook address
            os.environ["ARISE_DISCORD_TOML"] = str(self.tmp / "none.toml"); self.addCleanup(os.environ.pop, "ARISE_DISCORD_TOML", None)
            with mock.patch("arise_server.push.send", return_value={"ok": True}) as push:
                self.assertTrue(notices.alert_admins("disk full", key="k1")["ok"])
                self.assertTrue(notices.alert_admins("disk full", key="k1").get("duplicate"))
            push.assert_called_once()

    def test_silent_and_the_helpers_config(self):
        with real_mode(self.tmp, extra='apps = [{name = "Firefox", app = "Firefox.app", team = "43AQ936H96", url = "https://example.org/f.pkg"},'
                                     ' {name = "Proclaim", app = "Proclaim.app", team = "ABCDEFGHIJ", url = "", media_only = true},'
                                     ' {name = "Bad", app = "Bad.app", team = "guess"}]\n'):
            _, r = self.enrol()
            m = macs.agent_auth(f"{r['mac_id']}:{r['key']}")
            macs.checkin(m, {}, now=datetime(2026, 10, 1, 12, 0))
            self.assertEqual([x["name"] for x in macs.silent_macs()], ["OFFICE-MAC-02"])
            self.assertTrue(any("has not checked in" in a["text"] for a in macs.attention()))
            cfg = macs.config_lines(macs._read()["macs"][r["mac_id"]])
            self.assertIn("LOGINTEXT Arise%20Church%3A%20sign%20in%20with%20your%20church%20account.%20Help%3A%20Bradly", cfg)
            self.assertIn("APP Firefox Firefox.app 43AQ936H96 https", cfg)
            self.assertNotIn("Proclaim", cfg); self.assertNotIn("Bad.app", cfg)                 # not the media Mac; no real Team ID
            self.assertIn("DNS 1.1.1.3 1.0.0.3", cfg)
            self.assertIn("HELP Bradly%20Dyer Kristina%20Robinson Ronnie", cfg)
            self.assertIn("FOLDERS Desktop Documents Downloads Pictures Music", cfg)
            self.assertTrue(macs.set_media(r["mac_id"], True, "bradly")["ok"])
            self.assertIn("APP Proclaim Proclaim.app ABCDEFGHIJ -", macs.config_lines(macs._read()["macs"][r["mac_id"]]))
            self.assertTrue(any(t["kind"] == "apps" for t in macs._read()["tasks"][r["mac_id"]]))
            # the default apps: the four from Installomator, and Proclaim read off the media Mac (Oct 30)
            self.assertEqual({a["team"] for a in macs.DEFAULT_APPS}, {"43AQ936H96", "EQHXZ8M8AV", "BJ4HAAB9B3", "NKUJUXUJ3B", "G2ET27DGDP"})
            proclaim = [a for a in macs.DEFAULT_APPS if a["name"] == "Proclaim"][0]
            self.assertTrue(proclaim["media_only"]); self.assertEqual(proclaim["url"], "")
            self.assertEqual(macs.LOGIN_TEXT, "Arise Church: sign in with your church account. Help: Bradly")
            self.assertTrue(macs.run_task(r["mac_id"], "dnsfilter", "bradly", {"mode": "off"})["ok"])
            self.assertFalse(macs.run_task(r["mac_id"], "dnsfilter", "bradly", {"mode": "maybe"})["ok"])


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
                                   ("POST", "/api/macs/mac-0000000000b2/local", {"local": "levi", "action": "leave"}),
                                   ("POST", "/api/macs/mac-0000000000a1/reveal", {"kind": "filevault"})):
            self.assertEqual(mem.request(method, path, json=body).status_code, 403, path)

    def test_list_detail_and_a_choice_that_makes_a_user(self):
        a = self.admin
        names = [m["name"] for m in a.get("/api/macs").json()["macs"]]
        self.assertEqual(names, ["KIDS-MAC", "MEDIA-MAC-01", "OFFICE-MAC-01"])
        d = a.get("/api/macs/mac-0000000000b2").json()
        k = next(x for x in d["accounts"] if x["user"] == "levi")
        self.assertEqual((k["state"], k["suggest"], k["suggest_exists"]), ("would make levi.mercer and link levi to it", "levi.mercer", False))
        r = a.post("/api/macs/mac-0000000000b2/local", json={"local": "levi", "action": "convert", "user": "levi.mercer", "display": "Levi Mercer"}).json()
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["made"]["user"], "levi.mercer")                                # made first, temporary password
        self.assertTrue(r["made"]["temporary_password"])
        self.assertIn("levi.mercer", [u["name"] for u in a.get("/api/directory/users").json()["users"]])
        d = a.get("/api/macs/mac-0000000000b2").json()
        self.assertEqual(next(x for x in d["accounts"] if x["user"] == "levi")["state"], "converting to levi.mercer")
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
        self.assertFalse([ln for ln in out.splitlines() if ln.startswith("TASK ")])           # watch mode: nothing handed out (round 7, 4)
        self.assertTrue([ln for ln in out.splitlines() if ln.startswith("WATCH ")])
        self.assertFalse(self.member().post("/api/macs/live", json={"on": True}).status_code == 200)   # admins only
        self.assertTrue(a.post("/api/macs/live", json={"on": True}).json()["ok"])
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

    def test_watch_switch_media_and_temp_password_routes(self):
        a, mem = self.admin, self.member()
        self.assertTrue(a.get("/api/macs").json()["watch"])                                      # the sample starts in watch mode
        for path, body in (("/api/macs/live", {"on": True}), ("/api/macs/mac-0000000000a1/media", {"on": True}),
                           ("/api/macs/mac-0000000000a1/temp-password", {"user": "levi.mercer"})):
            self.assertEqual(mem.post(path, json=body).status_code, 403, path)
        r = a.post("/api/macs/mac-0000000000a1/media", json={"on": False}).json()
        self.assertTrue(r["ok"]); self.assertFalse(r["media"])
        self.assertFalse(a.post("/api/macs/mac-0000000000a1/temp-password", json={"user": "nobody.here"}).json()["ok"])
        self.assertEqual(a.post("/api/macs/mac-0000000000a1/temp-password", json={"user": "../x"}).status_code, 400)
        self.assertTrue(a.post("/api/macs/live", json={"on": True}).json()["ok"])
        self.assertFalse(a.get("/api/macs").json()["watch"])
        d = a.get("/api/macs/mac-0000000000b2").json()
        self.assertFalse(d["watch"])

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
        # A removal keeps the rest of the Mac folder as a disk image first, and stops if it cannot.
        rm = src[src.index("t_remove_profile() {"):src.index("t_convert_local() {")]
        self.assertLess(rm.index("hdiutil create"), rm.index("sysadminctl -deleteUser"))
        self.assertIn('could not keep a copy', rm)
        # Convert refuses to take away the Mac's Secure Token, and a failed convert puts the account back.
        cv = src[src.index("t_convert_local() {"):src.index("restore_local() {")]
        self.assertLess(cv.index("has_token"), cv.index('dscl . -delete "/Users/$old"'))
        self.assertIn("Choose Link instead", cv)
        self.assertLess(cv.index('"$CMA" -n'), cv.index("restore_local"))
        # The listing says when a folder could not be read (Full Disk Access) instead of coming back empty.
        mf = src[src.index("manifest() {"):src.index("server_has_it_all() {")]
        self.assertIn("unreadable", mf); self.assertIn("#folder", mf)


if __name__ == "__main__":
    unittest.main()
