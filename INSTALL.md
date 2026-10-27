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
and should get a **fixed address** (a DHCP reservation on the router for its
MAC address is enough). A domain controller that changes address, or drops
off Wi‑Fi at 2 AM, takes every Mac's login with it.

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
| Storage | **Use an entire disk**, tick **Set up this disk as an LVM group**. Pick the disk; confirm it wipes it. |
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
==> 5/7  Active Directory domain AD.ARISECENLA.CHURCH (NetBIOS ARISE)
==> 6/7  Docker and the Arise services
==> 7/7  Done. What still needs you
```

Every step says what it did. If one fails it stops and prints the line and
the log (`/var/log/arise/install.log`). Fix the cause and run it again — it
skips what is already done. Flags if you need them: `--skip-docker` (no
apps), `--skip-domain` (no AD, for a test box), `--dry-run` (prints the plan,
changes nothing).

### 5. Fixed address

If you did not set a DHCP reservation on the router, pin it on the server:

```bash
sudo nano /etc/netplan/50-cloud-init.yaml
```

```yaml
network:
  version: 2
  ethernets:
    enp3s0:                      # your interface name — `ip link` shows it
      dhcp4: false
      addresses: [192.168.1.20/24]   # a free address on the church LAN
      routes:
        - to: default
          via: 192.168.1.1           # the router
      nameservers:
        addresses: [127.0.0.1]       # the DC is its own DNS
        search: [ad.arisecenla.church]
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
sudo bash bind-mac.sh            # from the mac/ folder of this repo, copied to the Mac
```

It points the Mac's DNS at the server, binds it to `AD.ARISECENLA.CHURCH`
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
  _ldap._tcp.ad.arisecenla.church 127.0.0.1` must answer. If not,
  `sudo systemctl status samba-ad-dc`. On the Mac, its DNS must be the
  server's address (`scutil --dns | head`).
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
