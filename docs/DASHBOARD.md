# The dashboard — `http://arise-server:4147`

One page, ten sections, the church's own look. It is served by `arise-web.service`
from `web/` and talks to the JSON API in `server/arise_server/`.

| Section | What it shows | What it can do |
|---|---|---|
| **Overview** | the "Needs you" list (anything red or amber on the box), live CPU / memory / network / disks, the directory, automator and backup summaries, tonight's timetable | links into each section |
| **Directory** | domain health (LDAP, Kerberos, DNS), users, groups, joined computers | add a user, reset a password, enable/disable, delete (type the name), new group, add a member |
| **Files** | the SMB shares, what is on them, Mac readiness | new share, remove a share (files stay) |
| **Backups** | repository size and snapshot count, last run per job, full history with the reason for every failure, snapshot list, restore instructions | run a job now, `restic check`, refresh the GitHub mirror |
| **Automator** | last run, quota today, token state and the days Google leaves on it, holds and rules, the latest report, the worklist, past reports | preview tonight (dry run), run now (confirmed) |
| **Apps** | installed Docker apps with state, address, CPU and memory; the store | install, start, stop, restart, update, logs, remove (data kept) |
| **NAS** | mount state, free space, DSM health and RAID state when `dsm_url` is set, off-site copy | mount, unmount |
| **Services** | the systemd units that matter | start, stop, restart, jump to logs |
| **Logs** | the last 300 journal lines of any unit | pick a unit, refresh |
| **Settings** | every non-secret value of `arise.toml` and where it came from | read only, on purpose |

## Rules it keeps

- **Nothing is deleted without typing its name.** Users, shares and apps ask
  for the exact name. Home folders, share folders and app data folders are
  never removed by the dashboard at all.
- **Secrets never reach the browser.** `GET /api/settings` strips every key
  with `password`, `token` or `secret` in its name.
- **Sample data is labelled.** When a tool is missing or there is no config,
  the response carries `"demo": true` and the top bar shows an amber *Sample
  data* badge. The published preview page shows *Preview · sample data*.
- **One admin login.** `arisectl admin set-password` writes a bcrypt hash into
  `arise.toml`; the session is a signed cookie that expires after
  `session_hours`. With no hash set the page refuses to show anything and
  tells you the command.

## Live stats

`/api/stats/stream` is a Server-Sent Events feed: one JSON sample a second
(CPU, per core, temperature where the board reports it, memory, swap, network
and disk rates, load, uptime). One collector thread samples psutil; every
open browser reads the same cache, so a dozen tabs cost the same as one.
`/api/stats/history` returns the last 60 samples so the sparklines are full on
first paint.

## Keeping it on the LAN

The dashboard listens on every interface so a phone on the church Wi‑Fi can
open it. It is not meant to be exposed to the internet: there is no HTTPS in
this release and the password is the only lock. If you want it from home, use
an SSH tunnel (`ssh -L 4147:127.0.0.1:4147 bradly@arise-server`) or the
Synology's VPN server.

## Running it anywhere

```bash
cd server && pip install -r requirements.txt
python -m arise_server --demo --port 4147     # sample data, no root needed
```

`python3 scripts/gen-demo-data.py` rebuilds `web/demo-data.js` from the same
sample responses; that file is what the static preview page uses.
