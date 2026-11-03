"""The weekly YouTube sign-in (ytauth.py; Bradly, Oct 29: the OAuth app stays in Testing).

What is pinned: the link carries PKCE and the server's state, never the verifier or the client
secret; a pasted address from another attempt, an old link or the wrong channel is refused and
nothing is written; the token is written 0600 and never appears in an answer, the audit log or
anything printed; the weekly clock, the Needs You line and the Saturday/Sunday reminders.
Fake values below are plain words: nothing here is shaped like a real Google credential.
"""
import base64
import contextlib
import hashlib
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from arise_server import automator, config, ytauth  # noqa: E402

ACCESS = "access-sample-value-abc"
REFRESH = "refresh-sample-value-xyz"
SECRET = "client-sample-secret-word"
MANAGE = "https://www.googleapis.com/auth/youtube.force-ssl"


@contextlib.contextmanager
def real_box(tmp: Path):
    conf = tmp / "arise.toml"
    conf.write_text(f'[system]\ndata_root = "{tmp}/data"\n[paths]\nstate_dir = "{tmp}/state"\nlog_dir = "{tmp}/state"\n')
    (tmp / "state").mkdir()
    (tmp / "secrets").mkdir(mode=0o700)
    repo = tmp / "repo"
    repo.mkdir()
    (repo / "authorize_headless.py").write_text(f'CHANNEL_ID = "{ytauth.CHANNEL_ID}"\nMANAGE = "{MANAGE}"\nANALYTICS = "x"\n')
    (tmp / "secrets" / "client_secret.json").write_text(json.dumps({"installed": {
        "client_id": "sample-client.apps.googleusercontent.com", "client_secret": SECRET, "project_id": "sample",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth", "token_uri": "https://oauth2.googleapis.com/token"}}))
    paths = {"root": str(repo), "token": str(tmp / "secrets" / "token.json"), "secret": str(tmp / "secrets" / "client_secret.json")}
    old = {k: os.environ.get(k) for k in ("ARISE_CONFIG", "ARISE_DEMO")}
    os.environ["ARISE_CONFIG"] = str(conf)
    os.environ.pop("ARISE_DEMO", None)
    config.load(force=True)
    try:
        with mock.patch.object(automator, "_paths", return_value=paths), \
             mock.patch("arise_server.church.in_service_now", return_value=None), \
             mock.patch.object(automator, "job_user", return_value=""):
            yield paths
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        config.load(force=True)


def google(channel=ytauth.CHANNEL_ID, refresh=REFRESH, seen=None):
    """Stand-ins for Google's token endpoint and channels.list."""
    def post(url, form):
        if seen is not None:
            seen.append(form)
        return {"access_token": ACCESS, "refresh_token": refresh, "expires_in": 3599, "scope": MANAGE, "token_type": "Bearer"}

    def get(url, bearer):
        assert bearer == ACCESS and "mine=true" in url
        return {"items": [{"id": channel, "snippet": {"title": "Arise Church" if channel == ytauth.CHANNEL_ID else "Someone Else"}}]}
    return post, get


def link_state(url: str) -> str:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]


class Link(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="arise-ytauth-"))

    def test_pkce_is_s256(self):
        v, c = ytauth.pkce_pair()
        self.assertTrue(43 <= len(v) <= 128)
        self.assertEqual(c, base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("="))

    def test_scopes_come_from_the_handoffs_script_or_doc_never_a_guess(self):
        repo = self.tmp / "r"
        repo.mkdir()
        with self.assertRaises(ValueError):
            ytauth.scopes(str(repo))
        (repo / "SERVER_HANDOFF.md").write_text("- Scope is `youtube.force-ssl` only, which is everything the nightly job needs.\n")
        self.assertEqual(ytauth.scopes(str(repo)), [MANAGE])
        (repo / "authorize_headless.py").write_text('MANAGE = "https://www.googleapis.com/auth/youtube"\n')
        self.assertEqual(ytauth.scopes(str(repo)), ["https://www.googleapis.com/auth/youtube"])

    def test_the_link_carries_pkce_and_state_but_never_the_verifier_or_secret(self):
        with real_box(self.tmp):
            r = ytauth.start("bradly")
            self.assertTrue(r["ok"], r)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query)
            self.assertEqual(q["code_challenge_method"], ["S256"])
            self.assertEqual(q["redirect_uri"], ["http://localhost:8765/"])
            self.assertEqual(q["scope"], [MANAGE])
            self.assertEqual(q["access_type"], ["offline"])
            pend = json.loads((self.tmp / "state" / "ytauth-pending.json").read_text())
            self.assertEqual(stat.S_IMODE(os.stat(self.tmp / "state" / "ytauth-pending.json").st_mode), 0o600)
            self.assertEqual(q["state"], [pend["state"]])
            self.assertNotIn(pend["verifier"], json.dumps(r))
            self.assertNotIn(SECRET, json.dumps(r))

    def test_refused_during_a_service(self):
        with real_box(self.tmp):
            with mock.patch("arise_server.church.in_service_now", return_value={"name": "Glory Night"}):
                r = ytauth.start("bradly")
            self.assertFalse(r["ok"])
            self.assertIn("after the service", r["err"])


class Finish(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="arise-ytauth-"))

    def test_a_different_attempt_is_refused_and_nothing_is_written(self):
        with real_box(self.tmp) as p:
            ytauth.start("bradly")
            post, get = google()
            r = ytauth.finish("http://localhost:8765/?state=not-the-one&code=sample-code", "bradly", post=post, get=get)
            self.assertFalse(r["ok"])
            self.assertIn("state does not match", r["err"])
            self.assertFalse(os.path.exists(p["token"]))
            self.assertFalse((self.tmp / "state" / "ytauth-pending.json").exists())   # one try per link

    def test_an_old_link_is_refused(self):
        with real_box(self.tmp) as p:
            u = ytauth.start("bradly", now=1000.0)["url"]
            post, get = google()
            r = ytauth.finish(f"http://localhost:8765/?state={link_state(u)}&code=c", "bradly", post=post, get=get, now=1000.0 + 601)
            self.assertFalse(r["ok"])
            self.assertIn("ten minutes", r["err"])
            self.assertFalse(os.path.exists(p["token"]))

    def test_the_wrong_channel_is_refused_and_nothing_is_written(self):
        with real_box(self.tmp) as p:
            u = ytauth.start("bradly")["url"]
            post, get = google(channel="UCsomeoneelse")
            r = ytauth.finish(f"http://localhost:8765/?state={link_state(u)}&code=c", "bradly", post=post, get=get)
            self.assertFalse(r["ok"])
            self.assertIn("not Arise Church", r["err"])
            self.assertFalse(os.path.exists(p["token"]))
            self.assertFalse((self.tmp / "state" / "ytauth.json").exists())

    def test_no_refresh_token_is_refused(self):
        with real_box(self.tmp) as p:
            u = ytauth.start("bradly")["url"]
            post, get = google(refresh=None)
            r = ytauth.finish(f"http://localhost:8765/?state={link_state(u)}&code=c", "bradly", post=post, get=get)
            self.assertFalse(r["ok"])
            self.assertFalse(os.path.exists(p["token"]))

    def test_renewed_0600_and_the_token_is_never_shown(self):
        with real_box(self.tmp) as p:
            u = ytauth.start("bradly")["url"]
            seen = []
            post, get = google(seen=seen)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                r = ytauth.finish(f"http://localhost:8765/?state={link_state(u)}&code=sample-code", "bradly", post=post, get=get)
            self.assertTrue(r["ok"], r)
            # the code was swapped with this server's own verifier
            self.assertEqual(seen[0]["code"], "sample-code")
            self.assertTrue(seen[0]["code_verifier"])
            self.assertEqual(seen[0]["redirect_uri"], "http://localhost:8765/")
            # written, owner-only, in the format the job reads
            self.assertEqual(stat.S_IMODE(os.stat(p["token"]).st_mode), 0o600)
            tok = json.loads(Path(p["token"]).read_text())
            self.assertEqual(tok["refresh_token"], REFRESH)
            self.assertEqual(tok["client_id"], "sample-client.apps.googleusercontent.com")
            self.assertIn(MANAGE, tok["scopes"])
            self.assertTrue(tok["expiry"].endswith("Z"))
            # never in the answer, anything printed, or the audit log
            shown = json.dumps(r) + out.getvalue() + err.getvalue()
            audit_txt = "".join(f.read_text() for f in (self.tmp / "state").glob("**/*") if f.is_file() and "audit" in f.name)
            for secret_bit in (ACCESS, REFRESH, SECRET):
                self.assertNotIn(secret_bit, shown)
                self.assertNotIn(secret_bit, audit_txt)
            self.assertIn("renewed, expires", audit_txt)
            # the weekly clock started
            e = ytauth.expiry()
            self.assertTrue(e["known"])
            self.assertAlmostEqual(e["days_left"], 7, delta=0.1)
            self.assertEqual(r["expires_text"], e["expires_text"])

    def test_the_bare_code_and_google_errors(self):
        self.assertEqual(ytauth.parse_answer("just-a-code")["code"], "just-a-code")
        self.assertIn("access_denied", ytauth.parse_answer("http://localhost:8765/?error=access_denied&state=x")["error"])
        self.assertIn("no code=", ytauth.parse_answer("http://localhost:8765/?state=x")["error"])
        self.assertIn("Nothing", ytauth.parse_answer("  ")["error"])


class Clock(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="arise-ytauth-"))

    def issued(self, when: datetime):
        (self.tmp / "state" / "ytauth.json").write_text(json.dumps({"issued": when.isoformat(timespec="minutes"), "by": "bradly"}))

    def test_unknown_until_a_renewal_is_recorded(self):
        with real_box(self.tmp):
            self.assertFalse(ytauth.expiry()["known"])
            self.assertEqual(ytauth.attention(), [])

    def test_soon_and_ended_reach_needs_you(self):
        sun = datetime(2026, 11, 1, 12, 14)
        with real_box(self.tmp):
            self.issued(sun)
            self.assertEqual(ytauth.attention(sun + timedelta(days=3)), [])
            a = ytauth.attention(sun + timedelta(days=6, hours=1))          # Saturday 13:14: 23 h left
            self.assertEqual(a[0]["level"], "warn")
            self.assertIn("Media Mac", a[0]["text"])
            b = ytauth.attention(sun + timedelta(days=7, hours=1))
            self.assertEqual(b[0]["level"], "bad")
            self.assertIn("expired on Sun Nov 8, 12:14 PM", b[0]["text"])

    def test_reminders_saturday_evening_and_sunday_after_the_service_once_each(self):
        sun = datetime(2026, 11, 1, 12, 14)
        posted = []

        def post(ch, text, key=""):
            dup = key in posted
            posted.append(key)
            return {"ok": True, "duplicate": dup}
        with real_box(self.tmp):
            self.issued(sun)
            self.assertEqual(ytauth.reminders(sun + timedelta(days=3), post=post, push=lambda t: None), [])   # Wednesday
            sat = datetime(2026, 11, 7, 19, 5)
            got = ytauth.reminders(sat, post=post, push=lambda t: None)
            self.assertEqual(len(got), 1)
            self.assertEqual(ytauth.reminders(sat + timedelta(hours=1), post=post, push=lambda t: None), [])   # once
            sun2 = datetime(2026, 11, 8, 12, 5)
            with mock.patch("arise_server.church.in_service_now", return_value={"name": "Sunday Service"}):
                self.assertEqual(ytauth.reminders(sun2, post=post, push=lambda t: None), [])                    # never during a service
            self.assertEqual(len(ytauth.reminders(sun2 + timedelta(hours=1), post=post, push=lambda t: None)), 1)


class Routes(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.get("ARISE_DEMO")
        os.environ["ARISE_DEMO"] = "1"
        config.load(force=True)

    def tearDown(self):
        os.environ.pop("ARISE_DEMO", None) if self._old is None else os.environ.__setitem__("ARISE_DEMO", self._old)
        config.load(force=True)

    def test_the_preview_renews_with_the_right_state_only(self):
        from fastapi.testclient import TestClient
        from arise_server.main import app
        c = TestClient(app)
        r = c.post("/api/automator/signin/start").json()
        self.assertTrue(r["ok"], r)
        st = link_state(r["url"])
        self.assertFalse(c.post("/api/automator/signin/finish", json={"address": "http://localhost:8765/?state=nope&code=c"}).json()["ok"])
        r = c.post("/api/automator/signin/start").json()
        f = c.post("/api/automator/signin/finish", json={"address": f"http://localhost:8765/?state={link_state(r['url'])}&code=c"}).json()
        self.assertTrue(f["ok"], f)
        self.assertIn("Sample", f["note"])
        self.assertTrue(c.get("/api/automator/signin").json()["known"])
        self.assertNotEqual(st, link_state(r["url"]))

    def test_the_finish_route_signs_this_browser_out_unless_unticked_or_the_monitor(self):
        src = (ROOT / "server" / "arise_server" / "main.py").read_text()
        body = src[src.index("def auto_signin_finish"):src.index("\n@app.", src.index("def auto_signin_finish"))]
        self.assertIn("body.sign_out", body)
        self.assertIn("kiosk_profiles.on_monitor", body)
        self.assertIn("response.delete_cookie(COOKIE)", body)
        self.assertNotIn("revoke_sessions", body)       # only this browser; his other devices stay signed in


if __name__ == "__main__":
    unittest.main()
