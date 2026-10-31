# Reinstall from the backup

Bradly (round 3, 24): "Yes, with the synology holding the backup to the
server as well!" The Synology holds the server's restic repository, as it has
since v0.1; this is the runbook that turns that repository back into a working
server on a fresh Ubuntu. Like *Reset this PC*, one command once Ubuntu is on.

## What you need

- The Dell (or any PC) with a fresh **Ubuntu Server 24.04** install, LUKS
  ticked (docs/SECURITY.md, *Encryption*), hostname `arise-server`.
- The Synology on the network, reachable from the box, with the share that
  holds `arise-backups/restic`.
- The **restic password** from the closet card inside the closet, or from
  Kristina (round 7, 58). Without it the repository cannot be read. Nobody at
  Anthropic, Synology or restic can recover it.
- About an hour. The domain restore is minutes; the apps pulling their images
  is most of it.

## What comes back, and from where

The `config` job in `/etc/arise/backups.yaml` (tagged `system`, nightly 03:00) holds:

| Path | What it is |
|---|---|
| `/etc/arise` | arise.toml, backups.yaml, every secret (restic, Resend, VAPID, TOTP, the apps' passwords), the closet card |
| `/etc/samba` | smb.conf and arise-shares.conf |
| `/var/lib/arise/samba-backup/` | the domain itself: `samba-tool domain backup offline` tarballs, the last two. Taken right before the restic run, so the database inside is consistent |
| `/var/lib/samba/private` | a live copy of the same database, for a quick single-file look; not what the restore uses |
| `/etc/netplan/60-arise-pinned.yaml` | the pinned address, so the Macs find the server where they left it |

The `homes`, `shares`, `apps`, `automator` and `media` jobs hold the church's
files and the apps' data; they come back in the last step.

Why an offline backup and not just the files: Samba writes to `sam.ldb` while
it runs, and a copy taken mid-write can be torn. `samba-tool domain backup
offline` locks each database and writes a tarball that `samba-tool domain
backup restore` is built to rebuild a DC from. `backups.samba_offline_backup`
runs it before the config job; the monthly drill checks the newest `system`-tagged
snapshot still contains `arise.toml` and a samba tarball.

## The steps

On the fresh box, as the user Ubuntu's installer made:

```
sudo apt-get install -y git
git clone https://github.com/Rehchu/Church-server-OS-.git arise
cd arise
# mount the Synology once by hand (the restored arise.toml takes over afterwards):
sudo mkdir -p /mnt/synology
sudo mount -t cifs //SYNOLOGY/arise /mnt/synology -o username=...,password=...,vers=3.0
sudo arisectl reinstall /mnt/synology/arise-backups/restic
```

`arisectl reinstall` prints what it is about to do, asks you to type
REINSTALL, then runs `installer/install.sh --restore <repo>`, which:

1. **0b** asks for the restic password (closet card), reads the newest
   `system` snapshot and restores `/etc/arise`, `/etc/samba`,
   `/var/lib/arise/samba-backup` and the pinned address onto the fresh disk.
   It refuses if the box already has a domain database: `--restore` is for a
   fresh Ubuntu only.
2. **1 to 4** install packages, set the hostname, copy the code, build the
   venv; the config is already in place, so nothing is written over it.
3. **5** finds the samba tarball and runs
   `samba-tool domain backup restore --backup-file=… --targetdir=/var/lib/samba --newservername=arise-server`,
   puts the restored smb.conf where Samba reads it, runs `testparm`, starts
   `samba-ad-dc`. Every user, group, computer account and password is back.
   No tarball in the repository: it says so and provisions a fresh domain
   instead (users would need to be re-created; this is the fallback, not the
   plan).
4. **5b onward** as a normal install: shares, Docker, the apps (their `.env`
   files came back with `/etc/arise/secrets/apps`), the firewall, Caddy, the
   kiosk, the timers, the safety step.
5. Then the data:

```
sudo arisectl nas mount
sudo arisectl backup restore latest --tag homes  --target /
sudo arisectl backup restore latest --tag shares --target /
sudo arisectl backup restore latest --tag apps   --target /
sudo arisectl backup restore latest --tag automator --target /
sudo arisectl doctor
```

`--target /` puts each path back where it was. The `media` job's files are on
the Synology already and need no restore.

## Afterwards

- `sudo arisectl doctor` green, `sudo arisectl security` green or amber with
  reasons.
- The Macs keep working: the domain's SID, the computer accounts and the
  server's address are the same, so no Mac needs re-binding.
- Tailscale: `sudo tailscale up --ssh` once (its key is per machine; it is not
  in the backup on purpose).
- Token files the automator needs (`token.json`, `client_secret.json`) come
  back with the automator job.
- Print a fresh closet card: `sudo arisectl rescue card`, then tape it inside
  the closet and give Kristina the new copy.
- If the Synology is gone too, the same restore runs from Arise-Home's copy
  (round 7, 53): `sudo arisectl reinstall sftp:arise-backup@arise-home:/srv/arise/backups/restic-pineville`
  (the fresh box needs Tailscale up and its root key in arise-backup's
  `authorized_keys` on Arise-Home first: BACKUPS.md, "Where tonight's backup goes").

## Drilled, not proven

The monthly drill checks the system snapshot has what this runbook needs.
The full runbook has not been run on real hardware in this build; the first
real reinstall should be a rehearsal on a spare PC, not the day the Dell
dies. Put it on the calendar once the Synology is reachable from the box.
