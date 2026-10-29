# The automator on the server

The Arise YouTube nightly job (`automator/arise_daily.py` in
`Rehchu/arise-youtube-automation`) moves from the church PC to ariseOS. The
session that maintains the automator wrote the brief for it:
**SERVER_HANDOFF.md** in that repo, commit "Server-ready automator"
(8326b4a, Oct 28 2026), revised the same day after ariseOS's build report with
Bradly's decisions (commit "Per-machine job state, server cap 6,000"). The
revision accepts ariseOS's placements below. This page is how ariseOS carries
it out. Where this page and the handoff disagree on the automator's own rules,
**the handoff wins**.

> **As of Oct 28, evening: the revision commit is not on GitHub yet.** `main` is
> still at 8326b4a, so the repo still says 4,000 (2,000 Sun/Mon), still has
> `sunday-playlist-reassign` enabled and still tracks the four state files.
> ariseOS reads all three from the repo at run time, so nothing on the server
> changes when it lands: **push it from the PC** and the next pull carries it.

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
| The user | `arise` | **Bradly's own account** (`[owner] user` in arise.toml; Oct 28: "the Automator doesn't need its own profile, it can run on mine") | the units get `User=` from a drop-in (`arise-automator.service.d/10-owner.conf`) that `arise-automator-setup` writes; with no drop-in the unit refuses to run as root |
| Secrets (`ARISE_TOKEN`, `ARISE_CLIENT_SECRET`) | `/etc/arise/secrets/` | `/etc/arise/secrets/youtube/` (the owner, 0700; files 0600) | `/etc/arise/secrets/` also holds the backup password, two-step secrets and the rescue password; the job cannot read them |
| State (`ARISE_STATE_DIR`) | `/var/lib/arise` | `/var/lib/arise/automator` (the owner) | `/var/lib/arise` holds the audit log and the dashboard's state |
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
git -C /srv/arise/automator/ARISE_YouTube_Updater status
```

## The Automator app (the dashboard)

The app on the desktop has eight tabs. Everything in the first two is read-only:
nothing there spends quota, writes to YouTube or touches the token.

| Tab | What |
|---|---|
| **Videos** | Every video the channel snapshots and the archive know (about 1,380 at the Oct 28 inventory), newest first, each with its YouTube thumbnail. Filter by title or id, by Services / Shorts / Other, or to the ones with a transcript, with chapters, or on the hold list. |
| **Search** | Searches the sermon transcripts (the default), descriptions, chapters, songs, set lists and notes, or everything. Results are grouped by video: thumbnail, title, date, YouTube and Studio links, and each hit with its time. Clicking a time opens the video with the transcript at that moment. A CCLI number shows its song_bank.json entry. "Past versions" adds the `_backup` files; "private folders" (emails/, memory/) is there for Bradly only. |
| **Songs** | Every song in song_bank.json (139 at the Oct 28 inventory), searchable by title, CCLI number, writer or **a line of the lyrics**. Filter to the ones with lyrics, without, or the originals. Each song shows its credits as song_bank.json writes them (with Copy on the credit line), every service it was sung at (from the set lists, and from descriptions that credit its number), and its lyrics. |
| Latest report, Worklist, Hold list, Past reports | as before |
| **Server switch** | Who runs the 02:05 job tonight (the PC, until runner.json says otherwise) and the handoff's section 9 checklist, row by row. |

**A video's card** (open one from either tab):

- **Thumbnails.** YouTube's current one (full-size link), plus every thumbnail the toolkit made: files named after the video id, and `THUMB_<date>_…` / podcast / Spotify art made for the service date. Each opens full size or downloads. A Short shows only files named after itself.
- **Links.** Watch on YouTube, Open in Studio (`studio.youtube.com/video/<id>/edit`), Copy link, and on a Short, the full service it came from.
- **Chapters** from the description, each one a jump into the transcript and a ▶ link to YouTube at that second.
- **Songs** exactly as the description credits them, and the set list for that date when there is one. Nothing is looked up or added: credits come only from song_bank.json.
- **Shorts from this service** (the Shorts whose description links to it).
- **Description**: every version (the channel snapshot, the toolkit's description files, the applied text, past versions marked as such), with **Copy** and **Copy clean** (no `**`, no CCLI numbers: the text for StreamYard, CLAUDE.md Oct 5).
- **Transcript**: the timed text with each line linked to that second on YouTube, a find box, and a choice of source when there are several. The note above it says what the archive's rule says: transcripts hold sung lyrics, which never go into a title, description or Short.
- **In the archive**: every file that names the video, each one readable in place.

**Lyrics** (Oct 28: "I'd have to add the lyrics most likely from Proclaim"):

- **Paste** into a song: open it in the Songs tab and paste from Proclaim's song
  editor (or SongSelect), section names (Verse 1, Chorus) on their own lines.
  Edit any time; every earlier version is kept.
- **Import files**, many at once: SongSelect's `.txt` and `.usr` downloads,
  ChordPro (`.cho`, `.chopro`, `.pro`; chords are stripped), or plain text.
  A file links to its song by the CCLI number in it, else by a title exactly
  one song has. Two songs that share a title (Holy Ground, Dry Bones, You Are
  Good, Kadosh) are never guessed between: the file is kept, not linked, and
  you paste it into the right one. A file whose number is not in song_bank.json
  is kept too, marked "not in song_bank.json", until the PC adds the song.
- Proclaim has no lyrics export that this could read; paste is the way from it.
- **Where they live:** `/srv/arise/songs/lyrics/<CCLI number>.txt` (or
  `t-<title>.txt` for a song with no number), with `.versions/` and `.removed/`
  beside it: removing asks for the title and moves the file, nothing is deleted.
  The folder is yours (the owner's account), so Claude on the box can work with
  it too; the nightly backup job `songs` copies it to the Synology. It is never
  in a git repository: these are the church's licensed copies (CCLI No. 245091),
  and they never go into a title, description or Short.
- **Find a line in the transcripts** (on a song) searches the sermon
  transcripts for that line, to see where it was sung. That is a lead for you to
  check, never a credit: credits come only from song_bank.json.

Where the data comes from: the archive's index and its clone of the automator repo
(docs/ARCHIVE.md), so it is as fresh as the 04:15 refresh. Titles and descriptions
come from the channel snapshots the PC writes (`cloud_workspace/_all_vids.json`,
`_channel_index.json`, `channel_descriptions.json`, `channel_inventory.csv`) and
can be older than YouTube. The card asks YouTube's public oEmbed for the title as
it is now (no key, no quota; cached a week in `/var/lib/arise/channel/oembed.json`)
and shows it when it differs. A date in the title ("Glory Night October 19, 2026")
wins over the snapshot's, because a stream is often scheduled a week ahead.

The tabs are the administrator's. Spotlight's sermon-transcript results open the
Search tab for an administrator, and the Sermons app for members as before.

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
   - APIs & Services → OAuth consent screen → **Audience**: it stays in
     **Testing**, on purpose (Bradly, Oct 29). Refresh tokens then die 7 days
     after they are given, so the server's sign-in is renewed each week
     (Weekly sign-in, below). Bradly's account must be on the Test users list.
   - Credentials → Create credentials → OAuth client ID → **Desktop app**,
     named **ariseOS server**. Download the JSON.
3. Copy it in with `scp` (never chat or git) to
   `/etc/arise/secrets/youtube/client_secret.json`, then
   `sudo chown $USER: … && sudo chmod 600 …` (your account).
4. **Sign in once**: `sudo arisectl automator signin`. It runs the handoff's
   `authorize_headless.py` as your account. Open the link on any computer or phone,
   sign in as the channel's owner, pass the unverified-app warning (Advanced →
   Go to …), approve, then paste the whole `http://localhost:8765/?state=…&code=…`
   address the browser fails to load. The script checks the channel is Arise
   Church before writing the token (0600) and never prints it.
5. **The first check**: `sudo arisectl automator preview` (it asks, because the
   reads spend quota), then `arisectl automator report`. Expected:
   `this machine: ariseOS · designated runner: pc`, "plan-only… continuing",
   `signed in as Arise Church`, a budget of 6000, **the same hold count as
   the PC's LATEST_REPORT.md** (8 on hold, 6 standing rules), and each enabled
   job's dry run.

## Weekly sign-in (Testing mode)

Bradly keeps the OAuth app in Testing (Oct 29), so Google ends a sign-in seven
days after it is given. He renews the PC's every Sunday; the server's is renewed
the same day, the same way, in the dashboard. The server uses its own "ariseOS
server" client; the PC's token never comes to the server, and no token ever goes
through a chat, a log, git or the dashboard's answers.

**Where: the Media Mac.** It is the Mac signed in to the channel's Google account
(Bradly, Oct 29), so the whole renewal runs in one browser there:

1. On the Media Mac, open `https://arise-server.ad.arisecenla.com` in Safari and
   sign in to the dashboard as yourself.
2. **Automator → Sign-in → Renew for the week.** It asks for your password again.
3. **Open Google's sign-in.** It opens in a new tab of the same browser. Choose
   the **Arise Church** channel, then Advanced → Go to … (the church's own app),
   then Allow.
4. Google sends that tab to `http://localhost:8765/?state=…&code=…`, which
   **fails to load**. That is expected. Copy the whole address (click the address
   bar, ⌘A, ⌘C), close the tab, paste it into the dashboard (⌘V), press **Renew**.
5. The server checks the address came from this very attempt, swaps the code for
   a sign-in, asks YouTube once (1 quota unit) that it is Arise Church
   (`UCGS9j7B_prcJkbTNgzlGrKg`), and only then writes `token.json` (0600, your
   account) for the 02:05 job. The answer says when the sign-in now ends.

**The shared Mac.** A dashboard sign-in lasts a year, and the Media Mac is shared,
so the box **"Sign me out of this browser when done"** is ticked: once the renewal
works, that browser is signed out of the dashboard. Only that browser: your phone
and the closet stay signed in. Untick it to stay signed in; the success screen
also has a **Sign me out of this browser** button. On the closet monitor it never
signs out.

**Rules.** The link works ten minutes and once. A pasted address from another
attempt, an old link, an account with no refresh token or the wrong channel is
refused and nothing is written. Never during a service: the Media Mac streams, so
Renew is refused while a service is on. The audit log says "renewed, expires …"
and nothing more. The PKCE verifier and the state wait in
`/var/lib/arise/ytauth-pending.json` (root, 0600) for ten minutes; the renewal
date is in `/var/lib/arise/ytauth.json` (the job rewrites `token.json` every night,
so its date says nothing about when Google gave the sign-in).

**Reminders.** When the sign-in ends within 30 hours: a Discord #alerts line and a
push on **Saturday evening** (19:00) and again **Sunday after the service** (from
12:00, never during one), once each a week: "Renew from the Media Mac: Automator →
Sign-in". Needs You (and so the morning note) says when it ends, and once it has
ended: "the YouTube sign-in expired on …; renew it from the Media Mac". The job
itself already fails safe on an expired sign-in; nothing about it changed.

**From a terminal:** `sudo arisectl automator renew` prints the same link and reads
the pasted address (the token is never printed). `sudo arisectl automator signin`
(the handoff's own `authorize_headless.py`) still works and starts the weekly
clock too. `[automator] oauth_testing = false` in arise.toml turns the weekly clock
off if the app is ever published.

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
the PC 10,000; **ariseOS 6,000 every day** (Bradly, Oct 28; weekday keys still
work if he wants them later). A job whose estimate does not fit (with a
300-unit reserve) is not started. The ledger books estimates; the true figure
is in Cloud Console → YouTube Data API v3 → Quotas.

`sunday-playlist-reassign` is **parked** (Bradly, Oct 28: its work was done and
it booked 3,500 a night). With it parked, tonight's enabled jobs fit inside
6,000: preflight 1, then `vertical-twin-titles` 400, `pull-transcripts` 2,500
and `strip-markdown-stars` 2,000, each passing the reserve. That leaves at least
4,000 for Sunday and Monday chat work, which uses about 1,000 to 1,500 on a
service day.

## Cutover

`sudo arisectl automator cutover` (and the Automator app) shows the handoff's
section 9 list, ticking what the server can see:

1. The OAuth app stays in Testing (Oct 29); the server's sign-in has been renewed this week (Automator → Sign-in).
2. The server's own client and token are here, 0600, your account.
3. The timer has written a "not the runner" report.
4. A plan-only run shows "signed in as Arise Church" and the hold count.
5. The job's state files. **Decided Oct 28**: `_starfix_state.json`,
   `_tx_run.json`, `_retitle_report.txt` and `_ss_fix_report.txt` move to
   `ARISE_STATE_DIR` through `arise_paths.job_state()` and are untracked on
   `main`. When the server pulls that commit, git deletes its unmodified
   checkout copies; that is expected. The check turns green when the pulled
   repo no longer tracks them.
6. `sunday-playlist-reassign` is parked; the server's cap is 6,000 (decided
   Oct 28). A server plan-only report shows budget 6000 and the three
   remaining jobs planned.
7. The PC's `_starfix_state.json` is copied into **`/var/lib/arise/automator`**
   (the state folder, not the checkout), owned by your account, so the star
   cleanup resumes where the PC stopped.
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

## `transcripts/` and a blocked pull

`transcripts/` stays tracked (162 files): the PC uses it too. The server never
pushes, so a transcript it writes (Whisper, later) stays untracked in its
checkout. If the PC then commits a transcript for the same video, the
server's fast-forward stops with "untracked working tree files would be
overwritten" and that night runs plan-only. The cutover check and the
Automator app show it (item 9). `sudo arisectl automator unblock` lists the
files git named in last night's log and, after you type `move`, moves the
server's copies into `/var/lib/arise/automator/displaced/<date>/`. It never
deletes them and never touches a tracked file. The next pull goes through.

## If the server's token leaks (the handoff's section 10)

1. Cloud Console → Credentials → the **ariseOS server** client → delete it (or
   disable its secret). The PC uses a different client and is untouched.
2. Revoke the token itself, on the server, without printing it:
   ```
   /opt/arise/venv/bin/python -c "import json,urllib.request,urllib.parse;t=json.load(open('/etc/arise/secrets/youtube/token.json'))['refresh_token'];urllib.request.urlopen('https://oauth2.googleapis.com/revoke',urllib.parse.urlencode({'token':t}).encode())"
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

- Create the "ariseOS server" client (the app stays in Testing; the server's sign-in is renewed weekly from the Media Mac).
- Add the server's read-only deploy key on GitHub.
- **Push the revision commit** ("Per-machine job state, server cap 6,000")
  from the PC; GitHub's `main` is still at 8326b4a.
- The recording source for Whisper, and how its transcripts should reach the PC.
- Decided Oct 28: state files moved and untracked; `sunday-playlist-reassign`
  parked; the server's cap 6,000 every day; both repos on the server as a
  searchable archive for Claude (docs/ARCHIVE.md).
- Later, maybe: the server pushing reports and transcripts to a `server-out`
  branch (a separate write key; never `main`).

## Round 7: songs, transcripts and the channel copy

- **The Lyrics inbox** (99, 100): a *Lyrics inbox* folder in Nextcloud for
  Bradly and the worship leader (`[songs] inbox_users`; the owner always).
  Every 15 minutes (`arise-lyrics-inbox.timer`) the files dropped there go
  through the same import as the Songs tab's *Import lyrics files*
  (`songs.import_files`: SongSelect `.txt`/`.usr`, ChordPro, plain text,
  matched to song_bank.json by CCLI number, then by title). Each file then
  moves to `Imported/` (or `Not imported/` with the reason in the Songs tab).
  The lyrics land in `/srv/arise/songs/lyrics` and nowhere else: never into
  a title, a description, a Short or a log line.
- **Held videos stay out of transcript search** (105): a video in
  `holds.json` is left out of the Search tab's transcript and title hits;
  the answer says how many were held back.
- **The CCLI usage report** (106): Songs → *CCLI usage* shows this quarter;
  `arise-ccli.timer` writes `songs/reports/ccli-usage-YYYY-Qn.csv` on the
  first of January, April, July and October. From the set lists and song
  credits already in the archive: title, the CCLI number exactly as
  song_bank.json has it, times used. No lyrics. A song with no number banked
  is listed as such, never guessed; Arise originals say so.
- **The nightly channel copy** (62): `arise-channel-copy.timer` at 04:45 copies
  the automator repo's own snapshot files (already synced to
  `/srv/arise/repos`) into `/srv/arise/channel-copy/<date>/`, and each
  video's public thumbnail from `i.ytimg.com` into
  `channel-copy/thumbnails/` (up to 300 new a night). Zero quota: never the
  YouTube API. Skipped during a service.
- **The morning note explains a failed 02:05 run** (145): when the night's
  report failed, the note quotes the report's own failing lines in plain
  words, with the quota reset time when that was the cause. The note stays
  off until a webhook is set.

## Commands

```
sudo arisectl automator setup        make the server ready (idempotent)
sudo arisectl automator signin       sign the server in to YouTube (once; --force to replace)
sudo arisectl automator preview      a plan-only run through its unit (asks: reads spend quota)
arisectl automator status            runner, this machine's cap today, token, holds, last run
arisectl automator report [name]     the latest report, or one by name
sudo arisectl automator cutover      the section 9 checklist
```
