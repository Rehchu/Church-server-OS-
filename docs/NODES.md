# The nodes: Arise-Pineville, Arise-Home, Arise-Alexandria

Bradly's decision, Oct 28 (docs/ANSWERS.md round 4, 106 to 115). The church
has two Windows PCs, one of them the Dell OptiPlex. Both are wiped and both
get the full ariseOS:

| Node | Where | What it is |
|---|---|---|
| **Arise-Pineville** (`arise-pineville`) | the church closet | the church's server: the domain, the files, the apps, the timers, the closet monitor. The **primary**. The strongest of the two PCs, decided from Friday's specs (109) |
| **Arise-Home** (`arise-home`) | Bradly's house | the full OS on the other PC. His control node ("the one I can actually push updates and stuff through and maintenance the other one so I don't have to travel to the church") and a live replica of Pineville |
| **Arise-Alexandria** (`arise-alexandria`) | the Alexandria campus, when a third PC comes | a second domain controller and the campus screen there |

Nothing in this document is built yet. v0.8 ships one box called
`arise-server`; the node work is the first block of v0.8.1 (docs/ROADMAP.md)
and the hostname becomes a per-node value then. Friday's specs decide which
PC is which.

## What replicates, and how

Three kinds of data, three honest answers.

| Data | Between Pineville and Home | How |
|---|---|---|
| **The domain**: users, passwords, groups, DNS | both ways, live | Home joins as a second Samba domain controller; Samba replicates the directory itself. Sysvol (group policy) is not replicated by Samba and is not used here |
| **Files**: every share and every home | both ways, continuous | Syncthing between the two boxes over Tailscale. When the same file changes in both places before they sync, both copies are kept (`name.sync-conflict-…`), never silently overwritten; the Storage pane lists conflict copies |
| **The apps' data**: Immich's library and database, BookStack, Vaultwarden, Trilium, Uptime Kuma's history, every container's volume | **one way, nightly**, primary to standby | after the 03:00 backup the standby pulls each app's data folder and a dump of each database. Home runs the same apps, so it can take over with last night's state |
| **Backups**: the restic repository | Home holds a full second copy | the off-site backup Bradly said "not now" to for the cloud (112) comes free with the home node; the monthly drill runs on both |

Why the apps' databases do not sync live: two running copies of a database
cannot be merged back together. Immich at Pineville and Immich at Home each
believing it owns the library would fork the data the first time both were
used, and nothing could reconcile it. So one node runs the apps for real at
any moment and the other keeps a nightly copy. Bradly asked for "FULLY SYNCED
back and forth" (115); files and the domain are that, the apps are a
nightly copy, and the dashboard says which is which.

## Who is primary, and the takeover

One node holds the **primary role**: it runs the automator at 02:05, the
backups at 03:00, the mirror, the scan, the update window, and the apps for
real. The other is the **standby**. The role is a record both nodes read
(`/var/lib/arise/primary.json`, mirrored by Syncthing and checked over
Tailscale), not an assumption.

Bradly chose **automatic takeover after an hour** (113). The fence that
makes that safe:

1. Home watches Pineville over Tailscale. After sixty minutes without a
   reply it promotes itself: takes the primary record, starts the apps from
   last night's copy, enables the timers, and pushes "Arise-Home took over
   at HH:MM; Pineville unreachable since HH:MM".
2. The nightly job and the timers run on **exactly one node**. A standby
   never enables them; a node that finds the record says the other is
   primary disables its own.
3. When Pineville comes back it reads the record, sees Home holds the role,
   and **stays standby** until Bradly hands the role back from the Nodes page
   (`arisectl node promote pineville`, the name typed). Nothing flips back
   on its own, so a flapping internet link at the church cannot make the
   automator run twice in one night.
4. Handing the role back syncs the apps' data from Home to Pineville first
   (the direction reversed for that one run), then moves the timers.

While Home is primary, the church's Macs reach it over Tailscale: the
domain already lives in both places, and the Macs' resolver files name both
DCs (docs/DIRECTORY.md). Files at Pineville are whatever Syncthing had
mirrored before the box went down.

## The Nodes page

A page on both dashboards (admins):

- each node: online, its address on Tailscale, the primary badge, the last
  sync of files and of the apps' data, `arisectl doctor`'s summary;
- **Update now**: pushes an ariseOS update to the other node over Tailscale
  SSH with keys, a system snapshot first, refused during a service (114);
- **Open its dashboard**, **Run a command** (`arisectl` verbs only, logged in
  the audit);
- **Promote** / **Hand back**, the name typed and the password asked again.

Everything the Nodes page does is an `arisectl node …` verb, so it works
from the terminal when the dashboard is what is broken.

## Node mode `home`

Arise-Home sits on Bradly's home network next to his own devices. Rule
(115): invisible to that network except through Tailscale.

- The installer gets `--node home`: Samba binds its DNS and the domain to
  the Tailscale interface only; nothing answers the home LAN. ufw allows
  the dashboard and SSH from Tailscale only.
- It takes a normal DHCP address from the home router like any other box;
  nothing is pinned, no router changes (the rule that never bends).
- Bradly's own Mac and phone reach it through Tailscale, exactly as they
  reach Pineville.
- Staging mode (`--staging`) stays what it is: a box that is *going to* the
  church. A home node is a box that stays.

## Node mode `alexandria`

The same shape as Home without the replica of the apps: a second domain
controller, the campus screen, Syncthing for the shares that campus uses.
docs/MULTI-SITE.md keeps the campus picture.

## What Friday decides

- The makes, models, RAM and disks of both PCs (111): the stronger is
  Pineville.
- Whether the Dell is Pineville or Home.
- The disk split on each (91) and the Synology layout (55).

## Until it is built

The one-box install is what v0.8 ships. Bradly can install it at home in
staging mode now and carry it to the church (INSTALL.md); the second box
waits for the node work. Nothing about the one-box install is wasted: a
Pineville box becomes the primary node by a flag, and `arisectl reinstall`
is how a Home box is first seeded from Pineville's backup.
