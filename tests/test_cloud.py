"""Round 6: Mac and phone syncing (docs/ANSWERS.md round 6, rows 13-19, 39, 40; docs/SYNC.md).

What is pinned:
- Nextcloud's mounts give each person exactly the access the Samba lines give
  (sharing.folder_access): Church for everyone, a department written by staff, admins
  and its own login and read by its people, Pastors for the two pastors only;
- the domain sign-in is LDAPS, first.last, enabled accounts only, and Nextcloud keeps no
  copy of a domain password; its own sharing is off;
- a change on the server's disk maps to the one folder Nextcloud must rescan;
- newest wins: the older copy of a conflict goes to the Trash with a Put Back record,
  both ways round, and nothing is deleted;
- a person's Nextcloud files ARE their home (the link), and a home with files is never hidden;
- device app passwords: shown once, only a hash kept, issued again replaces the old one,
  revoke cuts one device or all; the Mac helper gets one only for a task an admin queued;
- the routes are the administrator's; the helper's door wants its Mac key;
- the container publishes on 127.0.0.1 only; Caddy serves it on the church certificate;
- mac/helper/tasks/nextcloud.sh: syntax, the signature check, both argument styles, and its
  config editing run for real against a sample nextcloud.cfg.
Real temp dirs throughout; the only stand-ins are for what is not on this box: Nextcloud's
occ (a small token store with occ's own output) and the Macs app's task list.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["ARISE_DEMO"] = "1"
os.environ["ARISE_CONFIG"] = str(ROOT / "config" / "arise.toml.example")

from fastapi.testclient import TestClient  # noqa: E402

from arise_server import audit, cloud, config, demo_state, sharing  # noqa: E402
from arise_server.main import app  # noqa: E402

SCRIPT = ROOT / "mac" / "helper" / "tasks" / "nextcloud.sh"


def effective(ms, user, groups):
    """What Nextcloud gives this person at each mount point: the applicable mount with the
    highest priority (users/groups empty = everyone)."""
    out = {}
    for m in ms:
        applies = (not m["users"] and not m["groups"]) or user in m["users"] or any(g in m["groups"] for g in groups)
        if not applies:
            continue
        cur = out.get(m["mount_point"])
        if cur is None or m["priority"] > cur["priority"]:
            out[m["mount_point"]] = m
    return {k: ("read" if v["readonly"] else "write") for k, v in out.items()}


class Base(unittest.TestCase):
    def setUp(self):
        os.environ["ARISE_DEMO"] = "1"
        os.environ["ARISE_CONFIG"] = str(ROOT / "config" / "arise.toml.example")
        self.cfg = config.load(force=True)
        demo_state.reset()


class Real(Base):
    """A real (not demo) config over a temp tree: /srv/arise is never touched."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="arise-cloud-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        t = self.tmp
        for d in ("homes", "shares/church", "shares/media", "pastors", "shared", "state", "logs", "apps/nextcloud/data"):
            os.makedirs(os.path.join(t, d), exist_ok=True)
        toml = os.path.join(t, "arise.toml")
        with open(toml, "w") as f:
            f.write(f'[system]\ndata_root = "{t}"\n[directory]\nhomes_path = "{t}/homes"\n'
                    f'[paths]\nstate_dir = "{t}/state"\nlog_dir = "{t}/logs"\n[apps]\nroot = "{t}/apps"\n'
                    f'[storage]\npastors_path = "{t}/pastors"\nshared_path = "{t}/shared"\n')
        self._env = {k: os.environ.get(k) for k in ("ARISE_DEMO", "ARISE_CONFIG")}
        os.environ.pop("ARISE_DEMO", None)
        os.environ["ARISE_CONFIG"] = toml
        self.cfg = config.load(force=True)
        self.assertFalse(self.cfg.demo)
        self.addCleanup(self._restore)

    def _restore(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        config.load(force=True)


# ---- the mounts: the same rule as the Samba lines -----------------------------------
class Mounts(Base):
    def test_every_folder_is_there(self):
        points = {m["mount_point"] for m in cloud.mounts()}
        self.assertIn("/Church", points)
        self.assertIn("/Pastors", points)
        self.assertIn("/Shared with me", points)
        for d in sharing.departments():
            self.assertIn("/" + cloud.label(d), points)
        self.assertIn("/Alexandria", points)
        self.assertIn("/Childrens Department", points)

    def test_nextcloud_access_matches_the_samba_rule(self):
        ms = cloud.mounts()
        people = [("jane.doe", ["Staff"], False), ("bradly", ["Domain Admins"], True), ("volunteer", ["Media"], False),
                  ("singer", ["Worship"], False), ("media-mac", [], False), ("inedge", [], False),
                  ("childrens.department", [], False), ("guest", [], False)]
        for user, groups, is_admin in people:
            got = effective(ms, user, groups)
            for d in [str(self.cfg.storage.church_folder)] + sharing.departments():
                want = sharing.folder_access(d, user, groups, is_admin)
                self.assertEqual(got.get("/" + cloud.label(d)), want, f"{user} on {d}")

    def test_pastors_is_the_two_pastors_only(self):
        ms = cloud.mounts()
        self.assertEqual(effective(ms, "bryant.sanders", []).get("/Pastors"), "write")
        self.assertEqual(effective(ms, "vanessa.sanders", []).get("/Pastors"), "write")
        for who, groups in (("bradly", ["Domain Admins"]), ("kristina.robinson", ["Domain Admins", "Staff"]), ("jane.doe", ["Staff"])):
            self.assertNotIn("/Pastors", effective(ms, who, groups), who)
        pm = next(m for m in ms if m["mount_point"] == "/Pastors")
        self.assertEqual(pm["groups"], [])
        self.assertEqual(sorted(pm["users"]), sorted(["bryant.sanders", "vanessa.sanders", cloud.SCANNER]))

    def test_shared_with_me_is_each_persons_own(self):
        m = next(m for m in cloud.mounts() if m["mount_point"] == "/Shared with me")
        self.assertEqual(m["datadir"], "/shared/$user")

    def test_import_json_is_local_storage_with_no_sharing(self):
        rows = cloud.import_json()
        self.assertEqual(len(rows), len(cloud.mounts()))
        for r in rows:
            self.assertEqual(r["storage"], "\\OC\\Files\\Storage\\Local")
            self.assertEqual(r["authentication_type"], "null::null")
            self.assertFalse(r["options"]["enable_sharing"])
            self.assertEqual(r["options"]["filesystem_check_changes"], 1)
            self.assertTrue(r["configuration"]["datadir"].startswith(("/shares/", "/pastors", "/shared/")))
            self.assertIsInstance(r["priority"], int)
        json.dumps(rows)


# ---- the domain sign-in and Nextcloud's settings ---------------------------------------
class Settings(Base):
    def test_ldap_is_ldaps_first_last_enabled_only(self):
        s = cloud.ldap_settings("pw")
        self.assertEqual(s["ldapHost"], "ldaps://arise-server.ad.arisecenla.com")
        self.assertEqual(s["ldapPort"], "636")
        self.assertEqual(s["ldapExpertUsernameAttr"], "sAMAccountName")
        self.assertIn("sAMAccountName=%uid", s["ldapLoginFilter"])
        self.assertIn("1.2.840.113556.1.4.803:=2", s["ldapUserFilter"])     # disabled accounts stop at once
        self.assertIn("!(sAMAccountName=arise-nextcloud)", s["ldapUserFilter"])
        self.assertEqual(s["ldapAgentName"], "CN=arise-nextcloud,CN=Users,DC=ad,DC=arisecenla,DC=com")
        self.assertEqual(s["ldapBase"], "DC=ad,DC=arisecenla,DC=com")
        self.assertEqual(s["turnOnPasswordChange"], "0")

    def test_the_occ_plan(self):
        plan = [" ".join(a) for a in cloud.occ_plan("pw")]
        for want in ("config:app:set core shareapi_enabled --value no",
                     "config:system:set auth.storeCryptedPassword --value false --type boolean",
                     "config:system:set memcache.locking --value \\OC\\Memcache\\Redis",
                     "config:system:set localstorage.allowsymlinks --value true --type boolean",
                     "config:system:set skeletondirectory --value ",
                     "theming:config name Arise", "app:enable user_ldap", "app:enable files_external",
                     "config:system:set trusted_domains 1 --value cloud.ad.arisecenla.com"):
            self.assertIn(want, plan)
        self.assertEqual(cloud.url(), "https://cloud.ad.arisecenla.com")

    def test_setup_dry_run_shows_no_password(self):
        r = cloud.setup(dry_run=True)
        text = json.dumps(r)
        self.assertIn("ldap:set-config s01 ldapAgentPassword ***", r["plan"])
        self.assertIn("samba-tool user setpassword arise-nextcloud --newpassword=***", r["account"])
        self.assertNotIn("{LDAP_BIND_PASSWORD}", text)
        self.assertEqual(r["env"]["CLOUD_HOST"], "cloud.ad.arisecenla.com")
        self.assertEqual(r["env"]["ARISE_HOMES"], self.cfg.directory.homes_path)

    def test_env_keys_follow_the_config_and_merge_keeps_the_rest(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, ".env")
            with open(p, "w") as f:
                f.write("APP_NAME=nextcloud\nDB_PASSWORD=keep-me\n# a note\nARISE_HOMES=/old\n")
            self.assertTrue(cloud.merge_env(p, cloud.env_keys()))
            body = Path(p).read_text()
            self.assertIn("DB_PASSWORD=keep-me\n", body)
            self.assertIn("# a note\n", body)
            self.assertIn(f"ARISE_HOMES={self.cfg.directory.homes_path}\n", body)
            self.assertNotIn("/old", body)
            self.assertIn("DC_FQDN=arise-server.ad.arisecenla.com\n", body)
            self.assertEqual(os.stat(p).st_mode & 0o777, 0o600)
            self.assertFalse(cloud.merge_env(p, cloud.env_keys()))     # nothing new: not rewritten, compose not re-run

    def test_service_account_plan(self):
        plan = cloud.service_account_plan("s3cret")
        self.assertEqual(plan[0][:4], ["samba-tool", "user", "create", "arise-nextcloud"])
        self.assertIn("--newpassword=s3cret", plan[1])
        self.assertEqual(plan[2], ["samba-tool", "user", "setexpiry", "arise-nextcloud", "--noexpiry"])


# ---- changes on disk -> the folder Nextcloud rescans -------------------------------------
class Paths(Base):
    def test_nc_path(self):
        p = cloud.paths()
        self.assertEqual(cloud.nc_path(p["homes"] + "/jane.doe/Documents/a.docx"),
                         {"kind": "home", "user": "jane.doe", "path": "/jane.doe/files/Documents/a.docx"})
        self.assertEqual(cloud.nc_path(p["shares"] + "/media/Fonts")["path"], f"/{cloud.SCANNER}/files/Media/Fonts")
        self.assertEqual(cloud.nc_path(p["shares"] + "/church")["path"], f"/{cloud.SCANNER}/files/Church")
        self.assertEqual(cloud.nc_path(p["pastors"] + "/notes.txt")["path"], f"/{cloud.SCANNER}/files/Pastors/notes.txt")
        self.assertEqual(cloud.nc_path(p["shared"] + "/jane.doe/x")["path"], "/jane.doe/files/Shared with me/x")
        for skip in (p["homes"] + "/jane.doe/.Trash/jane.doe/a", p["homes"] + "/jane.doe/Documents/.~lock.a.docx#",
                     p["homes"] + "/jane.doe/._x", p["shares"] + "/not-a-share/x", "/etc/passwd"):
            self.assertIsNone(cloud.nc_path(skip), skip)

    def test_debounce_rescans_each_folder_once(self):
        h = cloud.paths()["homes"]
        ev = [f"{h}/jane.doe/Documents/a.docx", f"{h}/jane.doe/Documents/b.docx", f"{h}/jane.doe/Documents/a.docx",
              f"{h}/jane.doe/Desktop/c.png", f"{h}/jane.doe/.Trash/jane.doe/old.txt"]
        got = [m["path"] for m in cloud.debounce(ev)]
        self.assertEqual(got, ["/jane.doe/files/Documents", "/jane.doe/files/Desktop"])
        self.assertEqual(cloud.scan_cmd({"path": "/jane.doe/files/Desktop"}), ["files:scan", "--path", "/jane.doe/files/Desktop", "--shallow"])


# ---- newest wins (row 15) ----------------------------------------------------------------
class Conflicts(Real):
    def test_names(self):
        self.assertEqual(cloud.conflict_of("Budget (conflicted copy 2026-10-29 101500).xlsx"), ("Budget.xlsx", "2026-10-29 101500"))
        self.assertEqual(cloud.conflict_of("Budget (conflicted copy Jane Doe 2026-10-29 101500).xlsx"), ("Budget.xlsx", "2026-10-29 101500"))
        self.assertEqual(cloud.conflict_of("Notes_conflict-20261029-101500.txt"), ("Notes.txt", "20261029-101500"))
        self.assertEqual(cloud.conflict_of("Makefile (conflicted copy 2026-10-29 101500)"), ("Makefile", "2026-10-29 101500"))
        self.assertIsNone(cloud.conflict_of("Budget.xlsx"))
        self.assertIsNone(cloud.conflict_of("conflicted copy.txt"))
        self.assertEqual(cloud.decide(100.0, 200.0), "conflict")
        self.assertEqual(cloud.decide(300.0, 200.0), "original")
        self.assertEqual(cloud.decide(None, 200.0), "conflict")

    def _pair(self, folder, orig_age, conf_age):
        os.makedirs(folder, exist_ok=True)
        o = os.path.join(folder, "Bulletin.docx")
        c = os.path.join(folder, "Bulletin (conflicted copy 2026-10-29 101500).docx")
        with open(o, "w") as f:
            f.write("ORIGINAL")
        with open(c, "w") as f:
            f.write("CONFLICT")
        import time
        now = time.time()
        os.utime(o, (now - orig_age, now - orig_age))
        os.utime(c, (now - conf_age, now - conf_age))
        return o, c

    def test_newer_conflict_copy_takes_the_name_older_original_to_the_trash(self):
        home = os.path.join(self.tmp, "homes", "jane.doe")
        o, c = self._pair(os.path.join(home, "Documents"), 600, 60)
        r = cloud.sweep(roots=[os.path.join(self.tmp, "homes")])
        self.assertEqual(len(r["moved"]), 1)
        self.assertEqual(Path(o).read_text(), "CONFLICT")
        self.assertFalse(os.path.exists(c))
        trash = os.path.join(home, ".Trash", "jane.doe", "Documents", "Bulletin.docx")
        self.assertEqual(Path(trash).read_text(), "ORIGINAL")                       # nothing deleted
        man = json.loads(Path(os.path.join(home, ".Trash", "jane.doe", ".arise-trash.json")).read_text())
        self.assertEqual(man["Documents/Bulletin.docx"]["original"], "Documents/Bulletin.docx")   # Put Back knows the way
        self.assertEqual(man["Documents/Bulletin.docx"]["who"], "sync")
        log = [json.loads(x) for x in Path(os.path.join(self.tmp, "state", "cloud-conflicts.jsonl")).read_text().splitlines()]
        self.assertEqual(log[-1]["kept"], "conflict copy (newer)")
        self.assertEqual(log[-1]["user"], "jane.doe")
        self.assertEqual(cloud.conflicts()["conflicts"][0]["file"], o)

    def test_newer_original_keeps_its_name_conflict_copy_to_the_trash(self):
        home = os.path.join(self.tmp, "homes", "jane.doe")
        o, c = self._pair(os.path.join(home, "Desktop"), 60, 600)
        cloud.sweep(roots=[os.path.join(self.tmp, "homes")])
        self.assertEqual(Path(o).read_text(), "ORIGINAL")
        self.assertFalse(os.path.exists(c))
        trash = os.path.join(home, ".Trash", "jane.doe", "Desktop", os.path.basename(c))
        self.assertEqual(Path(trash).read_text(), "CONFLICT")

    def test_dry_run_changes_nothing_and_the_trash_is_not_swept(self):
        home = os.path.join(self.tmp, "homes", "jane.doe")
        o, c = self._pair(os.path.join(home, "Documents"), 600, 60)
        r = cloud.sweep(dry_run=True, roots=[os.path.join(self.tmp, "homes")])
        self.assertEqual(len(r["moved"]), 1)
        self.assertTrue(os.path.exists(o) and os.path.exists(c))
        # a conflict copy already in the Trash is left alone
        t = os.path.join(home, ".Trash", "jane.doe")
        self._pair(t, 600, 60)
        cloud.sweep(roots=[os.path.join(self.tmp, "homes")])
        self.assertEqual(len(os.listdir(t)), 2 + 1 + 1)   # the pair in the Trash, plus this sweep's Documents/ and manifest

    def test_a_share_conflict_lands_in_a_trash_too(self):
        o, c = self._pair(os.path.join(self.tmp, "shares", "church", "Sunday"), 600, 60)
        r = cloud.sweep(roots=[os.path.join(self.tmp, "shares")])
        self.assertNotIn("error", r["moved"][0])
        self.assertTrue(os.path.exists(r["moved"][0]["trash"]))
        self.assertEqual(Path(o).read_text(), "CONFLICT")


# ---- the home is Nextcloud's files ---------------------------------------------------------
class Homes(Real):
    def test_link_home(self):
        data = os.path.join(self.tmp, "apps", "nextcloud", "data")
        r = cloud.link_home("jane.doe", data_dir=data, uid=os.getuid())
        self.assertTrue(r["ok"], r)
        self.assertEqual(os.readlink(os.path.join(data, "jane.doe", "files")), "/homes/jane.doe")
        self.assertTrue(cloud.link_home("jane.doe", data_dir=data, uid=os.getuid())["already"])
        # an empty real folder (Nextcloud made one at a first sign-in) is replaced by the link
        os.makedirs(os.path.join(data, "sam.lee", "files"))
        self.assertTrue(cloud.link_home("sam.lee", data_dir=data, uid=os.getuid())["ok"])
        self.assertTrue(os.path.islink(os.path.join(data, "sam.lee", "files")))
        # one holding files is never hidden behind a link
        os.makedirs(os.path.join(data, "kim.ng", "files"))
        open(os.path.join(data, "kim.ng", "files", "keep.txt"), "w").close()
        r = cloud.link_home("kim.ng", data_dir=data, uid=os.getuid())
        self.assertFalse(r["ok"])
        self.assertTrue(os.path.exists(os.path.join(data, "kim.ng", "files", "keep.txt")))
        self.assertFalse(cloud.link_home("../etc", data_dir=data)["ok"])

    @unittest.skipUnless(hasattr(os, "geteuid") and os.geteuid() == 0, "needs root to own files as two users")
    def test_files_nextcloud_writes_go_back_to_the_homes_owner(self):
        homes = os.path.join(self.tmp, "homes")
        home = os.path.join(homes, "jane.doe")
        os.makedirs(os.path.join(home, "Documents"))
        os.chown(home, 1234, 1234)
        f = os.path.join(home, "Documents", "from-the-phone.jpg")
        open(f, "w").close()
        os.chown(f, 33, 33)
        self.assertEqual(cloud.owner_fix(f, homes, www_uid=33), (1234, 1234))
        os.chown(f, 1234, 1234)
        self.assertIsNone(cloud.owner_fix(f, homes, www_uid=33))           # already theirs
        self.assertIsNone(cloud.owner_fix(os.path.join(self.tmp, "shares", "x"), homes, www_uid=33))   # shares keep theirs

    def test_acl_plan(self):
        lines = [" ".join(a) for a in cloud.acl_plan(["jane.doe", "bad name"])]
        self.assertTrue(any(l.endswith(os.path.join(self.tmp, "homes", "jane.doe")) and "u:33:rwX,d:u:33:rwX,u:jane.doe:rwX" in l for l in lines))
        self.assertFalse(any("bad name" in l for l in lines))
        self.assertTrue(any(l.endswith(os.path.join(self.tmp, "pastors")) for l in lines))


# ---- device app passwords -------------------------------------------------------------------
class FakeOcc:
    """What `occ user:auth-tokens:*` does in Nextcloud 29 (core/Command/User/AuthTokens), for one box."""
    def __init__(self):
        self.tokens, self.next, self.calls = {}, 1, []

    def __call__(self, argv, env=None):
        self.calls.append((list(argv), env))
        cmd = argv[0]
        if cmd == "user:auth-tokens:add":
            tok = "".join(__import__("random").choice("ABCDEFabcdef0123456789") for _ in range(72))
            self.tokens[self.next] = {"id": self.next, "user": argv[1], "name": "cli", "lastActivity": 1793260000 + self.next, "type": 1}
            self.next += 1
            return {"ok": True, "out": f"app password:\n{tok}\n", "err": ""}
        if cmd == "user:auth-tokens:list":
            rows = [{k: v for k, v in t.items() if k != "user"} for t in self.tokens.values() if t["user"] == argv[1]]
            return {"ok": True, "out": json.dumps(rows), "err": ""}
        if cmd == "user:auth-tokens:delete":
            ok = self.tokens.pop(int(argv[2]), None) is not None
            return {"ok": ok, "out": "", "err": "" if ok else "not found"}
        return {"ok": True, "out": "", "err": ""}


class Devices(Real):
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.tmp, "homes", "jane.doe"))
        self.occ = FakeOcc()

    def test_issue_once_keep_only_a_hash(self):
        r = cloud.app_password("jane.doe", "Office iMac", by="bradly", runner=self.occ)
        self.assertTrue(r["ok"], r)
        self.assertEqual(len(r["app_password"]), 72)
        self.assertEqual(r["server"], "https://cloud.ad.arisecenla.com")
        stored = Path(os.path.join(self.tmp, "state", "cloud-devices.json")).read_text()
        self.assertNotIn(r["app_password"], stored)
        row = json.loads(stored)["jane.doe"]["Office iMac"]
        self.assertEqual(row["sha256"], hashlib.sha256(r["app_password"].encode()).hexdigest())
        self.assertEqual(row["token_id"], 1)
        # no login password behind the token: Nextcloud never holds or re-checks a domain password
        add = [c for c in self.occ.calls if c[0][0] == "user:auth-tokens:add"]
        self.assertEqual(add[0], (["user:auth-tokens:add", "jane.doe"], None))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "homes", "jane.doe", "Desktop")))
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "homes", "jane.doe", "Documents")))
        self.assertEqual(os.readlink(os.path.join(self.tmp, "apps", "nextcloud", "data", "jane.doe", "files")), "/homes/jane.doe")
        log = Path(os.path.join(self.tmp, "state", "audit.jsonl")).read_text()
        self.assertIn("cloud.app_password", log)
        self.assertNotIn(r["app_password"], log)

    def test_again_for_the_same_device_replaces_the_old_one(self):
        cloud.app_password("jane.doe", "Office iMac", runner=self.occ)
        cloud.app_password("jane.doe", "iPhone", runner=self.occ)
        cloud.app_password("jane.doe", "Office iMac", runner=self.occ)
        self.assertEqual(sorted(self.occ.tokens), [2, 3])

    def test_revoke_one_device_then_all(self):
        cloud.app_password("jane.doe", "Office iMac", runner=self.occ)
        cloud.app_password("jane.doe", "iPhone", runner=self.occ)
        r = cloud.revoke("jane.doe", "iPhone", by="bradly", runner=self.occ)
        self.assertEqual(r["revoked"], [2])
        self.assertEqual(sorted(self.occ.tokens), [1])
        self.assertFalse(cloud.revoke("jane.doe", "Not A Device", runner=self.occ)["ok"])
        self.occ.tokens[9] = {"id": 9, "user": "jane.doe", "name": "Firefox (web)", "lastActivity": 0, "type": 0}
        r = cloud.revoke("jane.doe", None, runner=self.occ)       # someone leaving: every sign-in, web too
        self.assertEqual(sorted(r["revoked"]), [1, 9])
        self.assertEqual(self.occ.tokens, {})
        rows = json.loads(Path(os.path.join(self.tmp, "state", "cloud-devices.json")).read_text())["jane.doe"]
        self.assertTrue(all(v["revoked"] for v in rows.values()))

    def test_refusals(self):
        for user, dev in (("Jane Doe", "Mac"), ("jane.doe", ""), ("jane.doe", "x" * 61), ("arise-nextcloud", "Mac"), ("arise-sync", "Mac"), ("jane.doe", "Mac (old)")):
            self.assertFalse(cloud.app_password(user, dev, runner=self.occ)["ok"], (user, dev))
        self.assertEqual(self.occ.tokens, {})

    def test_last_sync_per_device(self):
        cloud.app_password("jane.doe", "Office iMac", runner=self.occ)
        from arise_server import directory
        real = directory.list_users
        directory.list_users = lambda: {"users": [{"name": "jane.doe"}, {"name": "arise-nextcloud"}]}
        self.addCleanup(setattr, directory, "list_users", real)
        p = cloud.people(runner=self.occ)
        jane = next(x for x in p["people"] if x["user"] == "jane.doe")
        self.assertEqual(jane["devices"][0]["device"], "Office iMac")
        self.assertNotIn("sha256", jane["devices"][0])
        self.assertTrue(jane["last_sync"].startswith("2026-"))
        self.assertNotIn("arise-nextcloud", [x["user"] for x in p["people"]])


class MacHelper(Real):
    """The helper's door: only for a nextcloud task an admin queued on that Mac."""
    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.tmp, "homes", "media-mac"))
        self.occ = FakeOcc()
        self.tasks = {"m1": [{"kind": "nextcloud", "state": "sent", "args": {"user": "media-mac", "local": "booth"}}]}
        fake = types.ModuleType("arise_server.macs")
        fake._read = lambda: {"tasks": self.tasks, "macs": {}}
        fake.agent_auth = lambda h: {"id": "m1", "name": "Media Mac", "status": "active", "church_owned": True} if h == "m1:key" else None
        # `from . import macs` reads the package's attribute once the real module has been
        # imported (other tests do), so both it and sys.modules are swapped.
        import arise_server
        self._had = sys.modules.get("arise_server.macs")
        self._had_attr = getattr(arise_server, "macs", None)
        sys.modules["arise_server.macs"] = fake
        arise_server.macs = fake
        self.addCleanup(self._unfake)

    def _unfake(self):
        import arise_server
        if self._had is None:
            sys.modules.pop("arise_server.macs", None)
        else:
            sys.modules["arise_server.macs"] = self._had
        if self._had_attr is None:
            if hasattr(arise_server, "macs"):
                delattr(arise_server, "macs")
        else:
            arise_server.macs = self._had_attr

    def test_queued_task_gets_a_password_linked_to_the_local_account(self):
        mac = {"id": "m1", "name": "Media Mac"}
        r = cloud.agent_app_password(mac, "media-mac", "booth", runner=self.occ)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["device"], "Media Mac booth")
        row = json.loads(Path(os.path.join(self.tmp, "state", "cloud-devices.json")).read_text())["media-mac"]["Media Mac booth"]
        self.assertEqual((row["mac_id"], row["local"]), ("m1", "booth"))
        self.assertEqual(cloud.revoke_mac("m1", runner=self.occ)["revoked"][0]["revoked"], [1])

    def test_no_task_no_password(self):
        mac = {"id": "m1", "name": "Media Mac"}
        for user, local in (("media-mac", "someone-else"), ("bradly", "booth"), ("media-mac", "../x")):
            self.assertFalse(cloud.agent_app_password(mac, user, local, runner=self.occ)["ok"], (user, local))
        self.tasks["m1"][0]["state"] = "done"
        self.assertFalse(cloud.agent_app_password(mac, "media-mac", "booth", runner=self.occ)["ok"])
        self.assertEqual(self.occ.tokens, {})

    def test_the_route_wants_the_mac_key(self):
        c = TestClient(app)
        r = c.post("/api/cloud/agent/app-password", data={"user": "media-mac", "local": "booth"})
        self.assertEqual(r.status_code, 401)
        self.assertTrue(r.text.startswith("ERROR"))
        r = c.post("/api/cloud/agent/app-password", data={"user": "bradly", "local": "booth"}, headers={"X-Arise-Mac": "m1:key"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("no Nextcloud task", r.text)


# ---- the routes ----------------------------------------------------------------------------------
class Routes(Base):
    def _client(self, user):
        c = TestClient(app)
        r = c.post("/api/auth/login", json={"user": user, "password": "anything"})
        self.assertEqual(r.status_code, 200, r.text)
        return c

    def test_admin_sees_the_sync_panel(self):
        c = self._client("bradly")
        st = c.get("/api/cloud").json()
        self.assertEqual(st["url"], "https://cloud.ad.arisecenla.com")
        people = c.get("/api/cloud/people").json()
        self.assertEqual(people["quota_gb"], 50)
        b = next(p for p in people["people"] if p["user"] == "bradly")
        self.assertEqual({d["device"] for d in b["devices"]}, {"Media Mac", "iPhone"})
        self.assertIn("quota", b["storage"])
        self.assertTrue(c.get("/api/cloud/conflicts").json()["conflicts"])
        r = c.post("/api/cloud/app-password", json={"user": "office", "device": "Office iPad"}).json()
        self.assertTrue(r["ok"] and r["app_password"])
        self.assertIn("Office iPad", [d["device"] for p in c.get("/api/cloud/people").json()["people"] if p["user"] == "office" for d in p["devices"]])
        self.assertTrue(c.post("/api/cloud/revoke", json={"user": "office", "device": "Office iPad"}).json()["ok"])
        self.assertFalse(c.post("/api/cloud/app-password", json={"user": "office", "device": ""}).json()["ok"])

    def test_staff_and_members_get_none_of_it(self):
        for access in ("none", "portal"):
            os.environ["ARISE_STAFF_ACCESS"] = access
            try:
                c = self._client("office")
                for m, p, body in (("GET", "/api/cloud", None), ("GET", "/api/cloud/people", None), ("GET", "/api/cloud/conflicts", None),
                                   ("POST", "/api/cloud/app-password", {"user": "office", "device": "Mine"}),
                                   ("POST", "/api/cloud/revoke", {"user": "bradly"}), ("POST", "/api/cloud/sweep", None)):
                    self.assertEqual(c.request(m, p, json=body).status_code, 403, (access, p))
            finally:
                os.environ.pop("ARISE_STAFF_ACCESS", None)


# ---- the container, Caddy, the units --------------------------------------------------------------
class Template(unittest.TestCase):
    def test_compose_publishes_on_loopback_only(self):
        doc = yaml.safe_load((ROOT / "templates" / "nextcloud" / "compose.yaml").read_text())
        published = [p for s in doc["services"].values() for p in (s.get("ports") or [])]
        self.assertEqual(published, ["127.0.0.1:8091:80"])
        nc = doc["services"]["nextcloud"]
        env = "\n".join(nc["environment"])
        self.assertIn("REDIS_HOST=redis", env)
        self.assertIn("NEXTCLOUD_ADMIN_USER=arise-sync", env)
        vols = "\n".join(nc["volumes"])
        for v in ("${ARISE_HOMES:-/srv/arise/homes}:/homes", "${ARISE_SHARES:-/srv/arise/shares}:/shares",
                  "${ARISE_SHARED:-/srv/arise/shared}:/shared", "${ARISE_PASTORS:-/srv/arise/pastors}:/pastors"):
            self.assertIn(v, vols)
        self.assertIn("cron", doc["services"])

    def test_template_starts_by_default_with_generated_secrets(self):
        t = yaml.safe_load((ROOT / "templates" / "nextcloud" / "template.yaml").read_text())
        self.assertTrue(t["autostart"])
        for k in ("DB_PASSWORD", "NEXTCLOUD_ADMIN_PASSWORD", "LDAP_BIND_PASSWORD"):
            self.assertTrue(str(t["env"][k]).startswith("CHANGE-ME"), k)
        for c in t["theme"]["commands"]:
            self.assertEqual(c[:4], ["-u", "www-data", "nextcloud", "php"])

    def test_caddy_serves_it_on_the_church_certificate(self):
        txt = (ROOT / "config" / "caddy" / "Caddyfile").read_text()
        block = txt.split("cloud.ad.arisecenla.com {")[1].split("\n}")[0]
        self.assertIn("tls internal", block)
        self.assertIn("reverse_proxy 127.0.0.1:8091", block)

    def test_the_units(self):
        sd = ROOT / "config" / "systemd"
        svc = (sd / "arise-cloud-conflicts.service").read_text()
        self.assertIn("ExecCondition=/usr/local/bin/arisectl service-now --quiet", svc)
        self.assertIn("arisectl cloud sweep --quiet", svc)
        self.assertIn("OnCalendar=hourly", (sd / "arise-cloud-conflicts.timer").read_text())
        self.assertIn("ExecStart=/usr/local/bin/arisectl cloud watch", (sd / "arise-cloud-watch.service").read_text())

    def test_the_installer_sets_it_up(self):
        sh = (ROOT / "installer" / "install.sh").read_text()
        self.assertIn("arisectl cloud setup", sh)
        self.assertIn("inotify-tools", sh)
        self.assertIn("cloud CNAME", sh)


# ---- mac/helper/tasks/nextcloud.sh -------------------------------------------------------------------
class Script(unittest.TestCase):
    def setUp(self):
        self.src = SCRIPT.read_text()

    def test_syntax_and_executable(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        self.assertTrue(os.access(SCRIPT, os.X_OK))

    def test_installs_only_nextclouds_signed_package(self):
        self.assertIn('TEAM_ID="NKUJUXUJ3B"', self.src)
        self.assertIn(self_version := 'VERSION_WANTED="3.14.3"', self.src)
        self.assertIn(config.DEFAULTS["cloud"]["client_version"], self_version)
        self.assertIn(config.DEFAULTS["cloud"]["client_team_id"], self.src)
        self.assertIn("pkgutil --check-signature", self.src)
        self.assertIn("Developer ID Installer: Nextcloud GmbH ($TEAM_ID)", self.src)
        self.assertIn("spctl --assess --type install", self.src)
        self.assertIn("codesign --verify --deep --strict", self.src)
        self.assertIn("macOS-vfs.pkg", self.src)       # the File Provider build: the shares on demand

    def test_both_argument_styles_and_no_domain_password(self):
        for opt in ("--user|--server-user)", "--local|--local-user)", "--server|--server-url)"):
            self.assertIn(opt, self.src)
        self.assertIn("/api/cloud/agent/app-password", self.src)
        self.assertIn("-H @-", self.src)                       # the Mac key goes on stdin, not in ps
        self.assertNotRegex(self.src, r"--password[ =]")       # it never takes a password on its command line
        self.assertNotIn("dscl . -passwd", self.src)            # nor touches the local login
        self.assertIn("tmutil localsnapshot", self.src)
        self.assertIn("promptDeleteAllFiles -bool true", self.src)
        self.assertIn("useNewBigFolderSizeLimit -bool false", self.src)

    def test_it_deletes_nothing_of_the_persons(self):
        for line in self.src.splitlines():
            s = line.strip()
            if s.startswith("#") or not re.search(r"\brm\b", s):
                continue
            self.assertRegex(s, r'rm (-P|-f|-rf) "?\$(work|PWFILE|st|tmp|HOME/Library/LaunchAgents/\$FIRSTRUN_LABEL\.plist)', s)

    def test_check_mode_on_linux_refuses_without_root_or_names(self):
        r = subprocess.run(["bash", str(SCRIPT), "--user", "Not Valid", "--check"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(r.stdout.strip().splitlines()[-1].startswith("FAILED:"))

    def test_config_editing_against_a_sample_nextcloud_cfg(self):
        with tempfile.TemporaryDirectory() as t:
            cfgp = os.path.join(t, "nextcloud.cfg")
            with open(cfgp, "w") as f:
                f.write("[General]\nclientVersion=3.14.3\n\n[Accounts]\n"
                        "0\\Folders\\1\\ignoreHiddenFiles=false\n0\\Folders\\1\\journalPath=.sync_abc.db\n"
                        "0\\Folders\\1\\localPath=/Users/kristina/Desktop/\n0\\Folders\\1\\paused=false\n"
                        "0\\Folders\\1\\targetPath=/Desktop\n0\\Folders\\1\\version=2\n0\\Folders\\1\\virtualFilesMode=off\n"
                        "0\\dav_user=kristina.robinson\n0\\url=https://cloud.ad.arisecenla.com\nversion=2\n")
            prog = f'''. "{SCRIPT}"; c="{cfgp}"
                echo "idx=$(account_index "$c" kristina.robinson cloud.ad.arisecenla.com)"
                account_index "$c" someone.else cloud.ad.arisecenla.com || echo "other=none"
                account_index "$c" kristina.robinson other.host || echo "host=none"
                has_pair "$c" 0 /Users/kristina/Desktop && echo desktop=yes
                has_pair "$c" 0 /Users/kristina/Documents || echo documents=no
                add_pair "$c" 0 /Users/kristina/Documents /Documents
                has_pair "$c" 0 /Users/kristina/Documents && echo documents=yes'''
            r = subprocess.run(["bash", "-c", prog], capture_output=True, text=True, env=dict(os.environ, ARISE_NC_LIB="1"))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.split(), ["idx=0", "other=none", "host=none", "desktop=yes", "documents=no", "documents=yes"])
            body = Path(cfgp).read_text()
            self.assertIn("0\\Folders\\2\\localPath=/Users/kristina/Documents/\n", body)
            self.assertIn("0\\Folders\\2\\targetPath=/Documents\n", body)
            self.assertIn("0\\Folders\\2\\virtualFilesMode=off\n", body)
            self.assertIn("0\\Folders\\1\\journalPath=.sync_abc.db\n", body)      # the first pair untouched
            self.assertIn("0\\dav_user=kristina.robinson\n", body)

    def test_the_old_copy_agent_stands_down(self):
        self.assertIn("Library/Preferences/Nextcloud/nextcloud.cfg", (ROOT / "mac" / "arise-home-sync.sh").read_text())


if __name__ == "__main__":
    unittest.main()
