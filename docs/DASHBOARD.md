# The dashboard — `http://arise-server:4147`

A desktop in the browser, in the church's own look: a menu bar across the top,
windows you drag and resize, a floating dock along the bottom, a launchpad with
every app. Served by `arise-web.service` from `web/`; it talks to the JSON API
in `server/arise_server/`. Plain HTML, CSS and JS; no build step.

The look is the website's "House Lights Down" theatre: ink and Arise red,
Anton and Oswald, the two red dashes before a kicker, numbered rooms (every
app carries its folio: 01 Overview … 15 Settings), a red footlight along the
diagonal cut at the bottom of the wallpaper.

## The parts

| Part | What it does |
|---|---|
| **Menu bar** | the flame opens the launchpad; the app name of the focused window; live CPU, RAM and uptime; a red *needs you* count that opens the Overview; the live/preview dot; the clock; your user (sign out) |
| **Desktop widgets** (left) | *Needs you* (or *All clear*), live CPU/memory with a sparkline, *The box* (directory, automator, quota, backups, Synology, what runs next), *This week* (service times) |
| **Windows** | title bar with the folio and the app name, three dots (close, minimise, zoom), drag by the bar, resize from the corner, double-click the bar to zoom. On a phone every window is full screen |
| **Dock** | the ten everyday apps, a dot under the running ones, hover for the name; the last icon is the launchpad. On a phone it becomes a bottom bar you can scroll |
| **Launchpad** | all fifteen apps with their folio and a one-line purpose; type to filter; Escape closes |

## The apps

| # | App | What it shows | What it can do |
|---|---|---|---|
| 01 | **Overview** | the "Needs you" list, live stats, directory / automator / backup cards, disks, tonight's timetable | links into the others |
| 02 | **Directory** | domain health (LDAP, Kerberos, DNS), users, groups, joined computers | add a user, reset a password, enable/disable, delete (type the name), new group, add a member |
| 03 | **Files** | *Browse*: the server's data root and the Synology, folder by folder, with download and upload; *Shares*: the SMB shares | new share, remove a share (files stay). No delete, no move: that is Finder's job |
| 04 | **Backups** | repository size, last run per job, full history with the reason for every failure, snapshots, restore instructions | run a job now, `restic check`, refresh the GitHub mirror |
| 05 | **Automator** | last run, quota today, token state, holds and rules, the latest report, the worklist, past reports | preview tonight (dry run), run now (confirmed) |
| 06 | **Sermons** | the channel from the automator's inventory, no quota spent: Sunday services, Glory Nights, Shorts, conferences, with thumbnails, playlists, the live page | open on YouTube or in Studio |
| 07 | **Bible** | a passage from bible-api.com (World English Bible, KJV and others; no key), verse numbers in the website's style, quick chips | copy, open on arisecenla.church's Bible Search |
| 08 | **Apps** | installed Docker apps with state, address, CPU and memory; the store (File Browser, Uptime Kuma, Syncthing, Vaultwarden, Guacamole, wg-easy) | install, start, stop, restart, update, logs, remove (data kept) |
| 09 | **Remote** | SSH state, Tailscale devices, WireGuard peers, Guacamole, and a plain "how to reach it from Alexandria, the Hub or home" | add a WireGuard peer and get its config |
| 10 | **Campuses** | Pineville, Alexandria, the Apostolic Hub: reachability, network, which joined computers sit at which site | read only |
| 11 | **Terminal** | a real shell on the server (xterm.js over a websocket) | everything `arisectl` does, and everything else. Treat it like root |
| 12 | **Synology** | mount state, free space, DSM health and RAID when `dsm_url` is set, off-site copy | mount, unmount |
| 13 | **Services** | the systemd units that matter | start, stop, restart, jump to logs |
| 14 | **Logs** | the last 300 journal lines of any unit | pick a unit, refresh |
| 15 | **Settings** | updates (packages, Arise Server itself), the daily note, power (reboot, shut down), every non-secret value of `arise.toml` | update, upgrade, test the note, reboot/shut down with the word typed |

## Rules it keeps

- **Nothing is deleted without typing its name.** Users, shares and apps ask
  for the exact name. Home folders, share folders, app data and snapshots are
  never removed by the dashboard at all.
- **Secrets never reach the browser.** `GET /api/settings` strips every key
  with `password`, `token` or `secret` in its name.
- **Sample data is labelled.** When a tool is missing or there is no config,
  the response carries `"demo": true` and the menu bar shows an amber *Sample
  data* badge. The published preview shows *Preview · sample data*.
- **One admin login.** `arisectl admin set-password` writes a bcrypt hash into
  `arise.toml`; the session is a signed cookie that expires after
  `session_hours`. The Terminal uses the same cookie. With no hash set the page
  refuses to show anything and tells you the command.

## Live stats

`/api/stats/stream` is a Server-Sent Events feed: one JSON sample a second
(CPU, per core, temperature where the board reports it, memory, swap, network
and disk rates, load, uptime). One collector thread samples psutil; every
open browser reads the same cache. `/api/stats/history` returns the last 60
samples so the sparklines are full on first paint.

## Reaching it

On the church network: `http://arise-server:4147`. From Alexandria, the Hub or
home: the same address over the VPN (docs/REMOTE-ACCESS.md), or
`https://arise-server.ad.arisecenla.church` once Caddy is on. It is not meant
to face the internet directly; the VPN is the front door.

## Running it anywhere

```bash
cd server && pip install -r requirements.txt
python -m arise_server --demo --port 4147     # sample data, no root needed
```

`python3 scripts/gen-demo-data.py` rebuilds `web/demo-data.js` from the same
sample responses; that file is what the static preview page uses. `web/vendor/`
holds xterm.js (MIT), fetched with `npm pack`, unmodified.
