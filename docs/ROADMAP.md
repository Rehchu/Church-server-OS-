# ariseOS roadmap

The order is Bradly's (round 2, question 50): Feel first, then Safety, then
Sunday, then Sermons. Releases are named after books of the Bible from here
on (question 20). Each line: what it is, what it needs from Bradly, and an
honest cost in time. "Small" is an evening, "a day" is a day, "several days"
means it should not be promised for a date.

## v0.7 "Genesis": Feel

| Item | What it is | Needs from Bradly | Cost |
|---|---|---|---|
| Boot splash | a Plymouth theme: the flame on ink, a progress bar, no sound (1) | nothing | a day (testing on the real Dell is the slow part) |
| The name | ariseOS on the splash, the About window and the docs; Arise Server stays the service name (19) | nothing | small |
| Sounds | dock click, checklist chime, failure tone, all quiet, a mute in Control Center (34) | nothing | small |
| Bone theme | the website's light paper look as a Control Center switch, per browser; the monitor stays dark (36) | nothing | a day |
| About flair | the week's verse, services held, hours streamed, the latest title, from the box's data (35) | nothing | small |
| Phone app | a web app manifest so the portal installs on a home screen (9) | nothing | small |
| Push | web push to Bradly's phone for failures, stream down, a new device (10) | tap "allow" once on the phone | a day |
| Walkthrough | five steps in the portal on each person's first sign-in (45) | nothing | a day |

## v0.8 "Exodus": the everyday OS and the safety basics

Round 3 (Oct 28) asked what Windows 11 and macOS have that ariseOS does not,
and what any OS needs underneath. docs/PARITY.md is the map. Everything in
this block is built in v0.8 unless the row says otherwise.

| Item | What it is | Needs from Bradly | Cost |
|---|---|---|---|
| Trash | a Trash on every share: the Macs' deletes (Samba recycle) and the portal's land there; put back your own; emptied after 30 days (r3 1) | nothing | a day |
| Previous Versions | right-click a file in Finder, see last night's and last week's copy from the backup, put one back beside the original (r3 2) | nothing | a day |
| System Settings | one window: appearance, users, sharing, backups, updates, time, notifications, about (r3 3) | nothing | a day |
| Software Update | security automatic as now; the rest listed with a badge, installed on his click in the Saturday 03:30 window, a snapshot first (r3 4, 23, 25) | a click | a day |
| Store | the 24 templates preinstalled (heavy ones stopped, RAM shown), a catalogue of more free apps, start/stop/open (r3 5, 40) | nothing | a day |
| Activity Monitor, Logs, Automations, Storage | the four admin tools every OS has (r3 6, 7, 8, 9) | nothing | two days |
| Calendar | one church calendar on the server; an ICS feed every Mac and phone subscribes to (r3 10) | subscribe once per device | a day |
| Notes, Photos | Trilium and Immich as the Notes and Photos icons (r3 11, 12) | nothing | small |
| Weather, Calculator, Clock | the small apps (r3 13, 14) | nothing | small |
| Finder extras | text editor, Compress, Get Info, Recents, Open on my Mac, Fonts (r3 15, 16, 18, 39) | nothing | a day |
| Screen Sharing | the closet monitor through Guacamole, Bradly only (r3 17) | nothing | small |
| Snap windows, accessibility | tiling, larger text, reduce motion, high contrast, keyboard (r3 19, 32) | nothing | small |
| Power menu, monitor sleep | Restart and Shut Down in the flame menu; the panel off 23:00 to 06:00 (r3 30, 31) | nothing | small |
| Help, What's New, password meter | the docs in the dashboard, the note after an update, the rules at a change (r3 34, 35, 36) | nothing | a day |
| 2FA | optional, per person; Microsoft Authenticator when they opt in (r2 11, Oct 28) | scan a QR code, if they want it | a day |
| Break-glass admin | `arise-rescue` for when the domain is down; console and SSH only; logged and pushed (r3 21) | keep the closet card in the safe | small |
| Encryption | LUKS chosen at the Ubuntu install; `arisectl encrypt tpm` binds it to the TPM; the passphrase on the closet card (r3 22) | pick "encrypt" in the Ubuntu installer | small, a day to test |
| Rollback, reinstall | a system snapshot before each update; `arisectl reinstall` from the Synology (r3 23, 24) | nothing | a day |
| Virus scan | ClamAV Sunday night, quarantine, a report, a push (r3 28) | nothing | small |
| Church CA | Caddy's internal CA in front of the dashboard; enroll-mac.sh trusts it (r3 29) | nothing | small |
| Audit log | who signed in, shared, changed a user, ticked the checklist; a year kept; admins read it (r2 23) | nothing | a day |
| Offboarding | a "leaving" button in Directory: 30 days of grace, then disable; a "move files to" picker (r2 24) | nothing | a day |
| Decided, nothing built | no lockout (r3 27), manual theme (33), hot corners (20), browsers never sign out (38), logs kept a year (26), MIT (37) | | |

## v0.9 "Leviticus": Sunday

| Item | What it is | Needs from Bradly | Cost |
|---|---|---|---|
| House Lights Down mode | from an hour before a service the desktop dims the admin noise and shows the stream, the checklist, the countdown and one-tap doors; off after; automatic by the clock (3) | nothing | a day |
| Stream watch | Uptime Kuma pings the YouTube live page and StreamYard every 30 s on service days; push, Discord and a red monitor if it drops (44) | the YouTube live URL stays the same | a day |
| Discord | a webhook: failures, and the Sunday "all green" (40) | a webhook URL from Discord | small |
| Checklist sounds | the chime when the Sunday list completes (34) | nothing | small |
| YouTube Partner widget | subscribers toward 1,000 and watch hours toward 4,000 from the automator's numbers, desktop only (2) | nothing | small |

## v1.0 "Numbers": Sermons

| Item | What it is | Needs from Bradly | Cost |
|---|---|---|---|
| Podcast feed | ffmpeg pulls audio from each new recording, an RSS feed Spotify and Apple read, the 16:9 art; episodes automatic, each title approved (4, 42) | submit the feed once to Spotify and Apple | several days |
| Transcript pages | a cleaned, searchable, printable page per sermon for admins and staff, no sung words (15) | nothing | a day |
| Thumbnails on the server | pick a frame in Sermons; the house layout in YouTube and Spotify sizes; approve before anything is set (42) | the house fonts on the box (Anton, Oswald) | several days |
| Channel page | views this week, top video, Shorts count under Sermons from the automator's data, no extra quota (41) | nothing | a day |
| Holds | the hold list editable in the dashboard with a note and a name per hold; holds.json stays the source (43) | nothing | small |
| Claude's drafts | titles and descriptions drafted from the transcript and the automator's rules, shown for approval, never live on their own; a "Why?" button on any red item; a help box in the portal that reads the docs (17) | sign in to Claude on the box | several days |
| Morning report | 06:00, the box's own data, in the dashboard only (7, 18) | nothing | a day |

## Later, when the thing it needs arrives

| Item | What it is | Needs | Cost |
|---|---|---|---|
| Time Machine | a Time Machine share on the Synology for every church Mac (5) | Synology space about equal to each Mac's used disk (estimate) | a day |
| Printing | CUPS with AirPrint so every Mac and phone prints to the office printer behind router B (6, 26) | the printer's brand and model | small to a day, by the driver |
| Syncthing mirrors | three pairs: Proclaim assets, the thumbnails folder, the office documents share (25) | nothing | small each |
| Second domain controller | an installer mode that joins an old PC at Alexandria or the Hub as a second DC (31) | an old PC | several days |
| Pineville's VPN after the move | Tailscale on each church Mac or a route box; decided at the move (30) | the Hub's date (29: none yet) | small either way |
| Jellyfin for families | staff only for now (13); open to families when asked | a decision | small |

## Not being built, by his answers

A clip cutter (8), a website feed from the server (16), guest accounts (21),
kids check-in (27), a volunteer rota (28), SMS (38), member self-service on
the mail list (39), any hardware purchase for now (32).
