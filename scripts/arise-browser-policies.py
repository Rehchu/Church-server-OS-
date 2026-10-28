#!/usr/bin/env python3
"""Writes Firefox's enterprise policy for the ariseOS closet monitor.

    python3 scripts/arise-browser-policies.py [--config /etc/arise/arise.toml] [--out FILE]

Reads [browser] from arise.toml:

    [browser]
    open_web = false     # true: any site; false: only the list below and the built-in one
    allow = []           # extra sites, as host names ("bible.com") or match patterns

Every policy name and preference here was checked against Firefox's own
schema and allow-list in mozilla-firefox/firefox
(browser/components/enterprisepolicies/schemas/policies-schema.json,
Policies.sys.mjs: Preferences' allowed prefixes); tests/test_arise_server.py
validates the output against a copy of that schema.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DASHBOARD = "http://127.0.0.1:4147"
CADDY_ROOT = "/etc/arise/ca/arise-root.crt"   # a world-readable copy of Caddy's root (the kiosk user cannot read /var/lib/caddy)

# The sites the monitor may open as a page or a frame (Firefox's site filter only
# judges documents and frames, so scripts and images from CDNs load as usual).
# Sign-in hops are included: Google for YouTube Studio, OpenAI/Apple/Microsoft for
# ChatGPT, X for Grok, Cloudflare's challenge frame for both.
BUILT_IN = [
    "127.0.0.1", "localhost", "arise-server", "*.ad.arisecenla.com", "arise-pineville", "arise-home", "arise-alexandria",
    "claude.ai", "*.claude.ai", "*.anthropic.com",
    "chatgpt.com", "*.chatgpt.com", "*.openai.com",
    "grok.com", "*.grok.com", "x.ai", "*.x.ai", "x.com", "*.x.com",
    "youtube.com", "*.youtube.com", "youtu.be", "*.ytimg.com", "*.googlevideo.com", "*.google.com", "*.googleusercontent.com", "*.gstatic.com", "*.recaptcha.net",
    "streamyard.com", "*.streamyard.com",
    "arisecenla.church", "*.arisecenla.church", "arisecenla.com", "*.arisecenla.com",
    "github.com", "*.github.com", "*.tailscale.com",
    "challenges.cloudflare.com", "appleid.apple.com", "login.microsoftonline.com", "login.live.com",
]


def patterns(hosts: list[str]) -> list[str]:
    """Host names to match patterns (any scheme, any port, any path)."""
    out = []
    for h in hosts:
        h = h.strip()
        if not h:
            continue
        if "://" in h:          # already a match pattern
            out.append(h)
            continue
        out.append(f"*://{h}/*")
    return sorted(set(out))


def build(cfg: dict) -> dict:
    b = cfg.get("browser", {}) if isinstance(cfg, dict) else {}
    hostname = (cfg.get("system", {}) or {}).get("hostname", "arise-server")
    allow = BUILT_IN + [hostname] + list(b.get("allow", []) or [])
    pref = lambda v, status="locked": {"Value": v, "Status": status}  # noqa: E731
    p = {
        "DisableAppUpdate": True,                 # apt updates it (packages.mozilla.org)
        "DisableTelemetry": True,
        "DisableFirefoxStudies": True,
        "DisablePocket": True,
        "DisableFirefoxAccounts": True,
        "DisableProfileImport": True,
        "DisableSetDesktopBackground": True,
        "DisableFeedbackCommands": True,
        "DontCheckDefaultBrowser": True,
        "SkipTermsOfUse": True,
        "OverrideFirstRunPage": "",
        "OverridePostUpdatePage": "",
        "NoDefaultBookmarks": True,
        "DisplayBookmarksToolbar": "never",
        "Homepage": {"URL": f"{DASHBOARD}/?kiosk=1", "Locked": True, "StartPage": "homepage"},
        "FirefoxHome": {"Search": False, "TopSites": False, "SponsoredTopSites": False, "Highlights": False,
                        "Pocket": False, "SponsoredPocket": False, "Snippets": False, "Locked": True},
        "FirefoxSuggest": {"WebSuggestions": False, "SponsoredSuggestions": False, "ImproveSuggest": False, "Locked": True},
        "UserMessaging": {"ExtensionRecommendations": False, "FeatureRecommendations": False, "UrlbarInterventions": False,
                          "SkipOnboarding": True, "MoreFromMozilla": False, "FirefoxLabs": False, "Locked": True},
        "GenerativeAI": {"Enabled": False, "Locked": True},   # Claude lives in Assistants, signed in as the church
        "PasswordManagerEnabled": False,          # a shared closet screen keeps no passwords; Vaultwarden does
        "OfferToSaveLogins": False,
        "AutofillCreditCardEnabled": False,
        "AutofillAddressEnabled": False,
        "BlockAboutConfig": True,
        "DisableDeveloperTools": True,
        "PopupBlocking": {"Allow": [DASHBOARD, f"http://{hostname}:4147"], "Default": True, "Locked": True},
        "Permissions": {k: {"BlockNewRequests": True, "Locked": True} for k in ("Camera", "Microphone", "Location", "Notifications", "VirtualReality")},
        "Certificates": {"Install": [CADDY_ROOT]},   # the church CA: the padlock on the box's own pages
        "EnableTrackingProtection": {"Value": True, "Cryptomining": True, "Fingerprinting": True},
        "ExtensionSettings": {
            "*": {"installation_mode": "blocked", "blocked_install_message": "Add-ons on the closet monitor are set by the server."},
            "uBlock0@raymondhill.net": {"installation_mode": "force_installed",
                                        "install_url": "https://addons.mozilla.org/firefox/downloads/latest/ublock-origin/latest.xpi"},
        },
        "Preferences": {
            "toolkit.legacyUserProfileCustomizations.stylesheets": pref(True),   # the house theme (userChrome.css)
            "extensions.activeThemeID": pref("firefox-compact-dark@mozilla.org", "default"),
            "browser.uidensity": pref(1),
            "browser.theme.toolbar-theme": pref(0),
            "browser.theme.content-theme": pref(0),
            "ui.systemUsesDarkTheme": pref(1),
            "layout.css.prefers-color-scheme.content-override": pref(0),
            "browser.tabs.closeWindowWithLastTab": pref(False),
            "browser.link.open_newwindow": pref(3),            # a new window opens as a tab: closing it shows the desktop
            "browser.link.open_newwindow.restriction": pref(0),
            "browser.sessionstore.resume_from_crash": pref(False),
            "browser.tabs.firefox-view": pref(False),
            "browser.tabs.tabmanager.enabled": pref(False),
            "browser.toolbars.bookmarks.visibility": pref("never"),
            "browser.ml.chat.enabled": pref(False),
            "browser.urlbar.suggest.quicksuggest.sponsored": pref(False),
            "browser.urlbar.trending.featureGate": pref(False),
            "browser.newtabpage.activity-stream.feeds.section.topstories": pref(False),
            "browser.aboutwelcome.enabled": pref(False),
            "browser.translations.automaticallyPopup": pref(False),
            "dom.disable_open_during_load": pref(True),
            "dom.allow_scripts_to_close_windows": pref(True),   # the new tab's "The desktop" tile closes itself
            "browser.tabs.selectOwnerOnClose": pref(True),      # closing a tab returns to the one that opened it
            "media.autoplay.default": pref(1, "default"),
            "browser.display.use_system_colors": pref(False),
        },
    }
    if not b.get("open_web", False):
        p["WebsiteFilter"] = {"Block": ["<all_urls>"], "Exceptions": patterns(allow)}
    return {"policies": p}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="/etc/arise/arise.toml")
    ap.add_argument("--out", default="-")
    a = ap.parse_args(argv)
    cfg = {}
    try:
        import tomllib
        with open(a.config, "rb") as f:
            cfg = tomllib.load(f)
    except FileNotFoundError:
        pass
    doc = json.dumps(build(cfg), indent=2) + "\n"
    if a.out == "-":
        sys.stdout.write(doc)
    else:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
