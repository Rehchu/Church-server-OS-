# Recovering ariseOS from backup

A recovery must restore the original domain, credentials and application
data before starting services. It is not a normal fresh install. Rehearse
on an isolated empty VM before relying on this process for the church.
Do not connect a recovered duplicate DC to the live network during rehearsal.

## Prerequisites

Use a fresh encrypted Ubuntu 24.04 target with the intended hostname,
working internet, the tested source snapshot, and a readable restic backup.
Keep the restic password in its existing secure offline record; do not
create a new one. Mount the NAS using a protected credential file or a secure
password prompt, never a password in a command line or chat.

On a fresh target `arisectl` does not yet exist. The entry point is the
source install script, not `arisectl reinstall`:

```bash
sudo bash /path/to/reviewed-source/installer/install.sh \
  --restore /mnt/synology/arise-backups/restic --no-start --no-apps
```

Use the tested release/source snapshot, not the old README-only `main`.
The recovery first restores `/etc/arise`, Samba configuration, the Samba
offline backup and any saved netplan file. A missing or invalid domain
backup stops recovery; it must never silently provision a new domain.
The installer leaves services stopped so the original app environment and
data can be restored together. Keep the existing restic password unchanged.

Restore the required data/state jobs from the intended backup snapshot,
including homes, shares, apps, application state and any leaver archive.
Use the backup plan's actual tags and inspect the selected snapshots before
restoring to `/`; do not assume that `latest` across all jobs is one
consistent point in time. Restore apps with containers stopped. App `.env`
files and their databases must come from the matching backup generation.
Preserve the restored original secrets in `/etc/arise/secrets/apps`.

After restoration, start the domain and dashboard, validate the original
users/passwords/group memberships and DNS, then start apps one at a time.
Check every database-backed app, one SMB file and ACL, a staff home, a
Nextcloud login/sync, and a backup/restore. Check the restored audit/state
history. Do not initialize replacement accounts or a new domain to make a
failed check look healthy.

Review the restored address settings before connecting the replacement
hardware: old interface names and old addresses might not fit the new
machine. No router changes are part of this procedure. Reauthorize Tailscale
on the replacement machine through its normal secure flow.

The on-screen ISO workflow handles normal installation. Disaster recovery
still needs an administrator following this runbook; it is not currently
an unattended image-recovery wizard. A monthly sample-file drill does not
prove full domain/database recovery. Record the results of a complete fresh
VM recovery before declaring it ready for production.
