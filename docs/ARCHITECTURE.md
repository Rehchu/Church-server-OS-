# Arise Server — architecture and the contract every part follows

Arise Server is the church's own server operating layer for Arise Church,
Pineville LA. It is modelled on three things:

| Borrowed from | What we took |
|---|---|
| **Monolith OS** (shirou-eh) | the shape: one CLI (`arisectl`), one config file, one web dashboard, an installer, resource profiles, restic backups, app templates, a landing page |
| **HomeDock OS** (BansheeTech) | the plumbing: a Python backend, a browser dashboard that streams live stats, apps as Docker Compose stacks, a desktop-like feel |
| **arisecenla.church** (the Wix site) | the look: Anton + Oswald, ink `#0A0A0C`, Arise red `#D6222D`, bone `#F4F2F0`, the two red dashes, skewed red strips, square buttons, uppercase letter-spaced labels |

Everything is plain Python + plain HTML/CSS/JS. No Node build step, no
framework, so it installs on an old PC with nothing but Python 3.11+.

## What it is for

1. **A directory, like Active Directory.** A Samba Active Directory Domain
   Controller. Real AD: Kerberos, LDAP, DNS, group policy. Macs bind to it with
   Apple's own Directory Utility; the Synology joins it too. One login
   everywhere. Realm `AD.ARISECENLA.CHURCH`, NetBIOS `ARISE`.
   (Never `.local`: macOS Bonjour owns that suffix and binding breaks.)
2. **Files and user profiles on the server.** Every domain user gets a home
   share (`\\arise-server\homes\<user>`, or on the Synology once it is joined).
   Macs log in with mobile accounts and sync Desktop/Documents to that share.
   `mac/migrate-mac-user.sh` moves an existing local Mac account's data over.
3. **The automator.** The nightly YouTube job (`arise_daily.py`) runs on the
   server at 2:05 AM Central from a systemd timer, with its reports, hold
   list, worklist and quota ledger visible in the dashboard.
4. **Backups of everything Arise.** restic snapshots of the automator folder,
   home shares, the Proclaim graphics, the website workspace and a mirror of
   every GitHub repo, to the Synology, on a schedule, with history in the
   dashboard.
5. **Apps.** Docker Compose templates (file browser, uptime monitor, sync),
   one click each, like HomeDock's store but only what the church uses.
6. **Feel great.** A dashboard that loads instantly, streams live CPU, RAM,
   disk, network and service health, and looks like the church's own site.
7. **Reachable from a locked closet.** Key-only SSH, a VPN (Tailscale or
   WireGuard), Guacamole remote desktop in the browser, HTTPS through Caddy,
   and a Terminal app in the dashboard. Nothing is forwarded on the router
   except UDP 51820 when WireGuard is chosen. docs/REMOTE-ACCESS.md.
8. **Three sites.** Pineville (the server, the DC, the NAS), Arise Church
   Alexandria and the Apostolic Hub, over the VPN, with a Campuses app that
   watches each. docs/MULTI-SITE.md.

## Names, paths, ports — fixed

| Thing | Value |
|---|---|
| Product | **Arise Server** |
| CLI | `arisectl` |
| Web service | `arise-web.service`, port **4147** (the channel handle, @arisechurch4147) |
| Hostname | `arise-server` in the code, the units, the Caddyfile and these docs today |
| Nodes (decided Oct 28, round 4, 110; not yet in the code) | the boxes are **`arise-pineville`** (the church's server, the strongest PC), **`arise-home`** (Bradly's full install at his house, the control node and replica) and later **`arise-alexandria`**. The hostname becomes a per-node value when the node work lands (docs/NODES.md); until then `arise-server` stays the name the installer sets |
| AD realm / NetBIOS | `AD.ARISECENLA.CHURCH` / `ARISE` |
| Install root (code) | `/opt/arise` |
| Config | `/etc/arise/arise.toml`, `/etc/arise/backups.yaml` |
| Secrets | `/etc/arise/secrets/` (restic password, DSM credentials, `vapid.json`, `apps/<name>.env`, `totp/<user>.json`, `rescue-password`, `wayvnc`, `discord.toml` when set), mode 0600; `/etc/arise/SAFE-CARD.txt` (the arise-rescue password and the disk passphrase line, for the safe, never the door) |
| State | `/var/lib/arise/` (`state.json`, `backup-history.json`, metrics ring) |
| Data root | `/srv/arise/` — `homes/`, `shares/`, `automator/`, `apps/`, `backups/` |
| Automator checkout | `/srv/arise/automator/ARISE_YouTube_Updater` (clone of `Rehchu/arise-youtube-automation`) |
| Synology mount | `/mnt/synology` (SMB or NFS), subfolders `arise-backups/`, `homes/` |
| Timers | `arise-automator.timer` 02:05 America/Chicago · `arise-backup.timer` 03:00 · `arise-mirror.timer` 04:00 · `arise-trash.timer` 04:30 (the 30-day sweep) · `arise-notify.timer` 07:00 (off: no daily note) · `arise-devices.timer` hourly network scan · `arise-idle-apps.timer` every 15 min (desktop programs idle an hour are stopped) · `arise-drill.timer` monthly · `arise-update.timer` Saturday 03:30 (only what Software Update queued; a snapshot first) · `arise-clamscan.timer` Sunday 23:30 · `arise-monitor-off.timer` 23:00 / `arise-monitor-on.timer` 06:00 (the closet panel, with `--kiosk`) · `arise-wayvnc.service` (Screen Sharing of the panel). Nothing runs during a service |
| VPN | Tailscale (100.64.0.0/10) or WireGuard `wg0` on UDP 51820, tunnel `10.47.0.0/24` |
| Remote desktop | Guacamole, port 8084 (`remote.ad.arisecenla.church` behind Caddy) |
| HTTPS | Caddy, `tls internal`, `config/caddy/Caddyfile`; on by default since v0.8 (`--no-caddy` to skip); the root certificate is served at `/ca.crt` and `enroll-mac.sh` / `bind-mac.sh --dns` trust it on each Mac |
| Closet monitor | `arise-kiosk.service` on tty1: `cage` + Epiphany (app mode) showing `http://127.0.0.1:4147/?kiosk=1` as user `arise-kiosk` (uid 1501); or `arise-console.service` (`arisetui --kiosk`) for a text screen. They conflict; one at a time |
| Logs | `journalctl -u arise-*`, plus `/var/log/arise/` |
| Windows mode root | `C:\Arise\` with the same subfolders (`config\`, `data\`, `automator\`) |

Linux is the recommended install (Ubuntu Server 24.04 LTS on the old PC).
Windows mode exists for the case where Windows must stay: it runs the
dashboard, the automator and the backups, but **a Windows 10/11 PC cannot be a
domain controller**. Directory features need the Linux install.

## Repository layout

```
README.md                landing-style overview (Monolith README shape)
INSTALL.md               both install paths, step by step
docs/                    ARCHITECTURE (this), DIRECTORY, MAC-MIGRATION, SYNOLOGY, BACKUPS, AUTOMATOR,
                         HARDWARE, DASHBOARD, CLI, REMOTE-ACCESS, MULTI-SITE, EVERYDAY, FINDER, SYSTEM-APPS,
                         STORE, SECURITY, REINSTALL, NODES, PARITY, ROADMAP, ANSWERS
catalog/catalog.yaml     the Store's catalogue of further free apps (compose generated from each entry)
CHANGELOG.md             What's New: the top section is what About shows after an update
site/                    the landing page (static, Arise design)
server/arise_server/     FastAPI backend — the JSON API and static host; v0.8 adds twofa, security, calendar,
                         help, weather, finder, updates, activity, automations, storage, monitor
web/                     the dashboard SPA (vanilla JS, Arise design)
cli/arisectl             the CLI (Python, stdlib only)
installer/               install.sh (Ubuntu; --with-tailscale --with-wireguard --with-caddy), install.ps1 (Windows), autoinstall.yaml
config/                  arise.toml.example, backups.yaml.example, systemd units, smb.conf.template, caddy/Caddyfile
templates/<app>/         compose.yaml + template.yaml per app (autostart, ram_mb, limits, theme)
mac/                     bind-mac.sh, migrate-mac-user.sh, mount-home.sh, CHECKLIST.md
tests/                   pure-function tests, `python -m unittest discover tests`
```

## The config file: `/etc/arise/arise.toml`

```toml
[system]
hostname = "arise-server"
timezone = "America/Chicago"
profile = "server"        # "server" (Linux, full) | "windows" (dashboard+automator+backups only)
data_root = "/srv/arise"

[web]
bind = "0.0.0.0"
port = 4147
# bcrypt hash of the admin password, written by `arisectl admin set-password`
admin_user = "bradly"
admin_password_hash = ""
session_hours = 8760               # a year: signed in until they sign out (round 3, 38)

[links]
days = 0                            # a share link lives until removed (Oct 28); 0 = never
max_days = 365                      # the longest life a link may be given

[directory]
enabled = true
realm = "AD.ARISECENLA.CHURCH"
netbios = "ARISE"
dns_forwarder = "1.1.1.1"
homes_path = "/srv/arise/homes"      # or /mnt/synology/homes once the NAS is joined

[automator]
enabled = true
path = "/srv/arise/automator/ARISE_YouTube_Updater"
python = "/opt/arise/venv/bin/python"
schedule = "02:05"                  # local time, America/Chicago

[backups]
restic_repo = "/mnt/synology/arise-backups/restic"
password_file = "/etc/arise/secrets/restic-password"
schedule = "03:00"
keep_daily = 14
keep_weekly = 8
keep_monthly = 12
jobs_file = "/etc/arise/backups.yaml"

[nas]
enabled = true
host = "synology.ad.arisecenla.church"
mount = "/mnt/synology"
protocol = "smb"                    # smb | nfs
share = "arise"
dsm_url = ""                        # optional, e.g. https://synology:5001 for DSM API health
dsm_credentials_file = "/etc/arise/secrets/dsm.json"

[apps]
docker = true
root = "/srv/arise/apps"

[remote]
ssh_port = 22
vpn = "tailscale"                   # tailscale | wireguard | none
wg_interface = "wg0"
wg_endpoint = ""                    # "arise.duckdns.org:51820" once the router forwards it
wg_subnet = "10.47.0.0/24"
guacamole_url = "http://arise-server:8084"
lan_subnet = "192.168.1.0/24"

[notify]
webhook_url = ""                    # Discord or Slack incoming webhook
hour = 7                            # local time of the morning report
only_when_attention = true          # quiet when there is nothing to say

[[sites]]
id = "pineville"
name = "Arise Church Pineville"
kind = "main"                       # main | campus | office
address = "501 Ates Road, Pineville, LA"
subnet = "192.168.1.0/24"
probe = ""                          # a host at the site that is always on (router, a Mac)
services = "Sunday 10:30 AM · Glory Night Monday 7 PM"
note = "The server, the Synology and the domain live here."

[[sites]]
id = "alexandria"
name = "Arise Church Alexandria"
kind = "campus"
address = ""
subnet = "192.168.2.0/24"
probe = ""
services = "Sunday 10:00 AM"
note = "Reaches the server over the VPN. Macs here bind to the domain through it."

[[sites]]
id = "hub"
name = "The Apostolic Hub"
kind = "office"
address = ""
subnet = "192.168.3.0/24"
probe = ""
services = ""
note = "Office and leadership computers. VPN clients, no site router needed."

[github]
mirror = true
mirror_path = "/srv/arise/backups/github-mirror"
repos = [
  "Rehchu/Church-server-OS-", "Rehchu/arise-youtube-automation", "Rehchu/arisechurch",
  "Rehchu/arisehub", "Rehchu/arise-church-backup", "Rehchu/arise-youtube",
  "Rehchu/projectbackups", "Rehchu/ai-chat-backups"
]
```

The backend reads it with `tomllib`. Nothing in the UI writes `arise.toml`;
the UI writes only `/var/lib/arise/state.json`. The CLI and installer write
`arise.toml`.

## The backup jobs file: `/etc/arise/backups.yaml`

```yaml
jobs:
  - id: automator
    name: YouTube automator
    paths: ["/srv/arise/automator"]
    exclude: ["**/__pycache__", "**/*.zip"]
    tags: [automator]
  - id: homes
    name: Home folders
    paths: ["/srv/arise/homes"]
    exclude: ["**/Library/Caches", "**/.Trash", "**/node_modules"]
    tags: [homes]
  - id: shares
    name: Shared folders
    paths: ["/srv/arise/shares"]
    tags: [shares]
  - id: github
    name: GitHub mirror
    paths: ["/srv/arise/backups/github-mirror"]
    tags: [github]
  - id: config
    name: Server config
    paths: ["/etc/arise", "/etc/samba", "/var/lib/samba/private"]
    tags: [config]
```

Every job runs `restic backup` with its paths and tags; the runner records
`{job, started, finished, ok, snapshot_id, bytes_added, error}` to
`/var/lib/arise/backup-history.json`. The dashboard and `arisectl backup
status` read that file. restic forget/prune runs after the nightly set with
the keep_* policy from `arise.toml`.

## The JSON API (served by `arise-web` on :4147)

All under `/api/`. All JSON. Session cookie auth; `POST /api/auth/login`
with `{user, password}`; `GET /api/auth/me`. Every router has a **demo
mode**: when the underlying tool (samba-tool, docker, restic, systemctl) is
not on the machine, or `ARISE_DEMO=1`, it returns representative sample data
and marks the response `"demo": true`. That is what lets the UI be developed
and previewed anywhere, including the published preview page.

| Route | Returns |
|---|---|
| `GET /api/overview` | hostname, profile, uptime, versions, counts (users, shares, apps, backups), health flags |
| `GET /api/stats/stream` | SSE, one JSON event per second: cpu %, per-core, ram, swap, disks, net rates, load, temps |
| `GET /api/stats/history` | last 60 samples (ring buffer) for sparklines on first paint |
| `GET /api/services` | systemd units of interest with state |
| `POST /api/services/{unit}/{start,stop,restart}` | |
| `GET /api/directory/users` · `POST` · `DELETE /{name}` · `POST /{name}/reset-password` · `POST /{name}/{enable,disable}` | samba-tool user ops |
| `GET /api/directory/groups` · `POST` · `POST /{name}/members` | |
| `GET /api/directory/computers` | joined Macs, PCs, the NAS |
| `GET /api/directory/status` | realm, DC health (`samba-tool domain info`), DNS, Kerberos |
| `GET /api/shares` · `POST` · `DELETE /{name}` | SMB shares from smb.conf + usage |
| `GET /api/backups/jobs` · `GET /api/backups/history` · `POST /api/backups/run/{job}` · `GET /api/backups/snapshots` · `GET /api/backups/repo` | restic |
| `GET /api/automator` | latest report (md), last run, next run, quota today, holds count, worklist summary, token status |
| `GET /api/automator/reports` · `GET /api/automator/reports/{name}` | |
| `GET /api/automator/worklist` · `GET /api/automator/holds` · `GET /api/automator/quota` | read-only views |
| `POST /api/automator/run` · `POST /api/automator/preview` | run-daily / preview (dry run) |
| `GET /api/apps` · `GET /api/apps/templates` · `POST /api/apps/deploy` · `POST /api/apps/{name}/{start,stop,restart,remove}` · `GET /api/apps/{name}/logs` | docker compose |
| `GET /api/nas` | mount status, free space, DSM health if configured, last Hyper Backup |
| `GET /api/logs/{unit}` | last N journal lines |
| `GET /api/settings` | the non-secret parts of arise.toml |
| `GET /api/sites` | the `[[sites]]` blocks with each probe's reply and the computers in each subnet |
| `GET /api/remote` | sshd state (port, key-only, last logins), Tailscale and WireGuard state and peers, Guacamole state |
| `POST /api/remote/wireguard/peers` `{name}` | adds a peer to `wg0`, returns the client config text |
| `GET /api/bible?ref=&translation=` | a passage from bible-api.com (public-domain texts), the Bible app |
| `GET /api/sermons` | the channel from the automator's `channel_inventory.csv`, zero quota |
| `GET /api/files/roots` · `GET /api/files/list?root=&path=` · `GET /api/files/download?root=&path=` · `GET /api/files/view?root=&path=` · `POST /api/files/upload` · `POST /api/files/mkdir` | the Finder, inside `/srv/arise` and the NAS mount; `view` is inline (Quick Look), `download` is an attachment; no delete, no move |
| `GET /api/links` · `POST /api/links` {root,path,days,note} · `DELETE /api/links/{token}` · `GET /s/{token}` (no login) | share links: a time-limited public download of one file or a zipped folder |
| `POST /api/me/password` {old,new} | a person changes their own directory password (Kerberos check of the old one first) |
| `POST /api/devices/scan?wide=1` · `GET /api/devices/cameras` | the wide scan ARPs the common ranges a device may be parked on (strays); cameras is an ONVIF WS-Discovery probe (UDP 3702, 3 s) with a reachable flag |
| `GET /manifest.webmanifest` · `GET /sw.js` · `GET /api/push/key` · `POST /api/push/subscribe` · `POST /api/push/test` · `GET /api/about/week` | the phone app (manifest, service worker, home-screen icons under `web/icons/`), web push with VAPID keys made on the box (`/etc/arise/secrets/vapid.json`), subscriptions in `/var/lib/arise/push.json`; the About window's week |
| `GET /api/church` · `GET /api/sunday` · `POST /api/sunday/{i}` · `POST /api/kiosk/open` {url} · `GET /api/public/signage` (no login) · `GET /signage` | the church (services from `[church]`, next service, verse of the day, the assistants list), the Sunday checklist (weekly, who ticked), the monitor opening a listed https site in its own window (localhost only), the lobby screen's feed and page. The other no-login routes: `/calendar.ics`, `/api/public/calendar.ics`, `/ca.crt`, `/api/public/ca.crt`, `/s/{token}` |
| `GET /api/mail` · `GET /api/mail/contacts` · `POST /api/mail/import/preview` · `POST /api/mail/import` · `POST /api/mail/preview` · `POST /api/mail/test` · `POST /api/mail/broadcasts` · `POST /api/mail/broadcasts/{id}/send` {confirm:"send"} · `GET /api/mail/broadcasts` | Resend: one audience for the church family, contacts imported from a CSV in a background thread (rate-limited), the house HTML template, a test email, broadcasts; the key is `[mail] api_key_file`, never in the browser |
| `GET /api/devices/behind` | what the other routers report as attached, read over their own API with the admin password (`[[routers]]`, kind netgear); never written |
| `GET /api/devices` · `POST /api/devices/scan` · `POST /api/devices/{mac}` {name,note,kind} · `DELETE /api/devices/{mac}` | everything on the switch: `arp-scan --localnet` (else a ping sweep and the neighbour table), merged into `/var/lib/arise/devices.json` by MAC |
| `GET /api/search?q=` | Spotlight: file names on both roots (a bounded `os.walk` index, cached 120 s), users and computers from the directory |
| `GET /api/system/updates` · `POST /api/system/update` · `POST /api/system/apt-upgrade` | apt and Arise Server updates |
| `POST /api/system/power` `{action: reboot|poweroff, confirm}` | the closet has no power button you can reach |
| `POST /api/notify/test` | sends a test line to the webhook |
| `WS /api/terminal` | a pty on the box for the Terminal app (root on the Linux install) |
| `POST /api/auth/login` → `{need_code, pending}` · `POST /api/auth/login/code` {pending, code} · `POST /api/auth/reauth` {password} | two-step sign-in (optional per person, TOTP, `twofa.py`): the second step when the person is enrolled, three wrong codes end the pending token; reauth stamps the session for five minutes and `require_recent_auth` guards `DELETE /api/directory/users/{name}` and `POST /api/system/power` |
| `GET /api/me/2fa` · `POST /api/me/2fa/setup` · `POST /api/me/2fa/enable` {code} · `POST /api/me/2fa/disable` {password, code} · `GET /api/directory/2fa` (admin) | enrol: a fresh secret in `/etc/arise/secrets/totp/<user>.json` (0600), the otpauth URI and a QR as SVG (`segno`), the secret shown once; who has it on, names only |
| `GET /api/me/password/rules` | the domain's password rules in words, read from `samba-tool domain passwordsettings show` (12 characters, never expires, no lockout) |
| `GET /api/calendar?year&month` · `GET /api/calendar/subscribe` · `POST /api/calendar` · `PUT /api/calendar/{id}` · `DELETE /api/calendar/{id}` (admin) · `GET /api/public/calendar.ics` and `GET /calendar.ics` (no login) | the church calendar (`calendar.py`): the services generated from `[church]`, events in `/var/lib/arise/calendar.json`, an ICS feed with the services as RRULE every Mac and phone subscribes to |
| `GET /api/weather` | Pineville from Open-Meteo (`weather.py`), °F, today and five days, cached 30 min; `{ok:false, why}` when offline |
| `GET /api/help?q=` · `GET /api/help/{name}` | the docs (`help.py`): README and `docs/*.md` rendered server-side with raw HTML escaped; members get `PORTAL-GUIDE` only |
| `GET /api/about/whatsnew` | the top section of CHANGELOG.md, ten lines at most |
| `GET /api/files/info` · `GET /api/files/recent` · `GET /api/files/zip` · `GET`/`PUT /api/files/text` · `POST /api/files/text/preview` · `GET /api/files/all?folder=` (admin) | Finder (`finder.py`): Get Info (size, owner, dates, the SMB path, the share's valid users), Recents (7 days, cached 60 s), Compress (a zip to 2 GB), the text editor (text types to 1 MB, Markdown preview), the Everyone views |
| `GET /api/files/trash` · `POST /api/files/trash` · `POST /api/files/trash/restore` · `POST /api/files/trash/empty` (admin) | the Trash: `<root>/.Trash/<user>/<timestamp>-<name>` with a manifest; Put Back; Empty with the share's name; Samba's `recycle` module lands the Macs' deletes in the same place; `arise-trash.timer` sweeps after 30 days |
| `GET /api/files/versions` · `POST /api/files/versions/restore` | Previous Versions from restic (`backups.versions_of`, `restore_version`): restored beside the original as `name (restored YYYY-MM-DD)`; members for their own roots |
| `POST /api/files/upload/start` · `PUT /api/files/upload/chunk?token&offset` · `GET /api/files/upload/status` · `POST /api/files/upload/finish` | resumable uploads to 10 GB; stale parts dropped by the trash sweep after 3 days |
| `GET /api/updates` · `POST /api/updates/refresh` · `POST /api/updates/check-apps` · `POST /api/updates/queue` · `POST /api/updates/apply` | Software Update (`updates.py`): apt split security/other, app image updates, reboot-required, ariseOS's own version; the queue in `/var/lib/arise/updates-queue.json`; apply = `arisectl update apply` (snapshot first, refused during a service) |
| `GET /api/activity` · `POST /api/activity/kill` {pid} | Activity Monitor (`activity.py`): processes and container stats, cached 3 s; kill refuses PID 1, samba, arise-web, dockerd, containerd, sshd |
| `GET /api/automations` · `POST /api/automations/{timer}/{pause,resume}` | every `arise-*` timer with next run, last result, enabled (`automations.py`) |
| `GET /api/storage` · `POST /api/storage/scan` | the disk by mount, share and app, the biggest files, the unchanged-in-a-year list (`storage.py`; the scan runs in a thread) |
| `GET /api/monitor` · `POST /api/monitor/power` {on} | the closet panel's hours and Screen Sharing (`monitor.py`) |
| `GET /api/apps/catalog` · `GET /api/apps/theme/{name}` · `GET /api/apps/open/{trilium,immich}` (members in Staff/Media) · `POST /api/apps/{name}/autostart` | the Store: the catalogue, what of the house look an app takes, the Notes and Photos windows, autostart per app |
| `GET /api/logs/sources` · `GET /api/logs/file/{name}` | the grouped unit list and the files under `/var/log/arise` |
| `GET /api/security` · `GET /api/security/scan` · `POST /api/security/scan/run` · `POST /api/security/scan/restore` {name} · `GET /api/security/snapshots` (admin) | the Security app (`security.py`): the rows, the ClamAV scan and quarantine, the Timeshift snapshots |
| `GET /api/public/ca.crt` and `GET /ca.crt` (no login) | Caddy's root certificate as PEM, or 404 with a plain message when Caddy is not there |

## The dashboard (web/)

Laid out like a desktop, the way HomeDock does it: a **menu bar** across the
top (the flame, the open app's name, live CPU/RAM pills, the clock, the
signed-in admin), a wallpaper in the church's ink and red, **windows** that
open, move, resize, minimise and stack, a floating **dock** along the bottom
with one icon per app and a dot under the ones that are open, and a
**launchpad** grid for the rest. On a phone every window is full-screen and
the dock becomes a bottom bar.

The apps, by folio:
**01 Finder · 02 Overview · 03 Directory · 04 Backups · 05 Automator · 06 Sermons · 07 Bible · 08 Store · 09 Remote · 10 Campuses · 11 Terminal · 12 Synology · 13 Services · 14 Logs · 15 System Settings · 16 Network · 17 Assistants · 18 Sunday · 19 Mail · 20 Calendar · 21 Calculator · 22 Clock · 23 Help · 24 Activity Monitor · 25 Automations · 26 Storage · 27 Software Update · 28 Notes · 29 Photos · 30 Monitor · 31 Security**, and About from the flame menu. docs/DASHBOARD.md has the table.

Design tokens (from the Wix site, do not drift):

```css
--red:#D6222D; --redL:#DB3F48; --redD:#780C12;
--ink:#0A0A0C; --scrim:#060608; --panel:#111115; --panel2:#16161B; --line:rgba(255,255,255,.12);
--paper:#FFFFFF; --bone:#F4F2F0; --muted:#6A6A6E; --text:rgba(255,255,255,.86);
--ok:#3DBE7A; --warn:#E0A32E; --bad:#D6222D;
font-family: 'Oswald' (body, weights 300–600) · 'Anton' (headings, uppercase, letter-spacing .02em)
```

Shapes: square corners everywhere (the site has no border-radius), 1px
`--line` rules, 3px red top borders on raised panels, the "mark" (two red
dashes before a kicker), the skewed red strip for badges, uppercase 12px
letter-spaced buttons. Dark chrome (ink) like the site's header and footer;
content panels on `--panel`. Reduced-motion honoured. Works at 360px wide.

## The CLI (`arisectl`)

Mirrors Monolith's verbs, stdlib only, talks to the API on localhost (or
reads files directly when the API is down):

```
arisectl info                     # version, profile, realm, uptime, health
arisectl service list|status|start|stop|restart <unit>
arisectl user list|add|remove|passwd|enable|disable <name>
arisectl group list|add|addmember <group> <user>
arisectl share list|add <name> <path>|remove <name>
arisectl backup status|run [job]|list|snapshots|restore <snapshot> <target>
arisectl automator status|preview|run|report|holds|worklist
arisectl app list|templates|deploy <template> --name <n>|start|stop|logs <n>
arisectl nas status|mount|unmount
arisectl mirror run               # refresh the GitHub mirror
arisectl remote status|add-peer <name>   # VPN, SSH, Guacamole state; a new WireGuard device
arisectl sites                    # Pineville · Alexandria · the Hub, with probe replies
arisectl notify test|send         # the morning report to the webhook
arisectl update [check|refresh|queue|apply|apt|self]   # Software Update; apply = snapshot first, never during a service
arisectl admin set-password       # writes the bcrypt hash into arise.toml
arisectl doctor                   # checks everything and prints what to fix
arisectl trash | app catalog|install-all|autostart|theme|idle-sweep | automations | storage | monitor
arisectl security | twofa | rescue | encrypt | snapshot | scan | reinstall     # docs/CLI.md
```

## Rules carried over from the rest of the Arise work

- Never silent: every scheduled run writes a report or a history row, success or failure.
- Deleting is Bradly's click. No API route deletes a user's home or a backup snapshot without `confirm: "<name>"` in the body, and the UI asks twice; since v0.8 deleting a user and the power menu also ask the person's password again (`require_recent_auth`, five minutes). A delete in Finder is a move to the share's Trash.
- Secrets never go in git. `token.json`, `client_secret.json`, restic password, DSM credentials: `.gitignore` covers them and the installer prints where to put them.
- Chapter and quota rules of the automator are the automator's; this server only runs it and shows its output.
