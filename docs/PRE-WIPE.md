# Before the wipe — the HP EliteDesk 800 G1 SFF

Decision (Bradly, Oct 30, H6): the **HP EliteDesk 800 G1 SFF** is free to wipe
and becomes arise-server. The Dell OptiPlex 3010 is the spare. Install path
**A** uses Ubuntu Server 24.04 LTS. Check the exact CPU, RAM and disks before
buying the approved 500 GB SATA SSD and, if needed, compatible RAM to 16 GB
(`docs/HARDWARE.md`).

Complete the preservation checks **while Windows is still on it**. Booting
the USB does not erase a disk by itself; confirming the installation storage
plan does. Review the disk identity before that confirmation.

## 1. Read the specs off it (two minutes)

Either of these gives everything `docs/HARDWARE.md` asks for:

- **The HP product and serial numbers.** Read the case label and the
  matching HP support page/service manual. Factory specifications are a
  starting point; inspect the installed parts because they may have changed.
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
  in git on purpose and the wipe destroys them. Also preserve any uncommitted files and local-only history; do not assume
  GitHub contains everything. The existing designated automator runner stays
  in charge until Bradly deliberately migrates it. Do not delete its Windows
  scheduled task as part of this checklist; follow `docs/AUTOMATOR.md` for a
  coordinated cutover, with a recoverable copy of the task configuration.
- Anything in `C:\Users\...` that matters: Desktop, Documents, Downloads,
  Pictures. Copy to the Synology or a USB drive. Verify the copies before confirming disk changes in the installer.
- Check Proclaim media, exports, browser profiles and other local app data
  even when an app uses the cloud. Confirm the needed files can be restored.
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
2. Boot the HP from the stick: use **Esc/F9** for its boot menu and **F10**
   for setup, following the on-screen prompts. Select the UEFI USB entry.
   Check the actual storage mode before changing it; a SATA-mode change can
   break the old Windows boot. Ubuntu has signed boot components, but verify
   Secure Boot with this media on this machine. The Dell spare uses F12/F2.
3. Follow `INSTALL.md` for the on-screen installation. Select the intended
   disk, choose LUKS encryption for production and review the final storage
   plan. The media asks for storage and identity; it does not silently wipe
   the largest disk.
4. Eject the ISO after Ubuntu finishes. Complete the ariseOS firstboot screens:
   choose home/test staging for a rehearsal, the owner, domain password and
   the **core app set** (Nextcloud, Vaultwarden, Uptime Kuma, Netdata and
   File Browser), or **Desktop and directory only** for a smaller test VM.
   Password entry is interactive. Do not put domain passwords in command-line
   arguments.
5. After the desktop appears, configure the NAS and backups and verify a
   restore. Record the restic password and LUKS passphrase on the owner-approved
   closet card; Bradly and Kristina must be able to unlock the disk after a
   restart. Test that unlock with the USB removed. Optional early-boot SSH
   needs separate setup and a tested LAN address (`docs/SECURITY.md`).
   The automator stays on its existing designated runner
   until the deliberate migration described in `docs/AUTOMATOR.md`.

For advanced manual installation, use the tested source under
`/opt/arise-src` and the instructions in `INSTALL.md`; installed runtime code
lives under `/opt/arise`. Omit `--admin-pass` so the installer prompts.

## 5. Before declaring it ready

## 6. On install day, in this order

1. Plug in **Ethernet**. A domain controller on Wi-Fi is a bad day, and the installer wants the
   network up.
2. Boot from the stick: power on and tap **F9** (HP's boot menu; F12 on the Dell), pick the USB
   under *UEFI Boot Sources*.
3. The install disc's two screens (installer/MAKE-USB.md):
   - **the disk:** check it's the new SSD, keep LVM, tick **Encrypt the LVM group with LUKS**,
     type the passphrase twice and write it on the safe card;
   - **you:** your name, server name `arise-server`, user `bradly`, a password.
4. It restarts and stops at **"Please unlock disk"**: type the passphrase. Then the ariseOS
   setup wizard runs on the screen (church or home, the domain password, the rest).
5. Then the "First boot" list in `INSTALL.md`: the dashboard password, the restic password (and
   on paper), mount the Synology, `sudo arisectl doctor`.
6. From your PC, add your SSH key so the passphrase can be typed from a church computer
   (docs/SECURITY.md), then `sudo arisectl encrypt ssh`.

## 6b. If the install seems frozen

Every step now prints its time, long steps print "still working (N min)" every minute, and
nothing waits forever: each slow step has a time limit, and git never stops to ask for a
password. So if the screen hasn't changed for **20 minutes**:

1. Press **Ctrl+Alt+F2** (in VirtualBox: Right Ctrl+F2) and log in. If that screen comes up,
   the computer is fine and the install is busy or stuck on one thing. Run:
   `cat /var/log/arise/install-step` (the step and when it started),
   `sudo tail -n 30 /var/log/arise/install.log` (what it last did), and
   `top` (what is using the CPU; q to quit). Send those to Claude.
2. If **nothing** answers, not even Ctrl+Alt+F2 or Caps Lock, the whole computer froze:
   that's the hardware, not the installer. Hold the power button and start it again: the setup
   screen comes back with Retry (or run `sudo arisectl setup`); finished steps are skipped.
   `cat /var/log/arise/install-step` still says where it stopped.
3. Ctrl+Alt+F1 goes back to the install screen.

## 7. What this PC's generation means

The HP model is a candidate, not a physical test result. Verify the installed
RAM, SSD health, wired link, firmware boot, encrypted restart and recovery
path. Test the chosen apps together with a backup and restore; more RAM does
not prove every catalogue app can run together. The expected TPM 1.2 means
passphrase boot (H3); only a verified usable TPM 2.0 invokes H6's exception.
Power restoration alone does not make a locked server available. Keep the
spare Dell and its data separate from the selected installation disk.


| It has | Expect |
|---|---|
| 8 GB | the domain, the dashboard, backups and the core five apps: comfortable |
| 16 GB | room for the Store's heavier apps (BookStack, Jellyfin, Immich) as well |
| a spinning disk | works, but slow and the part most likely to die: the SSD is the fix (H5) |
| a 4-core i5 (4th gen) | more than enough; it idles most of the day |
| Intel I217-LM network | supported by Ubuntu 24.04 out of the box |
