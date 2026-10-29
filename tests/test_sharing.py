"""Round 5: storage, sharing and privacy (docs/ANSWERS.md, round 5, rows 12-20, 23, 36).

What is pinned:
- the Samba lines and the ACL plan for the Church, department, Pastors and Shared-with-me folders;
- a share writes ACLs for only what it adds, and revoke takes back only that;
- the Pastors folder is hidden from everyone but the two pastors, admins included,
  in listings, search, recent and the Trash;
- Share with…: recipient's sidebar, revoke by the sharer or an admin, members share only their own;
- the 50 GB home quota refuses an upload past it; Previous Versions reach 90 days;
- the backup target: the first ready one, red when none is;
- an admin opening someone else's home is audited, at most once per folder per 10 minutes;
- the network scan is for admins only.
The ACL tests run real setfacl on a temp dir where the tools exist, and skip otherwise.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["ARISE_DEMO"] = "1"
os.environ["ARISE_CONFIG"] = str(ROOT / "config" / "arise.toml.example")

from fastapi.testclient import TestClient  # noqa: E402

from arise_server import audit, config, demo_state, sharing  # noqa: E402
from arise_server.main import app  # noqa: E402


def client(user="bradly"):
    c = TestClient(app)
    if user:
        r = c.post("/api/auth/login", json={"user": user, "password": "anything"})
        assert r.status_code == 200, r.text
    return c


class Base(unittest.TestCase):
    # These tests sign in as staff and members through the dashboard: the "portal" setting.
    # The default since Oct 28 is "none" (staff use their Macs), pinned in test_desktop_r5.
    def setUp(self):
        os.environ["ARISE_STAFF_ACCESS"] = "portal"
        self.addCleanup(os.environ.pop, "ARISE_STAFF_ACCESS", None)
        self.cfg = config.load(force=True)
        demo_state.reset()
        sharing._seen_home.clear()
        sharing._target_cache.clear()


# ---- the folders: Samba lines and ACLs (rows 16-18, 36) ----------------------------
class Folders(Base):
    def test_church_folder_every_account_writes(self):
        conf = sharing.smb_conf()
        block = conf.split("[church]")[1].split("\n[")[0]
        self.assertIn('valid users = @"ARISE\\Domain Users"', block)
        self.assertIn("read only = no", block)
        self.assertEqual(sharing.folder_access("church", "anyone", [], False), "write")

    def test_departments_staff_and_account_write_members_read(self):
        conf = sharing.smb_conf()
        block = conf.split("[media]")[1].split("\n[")[0]
        self.assertIn("read only = yes", block)
        self.assertIn('write list = @"ARISE\\Staff" @"ARISE\\Domain Admins"', block)
        self.assertIn("media-mac", block)                      # the booth Mac keeps its write
        self.assertIn('@"ARISE\\Media"', block.split("valid users")[1].split("\n")[0])
        fa = sharing.folder_access
        self.assertEqual(fa("media", "jane.doe", ["Staff"], False), "write")          # all staff
        self.assertEqual(fa("media", "media-mac", [], False), "write")                # its own account
        self.assertEqual(fa("media", "bradly", ["Domain Admins"], True), "write")     # admins
        self.assertEqual(fa("media", "volunteer", ["Media"], False), "read")          # in the department
        self.assertIsNone(fa("media", "volunteer", ["Worship"], False))               # not in it
        self.assertEqual(sharing.department_accounts("childrens-department"), {"childrens-department", "childrens.department"})

    def test_alexandria_from_day_one(self):
        self.assertIn("alexandria", sharing.departments())
        self.assertIn("[alexandria]", sharing.smb_conf())
        self.assertIn("Alexandria", (ROOT / "installer" / "install.sh").read_text())

    def test_pastors_share_is_theirs_alone_and_hidden(self):
        conf = sharing.smb_conf()
        block = conf.split("[pastors]")[1].split("\n[")[0]
        self.assertIn("valid users = bryant.sanders vanessa.sanders", block)
        self.assertIn("browseable = no", block)
        self.assertNotIn("Domain Admins", block)
        self.assertNotIn("admin users", block)
        self.assertEqual(sharing.audit_rule(), f"-w {sharing.pastors_path()} -p rwxa -k arise-pastors")

    def test_netbios_comes_from_config(self):
        self.assertIn('@"CHURCH\\Staff"', sharing.smb_conf(netbios="CHURCH"))
        self.assertNotIn("AD.ARISECENLA", sharing.smb_conf())

    def test_acl_plan_leaves_out_accounts_that_do_not_exist(self):
        plan = sharing.acl_plan(exists=lambda n: n != "childrens-department")
        line = next(c for c in plan if c[0] == "setfacl" and c[-1].endswith("/childrens-department"))
        self.assertIn("u:childrens.department:rwx", line[2])
        self.assertNotIn("u:childrens-department:", line[2])
        self.assertIn("g:Staff:rwx", line[2])
        self.assertIn("o::---", line[2])
        pp = next(c for c in plan if c[0] == "setfacl" and c[-1] == sharing.pastors_path())
        self.assertIn("u:bryant.sanders:rwx", pp[2])
        self.assertIn("g::---", pp[2])
        self.assertIn(["chmod", "2775", os.path.join(self.cfg.system.data_root, "shares", "church")], plan)

    def test_shares_folders_dry_run_route(self):
        r = client().post("/api/shares/folders", json={"dry_run": True}).json()
        self.assertTrue(r["ok"])
        self.assertIn("[pastors]", r["conf"])
        self.assertTrue(r["acls"])

    def test_template_leaves_the_department_shares_to_arise_folders(self):
        tpl = (ROOT / "config" / "samba" / "smb.conf.template").read_text()
        for d in ("[media]", "[worship]", "[kids]", "[church]", "[pastors]"):
            self.assertNotIn(d, tpl)


# ---- Share with… (row 19) ----------------------------------------------------------
class ShareWith(Base):
    def test_acl_cmds_grant_and_traverse(self):
        cmds = sharing.acl_cmds("/srv/arise/homes/bradly/Docs/Setlist.pdf", "u:office", "read", "/srv/arise/homes/bradly", False)
        self.assertEqual(cmds[0], ["setfacl", "-m", "u:office:rX", "/srv/arise/homes/bradly/Docs/Setlist.pdf"])
        self.assertIn(["setfacl", "-m", "u:office:--x", "/srv/arise/homes/bradly/Docs"], cmds)
        self.assertIn(["setfacl", "-m", "u:office:--x", "/srv/arise/homes/bradly"], cmds)
        self.assertNotIn("/srv/arise/homes", [c[-1] for c in cmds])
        d = sharing.acl_cmds("/srv/arise/homes/bradly/Docs", "g:Worship", "write", "/srv/arise/homes/bradly", True)
        self.assertEqual(d[0], ["setfacl", "-R", "-m", "g:Worship:rwX", "/srv/arise/homes/bradly/Docs"])
        self.assertEqual(d[1], ["setfacl", "-R", "-d", "-m", "g:Worship:rwX", "/srv/arise/homes/bradly/Docs"])

    def test_a_share_never_touches_what_was_there_before(self):
        # g:Staff already has its own entry on the department folder: the share neither changes it
        # nor, on revoke, takes it away.
        had = lambda pr, p: p == "/srv/arise/shares/media"
        cmds, added = sharing.plan_grant("/srv/arise/shares/media/loops/a.mov", "g:Staff", "read", "/srv/arise/shares/media", False, had=had)
        self.assertNotIn("/srv/arise/shares/media", [c[-1] for c in cmds])
        self.assertEqual(added, ["/srv/arise/shares/media/loops/a.mov", "/srv/arise/shares/media/loops"])
        g = {"abs": "/srv/arise/shares/media/loops/a.mov", "perm": "read", "dir": False, "acl_added": {"g:Staff": added}}
        rv = sharing.plan_revoke(g, "g:Staff", [])
        self.assertIn(["setfacl", "-x", "g:Staff", "/srv/arise/shares/media/loops/a.mov"], rv)
        self.assertIn(["setfacl", "-x", "g:Staff", "/srv/arise/shares/media/loops"], rv)
        self.assertNotIn("/srv/arise/shares/media", [c[-1] for c in rv])
        # another share for the same group still needs the traverse on loops/
        other = {"abs": "/srv/arise/shares/media/loops/b.mov", "acl_added": {"g:Staff": ["/srv/arise/shares/media/loops/b.mov", "/srv/arise/shares/media/loops"]}}
        rv2 = sharing.plan_revoke(g, "g:Staff", [other])
        self.assertNotIn(["setfacl", "-x", "g:Staff", "/srv/arise/shares/media/loops"], rv2)
        self.assertTrue(sharing.has_entry("# file: x\nuser::rwx\ngroup:Staff:rwx\nmask::rwx\n", "g:Staff"))
        self.assertFalse(sharing.has_entry("user::rwx\ngroup::r-x\n", "g:Staff"))

    def test_link_names(self):
        self.assertEqual(sharing.link_name("Setlist.pdf", "bradly", lambda n: False), "Setlist (from bradly).pdf")
        self.assertEqual(sharing.link_name("Notes", "bradly", lambda n: False), "Notes (from bradly)")
        self.assertEqual(sharing.link_name(".hidden", "bradly", lambda n: False), ".hidden (from bradly)")
        taken = {"Setlist (from bradly).pdf"}
        self.assertEqual(sharing.link_name("Setlist.pdf", "bradly", taken.__contains__), "Setlist (from bradly 2).pdf")

    def test_share_shows_in_recipient_sidebar_and_revoke(self):
        admin = client()
        r = admin.post("/api/files/share", json={"root": "home", "path": "/Documents", "to": ["office"], "perm": "read"}).json()
        self.assertTrue(r["ok"], r)
        sid = r["share"]["id"]
        self.assertEqual(r["share"]["link"], "Documents (from bradly)")
        self.assertIn("push", r["notified"])
        self.assertIn(sid, [x["id"] for x in admin.get("/api/files/shared").json()["by_me"]])
        office = client("office")
        roots = office.get("/api/files/roots").json()["roots"]
        mine = [x for x in roots if x["id"] == "shared:" + sid]
        self.assertEqual(len(mine), 1)
        self.assertFalse(mine[0]["writable"])
        self.assertEqual(office.get("/api/files/shared").json()["with_me"][0]["id"], sid)
        lst = office.get("/api/files/list", params={"root": "shared:" + sid, "path": "/"}).json()
        self.assertNotIn("error", lst)
        # the recipient cannot revoke it; the sharer can
        self.assertFalse(office.delete(f"/api/files/share/{sid}").json()["ok"])
        self.assertTrue(admin.delete(f"/api/files/share/{sid}").json()["ok"])
        self.assertNotIn("shared:" + sid, [x["id"] for x in office.get("/api/files/roots").json()["roots"]])
        acts = [e["action"] for e in audit.recent(50)["events"]]
        self.assertIn("files.share", acts)
        self.assertIn("files.share.revoke", acts)

    def test_group_share_reaches_its_members(self):
        admin = client()
        r = admin.post("/api/files/share", json={"root": "home", "path": "/Documents", "to": ["@Staff"], "perm": "write"}).json()
        self.assertTrue(r["ok"], r)
        self.assertIn("office", demo_state.get("sharing.grants", list)[0]["users"])
        roots = client("office").get("/api/files/roots").json()["roots"]
        self.assertTrue(next(x for x in roots if x["id"] == "shared:" + r["share"]["id"])["writable"])

    def test_bad_shares_are_refused_with_words(self):
        admin = client()
        self.assertIn("pick a person", admin.post("/api/files/share", json={"path": "/Documents", "to": []}).json()["err"])
        self.assertIn("not a person", admin.post("/api/files/share", json={"path": "/Documents", "to": ["nobody.here"]}).json()["err"])
        self.assertIn("already have", admin.post("/api/files/share", json={"path": "/Documents", "to": ["bradly"]}).json()["err"])
        self.assertIn("no such", admin.post("/api/files/share", json={"path": "/Nope.txt", "to": ["office"]}).json()["err"])

    def test_members_share_only_their_own_files(self):
        office = client("office")
        roots = [x["id"] for x in office.get("/api/files/roots").json()["roots"]]
        other = next(r for r in roots if r.startswith("share:"))
        lst = office.get("/api/files/list", params={"root": other, "path": "/"}).json()["entries"]
        if lst:
            r = office.post("/api/files/share", json={"root": other, "path": "/" + lst[0]["name"], "to": ["bradly"]}).json()
            self.assertFalse(r["ok"])
            self.assertIn("only your own", r["err"])
        mine = office.get("/api/files/list", params={"root": "home", "path": "/"}).json()["entries"]
        self.assertTrue(mine)
        self.assertTrue(office.post("/api/files/share", json={"root": "home", "path": "/" + mine[0]["name"], "to": ["bradly"]}).json()["ok"])

    def test_people_list_for_staff_typed_for_others(self):
        p = client().get("/api/files/share/people").json()
        self.assertFalse(p["typed"])
        self.assertNotIn("Pastors", p["groups"])
        self.assertIn("office", [u["name"] for u in p["people"]])


# ---- the Pastors folder (row 18) ---------------------------------------------------
class Pastors(Base):
    def test_hidden_from_admins_everywhere(self):
        bradly = client()
        top = [e["name"] for e in bradly.get("/api/files/list", params={"root": "data", "path": "/"}).json()["entries"]]
        self.assertNotIn("pastors", top)
        self.assertIn("error", bradly.get("/api/files/list", params={"root": "data", "path": "/pastors"}).json())
        self.assertNotIn("pastors", [r["id"] for r in bradly.get("/api/files/roots").json()["roots"]])
        hits = bradly.get("/api/search", params={"q": "Counsel"}).json().get("hits", [])
        self.assertFalse([h for h in hits if "Counsel" in h.get("name", "")])
        rec = bradly.get("/api/files/recent").json().get("hits", [])
        self.assertFalse([h for h in rec if "pastors" in h.get("path", "")])
        self.assertFalse(bradly.post("/api/files/share", json={"root": "data", "path": "/pastors/Counsel follow-ups.docx", "to": ["office"]}).json()["ok"])

    def test_visible_to_the_pastors(self):
        bryant = client("bryant.sanders")
        roots = [r["id"] for r in bryant.get("/api/files/roots").json()["roots"]]
        self.assertIn("pastors", roots)
        names = [e["name"] for e in bryant.get("/api/files/list", params={"root": "pastors", "path": "/"}).json()["entries"]]
        self.assertIn("Counsel follow-ups.docx", names)

    def test_trash_from_the_pastors_folder_stays_theirs(self):
        bryant = client("bryant.sanders")
        r = bryant.post("/api/files/trash", json={"root": "pastors", "path": "/Counsel follow-ups.docx", "confirm": "Counsel follow-ups.docx"}).json()
        self.assertTrue(r.get("ok"), r)
        self.assertIn("Counsel follow-ups.docx", [i["name"] for i in bryant.get("/api/files/trash").json()["items"]])
        self.assertNotIn("Counsel follow-ups.docx", [i["name"] for i in client().get("/api/files/trash").json()["items"]])

    def test_hidden_rule(self):
        pp = sharing.pastors_path()
        self.assertTrue(sharing.hidden(pp + "/x.docx", {"user": "bradly", "role": "admin"}))
        self.assertFalse(sharing.hidden(pp + "/x.docx", {"user": "vanessa.sanders", "role": "admin"}))
        self.assertFalse(sharing.hidden(pp + "/x.docx", None))           # the system itself (backups)
        self.assertFalse(sharing.hidden(pp + "-other/x", {"user": "bradly", "role": "admin"}))


# ---- an admin opening someone else's home (row 20) ---------------------------------
class HomeAudit(Base):
    def test_once_per_folder_per_ten_minutes(self):
        homes = self.cfg.directory.homes_path
        n0 = len([e for e in audit.recent(500)["events"] if e["action"] == "files.home.open"])
        me = {"user": "bradly", "role": "admin"}
        f = f"{homes}/office/Documents/Budget.xlsx"
        sharing.note_access(f, me, "open")
        sharing.note_access(f, me, "open")                                      # same folder, same ten minutes
        sharing.note_access(f"{homes}/bradly/Documents/x.txt", me, "open")      # his own: never
        sharing.note_access(f, {"user": "office", "role": "member"}, "open")    # not an admin: not this rule
        n1 = len([e for e in audit.recent(500)["events"] if e["action"] == "files.home.open"])
        self.assertEqual(n1 - n0, 1)
        k = ("bradly", os.path.normpath(f"{homes}/office/Documents"))
        sharing._seen_home[k] -= sharing.HOME_AUDIT_EVERY + 1
        sharing.note_access(f, me, "open")
        self.assertEqual(len([e for e in audit.recent(500)["events"] if e["action"] == "files.home.open"]) - n0, 2)

    def test_demo_listing_records_it(self):
        client().get("/api/files/list", params={"root": "data", "path": "/homes/office"})
        ev = [e for e in audit.recent(100)["events"] if e["action"] == "files.home.open"]
        self.assertTrue(ev)
        self.assertEqual(ev[0]["target"], "office")


# ---- quota, versions, backup targets (rows 12-15) ----------------------------------
class Storage(Base):
    def test_quota_numbers(self):
        q = client().get("/api/files/quota", params={"user": "bradly"}).json()
        self.assertEqual(q["quota"], 50 * 1024 ** 3)
        self.assertFalse(q["warn"])
        demo_state.put("storage.home_usage", {"bradly": int(46 * 1024 ** 3)})
        q = client().get("/api/files/quota", params={"user": "bradly"}).json()
        self.assertTrue(q["warn"])                                               # 92 %: the 90 % warning
        self.assertFalse(q["full"])
        self.assertIsNotNone(sharing.quota_refusal_demo("/homes/bradly/Documents", 5 * 1024 ** 3))
        self.assertIsNone(sharing.quota_refusal_demo("/homes/bradly/Documents", 1024))
        self.assertIsNone(sharing.quota_refusal_demo("/shares/church", 10 * 1024 ** 3))

    def test_upload_past_the_quota_is_refused(self):
        demo_state.put("storage.home_usage", {"bradly": int(49.9 * 1024 ** 3)})
        r = client().post("/api/files/upload/start", json={"root": "data", "path": "/homes/bradly", "name": "big.mov", "size": 2 * 1024 ** 3, "fingerprint": "x"}).json()
        self.assertFalse(r["ok"])
        self.assertIn("quota", r["err"])
        r = client().post("/api/files/upload/start", json={"root": "data", "path": "/homes/bradly", "name": "small.txt", "size": 1024, "fingerprint": "y"}).json()
        self.assertTrue(r["ok"], r)

    def test_members_see_only_their_own_quota(self):
        office = client("office")
        self.assertEqual(office.get("/api/files/quota").json()["user"], "office")
        self.assertEqual(office.get("/api/files/quota", params={"user": "bradly"}).status_code, 403)
        self.assertEqual(office.get("/api/storage/quotas").status_code, 403)
        self.assertIn("homes", client().get("/api/storage/quotas").json())

    def test_real_quota_refusal_on_a_temp_home(self):
        d = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(d, "office"))
            with open(os.path.join(d, "office", "a.bin"), "wb") as f:
                f.write(b"x" * 4096)
            old_demo, old_home, old_q = self.cfg.demo, self.cfg.directory.homes_path, self.cfg.storage.home_quota_gb
            self.cfg.demo, self.cfg.directory.homes_path, self.cfg.storage.home_quota_gb = False, d, 8192 / 1024 ** 3
            try:
                sharing._usage_cache.clear()
                self.assertIsNone(sharing.quota_refusal(os.path.join(d, "office"), 1000))
                self.assertIn("quota", sharing.quota_refusal(os.path.join(d, "office", "sub"), 8000))
                self.assertIsNone(sharing.quota_refusal("/somewhere/else", 10 ** 12))
                self.assertEqual(sharing.setquota_cmd("office", "/srv"), ["setquota", "-u", "office", "8", "8", "0", "0", "/srv"])
            finally:
                self.cfg.demo, self.cfg.directory.homes_path, self.cfg.storage.home_quota_gb = old_demo, old_home, old_q
                sharing._usage_cache.clear()
        finally:
            shutil.rmtree(d)

    def test_versions_reach_ninety_days(self):
        now = datetime(2026, 10, 28, 12, 0)
        rows = [{"time": (now - timedelta(days=n)).isoformat(timespec="seconds")} for n in (1, 45, 89, 91, 120)]
        kept = sharing.within_versions(rows, now=now)
        self.assertEqual(len(kept), 3)
        self.assertEqual(self.cfg.storage.versions_days, 90)

    def test_backup_target_first_ready_and_red_when_none(self):
        old_demo, old_home = self.cfg.demo, self.cfg.backups.arise_home_repo
        self.cfg.demo, self.cfg.backups.arise_home_repo = False, "sftp:arise-backup@arise-home:/srv/arise/backups/restic-pineville"
        try:
            t = sharing.backup_targets(probe={"synology": lambda: False, "arise-home": lambda: True})
            self.assertEqual(t["live"], "arise-home")
            self.assertIsNone(t["error"])
            t = sharing.backup_targets(probe={"synology": lambda: True, "arise-home": lambda: True})
            self.assertEqual(t["live"], "synology")
            t = sharing.backup_targets(probe={"synology": lambda: False, "arise-home": lambda: False})
            self.assertIsNone(t["live"])
            self.assertIn("no backup target", t["error"])
            self.assertEqual(sharing._sftp_host("sftp:arise-backup@arise-home:/x"), "arise-backup@arise-home")
        finally:
            self.cfg.demo, self.cfg.backups.arise_home_repo = old_demo, old_home
            sharing._target_cache.clear()

    def test_homes_on_synology_moves_the_homes(self):
        p = Path(tempfile.mkdtemp()) / "arise.toml"
        try:
            p.write_text('[storage]\nhomes_on = "synology"\n[nas]\nmount = "/mnt/synology"\n')
            cfg = config.load(path=str(p), force=True)
            self.assertEqual(str(cfg.directory.homes_path), "/mnt/synology/arise/homes")
            self.assertTrue(str(cfg.nas.host).startswith("synology."))
        finally:
            shutil.rmtree(p.parent)
            config.load(force=True)


# ---- the network scan is admins only (row 23) --------------------------------------
class Devices(Base):
    def test_members_get_403(self):
        office = client("office")
        for path in ("/api/devices", "/api/devices/behind", "/api/devices/cameras"):
            self.assertEqual(office.get(path).status_code, 403, path)
        self.assertEqual(client().get("/api/devices").status_code, 200)


# ---- real ACLs on a temp dir, where the tools exist --------------------------------
@unittest.skipUnless(shutil.which("setfacl") and shutil.which("getfacl"), "setfacl/getfacl not installed here")
class RealAcls(unittest.TestCase):
    def test_grant_and_revoke_on_disk(self):
        d = tempfile.mkdtemp()
        try:
            home = os.path.join(d, "bradly")
            os.makedirs(os.path.join(home, "Docs"))
            f = os.path.join(home, "Docs", "Setlist.txt")
            Path(f).write_text("x")
            me = os.getuid()
            principal = f"u:{me}"
            for c in sharing.acl_cmds(f, principal, "read", home, False):
                subprocess.run(c, check=True)
            out = subprocess.run(["getfacl", "-cpn", f], capture_output=True, text=True).stdout
            self.assertIn(f"user:{me}:r--", out)
            self.assertTrue(sharing.has_entry(subprocess.run(["getfacl", "-cpn", home], capture_output=True, text=True).stdout, principal))
            g = {"abs": f, "perm": "read", "dir": False, "acl_added": {principal: [f, os.path.join(home, "Docs"), home]}}
            for c in sharing.plan_revoke(g, principal, []):
                subprocess.run(c, check=True)
            self.assertFalse(sharing.has_entry(subprocess.run(["getfacl", "-cpn", f], capture_output=True, text=True).stdout, principal))
        finally:
            shutil.rmtree(d)


if __name__ == "__main__":
    unittest.main()
