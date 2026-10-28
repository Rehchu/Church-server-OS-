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
| 5 | Who gets a mailbox? | Staff and departments, first.last@ad.arisecenla.church | one box per staff or department account |
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
| 23 | Share link expiry? | Never, until removed | changeable per link |
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

## Still needed

- Sunday: questions 1 to 7.
- Where the Synology is plugged in: on Netgear A's network it mounts directly; elsewhere it gets the Tailscale package. No cable moves either way.
- The full list of department accounts (27) and the people in staff and media (24).
- The UPS model (8), for `nut`.
- Friday: the Resend account, the domain to verify in it, the API key into `/etc/arise/secrets/resend-api-key`, the Wix contacts export.
- The printer's brand and model (round 2, 6 and 26), for CUPS.
- A Discord webhook URL for the failures and the Sunday all-green (round 2, 40).
