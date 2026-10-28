# The automator on the server

The Arise YouTube nightly job (`automator/arise_daily.py` in
`Rehchu/arise-youtube-automation`) moves from the church PC to ariseOS. The
session that maintains the automator wrote the brief for it:
**SERVER_HANDOFF.md** in that repo, commit "Server-ready automator"
(8326b4a, Oct 28 2026). This page is how ariseOS carries it out. Where this page
and the handoff disagree on the automator's own rules, **the handoff wins**.

## Where things stand

- **The PC is the runner** until Bradly says otherwise. `automator/runner.json`
  in the repo says `"pc"`. Only the machine named there may change anything;
  every other machine writes a "not the runner" report and stops.
- **ariseOS gets fully ready**: its own user, its own OAuth client and token,
  the timer, the pull, the logging. The timer can be on from day one. While
  `runner.json` names the PC, each 02:05 run writes a "not the runner" report,
  changes nothing and costs no quota.
- **The switch is Bradly's**, made on the PC by changing `runner.json`,
  committing and pushing (Cutover, below). Nothing on ariseOS flips it.

## The rules ariseOS keeps (the handoff's section 1)

1. Credentials (`token.json`, `client_secret*.json`, the deploy key) never go
   in git, a log, a report, an archive or a chat. No backup job takes them
   (`/etc/arise/secrets/youtube` is excluded; the automator job also excludes
   `**/token.json`, `**/client_secret*.json`). A test scans this repo for real
   Google token shapes (`1//0…`, `GOCSPX-…`, `ya29.…`) on every run.
2. Both repos stay private.
3. The job does only what `worklist.json` lists. ariseOS never edits
   `holds.json`, `worklist.json`, `runner.json`, `song_bank.json` or
   `speakers.json`; Bradly edits them on the PC. The dashboard shows them read-only.
4. Videos in `holds.json` are never written to (`hold_gate.py` refuses).
5. Nothing deletes, unlists or privates a video or a playlist.
6. **No apply run by hand.** The dashboard's and `arisectl`'s Run is refused
   while the timer is on, which is always. Preview is `--plan-only`: it changes
   nothing, but **its reads spend real quota** on the shared project, so it asks first.
7. No speaker, song credit, CCLI number or sermon theme is ever inferred from a
   transcript, Whisper's included.
8. Channel `UCGS9j7B_prcJkbTNgzlGrKg` (Arise Church); Cloud project `iconic-vine-505702-i5`.

## Where ariseOS puts it

The handoff's layout, with three placements changed for least privilege. The
variables are the handoff's own, so the automator's code is unchanged.

| What | The handoff | ariseOS | Why the difference |
|---|---|---|---|
| The checkout (`ARISE_REPO`) | `/opt/arise/ARISE_YouTube_Updater` | `/srv/arise/automator/ARISE_YouTube_Updater` | `/opt/arise` is the dashboard's own git checkout; `/srv/arise/automator` is already backed up nightly |
| The user | `arise` | `arise-yt` (uid 1502) | `arise` (uid 1500) already owns the Docker apps' data; the token gets a user of its own |
| Secrets (`ARISE_TOKEN`, `ARISE_CLIENT_SECRET`) | `/etc/arise/secrets/` | `/etc/arise/secrets/youtube/` (arise-yt, 0700; files 0600) | `/etc/arise/secrets/` also holds the backup password, two-step secrets and the rescue password; the job cannot read them |
| State (`ARISE_STATE_DIR`) | `/var/lib/arise` | `/var/lib/arise/automator` (arise-yt) | `/var/lib/arise` holds the audit log and the dashboard's state |
| The venv (`ARISE_PYTHON`) | `/opt/arise/venv` | the same | |
| The environment | `/etc/arise/arise.env` | the same (paths only) | |
| The wrapper | `/opt/arise/bin/arise-nightly.sh` | `/opt/arise/scripts/arise-nightly.sh` | the handoff's script, unchanged, shipped in this repo |
| The units | `arise-nightly.service` / `.timer` | `arise-automator.service` / `.timer` | the name the dashboard, arisectl and the docs already use; same contents as the handoff's section 7 |
| Previews | `arise_daily.py --plan-only` by hand | `arise-automator-preview.service` | the same command as the same user, behind the same lock |

So the handoff's morning checks read, on ariseOS:

```
sudo cat /var/lib/arise/automator/LATEST_REPORT.md
sudo tail -40 /var/lib/arise/automator/last-run.log
systemctl list-timers arise-automator.timer
sudo stat -c '%a %U %y' /etc/arise/secrets/youtube/token.json
sudo -u arise-yt git -C /srv/arise/automator/ARISE_YouTube_Updater status
```

## Setting it up

`install.sh` runs `scripts/arise-automator-setup`; `sudo arisectl automator setup`
runs it again any time. It makes the user and folders, writes
`/etc/arise/arise.env`, makes a **read-only deploy key**, pins GitHub's published
host keys, clones `main`, installs the libraries and log rotation. Then, in
this order, the parts only Bradly can do:

1. **GitHub**: Rehchu/arise-youtube-automation → Settings → Deploy keys → Add,
   title "ariseOS server", paste the key the setup printed, **leave "Allow
   write access" unticked**. Then `sudo arisectl automator setup` again; it clones.
2. **Cloud Console**, project `iconic-vine-505702-i5`:
   - APIs & Services → OAuth consent screen → **Audience** → if it says
     Testing, **Publish app**. In Testing, refresh tokens die after 7 days.
   - Credentials → Create credentials → OAuth client ID → **Desktop app**,
     named **ariseOS server**. Download the JSON.
3. Copy it in with `scp` (never chat or git) to
   `/etc/arise/secrets/youtube/client_secret.json`, then
   `sudo chown arise-yt: … && sudo chmod 600 …`.
4. **Sign in once**: `sudo arisectl automator signin`. It runs the handoff's
   `authorize_headless.py` as arise-yt. Open the link on any computer or phone,
   sign in as the channel's owner, pass the unverified-app warning (Advanced →
   Go to …), approve, then paste the whole `http://localhost:8765/?state=…&code=…`
   address the browser fails to load. The script checks the channel is Arise
   Church before writing the token (0600) and never prints it.
5. **The first check**: `sudo arisectl automator preview` (it asks, because the
   reads spend quota), then `arisectl automator report`. Expected:
   `this machine: ariseOS · designated runner: pc`, "plan-only… continuing",
   `signed in as Arise Church`, a budget of 4000 (2000 on a Pacific Sunday or
   Monday), **the same hold count as the PC's LATEST_REPORT.md**, and each
   enabled job's dry run.

## The timer

`arise-automator.timer`: 02:05 America/Chicago, five minutes after Google's
quota day resets (midnight Pacific). **`Persistent=false` on purpose**: a night
missed to a power cut must not fire at 10 AM on a Sunday and eat the quota
Bradly needs for that day's service. The wrapper pulls `origin/main` just
before running, so a hold Bradly pushes in the evening applies that night; if
the pull fails it runs plan-only, because stale holds must never drive writes.
A lock stops two runs at once. `last-run.log` rotates monthly.

## The quota

One project, 10,000 units a day, shared by the PC's token, the server's and
Bradly's chat sessions on Sunday and Monday. The 02:05 run spends from the same
quota day as that day's service work. Caps per machine are in `runner.json`:
the PC 10,000; ariseOS 4,000, and 2,000 on a Pacific Sunday or Monday. A job
whose estimate does not fit (with a 300-unit reserve) is not started. The
ledger books estimates; the true figure is in Cloud Console → YouTube Data API
v3 → Quotas.

What that means for tonight's worklist (Oct 28), on the server's cap:

| Job | Enabled | Books | Fits under 4,000? | Under 2,000 (Sun/Mon)? |
|---|---|---|---|---|
| sunday-playlist-reassign | yes | 3,500 | alone, then nothing else fits | no, skipped |
| vertical-twin-titles | yes | 400 | only if the first is off | yes |
| pull-transcripts | yes | 2,500 | only if the first is off | no |
| strip-markdown-stars | yes | 2,000 | no, after the two above | no |

**Bradly decides** whether `sunday-playlist-reassign` (its work is done: last
night added 0, already there 109) is set `"enabled": false` on the PC.

## Cutover

`sudo arisectl automator cutover` (and the Automator app) shows the handoff's
section 9 list, ticking what the server can see:

1. The OAuth app is Published. *(Bradly confirms.)*
2. The server's own client and token are here, 0600, arise-yt.
3. The timer has written a "not the runner" report.
4. A plan-only run shows "signed in as Arise Church" and the hold count.
5. The in-checkout state files question is answered. **As of Oct 28 all four
   are tracked in git**: `_starfix_state.json`, `_tx_run.json`,
   `_retitle_report.txt`, `_ss_fix_report.txt`, and 162 files in
   `transcripts/`. Once the server writes to one, the PC's next push to it
   makes the server's fast-forward fail, and that night runs plan-only. Safe,
   but the night is lost. Untracking them is Bradly's call, on the PC; ariseOS
   never untracks anything on `main`.
6. `sunday-playlist-reassign` is decided.
7. The PC's `_starfix_state.json` is copied into the server's checkout, so the
   star cleanup resumes where the PC stopped.
8. The PC is clean and pushed (`origin/main` has the latest holds and worklist).

**The switch**, by day and not on a Sunday or Monday: on the PC set
`"runner": "ariseOS"` in `automator/runner.json`, commit, push. The PC's
Windows task can stay on: from then on it writes a "not the runner" report
nightly, a heartbeat. **Rollback**: `"runner": "pc"`, commit, push.

**From the switch on, holds and worklist changes must be pushed to count.** A
hold added on the PC but not pushed before 02:00 does not reach that night's
run. The PC read its own file; the server sees only GitHub.

**The morning after**: the server's LATEST_REPORT.md is dated today 02:05, says
`this machine: ariseOS · designated runner: ariseOS`, `signed in as Arise
Church`, `0 failed`; `last-run.log` shows `repo at <sha>` matching the PC's
push and no WARNING; the PC's report says "not the runner"; the Cloud quota
graph shows one run; `token.json` was modified overnight and is still 0600;
`git status` on the server is clean; one changed video looks right.

## If the server's token leaks (the handoff's section 10)

1. Cloud Console → Credentials → the **ariseOS server** client → delete it (or
   disable its secret). The PC uses a different client and is untouched.
2. Revoke the token itself, on the server, without printing it:
   ```
   sudo -u arise-yt /opt/arise/venv/bin/python -c "import json,urllib.request,urllib.parse;t=json.load(open('/etc/arise/secrets/youtube/token.json'))['refresh_token'];urllib.request.urlopen('https://oauth2.googleapis.com/revoke',urllib.parse.urlencode({'token':t}).encode())"
   ```
   (The handoff notes it is not confirmed whether this kills one token or the
   client's whole grant; with separate clients only the server is affected.)
3. **Do not** use myaccount.google.com → Third-party connections → Remove
   access: it lists the app, not the machine, and would sign the PC out too.
4. A new Desktop client, its JSON into `/etc/arise/secrets/youtube/`,
   `sudo arisectl automator signin --force`, then a preview.
5. Check YouTube Studio and the quota graph for anything the token did.

Routine rotation is steps 1, 4 and 5.

## Whisper transcripts (round 4, 100: planned, not built)

The handoff's section 11 is the contract: write
`transcripts/<videoId>.json` in the checkout as
`{"segments": [{"start": 12.34, "dur": 4.10, "text": "…"}], "source": "whisper (<model>)"}`,
seconds as floats, no `.nocaptions` or `.failed` markers. The caption puller
skips a video that already has a file, so captions stay the fallback. There is
no automated chapter step. Whisper output is evidence, never authority: no
names from it decide who spoke, and sung words are never copied. **Open
question for Bradly**: where the recordings come from (the API cannot download
the channel's video; StreamYard or a local capture).

## Open items for Bradly (the handoff's section 12, plus what ariseOS found)

- Publish the OAuth app; create the "ariseOS server" client.
- Add the server's read-only deploy key on GitHub.
- The four tracked state files and `transcripts/` (Cutover, item 5).
- `sunday-playlist-reassign`.
- The recording source for Whisper.
- Later, maybe: the server pushing reports and transcripts to a `server-out`
  branch (a separate write key; never `main`).

## Commands

```
sudo arisectl automator setup        make the server ready (idempotent)
sudo arisectl automator signin       sign the server in to YouTube (once; --force to replace)
sudo arisectl automator preview      a plan-only run through its unit (asks: reads spend quota)
arisectl automator status            runner, this machine's cap today, token, holds, last run
arisectl automator report [name]     the latest report, or one by name
sudo arisectl automator cutover      the section 9 checklist
```
