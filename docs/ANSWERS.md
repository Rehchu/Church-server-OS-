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

## The Pineville equipment (Oct 28, later the same day)

| Fact | What it decides |
|---|---|
| Modem → Netgear router A → the switch → Netgear router B in the office; the Google Mesh (2 or 3 points) hangs off Netgear A; the switch is unmanaged and may be a Netgear, not a Cisco | three stacked networks (double NAT behind A). The server goes wired on the switch, on A's network, with a DHCP reservation. B and the Mesh hand out the server as DNS. docs/NETWORK.md § The Pineville network as it is |
| The office user is wired to Netgear B | the office Mac joins the domain through B's NAT; it works because every directory and share connection is started by the Mac |
| The media / streaming Mac is on the Mesh Wi-Fi; the NDI cameras are split between the Mesh and the switch | NDI discovery does not cross the NAT; sources are added by address. Guacamole cannot reach that Mac through the NAT, so the media Mac runs Tailscale and Guacamole uses its Tailscale address |
| **Bradly: leave the network as it is; leave the streaming Mac on Wi-Fi; the infrastructure cannot be changed at all, not even a router setting** | no re-wiring, no AP mode, no VLANs, no DHCP reservation, no DNS change on any router. Static address in netplan on the server; `/etc/resolver` file on each Mac (`bind-mac.sh --dns`); Tailscale for everything the NATs block, including the Synology if it is not on Netgear A's network. NETWORK.md § The Pineville network as it is |
| Alexandria's equipment: unknown | one Mac with Tailscale needs nothing from the router there |
| The NDI cameras are on their own unmanaged switch, which plugs into the Mesh (not into Netgear A's switch) | the cameras and the streaming Mac share the Mesh's network, so NDI discovery works between them as it does today; nothing on the server side is involved. The Network app cannot see them (they are behind the Mesh's NAT) and does not need to |
| Router A's own settings page does not show the things on the switch | expected: a router lists only the DHCP leases it remembers. The Network app's ARP scan asks the wire itself. NETWORK.md § Why Router A's own page does not show them |
| Router B is 10.0.0.1 (certain; the office printer was set to about 10.0.0.8). Router A is 192.168.0.1 or 10.0.0.1 (exact addresses on Friday) | if A were also 10.0.0.1, B's network would overlap its upstream and nothing behind B could reach the server; the plan assumes A is 192.168.0.1 until Friday. `[[routers]]` for Netgear B gets `host = "10.0.0.1"` |
| Security cameras (PoE) are on Router A's switch, do not work, and Router A does not list them | most likely no power (the switch is probably not a PoE switch) or factory addresses from another range. The Network app's Wide scan and Find cameras tell the two apart; Frigate records them once they are reachable. NETWORK.md § The security cameras. New hardware (a PoE switch or injectors) is the only fix for the first case |
| "It needs to check EVERYTHING that is connected to the switch" | the **Network** app (16) and `arisectl devices scan`: an hourly ARP scan of Netgear A's wire with names, makers, kinds, joined-or-not, first and last seen, and a flag on anything new. Behind-the-NAT devices show as their router, by the nature of NAT |
| **Bradly: no IP address, network setting or router change of any kind** | the server keeps the address Netgear A gives it and pins it on itself (install.sh step 2b); no device changes address; every Mac-side setting is a file on that Mac; Tailscale does the rest. There is nothing left on the list that touches a router, and the router pages no longer need a photo |

| Mass email to the church family through Resend; contacts exported from Wix; "emails will come from Arisenow.church@gmail.com or something like that"; Proclaim does the lobby signage | the **Mail** app (19) and `arisectl mail`: Wix CSV import into a Resend audience (unsubscribes handled by Resend), the house template, a test send, broadcasts with a typed `send`. Resend cannot send FROM gmail.com: `from_email` must be at a domain verified in Resend (arisecenla.church, or arisenow.church if the church owns it); the Gmail is the reply-to. Proclaim has no Linux version; it stays on its Mac, and `/signage` is for a screen with no Mac behind it |

## Still needed

- Sunday: questions 1 to 7.
- Where the Synology is plugged in: on Netgear A's network it mounts directly; elsewhere it gets the Tailscale package. No cable moves either way.
- The full list of department accounts (27) and the people in staff and media (24).
- The UPS model (8), for `nut`.
- Friday: the Resend account, the domain to verify in it, the API key into `/etc/arise/secrets/resend-api-key`, the Wix contacts export.
