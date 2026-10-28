# The setup guide — from a wiped OptiPlex to three sites

This is the one page to start from. It says what the system is, who gets
what, and the order to do things in. Every step points at the page that has
the commands, so nothing is repeated here twice. Read it once end to end
before you touch the PC.

Open questions that change parts of this plan are in **docs/QUESTIONS.md**.
Where this guide assumes an answer, it says so.

---

## 1. What you are building, on one page

One Dell OptiPlex, wiped, running Ubuntu Server 24.04 with Arise Server on
top. Four faces, one box:

| Face | What it is | Who uses it | From where |
|---|---|---|---|
| **The OS on the monitor** | the Arise desktop, full screen on the closet monitor from boot (`install.sh --kiosk`, docs/CONSOLE.md) | you, standing at the box | the closet |
| **The dashboard** | the same desktop in a browser: `http://arise-server:4147`. Every directory user can sign in. Admins see everything; members see their files, the shares they are allowed, Sermons, Bible, Campuses, a share-link button and a change-password button | everyone with an account | the church network, the VPN, or the internet through Caddy if you choose to expose it (§ 9) |
| **SMB on the network** | `smb://arise-server/homes/<user>` and `smb://arise-server/shares/<name>`, the same folders the dashboard shows. Macs bound to the domain log in with the directory password and keep Desktop and Documents on the server | staff and volunteers at a church computer | any church site, on the LAN or over the site VPN |
| **The directory** | a real Active Directory domain, `AD.ARISECENLA.CHURCH`, run by Samba (docs/DIRECTORY.md). Users, groups, computers, passwords, Kerberos, DNS | every Mac and PC that joins; every login above | everywhere the DNS reaches |

Underneath: the YouTube automator at 02:05, restic backups to the Synology
at 03:00, the GitHub mirror at 04:00, the daily note at 07:00
(README § The nightly timetable).

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

How "across town" connects is docs/NETWORK.md. Short version: every laptop
runs Tailscale; each site gets one small always-on box that routes the whole
site over Tailscale, so the Macs, printers and the check-in iPad there are
on the church network without installing anything.

---

## 2. Roles: who can reach what, from where

Groups are in the directory (docs/DIRECTORY.md § Organisational units and
groups). The dashboard reads them: a member of `Domain Admins` (or the
`admin_user` in `arise.toml`) is an **admin**; everyone else is a
**member**. A share is readable by the groups listed on it.

| Role | Directory group | On-site Mac (bound) | On-site PC (joined) | Off-site laptop | Phone |
|---|---|---|---|---|---|
| **Admin** (Bradly) | `Domain Admins` | everything: all shares, the dashboard as admin, SSH, the Terminal | same | same, over Tailscale; dashboard as admin | dashboard as admin over Tailscale; Tailscale SSH |
| **Staff** (pastors, paid staff) | `Staff` | own home folder on the server, `staff` share, their own mobile account | same | dashboard member portal: own home, `staff` share, upload, download, share links; Tailscale for full SMB if installed | dashboard member portal |
| **Leadership** | `Leadership` (+ `Staff`) | the above plus the `leadership` share | same | same plus `leadership` in the portal | dashboard member portal |
| **Media** | `Media` | the above plus the `media` share, the StreamYard/Proclaim Macs | same | same plus `media` in the portal | dashboard member portal |
| **Volunteer** | `Volunteers` | own home folder only | own home folder only | dashboard member portal: own home only | dashboard member portal |
| **Guest** | no account | the guest Wi-Fi, which cannot see the server (docs/NETWORK.md) | — | nothing | nothing |

What a member **cannot** do anywhere: see another person's home, see a share
their group is not on, delete or move files from the dashboard (that is the
Mac's own Finder over SMB, on purpose), see settings, services, logs, the
Terminal, backups or the automator. What an admin cannot do from the
dashboard: delete a home folder, delete a snapshot, delete a share's files
(all by design; README § Rules it keeps).

Guests on the kids check-in station and the lobby PC: a `Kids-Check-in`
group and a shared, locked-down account. Decide the exact list of people
and groups before day 5 below; the questions in docs/QUESTIONS.md § People
and accounts are what I need to fill in the names.

---

## 3. The order of work

Each day is a block that ends in a state you can leave the box in. Do them
in order. Nothing in a later block is needed by an earlier one.

### Day 0 — before the wipe

docs/PRE-WIPE.md, all of it: what is on the old Windows PC that is worth
keeping, the automator's `token.json` and `client_secret.json` copied to a
USB stick **and** your Mac, the Synology admin password written down, a
photo of the back of the PC and the switch port it is in.

Answer the questions in docs/QUESTIONS.md that are marked **before the
wipe** (the OptiPlex, the Synology, the Pineville network). Two decisions
have to be made before the installer runs:

- the server's **static IP** and the subnet it sits on (docs/NETWORK.md § The IP plan);
- whether home folders live on the server's disk or on the Synology (docs/SYNOLOGY.md; the OptiPlex's disk size decides, and I do not know it yet).

### Day 1 — the OS

INSTALL.md § Path A, steps 1 to 5: make the USB, install Ubuntu, get the
code on it, run the installer, set the fixed address. Run the installer with
the flags you will actually use so the box is complete on the first pass:

```bash
sudo bash /opt/arise/installer/install.sh --with-tailscale --with-caddy --kiosk
```

The monitor in the closet shows the Arise desktop as soon as the installer
finishes and the box reboots (docs/CONSOLE.md). The Windows keyboard works
as is: **Ctrl** does what ⌘ does on a Mac, and the Windows key does too
where the browser reports it. The desktop prints shortcut labels as `Ctrl`
on that keyboard.

End of day 1: `sudo arisectl doctor` is green for the OS, the dashboard
opens on the LAN, the domain exists, nobody is in it yet.

### Day 2 — the directory, DNS, the first Mac

1. docs/DIRECTORY.md § DNS on the church network. The router (or the Cisco,
   if it is the DHCP server) hands out the server as the **only** DNS. This
   is the step people skip and then nothing binds. Verify with the two `dig`
   lines on a Mac.
2. Create yourself and the groups (§ 4 below). Give yourself `Domain Admins`
   and `Staff` and `Media`.
3. Bind **one** Mac, yours, with `mac/enroll-mac.sh` (docs/MAC-MIGRATION.md).
   Log out, log in as your domain user, watch Desktop and Documents land in
   `smb://arise-server/homes/bradly`. Make a file on the Mac, see it in the
   dashboard's Finder within fifteen minutes (that is the home-sync agent).
   Do not bind a second Mac until this one is boring.

### Day 3 — the automator, the Synology, backups

INSTALL.md § First boot, steps 2 to 4 and 6, in that order: the automator
checkout and its two secret files, the restic password (on paper too), the
Synology mounted, `arisectl doctor`. Then Dashboard → Backups → run every
job once by hand and read the history rows. A backup you have never watched
succeed is not a backup.

Wait one night. In the morning the 02:05 automator report and the 03:00
backup rows are in the dashboard, and the 07:00 daily note is in Discord or
Slack if you set the webhook (docs/BACKUPS.md, `[notify]` in `arise.toml`).

### Day 4 — remote access, the closet door closes

docs/REMOTE-ACCESS.md § (f), the checklist. The test that matters: from
your phone's hotspot, on your laptop, open `http://arise-server:4147`,
sign in, open a file in the Finder. If that works the server no longer
needs you in the room.

Set up the member portal's public door if you want one (§ 9 below); it is
optional and has a cost.

### Day 5 — people

Every staff member and every volunteer who will ever touch a church
computer gets an account (§ 4). Groups per § 2. Each person's first login
sets their own password (`arisectl user passwd` marks "must change at next
login"). Give each person the one-paragraph "what you do" from § 6 or § 7.

### Day 6 — the rest of Pineville's computers

`mac/enroll-mac.sh` on each Mac, one at a time, the person present for the
first login (docs/MAC-MIGRATION.md). Windows PCs: docs/DIRECTORY.md
§ Joining a Windows PC. The lobby PC and the check-in station last.

The media Mac is special: it carries the StreamYard and Proclaim work and
tens of gigabytes of video. Bind it, but keep the video local and let the
nightly jobs move finished pieces (docs/MULTI-SITE.md § Latency). Do not
let the home-sync agent try to push a 40 GB folder; the agent syncs Desktop
and Documents only unless you add folders to its list.

### Day 7 — Alexandria

docs/NETWORK.md § A church across town. The order: Tailscale on your laptop
first (already done on day 4), then the Alexandria site router box
(a Raspberry Pi or mini PC with `tailscale up --advertise-routes=…`),
approve its route in the Tailscale console, then the split-DNS rule for
`ad.arisecenla.church`, then bind the first Alexandria Mac exactly like day
2. Drive there for the first one.

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
sudo arisectl user add jsmith --given "Jane" --surname "Smith" --groups Staff
sudo arisectl user passwd jsmith              # prompts twice; "must change at next login"
sudo arisectl group addmember Media jsmith
sudo arisectl user list
sudo arisectl user disable jsmith             # when someone leaves; files stay
```

**Usernames**: lowercase, first initial plus surname (`jsmith`), or the
first name when the church already calls people that way. Pick one rule and
keep it; the Mac's local account names should match the directory names
(`mac/enroll-mac.sh` matches existing local users to directory users by
name, so a Mac user called `vanessa` needs a directory user called
`vanessa`). This is question 23.

**Groups**: make them once, by name, exactly as in § 2. `install.sh` creates
`Staff`, `Leadership`, `Media`, `Volunteers`, `Kids-Check-in`. Add others
with `arisectl group add` or Directory → Groups → **New group**.

**Shares**: Directory → Shares → **New share** (name, path, which groups may
read, which may write), or `arisectl share add`. A share is a folder under
`/srv/arise/shares/` (or on the Synology) with a group on it. The dashboard
member portal shows a person the shares whose groups they are in; SMB shows
the same ones.

A person's own password: Dashboard → the flame menu → **Change Password**
(members and admins alike), or on a bound Mac the normal System Settings
password change, which goes to the domain.

---

## 5. Joining computers, per site

| Where | Macs | Windows PCs | What it needs first |
|---|---|---|---|
| **Pineville** (server on the LAN) | `mac/enroll-mac.sh` (docs/MAC-MIGRATION.md) | docs/DIRECTORY.md § Joining a Windows PC | the server as the only DNS from DHCP; the computer on a VLAN that may reach the server (docs/NETWORK.md) |
| **Alexandria** | same script, over the site's Tailscale route | same, over the route | the Alexandria route approved; the split-DNS rule; or Tailscale on the Mac itself |
| **The Hub** (before the move) | Tailscale on the Mac, signed in, start at login; then the same script | Tailscale on the PC, then the join | the split-DNS rule |
| **A laptop that moves between sites** | bind it at whichever site; it is a mobile account, it works everywhere and offline | same | Tailscale on it, so it is "home" from anywhere |

A joined computer appears in Dashboard → Directory → Computers, and in
Campuses under the site whose subnet its address is in. That is how you
know which building a Mac is in.

---

## 6. What a remote member does

Someone on the staff, at home, with a file to drop off and a video to
collect:

1. Open the dashboard address you gave them (over Tailscale it is
   `http://arise-server:4147`; through the public door it is
   `https://files.arisecenla.church` or whatever name you chose in § 9).
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
6. **Share a link**: select a file, **Share link**. A `https://…/s/<token>`
   address goes to the clipboard. Anyone with it can download that one file,
   for 7 days by default; the link is listed under the flame menu → **My
   links**, with a revoke button. The link is public: do not share the
   leadership share's payroll sheet this way.
7. **Change Password**: flame menu → Change Password. Old password, new
   password twice. It changes in the directory, so the Mac at church uses the
   new one next login.
8. Sign out (flame menu) on a shared computer.

That is the whole portal. It is deliberately small.

---

## 7. What a staff Mac does

After `mac/enroll-mac.sh`:

- Login is the directory username and password. The first login at church
  takes a minute while the mobile account is made. After that the Mac works
  with the server up or down, on site or at home: the account and password
  are cached.
- Desktop and Documents are kept on the server (`/Volumes/<user>` when the
  share is mounted, synced every 15 minutes by `arise-home-sync` when the
  server is reachable). Downloads, Pictures, Movies, Music stay on the Mac.
  Add folders to the sync list in the script if a person needs more.
- Shares appear under Network in the Finder, or `⌘K` →
  `smb://arise-server/shares/staff`. No password prompt: Kerberos from the
  login carries it.
- Off site without Tailscale: the Mac works, the sync waits, Desktop and
  Documents show the last synced copy, the shares are not there. With
  Tailscale installed and signed in, everything is the same as at church,
  just slower.
- A Mac that already had local users before enrolment: the script makes a
  directory user for each local user it finds (you confirm each one and set
  a first password), copies that person's Desktop and Documents to their
  server home, and leaves the old local account in place, renamed, until
  you delete it yourself. Nothing is deleted by the script.

---

## 8. Care

| When | What | Where |
|---|---|---|
| **Every morning** | read the daily note (Discord/Slack). If it did not arrive, the server or the internet is down | the webhook; Dashboard → Overview → *Needs you* |
| **Weekly** | `sudo arisectl doctor`; Backups → last run per job is green; Updates on System Settings; a glance at the closet monitor | the dashboard or SSH |
| **Monthly** | restore one file from a snapshot to prove the backups restore (docs/BACKUPS.md); `restic check`; Directory → Users, disable anyone who left; Remote → the device list, remove a lost laptop | Dashboard → Backups → Snapshots |
| **Quarterly** | a full `apt upgrade` and a reboot on a weekday morning; the Synology's own update; re-read docs/QUESTIONS.md for anything that changed | System Settings → Updates → Upgrade packages |
| **Yearly** | a second copy of the restic repository somewhere not in the building (docs/IDEAS.md); the automator's OAuth token re-consent if Google asks; the UPS battery test | — |
| **Before every move, every ISP change, every new router** | docs/MOVING-DAY.md, even if the box only moves to another room: the IP and DNS are what everything else points at | — |

---

## 9. The public door, if you want one

Everything above works with **nothing** on the internet: off-site people
install Tailscale, sign in once, and the dashboard is just there. That is
the recommendation, and it is free.

The alternative is a public HTTPS address for the dashboard so a member can
sign in from any browser without installing anything. It means: a real
domain name (`files.arisecenla.church` is the natural one), a port forward
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
| A Mac will not bind, or a login hangs at church | the Mac is not using the server for DNS: `dig +short _ldap._tcp.ad.arisecenla.church SRV` on the Mac | docs/DIRECTORY.md § DNS; the VLAN the Mac is on (docs/NETWORK.md) |
| Everything is fine on site, nothing works from Alexandria | Tailscale: is the Alexandria route box up, is its route approved | Dashboard → Remote → the device list; docs/NETWORK.md § A church across town |
| The dashboard says *Sample data* | the server has no `arise.toml` or a tool is missing | `sudo arisectl doctor` |
| A backup row is red | the reason is in the row | Dashboard → Backups → History; docs/BACKUPS.md |
| The automator did not run | Automator → last run; the token | docs/AUTOMATOR.md |
| The monitor shows a text banner instead of the desktop | `arise-kiosk` failed to start | `journalctl -u arise-kiosk`; docs/CONSOLE.md |
| A person cannot sign in to the dashboard | disabled user, wrong password, or not in any group | Directory → Users; reset the password |
| A share link does not open | expired or revoked; or the public door is not set up and the person is not on Tailscale | flame menu → Shared Links |
| The server is off and nobody can log in to a Mac | mobile accounts still log in; new users and password changes wait | get the server up; then docs/MULTI-SITE.md § A second domain controller is the long-term answer |
| You are locked out of SSH | the closet monitor: Alt+F2 is a text login on tty2 | docs/CONSOLE.md |

Paste `arisectl doctor` output when you ask me for help. It says more than
a description does.
