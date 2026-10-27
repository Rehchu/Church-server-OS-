# Before the wipe — the checklist for the old Dell OptiPlex

Decision (Bradly, Oct 27 2026): the old Windows PC gets wiped and becomes the
server. Install path **A** (Ubuntu Server 24.04 LTS, `installer/install.sh`).
Model: a Dell OptiPlex, exact model and specs to follow.

Everything below happens **while Windows is still on it**. Once the USB stick
boots, the disk is gone.

## 1. Read the specs off it (two minutes)

Either of these gives everything `docs/HARDWARE.md` asks for:

- **The service tag.** A sticker on the case (top, side or back; on small-form
  OptiPlexes it is on a pull-out tab at the front). Seven characters, like
  `7XK2Q32`. Put it into https://www.dell.com/support and the page lists the
  exact model, CPU, RAM, disks and network card as shipped.
- **Or in Windows:** press Win+R, type `msinfo32`, Enter. Read *System Model*,
  *Processor*, *Installed Physical Memory (RAM)*, *BIOS Mode* (UEFI or Legacy).
  Then Win+R, `diskmgmt.msc` for the disks (size, and whether it says SSD or
  the disk model number).

Send: model, CPU, RAM, disk size and type, BIOS mode, and whether the Ethernet
port is in use or the PC is on Wi‑Fi.

## 2. Make sure nothing on it is the only copy

- **Is this PC the one that runs the nightly automator today?** If `D:\Arise
  Church Youtube Stuff\ARISE_YouTube_Updater` is on it, copy `token.json` and
  `client_secret.json` to a USB stick or password manager now. They are not
  in git on purpose and the wipe destroys them. Everything else in that folder
  is in `Rehchu/arise-youtube-automation` (commit and push once more first).
  Also delete the Windows scheduled task "Arise YouTube Automator" so two
  machines never run it the same night.
- Anything in `C:\Users\...` that matters: Desktop, Documents, Downloads,
  Pictures. Copy to the Synology or a USB drive. Nothing is recoverable after
  step 3.
- Proclaim, StreamYard, Canva, the website: all cloud-side; nothing to save.
- Browser passwords: if anyone saved passwords in a browser on this PC, sign
  into the browser's sync first or export them.

## 3. Prepare the stick (can happen today, no specs needed)

`installer/MAKE-USB.md`: download Ubuntu Server 24.04 LTS, write it with
Rufus (Windows) or `dd` (Mac). For the hands-off install, add
`installer/autoinstall.yaml` as it describes. Keep the stick; it is also how
the server gets reinstalled one day.

## 4. On wipe day, in this order

1. Plug in **Ethernet**. A domain controller on Wi‑Fi is a bad day, and the
   installer wants the network up.
2. Boot from the stick: power on and tap **F12** for the one-time boot menu,
   pick the USB device under *UEFI BOOT*. If it is not listed, **F2** → Boot
   Sequence → set *UEFI*, and under *System Configuration → SATA Operation*
   choose **AHCI** (not RAID). Secure Boot can stay on; Ubuntu is signed.
3. Install Ubuntu Server to the whole disk, hostname `arise-server`, user
   `bradly`, OpenSSH on. (The autoinstall does all of this unattended.)
4. First login: `sudo apt install -y git`, clone the repo, run
   `sudo bash installer/install.sh --admin-pass '...' --with-tailscale`
   (or `--with-wireguard` if that is the VPN choice).
5. Then the "First boot" list in `INSTALL.md`: dashboard password, token.json
   and client_secret.json into the automator folder, the restic password (and
   on paper), mount the Synology, `arisectl doctor`.

## 5. What the OptiPlex generation changes

| If it has | Expect |
|---|---|
| 4 GB RAM | directory, dashboard, automator, backups: fine. Docker apps: one or two, not Guacamole. An 8 GB stick is the cheapest upgrade there is |
| 8 GB RAM | everything, Guacamole included |
| a spinning disk | it works, but the dashboard and logins feel slow and the disk is the part most likely to die. A 240 GB+ SATA SSD is a 15-minute swap on an OptiPlex |
| 2 cores | fine; the box idles most of the day |
| only Wi‑Fi | run a cable. Not optional for a domain controller |

OptiPlex 3020/7020/9020 (4th-gen Intel, 2014) and newer run Ubuntu 24.04
without any driver work; the Intel network card is supported out of the box.
