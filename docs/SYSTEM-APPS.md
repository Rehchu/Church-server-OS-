# The system apps (v0.8 "Exodus", round 3)

What Windows 11 and macOS have underneath and ariseOS did not until now:
one Settings window, Software Update, Activity Monitor, a real Logs app,
Automations, Storage, and the closet monitor's hours and Screen Sharing.
Each is an app in Launchpad (its number in brackets), a route in the API,
and an `arisectl` verb, so the dashboard and the terminal never disagree.
The Store (round 3, 5) has its own page: docs/STORE.md.

## System Settings (15)

One window with a sidebar, like System Settings on a Mac: Appearance, Users,
Sharing, Backups, Software Update, Time, Notifications, Power, Config file,
About. Each section shows the current state in plain words and opens the
app that owns it (Directory, Finder, Backups, Software Update, Automations,
Monitor). Appearance switches are browser preferences (theme, sounds,
accessibility), the same ones Control Center has. Nothing here writes
`/etc/arise/arise.toml`; the Config file section says where to edit it.
Power holds Restart and Shut Down (a typed word each, refused during a
service), Restart the dashboard, Restart the domain.

## Software Update (27)

Round 3, 4 and 25: **security patches install themselves** (unattended-upgrades,
installer step 6f, never a reboot); **everything else waits for Bradly's
click** and installs **Saturday 03:30** after a system snapshot.

- `GET /api/updates`: packages split into *security* (suite ends in
  `-security`) and *other*, each app's image state from the last "Check
  apps", whether `/run/reboot-required` exists, the queue, the last apply,
  whether a service is on now. Cached ten minutes; the menu-bar badge
  ("4 updates · reboot") reads it every minute.
- **Refresh the lists** = `apt-get update`. **Check apps** pulls every app's
  images and compares image IDs with the running containers; nothing is
  switched. **Queue the ticked items** writes `/var/lib/arise/updates-queue.json`.
  **Install now** queues and runs the apply at once (typed word `install`).
- `arise-update.timer` (Saturday 03:30 America/Chicago) runs
  `arisectl update apply --quiet`:
  1. refuses if a service is on (an hour before to three hours after each
     service in `[church]`; `church.in_service_now` is used when present);
  2. runs `arisectl snapshot create "before update"` and **stops** if that
     verb is missing or fails (`--no-snapshot` to go without one);
  3. `apt-get install --only-upgrade` for the queued packages, then
     `docker compose pull` + `up -d` for the queued apps;
  4. reboots only if `/run/reboot-required` exists, the reboot was queued,
     and still no service is on.
  Everything lands in `/var/log/arise/updates.log` and
  `/var/lib/arise/updates-last.json` (the Last apply line in the app).
- `arisectl update` (status), `update refresh`, `update queue <pkg|app|reboot|all|clear>`,
  `update apply [--now] [--no-snapshot] [--quiet]`, `update self` (ariseOS
  itself from GitHub, the old `update apply`), `update apt` (plain upgrade).

## Activity Monitor (24)

Processes (psutil: CPU, memory, read/write, the container they run in) and
containers (`docker stats`), sortable, refreshed every three seconds while
open, the whole answer cached three seconds server-side. **End** asks for
the PID and refuses the processes the box cannot live without: PID 1,
systemd, Samba, Docker, SSH, the dashboard, cage and Epiphany, the UPS
monitor (`activity.may_kill`, pinned by the tests). TERM first, KILL a
second later if it ignored that.

## Logs (14)

A grouped picker: the arise units (dashboard, automator, backups, mirror,
scan, drill, updates, kiosk, screen sharing), the box (domain, Docker, SSH,
Caddy, UPS, disk health, security patches, Tailscale), every app (`docker
compose logs`), and the files under `/var/log/arise`. 100, 300 or 1000
lines; a search box that highlights; the last error line (error, failed,
fatal, traceback, denied, refused, timed out) highlighted with a jump
button; **Copy**; **Copy for Claude** copies a short prompt with the unit,
the last error and the lines, to paste into Claude on the box or on a
phone. Units outside the allow-list (`services.READABLE_RE`) are refused.

## Automations (25)

`systemctl list-timers --output=json` for every `arise-*` timer plus
fstrim and the daily security patches: what it does in plain words, next
run, last run and its result, whether it is paused. **Pause** / **Resume**
(typed timer name) are `systemctl disable --now` / `enable --now`, arise
timers only. **Preview (dry run)** for the automator, **Run every job now**
for backups, **Refresh the mirror**, **Scan now**. The real automator run is
still the timer's alone (CLAUDE.md rule 3). The banner repeats the rule:
never during a service. `arisectl automations list|pause|resume`.

## Storage (26)

Every real mount's free space, with the 75 % warning (Bradly, Oct 28) in
the Needs You list and the panel's colour; then a walk of the shares and the
app data folders in a background thread (time-capped, the result cached in
`/var/lib/arise/storage.json` with an "as of"): size per share and app, the
50 biggest files, files over 1 MB not **changed** in a year. Linux does not
record when a file was last opened on these disks, and the page says so.
Nothing deletes from here; Finder does, by hand. `arisectl storage [scan]`.

## Monitor (30): the closet panel and Screen Sharing

**Hours** (round 3, 30): `arise-monitor-off.timer` at 23:00 and
`arise-monitor-on.timer` at 06:00 run `arisectl monitor off|on`, which drives
cage's output through `wlr-randr` on the kiosk's Wayland socket (as the
`arise-kiosk` user). Honest note: after a scheduled off the panel does not
wake on a key; the 06:00 timer or **On now** brings it back. The screensaver
at five idle minutes and the lock at ten are unchanged. `arisectl monitor
status` shows the outputs and the timers; `doctor` warns when the timers are
missing on a kiosk box.

**Screen Sharing** (round 3, 17, Bradly only): `arisectl monitor share on`
- writes a wayvnc password to `/etc/arise/secrets/wayvnc` and a TLS pair
  under `/etc/arise/secrets/wayvnc-tls/` (wayvnc's authentication needs TLS);
- writes `/etc/arise/wayvnc.conf` binding wayvnc to the address this host
  has on **Guacamole's Docker network** (the gateway of `guacamole_default`),
  so only the Guacamole containers can reach port 5900; ufw allows that
  subnet alone;
- creates a Guacamole user named for the admin (a local Guacamole account,
  not the domain one; password in `/etc/arise/secrets/guacamole-<user>`,
  shown once) and the VNC connection **Closet monitor** with READ permission
  for that user only (`monitor.guac_sql`, idempotent);
- enables `arise-wayvnc.service` (runs as `arise-kiosk` on `wayland-0`).
The Monitor app shows the state and opens Guacamole. `share off` stops
wayvnc. The installer's `--kiosk` step installs `wlr-randr` and `wayvnc`,
enables the two timers, and turns sharing on when Guacamole is deployed.

Not verified here: guacd's VNC client negotiating wayvnc's VeNCrypt TLS
(the official image builds libvncclient with GnuTLS; if it refuses, the
fallback is wayvnc without `enable_auth`, still reachable from the Guacamole
network alone), and `wlr-randr --off` on the real cage build.

## Disks at 75 %

`storage.disk_alerts` adds a Needs You line (amber at 75 %, red at 90 %) for
any mount, with the free space and a pointer to Storage. It is in
`_attention`, so the push watcher and the morning report carry it too.
