# Arise Server

**The church server for Arise Church, Pineville LA. One box. One login. Nothing silent.** The OS it becomes is called **ariseOS**; Arise Server is the service inside it (docs/ROADMAP.md).

Arise Server turns an old PC into the church's own server:

- a real **Active Directory** (Samba AD DC) that the Macs, the Windows PC and the Synology sign in to
- **home folders and shares** on the server, Mac-friendly, with a script that moves an old Mac's data in
- the **nightly YouTube automator** (`arise_daily.py`) on a systemd timer at 02:05 Central, its reports on the dashboard
- **backups** with restic to the Synology at 03:00, every run recorded, failures in red, plus a mirror of every GitHub repo
- a **Store** of Docker Compose apps: 26 templates preinstalled within the box's memory, a catalogue of 35 more free ones, each capped and wearing the house look where it allows
- the **church Macs** run by the server, the church's own Active Directory with no Microsoft licence: a small helper on each church Mac (never a personal one) adds and removes accounts, waits for an admin's choice on local accounts (Convert, Link or Leave alone), keeps FileVault's key and a hidden admin's password on the server, and adds printers, bookmarks and security updates (docs/MACS.md)
- **Desktop and Documents synced** from every Mac and phone to the server through Nextcloud, newest wins with the older copy in the Trash (docs/SYNC.md). Staff and volunteers just use their Macs; the four admins use the OS at the closet monitor
- the **Synology** joined to the domain, mounted, and watched
- **remote access for a server in a locked closet**: key-only SSH, a VPN (Tailscale recommended, native WireGuard or wg-easy as the self-hosted option), Guacamole remote desktop to any church computer from a browser tab, HTTPS with the server's own CA, a Terminal app in the dashboard
- **three sites on one server**: Pineville (main), Arise Church Alexandria and the Apostolic Hub reach it over the VPN; a Campuses app watches each one
- **the safety basics**: optional two-step sign-in, a break-glass admin, the disk unlocked by the TPM, a snapshot before every update, a weekly virus scan, the church certificate on every Mac, reinstall from the Synology
- **Discord** as Bradly's monitoring room: four channels for alerts, Sunday, the weekly and the daily (docs/DISCORD.md)
- **one dashboard** on port 4147, laid out like a desktop (menu bar, windows, a dock, a launchpad), **one CLI**, `arisectl`, and **a console dashboard**, `arisetui`, for the monitor in the closet, all in the look of arisecenla.church

Three things shaped it: [Monolith OS](https://github.com/shirou-eh/Monolith) (one CLI, one config, a web dashboard, an installer, profiles, restic backups, a landing page), [HomeDock OS](https://github.com/BansheeTech/HomeDockOS) (a Python backend, a browser desktop that streams live stats, apps as Docker Compose stacks), and the [Arise Church website](https://arisecenla.church) (Anton + Oswald, ink `#0A0A0C`, Arise red `#D6222D`, square corners, the two red dashes).

Plain Python 3.11+ and plain HTML/CSS/JS. No Node build step. The whole thing runs in sample mode on any laptop with `python -m arise_server --demo`.

---

## Status

**v0.8.0 "Exodus" — built, not yet installed on the church PC.** One run of the installer brings up the OS desktop, the domain, every app template deployed with the light ones running (INSTALL.md § What is running), and the safety basics (docs/SECURITY.md). Thirty-three numbered apps in the dashboard (docs/DASHBOARD.md), a catalogue of 35 more free apps in the Store (docs/STORE.md), and the full map against Windows 11 and macOS in docs/PARITY.md. The next block is the two nodes, Arise-Pineville and Arise-Home (docs/NODES.md), once Friday's specs say which PC is which. Start with [docs/SETUP-GUIDE.md](docs/SETUP-GUIDE.md); the open questions are in [docs/QUESTIONS.md](docs/QUESTIONS.md). The PC's specs and the Synology model are still to come; `docs/HARDWARE.md` is the checklist. Until then: the unit tests pass, the dashboard and CLI run end to end in sample mode, the Ubuntu installer passes `bash -n` and a full `--dry-run` (with every remote-access flag), and the PowerShell installer has been checked statically only (no Windows here).

What has **not** been run against a real Samba domain, a real Synology, a real restic repository, a real Tailscale or WireGuard tunnel or a real Guacamole: every call is written against the tools' documented interfaces, and `arisectl doctor` is there to find the first thing that disagrees.

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
sudo bash installer/install.sh --admin-pass 'YourDomainAdminPassword' --with-tailscale --with-caddy
```

Then, in order: `sudo arisectl admin set-password`; copy `token.json` and `client_secret.json` into `/srv/arise/automator/ARISE_YouTube_Updater/`; write the restic password to `/etc/arise/secrets/restic-password` (and on paper); `sudo arisectl nas mount`; `ssh-copy-id bradly@arise-server` from your Mac and re-run the installer so password login goes off; `sudo tailscale up --ssh --advertise-routes=192.168.1.0/24`; `sudo arisectl doctor`. Dashboard: `http://arise-server:4147`.

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
| "Like Active Directory" | A Samba AD domain controller, realm `AD.ARISECENLA.COM`, NetBIOS `ARISE`. Kerberos, LDAP, DNS. Macs bind with Directory Utility; Windows joins the domain; the Synology joins too. [docs/DIRECTORY.md](docs/DIRECTORY.md) |
| Macs with profiles and files on the server | Mobile accounts (cached local home, works offline) plus the user's server home share mounted at login, Desktop and Documents kept there. `mac/migrate-mac-user.sh` moves an existing local account's data over with a manifest and never deletes. [docs/MAC-MIGRATION.md](docs/MAC-MIGRATION.md) |
| The Synology | Joins the domain; holds the bulk files (`media`, optionally `homes`) on four drives; is the restic target; ships the off-site copy with Hyper Backup. [docs/SYNOLOGY.md](docs/SYNOLOGY.md) |
| Run the automator | `arise-automator.timer` at 02:05 America/Chicago runs `automator/arise_daily.py` from the cloned `arise-youtube-automation` repo. Reports, worklist, holds and quota on the dashboard; preview (dry run) and run from there or `arisectl`. [docs/AUTOMATOR.md](docs/AUTOMATOR.md) |
| Back up everything Arise | restic jobs: automator, homes, shares, app data, media, GitHub mirror, server config. Keep 30 daily, 12 weekly, 24 monthly. History in the dashboard, restores by `arisectl backup restore`. [docs/BACKUPS.md](docs/BACKUPS.md) |
| Run great, feel great | A dashboard laid out like a desktop (menu bar, windows, dock, launchpad) that streams live stats over SSE; square, ink-and-red, Anton and Oswald; works on a phone. [docs/DASHBOARD.md](docs/DASHBOARD.md) |
| Reach it from anywhere | Key-only SSH, Tailscale or WireGuard, Guacamole remote desktop, HTTPS via Caddy, a Terminal app. Nothing forwarded on the router (Tailscale only). [docs/REMOTE-ACCESS.md](docs/REMOTE-ACCESS.md) |
| Three sites | Pineville, Alexandria and the Apostolic Hub on one server over the VPN; Macs in Alexandria stay domain-joined. [docs/MULTI-SITE.md](docs/MULTI-SITE.md) |

---

## Profiles

| Profile | Where | What runs | Needs |
|---|---|---|---|
| `server` (recommended) | Ubuntu Server 24.04 LTS on the old PC | everything above | 2 cores, 4 GB RAM (8 GB with apps), 64 GB+ SSD, **wired Ethernet**, on 24/7 |
| `windows` | Windows 10/11 stays | dashboard, `arisectl`, automator at 02:05, backups at 03:00, mirror at 04:00, Windows file sharing | the same PC. **A Windows 10/11 PC cannot be a domain controller.** |

`docs/HARDWARE.md` maps "what you have" to "what to expect".

---

## The three surfaces

**The dashboard** — `arise-web.service`, port 4147. A macOS-style desktop themed for Arise: a Finder, a menu bar with real menus, windows, a floating dock, Spotlight, Mission Control, ⌘Tab, a widgets panel, Control Center, a lock screen. With `install.sh --kiosk` it is also what the closet monitor shows. **Everyone in the directory signs in** with their domain password: members get their own files, the shares their groups allow, upload/download, share links, Sermons, Bible and Change Password from anywhere; the administrator gets everything. Apps: 01 Finder · 02 Overview · 03 Directory · 04 Backups · 05 Automator · 06 Sermons · 07 Bible · 08 Store · 09 Remote · 10 Campuses · 11 Terminal · 12 Synology · 13 Services · 14 Logs · 15 System Settings · 16 Network · 17 Assistants · 18 Sunday · 19 Mail · 20 Calendar · 21 Calculator · 22 Clock · 23 Help · 24 Activity Monitor · 25 Automations · 26 Storage · 27 Software Update · 28 Notes · 29 Photos · 30 Monitor · 31 Security. Every destructive action asks for the name typed, and the worst ones ask your password again. Secrets never reach the browser.

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
arisectl remote status|add-peer <name>
arisectl sites
arisectl notify test|send
arisectl update [check|refresh|queue|apply|apt|self]
arisectl trash | automations | storage | monitor | security | twofa | rescue | encrypt | snapshot | scan | reinstall
```

**The installer** — `installer/install.sh`: loud, idempotent steps, `--dry-run` to read them first; `--with-tailscale`, `--with-wireguard`, `--with-caddy` for the remote pieces; `--kiosk` to put the desktop on the closet monitor, `--console` for the text dashboard instead.

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

# Remote access (the server is in a locked closet)
ssh-copy-id bradly@arise-server                 # from your Mac, before the door closes
sudo bash installer/install.sh --with-tailscale --with-caddy
sudo tailscale up --ssh --advertise-routes=192.168.1.0/24
sudo arisectl remote add-peer alexandria-imac   # WireGuard: prints the config for the device
sudo arisectl app deploy guacamole              # remote desktop in a browser tab
arisectl sites                                  # Pineville · Alexandria · the Hub
arisectl notify test                            # the morning report, to the webhook
```

---

## The nightly timetable

| America/Chicago | What |
|---|---|
| 02:00 | YouTube quota resets (midnight Pacific) |
| 02:05 | `arise-automator.timer` → `scripts/arise-nightly.sh` → `arise_daily.py`, as Bradly's own account, only when `runner.json` names this box (worklist, holds, quota ledger, report) |
| 03:00 | `arise-backup.timer` → `arisectl backup run` (every job, then forget/prune) |
| 04:00 | `arise-mirror.timer` → `arisectl mirror run` (bare mirrors of the GitHub repos) |
| 04:15 | `arise-archive.timer` → the archive index, new files only (Wednesdays `arise-archive-rebuild.timer` rebuilds it in full) |
| 04:30 | `arise-trash.timer` → `arisectl trash sweep` (what sat 30 days in a Trash goes) |
| 05:15 | `arise-offboard.timer` → `arisectl offboard sweep` (leavers marked 30 days ago: files moved to whoever takes them) |
| 07:00 | `arise-notify.timer` → `arisectl notify send` (off: no daily note; Discord's #daily is the morning report's place, docs/DISCORD.md) |
| Sat 03:30 | `arise-update.timer` → `arisectl update apply` (only what was queued; a snapshot first) |
| Sun 23:30 | `arise-clamscan.timer` → `arisectl scan run` (the shares, video skipped) |

Through the day: `arise-repos.timer` every 15 minutes (`arisectl repos sync`), `arise-cloud-conflicts.timer` and `arise-devices.timer` hourly, `arise-idle-apps.timer` every 15 minutes.

Most timers are `Persistent=true`: if the PC was off, they run at next boot. The automator is not, on purpose: a night missed to a power cut must not fire at 10 AM on a Sunday and spend the quota that day's service needs. A missed night is skipped; the worklist carries on the next.

---

## Repository layout

```
README.md  INSTALL.md
docs/            ARCHITECTURE (the contract) · DIRECTORY · MACS · SYNC · STAFF-FILES · BROWSER · REPOS · ARCHIVE · MAC-MIGRATION · SYNOLOGY · BACKUPS · AUTOMATOR · HARDWARE · DASHBOARD · CLI · REMOTE-ACCESS · MULTI-SITE · EVERYDAY · FINDER · SYSTEM-APPS · STORE · SECURITY · REINSTALL · NODES · PARITY · ROADMAP · ANSWERS
catalog/         catalog.yaml, the Store's catalogue of further free apps
CHANGELOG.md     What's New
site/            the landing page (static)
server/          FastAPI backend: arise_server/{main,config,auth,metrics,services,directory,shares,backups,automator,apps,nas,remote,sites,bible,sermons,files,system,demo}.py
web/             the dashboard: index.html, styles.css, app.js, demo-data.js (generated)
cli/arisectl     the CLI
installer/       install.sh (Ubuntu; --with-tailscale --with-wireguard --with-caddy) · install.ps1 (Windows) · autoinstall.yaml · MAKE-USB.md
config/          arise.toml.example · backups.yaml.example · systemd/ · samba/smb.conf.template · caddy/Caddyfile
templates/       26 apps, each compose.yaml + template.yaml (autostart, ram_mb, limits, theme)
mac/             bind-mac.sh · migrate-mac-user.sh · mount-home.sh · LaunchAgent plist · CHECKLIST.md
scripts/         gen-demo-data.py
tests/           python3 -m unittest discover tests
```

---

## Configuration

One file, `/etc/arise/arise.toml` (`C:\Arise\config\arise.toml` on Windows), read with `tomllib`. The dashboard never writes it; the installer and `arisectl` do. Backup jobs live in `/etc/arise/backups.yaml`. The `[remote]`, `[notify]` and `[[sites]]` blocks hold the VPN, the morning-report webhook and the three campuses. Secrets live in `/etc/arise/secrets/` and are gitignored by name: `token.json`, `client_secret.json`, `restic-password`, `github-token`, `dsm.json`, `synology.cred`.

Fixed names, from [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): hostname `arise-server` (the nodes become `arise-pineville`, `arise-home`, `arise-alexandria` when docs/NODES.md is built), realm `AD.ARISECENLA.COM`, port `4147`, code in `/opt/arise`, data in `/srv/arise`, NAS at `/mnt/synology`, VPN tunnel `10.47.0.0/24` (WireGuard) or the Tailscale range.

---

## Rules it keeps

- **Never silent.** Every timer run writes a report or a history row, success or failure. The Overview's first panel is "Needs you", and the morning report says the same thing to the webhook.
- **Deleting is Bradly's click.** Users, shares and apps need their name typed; home folders, share folders, app data and snapshots are never removed by the dashboard.
- **Secrets never go to GitHub or the browser.**
- **Nothing on the internet.** No router port is forwarded (Tailscale only, docs/ANSWERS.md 36); SSH, the dashboard, the Terminal and the domain controller are reachable over the VPN only.
- **Sample data is labelled.** No config, or a missing tool, means `"demo": true` and an amber badge.
- **The automator's rules are the automator's.** This server runs `arise_daily.py` and shows its output; `holds.json`, the quota ledger and the chapter rules are untouched.

---

## Docs

**Start here:** [SETUP-GUIDE](docs/SETUP-GUIDE.md) · [STACK](docs/STACK.md) · [QUESTIONS](docs/QUESTIONS.md) · [NETWORK](docs/NETWORK.md) · [MOVING-DAY](docs/MOVING-DAY.md) · [IDEAS](docs/IDEAS.md)

[INSTALL.md](INSTALL.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [DIRECTORY](docs/DIRECTORY.md) · [MAC-MIGRATION](docs/MAC-MIGRATION.md) · [SYNOLOGY](docs/SYNOLOGY.md) · [BACKUPS](docs/BACKUPS.md) · [AUTOMATOR](docs/AUTOMATOR.md) · [HARDWARE](docs/HARDWARE.md) · [DASHBOARD](docs/DASHBOARD.md) · [CONSOLE](docs/CONSOLE.md) · [CLI](docs/CLI.md) · [REMOTE-ACCESS](docs/REMOTE-ACCESS.md) · [MULTI-SITE](docs/MULTI-SITE.md) · [templates](templates/README.md) · [mac checklist](mac/CHECKLIST.md)

**v0.8:** [EVERYDAY](docs/EVERYDAY.md) · [FINDER](docs/FINDER.md) · [SYSTEM-APPS](docs/SYSTEM-APPS.md) · [STORE](docs/STORE.md) · [SECURITY](docs/SECURITY.md) · [REINSTALL](docs/REINSTALL.md) · [NODES](docs/NODES.md) · [PARITY](docs/PARITY.md) · [ROADMAP](docs/ROADMAP.md) · [ANSWERS](docs/ANSWERS.md) · [DISCORD](docs/DISCORD.md) · [ASK-THE-AUTOMATOR-CHAT](docs/ASK-THE-AUTOMATOR-CHAT.md) · [PORTAL-GUIDE](docs/PORTAL-GUIDE.md) (what members see in Help) · [CHANGELOG](CHANGELOG.md)

## Licence

MIT, in [LICENSE](LICENSE) (Bradly Dyer, Arise Church; round 3, 37). Fonts: Anton and Oswald (SIL OFL, from Google Fonts).
