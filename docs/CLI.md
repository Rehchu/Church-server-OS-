# `arisectl` — the command line

Installed to `/usr/local/bin/arisectl` by `install.sh`. It imports the same
Python modules the dashboard uses (`server/arise_server/`), so the two never
disagree about what a backup did or who is in a group. It re-executes itself
under `/opt/arise/venv/bin/python` when that exists.

Anything that changes the box needs `sudo`. Anything that only reads does not.

```
arisectl info                       what this box is and whether it is well
arisectl doctor                     check everything, print what to fix (config, password, pinned address,
                                    SMART verdict per disk, services, domain, DNS, time, automator, backups;
                                    since v0.8: LUKS and the TPM, arise-rescue, clamav, timeshift, the church
                                    certificate, the apps' memory caps against the budget, the monitor timers
                                    and wayvnc where the kiosk is installed)
arisectl admin set-password         set the dashboard password (prompts twice)

arisectl service list
arisectl service status|start|stop|restart <unit>

arisectl user list
arisectl user add <name> [--display "Full Name"] [--groups Staff,Media] [--password P]
arisectl user passwd <name>         prompts
arisectl user enable|disable <name>
arisectl user remove <name>         asks you to type the name; the home folder stays
arisectl user homefix <name>        fix ownership of the home folder

arisectl group list
arisectl group add <group> [--description D]
arisectl group addmember <group> <user>
arisectl group removemember <group> <user>

arisectl computer list
arisectl computer remove <name>     for a Mac that was re-imaged and needs re-binding

arisectl share list
arisectl share add <name> <path> [--group "Domain Users"] [--comment C]
arisectl share remove <name>        files stay on disk

arisectl backup status              last run per job, repository size
arisectl backup jobs
arisectl backup run [job]           all jobs in order (then forget/prune), or one
arisectl backup snapshots
arisectl backup restore <id|latest> [--tag homes] [--at 2026-10-20] [--path /srv/arise/homes/office] --target /srv/arise/restore
arisectl backup verify              restic check --read-data-subset=10%
arisectl backup prune
arisectl backup drill [--quiet]     one random file back from last night's backup, compared; the monthly timer; its line goes to Discord #weekly
arisectl backup offsite             the off-site copy now: every new snapshot to Arise-Home (restic copy), raw recordings never (round 7, 53)

arisectl automator status
arisectl automator preview          dry run: prints tonight's plan, writes nothing
arisectl automator run              the real thing, same as 02:05
arisectl automator report [file]    latest, or a named one from reports/
arisectl automator holds
arisectl automator worklist
arisectl automator schedule 02:05   changes arise.toml and the systemd timer

arisectl app list
arisectl app templates
arisectl app catalog                the Store's catalogue (catalog/catalog.yaml): name, memory, category
arisectl app install-all            every template deployed; the autostart ones started within RAM minus 2 GB,
                                    the heavy ones left stopped (what install.sh step 6a runs)
arisectl app deploy <template> [--name instance]     a template or a catalogue entry
arisectl app start|stop|restart|update|remove|logs <name>
arisectl app autostart <name> on|off
arisectl app theme <name>           what of the house look that app takes (env, files, or CSS to paste)
arisectl app idle-sweep             stop the desktop programs nobody has used for an hour (arise-idle-apps.timer)

arisectl nas status|mount|unmount
arisectl mirror run                 refresh the bare GitHub mirrors

arisectl trash list                 what sits in every share's Trash, oldest first
arisectl trash sweep [--dry-run]    remove what is older than 30 days (arise-trash.timer, 04:30); also stale upload parts
arisectl trash empty <share>        the whole Trash of one share; the share's name typed again

arisectl cloud [status]             Nextcloud, the Macs' and phones' sync (docs/SYNC.md): running, its address, the folders
arisectl cloud people               per person: devices, last sync, conflicts settled, storage against the quota
arisectl cloud setup [--dry-run]    make Nextcloud ariseOS's: the directory account, the mounts, the theme, each home linked
arisectl cloud app-password <user> "<device>"   a device password for a phone or a Mac set up by hand (shown once)
arisectl cloud revoke <user> ["<device>"]       cut one device off, or every sign-in the person has
arisectl cloud sweep [--dry-run]    settle conflict copies: newest wins, the older to the Trash (arise-cloud-conflicts.timer, hourly)
arisectl cloud conflicts            what the sweep settled, newest first
arisectl cloud watch                the watcher arise-cloud-watch.service runs (SMB changes reach the clients)

arisectl update [check]             Software Update: what waits (security vs the rest), app images, reboot needed
arisectl update refresh             apt update and re-read
arisectl update queue <pkg|app|reboot|all|clear>   what the Saturday 03:30 run installs
arisectl update apply [--now] [--no-snapshot] [--quiet]   install the queue: a system snapshot first,
                                    refused during a service, a reboot only if needed and nothing is in service
arisectl update apt                 the plain apt upgrade
arisectl update self                ariseOS itself: pull the repo, pip, restart arise-web

arisectl automations list           every arise-* timer: what it does, next run, last result
arisectl automations pause|resume <timer>
arisectl storage [status|scan]      what is eating the disk; scan runs in the background
arisectl monitor status|on|off      the closet panel (off 23:00, on 06:00 by timer)
arisectl monitor share on|off       Screen Sharing of the panel through Guacamole, Bradly only

arisectl upkeep hourly              the hourly checks: a missed backup night, a church Mac silent 3 days, disk health, heat; each to Discord #alerts once
arisectl upkeep january             the January clean-up report and the Google export reminder (lists; never deletes)
arisectl upkeep changes [--limit N] the change record: what changed on the box, by Bradly, Kristina or Claude
arisectl upkeep health              every disk's SMART health and temperature, and the CPU's
arisectl notify test <channel>      one test post to Discord #alerts, #sunday, #weekly or #daily
arisectl notify discord             which of the four Discord channels are set (names only)
arisectl mail forward [status]      staff addresses: who forwards where (masked), on or off
arisectl mail forward run           one pass: what arrived at Resend goes on to each personal email (the 5-minute timer)
arisectl mail forward export <user> a leaver's mail: their forwarding log as CSV (forwarding only: no mailbox is kept)

arisectl security                   the Security app's rows: encryption, scan, certificate, two-step, rescue
arisectl twofa list                 who has two-step sign-in on
arisectl twofa reset <user>         turn it off for someone who lost the phone (the name typed)
arisectl rescue status              the break-glass admin arise-rescue: exists, last use
arisectl rescue rotate              a new password (prints nothing but "rotated"); rewrites the closet card: print it again
arisectl rescue card                write the closet card: /etc/arise/CLOSET-CARD.html (root only, with arise-rescue's password: print it, tape it INSIDE the closet) and a copy without it on the staff share; never prints the password
arisectl encrypt status             is the disk LUKS, is there a TPM, is it bound
arisectl encrypt tpm                bind the LUKS disk to the TPM with clevis (asks the passphrase once)
arisectl snapshot create "<note>"   a Timeshift system snapshot (rsync mode; church files are not in it)
arisectl snapshot list|restore <name>|prune    five kept; restore asks the name; never during a service
arisectl scan status                the weekly ClamAV scan: last run, what it found
arisectl scan run                   scan the shares now (video and audio skipped; refused during a service)
arisectl scan restore <file>        put a quarantined file back (the name typed)
arisectl reinstall <restic-repo>    rebuild this box from the Synology's backup (runs install.sh --restore; docs/REINSTALL.md)
```

Exit code is 0 on success, 1 on a failure it reported, 130 on Ctrl-C. In
sample mode (no config, or the tool for that command is not installed) it says
so on every command that would have changed something.

The timers call it: `arise-backup.service` runs `arisectl backup run`,
`arise-mirror.service` runs `arisectl mirror run`, `arise-nas-mount.service`
runs `arisectl nas mount`, `arise-trash.service` runs `arisectl trash sweep`,
`arise-update.service` runs `arisectl update apply` (Saturday 03:30),
`arise-idle-apps.service` runs `arisectl app idle-sweep`, `arise-clamscan.service`
runs `arisectl scan run` (Sunday 23:30), `arise-drill.service` runs
`arisectl backup drill --quiet`, the monitor timers run `arisectl monitor off|on`. On Windows the scheduled tasks run the same
commands through `C:\Arise\venv\Scripts\python.exe cli\arisectl`.

## arisectl devices

```
arisectl devices list              everything on the switch, from the last scan
arisectl devices scan [--quiet]    scan now (arp-scan, else a ping sweep); --quiet is what the hourly timer runs
arisectl devices scan --wide        also the common ranges an installer parks devices on (marked stray)
arisectl devices cameras           ONVIF discovery: which cameras answer, and whether this network can reach them
arisectl devices behind            what the office Netgear reports as attached ([[routers]])
arisectl devices name <mac> <name> give a device a name that sticks to its MAC
```

## arisectl mail

```
arisectl mail status                    Resend set up? from, reply-to, the audience
arisectl mail contacts                  the list
arisectl mail import <wix.csv>          parse, show the count, ask, then add (about a second per contact)
arisectl mail test <to> <subject>       send one test email; the body comes from stdin
```
Sending to everyone is the dashboard's job (it asks for the word `send`).

## The rest of the verbs

```
arisectl directory import <people.csv> [--apply]   the day-one people list (round 5, 8); checks only until --apply
arisectl quota [status]                  each home against its 50 GB quota
arisectl quota apply                     write the filesystem quota (setquota) for every home
arisectl sites                           the campuses and what answers at each
arisectl ups                             the UPS through NUT (not configured until the model is known)
arisectl link list|revoke <token>|sweep  the Finder's share links; sweep drops the expired ones
arisectl browser [status]|apply|policy   the closet monitor's Firefox: the theme, the policies (docs/BROWSER.md)
arisectl owner [status]                  Bradly's account: groups, sudo, the 02:05 job's drop-in; [owners] users too
arisectl owner setup [NAME]              make NAME the owner (default: [owner] user, then whoever ran sudo)
arisectl repos [status]|sync [NAME]|setup   the Arise repos, two-way with GitHub every 15 minutes (docs/REPOS.md)
arisectl offboard list|mark <name> --to <who>|cancel <name>|sweep   someone leaving (round 2, 24): 30 days, then the files move
arisectl audit [words] [--who U] [--failed] [--limit N]   the audit log, newest first, read-only
arisectl remote status|add-peer <name>   the VPN; add-peer is the WireGuard path, not used at Arise
arisectl notify test|send                the daily note (off: no webhook set)
arisectl archive status|build [--full]|search <words>|setup   the searchable archive of both repos (docs/ARCHIVE.md)
arisectl service-now [--quiet]           exit 1 during a service: the timers' ExecCondition gate
arisectl report weekly|status|test <ch>|pastors [YYYY-MM]   the Monday report, Discord's channels, a test line, the pastors' draft (never sends it)
arisectl songs inbox|usage|quarter       the Lyrics inbox now; this quarter's CCLI usage; write the quarter's CSV
arisectl channel copy                    the nightly copy of titles, descriptions and thumbnails (no quota)
arisectl speedtest [show]|run            the hourly internet speed test (refused during a service)
```
