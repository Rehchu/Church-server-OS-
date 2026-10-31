# What Windows 11 and macOS have, and where ariseOS stands

Bradly asked (Oct 28) for everything the two desktops have that ariseOS does
not, the comparable apps whether used daily or rarely touched, and the basics
any operating system needs. This is that map. The answers column points at
docs/ANSWERS.md round 3; "built" means it is in v0.8 "Exodus".

## Apps people open

| Windows 11 | macOS | ariseOS | Status |
|---|---|---|---|
| File Explorer | Finder | Finder (01) | built since v0.3; v0.8 adds Trash, Previous Versions, Compress, Get Info, Recents, a text editor, Open on my Mac (1, 2, 15, 16, 18) |
| Recycle Bin | Trash | Trash on every share, 30 days | built (1) |
| File History | Time Machine | Previous Versions from the nightly backup | built (2) |
| Settings | System Settings | System Settings (15), one window | built (3) |
| Windows Update | Software Update | Software Update, security automatic, the rest on his click, Saturday 03:30 | built (4, 25) |
| Microsoft Store | App Store | Store (08): the 24 templates preinstalled, a catalogue of more | built (5) |
| Task Manager | Activity Monitor | Activity Monitor | built (6) |
| Event Viewer | Console | Logs (14), search and the last error | built (7) |
| Task Scheduler | Shortcuts, Automator | Automations: every timer live | built (8) |
| Storage settings | Storage | Storage pane | built (9) |
| Calendar | Calendar | Calendar, one feed everyone subscribes to | built (10) |
| Sticky Notes, Notepad | Notes, Stickies | Notes opens Trilium | built (11) |
| Photos | Photos | Photos opens Immich, staff | built (12) |
| Weather | Weather | Weather widget, Pineville | built (13) |
| Calculator | Calculator | Calculator, and sums in Spotlight | built (14) |
| Clock | Clock | Clock: timer, stopwatch, alarm, world clock | built (14) |
| Notepad | TextEdit | the text editor in Finder | built (15) |
| Remote Desktop, Quick Assist | Screen Sharing | the closet monitor through Guacamole, Bradly only | built (17) |
| Phone Link | Continuity | the phone app and push (v0.7); Open on my Mac | built (18) |
| Snap layouts | Window tiling | Snap windows | built (19) |
| Hot corners | Hot corners | not built | his call (20) |
| Dock auto-hide | Dock hiding | the Dock hides, pins per person | built (round 4, 12, 13) |
| Sign-in greeting | (none) | "Good morning, Bradly" with the verse | built (round 4, 15) |
| Get Help | Help | Help: the docs in the dashboard, F1, a shortcut sheet | built (35) |
| Credential Manager | Keychain, Passwords | Vaultwarden (template) | since v0.5 |
| Mail | Mail | Mail (19): the church family list through Resend | since v0.6 |
| Copilot | Siri, Apple Intelligence | Assistants (17): Claude on the box, ChatGPT, Grok | since v0.6 |
| Edge | Safari | the Assistants' windows on the monitor | since v0.6 |
| Media Player | Music, TV, Podcasts | Jellyfin (template); the podcast feed is v1.0 | since v0.5 |
| Terminal | Terminal | Terminal (11) | since v0.2 |
| Paint, Snipping Tool, Clipchamp | Preview, Photos editing | not built: graphics stay on the Mac | no |
| Maps | Maps | not built | no |
| Teams | Messages, FaceTime | not built: the church has no chat app; Discord is Bradly's monitoring room (docs/DISCORD.md) | no (round 4, 89) |
| Mail (Exchange) | Mail (iCloud) | an internal mail server, forwarded to each person's own address | decided, not built (round 4, 3, 5 to 7) |
| Word, Excel, PowerPoint | Pages, Numbers, Keynote | OnlyOffice from Finder, co-editing | in the Store; the Finder hook decided, not built (round 4, 2, 70) |
| Paint, Photoshop, Premiere | Preview, iMovie | GIMP, Inkscape, Krita, Kdenlive, Shotcut, LibreOffice, Audacity in a browser window from the Store, idle-stopped | in the catalogue (round 4, 1) |
| Xbox, Game mode | Chess | a Game night entry in the catalogue, off by default | catalogue (round 4, 9) |

## Things an OS does underneath

| Windows 11 | macOS | ariseOS | Status |
|---|---|---|---|
| a local Administrator | a local admin | `arise-rescue`, the closet monitor only (SSH is keys only, and it has none) | built (21; round 4, 33) |
| BitLocker | FileVault | LUKS on the data disk, unlocked by the TPM | built (22) |
| System Restore | (Time Machine) | a system snapshot before every update, five kept | built (23) |
| Reset this PC | Recovery, Migration Assistant | `arisectl reinstall` from the Synology | built (24) |
| Active hours | (none) | the Saturday 03:30 window | built (25) |
| Event log retention | log rotation | one year | built (26) |
| Account lockout | (none by default) | none, by his answer; fail2ban removed if ever present | built as decided (27) |
| Windows Security | XProtect | ClamAV, weekly, quarantine and a report | built (28) |
| a trusted certificate | Keychain trust | the church CA, trusted by every enrolled Mac | built (29) |
| Power & sleep | Energy Saver | the monitor off 23:00 to 06:00 | built (30) |
| Shut down, Restart | Apple menu | the flame menu, admins, never during a service | built (31) |
| Accessibility | Accessibility | larger text, reduce motion, high contrast, keyboard | built (32) |
| Night light, auto dark | Auto appearance | manual only | decided (33) |
| What's new | release notes | the What's New note | built (34) |
| password rules | password assistant | the meter and the rules in words | built (36) |
| a licence | a licence | MIT | built (37) |
| screen lock timeout | screen lock timeout | the monitor at ten minutes; browsers never | decided (38) |
| Fonts | Font Book | `Media/Fonts`, installed on every Mac | built (39) |
| process limits | process limits | memory and CPU caps on every app | built (40) |
| Windows Hello | Touch ID | optional two-step with Microsoft Authenticator | built (round 2, 11) |
| UAC prompt | password for a system change | dangerous clicks ask the password again, five minutes | built (round 4, 54) |
| Domain join (Windows) | (Directory Utility) | a join script with drive letters and the certificate | decided, not built (round 4, 26, 67) |
| a second server, failover | (none) | Arise-Home as a replica with automatic takeover | decided, not built (docs/NODES.md) |
| Users & Groups | Users & Groups | Directory (03) | since v0.1 |
| Network settings | Network | Network (16), and the network stays as it is | since v0.5 |
| Backup | Time Machine | Backups (04), the drill | since v0.1 |
| Printers & Scanners | Printers & Scanners | CUPS when the printer is known | later |
| Bluetooth | Bluetooth | none: a server has no use for it | no |
| OneDrive | iCloud Drive | the shares, the portal, Syncthing | since v0.4 |
| Time sync | Time sync | chrony; the domain's clock, checked by doctor | since v0.1 |
| Firewall | Firewall | ufw and the Docker chain | since v0.2 |
| Virtual desktops | Spaces | not built | no |
| Family, Screen Time | Screen Time | not built | no |
