"""The searchable archive (docs/ARCHIVE.md; the automator's SERVER_HANDOFF.md 13.6).

Two layers:
  * A throwaway git repository made in a temp folder: the credential filter, the
    incremental update, the sha256 check on split videos, the MCP server over stdio.
    These always run.
  * The real clones of both repos, when present (ARISE_ARCHIVE_TEST_ROOT, or
    .archive-test/ in the repo folder, holding arise-youtube-automation/ and
    ProjectBackups/): the inventory reconciles, and the handoff's sample questions
    answer. They skip, saying why, when the clones are not here.

No credential is in this file: the fake token is built at runtime.
"""
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "archive"))

from arise_archive import indexer, mcp, query, secrets_filter, store  # noqa: E402
from arise_archive.config import Config  # noqa: E402

UNITS = ROOT / "config" / "systemd"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, text=True).stdout


def fake_token():
    """A refresh-token-shaped string, made fresh each run so none is ever committed."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
    return "1//0" + "".join(secrets.choice(alphabet) for _ in range(40))


def write(repo, rel, data):
    p = Path(repo) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    (p.write_bytes if isinstance(data, bytes) else p.write_text)(data)


class SyntheticRepo(unittest.TestCase):
    """One small repo shaped like the automation repo, indexed for real."""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("git"):
            raise unittest.SkipTest("git is not installed")
        cls.tmp = tempfile.mkdtemp(prefix="arise-archive-test-")
        root = Path(cls.tmp) / "root"
        cls.repo = root / "arise-youtube-automation"
        cls.repo.mkdir(parents=True)
        cls.token = fake_token()
        git(cls.repo, "init", "-q", "-b", "main")
        write(cls.repo, "song_bank.json", json.dumps({
            "We Want Revival": {"ccli": "7247827", "writers": "Hannah Yates, Jonathan Stamper, Seth Yates"},
            "Great Expectation": {"original": True, "writers": "Kristina Robinson", "note": "an Arise original; no CCLI"},
            "Praise": {"ccli": "7213077"},
        }))
        # The handoff names the patterns in prose; a mention is not a credential and must stay searchable.
        write(cls.repo, "SERVER_HANDOFF.md", "# Server handoff\n\nScan for `1//`, `GOCSPX-` and `ya29.` before any commit.\n\nThe archive is evidence, not authority.\n")
        write(cls.repo, "notes/leaked.txt", f"pasted by mistake: {cls.token}\nand the rest of the note\n")
        write(cls.repo, "token.json", json.dumps({"note": "a file named like a token is never read"}))
        write(cls.repo, "transcripts/PMVM1FhjizM.json", json.dumps({"video_id": "PMVM1FhjizM", "segments": [
            {"start": 0, "dur": 5, "text": "welcome to glory night"},
            {"start": 65, "dur": 5, "text": "the framing of the house matters more than the paint"},
        ]}))
        write(cls.repo, "GLORY_NIGHT_2026-10-19_description.txt", "Peace Is a Garrison | Apostle Bryant Sanders\n\n0:00 Welcome\n")
        good, bad = os.urandom(3000), os.urandom(2000)
        write(cls.repo, "large-videos-split/Night/good.mp4.part01", good[:1500])
        write(cls.repo, "large-videos-split/Night/good.mp4.part02", good[1500:])
        write(cls.repo, "large-videos-split/Night/bad.mp4.part01", bad)
        write(cls.repo, "large-videos-split/README.md",
              "| file | parts | size | sha256 |\n|---|---|---|---|\n"
              f"| `Night\\good.mp4` | 2 | 3000 | `{hashlib.sha256(good).hexdigest()}` |\n"
              f"| `Night\\bad.mp4` | 1 | 2000 | `{'0' * 64}` |\n")
        git(cls.repo, "add", "-A")
        git(cls.repo, "commit", "-q", "-m", "fixture")
        cls.cfg = Config(root=root, state=Path(cls.tmp) / "state",
                         repos={"arise-youtube-automation": "unused", "ProjectBackups": "unused"})
        cls.first = indexer.build(cls.cfg, pull_first=False)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_build_ok_and_accounts_for_every_tracked_file(self):
        self.assertTrue(self.first["ok"], self.first)
        r = self.first["repos"]["arise-youtube-automation"]
        self.assertEqual(r["tracked"], r["indexed_paths"] + r["skipped"] + r["not_present"])
        self.assertEqual(r["unaccounted"], 0)
        self.assertFalse(self.first["repos"]["ProjectBackups"]["cloned"])   # a missing clone is a line, not a crash

    def test_credential_content_is_skipped_by_path_never_by_match(self):
        with store.open_ro(self.cfg.index) as db:
            skipped = {r[0]: r[1] for r in db.execute("SELECT path, reason FROM skipped")}
            text = "\n".join(r[0] for r in db.execute("SELECT text FROM chunks"))
            paths = {r[0] for r in db.execute("SELECT path FROM docs")}
        self.assertIn("notes/leaked.txt", skipped)
        self.assertIn("token.json", skipped)
        self.assertNotIn(self.token, text)
        self.assertNotIn(self.token[4:20], text)
        self.assertNotIn(self.token, self.cfg.build_log.read_text())
        self.assertNotIn(self.token, self.cfg.status_file.read_text())
        self.assertIn("notes/leaked.txt", self.cfg.build_log.read_text())   # the path is reported
        self.assertIn("SERVER_HANDOFF.md", paths)                            # the rules file itself is indexed
        hits = query.search(self.cfg, "evidence authority")["results"]
        self.assertTrue(any(h["provenance"]["path"] == "SERVER_HANDOFF.md" for h in hits))

    def test_path_and_content_rules(self):
        for p in ("token.json", "a/my_token_old.json", "client_secret_123.json", "deploy_key", "deploy_key.pub", "x/server.pem", "k.key", ".git/config"):
            self.assertIsNotNone(secrets_filter.path_reason(p), p)
        for p in ("SERVER_HANDOFF.md", "tokens.md", "song_bank.json", "transcripts/abc.json"):
            self.assertIsNone(secrets_filter.path_reason(p), p)
        self.assertTrue(secrets_filter.content_has_credential(f"x {self.token} y".encode()))
        self.assertTrue(secrets_filter.content_has_credential(("GOCSPX-" + "a" * 24).encode()))
        self.assertTrue(secrets_filter.content_has_credential(("ya29." + "b" * 30).encode()))
        self.assertFalse(secrets_filter.content_has_credential(b"scan for `1//`, `GOCSPX-` and `ya29.`"))

    def test_song_lookups_are_exact(self):
        r = query.song(self.cfg, "7247827")
        self.assertEqual(r["songs"][0]["title"], "We Want Revival")
        self.assertIn("Hannah Yates", json.dumps(r))
        self.assertEqual(query.song(self.cfg, "CCLI #7247827")["songs"][0]["title"], "We Want Revival")
        g = query.song(self.cfg, "great expectation")
        self.assertEqual(g["songs"][0]["title"], "Great Expectation")
        self.assertFalse(g["songs"][0].get("ccli"))
        self.assertEqual(query.song(self.cfg, "We Want")["songs"], [])   # a partial title is not a credit

    def test_transcript_search_links_to_the_second(self):
        hits = query.search(self.cfg, "framing", kind="transcript")["results"]
        self.assertTrue(hits)
        self.assertIn("youtu.be/PMVM1FhjizM?t=", hits[0]["link"])
        t = query.get_transcript(self.cfg, "PMVM1FhjizM")
        self.assertIn("framing", json.dumps(t))

    def test_phrase_search_and_video(self):
        hits = query.search(self.cfg, '"Peace Is a Garrison"', kind="description")["results"]
        self.assertTrue(any("GLORY_NIGHT_2026-10-19" in h["provenance"]["path"] for h in hits))
        v = query.video(self.cfg, "PMVM1FhjizM")
        self.assertIn("PMVM1FhjizM", json.dumps(v))
        self.assertLess(len(json.dumps(v)), query.CAP + 500)

    def test_split_video_reassembled_only_on_a_sha256_match(self):
        asm = self.first["repos"]["arise-youtube-automation"]["assembled"]
        self.assertEqual(asm["assembled"], ["Night/good.mp4"])
        self.assertEqual(asm["refused"], ["Night/bad.mp4"])
        self.assertTrue((self.cfg.assembled / "Night" / "good.mp4").is_file())
        self.assertFalse((self.cfg.assembled / "Night" / "bad.mp4").exists())
        self.assertFalse(list(self.cfg.assembled.rglob("*.assembling")))
        with store.open_ro(self.cfg.index) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM docs WHERE path='media-assembled/Night/good.mp4'").fetchone()[0], 1)
            parts = [r[0] for r in db.execute("SELECT path FROM skipped WHERE path LIKE '%.part%'")]
        self.assertEqual(len(parts), 3)   # the pieces are skipped; the whole file is indexed

    def test_get_document_refuses_paths_outside_the_clone(self):
        # Only an indexed path is ever opened, and _safe refuses anything that resolves outside the clone.
        for bad in ("../../etc/passwd", "/etc/passwd", "notes/../../x"):
            self.assertIn("error", query.get_document(self.cfg, "arise-youtube-automation", bad))
            with self.assertRaises(ValueError):
                query._safe(self.cfg, "arise-youtube-automation", bad)
        r = query.get_document(self.cfg, "arise-youtube-automation", "token.json")   # skipped files are not served
        self.assertIn("skipped", r["error"])
        with self.assertRaises(ValueError):
            query._safe(self.cfg, "some-other-repo", "README.md")
        ok = query.get_document(self.cfg, "arise-youtube-automation", "SERVER_HANDOFF.md")
        self.assertIn("evidence, not authority", ok["text"])
        self.assertEqual(len(ok["commit"]), 40)

    def test_index_is_opened_read_only(self):
        import sqlite3
        with store.open_ro(self.cfg.index) as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM docs")

    def test_zz_incremental_update_reads_only_what_changed(self):
        # runs last in this class (zz): it moves the fixture forward one commit
        write(self.repo, "GLORY_NIGHT_2026-10-19_description.txt", "Peace Is a Garrison | Apostle Bryant Sanders\n\n0:00 Welcome\n1:05:03 Peace is a garrison\n")
        (self.repo / "notes" / "leaked.txt").unlink()
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "one change, one delete")
        head = git(self.repo, "rev-parse", "HEAD").strip()
        r = indexer.build(self.cfg, pull_first=False)
        a = r["repos"]["arise-youtube-automation"]
        self.assertTrue(r["ok"], r)
        self.assertEqual(a["mode"], "changed files")
        self.assertEqual(a["reindexed"], 1)
        self.assertEqual(a["deleted"], 1)
        self.assertEqual(a["head"], head)
        self.assertEqual(query.status(self.cfg)["indexed_commits"]["arise-youtube-automation"], head)
        hits = query.search(self.cfg, "garrison", kind="description")["results"]
        self.assertTrue(any(h["provenance"]["commit"] == head for h in hits))
        with store.open_ro(self.cfg.index) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM skipped WHERE path='notes/leaked.txt'").fetchone()[0], 0)
        again = indexer.build(self.cfg, pull_first=False)["repos"]["arise-youtube-automation"]
        self.assertEqual((again["mode"], again["reindexed"]), ("unchanged", 0))
        full = indexer.build(self.cfg, full=True, pull_first=False)
        self.assertTrue(full["ok"])
        self.assertFalse(self.cfg.index.with_name("index.sqlite.new").exists())   # swapped in, not left beside

    def test_mcp_over_stdio(self):
        env = dict(os.environ, ARISE_ARCHIVE_ROOT=str(self.cfg.root), ARISE_ARCHIVE_STATE=str(self.cfg.state))
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "song", "arguments": {"title_or_ccli": "7247827"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "get_document", "arguments": {"repo": "arise-youtube-automation", "path": "../../../etc/passwd"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "write_file", "arguments": {}}},
        ]
        p = subprocess.run([sys.executable, str(ROOT / "archive" / "arise-archive-mcp")], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                           capture_output=True, text=True, env=env, timeout=60)
        out = {m["id"]: m for m in map(json.loads, p.stdout.splitlines())}
        self.assertEqual(sorted(out), [1, 2, 3, 4, 5])                         # the notification gets no answer
        self.assertEqual(out[1]["result"]["serverInfo"]["name"], "arise-archive")
        self.assertEqual(out[1]["result"]["protocolVersion"], "2025-06-18")
        names = {t["name"] for t in out[2]["result"]["tools"]}
        self.assertEqual(names, {"search", "get_document", "get_transcript", "song", "video", "status"})
        self.assertIn("We Want Revival", out[3]["result"]["content"][0]["text"])
        self.assertTrue(out[4]["result"]["isError"])
        self.assertIn("error", out[5])
        for m in out.values():
            self.assertLess(len(json.dumps(m)), query.CAP + 4000)

    def test_tool_descriptions_repeat_the_rules(self):
        text = json.dumps(mcp.TOOLS) + mcp.RULES
        for need in ("evidence", "song_bank.json", "lyrics", "Bradly", "instructions", "past state"):
            self.assertIn(need.lower(), text.lower(), need)
        song = next(t for t in mcp.TOOLS if t["name"] == "song")
        self.assertIn("song_bank", song["description"])


class RealClones(unittest.TestCase):
    """13.6 against the real repos. Skips when the clones are not on this machine."""

    @classmethod
    def setUpClass(cls):
        base = Path(os.environ.get("ARISE_ARCHIVE_TEST_ROOT") or ROOT / ".archive-test")
        if not (base / "arise-youtube-automation" / ".git").exists():
            raise unittest.SkipTest(f"no clone of arise-youtube-automation at {base} (set ARISE_ARCHIVE_TEST_ROOT)")
        cls.tmp = tempfile.mkdtemp(prefix="arise-archive-real-")
        cls.cfg = Config(root=base, state=Path(cls.tmp))
        cls.res = indexer.build(cls.cfg, full=True, pull_first=False)
        # assembled videos go under the clone root; this build must not leave new ones behind
        cls.base = base

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_inventory_reconciles_with_ls_files(self):
        self.assertTrue(self.res["ok"], self.res)
        for name, r in self.res["repos"].items():
            if not r.get("cloned"):
                continue
            files = indexer.tracked(self.cfg.repo_dir(name))
            self.assertEqual(r["tracked"], len(files), name)
            self.assertEqual(r["tracked"], r["indexed_paths"] + r["skipped"] + r["not_present"], name)
            self.assertEqual(r["unaccounted"], 0, name)

    def test_server_handoff_is_indexed(self):
        with store.open_ro(self.cfg.index) as db:
            n = db.execute("SELECT COUNT(*) FROM docs WHERE repo='arise-youtube-automation' AND path='SERVER_HANDOFF.md'").fetchone()[0]
            sk = db.execute("SELECT COUNT(*) FROM skipped WHERE path LIKE '%SERVER_HANDOFF.md'").fetchone()[0]
        self.assertEqual((n > 0, sk), (True, 0))

    def test_no_credential_shape_in_the_index(self):
        import re
        pat = re.compile(r"1//0[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,}|ya29\.[A-Za-z0-9_-]{20,}")
        with store.open_ro(self.cfg.index) as db:
            for (t,) in db.execute("SELECT text FROM chunks"):
                self.assertIsNone(pat.search(t))

    def test_song_by_ccli(self):
        r = query.song(self.cfg, "7247827")
        self.assertTrue(r["songs"], r)
        self.assertEqual(r["songs"][0]["title"], "We Want Revival")
        for w in ("Hannah Yates", "Jonathan Stamper", "Seth Yates"):
            self.assertIn(w, json.dumps(r))

    def test_song_original_without_ccli(self):
        r = query.song(self.cfg, "Great Expectation")
        self.assertTrue(r["songs"], r)
        self.assertIn("Kristina Robinson", json.dumps(r))
        self.assertFalse(r["songs"][0].get("ccli"))

    def test_peace_is_a_garrison(self):
        d = query.search(self.cfg, '"Peace Is a Garrison"', kind="description", limit=20)["results"]
        self.assertTrue(any("GLORY_NIGHT_2026-10-19_description.txt" in h["provenance"]["path"] for h in d))
        a = query.search(self.cfg, '"Peace Is a Garrison"', limit=50)["results"] + query.search(self.cfg, "garrison", kind="media", limit=50)["results"]
        self.assertTrue(any("THUMB_2026-10-19_peace_is_a_garrison" in h["provenance"]["path"] for h in a))

    def test_framing_in_transcripts(self):
        r = query.search(self.cfg, "framing", kind="transcript")["results"]
        self.assertTrue(any("youtu.be/" in (h.get("link") or "") and "?t=" in h["link"] for h in r))
        for h in r:   # a transcript tied to a video links to the second; one with only a hint ("oct18") never guesses one
            self.assertEqual(bool(h.get("video_id")), "?t=" in (h.get("link") or ""), h["provenance"]["path"])

    def test_video_pmvm1fhjizm(self):
        v = json.dumps(query.video(self.cfg, "PMVM1FhjizM"))
        for p in ("glory_oct26/applied.json", "desc_written_log.json", "_backup_shorts.json"):
            self.assertIn(p, v)


class UnitsAndSetup(unittest.TestCase):
    """The units, the setup script and the package's reach, read as files."""

    def units(self):
        return {p.name: p.read_text() for p in UNITS.glob("*.service")}

    def test_non_root_units_gate_with_the_privileged_form(self):
        # /etc/arise/arise.toml is 0640: a service-now check run as the job's own user
        # cannot read the service times. `+` runs only that check with full privileges.
        for name, text in self.units().items():
            user = next((l.split("=", 1)[1].strip() for l in text.splitlines() if l.startswith("User=")), "root")
            if user == "root":
                continue
            for line in text.splitlines():
                if line.startswith("ExecCondition=") and "service-now" in line:
                    self.assertTrue(line.startswith("ExecCondition=+"), f"{name}: {line}")

    def test_archive_units_are_confined(self):
        for name in ("arise-archive.service", "arise-archive-rebuild.service"):
            t = (UNITS / name).read_text()
            for need in ("User=arise-kb", "Group=arise-kb", "ProtectSystem=strict", "NoNewPrivileges=yes",
                         "ReadWritePaths=/srv/arise/archive /var/lib/arise/archive",
                         "InaccessiblePaths=/etc/arise/secrets/youtube",
                         "ExecCondition=+/usr/local/bin/arisectl service-now --quiet"):
                self.assertIn(need, t, name)
            self.assertNotIn("/srv/arise/automator", t)
            self.assertNotIn("/srv/arise/repos", t)
        self.assertIn("build --full", (UNITS / "arise-archive-rebuild.service").read_text())

    def test_timers_stay_out_of_saturday_and_service_hours(self):
        nightly = (UNITS / "arise-archive.timer").read_text()
        weekly = (UNITS / "arise-archive-rebuild.timer").read_text()
        self.assertIn("04:15:00 America/Chicago", nightly)
        self.assertNotIn("Wed", nightly.split("OnCalendar=")[1].splitlines()[0])
        cal = weekly.split("OnCalendar=")[1].splitlines()[0]
        self.assertTrue(cal.startswith("Wed "), cal)
        for day in ("Sat", "Sun", "Mon"):
            self.assertNotIn(day, cal)

    def test_package_never_reaches_secrets_or_writes_out(self):
        import ast
        files = list((ROOT / "archive").rglob("*.py")) + [ROOT / "archive" / "arise-archive", ROOT / "archive" / "arise-archive-mcp"]
        src = "\n".join(p.read_text() for p in files)
        for p in files:   # no string the code uses names the secrets folder (docstrings may say it is never read)
            tree = ast.parse(p.read_text())
            docs = {id(n.body[0].value) for n in ast.walk(tree) if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))
                    and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
            for n in ast.walk(tree):
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
                    self.assertNotIn("/etc/arise/secrets", n.value, p.name)
                if isinstance(n, (ast.Import, ast.ImportFrom)):   # no route into the dashboard, the token or the automator
                    mods = [a.name for a in n.names] + [getattr(n, "module", None) or ""]
                    self.assertFalse(any(m.startswith(("arise_server", "googleapiclient", "google", "requests", "urllib")) for m in mods), f"{p.name}: {mods}")
        for verb in ('"push"', "'push'", "youtube.upload", "googleapiclient", "requests.post", "urllib.request"):
            self.assertNotIn(verb, src, verb)

    def test_setup_script(self):
        s = (ROOT / "scripts" / "arise-archive-setup").read_text()
        self.assertIn("visudo -cf", s)
        self.assertIn("%$GRP ALL=($U) NOPASSWD: $VENV_PY $MCP", s)     # exactly the MCP command, as arise-kb
        self.assertIn("usermod -aG arise-conf arise-kb", s)
        self.assertIn("deploy_key_automation", s); self.assertIn("deploy_key_projectbackups", s)
        self.assertIn("StrictHostKeyChecking=yes", s)
        self.assertNotIn("/srv/arise/repos", s.split("never /srv/arise/repos")[-1])   # mentioned once, as the thing it is not
        self.assertNotIn("/srv/arise/automator/", s)
        r = subprocess.run(["bash", "-n", str(ROOT / "scripts" / "arise-archive-setup")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("/.mcp.json", (ROOT / ".gitignore").read_text())

    def test_backups_take_no_archive_and_no_archive_key(self):
        import yaml
        jobs = yaml.safe_load((ROOT / "config" / "backups.yaml.example").read_text())["jobs"]
        for j in jobs:
            for p in j.get("paths", []):
                self.assertFalse(p.startswith(("/srv/arise/archive", "/var/lib/arise/archive")), j["id"])
        cfgjob = next(j for j in jobs if j["id"] == "config")
        self.assertIn("/etc/arise/secrets/archive", cfgjob["exclude"])

    @unittest.skipUnless(hasattr(os, "geteuid") and os.geteuid() == 0 and shutil.which("runuser"), "needs root and runuser")
    def test_a_non_root_reader_cannot_open_a_root_only_secret(self):
        # What the MCP server's user (arise-kb, here: nobody) meets at /etc/arise/secrets/youtube.
        d = Path(tempfile.mkdtemp(prefix="arise-archive-perm-"))
        try:
            os.chmod(d, 0o711)
            sec = d / "youtube"; sec.mkdir(mode=0o700)
            (sec / "token.json").write_text("{}")
            os.chmod(sec / "token.json", 0o600)
            r = subprocess.run(["runuser", "-u", "nobody", "--", sys.executable, "-c",
                                f"open({str(sec / 'token.json')!r}).read()"], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("PermissionError", r.stderr)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
