# Arise Server: notes for Claude Code running on this box

You are on `arise-server`, the Arise Church server (Pineville, LA). Bradly
Dyer runs it; this file is how he wants you to behave here. Read it before
you run anything. docs/ANSWERS.md is the record of every decision he made;
when a doc and ANSWERS.md disagree, ANSWERS.md wins.

## What this box is

- Ubuntu Server 24.04 on a Dell OptiPlex in a closet, with a monitor that
  shows the Arise desktop (a kiosk browser on tty1).
- A Samba Active Directory domain controller: realm `AD.ARISECENLA.CHURCH`,
  NetBIOS `ARISE`. It is also the DNS for that domain.
- The dashboard (`arise-web.service`, port 4147): the desktop, the member
  portal, every app page. Code in `/opt/arise`, config in
  `/etc/arise/arise.toml`, data in `/srv/arise`, the Synology at
  `/mnt/synology`, state in `/var/lib/arise`, logs in `/var/log/arise/`.
- Apps are Docker Compose stacks under `/srv/arise/apps/<name>/`, deployed
  from `/opt/arise/templates/<name>/`. Their generated passwords live in
  `/etc/arise/secrets/apps/`.
- `arisectl` (`/usr/local/bin/arisectl`) is the command line for all of it.

## Where to look first

```
sudo arisectl doctor                       what is wrong, in order
sudo arisectl info                         what this box is
journalctl -u arise-web -n 100             the dashboard
journalctl -u samba-ad-dc -n 100           the domain
ls /var/log/arise/                         install, backup and automator logs
sudo arisectl backup status                last backups, with the reason for a failure
sudo arisectl automator status             the nightly YouTube job
```

## Rules that do not bend

1. Deleting is Bradly's click, not yours: never delete a user, a group, a
   share, a snapshot, a home folder, an app's data folder, or a file in
   `/srv/arise` unless he typed the name in this conversation. `arisectl`
   verbs that delete ask for the name; do not script around that.
2. Never change anything on a router, switch or the Google Mesh, and never
   suggest it as a fix. The network stays as it is (docs/ANSWERS.md). The
   server adapts: `/etc/netplan/60-arise-pinned.yaml` on this box, resolver
   files on the Macs, Tailscale for the rest.
3. Never run the automator by hand while its timer is enabled, and never
   twice in a night: `arise-automator.timer` fires at 02:05 America/Chicago.
   `arisectl automator preview` is the dry run; `run` is real and writes to
   YouTube. Never invent a CCLI number, a speaker or a sermon title.
4. `/etc/samba/smb.conf`: edit only with a backup copy made first and
   `testparm -s` run after; a bad smb.conf takes the domain down. Prefer
   `arisectl share add` / `remove`, which write `arise-shares.conf` instead.
5. Prefer `arisectl` verbs over raw commands; they log, they refuse the
   dangerous shapes, and the dashboard agrees with them.
6. Secrets stay where they are: `/etc/arise/secrets/`, the apps' `.env`
   files, `token.json`. Never print one into the conversation, never move
   one into git, never paste one into a doc.
7. Nothing on this box is reachable from the internet, by Bradly's choice.
   Do not open a port, add a port forward, or turn `public_url` on.
8. `--staging` means the box is at Bradly's house: the domain is on
   loopback and no scan runs. Do not "fix" that; `install.sh` at the church
   relocates it.
9. Tell him what failed. A command that did nothing is a result to report,
   not a step to skip.

## The timers

| When (America/Chicago) | Unit | What |
|---|---|---|
| 02:05 | `arise-automator.timer` | the nightly YouTube job |
| 03:00 | `arise-backup.timer` | restic to the Synology (30/12/24 kept) |
| 04:00 | `arise-mirror.timer` | GitHub mirror refresh |
| 07:00 | `arise-notify.timer` | the daily note (off: no webhook set) |
| hourly | `arise-devices.timer` | the network scan |

Do not schedule anything during a service: Sundays 10:30, Mondays 19:00.

## Working on the code

```
cd /opt/arise
python3 -m unittest discover -s tests -q     # must stay green
bash -n installer/install.sh                 # before touching the installer
python3 scripts/gen-demo-data.py             # after any API change
sudo systemctl restart arise-web             # after a change to server/ or web/
```

Fixed names (hostname, realm, port, paths above) are the contract in
docs/ARCHITECTURE.md: change none of them. Usernames are `first.last`.
Commits are Bradly's to push; stage and show him the diff.
