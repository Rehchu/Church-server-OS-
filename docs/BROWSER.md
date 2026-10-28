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
| Enterprise policy | `/etc/firefox/policies/policies.json` | written by `scripts/arise-browser-policies.py` from `[browser]` in arise.toml | the desktop as home page; no telemetry, studies, Pocket, sponsored tiles, Firefox account, AI sidebar, password saving; dark theme; compact; uBlock Origin; the church certificate trusted; the site list |
| Theme | `/var/lib/arise/browser/chrome/userChrome.css` | `config/firefox/chrome/userChrome.css` | ink toolbars, square corners, Oswald caps tabs, the active tab's red top rule, a red ring on the address field, ink menus with red highlights, clutter buttons removed |
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
- **Sites are a list, not the open web** (`open_web = false`). The box, the
  Assistants, YouTube and Google sign-in, StreamYard, the church site, GitHub
  and Tailscale are on it. Any other site shows Firefox's "blocked" page with
  "Not on the monitor's list". Add sites to `allow` in `[browser]`, or set
  `open_web = true`, then run `sudo arisectl browser apply`. Only pages and
  frames are judged, so scripts, images and fonts from CDNs load as usual.
- **Nothing personal is kept.** The monitor is shared: no saved passwords,
  card or address autofill. Sign-ins stay as cookies, like the old browser.
  Camera, microphone, location and notification prompts are blocked.
- **Updates.** apt installs Firefox updates with the security updates
  (`/etc/apt/apt.conf.d/52arise-firefox`); Firefox's own updater is off.
- **If Firefox is ever missing,** the launcher falls back to Epiphany, the old
  browser, so the monitor is never blank. `arisectl browser status` says which
  is in use.

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
the setup script's dry run. The first real run is on the Dell (or the home PC)
at install; `arisectl browser status` is the check. If Firefox renames a
toolbar element in a later version, the theme degrades to Firefox's own dark
look, never to a broken window.

## Not built, and why

- **A rebranded build** ("ariseOS Browser"). Mozilla's trademark policy does
  not allow a modified binary to keep the Firefox name, and an unbranded
  rebuild would lose Mozilla's update stream. The theme carries the identity.
- **Firefox on the Macs.** The Macs keep whatever browser their users like;
  the dashboard works in Safari, Chrome and Firefox alike.
