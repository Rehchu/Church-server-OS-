# Answers from Bradly (Oct 28 2026) and what they decide

The multiple-choice questions in docs/QUESTIONS.md, answered in the chat
pop-ups. Questions 1 to 7 (the OptiPlex and the Synology) come Sunday.
Where an answer changes the plan, the change is named here and made in the
file it points to. Nothing in this file is assumed; every line is his answer.

## The box, the closet

| # | Answer | What it decides |
|---|---|---|
| 1 to 7 | **Sunday** | model, RAM, drives, Synology model and RAID, what is on it, its login, whether it moves to the Hub |
| 8 | Pineville has a UPS | the server plugs into it on day 1; `nut` auto-shutdown moves from IDEAS into the day-1 plan once the UPS model is known (a USB cable from the UPS to the server is needed) |
| 9 | Closet is cool and has a network cable | wired, as planned |

## Pineville network

| # | Answer | What it decides |
|---|---|---|
| 10 | Cisco model: photo of the sticker to come | until then: see 11 |
| 11 | "I think it's unmanaged" | an unmanaged switch has no VLANs. The VLAN plan in docs/NETWORK.md becomes: VLANs on the router if it can, or a managed switch later (an estimate: a 24-port managed gigabit switch is $150 to $300). Day 1 does not need VLANs; the server works on a flat network |
| 12 | Several routers, each its own network | the server lives behind ONE of them, on the network the staff Macs and the media Mac use. No two of those networks may share a subnet with Alexandria or the Hub. The list of those networks and their subnets is still needed (a photo of each router's LAN page) |
| 13 | A separate router (not the ISP box) | DHCP, DNS hand-out and any port forward live there; it may be able to do VLANs itself |
| 14 | The router hands out addresses | the one DNS setting that makes the domain work is on that router: point its DNS at the server |
| 15 | Over 50 Mbit/s upload | plenty for the sync, the VPN and the stream together |
| 16 | Dynamic public IP, can forward a port | Tailscale needs neither; nothing is forwarded (see 36) |
| 17 | Guest Wi-Fi is a separate network or VLAN | good; confirm it cannot reach the server's network once the router list is known |
| 18 | Cameras, thermostat, locks: not sure | check when photographing the routers; the NDI cameras (50) are on the media network by necessity |

## Alexandria

| # | Answer | What it decides |
|---|---|---|
| 19 | A single Mac | no route box needed (21): that Mac runs Tailscale itself and binds to the domain over it; docs/NETWORK.md option A |
| 20 | ISP box, upload unknown | fine for one Mac |
| 21 | No spot for an always-on box | see 19 |
| 22 | Never streams from Alexandria | no bandwidth rule there |

## People and accounts

| # | Answer | What it decides |
|---|---|---|
| 23 | Usernames are `first.last` | `bradly.dyer`, `bryant.sanders`, `vanessa.sanders`, `kristina.robinson`. The Mac enrol script maps an old local name to the new one with `--map old=first.last` |
| 24 | Staff and media only, for now | first accounts: the admins below, the staff, the media team; volunteers through department accounts (27) |
| 25 | Admins: Apostle Bryant Sanders, Pastor Vanessa Sanders, Kristina Robinson, Bradly | four members of `Domain Admins`; each gets the admin desktop; SSH keys only for Bradly unless asked |
| 26 | Passwords never expire; 12 characters minimum; lockout after 10 failures | the default in docs/DIRECTORY.md stays |
| 27 | Department accounts exist: Children's Department, Media, Inedge, and others | shared department logins instead of personal volunteer accounts: one directory user per department, in its own group, with its own share (37). The full list of departments is still needed |
| 28 | No kids check-in station yet | nothing to join; the `Kids-Check-in` group waits |
| 29 | A shared church Google account exists; one other person knows it | it is the Tailscale login (42) and the YouTube token's owner |

## Macs

| # | Answer | What it decides |
|---|---|---|
| 30 | Six to ten Macs | enrol them one at a time over two or three days (SETUP-GUIDE day 6) |
| 31 | No Windows PCs | the "joining a Windows PC" parts are reference only; Guacamole needs only VNC (macOS Screen Sharing) |
| 32 | One person per login, except the media Mac | enrol pairs each local user with `first.last`; the media Mac keeps a shared `media` login |
| 33 | The media Mac's video is small enough to move to the server | it goes to the new `recordings` share on the Synology (51) |
| 34 | Apostle Bryant's and Pastor Vanessa's personal Macs leave the building | personal Macs: do NOT bind them to the domain. They get Tailscale and the dashboard portal, and the home-sync agent if they want a folder backed up. Binding a personal Mac hands its login to the church directory, which is the wrong direction for a personal machine |
| 35 | Nothing is managed | no MDM to untangle |

## Files and shares

| # | Answer | What it decides |
|---|---|---|
| 36 | Tailscale only, nothing exposed | no port forward, no public Caddy door; `public_url` stays empty; share links work for people on Tailscale (a link to someone outside needs the public door, so it is off until he says otherwise) |
| 37 | Shares: staff, leadership, media, kids, graphics, plus Children's Department, Inedge, Worship / music, Recordings | nine shares, each with a group: `childrens-department`, `inedge`, `worship`, `recordings` added to `config/samba/smb.conf.template` and docs/DIRECTORY.md |
| 38 | Proclaim assets: synced local copy on the media Mac | Syncthing between the media Mac and the `graphics` share (templates/syncthing) |
| 39 | Share links: 7 days, everyone | the default stays |
| 40 | Giving, payroll and counselling records live on a local Mac that will not be on the server | nothing to configure; that Mac is not enrolled |
| 41 | Data per year: no idea | the dashboard's disk widget answers it after a month; Synology sizing waits for 4 |

## Remote access and security

| # | Answer | What it decides |
|---|---|---|
| 42 | One church Tailscale login for every device | the shared Google account (29); free plan |
| 43 | Everyone with an account may reach the server from home | every account gets the portal address; staff laptops get the Tailscale app |
| 44 | Remote desktop into the media Mac only | one Guacamole connection (VNC to macOS Screen Sharing); sleep off on that Mac |
| 45 | No cyber insurance or written policy | the defaults stand |

## Automator, backups, the note

| # | Answer | What it decides |
|---|---|---|
| 46 | The automator keeps running on the Windows PC until the server's timer is on, then stops | SETUP-GUIDE day 3 keeps that order |
| 47 | More backup history | `keep_daily = 30, keep_weekly = 12, keep_monthly = 24` in `config/arise.toml.example`; how much Synology space that needs waits for 4 |
| 48 | Off-site copy: nowhere yet | stays open; a fire still takes the server and the Synology together |
| 49 | No daily note | `[notify]` stays empty; `arise-notify.timer` sends nothing; the dashboard's Needs-you list is the only alarm. The installer does not enable the timer |

## Livestream and recordings

| # | Answer | What it decides |
|---|---|---|
| 50 | StreamYard with the OBS virtual camera; NDI from the media Mac running Proclaim for lower thirds; the cameras are NDI too | NDI is the heaviest thing on the church network: 100 to 200 Mbit/s per full-NDI source, discovery by mDNS. Rules in docs/NETWORK.md: every NDI device and the streaming Mac on the same gigabit wired segment, never Wi-Fi; the server may share that segment (an unmanaged gigabit switch copes) but its nightly backup must not run during a service; no VPN profile on the streaming Mac; Proclaim's media Mac is a Mac (follow-up), so it is enrolled like the others |
| 51 | Recordings go to YouTube AND the server | a `recordings` share on the Synology; the media Mac copies each service there (Syncthing folder or a drag); restic EXCLUDES `recordings` by default (a 6 GB file a week would swallow the backup history) and the Synology's own RAID is its protection until an off-site copy exists (48) |

## Day to day

| # | Answer | What it decides |
|---|---|---|
| 52 | No second person yet | the printed checklists in docs/MOVING-DAY.md and docs/SETUP-GUIDE.md matter more; a second admin exists (25), so at least the dashboard is not single-person |

## Still needed

- Sunday: questions 1 to 7.
- A photo of the Cisco's sticker (10) and of each router's LAN page (12).
- The full list of department accounts (27) and the people in staff and media (24).
- The UPS model (8), for `nut`.
