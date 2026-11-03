"""The Automator app's channel side (server/arise_server/channel.py, archive/arise_archive/catalogue.py).

A throwaway repo shaped like the automation repo (four snapshot files, a
transcript, a thumbnail, a Shorts description that links its service, a private
note) is indexed for real; then the dashboard's calls are checked against it,
not against mocks. The routes are checked as the administrator and as a member.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "archive"))
sys.path.insert(0, str(ROOT / "server"))

from arise_archive import catalogue, indexer  # noqa: E402
from arise_archive.config import Config as ArchiveConfig  # noqa: E402

SERVICE, SHORT, LATER = "AnVfOCesXM4", "yMewy7Nwi3c", "hu9cnsymsSo"


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                    "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, text=True)


def write(repo, rel, data):
    p = Path(repo) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    (p.write_bytes if isinstance(data, bytes) else p.write_text)(data)


def png() -> bytes:
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (32, 18), (214, 34, 45)).save(b, "PNG")
    return b.getvalue()


class Catalogue(unittest.TestCase):
    def test_durations_dates_and_title_dates(self):
        self.assertEqual(catalogue.iso_seconds("PT1H2M3S"), 3723)
        self.assertEqual(catalogue.iso_seconds("4:07"), 247)
        self.assertEqual(catalogue.iso_seconds("P0D"), 0)
        self.assertEqual(catalogue.central_date("2026-10-12T02:30:00Z"), "2026-10-11")   # 9:30 PM Sunday in Pineville
        self.assertEqual(catalogue.date_in_title("Peace Is a Garrison | Apostle Bryant Sanders | Glory Night October 19, 2026"), "2026-10-19")
        self.assertIsNone(catalogue.date_in_title("PITCH THE SHIP | Apostle Bryant Sanders"))
        # A stream scheduled a week ahead: the title's date wins over the schedule.
        r = catalogue.finish({"title": "X | Y | Glory Night October 19, 2026", "started": "2026-10-12T23:25:01Z", "live": True})
        self.assertEqual((r["date"], r["kind"]), ("2026-10-19", "service"))
        r = catalogue.finish({"title": "Glory Night | Arise Church", "started": "2026-10-12T23:25:01Z", "live": True, "upcoming": "upcoming"})
        self.assertIn("scheduled", r["date_note"])
        self.assertEqual(catalogue.finish({"seconds": 58})["kind"], "short")


class Channel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("git"):
            raise unittest.SkipTest("git is not installed")
        cls.tmp = tempfile.mkdtemp(prefix="arise-channel-test-")
        root = Path(cls.tmp) / "root"
        repo = root / "arise-youtube-automation"
        repo.mkdir(parents=True)
        git(repo, "init", "-q", "-b", "main")
        write(repo, "cloud_workspace/_all_vids.json", json.dumps([
            {"id": SERVICE, "snippet": {"title": "PITCH THE SHIP | Apostle Bryant Sanders", "publishedAt": "2026-10-11T15:20:00Z",
                                        "description": "Sunday service.\n\n0:00 Welcome\n2:30 Worship\n41:10 The message\n\nCCLI Song # 7213077 Praise\n",
                                        "liveBroadcastContent": "none"},
             "status": {"privacyStatus": "public"}, "contentDetails": {"duration": "PT1H56M30S"},
             "liveStreamingDetails": {"actualStartTime": "2026-10-11T15:31:00Z"}, "statistics": {"viewCount": "40"}},
            {"id": SHORT, "snippet": {"title": "Pitch the Ship: Intimacy with the Holy Spirit", "publishedAt": "2026-10-12T01:00:00Z",
                                      "description": f"A clip.\n\nWatch the full service: https://youtu.be/{SERVICE}\n#Shorts"},
             "status": {"privacyStatus": "public"}, "contentDetails": {"duration": "PT58S"}},
        ]))
        write(repo, "channel_inventory.csv", "video_id,type,title,published,duration,views,privacy\n"
                                             f"{SERVICE},long,Old title,2026-10-11,1:56:30,12,public\n")
        write(repo, f"transcripts/{SERVICE}.json", json.dumps({"video_id": SERVICE, "segments": [
            {"start": 0, "dur": 5, "text": "good morning church"},
            {"start": 2470, "dur": 6, "text": "the ship is the place where the intimacy happens"},
            {"start": 2480, "dur": 6, "text": "so pitch the ship and stay close"},
        ]}))
        write(repo, f"transcripts/{LATER}.json", json.dumps({"video_id": LATER, "segments": [
            {"start": 7804, "dur": 4, "text": "framing gives the structure of the house"}]}))
        write(repo, "THUMB_2026-10-11_pitch_the_ship.png", png())
        write(repo, "memory/people.md", "# People\n\nA private note that names someone: the intimacy of prayer.\n")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "fixture")
        cls.acfg = ArchiveConfig(root=root, state=Path(cls.tmp) / "state")
        r = indexer.build(cls.acfg, pull_first=False)
        assert r["ok"], r
        # A real (not demo) dashboard config, so channel.py reads the index.
        cls.conf = Path(cls.tmp) / "arise.toml"
        cls.conf.write_text(f'[web]\nadmin_user = "bradly"\n[directory]\nenabled = false\n[paths]\nstate_dir = "{cls.tmp}/s"\nlog_dir = "{cls.tmp}/s"\n')
        cls.env = {k: os.environ.get(k) for k in ("ARISE_CONFIG", "ARISE_DEMO", "ARISE_ARCHIVE_ROOT", "ARISE_ARCHIVE_STATE", "ARISE_NO_NET")}
        os.environ.update(ARISE_CONFIG=str(cls.conf), ARISE_ARCHIVE_ROOT=str(root), ARISE_ARCHIVE_STATE=str(cls.acfg.state), ARISE_NO_NET="1")
        os.environ.pop("ARISE_DEMO", None)
        from arise_server import config, channel
        config.load(force=True)
        cls.ch = channel
        cls.bradly, cls.office = {"user": "bradly", "role": "admin"}, {"user": "office.staff", "role": "admin"}

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        from arise_server import config
        config.load(force=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_catalogue_merges_the_snapshots_newest_shape_last(self):
        cat = catalogue.load(self.acfg)
        self.assertEqual(cat[SERVICE]["title"], "PITCH THE SHIP | Apostle Bryant Sanders")   # _all_vids replaces the csv's title
        self.assertEqual(cat[SERVICE]["kind"], "service")
        self.assertEqual(cat[SERVICE]["date"], "2026-10-11")
        self.assertEqual(cat[SHORT]["kind"], "short")
        self.assertEqual(cat[SHORT]["parent"], SERVICE)                                  # the Short names its full service
        self.assertEqual(cat[SERVICE]["children"], [SHORT])

    def test_videos_lists_snapshot_and_index_videos_newest_first(self):
        v = self.ch.videos()
        ids = [r["id"] for r in v["videos"]]
        self.assertEqual(set(ids), {SERVICE, SHORT, LATER})      # LATER is only in the index (a transcript)
        self.assertEqual(ids[0], SHORT)                          # Oct 11 evening, Central
        later = next(r for r in v["videos"] if r["id"] == LATER)
        self.assertEqual(later["kind"], "service")
        self.assertTrue(later["transcript"])
        self.assertEqual([r["id"] for r in self.ch.videos(kind="short")["videos"]], [SHORT])
        self.assertEqual({r["id"] for r in self.ch.videos(has="transcript")["videos"]}, {SERVICE, LATER})
        self.assertEqual([r["id"] for r in self.ch.videos(q="pitch ship")["videos"]][:2], [SHORT, SERVICE])

    def test_the_card_has_thumbnails_links_chapters_credits_shorts_and_transcript(self):
        c = self.ch.video(SERVICE, self.bradly)
        self.assertTrue(c["ok"])
        self.assertEqual(c["watch"], f"https://youtu.be/{SERVICE}")
        self.assertEqual(c["studio"], f"https://studio.youtube.com/video/{SERVICE}/edit")
        self.assertIn("i.ytimg.com", c["thumb_large"])
        self.assertEqual([t["path"] for t in c["thumbs"]], ["THUMB_2026-10-11_pitch_the_ship.png"])   # matched by the service date
        self.assertEqual([x["at"] for x in c["chapters"]], ["0:00", "2:30", "41:10"])
        self.assertEqual(c["chapters"][2]["link"], f"https://youtu.be/{SERVICE}?t=2470")
        self.assertEqual(c["credits"], ["CCLI Song # 7213077 Praise"])                               # as written, nothing added
        self.assertEqual([s["id"] for s in c["shorts"]], [SHORT])
        self.assertEqual(c["transcripts"][0]["segments"], 3)
        t = self.ch.transcript(SERVICE)
        self.assertEqual([s["t"] for s in t["segments"]], [0, 2470, 2480])
        self.assertIn("sung", t["lyrics"])
        # A Short shares its service's date, but not its thumbnail.
        s = self.ch.video(SHORT, self.bradly)
        self.assertEqual(s["thumbs"], [])
        self.assertEqual(s["parent_video"]["id"], SERVICE)

    def test_search_groups_hits_by_video_with_timestamps(self):
        r = self.ch.search("intimacy", who=self.bradly)
        self.assertEqual([g["id"] for g in r["videos"]], [SERVICE])
        hit = r["videos"][0]["hits"][0]
        self.assertEqual((hit["at"], hit["link"]), ("41:10", f"https://youtu.be/{SERVICE}?t=2470"))
        self.assertIn("[intimacy]", hit["snippet"])
        self.assertEqual(self.ch.search("framing", who=self.bradly)["videos"][0]["id"], LATER)
        self.assertEqual(self.ch.search("", who=self.bradly)["videos"], [])
        self.assertEqual(self.ch.search('"unbalanced quote', who=self.bradly).get("videos"), [])    # never a crash

    def test_private_folders_are_bradlys_only(self):
        everything = lambda who, priv: self.ch.search("intimacy", kind="all", private=priv, who=who)  # noqa: E731
        self.assertFalse(any(f["path"].startswith("memory/") for f in everything(self.bradly, False)["files"]))   # off by default
        self.assertTrue(any(f["path"].startswith("memory/") for f in everything(self.bradly, True)["files"]))
        self.assertFalse(any(f["path"].startswith("memory/") for f in everything(self.office, True)["files"]))    # asked, and refused
        self.assertFalse(self.ch.document("arise-youtube-automation", "memory/people.md", who=self.office)["ok"])
        self.assertTrue(self.ch.document("arise-youtube-automation", "memory/people.md", who=self.bradly)["ok"])

    def test_images_only_from_the_archive(self):
        f, ctype, err = self.ch.image("arise-youtube-automation", "THUMB_2026-10-11_pitch_the_ship.png", self.bradly)
        self.assertEqual((ctype, err), ("image/png", ""))
        self.assertTrue(f.is_file())
        for repo, path in [("arise-youtube-automation", "../../etc/passwd.png"), ("arise-youtube-automation", f"transcripts/{SERVICE}.json"),
                           ("nope", "x.png"), ("arise-youtube-automation", "missing.png")]:
            self.assertIsNone(self.ch.image(repo, path, self.bradly)[0], path)
        self.assertFalse(self.ch.video("not-an-id", self.bradly)["ok"])

    def test_oembed_is_cached_and_says_nothing_on_failure(self):
        os.environ.pop("ARISE_NO_NET")
        try:
            calls = []
            ok = lambda url: calls.append(url) or {"title": "Peace Is a Garrison | Apostle Bryant Sanders | Glory Night October 19, 2026", "author_name": "Arise Church"}  # noqa: E731
            self.assertEqual(self.ch.oembed("2wVIGBvQLzE", fetch=ok)["author"], "Arise Church")
            self.assertEqual(self.ch.oembed("2wVIGBvQLzE", fetch=ok)["author"], "Arise Church")
            self.assertEqual(len(calls), 1)                                    # a week's cache
            self.assertIn("youtube.com/oembed", calls[0])

            def boom(url):
                raise OSError("offline")
            self.assertIsNone(self.ch.oembed("4V4QeHZevgU", fetch=boom))
        finally:
            os.environ["ARISE_NO_NET"] = "1"


class Routes(unittest.TestCase):
    """Sample mode: the routes answer, and they are the administrator's."""

    def setUp(self):
        self.was = os.environ.get("ARISE_DEMO")

    def tearDown(self):
        if self.was is None:
            os.environ.pop("ARISE_DEMO", None)
        else:
            os.environ["ARISE_DEMO"] = self.was

    def test_admin_gets_them_and_a_member_does_not(self):
        os.environ["ARISE_DEMO"] = "1"
        from fastapi.testclient import TestClient
        from arise_server import config, demo_state
        from arise_server.main import app
        config.load(force=True)
        demo_state.reset()
        admin = TestClient(app)
        v = admin.get("/api/automator/videos").json()
        self.assertGreaterEqual(v["total"], 5)
        vid = v["videos"][0]["id"]
        card = admin.get(f"/api/automator/videos/{vid}").json()
        self.assertTrue(card["ok"])
        self.assertTrue(card["thumbs"][0]["url"].startswith("data:image/svg+xml"))   # the sample thumbnail is drawn, not fetched
        self.assertTrue(admin.get(f"/api/automator/videos/{vid}/transcript").json()["segments"])
        s = admin.get("/api/automator/search", params={"q": "garrison"}).json()
        self.assertEqual(s["videos"][0]["id"], "2wVIGBvQLzE")
        self.assertIn("sample", s["videos"][0]["hits"][0]["snippet"].lower())          # sample text says it is one
        m = TestClient(app)
        self.assertEqual(m.post("/api/auth/login", json={"user": "office", "password": "anything"}).json()["role"], "member")
        for path in ("/api/automator/videos", f"/api/automator/videos/{vid}", "/api/automator/search?q=x", "/api/automator/archive/file?repo=a&path=b.png"):
            self.assertIn(m.get(path).status_code, (401, 403), path)


if __name__ == "__main__":
    unittest.main()
