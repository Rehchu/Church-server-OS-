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
| Hostname | `arise-server` |
| AD realm / NetBIOS | `AD.ARISECENLA.CHURCH` / `ARISE` |
| Install root (code) | `/opt/arise` |
| Config | `/etc/arise/arise.toml`, `/etc/arise/backups.yaml` |
| Secrets | `/etc/arise/secrets/` (restic password, DSM credentials), mode 0600 |
| State | `/var/lib/arise/` (`state.json`, `backup-history.json`, metrics ring) |
| Data root | `/srv/arise/` — `homes/`, `shares/`, `automator/`, `apps/`, `backups/` |
| Automator checkout | `/srv/arise/automator/ARISE_YouTube_Updater` (clone of `Rehchu/arise-youtube-automation`) |
| Synology mount | `/mnt/synology` (SMB or NFS), subfolders `arise-backups/`, `homes/` |
| Timers | `arise-automator.timer` 02:05 America/Chicago · `arise-backup.timer` 03:00 · `arise-mirror.timer` 04:00 · `arise-notify.timer` 07:00 |
| VPN | Tailscale (100.64.0.0/10) or WireGuard `wg0` on UDP 51820, tunnel `10.47.0.0/24` |
| Remote desktop | Guacamole, port 8084 (`remote.ad.arisecenla.church` behind Caddy) |
| HTTPS | Caddy, `tls internal`, `config/caddy/Caddyfile` |
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
docs/                    ARCHITECTURE (this), DIRECTORY, MAC-MIGRATION, SYNOLOGY,
                         BACKUPS, AUTOMATOR, HARDWARE, DASHBOARD, CLI, REMOTE-ACCESS, MULTI-SITE
site/                    the landing page (static, Arise design)
server/arise_server/     FastAPI backend — the JSON API and static host
web/                     the dashboard SPA (vanilla JS, Arise design)
cli/arisectl             the CLI (Python, stdlib only)
installer/               install.sh (Ubuntu; --with-tailscale --with-wireguard --with-caddy), install.ps1 (Windows), autoinstall.yaml
config/                  arise.toml.example, backups.yaml.example, systemd units, smb.conf.template, caddy/Caddyfile
templates/<app>/         compose.yaml + template.yaml per app
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
session_hours = 12

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
| `GET /api/search?q=` | Spotlight: file names on both roots (a bounded `os.walk` index, cached 120 s), users and computers from the directory |
| `GET /api/system/updates` · `POST /api/system/update` · `POST /api/system/apt-upgrade` | apt and Arise Server updates |
| `POST /api/system/power` `{action: reboot|poweroff, confirm}` | the closet has no power button you can reach |
| `POST /api/notify/test` | sends a test line to the webhook |
| `WS /api/terminal` | a pty on the box for the Terminal app (root on the Linux install) |

## The dashboard (web/)

Laid out like a desktop, the way HomeDock does it: a **menu bar** across the
top (the flame, the open app's name, live CPU/RAM pills, the clock, the
signed-in admin), a wallpaper in the church's ink and red, **windows** that
open, move, resize, minimise and stack, a floating **dock** along the bottom
with one icon per app and a dot under the ones that are open, and a
**launchpad** grid for the rest. On a phone every window is full-screen and
the dock becomes a bottom bar.

The apps, in dock order:
**Overview · Directory · Files · Backups · Automator · Sermons · Bible · Apps · Remote · Campuses · Terminal · NAS · Services · Logs · Settings**.

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
arisectl update                   # git pull + pip + restart arise-web
arisectl admin set-password       # writes the bcrypt hash into arise.toml
arisectl doctor                   # checks everything and prints what to fix
```

## Rules carried over from the rest of the Arise work

- Never silent: every scheduled run writes a report or a history row, success or failure.
- Deleting is Bradly's click. No API route deletes a user's home or a backup snapshot without `confirm: "<name>"` in the body, and the UI asks twice.
- Secrets never go in git. `token.json`, `client_secret.json`, restic password, DSM credentials: `.gitignore` covers them and the installer prints where to put them.
- Chapter and quota rules of the automator are the automator's; this server only runs it and shows its output.
