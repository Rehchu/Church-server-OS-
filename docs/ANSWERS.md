# Answers from Bradly (Oct 28 2026) and what they decide

The multiple-choice questions in docs/QUESTIONS.md, answered in the chat
pop-ups. Later answers supersede earlier ones where they conflict; see the
Oct 30 hardware decisions H1–H6 for the current server, NAS, encryption and app plan.
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

## Round 2 (Oct 28, the same night): fifty more

Fifty pop-up questions about what to add, improve and polish. His words are
quoted where he typed them. The build order is his (50): Feel first.
docs/ROADMAP.md turns these into releases.

| # | Question, in a few words | Answer | What it decides |
|---|---|---|---|
| 1 | Boot like a product? | Splash, no sound | a Plymouth theme in the house style; silent boot |
| 2 | YouTube Partner progress widget? | Yes, desktop only | subscribers toward 1,000 and watch hours toward 4,000 from the automator's numbers; not on the lobby sign |
| 3 | House Lights Down mode on Sunday morning? | Yes, automatic | from an hour before a service the desktop dims admin noise and shows stream, checklist, countdown, one-tap doors; off after |
| 4 | A sermon podcast feed? | Yes, build it | ffmpeg pulls audio from each recording, an RSS feed for Spotify and Apple, the 16:9 art; episodes automatic, titles approved by Bradly |
| 5 | Time Machine backups of the Macs? | Yes, every church Mac | a Time Machine share on the Synology; needs space about equal to each Mac's used disk (estimate) |
| 6 | A print server? | "It's not an HP printer. It's a different one. But I'd like all devices to be able to print from it" | CUPS with AirPrint on the server once the model is known; the printer sits behind router B, which the server can reach |
| 7 | A morning report written by Claude? | Yes, every morning | a 06:00 run on the box's own data; summarises, never invents |
| 8 | A clip cutter for Shorts? | No | nothing built; cutting stays on the Mac |
| 9 | The portal as a phone home-screen app? | Yes | a web app manifest; Add to Home Screen on iPhone and Android |
| 10 | Push notifications? | Yes, to me only | web push to Bradly's phone: failed backup, stream down, new device |
| 11 | Two-step sign-in for admins? | "2 step authentication using Microsoft Authenticator"; Oct 28: "2fa is optional, but if they do opt in, then it uses Microsoft Authenticator" | Two-step is optional for everyone; whoever turns it on enrols Microsoft Authenticator (TOTP, no Microsoft account needed). Nobody is forced |
| 12 | Who ticks the Sunday checklist? | Anyone signed in | members included; the audit log says who |
| 13 | Jellyfin for whom? | Staff only for now | no lobby channel, no family access yet |
| 14 | Recordings kept how long? | Forever (YouTube is also the archive) | nothing is ever deleted; the Synology's size is the only limit |
| 15 | Transcript pages per sermon? | Yes, for admins and staff | a cleaned, searchable, printable page under Sermons; no sung words |
| 16 | The website pulling from the server? | Not from the server; the site stays separate | no public feed is built for the site |
| 17 | What may Claude do on its own? | Draft YouTube titles and descriptions for approval; explain any failure in plain English; answer staff questions in the portal | three Claude features, all read-only on the box, nothing live without Bradly's approval |
| 18 | Where does the morning report land? | Dashboard only | a widget and a page; no email, no push for it |
| 19 | A name for the OS? | ariseOS | the splash, the About window, the docs say ariseOS; "Arise Server" stays the name of the service and the repo |
| 20 | Codenames? | Books of the Bible | the next release is "Genesis"; docs/ROADMAP.md |
| 21 | Guest speakers' accounts? | "They email the media team everything they need" | no guest accounts, no expiry feature |
| 22 | Who makes share links to outsiders? | Everyone, as now | 7 days, revocable; unchanged |
| 23 | An audit trail? | Yes, admins see it | sign-ins, shares, user changes, checklist ticks, kept a year, nothing deleted from the dashboard |
| 24 | When someone leaves? | "Disable the login after 30 days just in case they come back. Move the files to the next appropriate member or account." | an offboarding step in Directory: a 30-day grace timer, then disable; a "move files to" picker |
| 25 | Which folders mirror with Syncthing? | The thumbnails folder (the automator's output) and the office documents share, plus Proclaim assets | three Syncthing pairs; nothing else |
| 26 | The printer? | On router B; "it's a weird brand"; info coming | CUPS waits for the model |
| 27 | Kids check-in? | Not planned | nothing built |
| 28 | A volunteer rota? | Keep what we use now | nothing built |
| 29 | When is the Hub built? | No date yet | the move is written up, not scheduled |
| 30 | Pineville's VPN after the move? | Decide at the move | both options stay in MOVING-DAY |
| 31 | A second domain controller later? | Yes, plan for it | a "second DC" installer mode goes on the roadmap |
| 32 | Hardware purchases? | None of these yet | no PoE switch, second SSD or Coral stick for now |
| 33 | The wallpaper? | The ink and red stage, as now | unchanged |
| 34 | Desktop sounds? | All of them, quiet | dock click, checklist chime, failure tone, all low |
| 35 | About-window flair? | Fun, do it | the week's verse, service count, hours streamed, the latest title, from real data |
| 36 | A light "Bone" theme? | Yes, a switch in Control Center | per browser; the monitor stays House Lights Down |
| 37 | Newsletter rhythm? | Only when there is news | no reminder, no schedule |
| 38 | SMS alerts? | Not now | nothing built |
| 39 | Members edit their own contact details? | No, staff keep the list | one source: the Mail app's contacts |
| 40 | Discord posts? | Yes, failures and the Sunday "all green" | a webhook; the daily note stays off |
| 41 | Channel stats in the dashboard? | Yes, a Channel page under Sermons | views, top video, Shorts count from the automator's data; no extra quota |
| 42 | Thumbnails and podcast art made on the server? | Yes, on the server | pick a frame in Sermons; the house layout rendered in both sizes; Bradly approves before anything is set |
| 43 | The hold list editable in the dashboard? | Yes | add, remove, a note and a name per hold; holds.json stays the source |
| 44 | Stream watch on Sundays? | Yes | Uptime Kuma pings the live page and StreamYard every 30 s; push, Discord and a red monitor if it drops |
| 45 | Training? | A built-in walkthrough on first sign-in | five steps in the portal, once per person |
| 46 | A closet-door card? | Yes | a one-page PDF the installer writes: the commands, the Tailscale address, the backups, who to call |
| 47 | A restore drill? | Yes, monthly, automatic | one random file restored from last night's backup to a scratch folder and compared; the result in the dashboard |
| 48 | UPS shutdown timing? | When the battery is nearly flat | nut shuts the box down on the low-battery signal, not on a timer |
| 49 | The showpiece? | The desktop on the monitor | polish goes there first: the shell, the screensaver, Sunday mode |
| 50 | Build order? | Feel first | v0.7 "Genesis" is the Feel block; docs/ROADMAP.md |

## Round 3 (Oct 28): what Windows 11 and macOS have, and the basics any OS needs

Forty pop-up questions. Bradly's words quoted where he typed them. Builds as
v0.8 "Exodus"; docs/PARITY.md is the full map of what the two desktops have
and where ariseOS stands on each.

| # | Question, in a few words | Answer | What it decides |
|---|---|---|---|
| 1 | Trash for the shares? | 30 days, then it empties itself | a Trash on every share (Samba recycle for the Macs, the portal too); anyone puts back their own file; `arise-trash.timer` empties what is older than 30 days; emptying early is Bradly's click |
| 2 | Previous Versions in Finder? | Yes, everyone for their own files | right-click a file, see the nightly copies, put one back beside the original; members for their own, admins for anything |
| 3 | A Settings app, one place? | Yes, build it | System Settings becomes the one window: appearance, users, sharing, backups, updates, time, notifications, about |
| 4 | A Software Update app, who clicks? | Security automatic, I click the rest | security patches stay unattended; everything else is listed with a badge and waits for his click, then installs in the window (25) |
| 5 | An App Store? | "The 24 app templates should already be preinstalled, but definitely an App Store for other Linux programs that are free!" | all 24 templates deployed at install (the heavy ones stopped until started, with the RAM shown); a catalogue of further free self-hosted apps in the Store |
| 6 | Activity Monitor? | Yes, admins | processes and containers, CPU, memory, disk, network; End Process with a confirm |
| 7 | A Logs app? | Yes, admins | the journal by service, the arise logs, search, the last error highlighted |
| 8 | An Automations app? | Yes | every timer live: next run, last result, run a preview, pause one; the real automator still refused while its timer is on |
| 9 | A Storage pane? | Yes | disk by share and by app, the biggest files, a "not changed in a year" list; deleting stays his click |
| 10 | A church Calendar everyone can subscribe to? | Yes, one calendar | services and events on the server; an ICS feed every Mac and phone subscribes to; staff add events |
| 11 | Notes? | Trilium (the template) | the Notes icon opens Trilium in a window; no second notes app |
| 12 | Photos? | Yes, Immich for staff | the Immich template; staff phones upload over Tailscale |
| 13 | A Weather widget? | Yes | Pineville from Open-Meteo, no key; a line in the morning report |
| 14 | Calculator and Clock? | Yes, both | both in Launchpad and Spotlight; Spotlight answers a sum |
| 15 | Edit a text file in Finder? | Yes | .txt and .md open in place with a Markdown preview |
| 16 | Compress, Get Info, Recents? | All three | zip a folder to download; file info; what you touched this week |
| 17 | Screen Sharing of the closet monitor? | Yes, me only | wayvnc on the monitor's display, reached through Guacamole over Tailscale; Bradly first, admins later if he says |
| 18 | "Open on my Mac"? | Yes | a button in the portal's Finder opens the same folder in the Mac's Finder over the share |
| 19 | Snap windows? | Yes | drag to an edge for half, a corner for a quarter; Ctrl/Cmd+arrow tiles |
| 20 | Hot corners on the monitor? | No | nothing built |
| 21 | A break-glass local admin? | Yes | `arise-rescue`: console and SSH only, never the dashboard; its password on the closet card; every use logged and pushed |
| 22 | Disk encryption? | Encrypt the data disk, TPM unlocks it | LUKS chosen at the Ubuntu install; `arisectl encrypt tpm` binds the key to the Dell's TPM so it boots alone; the passphrase stays the fallback on the closet card |
| 23 | OS rollback? | Yes, snapshot before every update | a system snapshot (Timeshift) before each update, the last five kept; church files are in the backup, not the snapshot |
| 24 | Reinstall from backup? | "Yes, with the synology holding the backup to the server as well!" | `arisectl reinstall` rebuilds a fresh Ubuntu from the Synology's restic repository: config, the domain's database, users, shares, apps, secrets. The Synology holds the server's backup, as it does today; read that way, nothing changes about where the backup lives |
| 25 | The maintenance window? | Saturday 03:30 | updates he has clicked, and any reboot they need, apply Saturday 03:30; never during a service |
| 26 | Log retention? | 1 year | the journal and the arise logs kept a year |
| 27 | Failed sign-in lockout? | None | no fail2ban, no domain lockout; everything is behind Tailscale or inside the building |
| 28 | A virus scan of the shares? | Weekly scan, quarantine with a report | ClamAV Sunday night over the shares (video skipped); a found file moved aside; the list in the dashboard and a push |
| 29 | HTTPS inside the building? | Church CA, padlock on every Mac | Caddy's internal CA in front of the dashboard; `enroll-mac.sh` trusts the root once; phones on Tailscale use Tailscale's certificate |
| 30 | Monitor power? | Off overnight, 23:00 to 06:00 | the panel sleeps at 23:00 and wakes at 06:00; a key wakes it anytime |
| 31 | Restart and Shut Down in the flame menu? | Yes | admins, a confirm, refused during a service; "Restart the dashboard" and "Restart the domain" as gentler steps |
| 32 | Accessibility? | Yes | larger text, reduce motion, high contrast in Control Center; Tab reaches everything |
| 33 | Auto theme by daylight? | Manual only | the theme stays whatever was last picked |
| 34 | A What's New note after updates? | Yes | ten lines at most, in About and the morning report, from CHANGELOG.md |
| 35 | A Help app? | Yes | the docs rendered in the dashboard, searchable; F1 or Ctrl+? opens it; a shortcut sheet |
| 36 | Password rules at change? | Yes | a strength meter and the domain's rules in plain words |
| 37 | A licence? | MIT | LICENSE at the root, Bradly's name on it |
| 38 | Idle sign-out in a browser? | Never, until they sign out | the sign-in cookie lasts a year; the closet monitor still locks at ten minutes |
| 39 | A Font library? | Yes | `Media/Fonts` on the share; every enrolled Mac installs what is there on the hourly sync |
| 40 | Resource caps on the apps? | Yes, cap every app | memory and CPU limits from each template; the domain and the dashboard always have room |

## Round 4 (Oct 28, later): one hundred more, the whole OS

Bradly: "Ask another 100 questions covering the entirety of the OS to make
it the best thing ever! This is going to be the final batch until I get the
info from the equipment." He also pasted a list of free desktop programs
(LibreOffice, OnlyOffice, Thunderbird, GIMP, Krita, Inkscape, Kdenlive,
Shotcut, VLC, Dolphin, Ark, Flameshot, GParted, Heroic, Wine, Okular, Samba,
Nextcloud, Postfix+Dovecot, CUPS, PostgreSQL, Nginx, Docker, restic, Netdata)
with "If you can use any of these as well, use them! If not then they can be
in the App Store!" and "Any and all apps installed should match our theme,
colors, etc! Not the native app stylings." The codename is his: Exodus.

Desktop programs cannot run inside a browser desktop as themselves; they run
on the server in a container and open in a browser window (the way Kasm and
linuxserver.io do it), saving to the shares. That is what "in the Store"
means below.

| # | Question, in a few words | Answer | What it decides |
|---|---|---|---|
| 1 | The desktop programs (GIMP, Inkscape, Krita, Kdenlive, Shotcut, LibreOffice, Audacity) in the browser? | In the Store, started when needed | installed and ready, stopped until Open, stop themselves after an hour idle; the memory cost shown |
| 2 | Documents in the browser? | OnlyOffice Docs, opened from Finder | click a .docx in the portal, edit in place, saved to the share |
| 3 | An internal mail server? | Yes, an internal-only mail server | Postfix + Dovecot on the box; see 5 to 7 |
| 4 | The theme rule for apps? | Set everything each app allows; frame the rest | house red, ink, the flame, Anton and Oswald wherever an app takes them; an app that takes nothing keeps its look inside our window |
| 5 | Who gets a mailbox? | Staff and departments, first.last@ad.arisecenla.com | one box per staff or department account |
| 6 | How is it read? | "They should get it through their personal email, apple mail, or whatever mail service they use on their phone." | each account's mail is forwarded out through Resend's relay to the person's own address; nothing inbound from the internet |
| 7 | Where does the personal address come from, and replies? | a field on their Directory account; replies go back to the sender's personal address (Reply-To) | admins type it once; the person can change it |
| 8 | Proclaim under Wine on the server? | Try it as an experiment, not relied on | a Store entry marked experimental, off by default |
| 9 | Games? | Heroic + a few FOSS games on the lobby TV | a "Game night" Store entry, off by default |
| 10 | The lobby TV? | Keep Proclaim; the server's sign page is a backup | nothing changes on the TV |
| 11 | Announcements? | Staff, in the Calendar app | an event marked "announce" shows on the sign and in the week widget |
| 12 | The Dock? | Auto-hide, slides up from the bottom | mouse at the bottom edge brings it back |
| 13 | The Dock's default set? | Finder, Overview, Sunday, Sermons, Calendar, Mail, Store, Settings, Terminal | each person pins or unpins their own |
| 14 | The sign-in screen? | A list of faces to click, like a Mac | see 16 |
| 15 | A greeting after sign-in? | "Good morning, Bradly" with the day's verse reference | a three-second toast |
| 16 | Whose faces, and on the monitor? | Each person uploads their own; admins and staff listed on the monitor | members type their name on their own devices; no photo = initials on red |
| 17 | Clock and dates? | 12-hour, Sunday first, US dates, °F | |
| 18 | The screensaver? | Clock, next service, the verse, the channel's thumbnails slowly | plus the weather and the week's announcements |
| 19 | The lock and sign-in line? | "Arise Church · Pineville" and the next service | |
| 20 | Folder layout? | "Each user has a folder, admin access them all! Users can't access other users folders. So documents would all merge into one document folder for admins, photos, etc." | a personal folder each; admins get merged views (All Documents, All Photos, …) with the owner labelled; members never see another person's folder |
| 21 | Home quota? | "Depends on the synology storage. I still need to get drives for it." | no quota until the Synology's drives are known (see 30) |
| 22 | Biggest upload? | 10 GB, resumable | chunked uploads that continue after a drop |
| 23 | Share link expiry? | Never, until removed | changeable per link. **Replaced by round 7, 47:** admins only, 7 days |
| 24 | Starting folders in a home? | Documents, Photos, Videos, Music, Downloads | created at first sign-in; these are what the admin's merged views merge |
| 25 | A shared space? | Yes: one Church folder for all, plus a folder per department | |
| 26 | Windows PCs? | "Yes add windows pc capabilities just in case we get them at a location" | Windows joins the domain the same way; the shares as network drives; a join script and doc |
| 27 | Downloading recordings? | Admins and Media; everyone can stream in the browser | |
| 28 | An off-site backup copy? | Not now | |
| 29 | Back up the recordings? | "The synology isn't even setup yet. It needs 4 new hard drives. Will get the model of it for you Friday so you can recommend a setup for user data, storage, etc." | a Synology layout recommendation waits for the model on Friday |
| 30 | Where the restic key lives? | The closet card only | |
| 31 | A USB drive plugged into the server? | "It auto syncs everything to the appropriate folder or location" → Into the folder of whoever is signed in on the monitor | a plugged-in drive is imported, sorted by type (Photos, Videos, Documents, Audio), virus-scanned, into the signed-in person's home; the stick is never changed; a push when done |
| 32 | Phone photos without cables? | Through the portal's upload only | Immich stays the library; the phone uploads through the portal |
| 33 | SSH? | Keys only, passwords off; arise-rescue is the exception at the console | |
| 34 | Keep Cockpit? | Keep it, admins only, for the rare deep thing | linked from Settings |
| 35 | Disk-space warning? | 75% | a push at 75% |
| 36 | Temperature alerts? | Just the morning report line | |
| 37 | A weekly summary? | Yes, Monday morning, in the dashboard and a push | |
| 38 | Push at night? | Everything, any hour | no quiet hours |
| 39 | Tailscale access? | Admins now; staff when they ask | |
| 40 | A screen per campus after the move? | Yes, any old PC or a Raspberry Pi per campus, same desktop, a campus badge | a kiosk image that boots into the dashboard over Tailscale |
| 41 | Wake-on-LAN for the Macs? | No | |
| 42 | Remote screen of a church Mac? | "I never miss a service" | nothing built |
| 43 | May Claude fix things itself? | Fix small things itself, tell me after | restart a stuck service, re-run a failed backup, clear a full log; bigger waits for him |
| 44 | Who can talk to Claude on the box? | "Claude is available to me only" | Bradly only; members get the help box |
| 45 | Who edits Claude's notes (CLAUDE.md on the box)? | Claude edits freely | |
| 46 | "Ask Claude about this" on red items? | Yes, everywhere something is red | opens Claude with the facts pasted in; Bradly only (44) |
| 47 | What buzzes the phone? | Everything: failures (backup, stream, domain, disk, UPS), Sunday all-green and the Monday weekly, security (new device, arise-rescue used, a virus found), housekeeping (updates waiting, an import finished, a quota warning) | |
| 48 | The phone home screen? | Needs-you list, next service, backups, stream, the checklist | |
| 49 | A member's first screen? | Their files, the Sunday list, this week's calendar, the verse | |
| 50 | Members see who else has an account? | No; only staff and admins see the list | |
| 51 | Default Bible translation? | KJV | public domain, offline |
| 52 | A Songs app for the CCLI report? | Yes | every song per service from the automator's credits; a count per song; an export in CCLI's shape; numbers only from the song bank |
| 53 | Where ariseOS updates come from? | GitHub releases, checked daily, installed on his click in the window | What's New shown before the click |
| 54 | Password again for dangerous clicks? | Yes, password again, remembered for five minutes | on top of typing the name |
| 55 | The Synology's four drives? | "Probably will just have 3 as one big drive, and 1 for backups of documents or something. Need to have important items backed up on there only. The other 3 drives are one big drive." | three drives as one volume (recordings, media, Time Machine); the fourth drive alone holds the server's restic backups and the documents; the layout proposal waits for the model |
| 56 | Drive size? | 4 TB each | about 8 TB usable on the three-drive volume with one-drive protection, 4 TB on the backup drive |
| 57 | Where files live? | "Depends on the files. But the server disk should be utilized too!" | homes, shares and the apps on the server's disk; recordings, photos and backups on the Synology; Storage shows both |
| 58 | Time Machine space? | "Time Machine set to hold 2 Mac backups at a time per device" | the share keeps the two newest backups per Mac and thins older ones |
| 59 | The install itself? | A short on-screen wizard, flags still work | church or staging, admin password, Synology, Tailscale, encrypt; then it runs |
| 60 | First thing on the monitor after install? | The sign-in screen only | no QR on screen; the closet card carries it |
| 61 | Power back after a cut? | Yes, auto power-on; the installer tells you the BIOS setting | the box comes back on its own; the TPM unlocks the disk |
| 62 | Internet down? | Everything inside keeps working; YouTube, mail, weather and Claude wait | an "offline" chip; the automator skips the night with a note |
| 63 | The per-campus screen? | The same desktop, signed in as a campus account, badge in the bar | a kiosk image that boots, joins Tailscale, opens the dashboard |
| 64 | What campuses can do? | Everything an admin or member can, by who signs in | same rules everywhere |
| 65 | Move day? | "I'll probably move everything on a day nobody is there. So there should only be Down time for maintenance that day." | no Pineville cache box; MOVING-DAY.md plans one quiet day |
| 66 | The Campuses app? | Each campus: online, its screen, its devices, who signed in there | live from Tailscale and the sign-ins |
| 67 | What the server gives a Windows PC? | A join script, drive letters, and the church certificate; nothing else | one PowerShell file from the dashboard; no group policy |
| 68 | Mail attachments? | Larger attachments, 100 MB | |
| 69 | Who may send internal mail? | "anybody with an account that was registered." | every domain account may send; delivery is inside and to personal addresses only |
| 70 | Two people in one document? | They edit together, live | OnlyOffice co-editing; saved to the share when the last closes |
| 71 | Window chrome? | Mac-style, top-left | |
| 72 | Where Store apps open? | In a window on the desktop, with a pop-out to a tab | |
| 73 | What Spotlight searches? | Also inside documents, the calendar, mail subjects, the Bible, and sums | a nightly text index of the shares |
| 74 | Quick Look previews? | Images, PDFs, video with scrubbing, audio, text, Office files | Office files through OnlyOffice; video streamed, not downloaded |
| 75 | Songs per service? | The automator's credited songs, confirmed by you per service | tick "reported"; export in CCLI's shape |
| 76 | Thumbnail approval? | "Option A, Even though i'll still probably do everything Sunday and Monday night through Claude Web." | a push with the image, Approve or Change; the Sermons app too |
| 77 | Post the live link to Discord? | Yes, to a channel you name | the watcher posts once when the stream starts |
| 78 | A checklist nudge? | Yes, one push at 9:30 | names the open items |
| 79 | Audit log kept? | Forever | |
| 80 | Who exports the mail list? | Admins only, and the export is logged | |
| 81 | Immich and faces? | Staff only can see Immich; no sharing links from it | public sharing off |
| 82 | A leaver's mailbox? | Mailbox deleted with the account | files still move to the next person (round 2, 24) |
| 83 | Easter eggs? | Yes, a few quiet ones | the Konami code lights the flame; a verse typed in Spotlight shows it; the About flame flickers on the anniversary |
| 84 | A founding date? | "All i know is 2018" | the year only; no day is invented; the flicker waits for a date |
| 85 | Which events make a sound? | Checklist tick, a failure, the lock, a finished import, the greeting | |
| 86 | A startup sound? | No, silent | |
| 87 | Scanning? | "Scans land in the Signed-in person's documents, the Local mac, and an Option to Share." | scan-to-share when the printer can; a copy to the Mac; a share link offered |
| 88 | Jellyfin libraries? | Service recordings, worship, graphics loops, podcast audio | read from the Synology |
| 89 | Internal chat? | "Church doesn't use Discord, I'll be using it for Server monitoring and Alerts. As well as Anything Else that i can do with it. The Church doesn't have a Groupchat app or anything." | Discord is Bradly's monitoring channel, not the church's chat; no chat server runs; Mattermost and Element stay stopped in the Store |
| 90 | Nextcloud? | In the Store, stopped, for whoever wants it | |
| 91 | One disk: split it? | "It depends on the Storage of the Optiplex. I'll have FULL specs for you Friday." | the partition plan waits for the Dell's disk size; both shapes are in INSTALL.md |
| 92 | Reboot with people signed in? | "Reboot after everybody is signed out, but there's never anybody at the church saturday anyway, so it should be fine!" | the Saturday reboot waits until nobody is signed in, then goes; a note in the weekly if it had to wait |
| 93 | A prayer-request box? | No; prayer requests stay off the server | like counselling records |
| 94 | Birthdays in the weekly? | Yes, in the weekly, if the field exists | never guessed; staff only |
| 95 | (unprompted) The automator's backups? | "The Arise Automator will need to keep backups on my personal PC like it does now! i'll make sure the automator has the Repo up to date as well so it syncs to the Synology or wherever correctly!" | the PC stays the automator's working copy and keeps its own backups; the server pulls the automator from the GitHub repo Bradly keeps current (the 04:00 mirror), runs the nightly job from that copy, and restic backs it up to the Synology; nothing on the server overwrites the PC |
| 96 | Which machine runs the real 02:05 job? | The server runs it; the PC keeps the copy and the dev work | the PC's timer goes off at the move; the server's timer is the only writer; holds.json lives in the repo |
| 97 | How the server gets YouTube access? | "Give me a markdown on what to ask that specific chat about how we can do it since it handles ALL the automations, and i'll let you know." | docs/ASK-THE-AUTOMATOR-CHAT.md is that markdown; the decision waits for the automator chat's answer |
| 97b | The automator chat's answers (Oct 28) | SERVER_HANDOFF.md in Rehchu/arise-youtube-automation, commit 'Server-ready automator', pasted here by Bradly | the server gets its own Desktop OAuth client and token, signed in headless; runner.json on the PC decides who runs (the PC until Bradly switches); ariseOS caps 4,000 (2,000 Sun/Mon); docs/AUTOMATOR.md carries it out |
| 97c | The revised handoff (Oct 28, Bradly's decisions) | the four job-state files move to ARISE_STATE_DIR and are untracked; `sunday-playlist-reassign` parked; the server's cap 6,000 every day; both repos on the server as a searchable archive for Claude | docs/AUTOMATOR.md, docs/ARCHIVE.md; the revision commit still has to be pushed from the PC |
| 97d | (unprompted) Working on the automator from the server | "The chat will be accessible from Claude desktop when it's installed on there. He can work on it from the server when it's up" | Claude Desktop (Linux beta) on the box, Bradly only; claude.ai/code in Firefox and `claude --teleport` also reach the automator chat; never in the job's checkout (docs/CLAUDE-ON-THE-BOX.md) |
| 98b | (unprompted) The repos on the server | "We would need designated folders for all the repos or download all the arise repos to the server and keep them synced with GitHub and the server"; then: two-way every 15 minutes with automatic pushes; the 8 Arise repos; one fine-grained token; the search archive stays at the 2 repos | /srv/arise/repos (docs/REPOS.md); AriseHub pull-only and the automator's main held back by default, because a push there deploys or contradicts the handoff |
| 98 | Trash on the media share? | 7 days on the media share | 30 days everywhere else; the Storage pane shows the Trash's size |
| 99 | A staff tier? | Yes: admin, staff, member, by group | staff = anyone in Staff or Media; Photos, Notes, transcripts, calendar events, internal mail are theirs |
| 100 | Transcripts from where? | Whisper on the server overnight; YouTube captions as the fallback | one recording a night after the backup; never during a service; sung words never written |
| 101 | Discord channels? | "Add a #daily to option 1 and then it's approved so 4 channels total! i'll get discord setup right now if you'd like!" | four webhooks: #alerts, #sunday, #weekly, #daily (the morning report goes to #daily); docs/DISCORD.md says what to set up |
| 102 | The monitor when nobody is signed in? | Yes, the glance view when idle; sign in for anything else | next service, backups, attention, stream; nothing clickable, no names or files |
| 103 | Immich's library? | Watch Media/Photos and every staff member's Photos folder | external, read-only; deleting in Immich never deletes a file |
| 104 | Department accounts? | "Staff can be assigned individual accounts, but they're also assigned to a department or multiple departments. when they log in with their individual login, they get access to the department account stuff as well!" | everyone has their own account; departments are groups with their own share folder; membership grants the department's files and mail; a shared department login is not needed |
| 105 | A rehearsal at home? | Yes, rehearse the install and the reinstall at home first | REINSTALL.md gets the rehearsal checklist |
| 106 | (unprompted) Two Windows PCs at the church | "we have 2 Windows PCs at the Church, so technically, One could be at Arise Church Alexandria, while the other is at Pineville, or i Run One from my house that is linked to the Pineville location so i can do EVERYTHING from the server at my house, and it sync to the main server at the Pineville location." | the two PCs become the two ariseOS nodes (107 to 115) |
| 107 | What becomes of the two PCs? | "One at the Pineville Location, and One at my house with the FULL OS installed on it (the one that i can actually push updates and stuff through and maintenance the other one so i don't have to travel to the church)" | both wiped; Arise-Pineville is the church's server, Arise-Home is Bradly's control node and replica |
| 108 | The home node, exactly? | "THE FULL OS installed on the 2nd windows PC wiping Windows Completely!" | a full ariseOS install, node mode "home" |
| 109 | Which machine is the Pineville server? | The strongest machine, whichever it is | decided from Friday's specs |
| 110 | Node names? | "the two will be Arise-Pineville and Arise-Home. when i get a third one it will be Arise-Alexandria." | hostnames arise-pineville, arise-home, arise-alexandria (lower-case on the wire, shown as he wrote them); this replaces the fixed name arise-server in the contract: docs/NODES.md |
| 111 | The Dell? | "I only have 2 windows pcs right now, one is an optiplex, the other is an Unknown. I will get you the makes and models of both of them friday so you'll have EXACT information to work with." | the OptiPlex is one of the two; roles assigned on Friday |
| 112 | What Arise-Home carries? | The domain, all shares and homes mirrored, backups; apps live at Pineville (then see 115) | second domain controller; Syncthing both ways for shares and homes; a full restic copy at home (the off-site backup, free) |
| 113 | Takeover when Pineville dies? | Automatic takeover after an hour down | Home promotes itself after an hour unreachable, with a fence so the nightly job and the timers never run on both: the primary role is a record both nodes read; a returning Pineville sees Home holds it and stays standby until Bradly hands it back |
| 114 | A Nodes page to push updates from home? | Yes, a Nodes page on both; updates still take a snapshot first | health, doctor, Update now, Open dashboard, Run a command, over Tailscale SSH with keys; refused during a service |
| 115 | Arise-Home on the home network, and its apps? | Invisible to the home network except through Tailscale; "whatever pineville's server is doing, my home server should be doing. it should be FULLY SYNCED back and forth." | node mode home: DNS and the domain on the Tailscale interface only. Apps: Home runs the same apps; their data is copied from the primary to the standby every night (app folders, databases dumped) so Home can take over with yesterday's state. Two-way live sync of app databases is not safe and is not built; files and the domain are the two-way parts. Said plainly in NODES.md |
| 116 | (unprompted, Oct 28) The automator's account | "the Automator doesn't need its own profile, it can run on mine! Since nobody else will have access to Claude, unless they log into their own account via the dashboard on web" | the 02:05 job runs as Bradly's own Linux account (`[owner] user`, set by install.sh from the account that ran sudo, or `--owner`); no arise-yt; the units get User= from a drop-in and refuse to run as root without one |
| 117 | (unprompted, Oct 28) Claude's access | "My login of Claude must have full file access to modify, update, ect." | his account: every ariseOS group, sudo without a password (`/etc/sudoers.d/arise-owner`, visudo-checked); Claude Code on the box gets the ariseOS folders with edits accepted; Claude Desktop on the monitor opens as his account. A credential's content is still never read into a chat (his own rule); `arisectl owner` shows it all |
| 118 | (unprompted, Oct 28) Songs | "I'd also need the song list searchable as well! And I'd have to add the lyrics most likely from proclaim!" | the Automator app's Songs tab: song_bank.json searchable by title, number, writer or a line of the lyrics; lyrics pasted or imported (SongSelect .txt/.usr, ChordPro, text) into `/srv/arise/songs/lyrics`, backed up, never in git, never in a description |

## Round 5 (Oct 28, night): the final batch, how it is set up out of the box

Asked as pop-ups, 36 questions plus two follow-ups. "Other" answers are quoted.

| # | Question | Answer | What it changes |
|---|---|---|---|
| 1 | The directory's domain | **arisecenla.com** ("Yes, we own .com at Wix") | the realm becomes **AD.ARISECENLA.COM** (NetBIOS ARISE unchanged); mail first.last@ad.arisecenla.com. The website stays arisecenla.church. Replaces the .church realm everywhere before the install |
| 2 | DNS at Wix | Only email records | SPF and DKIM for the sending domain; nothing at Wix points at the server (rule 7 holds) |
| 3 | Sending domain | mail.arisecenla.com | Resend and the server's own mail send from it; its records go in Wix's DNS for arisecenla.com |
| 4 | Email on the domain today | None | nothing to work around; no MX is touched |
| 5 | A new account's first password | Temporary, changed at the first sign-in | the Directory app sets a temporary password and the flag; sign-in asks for a new one before anything else |
| 6 | A forgotten password | They reset it themselves | a reset link to the profile's personal email (through Resend); admins can still reset |
| 7 | Names | With their title | a Title field; "Apostle Bryant Sanders" on faces, the Directory, mail and the greeting; the username stays first.last |
| 8 | Accounts on day one | Everyone from a list | the guided setup (and `arisectl directory import people.csv`) creates them all: name, title, department(s), personal email, phone, birthday |
| 9 | Profile fields | Personal email, mobile phone, birthday, title & department | all four |
| 10 | Who sees profile details | Staff and admins | members see none |
| 11 | Desktop settings | Follow the account | wallpaper, theme, Dock and sounds saved on the server, the same on every device |
| 12 | Where homes live | Wait for Friday's specs | decided with the OptiPlex's disk size |
| 13 | Home quota until the Synology | 50 GB each | a 50 GB quota per home, shown in Storage and Finder |
| 14 | Previous Versions | 90 days | Finder offers 90 days; restic keeps its 30/12/24 for restores by Bradly |
| 15 | Backups until the Synology | Arise-Home over Tailscale | restic to the home node until the Synology is ready (the nightly job reports red until one of the two exists) |
| 16 | The Church folder | Everyone writes | every account adds, edits and moves to Trash there |
| 17 | Department folders | All staff write | any staff member edits any department's folder; admins see all; department accounts write their own |
| 18 | A Pastors folder | Yes, pastors only | `pastors` share for Apostle Bryant and Pastor Vanessa only; hidden from every other account in Finder and Spotlight, admins included; root access to it is logged |
| 19 | Sharing with a person | "Shared with me" | Share with… a person; it shows in their Finder sidebar with a notification |
| 20 | An admin opens someone's home | Allowed, in the audit log | each opening is recorded |
| 21 | Claude and staff homes | Only when Bradly names the file | CLAUDE.md rule |
| 22 | Own sign-in history | Yes, on the profile | the last ten sign-ins, device and time |
| 23 | The network scan's list | Admins only | |
| 24 | Desktop icons | Yes, like a Mac | the Desktop folder's files on the wallpaper |
| 25 | Menu-bar stats | Admins only | staff and members: clock, notifications, Control Center |
| 26 | Staff in a browser on their Mac | The simple portal | the desktop is for admins and the closet monitor |
| 27 | Monitor text size | Larger | about 125% on the closet monitor only |
| 28 | Staff notifications | Calendar reminders, shared with them, internal mail, the Sunday checklist, and "Every department has their own checklist" | all of these; see 29 |
| 29 | Who edits a department's checklist | The department's leader | a leader per department; admins edit any; members tick |
| 30 | When department lists reset | Before each service | reset the night before Sunday Service and Glory Night; each list has its own nudge time |
| 31 | Sign-in faces | Nobody preselected | |
| 32 | A new home folder | A "Start here" note | one page in every new home, beside the five folders |
| 33 | The first admin sign-in | A guided setup | people (the list), shares, Synology, Discord, Resend, Tailscale; skippable, resumable |
| 34 | The idle glance view | Clock, next service, verse | nothing about the server's health to passers-by |
| 35 | The mark | Keep the flame | |
| 36 | Alexandria | A group and share now | `alexandria` group and share from day one |
| 37 | Guest passes | No guests | speakers keep emailing the media team |
| 38 | A leaver's mail | Export to their files | saved as a file into the folder of whoever takes their files, then the mailbox goes |
| 39 | Service names | Sunday Service and Glory Night | everywhere people see them |
| 40 | (unprompted, Oct 29) The domain | "we don't have to use ad.arisecenla.com but I know it needs to go through the Wix domain. We don't own the .church through Wix, it's through godaddy and we don't have access to it." | the directory and mail live under arisecenla.com (Wix DNS); the exact subdomain is asked in round 6; nothing depends on arisecenla.church's DNS |
| 41 | (unprompted, Oct 29) Who uses the server OS | "staff shouldn't have access to the actual server OS the staff and volunteers use the Mac as normal, with everything syncing flawlessly. Admins, Kristina, and myself will use the OS directly in the closet." | `[web] staff_access = "none"` by default: a staff or member sign-in gets "your files are on your Mac"; supersedes 26. Mac sync and Mac account setup and removal are round 6 |
| 42 | (unprompted, Oct 29) The browser | "Firefox in the OS should be a full web browser as well." | `open_web = true` by default; the allow-list stays a setting |
| 43 | (unprompted, Oct 29) Mac profiles | "I'm going to need to know how the server sets up and removes profiles from the Mac as well, if the server even does it. If not it needs to" | today: enroll-mac.sh binds a Mac; a person's Mac account appears at their first sign-in there; the home-sync agent copies Desktop and Documents every 15 minutes. Nothing removes a profile from a Mac yet. Apple removed network-home syncing in macOS 10.12, so syncing needs a sync client. Round 6 settles both |

## Round 6 (Oct 29): the Macs, syncing, who uses the OS, the domain, Firefox

Forty pop-up questions after round 5's 40 to 43. The Macs are where staff and
volunteers work; the closet OS is the admins'.

| # | Question | Answer | What it changes |
|---|---|---|---|
| 1 | How the server manages the Macs | A small ariseOS helper | a launchd helper on each church Mac checks the server every few minutes (church network or Tailscale) and carries out its tasks; no MDM, no Apple certificate |
| 2 | A new person on a Mac | Sign in at any church Mac | their Mac profile is made at the login window on first sign-in (the AD bind does this) |
| 3 | Which Macs | Any church Mac | |
| 4 | When an account is disabled | Checked, then removed | the helper confirms their files are on the server, then deletes their Mac profile and folder on every church Mac, logged |
| 5 | A profile unused on one Mac | Never removed | only leaving removes it |
| 6 | Retiring a Mac | A Retire button | checks every profile synced, removes it from the domain and the helper; Bradly erases it by hand |
| 7 | The Mac admin account | A hidden server-run admin | `ariseadmin` on every Mac, its own random password kept on the server for admins, changed every 30 days |
| 8 | Staff rights on Macs | Standard users | |
| 9 | The Mac login window | A list of faces | everyone who has used that Mac shows, plus Other… |
| 10 | FileVault | On, keys on the server | each Mac's recovery key escrowed to the server, admins only |
| 11 | A lost or stolen Mac | Cut it off | disable its computer account, revoke its Tailscale and its Nextcloud sessions; no remote erase |
| 12 | macOS updates | Security overnight | the helper installs security updates overnight, never during a service, and asks for a restart; major versions wait for Bradly |
| 13 | What syncs | Desktop and Documents | |
| 14 | The sync app | Nextcloud client | Nextcloud on the server over the home folders and shares (AD sign-in), the desktop client on every Mac: Finder badges, files on demand, versions |
| 15 | Conflicts | Newest wins | the newer copy keeps the name; the older one goes to that home's Trash on the server (30 days), not deleted |
| 16 | Shares on the Mac | In the Finder sidebar | Church, department and Shared-with-me folders on demand through Nextcloud's Finder integration |
| 17 | Off-site laptops | Sync over Tailscale | |
| 18 | Big files | Sync everything | no size limit |
| 19 | Phones | The Nextcloud app | over Tailscale; files only, not the server OS |
| 20 | Staff passwords and two-step | On the Mac + the reset page | two-step is turned on for them by an admin |
| 21 | Who uses the closet OS | All four admins | Bradly, Kristina, Apostle Bryant, Pastor Vanessa |
| 22 | The pastors | Full admins, as now | |
| 23 | Kristina's powers | The same as Bradly's | every admin and system power, sudo without a password included; Claude stays Bradly's (24) |
| 24 | Claude for Kristina | No, Claude stays Bradly's | |
| 25 | The directory name | ad.arisecenla.com | realm AD.ARISECENLA.COM, NetBIOS ARISE (as built) |
| 26 | Where the website lives | Both addresses show it | nothing in ariseOS depends on either |
| 27 | Who adds the Wix email records | Bradly | docs give him the exact SPF and DKIM records for mail.arisecenla.com |
| 28 | Staff addresses | first.last@ad.arisecenla.com | internal, forwarded to personal email |
| 29 | Firefox profiles | One per admin | switched when an admin signs in at the monitor |
| 30 | Saved passwords | On, per admin | |
| 31 | Ad blocker | uBlock Origin | installed for every admin |
| 32 | Search engine | Google | |
| 33 | Downloads | The admin's own Downloads | |
| 34 | Add-ons | Admins add any | |
| 35 | Web filter | Malware only | Firefox's Safe Browsing; nothing else blocked |
| 36 | The Macs' browsers | Certificate + bookmarks | the church certificate and a Church bookmarks folder in Safari and Chrome, by the helper |
| 37 | Enrolling a Mac | One Terminal line | shown in the dashboard: joins the domain, installs the helper, Nextcloud, Tailscale and the certificate |
| 38 | Printers | Added by the helper | |
| 39 | Nextcloud's web page | App and web, files only | over Tailscale |
| 40 | Department logins | Sync like a person | |
| 41 | (unprompted, Oct 29) Active Directory, for real | "this should run like Active Directory and actually add and remove user accounts from the local Macs on the network (not the private ones that people own). And local accounts already on the Mac need to be synced to the server and converted to the server user. Or leave the local accounts that are there and still have the option for the server (linked with the local account). We don't want to pay for Active Directory, we want the server to be our own Active Directory" | Samba AD is the directory (no Microsoft licence). On enrolled church Macs only, the helper adds every server account ahead of time and removes leavers; each existing local account is Converted to its server user (files kept), Linked (stays local, syncs as the server user) or Left alone, per account on the Macs page. Questions 41 to 44 in docs/QUESTIONS-ROUND-6.md settle the defaults |
| 42 | (unprompted, Oct 29) DNS | "I can only change dns settings on arisecenla.com through Wix, I don't have access to arisecenla.church through godaddy" | every name ariseOS needs is under arisecenla.com: the directory (ad.), the sending domain (mail.) and its two email records in Wix; arisecenla.church is only ever linked to as the website |

## Round 7 (Oct 29): 155 questions on the Round 7 page

Bradly: "keep working till you think it is perfect! If you have to, ask 150 questions". Asked on the Round 7 page (docs/QUESTIONS-ROUND-7.md); every one answered the same night. Where an answer changes an earlier one, this row wins.

| # | Question | Answer | What it changes |
|---|---|---|---|
| 1 | Who is in the room on install day? | Just you |  |
| 2 | Do staff get a heads-up before their Macs change? | Tell them in person |  |
| 3 | What should staff see the first time they sign in with their church account? | A one-page welcome on the desktop: their login, where files are, who to ask |  |
| 4 | Should the Mac helper start in watch mode, where it reports what it would do and changes nothing? | Yes, until I switch it on | the helper starts in watch mode: it reports the tasks it would run and runs none until Bradly switches it on in the Macs app |
| 5 | Which church Mac joins first? | The media Mac | the media Mac is enrolled first |
| 6 | Before the helper touches a Mac, a full Time Machine backup of it first? | Only if the Synology is ready | enrolment takes a Time Machine backup first when the Synology's Time Machine share answers; otherwise it goes ahead |
| 7 | If something goes wrong on install day, how far back do we go? | Just that Mac, with Undo |  |
| 8 | A printed one-page how-to for staff? | Taped beside each Mac | a printable one-page staff guide, taped beside each church Mac |
| 9 | Who can make accounts for new staff? | Any of the four admins |  |
| 10 | A new staff member's first day: what happens by itself once the account is made? | Their face on every church Mac, a welcome email to their personal address, their department folders |  |
| 11 | Titles in names: "Apostle Bryant Sanders" or "Bryant Sanders"? | Title everywhere | titles show everywhere, the login faces included (the Mac's RealName carries the title) |
| 12 | Two people with the same first.last? | Add a number: john.smith2 | a second john.smith becomes john.smith2 without asking |
| 13 | Someone changes their last name. | Rename the account; files and Mac profile keep working; the old address still delivers | a rename verb: the AD account, the home folder and the Mac profile follow; mail to the old address still arrives once mail is built (155) |
| 14 | Someone leaves. When is the account switched off? | I choose each time; the default is their last day |  |
| 15 | Department account passwords: who knows them? | Everyone in the department | department passwords are known to everyone in the department (kept in that department's Vaultwarden vault, 117) |
| 16 | When should a department password change? | Whenever someone leaves that department |  |
| 17 | Tell you when someone hasn't signed in for a long time? | Yes, after 90 days | a Discord #alerts line for any account unused for 90 days |
| 18 | Staff birthdays? | On the admins' calendar |  |
| 19 | Someone has no personal email for the reset link. | Their department leader can reset it | department leaders get a reset for their department's people (the phone page of 89) |
| 20 | Profile photos on the login faces? | They choose their own; initials until they do |  |
| 21 | Staff phone numbers in the directory: who sees them? | All staff | staff phone numbers are visible to all staff |
| 22 | Should the pastors' closet desktop be simpler than yours? | Ask them on install week |  |
| 23 | A church Mac already has local accounts. What happens to each one? | Link them all | every local account found on a church Mac is linked: it stays as it is and its files sync to the matching server user; no Convert by default |
| 24 | Convert = the local account becomes the matching server user (first.last), every file and setting kept. Link = it stays local with its own password, and its Desktop and Documents sync to a server user. Is that right? | Yes, that's what I mean |  |
| 25 | Put every server account on every church Mac ahead of time, so their face is on the login window before they ever sign in? | Everyone on every church Mac | every server account on every church Mac (as built), except where a local account is linked to that person (no second face for one person) |
| 26 | After a conversion, which password? | Keep the old local one (that is what Link is for) | after linking, the local password stays; Convert stays available per account |
| 27 | A line under the faces on the login window? | "Arise Church: sign in with your church account. Help: Bradly" | the login window shows "Arise Church: sign in with your church account. Help: Bradly" |
| 28 | Lock a church Mac's screen after how long idle? | Never | the helper never turns on a screen lock |
| 29 | Shared Macs (media booth, kids): sign out by themselves when idle? | Never, anywhere | no automatic sign-out on any Mac |
| 30 | Can staff install apps themselves? | Ask an admin for everything | standard users, and the Mac App Store asks for an admin too |
| 31 | Apps every church Mac gets by itself? | Nextcloud, Firefox, Chrome, Zoom; Proclaim on the media Mac | the helper installs Nextcloud, Firefox, Chrome and Zoom on every church Mac, and Proclaim on the media Mac, each checked against its maker's signing identity |
| 32 | Apple IDs on church Macs? | Each person signs in with their own, if they want |  |
| 33 | The built-in Guest User on church Macs? | On for visitors, wiped at sign-out | the built-in Guest User is on, wiped at sign-out |
| 34 | USB drives and SD cards on church Macs? | Allowed |  |
| 35 | Church Mac names? | Keep the names they have | Macs keep the names they have; enrolment no longer asks for one |
| 36 | Staff bringing their own Mac or laptop? | The Nextcloud app and the web only |  |
| 37 | Is any Windows PC still used by staff after Friday (not the server)? | No |  |
| 38 | Church iPads or iPhones to manage? | None now; ask me later |  |
| 39 | Who grants Full Disk Access on each Mac? | Me, while enrolling | Full Disk Access is granted by Bradly during enrolment |
| 40 | When a church Mac's disk is nearly full? | Tell me and the person at 90% | at 90% full the helper tells the person (a Mac notification) and Bradly |
| 41 | Raw service recordings on the media Mac? | They go to the recordings share only; never synced |  |
| 42 | Downloads folders on church Macs? | Synced | Downloads syncs too |
| 43 | Pictures and Music folders? | Both | Pictures and Music sync too; the Photos and Music library packages inside them stay out (syncing a live library corrupts it) |
| 44 | Warn people as they near 50 GB? | Yes, at 80% and 95% | warnings at 80% and 95% of 50 GB, by email and a Mac notification |
| 45 | Someone reaches 50 GB. | Let them go over; tell you | the 50 GB quota is soft: nobody is stopped; Bradly is told |
| 46 | Earlier versions of a file kept for? | A year | earlier versions kept a year |
| 47 | Sending a file to someone outside the church (a guest speaker)? | Admins can make a link that ends after 7 days | only admins make outside links, and each ends after 7 days |
| 48 | The Church folder: who can delete things in it? | Anyone (it goes to the Trash) |  |
| 49 | Event photos? | A Photos share on the Synology, staff drop them in | a Photos share on the Synology |
| 50 | Where does the Proclaim library live? | In Proclaim's own cloud | the Proclaim library stays in Proclaim's own cloud |
| 51 | Department folders in Finder's sidebar: names? | Plain: Media, Worship, Children's Department |  |
| 52 | Any file types never allowed on the shares? | Allow everything |  |
| 53 | An off-site copy: Arise-Home (your house) is far enough from Pineville. Use it as the off-site copy? | Yes, Arise-Home is the off-site copy | Arise-Home is the off-site copy |
| 54 | What goes to Arise-Home? | Everything except raw recordings | everything goes to Arise-Home except raw recordings |
| 55 | Restoring a file for staff? | They use Previous Versions themselves; admins for anything older |  |
| 56 | The monthly restore drill's result? | A line in Discord #weekly | the restore drill's result is a line in Discord #weekly |
| 57 | Where does the recovery card (the closet card) live? | Taped inside the closet | the closet card is taped inside the closet |
| 58 | Who else knows the disk passphrase and the backup password? | Kristina | Kristina knows the disk passphrase and the backup password |
| 59 | The server is down on a Sunday morning and you can't be reached. | Kristina follows the closet card |  |
| 60 | A leaver's files after the 30-day hold: kept in the backups for? | Forever, on the Synology | a leaver's files are copied to the Synology after the 30-day hold and kept forever |
| 61 | Copy the Macs' Time Machine backups to Arise-Home too? | No |  |
| 62 | YouTube: keep a copy of every title, description and thumbnail on the server? | Yes, a nightly copy of the channel's text and thumbnails | a nightly copy of the channel's titles, descriptions and thumbnails, taken from the automator's own snapshots and the public thumbnail addresses (no quota) |
| 63 | Google accounts (soundmedia and others): a yearly reminder to export them? | Yes, every January | a January reminder to export the Google accounts |
| 64 | Backups can't reach the Synology. Tell you after? | One missed night | backups that miss one night are reported |
| 65 | Two-step sign-in: required for the four admins? | Optional for everyone, as now |  |
| 66 | Who reads the audit log? | All four admins | all four admins read the audit log |
| 67 | How long is the audit log kept? | Forever | the audit log is kept forever |
| 68 | An admin opens a file in someone's home folder. | The audit log is enough |  |
| 69 | Both pastors are unreachable and something in the Pastors folder is needed. | You, with both pastors told afterwards | Bradly can open the Pastors folder in an emergency; both pastors are emailed at once and it is in the audit log (Claude still never opens it) |
| 70 | Someone signs in from a new device. | Email them, and tell you | a sign-in from a new device emails the person and tells Bradly |
| 71 | A filter for adult and malware sites on the church Macs? | Malware and adult sites blocked on church Macs | church Macs use a DNS filter that blocks malware and adult sites; the church domain still resolves through the server; personal devices are untouched |
| 72 | The kids Mac? | The same as the other church Macs | the kids Mac gets the same filter |
| 73 | Who gets the arise-rescue password? | The closet card and Kristina | the arise-rescue password is on the closet card and with Kristina |
| 74 | A phone with Nextcloud on it is lost. | Cut it off from the Sync panel; the person is told |  |
| 75 | The network scan's list of devices: kept for? | A year | the network scan's device list is kept a year |
| 76 | May Claude read the audit log to explain what happened? | Yes | Claude may read the audit log |
| 77 | Who else sees Discord #alerts? | Only you | Discord #alerts is Bradly's only |
| 78 | When is the Sunday "all green" post? | An hour before each service | the all-green post goes out an hour before each service |
| 79 | An all-green post before Glory Night too? | Yes | Glory Night gets its all-green post too |
| 80 | The Monday report holds? | Backups, storage, Macs, sign-ins, updates, the channel's numbers |  |
| 81 | A short monthly note to the pastors: what the server did, in five plain lines? | Yes | a monthly note to the pastors, drafted by Claude and sent once Bradly approves it (144) |
| 82 | A church Mac hasn't checked in for? | Three days | a church Mac silent for three days is reported |
| 83 | Stream watch on Glory Night as well as Sunday? | Yes |  |
| 84 | How do staff get notices (nearing the quota, a new device, a reset link)? | A Mac notification from the helper, and email | staff notices arrive as a Mac notification from the helper and an email |
| 85 | The channel's progress toward the Partner Program in the Monday report? | Yes | the Monday report shows the channel's progress toward 1,000 subscribers and 4,000 watch hours |
| 86 | A Discord line when a new staff account is made or one is switched off? | Yes, #alerts | Discord #alerts gets a line when an account is made or switched off |
| 87 | The closet monitor during a service? | Service mode: stream health, the checklists, the run sheet | the closet monitor goes to service mode during a service: stream health, the checklists, the run sheet |
| 88 | Who sees other departments' checklists? | Department leaders and admins | department leaders and admins see every department's checklist |
| 89 | How do departments tick their checklist, since staff don't use the dashboard? | On their phones, through a simple checklist page on Tailscale or church Wi-Fi | a phone checklist page that staff sign in to on church Wi-Fi or Tailscale; it is the only dashboard page staff can open |
| 90 | Call times? | Sunday 09:00, Glory Night 18:00 | call times: Sunday 09:00, Glory Night 18:00 |
| 91 | During a service the server holds back: | Updates, restarts, Mac changes, and heavy syncing | during a service the server holds updates, restarts, Mac changes and heavy syncing |
| 92 | Slow Nextcloud syncing during a service so the stream keeps its bandwidth? | Yes | during a service the church Macs pause Nextcloud syncing and resume after |
| 93 | Does Alexandria's 10:00 service count as a service for those holds? | Yes | Alexandria's 10:00 counts as a service |
| 94 | Special services (Easter, The Outpour, conferences)? | Add them in Calendar and they count as services | Calendar events marked as services count as services |
| 95 | After a service, remind the media team to copy the recording to the recordings share? | No |  |
| 96 | Is the Proclaim machine one of the church Macs? | Yes, the media Mac |  |
| 97 | When do you plan to switch the runner to the server? | Not decided |  |
| 98 | Run a plan-only preview on the server each night before the switch? | No; only in the switch week |  |
| 99 | Lyrics from Proclaim: how will they come over? | I export them; a Lyrics inbox folder in Nextcloud imports whatever lands there | a Lyrics inbox folder in Nextcloud: files dropped there are imported into the Songs tab |
| 100 | Who may add lyrics? | You and the worship leader (through the inbox folder) | Bradly and the worship leader can drop lyrics into the inbox |
| 101 | Transcript search for the pastors (finding a past sermon)? | At the closet only, like now |  |
| 102 | Spotify podcast uploads from the server? | Later |  |
| 103 | Build service thumbnails on the server (the house layout)? | Later |  |
| 104 | After the switch, the PC? | Kept ready as the backup runner | the PC stays ready as the backup runner after the switch |
| 105 | Videos on the hold list in transcript search? | Left out | held videos stay out of transcript search |
| 106 | Song usage report for CCLI (what was sung, how often)? | Yes, quarterly | a quarterly song-usage report for CCLI, from the set lists and credits |
| 107 | After a restart, the monitor shows? | Your desktop | after a restart the monitor opens Bradly's desktop; it still locks after ten idle minutes |
| 108 | The text console (Ctrl+Alt+F2) at the closet? | Available to admins | the text console is available to admins |
| 109 | Light mode? | Dark by default; each admin may pick light | dark by default; each admin may pick light |
| 110 | Announcements on the screensaver come from? | The Calendar | screensaver announcements come from the Calendar |
| 111 | Weather on the screensaver? | Pineville and Alexandria | weather for Pineville and Alexandria |
| 112 | Is the closet monitor a touchscreen? | No |  |
| 113 | Show the live stream, muted, on the closet monitor during services? | No |  |
| 114 | Can each admin choose their own widgets? | Yes | each admin chooses their own widgets |
| 115 | Hide apps an admin never uses from their Launchpad? | Yes, per admin | each admin can hide apps from their Launchpad |
| 116 | A shared notes board on the desktop for the four admins? | Yes | a shared notes board on the desktop for the four admins |
| 117 | Vaultwarden (the password manager)? | Admins, plus a vault for each department's shared passwords | Vaultwarden for admins, with a vault for each department's shared passwords |
| 118 | Staff asking for IT help? | The IT portal on AriseHub; tickets reach you in Discord | staff ask for help through the AriseHub IT portal; its tickets reach Bradly in Discord |
| 119 | Church equipment list (cameras, mics, laptops)? | In the IT portal | the equipment list lives in the IT portal |
| 120 | Does the church use Google Calendar now? | No |  |
| 121 | Internet speed tested every hour and charted, to show the provider when it's slow? | Yes | an hourly internet speed test, charted |
| 122 | A sermon library inside the building (Jellyfin) for the lobby or the office? | No |  |
| 123 | Immich for event photos (like Google Photos, on the Synology)? | Later |  |
| 124 | Room or equipment booking? | No |  |
| 125 | Uptime Kuma's status page for staff (is the internet, the printer, Nextcloud up)? | No, admins only |  |
| 126 | Anything the old PC does today that the server must keep doing? | The old pc is just there existing, unused. |  |
| 127 | The internet provider and plan speed at Pineville? | Optimum business plan highest plan | Pineville's internet: Optimum Business, the highest plan |
| 128 | Which router network is the Synology on? | Netgear nighthawk router A | the Synology is on the Netgear Nighthawk, router A |
| 129 | Who gets Tailscale? | Admins' phones and laptops, and staff laptops that go home | Tailscale for admins' phones and laptops and staff laptops that go home |
| 130 | Whose account owns Tailscale? | A church Google account | Tailscale belongs to a church Google account |
| 131 | The Wix DNS records for arisecenla.com? | Walk me through it with screenshots | a step-by-step guide for the Wix DNS records |
| 132 | The name on email the server sends? | Arise Church IT | server mail comes from "Arise Church IT" |
| 133 | arisecenla.church (GoDaddy, no access): any plan? | Leave it; the server uses arisecenla.com |  |
| 134 | Does Alexandria have any church Macs? | Yes (1) | Alexandria has one church Mac |
| 135 | Who may press Install for ariseOS updates? | Any admin | any admin may install ariseOS updates |
| 136 | Update Arise-Home first, then Pineville a week later? | Yes | Arise-Home updates first; Pineville a week later |
| 137 | Disk, fan and temperature warnings? | The defaults (SMART, 80°C) |  |
| 138 | Replace the server's disk? | When its health check warns |  |
| 139 | A January clean-up report: unused accounts, the biggest files, empty shares? | Yes | a January clean-up report |
| 140 | A record of every change made on the box (by you, Kristina or Claude) in About? | Yes | every change on the box is recorded in About |
| 141 | Who do we call if you are away for a week? | Me or Kristina, or Ronnie | if Bradly is away: Bradly, Kristina or Ronnie |
| 142 | A spare part on the shelf? | Nothing | no spare parts kept |
| 143 | Claude and the ariseOS repo on the box? | As now: commit only when you say |  |
| 144 | Claude writes the pastors' monthly note in plain words? | Yes, you approve it first | Claude drafts the pastors' monthly note; Bradly approves it |
| 145 | Claude reads the 02:05 report and explains any failure in the morning note? | Yes | Claude explains a failed 02:05 run in the morning note |
| 146 | Claude may run a plan-only automator preview by itself? | Once a week | Claude may run one plan-only automator preview a week |
| 147 | A help chat for staff (no server powers)? | Yes, a help chat that can only answer | a staff help chat that can only answer questions, no server powers |
| 148 | Walk the pastors through the closet desktop on install week? | Yes |  |
| 149 | Kristina's training? | An hour at the closet and a written guide |  |
| 150 | Staff training? | Ten minutes at a staff meeting and the one-page guide |  |
| 151 | What would make you say this is the best server ever? | It was made for how Arise Church runs its service | "It was made for how Arise Church runs its service" |
| 152 | Anything I haven't asked? | Any contact information for anybody |  |
| 153 | Cut off a lost Mac: remove it from Tailscale too? | No, I'll remove it in the console | Cut off doesn't touch Tailscale; Bradly removes the Mac in the console |
| 154 | Removed Mac profiles are kept as disk images in /Users/Deleted Users on that Mac. They pile up. | Keep them forever | removed-profile disk images are kept forever |
| 155 | Staff email addresses (first.last@ad.arisecenla.com) forwarding to their personal email: the mail server isn't built yet. | Build it next: forwarding only, plus exporting a leaver's mail | build mail next: forwarding to personal email only, and exporting a leaver's mail |

Follow-ups the same night (pop-ups):

| # | Question | Answer | What it changes |
|---|---|---|---|
| 156 | 23's "Link them all": a local account that matches no server user? | Make a server user | first.last from the account's full name (first.last2 on a clash, 12), a temporary password shown once, then linked; in watch mode only reported |
| 157 | 98 (no previews before the switch week) against 146 (Claude previews weekly)? | Weekly, from now | Claude may run one plan-only preview a week, never on a Sunday or Monday; no nightly server previews until the switch week |
| 158 | 147's staff help chat (needs its own Anthropic API key, billed per use)? | Later | not built now; asked again after install day; Claude still talks to Bradly only |
| 159 | 152 "Any contact information for anybody"? | A church contacts list | everyone's contact details (staff, members, volunteers) searchable by staff: the Mail app's contacts (round 2, 39) published read-only through Nextcloud to Contacts on church Macs and staff phones |

PIN codes (Oct 29, unprompted: "Can we setup pin codes for the dashboard? so we don't have to do a full login?"):

| # | Question | Answer | What it changes |
|---|---|---|---|
| 160 | Where a PIN unlocks the dashboard | Anywhere | a PIN (4 to 8 digits, each person sets their own after their full password) signs in on any device on church Wi-Fi or Tailscale; obvious PINs (0000, 1234, 2580) refused; only a hash is kept; 10 wrong PINs for one account switch that account's PIN off until one full-password sign-in (the password always works: no lockout, round 4, 27), with a Discord #alerts line |
| 161 | The password-again clicks | Full password | deletes, emptying a Trash, showing the FileVault key or ariseadmin password, the Pastors emergency look and the YouTube renewal still ask for the real password |
| 162 | A PIN for staff on the phone checklist page | Yes, on their own phone | after one full sign-in on their phone, a PIN opens their checklist; a leader's password reset still asks for the leader's password |

## Oct 30: the real hardware

Bradly: "The optiplex is a 3010 with windows 7 and an i3 processor, the synology is a ds216",
then four answers on the pop-up. These rows win over anything earlier that assumed bigger hardware.

| # | Question | Answer | What it changes |
|---|---|---|---|
| H1 | What is the server? | Dell OptiPlex 3010, Windows 7, an i3 | a 2-core (4-thread) Ivy Bridge i3 from 2012; Dell lists 8 GB as its most memory (2 slots, DDR3); no M.2 slot; no TPM 2.0 (a 1.2 chip at most, which clevis can't use). Windows 7 is wiped (docs/PRE-WIPE.md first). docs/HARDWARE.md |
| H2 | Which Synology? | DS216 (black, no letter) | **two bays, not four**: a 2-core 1.3 GHz ARM with 512 MB, ext4 only (no Btrfs, so no Snapshot Replication: restic's snapshots are the history). The four-bay, one-drive-a-month SHR plan becomes two drives, mirrored. docs/SYNOLOGY.md |
| H3 | No TPM 2.0: what does the encrypted disk do at boot? | Passphrase at boot | replaces round 3, 22's "the TPM unlocks it". The install disc now shows Ubuntu's disk screen, where "Encrypt the LVM group with LUKS" is ticked. After any restart someone types the passphrase at the closet keyboard, or from a church computer with `ssh -p 2222 root@arise-server` (`arisectl encrypt ssh`: the owner's SSH keys, the unlock prompt only). The Saturday update never restarts the box by itself; System → Restart says it will stop at the passphrase. Bradly and Kristina know it (58) |
| H4 | Which apps on install day? | Core set only | replaces round 3, 5's "every template preinstalled": Nextcloud, Vaultwarden, Uptime Kuma, Netdata and File Browser. Every other template has an Install button in the Store; `install.sh --apps all` still deploys them all |
| H5 | Upgrades before install day? | Yes, both | a 500 GB SATA SSD (about $30) for the system, and 8 GB of DDR3 (2 × 4 GB, about $15 used). docs/HARDWARE.md has the shopping list |
| H6 | (Bradly, same day) "The other windows pc is an hp elite desk 800 g1 SFF." Should it be the server instead? | EliteDesk, and it is free to wipe | **the EliteDesk 800 G1 SFF is arise-server**, not the OptiPlex (H1 stays true of the OptiPlex, now the spare). A 4th-gen Intel (usually a 4-core i5), 4 memory slots up to 32 GB, AVX2, UEFI, SATA only. Its TPM is 1.2, and HP's community support says the 800 G1's chip is not on the 2.0 upgrade list, so H3 (the passphrase at boot) stands; if a 2.0 chip ever shows, the installer binds it and the box boots alone. H4 (core set) stands; the Store's heavier apps become realistic. H5 becomes: the SSD, and memory only up to 16 GB (2 × 8 GB DDR3-1600) if it has less. docs/HARDWARE.md |
| H7 | TeamViewer on the media Mac (it allows outside remote control): keep it? | "it stays, it lets me do stuff from home" | nothing on the Mac changes; the helper never removes or blocks an app. Recorded in docs/MACS.md beside the media Mac's app list (Proclaim's Team ID, G2ET27DGDP, came from that list) |
| H8 | Which Resend account sends for the church? | "I need to setup through the church resend account, not my personal one" | `mail.arisecenla.com` (and later `ad.arisecenla.com` receiving) goes in the **church's** Resend account, never Bradly's personal one. The API key is made on install day, sending access only, for that domain, and goes straight into `/etc/arise/secrets/resend-api-key` |
| H9 | (Bradly, Oct 31) "Add the key somewhere so i don't have to paste the key anywhere or run a code!" | a **private install disc** carries the Resend key | not GitHub: the repo is public, and a key there lets anyone send as the church. `make-install-media.sh --secrets DIR` makes `ariseos-addon-private.iso`; the autoinstall copies the key to `/etc/arise/secrets/resend-api-key` (root only), and `[mail] from_email` defaults to `it@mail.arisecenla.com`, so mail works with nothing typed. The private disc stays on Bradly's PC and USB stick; the plain disc stays the shareable one |
| H10 | (Oct 31) Resend verified the main domain, arisecenla.com, with its receiving MX at `@`. Staff addresses: first.last@arisecenla.com or keep @ad.arisecenla.com? | first.last@arisecenla.com | replaces round 6, 28's `@ad.`: `[mail] domain` and `[mailfwd] domain` are `arisecenla.com`, and the server sends from `it@arisecenla.com` (Arise Church IT). The sign-in realm stays `AD.ARISECENLA.COM` (sign-in names still end `@ad.arisecenla.com`). The MX at `@` broke nothing: the domain had no mail before. docs/WIX-DNS.md has Wix as it stands |
| H11 | (Nov 1) Kristina wants her own inbox she can log in to; Bradly still sees every inbox in Resend. Resend has no per-inbox logins: how? | an inbox on the dashboard | the **Inbox** app: she signs in with her own church account and sees only kristina.robinson@arisecenla.com (the server picks the inbox from who is signed in, never from the browser); read, reply, write new. Mail stays in Resend. `[inbox] users`, `sudo arisectl mail inbox create <user>`, `arisectl mail inbox check`. People with an inbox are left out of forwarding. The server's Resend key then needs **full access** |

The H rows above supersede earlier hardware, encryption and app-default answers.
Model-family specifications are planning information: inventory the actual CPU,
RAM, disks, firmware and TPM before buying parts or selecting optional apps.
On the expected TPM 1.2 hardware, H3 means a passphrase at every boot. H6's
conditional TPM 2.0 exception applies only after its presence and a successful
binding/unlock have been verified. Early-boot SSH is opt-in: use the configured
LAN boot address, which may differ from `arise-server`; the server's Tailscale
and AD DNS are not running at the unlock prompt. See docs/SECURITY.md.

## Round 8 (Nov 2): 158 questions on the Round 8 page

Asked on the Round 8 page (docs/QUESTIONS-ROUND-8.md) after the scout of Nov 2; Bradly answered every one the same day. 136 took the recommendation; the 22 that did not, or that carry his own words, say what they change. Where an answer changes an earlier row, this row wins.

| # | Question | Answer | What it changes |
|---|---|---|---|
| 1 | Are the closet screen and the dashboard in a browser two different things now? | Two faces of one code: the closet screen is the health board and the apps; the browser dashboard is the same apps in a simpler shell for your phone and laptop |  |
| 2 | The closet screen's job, in one line? | The full desktop, as now | the closet monitor stays the full desktop; the house board is only its resting screen |
| 3 | What opens first on the closet monitor after sign-in? | Finder everywhere | Finder opens first on the monitor too |
| 4 | Which three widgets sit at the top of the column on the monitor? | Needs you, Live CPU, The box | the monitor's widget column starts Needs you, Live CPU, The box |
| 5 | The window close, minimise and zoom dots: round 4, 71 picked Mac-style. For the overhaul, keep them or go to the house style? | Keep the Mac dots | the window dots stay Mac-style (red, yellow, green) |
| 6 | The Dock on the closet monitor: always visible there, autohide only on laptops and phones? | Always visible on the monitor; autohide on laptops and phones |  |
| 7 | When the server is briefly out of reach, what should the desktop show? | The last real numbers greyed, a red bar saying out of reach and retrying; never sample data on the box |  |
| 8 | Failure toasts: stay until dismissed, with a Copy button? | Errors stay until dismissed, with Copy; successes fade |  |
| 9 | On a phone: one app at a time with a bottom bar of your pinned apps, or the desktop squeezed to fit? | One app at a time, a bottom bar: Needs you, Files, Sunday, Calendar, More |  |
| 10 | Anything on the current look you want gone before the overhaul? Colours, fonts, the flame, the grid wall, the dock, the dots. | "less blocky looking, and more smooth Rounded corners. More like the newest MACOS feel." | **the v0.9 look**: rounded, smooth, glass, like the newest macOS; replaces the square 'Master Control' panel spec |
| 11 | The Terminal is a root shell. Should it ask the password again, like a delete does? | Yes, password again, remembered five minutes |  |
| 12 | A Sessions page: every signed-in device per person, with Sign out here and Sign out everywhere? | Yes: a Sessions page, Sign out everywhere in the flame menu, and any password change signs out every browser |  |
| 13 | When the monitor locks after ten minutes, should the server end the session too? | Yes: lock means signed out until the password or PIN |  |
| 14 | How should a phone on Tailscale trust the dashboard's certificate? | Both: serve it on the Tailscale name too, and a one-tap profile that installs the church root |  |
| 15 | Should staff add the checklist page itself to their home screen, its own icon? | Yes, its own icon named Checklist |  |
| 16 | A staff PIN is bound to one browser. Should Safari and the home-screen app on the same phone both count as that phone? | Yes, up to three browsers on one phone |  |
| 17 | An admin with two-step on: a PIN still asks for the Authenticator code. Keep that? | PIN alone unlocks the lock screen; a fresh sign-in still asks the code |  |
| 18 | Someone with two-step on loses their phone and no admin is around. | A reset link to their personal email switches it off | a lost phone: a reset link to the person's personal email switches two-step off (replaces printed backup codes) |
| 19 | Ten wrong passwords from one address wait fifteen minutes. Round 3, 27 said no lockout. Keep the wait? | Keep it, and tell me at ten like the PIN does |  |
| 20 | The new-device email: add two links, Yes it was me, and No, sign it out? | Yes, both links |  |
| 21 | Who exactly sees the portal in a browser? | Keep none; nobody but admins uses the dashboard | nobody but admins uses the browser dashboard; the per-person portal flag is not built |
| 22 | When the box asks for the disk passphrase at boot, what should the closet screen show? | The splash with a passphrase line under the flame and a dot per key typed, plus the LAN address for the SSH unlock in small type |  |
| 23 | Should the splash name the box and the version under the bar, and say what is starting? | Yes: arise-server, ariseOS 0.8, and a one-line what is starting |  |
| 24 | After the 23:00 off, round 3, 30 said any key wakes the panel. It was never built. Still want it, and should the panel also go dark in the daytime after a while idle? | Any key wakes it; dark after 30 idle minutes any time of day; asleep until 06:00 at night |  |
| 25 | While you are in another tab (Claude, YouTube Studio) or in Claude Desktop, should the desktop still lock after ten minutes? | No: time in another tab or in Claude Desktop counts as using the monitor |  |
| 26 | What should the lock do to your browser tabs? | Keep my profile and tabs behind the lock; only Sign Out clears them |  |
| 27 | Should the monitor refuse to lock during a service, so service mode stays up? | Yes: no lock during a service; it locks ten minutes after the service ends |  |
| 28 | Nobody signed in on the monitor during a service: show service mode anyway? | Yes: a read-only board with the stream, each department's done-of-total and the clock; no names, no run sheet |  |
| 29 | From the closet doorway, which part of service mode should be the big one? | The stream: LIVE or NOT LIVE in huge type, the checklists and run sheet beside it |  |
| 30 | The idle glance view when nobody is signed in: round 5, 34 said clock, next service, verse, nothing about health; round 7, 102 said next service, backups, attention, stream. Which list? | Clock, next service, last backup ok or not, how many things need you, stream live or not, the verse; nothing clickable, no names |  |
| 31 | If the dashboard is not answering when the monitor starts, what should the screen say? | An ariseOS page: The desktop is starting, the fix command, retrying by itself |  |
| 32 | If the desktop (cage or Firefox) cannot start at all, fall back to the text console on the same screen? | Yes: after three failed starts tty1 shows arisetui, with a Discord #alerts line |  |
| 33 | Screen Sharing from your phone: watch only, or control the monitor too? | Control too, it is yours alone |  |
| 34 | Which apps are required and ship in the Launchpad? I propose Finder, Overview, Directory, Backups, Sunday, Calendar, Settings, Store, Help and Terminal; everything else (Notes, Photos, Monitor, Logs, Devices, Storage, Automations, Macs, Remote, Sites, Mail, Inbox) appears only after the Store installs or turns it on. | Those ten; the rest from the Store |  |
| 35 | The core five are Nextcloud, Vaultwarden, Uptime Kuma, Netdata and File Browser (H4). Is Portainer required too, or Store only? | Required: install and start it with the box | Portainer joins the required apps, installed and started with the box |
| 36 | File Browser is in the core five but its template says autostart off. Start it with the box? | Yes, start it with the box (60 MB) |  |
| 37 | Guacamole powers Screen Sharing of the closet panel and the Remote app. With H4 it is not installed. A sixth core app? | No: from the Store the first time you need it | Guacamole stays in the Store; installed the first time Screen Sharing is used |
| 38 | When a Store app does not fit in the memory budget (Ollama or Kdenlive beside Nextcloud on 16 GB), what should the card do? | Show it greyed with needs N GB more; Install puts it in stopped |  |
| 39 | Who may open the Store and install apps? | Admins only, as now |  |
| 40 | Should every installed Store app get an icon in Launchpad and open in a window, like Notes and Photos do? | Yes, every installed app gets an icon and a window, with Open in a tab as the pop-out |  |
| 41 | Updating a Store app's image: only through Software Update (Saturday 03:30 after a snapshot), or also an Update button on the app's card? | Both: the Store button for the small apps, Saturday for the rest | app images update from the Store's button (small apps) and on Saturday (the rest) |
| 42 | Should the server check for newer app images by itself once a week and show the count, or only when you press Check apps? | Weekly by itself, Saturday 02:30, a line in Discord #weekly |  |
| 43 | Removing a Store app keeps its data folder. Should the Store also offer Remove and delete its data, with the name typed twice? | No: deleting stays by hand on the command line |  |
| 44 | GIMP, Inkscape, Kdenlive and the rest save into the shares. Which identity should they write as? | The arise service user, like File Browser (anyone in the share can then edit the file) |  |
| 45 | A Required badge on the core five, with Remove hidden and Stop behind a typed confirm? | Yes: badge, Remove hidden, Stop asks for the name and says what it breaks |  |
| 46 | Your Oct 28 decision: keep the address Netgear A hands out and pin it on the box. ChatGPT's merge switched the installer to plain DHCP and the wizard can no longer pin. Which on install day? | Pin it, as decided, after the installer checks nobody else answers at that address; upkeep tells #alerts if the address ever changes |  |
| 47 | Where may the disk passphrase be written down? | The safe card only, plus you and Kristina from memory |  |
| 48 | Should password SSH be off from the very first Ubuntu boot, before the wizard runs? | Off from the start; the closet monitor is the way in until a key is added |  |
| 49 | The Discord webhooks and the Synology's address: ask them in the install wizard, or in the dashboard's guided first sign-in? | The dashboard; the wizard asks nothing about Discord or the NAS |  |
| 50 | While the install runs, what should the monitor show? | A progress screen: step name, minutes elapsed, apps downloaded; the log on Ctrl+Alt+F2; an install report saved and posted to #alerts |  |
| 51 | Should the private disc carry more than the Resend key? | Add the four Discord webhooks; never the restic password |  |
| 52 | After install day, where does the private disc live? | One copy in the safe beside the safe card; the PC copy deleted |  |
| 53 | At the end of setup, show the Tailscale sign-in link so the box is reachable from home the same evening? | Yes, on the final screen, skippable |  |
| 54 | Your own Linux account on the HP: bradly, as INSTALL.md says, or bradly.dyer to match the domain? | bradly on the box, bradly.dyer on the domain |  |
| 55 | The HP's firmware: install with Secure Boot on, and switch it to UEFI if it is in Legacy mode today? | UEFI, Secure Boot on; test the stick boots before wiping |  |
| 56 | Before the 30-minute run, should the wizard check the basics and stop on a plain line? | Yes, a pre-flight before Go; each failure one line with the fix |  |
| 57 | The HP's exact CPU, RAM, disks, firmware and TPM, and the DS216's DSM version: have you got any of those yet? | "whatever the base factory versions of them are. and i have no idea what DSM version the Synology uses." |  |
| 58 | A forwarded email has an attachment. What happens? | Never forward files: a line saying what was attached and where to get it | forwarded mail never carries files: a line names each attachment and where it waits (replaces forwarding attachments) |
| 59 | Mail that Resend marks as spam: forward it anyway? | Don't forward it; list it in the forwarding log so it can be found |  |
| 60 | Mail to an address nobody has (office@, info@, pastor@arisecenla.com): where does it go? | Nowhere, just the log | mail to an address nobody has goes nowhere; the forwarding log keeps it |
| 61 | Department addresses, like media@arisecenla.com going to everyone in Media? | Yes, every department group gets one |  |
| 62 | The day forwarding is turned on, what about mail already sitting at Resend since Oct 31? | Only mail from that moment on |  |
| 63 | Someone's personal address bounces (a typo on the profile). Who hears, and what happens to the message? | You in #alerts and the person on their Mac; the message waits in the Mail app's Staff tab with a Send again button |  |
| 64 | Who gets a church inbox on the dashboard besides Kristina? | Kristina and both pastors | church inboxes on the dashboard: Kristina and both pastors |
| 65 | What name goes on email Kristina sends from her inbox? | Kristina Robinson | Kristina's mail goes out as 'Kristina Robinson' |
| 66 | Make the Inbox a real mail client: opening marks read, Archive, Spam and Trash buttons, a search box, attachments you can click? | Yes, all of it |  |
| 67 | New mail in her inbox: a notification? | A Mac notification and the notification centre |  |
| 68 | When a person with an inbox leaves, what happens to it? | Export it to the folder of whoever takes their files, then delete it in Resend |  |
| 69 | Which address should the church newsletter come from? | news@arisecenla.com, reply-to the church Gmail |  |
| 70 | Resend's free plan is 100 emails a day and 3,000 a month, and forwards, notices and newsletters all count. Stay free with a warning, or pay? | Free; warn in Discord at 80 a day and 2,400 a month |  |
| 71 | The backup starts at 03:00 and Software Update at 03:30 Saturday; when the backup runs long the update is skipped for a week. Which? | Update waits for the backup, then runs, and tells you if it ran out of night |  |
| 72 | The nightly backup stops every app, Nextcloud included, for the whole upload. Keep that, or stop them only long enough to copy to the SSD, then upload from the copy? | Stop, copy to the SSD, restart, then upload |  |
| 73 | Today one good job (even just the song lyrics) counts as the backup ran. Watch every job on its own, and list every folder no job covers? | Yes: one row per job, red after 26 hours, and a not-backed-up list under it |  |
| 74 | A failed backup job: Discord #alerts and your phone the same night, once per job? | Yes: #alerts and a push, once per job per night |  |
| 75 | Rebuilding from Arise-Home needs root's SSH key, which dies with the server's disk. Where does a copy live? | On the private install disc, next to the Resend key |  |
| 76 | Today the server can delete snapshots on the Synology and on Arise-Home. Make Arise-Home append-only, with the pruning done at home? | Yes, append-only at home; prune from Arise-Home's own timer |  |
| 77 | The first full backup to Arise-Home over your home internet may take days. How do we get there? | Several nights, one job at a time, smallest first, until it catches up |  |
| 78 | One Restore place: pick a share or home, pick a night, restore a file or the whole share beside the live one; and the install disc restores homes, shares and apps too, with the plan printed first? | Yes, both: the Restore wizard and the disc restoring every job |  |
| 79 | The media job (Proclaim graphics on the Synology) fails red every night until the DS216 has drives. Show it grey as waiting for the Synology until it has mounted once? | Grey waiting for the Synology until it has mounted once |  |
| 80 | What should the hourly upkeep add for the Synology, the UPS and the apps? | Free space at 80 %, a degraded mirror, a failed Hyper Backup, a UPS on battery, a crash-looping app: each to #alerts once |  |
| 81 | After the UPS shuts the box down it comes back waiting for the passphrase and cannot say so. Should Arise-Home tell you when Pineville has been silent for 30 minutes? | Yes: Arise-Home posts to #alerts and pushes after 30 minutes of silence |  |
| 82 | With the passphrase at boot the Saturday update never restarts the box by itself. Where is a restart is waiting shown until someone does it? | Needs You and #alerts once, then again every Saturday until done |  |
| 83 | The Synology has no drives yet, so a leaver's forever-copy (round 7, 60) has nowhere to go. Until the drives come? | Copy to the server's own disk (/srv/arise/leavers) and move on; it goes to the Synology when it exists |  |
| 84 | The older Mac set-up (enroll-mac.sh, the Desktop linked into the SMB mount, the 15-minute copy) still ships next to the helper's Nextcloud task. Retire it? | Retire it; keep the copy script only for the pastors' personal Macs (round 1, 34) |  |
| 85 | When Convert has to wait because the person is signed in, should the Mac start their sync by itself once the conversion goes through? | Yes, by itself |  |
| 86 | Hidden files (names starting with a dot) in Desktop, Documents and Downloads: sync them or leave them on the Mac? | Sync them | hidden files in Desktop, Documents and Downloads sync too |
| 87 | Downloads syncs installers and disk images too; a 12 GB macOS installer would go to the server and the phone. A size limit in Downloads only? | No limit anywhere | no size limit on what syncs, Downloads included |
| 88 | Tell you in #alerts when a Mac has not synced for 3 days, when Nextcloud is stopped, or when the watcher is down? | Yes, once each, like a missed backup, and a sync row in arisectl doctor |  |
| 89 | After a Cut off, the Mac keeps the dead account in its Nextcloud client until someone removes it by hand. Should the helper clear it and set the Mac up again when the person is cleared? | Yes, the helper does it |  |
| 90 | Earlier versions are kept only for changes made through Nextcloud; a save over SMB or in the dashboard keeps no version. Enough, with the nightly backup? | Enough: the backup covers the rest |  |
| 91 | The older copy of a conflict in a shared folder is filed under a sync user in that folder's Trash. File it under the person who last changed the file instead? | Under the person who last changed it |  |
| 92 | When you rename someone (round 7, 13), should the helper sign the Macs into Nextcloud again under the new name and rename the Mac home folder on its next check-in? | The helper does it on its next check-in |  |
| 93 | Phones: one profile that trusts the church certificate and adds Contacts, from the Sync panel, with the Nextcloud device password as a QR code, and Contacts on a device password too so Cut off covers it? | Yes: one profile, a QR, and a device password for Contacts |  |
| 94 | Shared with me on a Mac: today there are two doors, the shared SMB share and Nextcloud's sidebar. Keep which, and should it also be a folder inside Documents? | Nextcloud's sidebar only; the SMB share stays for Finder's Open on my Mac |  |
| 95 | Should the helper report each Mac's sync state (up to date, 14 files pending, error: name too long) at every check-in? | Yes, on the Macs page and the Sync panel |  |
| 96 | You delete an account. What they shared, the links they made, their profile details? | All of it goes with the account |  |
| 97 | Department accounts (media, inedge, childrens.department) are shared logins with no personal email. The 90-day unused line and the new-device email: skip them? | Skip department accounts for both |  |
| 98 | Staff hand in their photo for the login faces how? They don't use the dashboard. | They email it to it@arisecenla.com; it shows in the Inbox app and you add it with one click |  |
| 99 | Any other profile fields worth keeping? Start date, emergency contact, shirt size, anniversary. | "Start date, emergency contact, shirt size, anniversary." | profile fields added: start date, emergency contact, shirt size, anniversary |
| 100 | Someone joins a group after a folder was shared with that group. Do they get it too? | Yes, by themselves; and someone who leaves the group loses it |  |
| 101 | Can staff share a file from a department folder (Media, Worship) with someone outside that department? | Yes, from any department folder they can write to |  |
| 102 | A file deleted on a Mac goes into Nextcloud's own trash, not the share's .Trash that Finder's Put Back and the 30-day sweep know. One Trash or two? | One: Nextcloud's deletes land in the same .Trash/<user>, so Put Back covers both |  |
| 103 | A share's Trash can swallow the disk (a 6 GB recording deleted twice). Besides the 30 days, sweep by size too? | Also sweep when a share's Trash passes 50 GB, oldest first, with a Discord line |  |
| 104 | Earlier versions for a year (round 7, 46): the backup keeps every night for 30 days, one a week for 12 weeks, then one a month. Is that cadence the year, or every night for a year? | Nightly for 30 days, weekly for 12 weeks, monthly after, as the backup keeps |  |
| 105 | A new department today means editing arise.toml twice, a share, a Nextcloud mount, a group and a checklist, in that order. One verb and one card in Directory that does all of it from a name, plan shown first? | Yes: arisectl department add, and a card in Directory |  |
| 106 | A Storage tab with the 50 biggest files, exact duplicates across homes and shares, and a find-a-file box (name, date, which Mac it came from, whether it sits in a Trash)? | Yes, all three, with Move to Trash asking for the name |  |
| 107 | When you export a song's lyrics from Proclaim, what do you actually get? | I copy and paste from Proclaim's editor; no export | lyrics arrive by copy and paste from Proclaim's editor (no export file) |
| 108 | Who is the worship leader for the Lyrics inbox? The username, first.last. | "Kristina.Robinson" | the Lyrics inbox's worship leader is kristina.robinson |
| 109 | The inbox gets a song that song_bank.json doesn't have. How should you hear about it? | A line in the morning note and Discord #daily, beside the 02:05 report's summary line |  |
| 110 | Which reporting window does the church's CCLI licence use? | Quarterly is fine; add a since-last-report button |  |
| 111 | Should the server keep its own set list per service (seeded from the live description's CCLI lines and the PC's setlist file, ticked by you, a reported flag per song) feeding the CCLI report? | Yes: a set list per service on the server, ticked, feeds the report; the PC's files seed it |  |
| 112 | Send me the six playlist links from YouTube Studio: Apostle Bryant, Pastor Vanessa, Glory Nights, Conferences, Guest Ministers, Praise Team. | "I will add them another date." | the six playlist links come later |
| 113 | Who gets to search the sermon transcripts from their own account? | Staff and Media, read-only under Sermons, printable, no sung words |  |
| 114 | With the EliteDesk's 4th-gen i5 as the server, should Whisper still run overnight for services with no StreamYard caption file? | Yes: one service a night, only where no VTT exists, after the backup |  |
| 115 | A Sunday pack: one button on a video's card gathers the clean description for StreamYard, the set list with numbers from the bank, the Shorts that link to it, the thumbnails made for that date and the chapters, Copy on each block? | Yes, build it |  |
| 116 | How long do the two services really run, for the calendar and the feed? | Sunday 10:30 to 12:30, Glory Night 19:00 to 21:00 (as now) |  |
| 117 | Which address should the Subscribe button hand phones and Macs for the calendar feed? | The full name with the church certificate, over https |  |
| 118 | In runner.json on the PC, is this server's budget keyed exactly ariseOS? | Yes, ariseOS |  |
| 119 | Claude's one weekly plan-only preview (round 7, 157): make it a timer, Wednesday 02:30, posted to #daily? And the Preview tonight tile in Control Center? | Timer on Wednesday 02:30 to #daily; the tile stays behind a confirm with the quota note, refused Sun/Mon |  |
| 120 | The morning note to #daily: every day, or only when something needs you? | Every day at 7:00, one line when all is well |  |
| 121 | Should the Monday report include the mail numbers? | Yes: forwards, failures, newsletters sent, Resend's monthly count |  |
| 122 | Should the server push Church-server-OS- only on branches, never main, the way the automator repo is held back? | Branches only; main is pushed by you |  |
| 123 | A repo with commits both here and on GitHub: how often should the server nag? | Once, then a line in the Monday report |  |
| 124 | A Why? on every red item: a drawer with the doctor's sentence, the last log lines, the matching audit entries, and the one allowed fix button (restart, re-run, clear)? | Yes, build it |  |
| 125 | A Notification Center that keeps every toast with its time and a Copy button, and dock badges: Overview's icon with the needs-you count, Inbox with unread, Updates with pending? | Yes, both |  |
| 126 | A lobby board at /board for any TV: next service countdown, stream state, the week, the verse, one line of health, no login, refreshed every minute? | Yes, build it |  |
| 127 | Spotlight actions: typing restart web, back up now, lock, empty trash lists the action with the confirm it needs? | Yes |  |
| 128 | An app shell that opens offline: the phone app paints in under a second over Tailscale and shows the last known Needs-you list greyed until the server answers? | Yes |  |
| 129 | Should arisectl doctor grow the sign-in and monitor checks: the secret file, Caddy proxying 4147, the certificate's expiry, clock drift (two-step breaks at 90 seconds), the kiosk socket, which Firefox profile is in, kiosk restarts in the last hour? | Yes, all of them |  |
| 130 | A Walk away button in the monitor's menu bar: lock, put the Firefox profile away, close Claude Desktop, darken the panel now, with an audit row? | Yes |  |
| 131 | Send to the closet screen: from a phone or Mac, Show on the monitor on a sermon, a checklist, a run sheet or a site? | Yes |  |
| 132 | The published preview: keep what you do between visits, or start fresh every time? | Start fresh on every republish, keep changes within one visit |  |
| 133 | Should the preview's dates move with the calendar, so last backup 03:00 is always last night, and the badge show the sample's age? | Yes: shift every date to today on load; the badge says sample from Nov 1 with a start over button |  |
| 134 | Members in the preview see exactly what members see on the box, even where that means for the administrator? | Yes, identical refusals |  |
| 135 | Keep the 000000 spare two-step code in the preview? | Keep it, labelled preview only on the lock screen |  |
| 136 | Who should the preview be signed in as when it opens, and which mail domain should it show? | You (bradly), with a one-click switch to Kristina and a member; addresses at arisecenla.com |  |
| 137 | How much of the docs should ride inside the preview? | Only the docs a member would read: Portal guide, Help, What's new |  |
| 138 | Should the preview carry a few failures on purpose (a missed backup night, a Mac silent three days, disk at 92 %) so you can see the red states? | Yes, behind a show problems switch on the Preview badge |  |
| 139 | Serve the demo scripts only in demo mode? | Yes: only with ARISE_DEMO=1 or on the artifact, and gzip the rest |  |
| 140 | What should this PR carry? | One PR: the overhaul, a before-and-after screenshot set, the preview link, the Round 8 page, and the answers folded into ANSWERS.md |  |
| 141 | Which artifacts should be republished? | All three at the same links, plus a one-page what changed for Kristina |  |
| 142 | This overhaul ships as? | v0.9.0 Leviticus | this overhaul ships as v0.9.0 "Leviticus" |
| 143 | Should the browser sweep run on the box itself after each Software Update, with the result in Discord #weekly and a rollback to the snapshot if the dashboard does not answer? | Yes, Saturday after the update, result to #weekly, rollback if /api/health is dead |  |
| 144 | When the sweep finds a failure, who hears? | Discord #alerts, one line per failure with the screenshot |  |
| 145 | Should python3 -m unittest refuse to pass when node is missing or app.js has a syntax error? | Yes: a syntax check of web/*.js is one of the tests |  |
| 146 | A route added without a preview sample: fail the tests or just warn? | Fail until the sample is added |  |
| 147 | A contract test between the mock and the server: every GET and the common POST flows on both, failing on a key one has and the other lacks? | Yes |  |
| 148 | Should the API sweep run against the real box after install day, read-only, as part of arisectl doctor? | Yes, GETs only, as the administrator, once a day |  |
| 149 | What should an error say when a form is missing a field? | A sentence naming the field: channel is required |  |
| 150 | ARCHITECTURE.md carries a full copy of arise.toml and a timer list, and both have drifted. One source of truth? | Yes: ARCHITECTURE links to arise.toml.example and CLAUDE.md's timer table; a test fails if it ever lists a key or timer again |  |
| 151 | About, What's new shows the top of CHANGELOG.md, which still says TPM-unlocked disk and every template preinstalled. How do we correct it? | Add a new dated section on top: core five installed, passphrase at boot on the HP, the rest unchanged |  |
| 152 | The Help app renders every docs/*.md for admins, including the question rounds, IDEAS, PARITY, ROADMAP, the ChatGPT review and the automator letters. Move the planning files out of Help? | Move them to docs/history/ (kept in git, still searchable by Claude); Help shows only the living docs |  |
| 153 | docs/CLI.md misses a dozen verbs, templates/README.md's port table is missing Immich, and ARCHITECTURE's route list is by hand. Generate the three tables from the code, with a test that fails when they differ? | Yes, all three generated; the prose stays hand-written |  |
| 154 | NODES.md still plans the Dell OptiPlex as a full ariseOS node. H6 made it the spare. What is the OptiPlex now? | It becomes Arise-Home at your house: the replica, the off-site target, Claude Desktop |  |
| 155 | SECURITY.md still carries the Postfix/Dovecot mail server design. The built thing is Resend forwarding plus the Inbox. Retire the design? | Retire it: a paragraph says forwarding and Inbox are what exists and why; the Postfix text goes to docs/history |  |
| 156 | Round 7, 47 made outside links admin-only and 7 days, but FINDER.md, DASHBOARD.md and the members' Portal guide still say never expires and right-click any file. Docs follow round 7, and what are members told? | Yes; the Portal guide says ask Bradly or Kristina for an outside link; it ends after 7 days |  |
| 157 | INSTALL.md used to have a What is running table (address, port, first login) and three docs still point at it. Where should it live now? | Generated from the templates: arisectl info --card prints it, and INSTALL.md's After the desktop appears carries the same |  |
| 158 | tests/test_docs_truth.py pins verbs and timers. Add the cheap checks it is missing: template ports against the README table, config keys in docs against arise.toml.example, OptiPlex never in a sentence about arise-server, every route in ARCHITECTURE exists, and the phrases the H rows retired (TPM unlocks, four-bay, every template preinstalled, @ad.arisecenla.com) never in a living doc? | Yes, all of them |  |

## Still needed

- Inventory the HP EliteDesk 800 G1 SFF primary server and Dell OptiPlex 3010 spare: exact CPU, installed RAM, disk models/health, firmware and TPM version. Record the DS216's DSM version, existing pool and drive health before changing storage; models and primary role are decided (H1–H6).
- The automator chat's answers to docs/ASK-THE-AUTOMATOR-CHAT.md (97).
- The four Discord webhook URLs into /etc/arise/secrets/discord.toml (101).

- Sunday: questions 1 to 7.
- Where the Synology is plugged in: on Netgear A's network it mounts directly; elsewhere it gets the Tailscale package. No cable moves either way.
- The full list of department accounts (27) and the people in staff and media (24).
- The UPS model (8), for `nut`.
- Friday: the Resend account, the domain to verify in it, the API key into `/etc/arise/secrets/resend-api-key`, the Wix contacts export.
- The printer's brand and model (round 2, 6 and 26), for CUPS.
- A Discord webhook URL for the failures and the Sunday all-green (round 2, 40).
