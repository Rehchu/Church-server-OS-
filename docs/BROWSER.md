# The browser: Firefox in the ariseOS look

Bradly asked (Oct 28) for Firefox, from github.com/mozilla-firefox/firefox, as
the OS's web browser, themed to match. This is how it is done and why.

## What runs

The closet monitor runs **Firefox**, Mozilla's own build of that repository,
from Mozilla's apt repository (packages.mozilla.org). It is not the Ubuntu
snap. `cage` shows it full screen on tty1 as the `arise-kiosk` user
(`config/systemd/arise-kiosk.service` runs `/usr/local/bin/arise-browser`).

Firefox is not compiled on the box. A build from source takes several hours on
a large machine and more than 40 GB of disk, and every security release would
mean another one. Mozilla's build of the same code, customised through the
layers Firefox supports for exactly this, gets every update the day Mozilla
ships it. The source repository is still used: every policy, preference and
toolbar element below was checked against it (main, Firefox 161), and the
tests validate the policy against Firefox's own schema
(`tests/fixtures/firefox-policies-schema.json`).

## How it is themed

| Layer | File on the box | From the repo | What it does |
|---|---|---|---|
| Enterprise policy | `/etc/firefox/policies/policies.json` | written by `scripts/arise-browser-policies.py` from `[browser]` in arise.toml | the desktop as home page; no telemetry, studies, Pocket, sponsored tiles, Firefox account, AI sidebar; saved passwords on; Google the default search; uBlock Origin installed, any other add-on allowed; Safe Browsing on; dark theme; compact; the church certificate trusted; the site list when `open_web = false` |
| Theme | `/var/lib/arise/browser/template/chrome/userChrome.css`, copied into every profile | `config/firefox/chrome/userChrome.css` | ink toolbars, square corners, Oswald caps tabs, the active tab's red top rule, a red ring on the address field, ink menus with red highlights, clutter buttons removed |
| Page theme | `.../chrome/userContent.css` | `config/firefox/chrome/userContent.css` | Firefox's own pages (blank, errors, add-ons, the "blocked" page) in ink and red; websites keep their design and are asked for their dark mode |
| Startup config | `<firefox>/ariseos.cfg` + `defaults/pref/autoconfig.js` | `config/firefox/` | the new-tab page |
| New tab | `http://127.0.0.1:4147/newtab.html` | `web/newtab.html` | the clock, the next service, the verse of the day, tiles for the desktop, Claude, ChatGPT, Grok, YouTube Studio, StreamYard, the church site and the Bible |
| Fonts | `/usr/local/share/fonts/arise/` | Google Fonts (OFL) | Anton and Oswald, so the look holds with the internet down |

## How it behaves

- **The desktop is the first tab, and its toolbars step aside.** When the
  selected tab is the ariseOS desktop (page title "ariseOS"), Firefox hides its
  own bars, so the monitor shows only the desktop, edge to edge. That tab has
  no close button.
- **Anything the desktop opens arrives as a tab** with the themed bar (Claude,
  YouTube Studio, StreamYard). Closing it returns to the desktop. The
  dashboard's title must stay exactly "ariseOS" for this; a test pins it.
- **A new tab** is the ariseOS new tab. Its "The desktop" and "Bible" tiles
  close the tab and hand back to the desktop instead of opening a second one.
- **A full web browser** (Bradly, Oct 29: "Firefox in the OS should be a full
  web browser as well"). Any site opens; only the admins use the closet OS.
  `open_web = false` in `[browser]` brings back the old list (the box, the
  Assistants, YouTube and Google sign-in, StreamYard, the church sites, GitHub,
  Tailscale, plus `allow`), then `sudo arisectl browser apply`.
- **Each admin has their own Firefox** (round 6, 29 to 35; below). Card and
  address autofill stay off. Camera, microphone, location and notification
  prompts are blocked.
- **Updates.** apt installs Firefox updates with the security updates
  (`/etc/apt/apt.conf.d/52arise-firefox`); Firefox's own updater is off.
- **If Firefox is ever missing,** the launcher falls back to Epiphany, the old
  browser, so the monitor is never blank. `arisectl browser status` says which
  is in use.

## One profile per admin (round 6, 29 to 35)

The closet OS is for the four admins (Bradly, Kristina, Apostle Bryant, Pastor
Vanessa; round 6, 21). Each one gets a Firefox of their own: their history,
sign-ins, saved passwords and add-ons.

| What | How |
|---|---|
| Where a profile lives | `/var/lib/arise/browser/profiles/<user>`, made on that admin's first sign-in at the monitor from `/var/lib/arise/browser/template` (the theme and `user.js`) |
| Switched when | an admin signs in at the monitor. The dashboard asks `/usr/local/sbin/arise-browser-profile switch <user>` (run as root by the server), Firefox restarts into that profile and opens the desktop already signed in: the server holds the session for one minute behind a one-time token (`/?kiosk=1&handoff=…`) |
| Locked | the screen lock switches back to a **neutral** profile, made fresh in the kiosk's runtime folder each time and thrown away when Firefox closes, so the lock screen's browser remembers nothing |
| Kept private | at rest every admin's profile is root's, mode 0700: the kiosk user cannot open it. It is lent to `arise-kiosk` only while that admin is signed in, and taken back on lock. Only the monitor itself can ask for a switch (a request from this box that did not come through Caddy) |
| Passwords | Firefox's own password manager, on, per profile (30). There is no primary password; the profile's ownership is what keeps one admin's passwords from the next |
| Ad blocker | uBlock Origin, installed for every admin by the policy and not removable (31) |
| Search | Google, the default search engine (32, the `SearchEngines` policy) |
| Downloads | the admin's own home folder's `Downloads` (`/srv/arise/homes/<user>/Downloads`), so they reach their Mac through sync (33). The kiosk may write there only while it is that admin's turn (an ACL taken back on lock); what it saved is then handed to the admin |
| Add-ons | any add-on an admin chooses (34) |
| Filtering | Firefox's Safe Browsing for malware, phishing and harmful downloads; nothing else is blocked (35) |
| The look | the ariseOS theme is copied into the profile on every switch, so a theme update reaches every admin; the desktop-tab behaviour above is the same in every profile |

Each switch and each lock restarts Firefox (a second or two). An older
install's single shared profile in `/var/lib/arise/browser` itself is left on
disk and no longer used; deleting it is Bradly's click.

## Commands

```
sudo bash /opt/arise/scripts/arise-browser-setup     install or repair Firefox, the theme, the policy (installer step 6d runs it)
sudo bash /opt/arise/scripts/arise-browser-setup --dry-run
sudo arisectl browser status                          version, policy, theme files, the monitor
sudo arisectl browser apply                           rewrite the policy from arise.toml, copy the theme, restart the monitor
arisectl browser policy                               print the policy that would be written
```

## Not verified here

Mozilla's servers are blocked from the sandbox this was built in, so Firefox
itself has not run with this configuration yet. Checked: the policy against
Firefox's schema, every preference against Firefox's allowed list, the toolbar
ids and theme variables against the source, the new-tab page in a browser,
the setup script's dry run. The profile switch (the restart, the hand-over,
the ownership and the Downloads ACL) has not run against a real cage and
Firefox either. The first real run is on the Dell (or the home PC)
at install; `arisectl browser status` is the check. If Firefox renames a
toolbar element in a later version, the theme degrades to Firefox's own dark
look, never to a broken window.

## Not built, and why

- **A rebranded build** ("ariseOS Browser"). Mozilla's trademark policy does
  not allow a modified binary to keep the Firefox name, and an unbranded
  rebuild would lose Mozilla's update stream. The theme carries the identity.
- **Firefox on the Macs.** The Macs keep whatever browser their users like;
  the dashboard works in Safari, Chrome and Firefox alike.
