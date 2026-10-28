# Backups — what is kept, where, and how to get it back

"Backed up" means: a copy exists somewhere else, taken on a schedule, with a
record that it ran, and a restore that has been tried. Everything here is
built to meet that definition. A run that fails writes a failed row; a run
that is skipped writes a skipped row. Nothing is ever silent.

## The tool: restic

[restic](https://restic.net) makes **encrypted, deduplicated snapshots**. Each
night it looks at the job's folders, stores only the blocks that changed, and
records a snapshot you can browse like a folder from any date. The repository
is a plain directory on the Synology:

```
/mnt/synology/arise-backups/restic
```

encrypted with the password in `/etc/arise/secrets/restic-password`. **Write
that password on paper and keep it away from the building.** Without it the
repository is noise; with it, any Linux or Mac with restic installed can read
every snapshot, with or without Arise Server.

## The jobs: `/etc/arise/backups.yaml`

| Job | Paths | What it is |
|---|---|---|
| `automator` | `/srv/arise/automator` | the YouTube toolkit: scripts, song bank, transcripts, setlists, thumbnails, the reports and the quota ledger. `token.json` and `client_secret.json` are **in** this backup (they are not in git, so this is their only other copy) |
| `homes` | `/srv/arise/homes` (or `/mnt/synology/homes` when homes are on the NAS) | every person's Desktop, Documents and whatever else they put in their home |
| `shares` | `/srv/arise/shares` | the staff, leadership, media and kids shares |
| `media` | `/mnt/synology/arise/media` | Proclaim graphics, loops, lower thirds, thumbnails, podcast art |
| `github` | `/srv/arise/backups/github-mirror` | a bare mirror of every repo in `arise.toml` (see below) |
| `config` | `/etc/arise`, `/etc/samba`, `/var/lib/samba/private` | the domain itself and the server's settings |
| `apps` | `/srv/arise/apps` | the Docker apps' data (Vaultwarden's vault, Uptime Kuma's history, Syncthing's config) |

Each job has an `exclude` list (caches, `.Trash`, `node_modules`,
`__pycache__`) and tags, so a snapshot can be found by what it is.

Edit the file to add a job. It is read fresh on every run.

## Schedule and retention

| When (America/Chicago) | What |
|---|---|
| 02:05 | the automator runs (YouTube quota resets at 02:00) |
| **03:00** | `arise-backup.timer`: every job in order, then `restic forget --prune` with the policy below |
| 04:00 | `arise-mirror.timer`: refresh the GitHub mirror (the 03:00 run of the next night snapshots it) |
| 04:30 | the Synology's own Hyper Backup to the off-site copy (set on the NAS) |

Policy from `arise.toml`: **keep 30 daily, 12 weekly, 24 monthly** snapshots (Bradly chose more than the old 14/8/12 default; docs/ANSWERS.md 47)
per job. A file deleted on a Tuesday is in last night's snapshot for two weeks,
in a weekly for two months, in a monthly for a year.

The run order matters: the automator must be finished before its folder is
snapshotted, and the mirror must be refreshed before the next snapshot. If the
automator is still running at 03:00 (it never has been; a run is under ten
minutes), the backup job snapshots whatever is on disk and notes it.

## Where to see that it ran

- **Dashboard → Backups**: last run per job (green/red), bytes added,
  snapshot count, repository size, free space on the NAS. The red ones say
  why.
- `arisectl backup status`: the same table in the terminal.
- `/var/lib/arise/backup-history.json`: the raw rows, one per job per run
  (`job, started, finished, ok, snapshot_id, bytes_added, error`).
- `journalctl -u arise-backup`: restic's own output.

## Restoring

Set these once in the shell (or use `arisectl`, which does it for you):

```bash
export RESTIC_REPOSITORY=/mnt/synology/arise-backups/restic
export RESTIC_PASSWORD_FILE=/etc/arise/secrets/restic-password
```

**One file, as it was last Thursday**

```bash
restic snapshots --tag homes                       # find the snapshot id from Thursday
restic restore <id> --include "/srv/arise/homes/jsmith/Documents/Budget 2026.xlsx" --target /tmp/restore
# the file is at /tmp/restore/srv/arise/homes/jsmith/Documents/Budget 2026.xlsx
```

or browse without restoring:

```bash
mkdir -p /mnt/restic && restic mount /mnt/restic       # then open /mnt/restic/snapshots/<date>/... in another terminal; Ctrl-C unmounts
```

**One folder**

```bash
restic restore <id> --include "/srv/arise/shares/media/loops" --target /tmp/restore
```

**A whole job to a date**

```bash
arisectl backup restore --job automator --at 2026-10-20 --target /tmp/restore-automator
```

which is `restic restore latest --tag automator --time "2026-10-20 23:59" --target ...`.
Restores go to a `--target` folder, never straight over the live data; moving
the restored files into place is a person's step.

**The whole server** — reinstall Ubuntu, run `installer/install.sh --skip-domain`,
mount the NAS (`arisectl nas mount`), restore the `config` job on top of the
fresh system (`arisectl backup restore latest --tag config --target /`), then
`systemctl unmask samba-ad-dc && systemctl enable --now samba-ad-dc`. The domain
comes back with every user and computer account. See
`INSTALL.md`.

## The GitHub mirror

Every repo in `[github].repos` in `arise.toml` is mirrored to
`/srv/arise/backups/github-mirror/<owner>__<repo>.git`:

```bash
git clone --mirror https://github.com/Rehchu/arisechurch.git      # first time
git -C <path>.git remote update --prune                            # every night after
```

A mirror is a bare repository with every branch, tag and commit. Clone from it
like from GitHub. The private repos need a **read-only** fine-grained token
(GitHub → Settings → Developer settings → Fine-grained tokens → Contents:
read-only on those repos, one year expiry) saved as one line in
`/etc/arise/secrets/github-token`, mode 0600. `arisectl mirror run` does a
refresh now and reports each repo as updated, unchanged or failed; the
dashboard's Backups page shows the same.

## Verifying — once a month

restic can read the whole repository back and check every block:

```bash
arisectl backup verify          # = restic check --read-data-subset=10%
```

Ten percent of the data, chosen at random, every month; the full read
(`restic check --read-data`) once a year or after any NAS drive is replaced.
`arise-backup-verify.timer` runs the monthly one on the first Sunday at 05:00
and the result is a row in the history like any other.

And the human half: **restore one real file every month** and open it.
A backup that has never been restored is a guess.

## What is NOT backed up here

- **The YouTube videos themselves.** They live on YouTube. Nothing on this
  server holds the recordings; StreamYard and YouTube do. If a local archive
  of the services is ever wanted, that is a separate job (and terabytes).
- **The live website.** Its code is in the `arisechurch` repo (mirrored, see
  above) and the CMS exports and audit material are in `arise-church-backup`
  (also mirrored). The design-only parts that live in the Wix Editor are
  Wix's; they are not exportable.
- **Mail, Google Drive, Tithe.ly, Canva.** Those are their providers'.
- **The Synology's own system settings** — use DSM's Control Panel →
  Update & Restore → Configuration Backup, and keep that `.dss` file in the
  `arise` share so restic picks it up.
- **Anything on a Mac that is not in Desktop, Documents or the share.**
  The migration doc says what stays local. If it matters, it goes in the
  share.
