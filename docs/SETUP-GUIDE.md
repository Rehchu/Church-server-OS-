# The setup guide — from a wiped OptiPlex to three sites

This is the one page to start from. It says what the system is, who gets
what, and the order to do things in. Every step points at the page that has
the commands, so nothing is repeated here twice. Read it once end to end
before you touch the PC.

Bradly's answers are in **docs/ANSWERS.md** (questions 1 to 7, the
OptiPlex and the Synology, come Sunday). This guide follows those answers;
where something still waits on Sunday or on a photo, it says so.

---

## 1. What you are building, on one page

One Dell OptiPlex, wiped, running Ubuntu Server 24.04 with Arise Server on
top. Four faces, one box:

| Face | What it is | Who uses it | From where |
|---|---|---|---|
| **The OS on the monitor** | the Arise desktop, full screen on the closet monitor from boot (`install.sh --kiosk`, docs/CONSOLE.md) | you, standing at the box | the closet |
| **The dashboard** | the same desktop in a browser: `http://arise-server:4147`. Every directory user can sign in. Admins see everything; members see their files, the shares they are allowed, Sermons, Bible, Campuses, a share-link button and a change-password button | everyone with an account | the church network, or Tailscale from anywhere. Nothing is exposed to the open internet (answer 36) |
| **SMB on the network** | `smb://arise-server/homes/<user>` and `smb://arise-server/shares/<name>`, the same folders the dashboard shows. Church Macs bound to the domain log in with the directory password and keep Desktop and Documents on the server | staff, media and the department logins at a church computer | any church site, on the LAN or over Tailscale |
| **The directory** | a real Active Directory domain, `AD.ARISECENLA.COM`, run by Samba (docs/DIRECTORY.md). Users, groups, computers, passwords, Kerberos, DNS | every Mac and PC that joins; every login above | everywhere the DNS reaches |

Underneath: the YouTube automator at 02:05, restic backups to the Synology
at 03:00, the GitHub mirror at 04:00 (README § The nightly timetable). The
07:00 daily note is off by Bradly's choice (answer 49); the dashboard's
*Needs you* list is the alarm.

"Active Directory, but better" means: it **is** AD (any Mac or Windows PC
binds to it the normal way, Kerberos single sign-on, one password
everywhere), and on top of AD it has what a church does not get from a
Windows Server box: a web portal for people who are not on site, share links,
a Finder in the browser, off-site VPN with no port forwarding, nightly
backups you can see the history of, and a desktop on the monitor instead of
a login prompt. What it does **not** have is group policy for Macs (AD never
did either) and a second domain controller on day one (docs/MULTI-SITE.md
says when to add one).

The three sites:

| Site | Now | Later |
|---|---|---|
| **Arise Church Pineville** | the server lives here, on the LAN | becomes a remote site when the server moves (docs/MOVING-DAY.md) |
| **Arise Church Alexandria** | reaches the server over the VPN | same |
| **The Apostolic Hub** | being built; people there use the VPN | the server moves here |

How "across town" connects is docs/NETWORK.md. Short version: every Mac
that is not on the server's own network runs Tailscale, signed in with the
one church login. Alexandria is a single Mac (answer 19), so that Mac runs
Tailscale itself and there is no route box there (answer 21). After the
server moves to the Hub, Pineville's church Macs need the same: Tailscale on
each, or one small route box for the building (that decision is still open,
docs/MOVING-DAY.md).

---

## 2. Roles: who can reach what, from where

Groups are in the directory (docs/DIRECTORY.md § Organisational units and
groups). The dashboard reads them: a member of `Domain Admins` (or the
`admin_user` in `arise.toml`) is an **admin**; everyone else is a
**member**. A share is readable by the groups listed on it.

| Role | Directory group | Church Mac (bound) | Personal Mac (not bound) | Off-site, any device | Phone |
|---|---|---|---|---|---|
| **Admin**: Apostle Bryant Sanders, Pastor Vanessa Sanders, Kristina Robinson, Bradly (answer 25; round 6, 21 to 23) | `Domain Admins` | everything: all shares; the OS itself at the closet monitor, each with their own Firefox profile | the dashboard as admin over Tailscale | same, over Tailscale | the dashboard as admin over Tailscale; the Nextcloud app |
| **Staff** (pastors, paid staff) | `Staff` | their AD account, made on every church Mac ahead of time by the helper (docs/MACS.md); Desktop and Documents sync to their server home through Nextcloud; the shares in Finder's sidebar | never enrolled; the Nextcloud app or web page over Tailscale, files only | Nextcloud over Tailscale | the Nextcloud app over Tailscale |
| **Leadership** | `Leadership` (+ `Staff`) | the above plus the `leadership` share | same | same | same |
| **Media** | `Media` | the above plus the `media`, `graphics` and `recordings` shares, the StreamYard and Proclaim Macs | same | same | same |
| **Department** (one shared login per department: Children's Department, Inedge, Worship, others to come; answer 27) | one group per department (`Childrens-Department`, `Inedge`, `Worship`) | the department's login, synced like a person (round 6, 40): its share and its home folder | — | Nextcloud over Tailscale | the Nextcloud app |
| **Guest** | no account | the guest Wi-Fi, already separate from the staff network (answer 17) | — | nothing | nothing |

Staff, departments and volunteers never sign in to the server OS: with
`[web] staff_access = "none"` (the default, round 5, 41) a non-admin sign-in
on the dashboard is told their files are on their Mac. SSH is Bradly's only;
the other three admins get the admin desktop, not a shell, unless they ask. Volunteers do not get personal
accounts (answer 24); they use a department login. The `Volunteers` group
stays in the directory, empty, for the day that changes.

What a member **cannot** do anywhere: see another person's home, see a share
their group is not on, delete or move files from the dashboard (that is the
Mac's own Finder over SMB, on purpose), see settings, services, logs, the
Terminal, backups or the automator. What an admin cannot do from the
dashboard: delete a home folder, delete a snapshot, delete a share's files
(all by design; README § Rules it keeps).

There is no kids check-in station yet (answer 28); the `Kids-Check-in`
group waits. Before day 5 below, two lists are still needed: the people in
staff and media, and every department that gets a login (docs/ANSWERS.md
§ Still needed).

---

## 3. The order of work

Each day is a block that ends in a state you can leave the box in. Do them
in order. Nothing in a later block is needed by an earlier one.

### Day 0 — before the wipe

docs/PRE-WIPE.md, all of it: what is on the old Windows PC that is worth
keeping, the automator's `token.json` and `client_secret.json` copied to a
USB stick **and** your Mac, the Synology admin password written down, a
photo of the back of the PC and the switch port it is in.

Questions 1 to 7 (the OptiPlex, the Synology) are answered on Sunday; the
Cisco sticker and each router's LAN page still need a photo (answers 10 and
12). Three decisions have to be made before the installer runs:

- **where the server plugs in**: decided. Wired into the switch on Netgear
  A's network (the router at the modem). **No router, switch or Mesh
  setting changes, ever, and no IP address changes**: the installer keeps
  the address the router hands the box and pins it on the server, each Mac
  gets a per-domain resolver file from `bind-mac.sh --dns`, and Tailscale
  covers everything the NATs block. docs/NETWORK.md § The Pineville network
  as it is;
- whether home folders live on the server's disk or on the Synology
  (docs/SYNOLOGY.md; the OptiPlex's disk size decides, question 2, Sunday).

Also needed on day 1: the model of the Pineville UPS (answer 8) and a USB
cable from the UPS to the server, for the step below.

### Day 1 — the OS

Bradly installs at home first and carries the box in. Use `--staging` at
home (INSTALL.md § Installing at home first): the domain listens on the
box only, no home address is pinned, no scan of the house, no DC port
open. At the church, the same command without `--staging` relocates it in
one run.


INSTALL.md § Path A, steps 1 to 5: make the USB, install Ubuntu, get the
code on it, run the installer, set the fixed address. Run the installer with
the flags you will actually use so the box is complete on the first pass:

```bash
sudo bash /opt/arise/installer/install.sh --with-tailscale --with-caddy --kiosk
```

Plug the server and the Synology into the Pineville UPS (answer 8) and run
the UPS's USB cable to the server. Install `nut` (Network UPS Tools, in
Ubuntu) and point it at the UPS model, so the server shuts itself down
cleanly before the battery dies; a domain controller that loses power
mid-write can corrupt its database. The exact `nut` lines wait on the UPS
model; docs/IDEAS.md § 1 has the shape of it.

The monitor in the closet shows the Arise desktop as soon as the installer
finishes and the box reboots (docs/CONSOLE.md). The Windows keyboard works
as is: **Ctrl** does what ⌘ does on a Mac, and the Windows key does too
where the browser reports it. The desktop prints shortcut labels as `Ctrl`
on that keyboard.

End of day 1: `sudo arisectl doctor` is green for the OS, the dashboard
opens on the LAN, the domain exists, nobody is in it yet.

### Day 2 — the directory, DNS, the first Mac

1. docs/DIRECTORY.md § DNS on the church network. The routers keep the DNS
   they hand out today; nothing on them changes (ANSWERS 111, 118).
   Enrolment writes a resolver file on each Mac that sends only
   `ad.arisecenla.com` to the server. Verify with the two `dig` lines on a
   Mac.
2. Create yourself and the groups (§ 4 below): `bradly.dyer` in
   `Domain Admins`, `Staff` and `Media`.
3. Enrol **one** church Mac, yours: Macs app → **Enrol a Mac**, paste the
   one Terminal line on the Mac (docs/MACS.md). Grant the helper Full Disk
   Access when enrolment asks. Log out, log in as `bradly.dyer`, and watch
   Desktop and Documents sync to your server home through Nextcloud
   (docs/SYNC.md). Make a file on the Mac and see it in the dashboard's
   Finder a few seconds later. Do not enrol a second Mac until this one is
   boring.

### Day 3 — the automator, the Synology, backups

INSTALL.md § First boot, steps 2 to 4 and 6, in that order: the automator
checkout and its two secret files, the restic password (on paper too), the
Synology mounted, `arisectl doctor`. Then Dashboard → Backups → run every
job once by hand and read the history rows. A backup you have never watched
succeed is not a backup.

The automator keeps running on the old Windows PC until the server's timer
is enabled, then it stops there (answer 46); never two copies at 02:05.
Backup history is 30 daily, 12 weekly, 24 monthly (answer 47); how much
Synology space that takes waits on question 4. The `recordings` share is
excluded from restic on purpose (§ 4, Shares).

Wait one night. In the morning the 02:05 automator report and the 03:00
backup rows are in the dashboard. There is no daily note (answer 49): the
*Needs you* list on the Overview is what to read.

### Day 4 — remote access, the closet door closes

docs/REMOTE-ACCESS.md § (f), the checklist. The test that matters: from
your phone's hotspot, on your laptop, open `http://arise-server:4147`,
sign in, open a file in the Finder. If that works the server no longer
needs you in the room.

Tailscale is signed in with the one shared church Google login on every
device (answers 29 and 42). Everyone with an account may reach the server
from home (answer 43), so each person gets the Tailscale app and the
dashboard address. Guacamole gets one connection, the media Mac (answer 44).
No public door (answer 36; § 9 is off).

### Day 5 — people

Accounts for staff and media now (answer 24): the four admins, the staff,
the media team, then one login per department (Children's Department,
Inedge, Worship, and the rest of the list when it comes). Groups per § 2. Each person's first login
sets their own password (`arisectl user passwd` marks "must change at next
login"). Give each person the one-paragraph "what you do" from § 6 or § 7.

### Day 6 — the rest of Pineville's computers

`mac/enroll-mac.sh` on each church Mac, one at a time, the person present
for the first login (docs/MAC-MIGRATION.md). Six to ten Macs in all
(answer 30), so two or three days. There are no Windows PCs (answer 31).
Where a Mac's local account name is not `first.last`, pass
`--map oldname=first.last`.

**Personal Macs are not bound.** Apostle Bryant's and Pastor Vanessa's own
Macs leave the building (answer 34); binding a personal Mac hands its login
to the church directory, which is the wrong direction for a personal
machine. They get the Tailscale app and, if they want their files there, the
Nextcloud app (files only, round 6, 19 and 39). The helper never touches a
personal Mac.

The media Mac runs Proclaim and sends NDI (answer 50); it is a Mac, so it
is enrolled like the others, with a shared `media` login (answer 32). Its
video is small enough to move (answer 33): it goes to the `recordings`
share on the Synology, not into the home-sync list. Proclaim's backgrounds,
loops and lower thirds get a Syncthing pair with the `graphics` share
(answer 38) so they play from local disk and are backed up from the share.
Two more Syncthing pairs, and only these (round 2, 25): the automator's
thumbnails folder to the media Mac, and the office documents share to the
office Mac. Every church Mac also backs itself up with Time Machine to a
share on the Synology (round 2, 5); space about equal to each Mac's used
disk, an estimate, so that waits for the Synology's size (question 4).
Printing: the office printer sits behind router B and is not an HP; once
its brand and model are known the server runs CUPS with AirPrint so every
Mac and phone prints to it (round 2, 6 and 26); nothing on router B changes.

### Day 7 — Alexandria

Alexandria is one Mac and there is no place for a route box (answers 19
and 21), so the Mac is its own tunnel: docs/NETWORK.md § A church across
town, option A. The order: the split-DNS rule for `ad.arisecenla.com` in
the Tailscale console (done on day 4), Tailscale installed on that Mac and
set to start at login, `ping arise-server` and the two `dig` lines, then
`mac/enroll-mac.sh` exactly like day 2. Drive there for it. Nobody streams
from Alexandria (answer 22), so there is no bandwidth rule there.

### Day 8 — the Hub

Until the Hub exists, Hub people are laptops on Tailscale (docs/MULTI-SITE.md
§ The Apostolic Hub). When the building is ready and the server moves,
docs/MOVING-DAY.md is the plan for that day.

### Then

The care list in § 8. `arisectl doctor` weekly. The questions in
docs/QUESTIONS.md that are not answered yet, as they come up.

---

## 4. Creating people: three doors, one result

All three run the same code. The result is the same user, the same home
folder, the same groups.

**From the dashboard, or the desktop on the monitor** (they are the same
thing): Directory → Users → **Add**. Username, display name, a first
password, groups. The row goes green when the home folder exists. Password
reset, enable, disable and delete are on the same row; delete asks for the
username typed back and never removes the home folder.

**Over SSH**, or in the dashboard's Terminal app:

```bash
sudo arisectl user add jane.smith --display "Jane Smith" --groups Staff
sudo arisectl user passwd jane.smith          # prompts twice
sudo arisectl group addmember Media jane.smith
sudo arisectl user list
sudo arisectl user disable jane.smith         # when someone leaves; files stay
```

When someone leaves (round 2, 24): the login stays on for 30 days in case
they come back, then is disabled; their files move to the next appropriate
person or department account, chosen by you. That becomes a "leaving"
button in the Directory app (v0.8 "Exodus", docs/ROADMAP.md); until then it
is `arisectl user disable` after the 30 days and a move in Finder.

The four admins get two-step sign-in with codes from Microsoft
Authenticator (round 2, 11; TOTP, so no Microsoft account is involved),
enrolled from the flame menu before any member signs in. Also v0.8.

**Usernames are `first.last`** (answer 23): `bradly.dyer`, `bryant.sanders`,
`vanessa.sanders`, `kristina.robinson`. Lower case, a dot, no spaces. A
Mac whose local account is called something else is paired by hand:
`mac/enroll-mac.sh --map oldname=first.last` (one `--map` per person).
Department logins are the department name in the same shape where it fits
(`childrens.department`, `inedge`, `worship`); say the exact names when the
department list comes.

**Groups**: make them once, by name, exactly as in § 2. `install.sh` creates
`Staff`, `Leadership`, `Media`, `Volunteers`, `Kids-Check-in`, and one group
per department: `Childrens-Department`, `Inedge`, `Worship`. Add others
with `arisectl group add` or Directory → Groups → **New group**.

**Shares**, nine of them (answer 37): `staff`, `leadership`, `media`,
`kids`, `graphics`, `childrens-department`, `inedge`, `worship`,
`recordings`. `install.sh` makes them from `config/samba/smb.conf.template`;
more with Directory → Shares → **New share** (name, path, which groups may
read, which may write), or `arisectl share add`. A share is a folder under
`/srv/arise/shares/` (or on the Synology) with a group on it. The dashboard
member portal shows a person the shares whose groups they are in; SMB shows
the same ones. `recordings` lives on the Synology, holds every Sunday's
video (answer 51), and is **excluded from restic**: a file of several GB a
week would swallow the backup history. Its protection is the Synology's own
RAID until an off-site copy exists (answer 48, "nowhere yet").

A person's own password: Dashboard → the flame menu → **Change Password**
(members and admins alike), or on a bound Mac the normal System Settings
password change, which goes to the domain.

---

## 5. Joining computers, per site

| Where | Church Macs | Personal Macs | What it needs first |
|---|---|---|---|
| **Pineville** (server on the LAN) | the one Terminal line from the Macs app (docs/MACS.md) | never enrolled: Tailscale + the Nextcloud app | the resolver file enrolment writes; the Mac on the server's network (docs/NETWORK.md) |
| **Alexandria** (one Mac) | Tailscale on the Mac, signed in, start at login; then the same Terminal line | — | the split-DNS rule |
| **The Hub** (before the move) | Tailscale on the Mac, then the same Terminal line | never enrolled: Tailscale + the Nextcloud app | the split-DNS rule |
| **A church laptop that moves between sites** | bind it at whichever site; it is a mobile account, it works everywhere and offline | — | Tailscale on it, so it is "home" from anywhere |

There are no Windows PCs today (answer 31); docs/DIRECTORY.md § Joining a
Windows PC is reference for the day one appears.

A joined computer appears in Dashboard → Directory → Computers, and in
Campuses under the site whose subnet its address is in. That is how you
know which building a Mac is in.

---

## 6. What a remote member does

**By default this is Nextcloud, not the dashboard.** With
`[web] staff_access = "none"` (round 5, 41) staff and volunteers open the
Nextcloud app or `https://cloud.ad.arisecenla.com` over Tailscale and see
their own files and the shares their groups allow (docs/STAFF-FILES.md).
The steps below are the dashboard portal, for the day an admin turns it on
with `staff_access = "portal"`.

Someone on the staff, at home, with a file to drop off and a video to
collect:

1. Open Tailscale (signed in with the church login), then the dashboard:
   `http://arise-server:4147`. There is no public address (answer 36).
2. Sign in with their directory username and password. The same one as the
   church Mac.
3. The Finder opens on their home folder. The sidebar shows **Home** and the
   shares their groups allow (`staff`, maybe `media`). Nothing else.
4. **Upload**: the Upload button, or drag files onto the window. Files land
   in the folder they are looking at, which is on the server, which is in
   tonight's backup. 2 GB per file through the browser; bigger than that,
   use Tailscale and the share over SMB.
5. **Download**: double-click a file, or select it and press Download.
   Space previews most things first (Quick Look).
6. **Share a link**: right-click a file, **Share Link…**. A
   `http://arise-server:4147/s/<token>` address goes to the clipboard. Anyone
   with it downloads that one file, no sign-in, for 7 days by default
   (answer 39); the link is listed under the flame menu → **Shared Links…**,
   with a Remove button. Because nothing is exposed to the internet, the
   link only opens for someone on the church's Tailscale; a link to someone
   outside the church needs the public door, which is off (answer 36).
7. **Change Password**: flame menu → Change Password. Old password, new
   password twice. It changes in the directory, so the Mac at church uses the
   new one next login.
8. Sign out (flame menu) on a shared computer.

That is the whole portal. It is deliberately small.

---

## 7. What a staff Mac does

After `mac/enroll-mac.sh`:

- Login is the directory username and password. The helper makes every
  server account on every church Mac ahead of time, so their face is on the
  login window before their first sign-in (round 6, 41). After that the Mac
  works with the server up or down, on site or at home: the account and
  password are cached.
- Desktop and Documents sync to the server through the Nextcloud client
  (docs/SYNC.md), on the church network or over Tailscale. Downloads,
  Pictures, Movies, Music stay on the Mac. `arise-home-sync` is the
  fallback on a Mac where Nextcloud is not running.
- Shares appear under Network in the Finder, or `⌘K` →
  `smb://arise-server/shares/staff`. No password prompt: Kerberos from the
  login carries it.
- Off site without Tailscale: the Mac works, the sync waits, Desktop and
  Documents show the last synced copy, the shares are not there. With
  Tailscale installed and signed in, everything is the same as at church,
  just slower.
- A Mac that already had local users before enrolment: each local account
  waits on the Macs page for an admin's choice: **Convert** (it becomes the
  server user, files kept, with Undo), **Link** (it stays as it is and its
  Desktop and Documents sync as the server user) or **Leave alone**
  (docs/MACS.md). Nothing happens to it before that choice.
- A personal Mac (Apostle Bryant's, Pastor Vanessa's) does none of this. It
  is never enrolled. It runs Tailscale and the Nextcloud app if its owner
  wants their files there.

---

## 8. Care

| When | What | Where |
|---|---|---|
| **Every morning** | Dashboard → Overview → *Needs you*. Red rows are last night's failures. (No daily note is sent, answer 49.) | the dashboard, or the closet monitor |
| **Weekly** | `sudo arisectl doctor`; Backups → last run per job is green; Updates on System Settings; a glance at the closet monitor | the dashboard or SSH |
| **Monthly** | restore one file from a snapshot to prove the backups restore (docs/BACKUPS.md); `restic check`; Directory → Users, disable anyone who left; Remote → the device list, remove a lost laptop | Dashboard → Backups → Snapshots |
| **Quarterly** | a full `apt upgrade` and a reboot on a weekday morning; the Synology's own update; re-read docs/QUESTIONS.md for anything that changed | System Settings → Updates → Upgrade packages |
| **Yearly** | the off-site copy of the restic repository is still "nowhere" (answer 48): decide again; the automator's OAuth token re-consent if Google asks; the UPS battery test | — |
| **Before every move, every ISP change, every new router** | docs/MOVING-DAY.md, even if the box only moves to another room: the IP and DNS are what everything else points at | — |

---

## 9. The public door: off, by Bradly's choice

Answer 36: Tailscale only, nothing exposed. Everything above works with
**nothing** on the internet: off-site people install Tailscale, sign in
once with the church login, and the dashboard is just there. The rest of
this section is what the other choice would mean, kept for the day it
changes.

The alternative is a public HTTPS address for the dashboard so a member can
sign in from any browser without installing anything. It means: a real
domain name (`files.arisecenla.com` would be the one, set in Wix's DNS; arisecenla.church is at GoDaddy, out of reach), a port forward
of 443 on the church router to the server, Caddy with a public certificate
instead of `tls internal` (Caddy does Let's Encrypt by itself once the name
resolves to your public IP), and fail2ban on the dashboard's login. The
dashboard's login then stands between the internet and the directory
passwords. It is a reasonable door for a church, and a bigger one than
Tailscale. I have not opened it in the installer; it is a flag I will add
the day you say yes to question 36. Until then the answer to "I'm at home
and need a file" is "install Tailscale."

---

## 10. When something breaks, where to look

| Symptom | Look here first | Then |
|---|---|---|
| A Mac will not bind, or a login hangs at church | the Mac is not using the server for DNS: `dig +short _ldap._tcp.ad.arisecenla.com SRV` on the Mac | docs/DIRECTORY.md § DNS; the VLAN the Mac is on (docs/NETWORK.md) |
| Everything is fine on site, nothing works from Alexandria | Tailscale on that Mac: signed in, running, the split-DNS rule in the console | Dashboard → Remote → the device list; docs/NETWORK.md § A church across town |
| The dashboard says *Sample data* | the server has no `arise.toml` or a tool is missing | `sudo arisectl doctor` |
| A backup row is red | the reason is in the row | Dashboard → Backups → History; docs/BACKUPS.md |
| The automator did not run | Automator → last run; the token | docs/AUTOMATOR.md |
| The monitor shows a text banner instead of the desktop | `arise-kiosk` failed to start | `journalctl -u arise-kiosk`; docs/CONSOLE.md |
| A person cannot sign in to the dashboard | disabled user, wrong password, or not in any group | Directory → Users; reset the password |
| A share link does not open | expired or revoked; or the person is not on Tailscale (there is no public door, answer 36) | flame menu → Shared Links |
| The server is off and nobody can log in to a Mac | mobile accounts still log in; new users and password changes wait | get the server up; then docs/MULTI-SITE.md § A second domain controller is the long-term answer |
| You are locked out of SSH | the closet monitor: Alt+F2 is a text login on tty2 | docs/CONSOLE.md |

Paste `arisectl doctor` output when you ask me for help. It says more than
a description does.
