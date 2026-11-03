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
| `automator` | `/srv/arise/automator`, `/var/lib/arise/automator` | toolkit, reports and quota ledger. Google tokens, OAuth client secrets and deploy keys are deliberately excluded; sign in again after recovery |
| `homes` | the actual `[directory] homes_path` | every person's home; `source: homes` follows configuration, including an explicitly configured NAS path |
| `shares` | `/srv/arise/shares` | the staff, leadership, media and kids shares |
| `media` | `/mnt/synology/arise/media` | Proclaim graphics, loops, lower thirds, thumbnails, podcast art |
| `github` | `/srv/arise/backups/github-mirror` | a bare mirror of every repo in `arise.toml` (see below) |
| `config` (tagged `system`) | `/etc/arise` (with the secrets; the repository is encrypted), `/etc/samba`, `/var/lib/arise/samba-backup`, `/var/lib/samba/private`, the pinned netplan file | everything `arisectl reinstall` needs (docs/REINSTALL.md). `samba_offline: true` runs `samba-tool domain backup offline` into `/var/lib/arise/samba-backup/` first, a consistent copy of the domain database (copying `private/` while Samba writes can tear it); the last two kept |
| `apps` | `[apps] root` (normally `/srv/arise/apps`) | Docker app data, backed up while running Arise containers are stopped cleanly |
| `state` | `[paths] state_dir` (normally `/var/lib/arise`) | calendar, profiles, sharing grants, offboarding state and audit history; rebuildable archive, drill scratch, sessions and reset tokens are excluded |
| `leavers` | `[people] leavers_archive`, otherwise `/mnt/synology/arise/leavers` | permanent leavers archive, included in offsite copying; an unmounted NAS fails this job |

`source` fields resolve configured paths when a job runs. Existing default homes
and apps paths also follow configuration. Explicit custom paths stay as written.
After an upgrade, check `arisectl backup jobs` includes `state` and `leavers`;
the installer adds missing jobs without replacing customized jobs.

App consistency: before the apps job, the server records precisely which Arise
Compose containers are running, stops them gracefully, and checks they stopped.
A force-killed/OOM-killed container or failed stop refuses the snapshot. The
containers are restarted in `finally`, even when restic fails. The backup unit's
`ExecStopPost` and `arise-backup-recover.service` handle an interrupted process or
reboot using `/var/lib/arise/backup-apps-stopped.json`. Previously stopped apps
stay stopped. A failed restart leaves the record and reports failure. This means
app downtime during the cold backup: measure it before production use. It is not
a live database dump or proof of restore success; test each app's database restore
in an isolated VM. Never restore app database files over running containers.

The shared maintenance lock excludes software updates and app changes while a
backup runs, including between jobs in a CLI batch. A new backup needs at least
30 minutes before the ten-minute service cleanup allowance; its restic timeout
is capped to leave that allowance before the next regular or calendar service.
Timeout aborts the backup and restarts stopped apps; it never pauses restic with
databases left stopped. Clock changes, a new service added after a run starts,
or a failed app restart still need operator attention.

Each job is a separate snapshot. Stopping the app databases for the `apps` job
does not create an atomic snapshot with homes/shares copied earlier: SMB clients
may still write those files. For Nextcloud acceptance, restore its database and
files together on an isolated VM, run its supported consistency/rescan checks,
and verify representative documents. Where that cannot satisfy the recovery
target, schedule a documented full write freeze or use database-native backups
with a coordinated storage snapshot. Do not call the entire server snapshot
application-consistent merely because individual restic jobs succeeded.

The system job requires a fresh, nonempty Samba offline backup on every run.
Failure stops that job rather than saving only a stale domain copy. Missing
required paths fail the job. A leavers archive that does not exist yet is an
explicitly skipped optional source, provided its NAS is mounted.

Each job has an `exclude` list (caches, `**/.Trash`, `node_modules`,
`__pycache__`) and tags, so a snapshot can be found by what it is. The
shares' Trash (v0.8, docs/FINDER.md) is excluded on purpose: what sits in a
Trash is on its way out, and Previous Versions restores from the snapshots,
not the Trash.

Edit the file to add a job. It is read fresh on every run.

## Schedule and retention

| When (America/Chicago) | What |
|---|---|
| 02:05 | the automator runs (YouTube quota resets at 02:00) |
| **03:00** | `arise-backup.timer`: every job in order, then `restic forget --prune` with the policy below |
| 04:00 | `arise-mirror.timer`: refresh the GitHub mirror (the 03:00 run of the next night snapshots it) |
| after the jobs | the off-site copy to Arise-Home (round 7, 53), `restic copy` of every new snapshot |

## The restore drill

A backup nobody has restored from is a hope, not a backup. Once a month
(`arise-drill.timer`, a random hour on the first of the month) the server
picks one random file under 50 MB from the latest snapshot, restores it
into a scratch folder, compares it byte for byte with the live file when
that file still exists, writes the verdict to
`/var/lib/arise/drill-history.json` (the last 24), and wipes the scratch
folder. `sudo arisectl backup drill` runs it now and says what happened:
restored and identical, restored but the live file has changed since (normal
for a working file), or a failure with the reason. The dashboard reads the
same history. Bradly's choice, answer 47: monthly, automatic. Since v0.8 the
drill also checks that the newest `system` snapshot holds
`/etc/arise/arise.toml` and a domain backup tarball. Missing either fails the
drill. This is a prerequisite check, not a full domain restore rehearsal.

Policy from `arise.toml`: **keep 30 daily, 12 weekly, 24 monthly** snapshots (Bradly chose more than restic's usual default; docs/ANSWERS.md 47)
per snapshot group. A deleted file is recoverable only while a retained snapshot
actually contains it; retention is not a guarantee that every version survives
two years. The permanent leavers source remains on the NAS and is included in
new snapshots. Retention pruning and the 30-day Trash sweep are explicit owner
exceptions to the rule that arbitrary deletion requires a human decision.

The mirror refresh is scheduled after the backup, so the next night's snapshot
captures it. Schedule spacing alone does not prove the automator or backup has
finished: measure runtimes and inspect the jobs before relying on these windows.
The backup unit has a six-hour total limit, including offsite copying. A larger
first copy needs a planned maintenance window and a reviewed timeout.

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
arisectl backup restore latest --tag automator --at 2026-10-20 --target /tmp/restore-automator
```

which is `restic restore latest --tag automator --time "2026-10-20 23:59" --target ...`.
Use a scratch `--target` folder for file recovery; moving files into place is a
person's step. The CLI accepts `/` for a deliberate full recovery, so the target
argument itself is not a safeguard against overwriting live files.

**The whole server:** follow `docs/REINSTALL.md` on a fresh isolated machine.
Restore the domain through `samba-tool domain backup restore` from its offline
tarball; do not treat the copied live `private/` directory as a consistent domain
backup. Restore app data and matching secrets before starting any app. Include
the `state`, homes, shares, pastors, songs, repos and other configured jobs in the
recovery plan. A missing or unusable domain backup is a recovery failure, not
permission to provision a replacement domain silently.

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

## Where tonight's backup goes (round 5, row 15)

Until the Synology has its drives, the backup goes to **Arise-Home over
Tailscale**. `[backups] targets = ["synology", "arise-home"]` is the order;
the first one that is ready at 03:00 is used:

| Target | Ready when | Repository |
|---|---|---|
| `synology` | `/mnt/synology` is mounted | `synology_repo`, or `restic_repo` when that is empty |
| `arise-home` | a read-only SFTP batch answers non-interactively over Tailscale | `arise_home_repo`, e.g. `sftp:arise-backup@arise-home:/srv/arise/backups/restic-pineville` |

**Neither ready = the job fails red** with "no backup target is ready", in the
history, on the Backups page and in `arisectl backup status`. It is never a
quiet skip. The Backups page shows the live target, both rows and why a row
is not ready. The same restic password opens both repositories.

Setting up Arise-Home as the target (once, by Bradly):

1. On Arise-Home: an account that can only do sftp
   (`useradd -m -s /usr/sbin/nologin arise-backup`, and a `Match User
   arise-backup` block at the end of `/etc/ssh/sshd_config` with
   `ForceCommand internal-sftp`, `AllowTcpForwarding no`), and the folder
   `/srv/arise/backups/restic-pineville` owned by it.
2. On this server, as root: `ssh-keygen -t ed25519` (root's own key: the
   backup runs as root), copy the `.pub` to that account's
   `authorized_keys`, then use `sudo sftp arise-backup@arise-home` once, verifying
   the host-key fingerprint independently before accepting it. Quit after it
   connects; no shell permission is needed. The check refuses unknown host keys.
3. `arise_home_repo = "sftp:arise-backup@arise-home:/srv/arise/backups/restic-pineville"`
   in `/etc/arise/arise.toml`, restart arise-web, and
   `sudo arisectl backup run` once: the first run initialises the repository.

**The switch to the Synology** needs no change: once the Synology is mounted
it is ready, it comes first in `targets`, and the next run goes there (a new
repository is initialised there on the first run). The Arise-Home repository
stays as it is and becomes the automatic offsite copy below when `[backups]
offsite = "arise-home"`. No second job is needed.

## The off-site copy: Arise-Home (round 7, 53 and 54)

Bradly, round 7: **Arise-Home is the off-site copy**, and it takes
**everything except the raw recordings**. Bradly's house is far enough from
Pineville that a fire, a flood or a theft at the church leaves it standing.

After the nightly jobs and the prune, `arisectl backup run` copies every
snapshot from tonight's target (the Synology) to `arise_home_repo` with
`restic copy`: only what is new travels, and restic skips snapshots that are
already there. The first night it prepares the repository with the Synology's
chunker settings (`init --copy-chunker-params`), so the two deduplicate the
same way. Arise-Home keeps the same history as here (30/12/24, pruned after the
copy). The same restic password opens both.

| Tonight | What the off-site step does |
|---|---|
| The Synology was the target and Arise-Home answers | copies every new snapshot; a row **Off-site copy (Arise-Home)** in the history |
| Arise-Home was the target (no Synology yet) | nothing to copy: the off-site copy and the only copy are the same place, and the row says so in amber |
| Arise-Home does not answer | the row is red: "off-site copy not made: Arise-Home over Tailscale is not reachable" |
| `[backups] offsite = ""` | off, and `arisectl backup run` says so |

Raw recordings never go: no job backs them up (they live on the Synology's
recordings share, and YouTube has every service), and any snapshot tagged
`recordings` is skipped anyway (`[backups] offsite_skip_tags`).

`sudo arisectl backup offsite` runs the copy now; `GET /api/backups/offsite`
is tonight's plan and the last run, for the Backups page.

**A night with no backup** (round 7, 64): if no job has finished well in the
last 26 hours, the Needs You list says "No backup ran last night" in red and
Discord `#alerts` gets one line (once per missed stretch, `arise-upkeep.timer`,
hourly). One missed night is enough to be told.

**The restore drill** (round 7, 56) posts its one line to Discord `#weekly`:
"Restore drill passed: <file> came back from snapshot <id>", or "FAILED" and
why.

**Who can open them** (round 7, 58 and 59): Bradly and Kristina. The restic
password is written by hand on the closet card taped inside the closet, and
Kristina has it too; on the box it is `/etc/arise/secrets/restic-password`
(root only, never in a chat, never in Vaultwarden). If Bradly can't be reached,
Kristina follows the closet card.

Encryption does not make backups immutable. A compromised server with write
access to both destinations can delete both copies. A separately protected
offline or immutable copy remains a recommendation requiring the owner's chosen
storage design. Test recovery without access to the original server.

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
