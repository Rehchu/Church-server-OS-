# The automator on the server

The nightly YouTube job — `automator/arise_daily.py` in the
`ARISE_YouTube_Updater` toolkit — moves from the Windows PC's Task Scheduler
to a systemd timer on Arise Server. Same script, same 2:05 AM, same rules. The
server adds a place to see it: the dashboard's Automator page.

Bradly's rules, Oct 28 (round 4, 95 and 96): **the server runs the real
nightly job; the PC keeps the working copy, the dev work and its own backups
as it does now.** The repo is the sync path: Bradly keeps it current from
the PC, the server's 04:00 mirror and its checkout pull it, restic backs the
server's copy up to the Synology. Nothing on the server ever writes back to
the PC. Which machine holds which YouTube token is **still open**: paste
docs/ASK-THE-AUTOMATOR-CHAT.md into the automator's own chat and bring the
answers back (97).

Nothing about *what* the automator does changes. Its hold list, quota ledger,
worklist and report format are its own; this server runs it and shows the
output.

## Where it lives

```
/srv/arise/automator/ARISE_YouTube_Updater/      git clone of Rehchu/arise-youtube-automation
├── automator/
│   ├── arise_daily.py        the runner
│   ├── worklist.json         the only work it will do
│   ├── holds.json            videos no script may write to, and the standing rules
│   ├── quota.py · quota_ledger.json
│   ├── reports/              one file per run
│   └── LATEST_REPORT.md
├── token.json                NOT in git — put it here by hand
├── client_secret.json        NOT in git — put it here by hand
└── ... the rest of the toolkit
```

`install.sh` clones the repo (it is private: it asks for the GitHub token, or
you clone it yourself as the `arise` user) and creates a Python virtualenv at
`/opt/arise/venv` with `requirements.txt` plus `google-api-python-client`,
`google-auth-oauthlib`, `pillow`, `tzdata`.

Then copy the two credential files in. They come from the Windows PC, or from
the `CHURCH_MAC_SIGNIN` flow in the toolkit (`authorize.py` on any machine
signed in as `arisenow.church@gmail.com`). The `.gitignore` in the repo keeps
them out of git; the `automator` backup job keeps a copy in restic.

```bash
sudo -u arise cp /path/from/usb/token.json /srv/arise/automator/ARISE_YouTube_Updater/
sudo -u arise cp /path/from/usb/client_secret.json /srv/arise/automator/ARISE_YouTube_Updater/
chmod 600 /srv/arise/automator/ARISE_YouTube_Updater/{token,client_secret}.json
arisectl automator status      # says "signed in as Arise Church" or exactly what is wrong
```

## The timer

`config/systemd/arise-automator.timer` fires `arise-automator.service` at
**02:05 America/Chicago**, five minutes after the YouTube quota resets at
midnight Pacific, exactly as the Windows task did. The unit:

```ini
[Service]
User=arise
WorkingDirectory=/srv/arise/automator/ARISE_YouTube_Updater/automator
Environment=PYTHONUTF8=1 PYTHONIOENCODING=utf-8 TZ=America/Chicago
ExecStart=/opt/arise/venv/bin/python arise_daily.py
```

`PYTHONUTF8=1` is kept on purpose: the Sep 22 run on Windows died printing a
fire emoji. Linux consoles are UTF-8 anyway; the variable costs nothing and
removes the question.

`arise_daily.py` already handles the two Windows-isms that mattered: it
formats the report time without `%-I` (Linux-only) when on Windows, and it
imports `central_tz` so a missing `tzdata` cannot stop the run. On the server
`tzdata` is installed, so `zoneinfo` works and the fallback is never needed.

If the server is off at 2:05 the timer has `Persistent=true`: the run happens
when the server next boots. Same as the Windows behaviour, and a missed night
costs nothing because every job is resumable.

## What the dashboard shows

**Automator** in the sidebar:

| Panel | Source | |
|---|---|---|
| Last run | `automator/LATEST_REPORT.md` | rendered, with the done / failed / skipped counts and the units used pulled into a header |
| Next run | the timer | and whether it is enabled |
| Quota today | `quota_ledger.json` | units spent of 10,000, and the **2:05 run's ~2,000 units** marked so a chat session knows what is left |
| Sign-in | a 1-unit `channels.list` on page load (cached 10 min) | "Arise Church (@arisechurch4147)" or the exact error — `invalid_grant` means the token expired |
| Hold list | `holds.json` | read-only, with each video's reason |
| Worklist | `worklist.json` | each job, enabled or not, its note |
| Reports | `reports/` | every past run, newest first |

Two buttons: **Preview tonight** (`arise_daily.py --dry-run`, changes nothing,
writes a report) and **Run now**. Both run under the `arise` user via the
service unit so the log lands in `journalctl -u arise-automator` like the
scheduled run.

The dashboard never edits `holds.json` or `worklist.json`. Those are edited
in the toolkit folder (over the `automator` share, or by Claude from a session
that has the repo), committed, and pushed, so the repo stays the record.

## The quota is shared — the rule from CLAUDE.md

YouTube gives the channel 10,000 units a day, resetting 2 AM Central. The 2:05
run spends about **2,000** of them. A live service on the same day costs about
**1,500** more (StreamYard, YouTube's own writes). So a chat session doing bulk
work that day has roughly **6,500** units, not 10,000. On Oct 6 a session wrote
~7,500 after the nightly run and hit `quotaExceeded`, after which nothing could
even be *read* until the reset.

The Automator page shows the ledger for exactly this reason. Before a bulk
job, look at it.

## The token keeps expiring

The Google Cloud OAuth app (`iconic-vine-505702-i5`) is in **Testing**, and
Google expires a Testing app's refresh token every **7 days**. It has cost
four working days so far. The automator's preflight detects it and the report
says so, but no script can fix it. One click fixes it forever:

Google Cloud console → APIs & Services → OAuth consent screen → **Audience →
Publish app**. No review is needed for this scope. Then sign in once more
(`authorize.py`) and the token stops expiring.

Until that click is made, the dashboard's Sign-in panel will go red every
week, and `arisectl automator status` will say
`token expired - publish the OAuth app`.

## Preview vs run

| | Changes YouTube? | Spends quota? | Writes a report? |
|---|---|---|---|
| `arisectl automator preview` / Preview tonight | no | reads only (a few units) | yes |
| `arisectl automator run` / Run now / the 02:05 timer | yes, per `worklist.json` | yes, per the ledger | yes |

Both read `holds.json` on every write through `hold_gate.py`; a missing or
unreadable hold file refuses every write. That file stays the one hold list.
Nothing in Arise Server keeps a second copy.

## Moving off the Windows PC

1. On the PC: `schtasks /Delete /TN "Arise YouTube Automator" /F` so two
   machines do not both run at 2:05 (they would double-spend the quota and
   race on the same videos).
2. Commit and push the toolkit from the PC one last time.
3. On the server: `install.sh` (clone, venv), copy the two credential files,
   `arisectl automator preview`, read the report.
4. Enable the timer: `systemctl enable --now arise-automator.timer`
   (`install.sh` does this when the preview succeeds).
5. Next morning: Dashboard → Automator → Last run.
