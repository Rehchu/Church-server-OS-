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

## v0.8 "Exodus": the everyday OS and the safety basics. Built Oct 28

Round 3 (Oct 28) asked what Windows 11 and macOS have that ariseOS does not,
and what any OS needs underneath. docs/PARITY.md is the map. Status is
against the merged code; "built" means it is in the tree and walked in sample
mode, not that it has run on the Dell.

| Item | What it is | Status |
|---|---|---|
| Trash | a Trash on every share: the Macs' deletes (Samba recycle) and the portal's land there; put back your own; emptied after 30 days (r3 1) | built (docs/FINDER.md) |
| Previous Versions | right-click a file in Finder, see last night's and last week's copy from the backup, put one back beside the original (r3 2) | built |
| System Settings | one window: appearance, users, sharing, backups, updates, time, notifications, about (r3 3) | built |
| Software Update | security automatic as now; the rest listed with a badge, installed on his click in the Saturday 03:30 window, a snapshot first (r3 4, 23, 25) | built |
| Store | the core five preinstalled (Oct 30, the OptiPlex 3010; every other template one click away), within the memory budget (RAM shown), a catalogue of 35 more free apps, start/stop/open, a cap on every app (r3 5, 40) | built (docs/STORE.md) |
| Activity Monitor, Logs, Automations, Storage | the four admin tools every OS has (r3 6, 7, 8, 9) | built (docs/SYSTEM-APPS.md) |
| Calendar | one church calendar on the server; an ICS feed every Mac and phone subscribes to (r3 10) | built (docs/EVERYDAY.md) |
| Notes, Photos | Trilium and Immich as the Notes and Photos icons, for admins and the Staff and Media groups (r3 11, 12) | built |
| Weather, Calculator, Clock | the small apps (r3 13, 14) | built |
| Finder extras | text editor, Compress, Get Info, Recents, Open on my Mac, Fonts (r3 15, 16, 18, 39) | built |
| Screen Sharing | the closet monitor through Guacamole, Bradly only (r3 17) | built; wayvnc against guacd unverified without the hardware |
| Snap windows, accessibility | tiling, larger text, reduce motion, high contrast, keyboard (r3 19, 32) | built |
| Power menu, monitor sleep | Restart and Shut Down in the flame menu, never during a service; the panel off 23:00 to 06:00 (r3 30, 31) | built |
| Help, What's New, password meter | the docs in the dashboard, the note after an update, the rules at a change (r3 34, 35, 36) | built |
| 2FA | optional, per person; Microsoft Authenticator when they opt in (r2 11, Oct 28) | built (docs/SECURITY.md) |
| Break-glass admin | `arise-rescue` for when the domain is down; the closet monitor only; logged and pushed (r3 21) | built |
| Encryption | LUKS chosen at the Ubuntu install; the installer or `arisectl encrypt tpm` binds it to the TPM; the passphrase on the safe card (r3 22) | built; untested on a real TPM |
| Rollback, reinstall | a system snapshot before each update; `arisectl reinstall` from the Synology (r3 23, 24) | built (docs/REINSTALL.md); the first real reinstall is a rehearsal (r4 105) |
| Virus scan | ClamAV Sunday night, quarantine, a report, a push (r3 28) | built |
| Church CA | Caddy on by default; `/ca.crt`; enroll-mac.sh trusts it (r3 29) | built |
| Asking twice | the password again for deleting a user and the power menu (r4 54) | built |
| The Dock that hides, the greeting, the lock-screen line | round 4, 12 to 19 | built |
| Audit log | who signed in, shared, changed a user, ticked the checklist; kept forever (r2 23; r4 79); admins read it | next, after this merge |
| Offboarding | a "leaving" button in Directory: 30 days of grace, then disable; a "move files to" picker; the mailbox deleted with the account (r2 24; r4 82) | next, after this merge |
| Decided, nothing built | no lockout (r3 27), manual theme (33), hot corners (20), browsers never sign out (38), logs kept a year (26), MIT (37) | done as decisions |

## v0.8.1 "Exodus, part two": round 4, the whole OS

Round 4 (Oct 28, 115 answers) covered the entirety of the OS. These are the
decisions not yet built, grouped. Costs are honest estimates.

| Item | What it is | Needs from Bradly | Cost |
|---|---|---|---|
| **The nodes** | Arise-Pineville and Arise-Home: a second domain controller, Syncthing for shares and homes both ways, the apps' data copied nightly, a full restic copy at home, automatic takeover after an hour with a fence, a Nodes page that pushes updates and runs doctor over Tailscale, node mode `home` invisible to the home network (r4 106 to 115; docs/NODES.md) | the specs of both PCs on Friday; the second PC wiped | several days |
| The staff tier | admin, staff, member by the Staff and Media groups: Photos, Notes, transcripts, calendar events, internal mail for staff (99) | nothing | a day |
| The internal mail server | Postfix + Dovecot, staff and departments, `first.last@ad.arisecenla.com`, every account may send, 100 MB attachments, forwarded out through Resend's relay to each person's own address kept on their Directory account, Reply-To the sender; no inbound from the internet (3, 5 to 7, 68, 69) | the Resend SMTP credential | several days |
| OnlyOffice from Finder | click a .docx/.xlsx/.pptx, edit in place, co-editing live, saved to the share (2, 70) | nothing | a day |
| Desktop programs' idle stop | the catalogue's GIMP, Inkscape, Krita, Kdenlive, Shotcut, LibreOffice, Audacity stop after an hour idle (1); the sweep exists, the "last used" signal from each needs wiring | nothing | small |
| The theme pack | house red, ink, the flame, Anton and Oswald on every app that takes them; the fields exist, the deeper wiring per app is next (4) | nothing | a day |
| Trash on the media share | 7 days there, 30 everywhere else (98) | nothing | small |
| Whisper transcripts | one recording a night transcribed on the box after the backup, captions as the fallback; feeds the chapters and the transcript pages (100) | nothing | a day, then a CPU night per service |
| Discord, four channels | #alerts, #sunday, #weekly, #daily through four webhooks in `/etc/arise/secrets/discord.toml` (101; docs/DISCORD.md); the Sunday live link (77), the 9:30 checklist nudge (78), the Monday weekly (37), birthdays in the weekly if the Wix field exists (94) | the four webhook URLs | a day |
| The glance view | the closet monitor idle shows the clock, the next service and the verse, nothing else; nothing clickable (102; round 5, 34: built) | nothing | done |
| Faces at sign-in | faces on the closet monitor's sign-in, nobody preselected; the administrators only, since staff use their Macs (14, 16; round 5, 31). Initials now; each person's own photo when profiles land | photos | initials done |
| Immich's library | watch Media/Photos and every staff member's Photos folder, read-only; no public share links (103, 81) | nothing | small |
| Departments as groups | each person has their own account; a department is a group with its share folder and mail; membership grants it (104) | the department list | small |
| USB import | a plugged-in drive sorted by type into the signed-in person's home, scanned, the stick untouched, a push when done (31) | nothing | a day |
| The Songs app | every song per service from the automator's credits, confirmed per service, counts, a CCLI-shaped export; numbers only from the song bank (52, 75) | nothing | a day |
| The campus kiosk image | any old PC or a Pi boots into the dashboard over Tailscale as a campus account with a badge; the Campuses app shows each campus's screen, devices and sign-ins (63, 64, 66) | an old PC per campus | a day |
| The Windows join script | one PowerShell file from the dashboard: join, drive letters, the certificate; nothing else (26, 67) | a Windows PC to test on | small |
| The install wizard | a short on-screen set of questions, flags still working (59) | nothing | a day |
| Spotlight inside documents | text inside .docx/.pdf/.txt on the shares indexed nightly; the calendar, mail subjects, the Bible, sums (73) | nothing | a day |
| Quick Look: video and Office | video scrubbing streamed from the Synology, Office files through OnlyOffice (74) | nothing | a day |
| ariseOS updates from releases | GitHub releases checked daily, What's New shown, installed on his click in the window (53) | tag a release | small |
| The 75% disk alert, the morning report line for heat, no quiet hours | the push rules (35, 36, 38, 47) | nothing | small |
| Scans | scan-to-share when the printer can: the signed-in person's Documents, a copy to the Mac, an offer to share (87) | the printer's model | small, after CUPS |
| Jellyfin's libraries | recordings, worship, graphics loops, podcast audio from the Synology, staff only (88) | nothing | small |
| Mail export logged | admins only, in the audit (80) | nothing | small |
| Easter eggs, the anniversary | the Konami code lights the flame, a verse typed in Spotlight, the About flame on the anniversary; only the year 2018 is known, no day is invented (83, 84) | the founding date, if there is one | small |
| The reboot rule | the Saturday reboot waits until nobody is signed in (92) | nothing | small |
| Time Machine, the Synology layout, the disk split | two backups per Mac kept; three drives one volume and one drive for the backups; the partition plan (58, 55, 91) | the Synology model and the PCs' specs on Friday | a day |
| Decided, nothing built | no prayer box (93), no hot corners, no Wake-on-LAN (41), no remote Mac screens (42), no chat server (89), Nextcloud stays stopped (90; replaced by round 6, 14: it is the sync now), Cockpit stays (34), KJV (51), Proclaim keeps the lobby TV (10), the automator keeps its PC backups and the server runs the real job (95, 96), the YouTube token question is with the automator chat (97) | | |

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
| Second domain controller | an installer mode that joins an old PC at Alexandria or the Hub as a second DC (31); now part of the node work, docs/NODES.md | the second PC (round 4) | several days |
| Pineville's VPN after the move | Tailscale on each church Mac or a route box; decided at the move (30) | the Hub's date (29: none yet) | small either way |
| Jellyfin for families | staff only for now (13); open to families when asked | a decision | small |

## Not being built, by his answers

A clip cutter (8), a website feed from the server (16), guest accounts (21),
kids check-in (27), a volunteer rota (28), SMS (38), member self-service on
the mail list (39), any hardware purchase for now (32).
