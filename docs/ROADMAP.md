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

## v0.8 "Exodus": Safety

| Item | What it is | Needs from Bradly | Cost |
|---|---|---|---|
| 2FA | Optional, per person (Bradly, Oct 28): anyone may turn two-step on from the flame menu; when they do, Microsoft Authenticator scans the code (TOTP, no Microsoft account needed). Nobody is forced; an admin can see who has it on | scan a QR code once, if they want it | a day |
| Audit log | who signed in, shared, changed a user, ticked the checklist; a year kept; admins read it; nothing deletable from the dashboard (23) | nothing | a day |
| Offboarding | a "leaving" button in Directory: 30 days of grace, then disable; a "move files to" picker (24) | nothing | a day |
| Restore drill | monthly, automatic: one random file restored from last night's backup to a scratch folder and compared (47) | nothing | small |
| Closet card | a one-page PDF the installer writes to the shares: the commands, the Tailscale address, the backups, who to call (46) | who to call | small |
| UPS | nut with the UPS, shutdown on the low-battery signal, not a timer (48) | the UPS model and a USB cable from it to the server | small once the model is known |

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
