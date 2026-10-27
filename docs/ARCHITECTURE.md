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
| Timers | `arise-automator.timer` 02:05 America/Chicago · `arise-backup.timer` 03:00 · `arise-mirror.timer` 04:00 |
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
                         BACKUPS, AUTOMATOR, HARDWARE, DASHBOARD, CLI
site/                    the landing page (static, Arise design)
server/arise_server/     FastAPI backend — the JSON API and static host
web/                     the dashboard SPA (vanilla JS, Arise design)
cli/arisectl             the CLI (Python, stdlib only)
installer/               install.sh (Ubuntu), install.ps1 (Windows), autoinstall.yaml
config/                  arise.toml.example, backups.yaml.example, systemd units, smb.conf.template
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

## The dashboard (web/)

Sections, in the sidebar, in this order:
**Overview · Directory · Files · Backups · Automator · Apps · NAS · Services · Logs · Settings**.

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
arisectl admin set-password       # writes the bcrypt hash into arise.toml
arisectl doctor                   # checks everything and prints what to fix
```

## Rules carried over from the rest of the Arise work

- Never silent: every scheduled run writes a report or a history row, success or failure.
- Deleting is Bradly's click. No API route deletes a user's home or a backup snapshot without `confirm: "<name>"` in the body, and the UI asks twice.
- Secrets never go in git. `token.json`, `client_secret.json`, restic password, DSM credentials: `.gitignore` covers them and the installer prints where to put them.
- Chapter and quota rules of the automator are the automator's; this server only runs it and shows its output.
