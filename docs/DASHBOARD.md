# The dashboard — `http://arise-server:4147`

A macOS-style desktop in the browser, in the church's own look: a menu bar
with real menus across the top, a Finder, windows you drag and resize, a
floating dock along the bottom, Spotlight, Mission Control, a widgets panel and
a launchpad with every app. Served by `arise-web.service` from `web/`; it talks to the JSON API
in `server/arise_server/`. Plain HTML, CSS and JS; no build step.

The look is the website's "House Lights Down" theatre: ink and Arise red,
Anton and Oswald, the two red dashes before a kicker, numbered rooms (every
app carries its folio: 01 Finder … 31 Security), a red footlight along the
diagonal cut at the bottom of the wallpaper.

## The parts

It is laid out like a Mac, because that is what the church's computers are,
and it is what the closet monitor shows all day with `install.sh --kiosk`
(docs/CONSOLE.md).

| Part | What it does |
|---|---|
| **Menu bar** | the flame menu (About This Server, System Settings, Change Password, **Two-step sign-in…**, **Security**, Launchpad, Run backups now, Preview tonight's automator, Lock Screen, Sign Out, and the **Power** group: Restart the dashboard, Restart the domain, Restart…, Shut Down…); the focused app's name and its menus (**File · View · Window · Help**, each app its own); a red *needs you* count; who is online; backup and VPN state; live CPU, RAM, uptime; the live/sample dot; Spotlight; Control Center; the clock, which opens the widgets panel |
| **Finder** (01) | the first window on every desktop. Sidebar: Favorites (Home folders, Shares, Media, Automator, Apps, Backups), Locations (the server, the Synology), Tags. Icon or list view, back/forward, breadcrumbs, filter, Upload, New Folder. Click to select, double-click to open, **Space** for Quick Look (images, text, Markdown, JSON, PDF, video, audio), **⌘I** for Get Info, right-click for Open · Quick Look · Download · Get Info · Previous Versions… · Compress · Share Link… · Move to Trash · Copy path · Copy `smb://` address. Since v0.8 a delete is a move to the share's Trash (30 days), a `.txt` or `.md` opens in an editor, and a Mac gets an *Open on my Mac* button; docs/FINDER.md |
| **Desktop** | volume icons on the right (the server, the Synology; double-click opens Finder there); widgets on the left; right-click the wallpaper for New Finder window, Show widgets, Mission Control, Launchpad |
| **Widgets** | on the desktop and in the panel behind the clock: *Needs you* (or *All clear*), live CPU and memory with a sparkline, *The box* (directory, automator, quota, backups, Synology, what runs next), *This week* (service times), the month, the latest sermon |
| **Windows** | title bar with the folio and the app name, three dots (close, minimise, zoom), drag by the bar, resize from the corner, double-click the bar to zoom; new windows cascade. On a phone every window is full screen |
| **Dock** | hides below the bottom edge (round 4, 12); the mouse at the edge or an opening app brings it back; a switch in Control Center keeps it visible. Default admin set: Finder, Overview, Sunday, Sermons, Calendar, Mail, Store, Settings, Terminal; members: Finder, Sermons, Bible, Sunday, Calendar, Assistants, Help. Right-click an icon to keep or remove it (per browser). Icons grow under the pointer, bounce while an app opens, carry a dot while it runs; the last icon is the launchpad. On a phone it becomes a bottom bar you can scroll |
| **Launchpad** | every app with its folio and a one-line purpose; type to filter; right-click to keep one in the Dock; Escape closes |
| **Spotlight** (⌘Space) | one box for everything: apps, actions (run backups, preview tonight, lock), people and computers from the directory, files by name on the server and the Synology, and a Bible reference (`John 3:16`) read straight away. Arrows and Enter |
| **Mission Control** (F3) | every open window laid out small; click one to go to it, Escape to leave |
| **⌘Tab** | the app switcher, newest first; hold and tap |
| **Control Center** | VPN and backup state at a glance, Back up now, Preview tonight, Mission Control, Lock screen, System Settings; the switches: House Lights Down / Bone, Sounds, Push, Dock hides, **Larger text**, **Reduce motion**, **High contrast**; Show me around |
| **Lock screen** (⌃⌘Q) | the time, the date, the flame, your name, the password, and the line *Arise Church · Pineville · next: the next service*. On the closet monitor it locks itself after ten idle minutes |
| **Login** | the flame, the user, the password, the same next-service line; it tells you the command when no password is set yet. When two-step is on for that person, a second step asks for the six digits from Microsoft Authenticator (three wrong codes and you start over). After sign-in, a three-second *Good morning, Bradly. Today: Romans 8:28* toast (not on the kiosk) |

Keyboard, when a window is focused: **⌘W** close · **⌘M** minimise ·
**⌘R** reload the window · **⇧⌘N** new
folder (Finder) · **⌘I** Get Info (Finder) · **F1** Help · **⌘/** the
shortcut sheet · **⌘ + arrows** snap the window to a half, a quarter or
the whole screen (dragging to an edge does the same, with a ghost) · **F4**
Launchpad · **Escape** closes whatever is on top. Tab reaches every control
and the arrow keys move inside menus.

## The apps

| # | App | What it shows | What it can do |
|---|---|---|---|
| 01 | **Finder** | the server's data root and the Synology, folder by folder, with Quick Look and Get Info; the SMB shares under Shares; **Recents** (this week) and **Trash** in the sidebar; for an administrator the **Everyone** views (All Documents, All Photos, All Videos, All Music, All Downloads: every person's folder of that name side by side, owner labelled; a member never sees another person's folder) | upload (to 10 GB, resumable), new folder, download, **Compress** (a folder as a zip, to 2 GB), **Get Info** (size, owner, dates, the SMB path, who can open it), **Previous Versions…** (last night's and older copies from the backup, restored beside the original as `name (restored date)`), edit a `.txt`/`.md`/`.csv`/`.json`/`.yaml`/`.toml`/`.log` in place (⌘S; Markdown preview), **Move to Trash** (30 days; Put Back; Empty is the administrator's with the share's name typed), **Open on my Mac**, share links that live until removed. No move |
| 02 | **Overview** | the "Needs you" list, live stats, directory / automator / backup cards, disks, tonight's timetable | links into the others |
| 03 | **Directory** | domain health (LDAP, Kerberos, DNS), users, groups, joined computers, the SMB shares | add a user, reset a password, enable/disable, delete (type the name), new group, add a member, new share, remove a share (files stay) |
| 04 | **Backups** | repository size, last run per job, full history with the reason for every failure, snapshots, restore instructions | run a job now, `restic check`, refresh the GitHub mirror |
| 05 | **Automator** | last run, quota today, token state, holds and rules, the latest report, the worklist, past reports | preview tonight (dry run), run now (confirmed) |
| 06 | **Sermons** | the channel from the automator's inventory, no quota spent: Sunday services, Glory Nights, Shorts, conferences, with thumbnails, playlists, the live page | open on YouTube or in Studio |
| 07 | **Bible** | a passage from bible-api.com (World English Bible, KJV and others; no key), verse numbers in the website's style, quick chips | copy, open on arisecenla.church's Bible Search |
| 08 | **Store** | two tabs. *Installed*: every template deployed at install, running or stopped, each with its memory cap and address, and a memory gauge (the running apps' caps against the box's RAM minus 2 GB kept for the domain and the dashboard). *Catalogue*: `catalog/catalog.yaml`, 35 more free apps by category with an honest memory cost, including the desktop programs that open in a browser window (GIMP, Inkscape, Krita, Kdenlive, Shotcut, LibreOffice, Audacity; they stop themselves after an hour idle), OnlyOffice, a *Game night* entry and a Proclaim-under-Wine experiment, both off by default. Each card says what of the house look the app takes. docs/STORE.md | install, start, stop, open (in a window, pop out to a tab), autostart on/off, logs, remove (the name typed; the data folder stays) |
| 09 | **Remote** | SSH state, Tailscale devices, WireGuard peers, Guacamole, and a plain "how to reach it from Alexandria, the Hub or home" | add a WireGuard peer and get its config |
| 10 | **Campuses** | Pineville, Alexandria, the Apostolic Hub: reachability, network, which joined computers sit at which site | read only |
| 11 | **Terminal** | a real shell on the server (xterm.js over a websocket) | everything `arisectl` does, and everything else. Treat it like root |
| 12 | **Synology** | mount state, free space, DSM health and RAID when `dsm_url` is set, off-site copy | mount, unmount |
| 13 | **Services** | the systemd units that matter | start, stop, restart, jump to logs |
| 14 | **Logs** | the journal by unit, grouped (arise-*, samba-ad-dc, docker, sshd, each app); the files under `/var/log/arise`; 100, 300 or 1000 lines; a search box with highlighting; the last error line marked and jumped to | pick, search, Copy, *Copy for Claude* (the unit, the last error and the lines, as a prompt) |
| 15 | **System Settings** | one window, a sidebar of sections: Appearance (theme, sounds, accessibility, as the browser has them), Users, Sharing, Backups (schedule, 30/12/24 kept, the repository), Software Update, Time (America/Chicago, the services, the timers), Notifications (push on/off and who; whether a Discord webhook is set, never the URL), About. Values from `arise.toml` are shown read-only with the file to edit named | open the app each section belongs to; the safe writes that already have a route |
| 16 | **Network** | everything on the switch: every device on Netgear A's wire with address, MAC, maker, a guessed kind, whether it is joined to the domain, first and last seen; the office Netgear and the Google Mesh appear as one device each (their networks are behind them). An hourly scan by itself (`arise-devices.timer`); new devices are flagged. Below the list, *Behind the other routers*: what the office Netgear reports as attached, read from the router with its admin password (`[[routers]]` in arise.toml), never written; the Google Mesh says plainly that it has no such list outside the Google Home app. **Wide scan** also looks on the common address ranges an installer parks devices on and marks those *stray*; **Find cameras** asks the wire for ONVIF cameras and says whether each is reachable from this network | Scan now, name a device (the name sticks to its MAC whatever address it gets), note, kind, forget an offline one |
| 17 | **Assistants** | Claude, ChatGPT, Grok, YouTube Studio, StreamYard, each with your own account: on the monitor each opens in its own window on top of the desktop (close it to come back); in a browser, a new tab. Plus Claude Code on the box itself, in the Terminal | open; no keys stored |
| 18 | **Sunday** | the service checklist (ticks reset weekly, who ticked what), the next service with a countdown, the service times, the verse of the day, quick doors | tick, untick |
| 19 | **Mail** | the church family list and newsletters through Resend: Compose (plain text with bold, links, headings, lists; live preview in the house template; "Hi {first name}," and an unsubscribe link Resend manages), Contacts (import the Wix CSV export; dedupe and bad-address check before anything is added), Sent (every broadcast and its status) | send a test to one address, send to everyone (type `send`), import. Admin only |
| 20 | **Calendar** | the services from `[church]` (Sunday 10:30, Glory Night Monday 19:00) and the events staff add, in a month view with the next two weeks beside it; members see it too | add, edit, remove an event (admins; remove is typed); **Subscribe**: the `webcal://` address of `/calendar.ics` with the steps for a Mac and an iPhone, so every device carries the church calendar; docs/EVERYDAY.md |
| 21 | **Calculator** | sums; Spotlight answers one typed into it (`12×(3+4)`), no `eval` | copy the result |
| 22 | **Clock** | world clock (America/Chicago and two more), a timer with the house tone, a stopwatch, an alarm | |
| 23 | **Help** | the docs rendered inside the dashboard (`markdown`, raw HTML escaped), searchable; **F1** or **⌘?** opens it, **⌘/** the shortcut sheet; members see the portal guide (docs/PORTAL-GUIDE.md) only | read, search |
| 24 | **Activity Monitor** | the top 60 processes by CPU and memory (pid, user, memory, reads and writes where known) and every container's stats, refreshed every few seconds, sortable | End Process (typed), refused for PID 1, Samba, the dashboard, Docker, containerd, sshd. Admins |
| 25 | **Automations** | every `arise-*` timer: what it does in plain words, next run, last run and its result, enabled or paused; the rule *never during a service* shown | Pause and Resume (typed), Preview for the automator, Run now where a route exists (backups, mirror, drill, scan). The real automator stays refused while its timer is enabled. Admins |
| 26 | **Storage** | each mount's free space; the disk by share and by app's data folder (computed in the background, with "as of"); the 50 biggest files; a *not changed in a year* list (by modified date; last-opened is not tracked, it says so); the Trash's size | Rescan. Nothing deletes from here; links open Finder. Admins |
| 27 | **Software Update** | apt updates split into security (installed by themselves, as before) and the rest, each app's newer image after *Check apps*, whether a reboot is waiting, ariseOS's own version against the repo; a badge in the menu bar when anything waits | *Install at the window* queues it for `arise-update.timer`, Saturday 03:30, which takes a system snapshot first and refuses during a service; *Install now* (typed) does the same at once. Admins. docs/SYSTEM-APPS.md |
| 28 | **Notes** | Trilium (the template) in a window | admins and members in the Staff or Media groups |
| 29 | **Photos** | Immich (the template) in a window: the church's photo library with faces, search, albums | admins and members in the Staff or Media groups |
| 30 | **Monitor** | the closet panel: off at 23:00, on at 06:00 by timer (a key wakes it any time); Screen Sharing of that panel through Guacamole, Bradly only (wayvnc on port 5900, listening only on the address Guacamole's Docker network reaches, its password in the secrets folder) | panel on/off now, share on/off. Admins |
| 31 | **Security** | each safety basic as a green, amber or red row with the command that fixes it: the disk (LUKS, TPM-bound or not), the last virus scan and the quarantine, the church certificate, who has two-step on, `arise-rescue` and its last use, the firewall, Tailscale, updates waiting, the last snapshot | Scan now (refused during a service), put a quarantined file back (typed), *Two-step for me…*. Admins. docs/SECURITY.md |
| — | **About This Server** | version, host, domain, kernel, processor, memory, uptime, profile, this week, and **What's new** (the top of CHANGELOG.md, ten lines at most; a one-time toast when the version changes) | from the flame menu |

### v0.8 Exodus: the everyday OS and the safety basics

Round 3 and round 4 of Bradly's answers (docs/ANSWERS.md), docs/PARITY.md
for the map against Windows 11 and macOS.

- **Twelve new apps**, 20 to 31, in the table above; **Store**, **Logs** and
  **System Settings** rebuilt. Members get Calendar, Calculator, Clock and
  Help; Notes and Photos open for members in the Staff or Media groups
  (`MEMBER_APPS` and `groups` in `web/app.js`).
- **Finder** gained Trash, Previous Versions, Get Info, Recents, the text
  editor, Compress, Open on my Mac, the Everyone views, resumable uploads to
  10 GB, and links that never expire unless removed (docs/FINDER.md).
- **Weather** widget for Pineville on the desktop and in the panel, from
  Open-Meteo with no key; offline it says *No weather* rather than invent.
- **Snap windows**, **accessibility** switches, the **Dock that hides**, the
  **greeting**, the next-service line on the lock and sign-in screens
  (docs/EVERYDAY.md).
- **Two-step sign-in**, optional per person, from the flame menu: a QR code
  for Microsoft Authenticator shown once; Directory marks who has it on; the
  login asks for the six digits (docs/SECURITY.md).
- **Asking twice**: deleting a user and the power menu ask the signed-in
  person's password again, remembered five minutes, on top of typing the
  name (round 4, 54).
- **The power menu** refuses during a service and says when it ends.
- **What's New** in About after each update.
- Everything an administrator needs to look after the box without a
  terminal: Activity Monitor, Automations, Storage, Software Update, Monitor,
  Security.

### The feel (v0.7 Genesis)

- **ariseOS** is the name on the boot splash, the login, the lock screen and
  About; "Arise Server" is the project and the service. Codenames are books
  of the Bible from here on.
- **Sounds**, quiet: a click on the dock, a three-note chime when the Sunday
  checklist completes, a low tone when a red item appears. Off in Control
  Center.
- **The Bone theme**: the website's light paper look, for laptops in
  daylight. A switch in Control Center, per browser. The closet monitor
  never goes light.
- **About This Server** carries the week: the verse, the services on the
  calendar, what the channel published this week and how many hours of it,
  the latest title. All from the box's own data.
- **A phone app**: open the dashboard in Safari or Chrome and Add to Home
  Screen; it runs full screen with its own icon, and offline it says so.
- **Push** to Bradly's phone (answer 10): Control Center → Push on. A new
  red item in Needs You sends one short notification with a link; the same
  item is not repeated for six hours. Needs `pywebpush` and `py-vapid` on
  the box (in requirements); the keys are made there, root-only.
- **The walkthrough**: five steps the first time each person signs in
  (different for admins and members), and "Show me around" in Control
  Center any time.

### The screensaver and the lobby screen

After five idle minutes the closet monitor shows a screensaver: the time,
the next service and how long until it, the verse of the day, the church's
name, and the channel's thumbnails slowly behind it. Any key or touch
brings the desktop back; at ten minutes the lock screen goes on top.

The same screen is a **lobby sign**: any old Mac mini, Raspberry Pi or TV
browser opens `http://arise-server:4147/signage`, no login, and shows the
service times, the next service, the verse and the latest titles. Service
times come from `[church]` in `arise.toml`; the verse is one of a fixed
list of references, text from the Bible app's source.

## Who can sign in, and what they see

| Who | Signs in with | Sees |
|---|---|---|
| **The administrator** (`admin_user` in `arise.toml`, or anyone in `admins_group`, default *Domain Admins*) | the local dashboard password from `arisectl admin set-password`, or their directory password | everything above |
| **Any directory user** (`member_login = true`) | their domain password, the same one the Macs and the shares use | the **portal**: Finder with *My files* (their home folder, which starts with Documents, Photos, Videos, Music and Downloads) and the shares their groups allow (read-only where the share's write list leaves them out), Upload, New Folder, Quick Look, Get Info, Download, Trash, Previous Versions of their own files, **Share Link**, Sermons, Bible, Campuses, Calendar, Calculator, Clock, Help, Assistants, Sunday, Spotlight over their own places, **Change Password** (with the meter and the domain's rules in words), **Two-step sign-in**, Lock, Sign Out. Notes and Photos when they are in Staff or Media |

**Staff use their Macs (round 5, after 26).** With `[web] staff_access = "none"`,
the default, a member's sign-in gets one page, *Your files are on your Mac …
ask Bradly*, and every member API call but sign-in and sign-out is refused
(403). `"portal"` brings the row above back. The closet desktop is for the
administrators.

### Round 5 on the desktop

- **The Desktop folder** sits on the wallpaper as icons, like a Mac: the
  administrator's is `homes/<user>/Desktop`. Double-click opens, right-click
  for the menu, drag to place (remembered per person in
  `/var/lib/arise/desktop/<user>.json`), drag a Finder file onto the wallpaper
  to move it there. Every new home gets `Desktop` and a `Start here.md` note
  (`config/home/Start here.md`; Samba's `[homes]` preexec does the same).
- **Notifications**: the clock carries a red count; the Notification Centre
  lists them. Calendar reminders go 30 minutes ahead to the event's *Who's in
  it*, the Sunday checklist nudges Staff at 9:30 when items are left, each
  department list nudges its group at its own time, and anything shared with
  someone tells them. Feed in `/var/lib/arise/notifications.json`, push to the
  person's own devices, email when `[notify] email_staff = true`. Nothing is
  sent during a service. `POST /api/notifications` (admin) adds one by hand.
- **Department checklists** under the Sunday checklist: one per
  `[church] departments` group. The leader (or any admin) edits it, members
  tick it, each service gets a fresh round (the list moves on at 8 PM the
  night before), the finished round goes to History, and each list has its
  own nudge time per service. For now only the administrators tick them
  here; staff get theirs another way after Bradly's answers.
- **Text size on the closet monitor**: Settings → *The monitor & setup*,
  100–150%, 125% by default. Saving writes `/var/lib/arise/kiosk-scale` and
  restarts the kiosk browser; refused during a service.
- **The guided setup** opens the first time an administrator signs in: people,
  shares, the Synology, Discord, Resend, Tailscale. *Later* puts it away;
  Settings opens it again. State in `/var/lib/arise/setup.json`.
- **Sign-in faces** on the closet monitor (`?kiosk=1`): the administrators as
  initials, nobody preselected; the name field starts empty everywhere.

A member who opens an admin app by its address gets *That part of the
dashboard is for the administrator* (HTTP 403); the server enforces it, not
the page. Login is a Kerberos check against the domain controller itself
(`kinit`), so a disabled or expired account cannot sign in here either.

### Share links

Right-click a file or folder → **Share Link…** (or File → Share Link…). A
link lives until it is removed (`[links] days = 0`, Bradly's choice, Oct 28);
pick a life of up to `max_days` (365) when you want one to lapse. The
dashboard makes
`https://<server>/s/<token>`: anyone with it downloads the file with no
sign-in, a folder arrives as a zip (up to 2 GB). **Shared Links…** in the
flame menu, the Finder sidebar or Control Center lists yours with the
download count; *Remove* kills a link at once. The administrator sees
everyone's. Links live in `/var/lib/arise/links.json`; `arisectl link list`,
`arisectl link revoke <token>`, `arisectl link sweep`. Set `public_url` in
`[web]` once HTTPS is up so links carry the public address.

### A Windows keyboard

The closet monitor has a Windows keyboard. Every shortcut takes **Ctrl**
where a Mac takes ⌘, and the menus say so: Ctrl+Space Spotlight, Ctrl+W
close, Ctrl+Shift+N new folder, Ctrl+Alt+Q lock. The Windows key works too
where the browser reports it as ⌘.

## Rules it keeps

- **Nothing is deleted without typing its name.** Users, shares and apps ask
  for the exact name. Home folders, share folders, app data and snapshots are
  never removed by the dashboard at all.
- **Secrets never reach the browser.** `GET /api/settings` strips every key
  with `password`, `token` or `secret` in its name.
- **Sample data is labelled.** When a tool is missing or there is no config,
  the response carries `"demo": true` and the menu bar shows an amber *Sample
  data* badge. The published preview shows *Preview · sample data*.
- **Two kinds of login, one cookie.** `arisectl admin set-password` writes a
  bcrypt hash into `arise.toml` for the administrator; every directory user
  signs in with their domain password. The session is a signed cookie that
  carries the role and expires after `session_hours` (8760, a year: a browser
or a phone stays signed in until the person signs out, round 3, 38). The Terminal uses the
  same cookie and is admin-only. With no admin hash set the page refuses to
  show anything and tells you the command.

## Live stats

`/api/stats/stream` is a Server-Sent Events feed: one JSON sample a second
(CPU, per core, temperature where the board reports it, memory, swap, network
and disk rates, load, uptime). One collector thread samples psutil; every
open browser reads the same cache. `/api/stats/history` returns the last 60
samples so the sparklines are full on first paint.

## Reaching it

On the church network: `http://arise-server:4147`. From Alexandria, the Hub or
home: the same address over the VPN (docs/REMOTE-ACCESS.md), or
`https://arise-server.ad.arisecenla.com` once Caddy is on. It is not meant
to face the internet directly; the VPN is the front door.

## Running it anywhere

```bash
cd server && pip install -r requirements.txt
python -m arise_server --demo --port 4147     # sample data, no root needed
```

`python3 scripts/gen-demo-data.py` rebuilds `web/demo-data.js` from the same
sample responses; that file is what the static preview page uses. `web/vendor/`
holds xterm.js (MIT), fetched with `npm pack`, unmodified.
