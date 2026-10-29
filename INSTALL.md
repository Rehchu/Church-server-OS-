# Installing Arise Server

Three ways onto the old PC. They all end in the same place: a box on the
church network called `arise-server`, a dashboard at
**http://arise-server:4147**, the nightly automator at 2:05 AM, restic
backups to the Synology at 3:00 AM, and (on Linux) an Active Directory domain
the Macs and the NAS log into.

| Path | What it is | Pick it when |
|---|---|---|
| **A · Ubuntu Server** (recommended) | Wipes Windows off the old PC. Everything works: directory, files, automator, backups, apps. | You want the Macs on server accounts and files on the server. This is the one that does what you asked for. |
| **B · Windows mode** | Keeps Windows 10/11. Dashboard, automator, backups, GitHub mirror. **No directory.** | Something on that PC must stay on Windows, or you want to try the dashboard before committing a machine. |
| **C · Hands-off USB** | Path A, but the installer answers its own questions. | You would rather build the USB once and walk away from the PC. |

The PC's specs decide nothing here except Docker apps (see `docs/HARDWARE.md`).
Send the specs when you have them and the install gets tuned; nothing in
these steps changes.

**One thing before any path:** the old PC must be on **Ethernet**, not Wi‑Fi,
and keeps a **fixed address**: the installer pins the address the router
already gives it on the server itself (`/etc/netplan/60-arise-pinned.yaml`,
§ 5). Nothing on the router changes (docs/ANSWERS.md, 111 and 118). A
domain controller that changes address, or drops off Wi‑Fi at 2 AM, takes
every Mac's login with it.

---

## Path A · Ubuntu Server 24.04 LTS

**This erases the PC.** Anything on it you still want, copy off first.

### 1. Make the USB

Follow `installer/MAKE-USB.md` (Rufus on Windows, `dd` on a Mac). Skip the
`autoinstall.yaml` part; that is Path C.

### 2. Install Ubuntu

Boot the PC from the stick and answer the installer:

| Screen | Answer |
|---|---|
| Language / keyboard | English, US |
| Type of install | **Ubuntu Server** (not minimized) |
| Network | leave DHCP for now; note the address it shows |
| Proxy | blank |
| Mirror | leave it |
| Storage | **Use an entire disk**, tick **Set up this disk as an LVM group** and **Encrypt the LVM group with LUKS** (round 3, 22; the passphrase goes on the safe card, the TPM unlocks it after step 6j). Pick the disk; confirm it wipes it. |
| Profile | Your name: `Bradly Dyer` · server name: **`arise-server`** · username: `bradly` · a password you will remember |
| Ubuntu Pro | Skip |
| SSH | **Install OpenSSH server** — tick it. Then you can do the rest from your own PC. |
| Snaps | none |

Reboot when it says to, pull the stick out.

### 3. Get the code on it

From your own PC (PowerShell or Terminal), or at the server's keyboard:

```bash
ssh bradly@<the address from step 2>
sudo apt-get update && sudo apt-get install -y git
sudo git clone https://github.com/Rehchu/Church-server-OS-.git /opt/arise
```

### 4. Run the installer

```bash
sudo bash /opt/arise/installer/install.sh
```

It asks once for the **domain Administrator password** (8+ characters,
upper, lower, digit; Samba refuses anything weaker). Write it down somewhere
that is not the server. Then it runs about five minutes:

```
==> 1/7  Packages
==> 2/7  Hostname and timezone
==> 3/7  Code to /opt/arise and the Python venv
==> 4/7  Config (/etc/arise), state (/var/lib/arise), data (/srv/arise)
==> 5/7  Active Directory domain AD.ARISECENLA.COM (NetBIOS ARISE)
==> 6/7  Docker and the Arise services
==> 7/7  Done. What still needs you
```

Every step says what it did. If one fails it stops and prints the line and
the log (`/var/log/arise/install.log`). Fix the cause and run it again — it
skips what is already done. Flags if you need them: `--skip-docker` (no
apps), `--skip-domain` (no AD, for a test box), `--dry-run` (prints the plan,
changes nothing).

Flags that arrived with v0.8 (the installer's header lists them all):

| Flag | What it does |
|---|---|
| `--ssh-key "ssh-ed25519 AAAA… name"` or `--ssh-key-file FILE` | enrols your public key for the admin user. **SSH is keys only**: password login is off, always (round 4, 33). With no key, SSH is closed until one is added; the closet monitor still signs in |
| `--no-caddy` | Caddy is now **on by default**: the dashboard behind `https://arise-server.ad.arisecenla.com` with the box's own certificate authority (round 3, 29). The root certificate is at `http://arise-server:4147/ca.crt`; `enroll-mac.sh` and `bind-mac.sh --dns` trust it on each Mac |
| `--no-tpm` | do not bind the encrypted disk to the TPM. Default: if the disk is LUKS and a TPM 2.0 is there, step 6j asks the passphrase once and binds it, so the box boots alone (round 3, 22) |
| `--no-safety` | skip step 6j: the break-glass admin, ClamAV, Timeshift, the TPM binding, the safe card |
| `--restore REPO` | **reinstall**: on a fresh Ubuntu, step 0b pulls `/etc/arise`, `/etc/samba`, the domain's offline backup and the pinned address back from that restic repository first, then installs around them. docs/REINSTALL.md |
| `--apps "a,b"` / `--no-apps` | the default is now **every template** (step 6a runs `arisectl app install-all`): all deployed, the autostart ones started within the memory budget, the heavy ones left stopped |
| `--kiosk` | also installs step 6d-2: the panel off at 23:00 and on at 06:00, and Screen Sharing of it through Guacamole (wayvnc) |

The disk: Bradly has not decided one partition or two (round 4, 91: "depends
on the storage of the OptiPlex", specs Friday). Both shapes work. One
partition is what the Ubuntu screen above does; two partitions (80 GB for
the system, the rest at `/srv/arise`) mean a runaway log can never fill the
church's files, only the data half needs the TPM-unlocked encryption, and a
reinstall can wipe the system half alone. Pick **Encrypt** on the Ubuntu
storage screen either way; it cannot be added later (docs/SECURITY.md).

The install wizard (round 4, 59: a short on-screen set of questions, flags
still working) is decided and not yet built; today the flags are the
questions.

### 5. Fixed address: automatic, nothing to type

The installer's step 2b keeps **the address Netgear A already gave the box**
and pins it in `/etc/netplan/60-arise-pinned.yaml` on the server, so the
domain controller never moves. No router setting changes, no existing device
changes address, and you never choose or type an IP (Bradly's rule,
docs/ANSWERS.md). `arisectl doctor` checks every day that the pinned
address is still the box's address.

Only if that step reported a warning, do it by hand with the same values
the box already has (`ip -4 addr` and `ip route` show them):

```bash
sudo nano /etc/netplan/60-arise-pinned.yaml
```

```yaml
network:
  version: 2
  ethernets:
    enp3s0:                      # your interface name — `ip link` shows it
      dhcp4: false
      addresses: [192.168.1.57/24]   # the address the box has NOW, unchanged
      routes:
        - to: default
          via: 192.168.1.1           # the router, as it is
      nameservers:
        addresses: [127.0.0.1]       # the DC is its own DNS
        search: [ad.arisecenla.com]
```

```bash
sudo netplan apply
```

Then continue at **First boot** below.

---

## Path B · Windows mode

What you keep: Windows, everything on the PC, the dashboard, the automator
on a scheduled task, restic backups, the GitHub mirror.

What you lose: **the directory.** A Windows 10/11 PC cannot be an Active
Directory domain controller. No domain accounts, no Mac binding, no
server-side user profiles. The Macs keep their local accounts and files. If
that is what you wanted the server for, this is not the path.

1. Open **PowerShell as Administrator** (right-click → Run as administrator).
2. ```powershell
   Set-ExecutionPolicy -Scope Process Bypass
   git clone https://github.com/Rehchu/Church-server-OS-.git C:\Arise\app
   C:\Arise\app\installer\install.ps1
   ```
   No git yet? Download the repo as a ZIP from GitHub, unzip it to
   `C:\Arise\app`, run the same `install.ps1`. It installs Git for next time.
3. It installs Python 3.12, Git and restic through `winget`, builds the venv,
   writes `C:\Arise\config\arise.toml` with `profile = "windows"`, registers
   four scheduled tasks (**Arise Web** at startup, **Arise YouTube
   Automator** 2:05 AM, **Arise Backup** 3:00 AM, **Arise GitHub Mirror**
   4:00 AM), opens port 4147 in the firewall, and starts the dashboard.
4. `-DryRun` prints the plan and changes nothing.

The "Arise YouTube Automator" task has the same name the old
`install-scheduler.bat` registered, so it replaces that one rather than
running beside it. Check Task Scheduler has exactly one, or the job runs
twice and spends the quota twice.

Then continue at **First boot** below, skipping the domain and Mac steps.

---

## Path C · Hands-off USB (autoinstall)

Path A with no questions. Build the USB per `installer/MAKE-USB.md`
**including** the `autoinstall.yaml` step, after putting your password hash
in the file:

```bash
openssl passwd -6 'the-password-you-want'      # on any Mac or Linux terminal
```

Boot the PC from the stick. It asks one question ("continue with
autoinstall?" — yes), wipes the disk, installs Ubuntu, clones the repo to
`/opt/arise`, runs `install.sh --no-start --skip-domain --skip-docker`, and
reboots. The login banner then tells you the one command left:

```bash
sudo bash /opt/arise/installer/install.sh
```

which provisions the domain (asks for the Administrator password), installs
Docker, and starts everything. Then **First boot**.

---

## What is running when the installer finishes

Everything below is installed, started and waiting after one run of
`install.sh` (Bradly: "all software should be on there ready to go"). Each
app's generated passwords are in `/etc/arise/secrets/apps/<app>.env`,
root-only; the same values sit in the app's own `.env`.

| | Address | First login |
|---|---|---|
| The desktop / dashboard | the monitor, and `http://arise-server:4147` | your directory or admin password |
| Cockpit (Linux console, a second door) | `https://arise-server:9090` | the box's own account (`bradly`) |
| Netdata (per-second graphs) | `http://arise-server:19999` | none |
| Uptime Kuma (is it up) | `http://arise-server:8082` | you make the admin on first visit |
| NetAlertX (who is on the network) | `http://arise-server:20211` | none |
| Portainer (containers) | `https://arise-server:9443` | make the admin within 5 minutes of first start |
| BookStack (the handbook) | `http://arise-server:8085` | `admin@admin.com` / `password`, change both |
| Jellyfin (the sermon archive) | `http://arise-server:8096` | you make the admin on first visit |
| Syncthing (media Mac mirror) | `http://arise-server:8384` | set a UI password on first visit |
| Vaultwarden (passwords) | `http://arise-server:8083` | admin token in the secrets file; signups off |
| Guacamole (remote desktop) | `http://arise-server:8084/guacamole` | `guacadmin` / `guacadmin`, change at once |
| Owncast (own live page) | `http://arise-server:8087` | `admin` / `abc123` at `/admin`, change at once |
| Icecast (audio to phones) | `http://arise-server:8000` | source and admin passwords in the secrets file |
| Trilium (Notes, app 28) | `http://arise-server:8090` | set the password on first visit |
| Immich (Photos, app 29) | `http://arise-server:2283` (see its template) | you make the admin on first visit; staff only |

**Every template is preinstalled** (Bradly, round 3, 5), and the honest
memory reality is this: the 26 templates together want far more RAM than
one PC has, so step 6a deploys every one (images pulled, passwords
generated, compose written) and starts only the ones marked `autostart` in
their `template.yaml`, biggest last, until the box's RAM minus a 2 GB
reserve for the domain and the dashboard is spoken for. Thirteen autostart
today: netdata, uptime-kuma, netalertx, portainer, bookstack, jellyfin,
syncthing, vaultwarden, guacamole, owncast, icecast, trilium, immich. The
rest (`frigate`, `churchcrm`, `nextcloud`, `moodle`, `mattermost`, `synapse`,
`kimai`, `phplist`, `nginx-rtmp`, `filebrowser`, `wg-easy`, `ollama`,
`open-webui`) are deployed and stopped; the Store starts one with a click
and shows the memory it costs. Every app runs under a memory and CPU cap
from its template (round 3, 40), and `arisectl doctor` warns when the
autostart caps would exceed the budget. `--apps "a,b"` on the installer
narrows the set, `--no-apps` deploys none. docs/STORE.md.

Every app answers the church LAN and the VPN only. Docker's published ports
bypass the normal firewall, so a small unit (`arise-docker-firewall`)
rewrites the chain Docker honours at every boot; in staging the allowed
list is empty and nothing at home can reach a container.

## The timers

| When (America/Chicago) | Unit | What |
|---|---|---|
| 02:05 | `arise-automator.timer` | the nightly YouTube job |
| 03:00 | `arise-backup.timer` | restic to the Synology, 30/12/24 kept |
| 04:00 | `arise-mirror.timer` | the GitHub mirror |
| 04:30 | `arise-trash.timer` | what has sat in a share's Trash for 30 days goes; stale upload parts after 3 days |
| hourly | `arise-devices.timer` | the network scan |
| every 15 min | `arise-idle-apps.timer` | desktop programs nobody has used for an hour are stopped |
| monthly | `arise-drill.timer` | the restore drill |
| Saturday 03:30 | `arise-update.timer` | only what Software Update queued: a snapshot first, a reboot only if needed |
| Sunday 23:30 | `arise-clamscan.timer` | the virus scan of the shares, video skipped, quarantine, a push |
| 23:00 / 06:00 | `arise-monitor-off.timer` / `arise-monitor-on.timer` | the closet panel sleeps and wakes (`--kiosk`) |

Nothing runs during a service (Sundays 10:30, Mondays 19:00); the verbs
behind these timers refuse to.

## Also installed: the splash, the UPS daemon, the drill, the closet card, the safety basics

- **Boot splash** (`--no-splash` to skip): the ariseOS Plymouth theme and a
  quiet kernel; docs/CONSOLE.md § The boot splash.
- **UPS** (`--no-ups` to skip): NUT is installed and set to shut the box down
  cleanly when the UPS reports low battery (answer 48). The driver stanza
  in `/etc/nut/ups.conf` stays commented until the UPS model is known;
  `sudo arisectl ups` says what to do and, once set, shows charge and runtime.
- **Restore drill**: `arise-drill.timer`, monthly; docs/BACKUPS.md § The restore drill.
- **The closet card**: `/srv/arise/shares/staff/CLOSET-CARD.html` (also in
  `/etc/arise/`): the box's addresses, the three commands, where the backups
  and the secrets are, who to call (write the phone numbers by hand), and a
  hand-written line for the restic password (Bradly's rule: the closet card
  is its only paper copy). Print it, tape it to the closet door.
- **The SAFE card** (step 6j): `/etc/arise/SAFE-CARD.txt`, root only, printed
  with `sudo arisectl rescue card`: the `arise-rescue` password and a line
  for the disk passphrase. **In the safe, never on the door.** It is a
  different card from the closet card on purpose.
- **The safety basics** (step 6j, `--no-safety` to skip; docs/SECURITY.md):
  `arise-rescue`, a local break-glass admin that signs in at the closet
  monitor when the domain itself is down (never SSH, never the dashboard;
  every use is pushed to Bradly); ClamAV and its Sunday scan; Timeshift and
  the first system snapshot; the TPM binding for the encrypted disk.
- **Step 5b** sets the domain's password policy with **no lockout**
  (round 3, 27); **step 6b** removes fail2ban if it was ever there and sets
  sshd to keys only; **step 6f** keeps the journal a year (4 GB cap) and
  rotates `/var/log/arise` weekly, 52 kept.
- **BIOS**: set the PC to power on by itself after a power cut (round 4,
  61): on a Dell, F2 → Power Management → **AC Recovery: Power On**. The
  installer cannot reach the BIOS; it prints this reminder at the end.

## Installing at home first, then carrying it to the church

Bradly's plan: install at home, check it, carry it in. The box must not
touch anything at home. So the first install runs in **staging** mode:

```bash
sudo bash /opt/arise/installer/install.sh --staging --kiosk --with-tailscale
```

What staging changes, and nothing else:

| At home (`--staging`) | At the church (plain `install.sh`, same other flags) |
|---|---|
| the domain listens on this box only (`interfaces = lo`); no home device can see the domain, its DNS or its shares | listens on the wire |
| the firewall opens only SSH and the dashboard; no DC port | the DC ports, LAN and VPN only, as documented |
| no address is pinned (it would pin your home address) | the church address is pinned on the box |
| the hourly network scan is off (it would list your house) | on |
| the apps deploy and start, but the Docker firewall lets nobody at home reach them | the LAN and the VPN reach them |
| timers enabled but idle: no automator token, no NAS, nothing to back up | the same timers, now with things to do |
| the dashboard shows a STAGING line in Needs You; `arisectl doctor` says so too | the line goes away |

Everything else is real: the OS, the desktop on the monitor, the dashboard,
the CLI, the domain itself (provisioned, just unreachable from the house),
Tailscale (`tailscale up` can wait for the church; if you do it at home, do
not advertise a route). Checking it from your laptop at home: SSH, and the
dashboard at the address `arisectl info` prints. Nothing at home connects to
it unless you type its address.

**At the church:** plug it into the switch, power on, then once:

```bash
sudo bash /opt/arise/installer/install.sh --kiosk --with-tailscale
```

The installer sees the staging marker and relocates: pins the church
address, puts Samba on the wire, opens the DC ports, refreshes the domain's
DNS records (`samba_dnsupdate`) so they carry the church address instead of
the home one, turns the network scan on, removes the marker. Then
`sudo arisectl doctor`.

## First boot — in this order

Every command below is real; run them on the server as `bradly`.

### 1. Dashboard password

```bash
sudo arisectl admin set-password
```

Then open **http://arise-server:4147** (or the IP) from any computer on the
church network and sign in as `bradly`.

### 2. The automator

```bash
sudo git clone https://github.com/Rehchu/arise-youtube-automation.git \
  /srv/arise/automator/ARISE_YouTube_Updater
```

It is a private repo; git asks for your GitHub username and a personal
access token (not your password). Then copy the two files that are never in
git into that folder:

```
/srv/arise/automator/ARISE_YouTube_Updater/token.json
/srv/arise/automator/ARISE_YouTube_Updater/client_secret.json
```

From the old PC (`D:\Arise Church Youtube Stuff\ARISE_YouTube_Updater\`), for
example with `scp` from PowerShell:

```powershell
scp "D:\Arise Church Youtube Stuff\ARISE_YouTube_Updater\token.json" bradly@arise-server:/tmp/
scp "D:\Arise Church Youtube Stuff\ARISE_YouTube_Updater\client_secret.json" bradly@arise-server:/tmp/
```
```bash
sudo mv /tmp/token.json /tmp/client_secret.json /srv/arise/automator/ARISE_YouTube_Updater/
sudo chmod 0600 /srv/arise/automator/ARISE_YouTube_Updater/token.json
```

Check it without spending quota or changing anything:

```bash
sudo arisectl automator preview
```

That is the server's `preview-tonight.bat`. The report lands in
`automator/LATEST_REPORT.md` and in the dashboard's Automator page. The
nightly timer is already on:

```bash
systemctl list-timers arise-automator.timer
```

Remember the token still expires every 7 days until the Google Cloud app is
published (Google Cloud console → APIs & Services → OAuth consent screen →
Audience → **Publish app**). The preflight reports it; the server cannot
click it for you.

### 3. restic password

```bash
openssl rand -base64 32 | sudo tee /etc/arise/secrets/restic-password >/dev/null
sudo chmod 0600 /etc/arise/secrets/restic-password
sudo cat /etc/arise/secrets/restic-password
```

**Copy that line into your password manager now.** Without it every backup
is unreadable, and nobody — not the server, not GitHub, not me — can get it
back.

### 4. The Synology

Full detail in `docs/SYNOLOGY.md`. The short version: the NAS joins the
domain, a share called `arise` is created on it, and the server mounts it.

```bash
sudo nano /etc/arise/secrets/synology.cred
```
```
username=arise-backup
password=<the NAS account's password>
domain=ARISE
```
```bash
sudo chmod 0600 /etc/arise/secrets/synology.cred
sudo nano /etc/arise/arise.toml        # [nas] host = the NAS's name or IP, share = "arise"
sudo arisectl nas mount
df -h /mnt/synology
```

Then the first backup, by hand, so you see it work:

```bash
sudo arisectl backup run
sudo arisectl backup status
```

The first run initialises the restic repository on the NAS and takes a while
(it copies everything once; after that only changes move). It prints each
job as done, failed or skipped, and writes the same to the dashboard's
Backups page.

### 5. The first Mac

`docs/DIRECTORY.md` and `docs/MAC-MIGRATION.md` have the full story. The
join itself is one script run on the Mac:

```bash
sudo bash bind-mac.sh --computer-name OFFICE-MAC-01 --dns 192.168.1.20   # from the mac/ folder, copied to the Mac; the IP is the server's
```

`--dns` writes a per-domain resolver file on the Mac (no router is touched;
Bradly's rule), binds it to `AD.ARISECENLA.COM`
with mobile accounts on, and checks that a domain user can be looked up.
Create that user first, on the server or in the dashboard's Directory page:

```bash
sudo arisectl user add vanessa --given Vanessa --surname Sanders
```

### 6. Doctor

```bash
sudo arisectl doctor
```

Checks everything above — services, domain, DNS, time, automator token,
restic repo, NAS mount, timers — and prints what is wrong in plain words.
Run it whenever something feels off, and paste its output to me when you
want help.

---

## Remote access

The PC goes in a locked closet; everything after the install happens from
somewhere else. The full story, with the trade-offs, is
[docs/REMOTE-ACCESS.md](docs/REMOTE-ACCESS.md); the three-site picture
(Pineville, Alexandria, the Apostolic Hub) is
[docs/MULTI-SITE.md](docs/MULTI-SITE.md). The short version:

1. **Put your SSH key on it before the door closes.** Give the installer
   `--ssh-key-file ~/.ssh/id_ed25519.pub` (or run `ssh-copy-id bradly@arise-server`
   from your Mac, then re-run the installer). Password login over SSH is off
   from the first run; with no key, SSH stays closed and the closet monitor
   is the way in.
2. **The VPN.** Re-run the installer with a flag:
   - `--with-tailscale` (recommended): installs Tailscale and prints the
     `sudo tailscale up --ssh --advertise-routes=…` line, which needs a browser
     login, so it is yours to run. Then install the Tailscale app on every
     off-site Mac, PC and phone, approve the subnet route and set the split
     DNS for `ad.arisecenla.com` in the admin console. No port forward.
   - `--with-wireguard`: native WireGuard on UDP 51820. **Not used at Arise:**
     it needs a port forwarded on the router, and Bradly chose Tailscale only
     with nothing forwarded (docs/ANSWERS.md 36, 111). Kept for another church.
3. **Remote desktop.** `sudo arisectl app deploy guacamole`, do the one-time
   database step in its template notes, open `http://arise-server:8084/guacamole`,
   change `guacadmin`, add the Macs (VNC) and PCs (RDP).
4. **HTTPS.** Caddy is on by default (`--no-caddy` to skip): the dashboard,
   Vaultwarden and Guacamole behind `https://…ad.arisecenla.com` with the
   server's own CA. Every enrolled Mac trusts the root certificate through
   `enroll-mac.sh` or `bind-mac.sh --dns`; anything else fetches it from
   `http://arise-server:4147/ca.crt`.
5. **The firewall** is always set: incoming denied by default, SSH allowed,
   the domain controller, dashboard and apps allowed from the LAN and the VPN
   only. No fail2ban and no lockout, by Bradly's choice (round 3, 27). Nothing
   is forwarded on the router (Tailscale only, docs/ANSWERS.md 36).

Check it from your phone's hotspot with the Tailscale app on: if
`http://arise-server:4147` opens, the closet can close.

## Where things are

| | |
|---|---|
| Dashboard | http://arise-server:4147 |
| Code | `/opt/arise` (Windows mode: `C:\Arise\app`) |
| Config | `/etc/arise/arise.toml`, `/etc/arise/backups.yaml` |
| Secrets | `/etc/arise/secrets/` |
| Data | `/srv/arise/{homes,shares,automator,apps,backups}` |
| NAS | `/mnt/synology` |
| Logs | `/var/log/arise/`, `journalctl -u arise-web`, `journalctl -u samba-ad-dc` |
| Install log | `/var/log/arise/install.log` |

## If something breaks

- **Dashboard not loading:** `sudo systemctl status arise-web`, then
  `sudo journalctl -u arise-web -n 50`.
- **Macs cannot find the domain:** on the server, `host -t SRV
  _ldap._tcp.ad.arisecenla.com 127.0.0.1` must answer. If not,
  `sudo systemctl status samba-ad-dc`. On the Mac, `/etc/resolver/ad.arisecenla.com` must name the
  server (`scutil --dns | grep -A3 arisecenla`); `bind-mac.sh --dns` writes it.
- **Kerberos "clock skew":** the server and the Mac are more than 5 minutes
  apart. `chronyc tracking` on the server; the Mac syncs to Apple by default.
- **Backup failed:** the dashboard's Backups page and `sudo arisectl backup
  status` show the error from restic verbatim. Nine times out of ten the NAS
  mount dropped: `sudo arisectl nas mount`.
- **Automator did nothing:** `automator/LATEST_REPORT.md` says why, every
  time. If that file did not change overnight, `sudo journalctl -u
  arise-automator -n 100`.
- **Start the domain over** (only on a fresh box, this deletes every user):
  `sudo systemctl stop samba-ad-dc && sudo rm -rf /var/lib/samba/* /etc/samba/smb.conf && sudo bash /opt/arise/installer/install.sh`.


---

Add `--kiosk` to `install.sh` to put the Arise desktop itself (Finder, dock, widgets) full screen on the closet monitor, or `--console` for the text `arisetui` dashboard instead (docs/CONSOLE.md).

**Decision, Oct 27 2026:** the old PC (a Dell OptiPlex, specs to follow) is wiped; path A. Start with `docs/PRE-WIPE.md`.

**Decision, Oct 28 2026:** there are two Windows PCs. Both are wiped and both get ariseOS: Arise-Pineville (the stronger one, the church's server) and Arise-Home (the other, at Bradly's house). docs/NODES.md. The one-box install above is what v0.8 ships; the node work is next. Rehearse the install and the reinstall at home first (round 4, 105; docs/REINSTALL.md).
