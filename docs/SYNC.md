# Sync: every Mac and phone, through Nextcloud

Round 6, rows 13 to 19, 39 and 40 (docs/ANSWERS.md). This page is how it works, what to do
when a file looks wrong, and what has not been tried on real hardware yet. Staff get
docs/STAFF-FILES.md instead.

## What a person sees

- **On a church Mac**, their Desktop and Documents are the same files as their home folder on
  the server, kept in full on the Mac, so they work with no network too (row 13).
- In Finder's sidebar, under Locations, **Nextcloud** holds Church, their department folders,
  Pastors (the two pastors only), Alexandria and Shared with me. Those files download when
  they are opened and show a cloud badge until then (row 16).
- **Off-site**, the same thing works over Tailscale (row 17). There is no size limit (row 18).
- **On a phone**, the Nextcloud app shows the same folders. Files only: nothing of the server
  OS (rows 19 and 39). The same through the web page, https://cloud.ad.arisecenla.com.
- **Department logins** (media-mac, inedge, childrens.department) sync like a person (row 40).

## How it is built

```
 Mac (Nextcloud client)  ─┐
 Phone (Nextcloud app)   ─┼─ https://cloud.ad.arisecenla.com ─ Caddy (church certificate)
 Web page                ─┘                                      │
                                                    127.0.0.1:8091 (never the internet)
                                                                 │
                                    Nextcloud 29 container (templates/nextcloud)
                                    ├── each person's files = /srv/arise/homes/<user>
                                    ├── Church, departments  = /srv/arise/shares/<folder>
                                    ├── Pastors               = /srv/arise/pastors
                                    └── Shared with me        = /srv/arise/shared/<user>
```

- **Nothing is copied.** A person's Nextcloud files folder is a link to their server home, and
  the shares are mounted over the same folders Samba serves. A file saved on a Mac shows in the
  dashboard's Finder and over SMB, and the other way round.
- **Sign-in is the domain's.** Nextcloud reads the directory over LDAPS as `arise-nextcloud`, a
  read-only account `arisectl cloud setup` makes. The login is first.last. A disabled account
  stops syncing at the next check (at most ten minutes).
- **No device holds a domain password.** Every Mac and phone signs in with its own *app
  password*, which only Nextcloud can check and which you can cut off on its own. The server
  issues it, shows it once, and keeps only a fingerprint of it. Nextcloud is set to keep no
  copy of a domain password either, not even for a web sign-in.
- **Who sees which folder** follows the same rule as the Samba lines (sharing.py): Church is
  everyone's; a department folder is written by all staff, admins and the department's own
  login, and read by the department's people; Pastors is the two pastors' only, admins
  included. tests/test_cloud.py checks the two agree for every kind of person.
- **Nextcloud's own sharing is off.** Sharing is the server's Share with…, so the dashboard, SMB
  and the clients never disagree about who has what.
- **Changes made over SMB reach the clients** through `arise-cloud-watch`, which tells Nextcloud
  to rescan just the folder that changed, a few seconds later.
- **File locking:** Redis. Two Macs saving one file at the same moment get a conflict copy,
  not a lost save.

## Conflicts: newest wins (row 15)

When the same file changed in two places before they synced, the client keeps both, naming one
`Budget (conflicted copy 2026-10-29 101500).xlsx`. Every hour (`arise-cloud-conflicts.timer`,
never during a service) the server settles each pair:

- the **newer** copy keeps the real name;
- the **older** copy goes to that folder's **Trash** (the same 30-day Trash as a delete in
  Finder), with a record so **Put Back** returns it to where it was;
- each one is written to `/var/lib/arise/cloud-conflicts.jsonl` and shows in the Sync panel.

Nothing is deleted by this. `sudo arisectl cloud sweep --dry-run` shows what it would do.

## When a file looks wrong

1. **The newest version is not the one you wanted.** Open the Trash of that folder (Finder on
   the dashboard, or the share's `.Trash` over SMB): the other copy is there under the same
   name. Put Back, or drag it out.
2. **A file is missing on a Mac.** Click the Nextcloud icon in the Mac's menu bar: it says what
   it is doing, and lists anything it could not sync and why (a name with a character the
   server refuses, a file open in an app). The file is still on the server: look in the
   dashboard's Finder.
3. **Something deleted on the Mac came back.** The server still had it and the Mac was offline.
   Delete it again once the Mac is back on the network.
4. **A Mac says it is signed out.** Its device was cut off. On that Mac, in Nextcloud → Settings,
   remove the account (the files on the Mac and the server stay), then run the Nextcloud task for
   that Mac again in the Macs app: it gets a new app password. While the client still holds the
   account the task leaves it alone, so a re-run never signs a working Mac out.
5. **Nothing syncs anywhere.** `sudo arisectl cloud status`, then `docker ps` for
   `arise-app-nextcloud`. `sudo arisectl app restart nextcloud` is the small fix.

## The Sync panel (admins)

Dashboard → Sync. For each person: their devices and when each last synced, how many conflicts
were settled for them, and their storage against the 50 GB home quota. **New device…** makes an
app password for a phone or a Mac set up by hand (shown once). **Cut off** stops one device;
**Cut off all** (typed name) stops every sign-in the person has: a lost phone, someone leaving.
Their files stay. The same from the command line:

```
sudo arisectl cloud status
sudo arisectl cloud people
sudo arisectl cloud app-password jane.doe "Jane's iPhone"
sudo arisectl cloud revoke jane.doe "Jane's iPhone"      # one device
sudo arisectl cloud revoke jane.doe                      # every sign-in
sudo arisectl cloud sweep [--dry-run]
sudo arisectl cloud setup [--dry-run]                    # safe to run again
```

## Setting up a Mac

The Mac helper does it (the Macs app's `nextcloud` task, mac/helper/tasks/nextcloud.sh):

1. installs the official **Nextcloud desktop client** (the File Provider build), refusing any
   package that is not signed by Nextcloud GmbH (Apple team NKUJUXUJ3B) and notarised;
2. asks the server for that person's device app password, which the server gives only for a
   task an admin queued on that Mac;
3. takes a local disk snapshot, then, inside the person's own session, signs the client in
   and adds Desktop and Documents as full sync folders. The first sync **merges**: what is on
   the Mac and what is on the server both stay; where both have the same file with different
   contents, both are kept and the hourly sweep settles them as above;
4. if the person is not signed in at that moment, it finishes at their next sign-in.

A **local account linked to a server user** (round 6, kept local) gets exactly the same, signed
in as the server user: its Desktop and Documents sync to that person's server home. The local
login itself is not touched.

**The first time** the client runs, macOS asks the person once to let Nextcloud use the Desktop
and Documents folders. They click Allow (docs/STAFF-FILES.md says so).

**iCloud's Desktop & Documents** must be off on that account; the task stops and says so if it
is on.

## Setting up a phone

Phones are not enrolled, so two things are done by hand, once (docs/STAFF-FILES.md has the
person's half):

1. **The church certificate.** cloud.ad.arisecenla.com is signed by the church's own authority
   (Caddy's `tls internal`), which a phone does not trust until it has the root:
   http://arise-server:4147/ca.crt, opened on the phone on the church network. An iPhone then
   needs Settings → General → About → Certificate Trust Settings → turn it on. Without it the
   Nextcloud app refuses the server.
2. **A device password**: Sync → the person → New device… → "Kristina's iPhone". They type it in
   the app's "Log in with an app password", never their domain password.

Off-site the phone needs Tailscale on.

## The name in DNS

`cloud.ad.arisecenla.com` is a CNAME to this box in the domain's own DNS; the installer adds it.
By hand:

```
sudo samba-tool dns add 127.0.0.1 ad.arisecenla.com cloud CNAME arise-server.ad.arisecenla.com -U administrator
```

The Macs and phones off-site resolve it the same way as the dashboard's name: Tailscale's split
DNS for ad.arisecenla.com. No router, no port forward, nothing on the internet (rule 7).

## Pieces

| Where | What |
|---|---|
| `templates/nextcloud/` | the containers: Nextcloud 29, MariaDB, Redis, cron; published on 127.0.0.1:8091 |
| `server/arise_server/cloud.py` | the mounts, the domain sign-in, app passwords, the conflict sweep, the watcher |
| `config/caddy/Caddyfile` | `cloud.ad.arisecenla.com` on the church certificate |
| `config/systemd/arise-cloud-*` | the watcher, and the hourly conflict sweep |
| `mac/helper/tasks/nextcloud.sh` | the Mac side |
| `/etc/arise/secrets/apps/nextcloud.env` | its passwords (database, the arise-sync admin, the directory account); root only |
| `[cloud]` in arise.toml | the host name, the folders that sync in full, the client version |

## Not yet tried on real hardware (Oct 29)

Built and tested on a Linux box with no Docker daemon and no Mac. The Python side and the
script's config editing are tested; these have not run anywhere yet:

- Nextcloud 29 serving a person's files through the link to their home
  (`localstorage.allowsymlinks`), and the read-only/read-write pair of mounts at one place
  resolving by priority the way `files_external:import` is given it;
- the LDAPS sign-in against Samba from inside the container (the DC's own certificate authority
  is mounted for it);
- the desktop client's command-line sign-in, the second folder pair written into its config,
  and the File Provider turning on from its settings, on a real Mac.

The first church Mac is the test. If any of it misbehaves, the fallback for that piece is in
the code comments next to it.
