# The FOSS stack: what fits this box, what does not, and why

Bradly brought a list of thirty open-source server packages. This is the
honest sort: which already exist here under another name, which are worth
adding (and are now one-click templates), which wait, and which would fight
the design or the hardware. Every memory figure is a typical idle number
from the projects' own docs or common experience, labelled as an estimate;
the Dell's real RAM (question 1, Sunday) decides how many run at once.

## The shape of the machine

One OptiPlex, Ubuntu Server, no desktop environment. The core that is
always on, with typical idle memory (estimates):

| Core | What | Memory |
|---|---|---|
| Samba AD DC | the directory, DNS, Kerberos, the shares | 200 to 400 MB |
| arise-web | the dashboard and the desktop on the monitor | 100 MB |
| cage + Epiphany | the kiosk browser | 300 to 500 MB |
| Docker | the engine, idle | 100 MB |
| restic, the automator | nightly, then gone | 0 idle, up to 1 GB while running |

About 1 to 1.5 GB before any app. On an 8 GB box that leaves room for five
or six light apps; on 16 GB, most of the "add" column below at once. The
rule: every app is one folder under `templates/`, one `docker compose`
stack, data under `/srv/arise/apps/<name>` (backed up nightly by the `apps`
job), reached on the LAN and over Tailscale only, never from the internet.
Nothing is installed "because it was on a list"; each one answers a
question somebody at the church actually asks.

## The thirty, sorted

### Already here under another name (do not add a second one)

| On the list | What this box already has | Why not both |
|---|---|---|
| Samba | the heart of the server: AD DC, DNS, every share | it is this |
| WireGuard | `install.sh --with-wireguard` or the `wg-easy` template; Tailscale is the chosen path | one VPN, not two on the same port |
| Nginx Proxy Manager | Caddy (`--with-caddy`) with its own CA and a one-file config | same job; Caddy needs no database and no clicking |
| ShellInABox | the Terminal app (xterm.js over a websocket), Tailscale SSH, and Cockpit's terminal | three doors already |
| Webmin | the dashboard for the church things, Cockpit for the Linux things | Webmin is a very large surface for a box that needs a small one |
| Patchman | System Settings → Updates (packages, security count, Arise itself) | Patchman is for a fleet; this is one box |
| Portainer | the Apps app for daily work | kept as an optional template for the hard days, below |
| OpenLP headless | Proclaim runs the slides, on the media Mac | nothing to serve |
| Nextcloud | the member portal: sign in from anywhere, own files, shares, upload, download, share links; Syncthing for folders that must mirror | for files, the portal and SMB already do it; Nextcloud is a template below for the calendar and documents side |

### Installed and running after `install.sh` (the church set)

`netdata`, `uptime-kuma`, `netalertx`, `portainer`, `bookstack`,
`jellyfin`, `syncthing`, `vaultwarden`, `guacamole`, `owncast`, `icecast`,
plus Cockpit and Tailscale (apt). Passwords are generated at deploy and
kept in `/etc/arise/secrets/apps/`. About 2.5 GB of memory for the set
(an estimate), 4 GB with the core: fits 8 GB with room, and the table in
INSTALL.md § What is running lists every address and first login.

### Worth adding, and now templates (`arisectl app deploy <name>`)

| Template | The question it answers | Memory (estimate) | Note |
|---|---|---|---|
| `netdata` | "what exactly is the box doing right now" | 150 to 300 MB | local only, no cloud account |
| `jellyfin` | "can I watch the Sunday recording on my TV" | 300 MB idle, a core per transcode | reads the `recordings` share read-only; hardware transcoding if the Dell has Intel graphics |
| `bookstack` | "where is the Sunday runbook written down" | 300 to 400 MB | the church handbook; start with this repo's docs |
| `churchcrm` | "who is in which group, who was here Sunday" | 300 MB | only if nothing is paid for already; giving stays off the box (answer 40) |
| `portainer` | "the Apps page is not enough today" | under 100 MB | root in all but name; LAN and VPN only |
| **Cockpit** (`install.sh --with-cockpit`) | "the dashboard is what broke; get me in" | 50 MB, apt not Docker | disks, services, logs, a terminal, updates, on :9090, the box's own logins |
| **FFmpeg** (apt) | the automator's thumbnails and the podcast audio | 0 idle | now in the package list |
| `frigate`, `netalertx` | cameras and "who is on my network" | see templates/README.md | added earlier for the switch question |

### Also templates now, off until somebody wants them (Bradly: "use what you can")

Carrying a template costs nothing; deploying one costs the memory in the
table. Deploy the day the question is asked, not before.

| Template | The question it answers | Memory (estimate) | Note |
|---|---|---|---|
| `owncast` | "we want our own live page" or "YouTube is down, where do we stream" | 200 MB | a second StreamYard/OBS output; shares 1935 with nginx-rtmp, so one or the other |
| `nginx-rtmp` | "OBS should push once and the server sends it everywhere" | 50 MB | only for an OBS setup; StreamYard already fans out |
| `icecast` | "the nursery / translation / hearing-assist audio on phones" | 50 MB | one laptop sends, phones listen in a browser |
| `mattermost` | "leadership wants its own chat" | 500 MB to 1 GB | the one app to think twice about on 8 GB |
| `synapse` | the same question, encrypted, with the Element apps | 400 MB+ | Mattermost or this, never both |
| `kimai` | "timesheets for the hourly staff" | under 200 MB | SQLite, one container |
| `trilium` | "a study notebook that is not Apple Notes" | 150 MB | one notebook per deployment; deploy twice for two people |
| `nextcloud` | "a shared calendar, documents in the browser, phone photo upload" | 1 GB | the shares are mounted into it, not copied; its LDAP app ties it to the domain; needs 16 GB to sit beside the rest |
| `moodle` | "a new-members course with a quiz" | 1 GB+ | heavy; deploy when someone will build the course |
| `phplist` | "the weekly email to the families" | 250 MB | only through an SMTP relay; Mailchimp's free tier is simpler until the list is big |
| Ansible | not a service: a tool for the day there is a second server or a dozen Macs to push one change to | 0 | today `install.sh` and `enroll-mac.sh` are the automation; an Ansible playbook would wrap them, not replace them |
| CiviCRM | ChurchCRM outgrown | 500 MB+ | not a template; it wants a CMS underneath (Drupal, WordPress) and a real sysadmin |

### Not on this box

| On the list | Why |
|---|---|
| Pi-hole | it wants port 53, which is the domain controller's. Bradly's rule is no router changes, so only domain Macs would use it anyway. The DC already forwards to 1.1.1.1; a filtering upstream (Cloudflare 1.1.1.2 or Quad9) gives most of the benefit with one line in `arise.toml` and no new daemon |
| Discourse | needs its own Docker host by the project's own rules, 2 GB+, and a public address, which this box does not have |
| MediaGoblin | unmaintained for years; Jellyfin (a photo library works too) or the website's own media page covers photos |
| ChurchInfo | ChurchCRM is its descendant |
| Webmin, Patchman, ShellInABox, Nginx Proxy Manager, OpenLP | see the first table |

## How it is all wired

```
 internet ── Tailscale (every laptop, Alexandria's Mac, the Hub) ──┐
                                                                   │
 Netgear A's wire ── the server ── Caddy :443 (optional) ──┬── dashboard :4147  (the desktop, the portal)
                                                           ├── apps       :8081..  (one compose each, /srv/arise/apps/<name>)
                                                           ├── cockpit    :9090
                                                           └── the DC     53/88/389/445  (LAN + VPN only)
```

- **One way in:** the LAN or Tailscale. ufw denies the rest. No app is ever
  reachable from the open internet (answer 36).
- **One place for data:** `/srv/arise/apps/<name>/`, snapshotted nightly by
  the `apps` restic job. Big media (recordings, Jellyfin's library) lives on
  the Synology and stays out of restic.
- **One way to run a thing:** `templates/<name>/compose.yaml` plus a
  `template.yaml` manifest, deployed by `arisectl app deploy` or the Apps
  page, which also stops, restarts, updates, shows logs and removes (data
  kept). No app is installed with apt except Cockpit and the tools
  (arp-scan, nmap, ffmpeg), because apt packages cannot be removed as
  cleanly or pinned as exactly.
- **One set of logins where the app allows it:** Cockpit uses the box's
  accounts; Jellyfin and BookStack have their own users (BookStack can do
  LDAP against the DC later; it is one config block, documented in its
  template when someone asks).

## Scripting it

There is no second installer. `install.sh` already does the box (one flag
per optional piece: `--with-tailscale`, `--with-caddy`, `--with-cockpit`,
`--kiosk`), and every service is a compose stack deployed by `arisectl app
deploy <template>`. A whole environment is therefore one line per app:

```bash
sudo bash /opt/arise/installer/install.sh --kiosk --with-tailscale --with-cockpit
for a in netdata bookstack jellyfin; do sudo arisectl app deploy $a; done
```

Add `portainer`, `churchcrm`, `frigate`, `netalertx`, `uptime-kuma`,
`syncthing`, `vaultwarden`, `guacamole`, `owncast`, `nginx-rtmp`, `icecast`,
`mattermost`, `synapse`, `kimai`, `trilium`, `nextcloud`, `moodle`,
`phplist` the same way, when and if each one is wanted. Twenty-two
templates; the box runs the ones somebody asked for. Remove one with `arisectl app remove <name>`; its folder stays
until a person deletes it.
