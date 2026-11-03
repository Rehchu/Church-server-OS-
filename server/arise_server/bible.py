"""Bible lookup for the desktop's Bible app.

The server fetches from bible-api.com (public-domain texts: World English
Bible, King James Version, and others) so no key is needed and the browser
never talks to a Bible source itself. Demo mode answers from a small
public-domain KJV sample so the preview works offline.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

from .config import load

TRANSLATIONS = [("web", "World English Bible"), ("kjv", "King James Version"), ("asv", "American Standard Version"), ("bbe", "Bible in Basic English"), ("darby", "Darby Translation"), ("ylt", "Young's Literal Translation")]

SAMPLE = {
    "john 3:16": ("John 3:16", [(16, "For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life.")]),
    "psalm 23": ("Psalm 23", [(1, "The LORD is my shepherd; I shall not want."), (2, "He maketh me to lie down in green pastures: he leadeth me beside the still waters."), (3, "He restoreth my soul: he leadeth me in the paths of righteousness for his name's sake."), (4, "Yea, though I walk through the valley of the shadow of death, I will fear no evil: for thou art with me; thy rod and thy staff they comfort me."), (5, "Thou preparest a table before me in the presence of mine enemies: thou anointest my head with oil; my cup runneth over."), (6, "Surely goodness and mercy shall follow me all the days of my life: and I will dwell in the house of the LORD for ever.")]),
    "romans 8:28": ("Romans 8:28", [(28, "And we know that all things work together for good to them that love God, to them who are the called according to his purpose.")]),
    "isaiah 40:31": ("Isaiah 40:31", [(31, "But they that wait upon the LORD shall renew their strength; they shall mount up with wings as eagles; they shall run, and not be weary; and they shall walk, and not faint.")]),
    "philippians 4:6-7": ("Philippians 4:6-7", [(6, "Be careful for nothing; but in every thing by prayer and supplication with thanksgiving let your requests be made known unto God."), (7, "And the peace of God, which passeth all understanding, shall keep your hearts and minds through Christ Jesus.")]),
    "exodus 19:5-6": ("Exodus 19:5-6", [(5, "Now therefore, if ye will obey my voice indeed, and keep my covenant, then ye shall be a peculiar treasure unto me above all people: for all the earth is mine:"), (6, "And ye shall be unto me a kingdom of priests, and an holy nation. These are the words which thou shalt speak unto the children of Israel.")]),
}


def lookup(ref: str, translation: str = "web") -> dict:
    ref = (ref or "").strip()
    if not re.match(r"^[1-3]?\s?[A-Za-z ]{2,30}\s?\d{1,3}(:\d{1,3}(-\d{1,3})?)?$", ref):
        return {"ok": False, "error": "Try a reference like John 3:16, Psalm 23 or Romans 8:28-30"}
    if translation not in dict(TRANSLATIONS):
        translation = "web"
    cfg = load()
    if cfg.demo:
        key = ref.lower().replace("psalms", "psalm")
        hit = SAMPLE.get(key) or SAMPLE.get(key.split(":")[0]) if ":" not in key else SAMPLE.get(key)
        if not hit:
            hit = (ref, [(1, f"(Preview) The server reads {ref} from bible-api.com when it is online. Try John 3:16, Psalm 23, Romans 8:28, Isaiah 40:31 or Philippians 4:6-7 here.")])
        return {"ok": True, "demo": True, "reference": hit[0], "translation": "kjv", "translation_name": "King James Version", "verses": [{"verse": v, "text": t} for v, t in hit[1]], "copyright": "Public domain."}
    url = f"https://bible-api.com/{urllib.parse.quote(ref)}?translation={translation}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": f"Could not reach bible-api.com: {str(e)[:120]}"}
    if data.get("error"):
        return {"ok": False, "error": data["error"]}
    return {"ok": True, "demo": False, "reference": data.get("reference", ref), "translation": data.get("translation_id", translation), "translation_name": data.get("translation_name", ""),
            "verses": [{"verse": v.get("verse"), "text": (v.get("text") or "").strip()} for v in data.get("verses", [])], "copyright": data.get("translation_note", "Public domain.")}
