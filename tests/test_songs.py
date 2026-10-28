"""The Songs tab (server/arise_server/songs.py): the song list from song_bank.json, read-only,
and the lyrics Bradly adds, against real files in a temp folder. No real lyrics anywhere here."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

USR = ("[File]\nType=SongSelect Import File\nVersion=3.0\n[S A7247827]\nTitle=We Want Revival\nAuthor=Hannah Yates | Seth Yates\n"
       "Copyright=Sample copyright\nFields=Verse 1/tChorus\nWords=sample line one/nsample line two/tsample chorus line\n")
TXT = ("Sample Song\n\nVerse 1\nsample verse words\n\nChorus\nsample chorus words\n\nCCLI Song # 1111111\nA Writer | B Writer\n"
       "© Sample Music\nFor use solely with the SongSelect Terms of Use.\nCCLI License # 245091\n")
CHO = "{title: Make Room}\n{ccli: 7122057}\n{comment: Verse 1}\n[G]sample [D]words here\n{soc}\nsample [C]chorus\n{eoc}\n"


class Parsers(unittest.TestCase):
    def setUp(self):
        from arise_server import songs
        self.s = songs

    def test_songselect_usr(self):
        p = self.s.parse_file("revival.usr", USR)
        self.assertEqual((p["title"], p["ccli"], p["writers"]), ("We Want Revival", "7247827", "Hannah Yates, Seth Yates"))
        self.assertEqual(p["text"], "Verse 1\nsample line one\nsample line two\n\nChorus\nsample chorus line")

    def test_songselect_txt(self):
        p = self.s.parse_file("song.txt", TXT)
        self.assertEqual((p["title"], p["ccli"], p["writers"], p["copyright"]), ("Sample Song", "1111111", "A Writer | B Writer", "© Sample Music"))
        self.assertNotIn("CCLI", p["text"])                       # the licence block is not lyrics
        self.assertTrue(p["text"].startswith("Verse 1\nsample verse words"))

    def test_chordpro_strips_chords(self):
        p = self.s.parse_file("room.cho", CHO)
        self.assertEqual((p["title"], p["ccli"]), ("Make Room", "7122057"))
        self.assertIn("Verse 1\nsample words here", p["text"])
        self.assertIn("Chorus\nsample chorus", p["text"])
        self.assertNotIn("[", p["text"])

    def test_plain_text_never_invents_a_number(self):
        p = self.s.parse_file("x.txt", "Great Expectation\n\nsample words\n")
        self.assertEqual((p["title"], p["ccli"]), ("Great Expectation", None))
        p = self.s.parse_file("x.txt", "Title: Praise\nCCLI: 7213077\n\nsample\n")
        self.assertEqual((p["title"], p["ccli"], p["text"]), ("Praise", "7213077", "sample"))


class Store(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="arise-songs-test-")
        t = Path(cls.tmp)
        repo = t / "archive" / "arise-youtube-automation"
        (repo / "cloud_workspace").mkdir(parents=True)
        (repo / "song_bank.json").write_text(json.dumps({
            "_comment": "rules",
            "Praise": {"ccli": "7213077", "writers": "Sample Writer", "note": "always followed by My Worship"},
            "My Worship": {"ccli": "7098688"},
            "Make Room": {"ccli": "7122057"},
            "Holy Ground": {"ccli": "1000001", "writers": "Writer One"},
            "Holy Ground ": {"ccli": "1000002", "writers": "Writer Two"},
            "Great Expectation": {"original": True, "writers": "Kristina Robinson"},
        }))
        (repo / "setlist_2026-10-11_sunday.json").write_text(json.dumps({"date_ct": "2026-10-11", "service": "Sunday", "video_id": "AnVfOCesXM4",
                                                                         "songs": [{"title": "Praise", "ccli": "7213077"}, {"title": "Great Expectation", "ccli": None}]}))
        (repo / "cloud_workspace" / "_all_vids.json").write_text(json.dumps([
            {"id": "W8t2JYXOIBk", "snippet": {"title": "A service", "publishedAt": "2026-10-04T15:00:00Z", "description": "Songs\nPraise CCLI Song # 7213077\n"},
             "contentDetails": {"duration": "PT1H50M"}, "liveStreamingDetails": {"actualStartTime": "2026-10-04T15:30:00Z"}}]))
        (t / "arise.toml").write_text(f'[system]\ndata_root = "{t}/data"\n[web]\nadmin_user = "bradly"\n[directory]\nenabled = false\n'
                                      f'[automator]\npath = "{t}/no-checkout"\n[paths]\nstate_dir = "{t}/state"\nlog_dir = "{t}/state"\n')
        cls.env = {k: os.environ.get(k) for k in ("ARISE_CONFIG", "ARISE_DEMO", "ARISE_ARCHIVE_ROOT", "ARISE_ARCHIVE_STATE", "ARISE_NO_NET")}
        os.environ.update(ARISE_CONFIG=str(t / "arise.toml"), ARISE_ARCHIVE_ROOT=str(t / "archive"), ARISE_ARCHIVE_STATE=str(t / "astate"), ARISE_NO_NET="1")
        os.environ.pop("ARISE_DEMO", None)
        from arise_server import config, songs
        config.load(force=True)
        cls.s, cls.lyr = songs, t / "data" / "songs" / "lyrics"

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.env.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        from arise_server import config
        config.load(force=True)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_the_list_is_song_bank_json(self):
        l = self.s.listing()
        self.assertEqual(l["counts"]["all"], 6)                      # "_comment" is not a song
        keys = {r["key"] for r in l["songs"]}
        self.assertIn("7213077", keys)
        self.assertIn("t-great-expectation", keys)                   # an original has no number: keyed by its title
        praise = next(r for r in l["songs"] if r["key"] == "7213077")
        self.assertEqual(praise["sung"], 2)                          # the set list, and a description that credits the number
        self.assertEqual(self.s.listing("7213077")["songs"][0]["title"], "Praise")   # the exact number first
        self.assertEqual([r["title"].strip() for r in self.s.listing("writer two")["songs"]], ["Holy Ground"])   # titles as written

    def test_lyrics_save_search_versions_and_remove(self):
        r = self.s.save("7122057", "Verse 1\nsample zebra line\n", "bradly")
        self.assertTrue(r["ok"])
        f = self.lyr / "7122057.txt"
        self.assertTrue(f.read_text().startswith("Title: Make Room\nCCLI: 7122057\n"))
        hit = self.s.listing("zebra")["songs"]
        self.assertEqual((hit[0]["key"], hit[0]["matched"]), ("7122057", "lyrics"))
        self.assertIn("[zebra]", hit[0]["snippet"])
        self.assertTrue(self.s.save("7122057", "Verse 1\nsecond version", "bradly")["kept_previous"])
        self.assertEqual(len(list((self.lyr / ".versions").glob("7122057-*.txt"))), 1)
        self.assertEqual(self.s.song("7122057")["versions"], 1)
        self.assertEqual(self.s.song("7213077")["note"], "always followed by My Worship")   # the song's own note, not the licence line
        self.assertIn("245091", self.s.song("7213077")["licence"])
        self.assertFalse(self.s.remove("7122057", "make room", "bradly")["ok"])   # the title, exactly
        self.assertTrue(self.s.remove("7122057", "Make Room", "bradly")["ok"])
        self.assertFalse(f.exists())
        self.assertEqual(len(list((self.lyr / ".removed").glob("7122057-*.txt"))), 1)   # moved, never deleted
        self.assertFalse(self.s.save("9999999", "x", "bradly")["ok"])               # not a song in the bank
        self.assertFalse(self.s.save("7122057", "   ", "bradly")["ok"])
        for bad in ("../../etc/passwd", "t-../x", "", "7213077/../x"):
            self.assertFalse(self.s.save(bad, "x", "bradly")["ok"], bad)
            self.assertFalse(self.s.song(bad)["ok"], bad)

    def test_import_links_by_number_then_by_a_unique_title_never_by_a_shared_one(self):
        r = self.s.import_files([
            {"name": "revival.usr", "text": USR},                            # its number is not in this bank: kept, not linked
            {"name": "room.cho", "text": CHO},                               # linked by number
            {"name": "praise.txt", "text": "Praise\n\nsample praise words\n"},   # linked by its one-song title
            {"name": "ground.txt", "text": "Holy Ground\n\nsample words\n"},     # two songs share it: not linked
            {"name": "notes.pdf", "text": "x"},
        ], "bradly")
        by = {x["name"]: x for x in r["results"]}
        self.assertEqual(by["room.cho"]["matched_by"], "CCLI number")
        self.assertEqual(by["room.cho"]["key"], "7122057")
        self.assertTrue(by["praise.txt"]["matched_by"].startswith("title"))
        self.assertIsNone(by["ground.txt"]["matched_by"])
        self.assertIn("several songs share that title", by["ground.txt"]["note"])
        self.assertIsNone(by["revival.usr"]["matched_by"])
        self.assertFalse(by["notes.pdf"]["ok"])
        self.assertEqual((r["linked"], r["unlinked"], r["failed"]), (2, 2, 1))
        unlinked = [x for x in self.s.listing(has="lyrics")["songs"] if not x["in_bank"]]
        self.assertEqual({x["key"] for x in unlinked}, {"x-we-want-revival", "x-holy-ground"})
        self.assertEqual(self.s.song("x-holy-ground")["in_bank"], False)


class Routes(unittest.TestCase):
    def setUp(self):
        self.was = os.environ.get("ARISE_DEMO")
        os.environ["ARISE_DEMO"] = "1"

    def tearDown(self):
        os.environ.pop("ARISE_DEMO", None) if self.was is None else os.environ.__setitem__("ARISE_DEMO", self.was)

    def test_admin_only(self):
        from fastapi.testclient import TestClient
        from arise_server import config, demo_state
        from arise_server.main import app
        config.load(force=True)
        demo_state.reset()
        a = TestClient(app)
        self.assertGreaterEqual(a.get("/api/songs").json()["total"], 5)
        self.assertTrue(a.put("/api/songs/7122057/lyrics", json={"text": "Verse 1\nsample quokka"}).json()["ok"])
        self.assertEqual(a.get("/api/songs", params={"q": "quokka"}).json()["songs"][0]["key"], "7122057")
        self.assertTrue(a.request("DELETE", "/api/songs/7122057/lyrics", json={"confirm": "Make Room"}).json()["ok"])
        m = TestClient(app)
        m.post("/api/auth/login", json={"user": "office", "password": "anything"})
        self.assertIn(m.get("/api/songs").status_code, (401, 403))
        self.assertIn(m.put("/api/songs/7122057/lyrics", json={"text": "x"}).status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
