"""Weather for Pineville, LA from Open-Meteo (free, no key), cached half an
hour. When the fetch fails the answer says so; nothing is made up (round 3, 13).
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request

from .config import load

LAT, LON = 31.32, -92.43
PLACE = "Pineville, LA"
# Round 7, 111: both campuses on the screensaver and the widget. [church] weather_places
# overrides: [{name, lat, lon}, ...]; the first is the main one.
PLACES = [{"name": "Pineville, LA", "lat": 31.32, "lon": -92.43}, {"name": "Alexandria, LA", "lat": 31.31, "lon": -92.45}]
URL = ("https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
       "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,precipitation"
       "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
       "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&timezone=America%2FChicago&forecast_days=6")
TTL = 30 * 60

# WMO weather interpretation codes, in words
_WORDS = [
    ((0,), "Clear"), ((1,), "Mostly clear"), ((2,), "Partly cloudy"), ((3,), "Overcast"),
    ((45, 48), "Fog"), ((51, 53, 55), "Drizzle"), ((56, 57), "Freezing drizzle"),
    ((61, 63, 65), "Rain"), ((66, 67), "Freezing rain"), ((71, 73, 75, 77), "Snow"),
    ((80, 81, 82), "Showers"), ((85, 86), "Snow showers"), ((95,), "Thunderstorm"), ((96, 99), "Thunderstorm with hail"),
]
_ICON = {"Clear": "sun", "Mostly clear": "sun", "Partly cloudy": "cloud-sun", "Overcast": "cloud", "Fog": "fog", "Drizzle": "rain", "Freezing drizzle": "rain",
         "Rain": "rain", "Freezing rain": "rain", "Snow": "snow", "Showers": "rain", "Snow showers": "snow", "Thunderstorm": "storm", "Thunderstorm with hail": "storm"}


def words(code) -> str:
    """A WMO code as a word or two. Pure."""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return "—"
    for codes, w in _WORDS:
        if code in codes:
            return w
    return "—"


def icon(code) -> str:
    return _ICON.get(words(code), "cloud")


_cache = {"at": 0.0, "data": None}
_caches: dict = {}
_lock = threading.Lock()


def places() -> list[dict]:
    raw = load().raw
    c = (raw.get("church") if isinstance(raw, dict) else None) or {}
    out = []
    for pl in c.get("weather_places") or PLACES:
        try:
            out.append({"name": str(pl["name"])[:60], "lat": float(pl["lat"]), "lon": float(pl["lon"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out or list(PLACES)


def _sample(place: str = PLACE, shift: int = 0) -> dict:
    from datetime import date, timedelta
    today = date.today()
    days = [(0, 74 + shift, 52, 0), (2, 71 + shift, 50, 10), (61, 66, 55, 80), (3, 68, 54, 30), (1, 72, 51, 5), (0, 75, 53, 0)]
    return shape({"current": {"temperature_2m": 68.4 + shift, "apparent_temperature": 68.0 + shift, "weather_code": 1, "wind_speed_10m": 6.3, "precipitation": 0.0},
                  "daily": {"time": [(today + timedelta(days=i)).isoformat() for i in range(6)], "weather_code": [d[0] for d in days],
                            "temperature_2m_max": [d[1] for d in days], "temperature_2m_min": [d[2] for d in days], "precipitation_probability_max": [d[3] for d in days]}},
                 demo=True, place=place)


def shape(raw: dict, demo: bool = False, place: str = PLACE) -> dict:
    """Open-Meteo's answer in the dashboard's shape. Pure."""
    cur = raw.get("current") or {}
    d = raw.get("daily") or {}
    days = []
    for i, day in enumerate(d.get("time") or []):
        days.append({"date": day, "code": (d.get("weather_code") or [None])[i] if i < len(d.get("weather_code") or []) else None,
                     "words": words((d.get("weather_code") or [None] * 9)[i]), "icon": icon((d.get("weather_code") or [None] * 9)[i]),
                     "hi": _r((d.get("temperature_2m_max") or [None] * 9)[i]), "lo": _r((d.get("temperature_2m_min") or [None] * 9)[i]),
                     "rain": (d.get("precipitation_probability_max") or [None] * 9)[i]})
    return {"ok": True, "place": place, "demo": demo, "source": "Open-Meteo",
            "now": {"temp": _r(cur.get("temperature_2m")), "feels": _r(cur.get("apparent_temperature")), "code": cur.get("weather_code"),
                    "words": words(cur.get("weather_code")), "icon": icon(cur.get("weather_code")), "wind": _r(cur.get("wind_speed_10m")), "rain": cur.get("precipitation")},
            "days": days}


def _r(v):
    try:
        return round(float(v))
    except (TypeError, ValueError):
        return None


def fetch(force: bool = False) -> dict:
    if load().demo:
        return _sample()
    with _lock:
        if not force and _cache["data"] and time.time() - _cache["at"] < TTL:
            return _cache["data"]
        try:
            pl = places()[0]
            req = urllib.request.Request(URL.format(lat=pl["lat"], lon=pl["lon"]), headers={"User-Agent": "ariseOS/weather"})
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = json.loads(r.read().decode("utf-8"))
            data = shape(raw, place=pl["name"])
            data["fetched"] = time.strftime("%Y-%m-%dT%H:%M")
            _cache.update(at=time.time(), data=data)
            return data
        except Exception as e:  # noqa: BLE001 - offline, DNS, a changed API: all the same to the widget
            stale = _cache["data"]
            if stale:
                return {**stale, "stale": True, "why": str(e)[:160]}
            return {"ok": False, "place": PLACE, "why": f"could not reach Open-Meteo: {str(e)[:160]}"}


def fetch_place(pl: dict, force: bool = False) -> dict:
    """One place, cached half an hour like the main one."""
    if load().demo:
        return _sample(pl["name"], shift=1 if pl["name"] != PLACE else 0)
    if pl["name"] == places()[0]["name"]:
        return fetch(force)
    with _lock:
        c = _caches.get(pl["name"]) or {"at": 0.0, "data": None}
        if not force and c["data"] and time.time() - c["at"] < TTL:
            return c["data"]
        try:
            req = urllib.request.Request(URL.format(lat=pl["lat"], lon=pl["lon"]), headers={"User-Agent": "ariseOS/weather"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = shape(json.loads(r.read().decode("utf-8")), place=pl["name"])
            data["fetched"] = time.strftime("%Y-%m-%dT%H:%M")
            _caches[pl["name"]] = {"at": time.time(), "data": data}
            return data
        except Exception as e:  # noqa: BLE001
            if c["data"]:
                return {**c["data"], "stale": True, "why": str(e)[:160]}
            return {"ok": False, "place": pl["name"], "why": f"could not reach Open-Meteo: {str(e)[:160]}"}


def all_places(force: bool = False) -> dict:
    """The main place's answer, as before, plus every place under "places" (round 7, 111)."""
    pls = places()
    main = fetch_place(pls[0], force)
    return {**main, "places": [main] + [fetch_place(pl, force) for pl in pls[1:]]}


def summary(data: dict | None = None) -> str:
    """One line for a morning report: today's sky, high and low, the chance of rain. Empty when there is no weather."""
    d = data or fetch()
    if not d.get("ok") or not d.get("days"):
        return ""
    t = d["days"][0]
    rain = f", {t['rain']}% chance of rain" if t.get("rain") is not None and t["rain"] >= 20 else ""
    return f"{PLACE}: {t['words'].lower()}, high {t['hi']}°, low {t['lo']}°{rain}."
