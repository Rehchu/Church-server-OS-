# Arise Server

**The church server for Arise Church, Pineville LA. One box. One login. Nothing silent.**

Arise Server turns an old PC into the church's own server:

- a real **Active Directory** (Samba AD DC) that the Macs, the Windows PC and the Synology sign in to
- **home folders and shares** on the server, Mac-friendly, with a script that moves an old Mac's data in
- the **nightly YouTube automator** (`arise_daily.py`) on a systemd timer at 02:05 Central, its reports on the dashboard
- **backups** with restic to the Synology at 03:00, every run recorded, failures in red, plus a mirror of every GitHub repo
- a small **app store** of Docker Compose templates the church actually uses
- the **Synology** joined to the domain, mounted, and watched
- **one dashboard** on port 4147 and **one CLI**, `arisectl`, in the look of arisecenla.church

Three things shaped it: [Monolith OS](https://github.com/shirou-eh/Monolith) (one CLI, one config, a web dashboard, an installer, profiles, restic backups, a landing page), [HomeDock OS](https://github.com/BansheeTech/HomeDockOS) (a Python backend, a browser dashboard that streams live stats, apps as Docker Compose stacks), and the [Arise Church website](https://arisecenla.church) (Anton + Oswald, ink `#0A0A0C`, Arise red `#D6222D`, square corners, the two red dashes).

Plain Python 3.11+ and plain HTML/CSS/JS. No Node build step. The whole thing runs in sample mode on any laptop with `python -m arise_server --demo`.

---

## Status

**v0.1.0 "Pineville" — built, not yet installed on the church PC.** The PC's specs and the Synology model are still to come; `docs/HARDWARE.md` is the checklist. Until then: 21 unit tests pass, the dashboard and CLI run end to end in sample mode, the Ubuntu installer passes `bash -n` and a full `--dry-run`, and the PowerShell installer has been checked statically only (no Windows here).

What has **not** been run against a real Samba domain, a real Synology or a real restic repository: every call is written against the tools' documented interfaces, and `arisectl doctor` is there to find the first thing that disagrees.

---

## Table of contents

1. [Quick start](#quick-start)
2. [What it is for](#what-it-is-for)
3. [Profiles](#profiles)
4. [The three surfaces](#the-three-surfaces)
5. [Cookbook](#cookbook)
6. [The nightly timetable](#the-nightly-timetable)
7. [Repository layout](#repository-layout)
8. [Configuration](#configuration)
9. [Rules it keeps](#rules-it-keeps)
10. [Docs](#docs)
11. [Licence](#licence)

---

## Quick start

**Path A — Ubuntu Server 24.04 LTS on the old PC (recommended; wipes Windows):**

```bash
sudo apt install -y git
git clone https://github.com/Rehchu/Church-server-OS-.git
cd Church-server-OS-
sudo bash installer/install.sh --admin-pass 'YourDomainAdminPassword'
```

Then, in order: `sudo arisectl admin set-password`; copy `token.json` and `client_secret.json` into `/srv/arise/automator/ARISE_YouTube_Updater/`; write the restic password to `/etc/arise/secrets/restic-password` (and on paper); `sudo arisectl nas mount`; `sudo arisectl doctor`. Dashboard: `http://arise-server:4147`.

**Path B — keep Windows (dashboard, automator and backups only; no domain controller):**

```powershell
git clone https://github.com/Rehchu/Church-server-OS-.git C:\Arise\app
Set-ExecutionPolicy -Scope Process Bypass
C:\Arise\app\installer\install.ps1
```

**Path C — hands-off USB:** `installer/autoinstall.yaml` + `installer/MAKE-USB.md`.

**Just to look at it, anywhere:**

```bash
cd server && pip install -r requirements.txt
python -m arise_server --demo          # http://localhost:4147, sample data, no root
```

Full guide: [INSTALL.md](INSTALL.md).

---

## What it is for

| Need | What Arise Server does |
|---|---|
| "Like Active Directory" | A Samba AD domain controller, realm `AD.ARISECENLA.CHURCH`, NetBIOS `ARISE`. Kerberos, LDAP, DNS. Macs bind with Directory Utility; Windows joins the domain; the Synology joins too. [docs/DIRECTORY.md](docs/DIRECTORY.md) |
| Macs with profiles and files on the server | Mobile accounts (cached local home, works offline) plus the user's server home share mounted at login, Desktop and Documents kept there. `mac/migrate-mac-user.sh` moves an existing local account's data over with a manifest and never deletes. [docs/MAC-MIGRATION.md](docs/MAC-MIGRATION.md) |
| The Synology | Joins the domain; holds the bulk files (`media`, optionally `homes`) on four drives; is the restic target; ships the off-site copy with Hyper Backup. [docs/SYNOLOGY.md](docs/SYNOLOGY.md) |
| Run the automator | `arise-automator.timer` at 02:05 America/Chicago runs `automator/arise_daily.py` from the cloned `arise-youtube-automation` repo. Reports, worklist, holds and quota on the dashboard; preview (dry run) and run from there or `arisectl`. [docs/AUTOMATOR.md](docs/AUTOMATOR.md) |
| Back up everything Arise | restic jobs: automator, homes, shares, app data, media, GitHub mirror, server config. Keep 14/8/12. History in the dashboard, restores by `arisectl backup restore`. [docs/BACKUPS.md](docs/BACKUPS.md) |
| Run great, feel great | A dashboard that paints from a 60-sample history on first load and streams live stats over SSE; square, ink-and-red, Anton and Oswald; works on a phone. [docs/DASHBOARD.md](docs/DASHBOARD.md) |

---

## Profiles

| Profile | Where | What runs | Needs |
|---|---|---|---|
| `server` (recommended) | Ubuntu Server 24.04 LTS on the old PC | everything above | 2 cores, 4 GB RAM (8 GB with apps), 64 GB+ SSD, **wired Ethernet**, on 24/7 |
| `windows` | Windows 10/11 stays | dashboard, `arisectl`, automator at 02:05, backups at 03:00, mirror at 04:00, Windows file sharing | the same PC. **A Windows 10/11 PC cannot be a domain controller.** |

`docs/HARDWARE.md` maps "what you have" to "what to expect".

---

## The three surfaces

**The dashboard** — `arise-web.service`, port 4147. Overview · Directory · Files · Backups · Automator · Apps · NAS · Services · Logs · Settings. One admin login (bcrypt hash in `arise.toml`). Every destructive action asks for the name typed. Secrets never reach the browser.

**`arisectl`** — the same Python modules from the terminal:

```
arisectl info | doctor | admin set-password
arisectl service list|status|start|stop|restart <unit>
arisectl user list|add|remove|passwd|enable|disable|homefix <name>
arisectl group list|add|addmember|removemember
arisectl computer list|remove <name>
arisectl share list|add <name> <path>|remove <name>
arisectl backup status|jobs|run [job]|snapshots|restore <id|latest> --target DIR|verify|prune
arisectl automator status|preview|run|report|holds|worklist|schedule HH:MM
arisectl app list|templates|deploy <template>|start|stop|restart|update|remove|logs <name>
arisectl nas status|mount|unmount
arisectl mirror run
```

**The installer** — `installer/install.sh`: seven loud, idempotent steps, `--dry-run` to read them first.

The landing page in `site/` describes all of this in the church's look; it is a static page, open `site/index.html`.

---

## Cookbook

```bash
# People
sudo arisectl user add jsmith --display "J Smith" --groups Staff
sudo arisectl user passwd jsmith
arisectl user list

# A Mac joins (on the Mac)
sudo ./mac/bind-mac.sh --computer-name MEDIA-MAC
sudo ./mac/migrate-mac-user.sh --from oldlocal --to jsmith --dry-run

# Files
sudo arisectl share add graphics /srv/arise/shares/graphics --group Media

# Backups
arisectl backup status
sudo arisectl backup run homes
sudo arisectl backup restore latest --tag homes --path /srv/arise/homes/jsmith/Documents --target /srv/arise/restore

# The automator
arisectl automator status
sudo arisectl automator preview      # dry run, prints tonight's plan

# Apps, the NAS, the box
sudo arisectl app deploy uptime-kuma
arisectl nas status
sudo arisectl doctor
```

---

## The nightly timetable

| America/Chicago | What |
|---|---|
| 02:00 | YouTube quota resets (midnight Pacific) |
| 02:05 | `arise-automator.timer` → `arise_daily.py` (worklist, holds, quota ledger, report) |
| 03:00 | `arise-backup.timer` → `arisectl backup run` (every job, then forget/prune) |
| 04:00 | `arise-mirror.timer` → `arisectl mirror run` (bare mirrors of the GitHub repos) |

Timers are `Persistent=true`: if the PC was off, they run at next boot. A missed night is skipped, not lost.

---

## Repository layout

```
README.md  INSTALL.md
docs/            ARCHITECTURE (the contract) · DIRECTORY · MAC-MIGRATION · SYNOLOGY · BACKUPS · AUTOMATOR · HARDWARE · DASHBOARD · CLI
site/            the landing page (static)
server/          FastAPI backend: arise_server/{main,config,auth,metrics,services,directory,shares,backups,automator,apps,nas,demo}.py
web/             the dashboard: index.html, styles.css, app.js, demo-data.js (generated)
cli/arisectl     the CLI
installer/       install.sh (Ubuntu) · install.ps1 (Windows) · autoinstall.yaml · MAKE-USB.md
config/          arise.toml.example · backups.yaml.example · systemd/ · samba/smb.conf.template
templates/       filebrowser · uptime-kuma · syncthing · vaultwarden
mac/             bind-mac.sh · migrate-mac-user.sh · mount-home.sh · LaunchAgent plist · CHECKLIST.md
scripts/         gen-demo-data.py
tests/           python3 -m unittest discover tests
```

---

## Configuration

One file, `/etc/arise/arise.toml` (`C:\Arise\config\arise.toml` on Windows), read with `tomllib`. The dashboard never writes it; the installer and `arisectl` do. Backup jobs live in `/etc/arise/backups.yaml`. Secrets live in `/etc/arise/secrets/` and are gitignored by name: `token.json`, `client_secret.json`, `restic-password`, `github-token`, `dsm.json`, `synology.cred`.

Fixed names, from [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): hostname `arise-server`, realm `AD.ARISECENLA.CHURCH`, port `4147`, code in `/opt/arise`, data in `/srv/arise`, NAS at `/mnt/synology`.

---

## Rules it keeps

- **Never silent.** Every timer run writes a report or a history row, success or failure. The Overview's first panel is "Needs you".
- **Deleting is Bradly's click.** Users, shares and apps need their name typed; home folders, share folders, app data and snapshots are never removed by the dashboard.
- **Secrets never go to GitHub or the browser.**
- **Sample data is labelled.** No config, or a missing tool, means `"demo": true` and an amber badge.
- **The automator's rules are the automator's.** This server runs `arise_daily.py` and shows its output; `holds.json`, the quota ledger and the chapter rules are untouched.

---

## Docs

[INSTALL.md](INSTALL.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [DIRECTORY](docs/DIRECTORY.md) · [MAC-MIGRATION](docs/MAC-MIGRATION.md) · [SYNOLOGY](docs/SYNOLOGY.md) · [BACKUPS](docs/BACKUPS.md) · [AUTOMATOR](docs/AUTOMATOR.md) · [HARDWARE](docs/HARDWARE.md) · [DASHBOARD](docs/DASHBOARD.md) · [CLI](docs/CLI.md) · [templates](templates/README.md) · [mac checklist](mac/CHECKLIST.md)

## Licence

MIT. Fonts: Anton and Oswald (SIL OFL, from Google Fonts).
