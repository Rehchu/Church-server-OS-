# `arisectl` — the command line

Installed to `/usr/local/bin/arisectl` by `install.sh`. It imports the same
Python modules the dashboard uses (`server/arise_server/`), so the two never
disagree about what a backup did or who is in a group. It re-executes itself
under `/opt/arise/venv/bin/python` when that exists.

Anything that changes the box needs `sudo`. Anything that only reads does not.

```
arisectl info                       what this box is and whether it is well
arisectl doctor                     check everything, print what to fix
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

arisectl automator status
arisectl automator preview          dry run: prints tonight's plan, writes nothing
arisectl automator run              the real thing, same as 02:05
arisectl automator report [file]    latest, or a named one from reports/
arisectl automator holds
arisectl automator worklist
arisectl automator schedule 02:05   changes arise.toml and the systemd timer

arisectl app list
arisectl app templates
arisectl app deploy <template> [--name instance]
arisectl app start|stop|restart|update|remove|logs <name>

arisectl nas status|mount|unmount
arisectl mirror run                 refresh the bare GitHub mirrors
```

Exit code is 0 on success, 1 on a failure it reported, 130 on Ctrl-C. In
sample mode (no config, or the tool for that command is not installed) it says
so on every command that would have changed something.

The timers call it: `arise-backup.service` runs `arisectl backup run`,
`arise-mirror.service` runs `arisectl mirror run`, `arise-nas-mount.service`
runs `arisectl nas mount`. On Windows the scheduled tasks run the same
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
