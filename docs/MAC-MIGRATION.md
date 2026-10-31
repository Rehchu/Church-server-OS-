# Macs — binding them to the domain and moving the data over

Two jobs, in this order, one Mac at a time:

1. **Bind** the Mac to `AD.ARISECENLA.COM` so people log in with their
   church account.
2. **Migrate** whatever is in the old local account into that person's server
   home, then have them log in as the domain user for the first time.

Nothing in this document deletes a local account. The old account stays on the
Mac until Bradly removes it himself, after the person has used the new one for
a while.

This is for **church** Macs. Personal Macs are a different case: see
§ Personal Macs below before running anything on one.

> **Since round 6 the Macs app does this for you (docs/MACS.md).** An admin
> enrols a church Mac with one Terminal line; the helper on it then makes every
> server user's account on its own, and each local account already on the Mac
> waits for an admin's choice in the Macs app: **Convert** (it becomes the
> server user, files kept, with a rollback record), **Link** (it stays, and its
> files sync as the server user) or **Leave alone**. This document stays as the
> by-hand way, and `migrate-mac-user.sh` is unchanged: use it when a Mac cannot
> run the helper, or to copy an old account's files to the server once before
> a conversion.

## The automatic way

One command does both jobs for a Mac that already has people on it:

```bash
# on the Mac, as an admin, with everyone else logged out, Ethernet plugged in
cd ~/Desktop/mac                      # the mac/ folder from the repo
sudo ./enroll-mac.sh --computer-name MEDIA-MAC-01 --dry-run   # read the plan
sudo ./enroll-mac.sh --computer-name MEDIA-MAC-01             # do it
```

`enroll-mac.sh` binds the Mac (it runs `bind-mac.sh`), lists the local
accounts that are real people (uid 501 and up, a home under `/Users`, not
`admin` or `guest`), creates each one in the directory as `first.last`
(answer 23) with their full name, copies each one's files into their server home
(`migrate-mac-user.sh`), installs the two LaunchAgents, and ends with a
report: what it did, the one-time passwords to hand over, and anything it left
for a human. Run it twice and the second run skips everything already done.

How it creates the users: over SSH by default, running
`sudo arisectl user add <name> --display "<Full Name>" --password <one-time> --groups Staff`
on the server. That needs `ssh bradly@arise-server` to work without a
password from that Mac (`ssh-copy-id bradly@arise-server` once). The fallback
is `--via api`: it logs into the dashboard as the admin and posts to
`/api/directory/users`, which is the same call the Directory app makes.

Flags worth knowing: `--map vanessa=vanessa.sanders` to pair a local
account whose name is not already `first.last` with its directory name (one
`--map` per person; the parent script gains this flag), `--only alice,bob`
to enrol some people and not others, `--skip name` to leave an account
alone, `--no-migrate` to bind and install the agents without copying
anything (a new Mac, or one where you will migrate by hand later). The by-hand steps below are what the script runs, for when one of
them needs doing alone.

## What "files saved to their profile on the server" means on a Mac

The short version: the person logs in on any church Mac with their church
password, their Desktop and Documents live on the server, and whatever else
they keep is copied to the server every fifteen minutes. In detail there are
three pieces, and each one covers a gap in the others:

| Piece | What it does | When it is the one that matters |
|---|---|---|
| **Mobile account** (the bind) | the directory account is cached on the Mac, with a local home under `/Users/<name>` | login works with the server off, on Wi‑Fi, at home |
| **Server home share** (`mount-home.sh` at login) | mounts `smb://arise-server/homes/<name>` as `/Volumes/<name>`; Desktop and Documents become links into it | every save in those two folders is on the server the moment it happens, and in the 03:00 backup |
| **Home sync** (`arise-home-sync.sh`, every 15 minutes) | rsyncs the folders in `/usr/local/arise/sync-folders.txt` to the share, newest wins, older server copies kept aside | a Mac that was never migrated (local accounts with the same names), extra folders like Downloads, and any time the share was not mounted at login |

macOS used to have "portable home directories" that synced the whole home.
Apple removed that sync in macOS 10.12 (Sierra, 2016): a mobile account still
caches the login, but nothing copies the files back any more. A true network
home over SMB makes Photos, Mail and Safari misbehave, so this is the honest
replacement: the two folders people actually work in live on the server, and
a sync catches the rest.

Round 6 (docs/MACS.md, docs/SYNC.md): Desktop and Documents sync through
the Nextcloud client, set up by the Mac helper's `nextcloud` task.
`arise-home-sync.sh` stands down for any account Nextcloud syncs, so two
programs never write the same folders; it stays the fallback on a Mac where
the Nextcloud client is not running.

What stays on the Mac on purpose, and why:

| Stays local | Why |
|---|---|
| Photos Library, iMovie / Final Cut libraries, Music library | sqlite databases inside a bundle; they corrupt over SMB and are tens of GB. They are **excluded** from the sync and copied once by the migration as a backup only |
| Mail | IMAP; it re-downloads from Google on any Mac |
| Keychain, Preferences, app containers | per-Mac and per-account; they do not travel well and hold secrets |
| Big video projects | work on them locally; drop the finished export in Documents or the `media` share |

Off-site (home, the Hub before it has a network, a laptop at a conference):
the login works because the account is cached. Desktop and Documents are
links to a share that is not there, so macOS shows them empty until the
share is reachable; with Tailscale on the laptop it is reachable from
anywhere and they fill back in. The sync agent checks for the server every
fifteen minutes and simply waits when it cannot see it. The older-copy
conflict folder lives in `~/Library/Application Support/Arise/conflicts/` on
the Mac, never on the share.

Check it is working on any Mac: `tail ~/Library/Logs/arise-home-sync.log`
shows a `sync done` line with a file count. `/Volumes/<name>` in Finder is the
server's copy.

## Personal Macs

Apostle Bryant's and Pastor Vanessa's own Macs leave the building (answer
34). A personal Mac is **not bound** to the domain: binding hands the
machine's login to the church directory, which is the wrong direction for a
computer the church does not own. What a personal Mac gets instead:

- the Tailscale app, signed in with the church login, so the dashboard and
  the shares are reachable from anywhere;
- the dashboard address, where they sign in as `bryant.sanders` or
  `vanessa.sanders` and see their home folder and the shares their groups
  allow (both are admins, answer 25, so they see everything);
- optionally, `arise-home-sync.sh` alone, installed by hand with
  `sync-folders.txt` naming the one or two folders they want kept on the
  server. It works for a local account whose name matches the directory
  name, or the Keychain holds the share password after the first mount.

Nothing is migrated from a personal Mac and no local account is renamed.

## The media Mac

The media Mac runs Proclaim and sends NDI lower thirds to the stream
(answer 50); it is a Mac, so it is enrolled like the others, keeping its
shared `media` login (answer 32). Two things are different about it:

- its video is small enough to move (answer 33): it goes to the
  `recordings` share on the Synology, by hand or with a Syncthing folder,
  and is **not** added to the home-sync list;
- Proclaim's backgrounds, loops and lower thirds get a Syncthing pair with
  the `graphics` share (answer 38; `templates/syncthing`), so they play
  from local disk and the share is the backed-up master.

## Before you start: the rules

- **Ethernet during migration.** Plug the Mac into the church switch. Copying
  a 60 GB home folder over Wi‑Fi takes hours and drops. On Ethernet it takes
  minutes to an hour.
- **Same network as the server**, and the Mac's DNS must be the server. Check
  with `dig +short _ldap._tcp.ad.arisecenla.com SRV` — it must print a line.
- **Time within 5 minutes of the server.** Kerberos refuses otherwise.
  System Settings → General → Date & Time → "Set time and date automatically"
  on. `bind-mac.sh` checks this.
- **Know the macOS version** (Apple menu → About This Mac). The scripts here
  were written against the current Directory Utility and `dsconfigad` options.
  Apple has moved AD options around between releases; where this doc is not
  sure how a particular version behaves it says "check on the Mac's version"
  rather than guess.
- An admin password on the Mac, and the `ARISE\administrator` (or Bradly's
  Domain Admin) password.

## Part 1 — bind the Mac

### The one-liner (what `mac/bind-mac.sh` runs for you)

```bash
sudo ./bind-mac.sh --computer-name MEDIA-MAC-01
```

That script checks DNS, checks the SRV records, checks the clock, then runs:

```bash
dsconfigad -add AD.ARISECENLA.COM \
  -computer MEDIA-MAC-01 \
  -username administrator \
  -ou "OU=Macs,OU=Computers,DC=ad,DC=arisecenla,DC=com" \
  -mobile enable -mobileconfirm disable \
  -localhome enable -useuncpath enable \
  -groups "ARISE\Domain Admins"
```

and prints `dsconfigad -show`, then tests `id <user>` for a domain account.

### By hand, in Directory Utility (same result)

1. Finder → Go → Go to Folder → `/System/Library/CoreServices/Applications/`
   → **Directory Utility**. Click the padlock.
2. Active Directory → ✓ → Active Directory Domain: `ad.arisecenla.com`,
   Computer ID: the name on the label (e.g. `MEDIA-MAC-01`). Click **Bind**.
3. Credentials: `administrator`. Computer OU:
   `OU=Macs,OU=Computers,DC=ad,DC=arisecenla,DC=com`.
4. Before clicking OK, open **Show Advanced Options**:
   - **User Experience**: ✓ *Create mobile account at login*,
     ✗ *Require confirmation before creating a mobile account*,
     ✓ *Force local home directory on startup disk*,
     ✓ *Use UNC path from Active Directory to derive network home location*,
     protocol **SMB**.
   - **Administrative**: ✓ *Allow administration by*: `ARISE\Domain Admins`.
5. OK. Then **Login Options** in Users & Groups: set "Display login window
   as: Name and password" so a domain user can type their name.

Log out, log in as `jane.smith` (short name is fine; `ARISE\jane.smith` also
works). The first login makes the mobile account and a local home at
`/Users/jane.smith`. That is expected and correct, see the next section.

## Mobile account vs network home — the decision

| | **Mobile account + server share** (recommended) | True network home over SMB |
|---|---|---|
| Where the home lives | on the Mac's disk, cached | on the server, every file read over the network |
| Works with the server off / on Wi‑Fi / at home | yes | no login at all |
| Speed | native | every app launch pulls its prefs over SMB; Wi‑Fi makes it crawl |
| Apple's support | this is the path Apple's own docs push | still exists, barely mentioned, sqlite-based apps (Photos, Mail, Safari) misbehave on it |
| Where the person's work ends up on the server | Desktop and Documents are kept on the server share by the mount script | automatically, everything |

So: **mobile accounts**. The person logs in with the domain password, gets a
fast local home, and `mac/mount-home.sh` (a LaunchAgent) mounts
`smb://arise-server/homes/<user>` at login as `/Volumes/<user>`. Their
**Desktop and Documents** folders are replaced by symlinks into that share, so
everything they save there is on the server and in the nightly restic backup.
Downloads, Pictures, Movies and Music stay local by default (Photos libraries
and video projects on a network share are a bad time); copy or move those by
hand when they matter.

The *Use UNC path* option tells macOS where the network home is; with
*Force local home directory* on, macOS makes the local home and only
**mounts** the UNC home in the sidebar. If a newer macOS on a given Mac no
longer shows the UNC option, the LaunchAgent does the same job by itself —
check on the Mac's version, and do not worry if the box is missing.

## Part 2 — move the old local data

### What gets copied

| Folder | Copy? | Note |
|---|---|---|
| `Desktop`, `Documents` | yes | these land on the server share and become the live Desktop/Documents |
| `Downloads` | yes | people keep things there |
| `Pictures` | yes, with a warning | a **Photos Library** can be 100 GB+; the script prints its size and asks. It must live on a local disk afterwards, not on the share |
| `Movies`, `Music` | yes | same size warning; local afterwards |
| `Library/Application Support` | selectively | the script copies only `Proclaim`, `StreamYard`, `OBS`, `Google` and `Microsoft` subfolders by default; add more with `--appsupport Name` |
| `Library/Preferences` | no | app prefs are per-Mac and per-account; re-set them |
| `Library/Mail` | **no** | the church mail is IMAP/Gmail; sign in again and it re-downloads |
| `Library/Caches`, `.Trash`, `.DS_Store` | never | |
| `Library/Keychains` | no | passwords live in Keychain Access; the person re-enters them, or exports what they need first |

### Running it

```bash
# on the Mac, logged in as a local admin, with the old user logged OUT
sudo ./migrate-mac-user.sh --from bradly --to bradly.dyer --dry-run   # look first
sudo ./migrate-mac-user.sh --from bradly --to bradly.dyer             # do it
```

What happens:

1. Mounts `smb://arise-server/homes/bradly.dyer` (prompts for the domain
   password) at `/Volumes/bradly.dyer`.
2. Writes a **before** manifest to the old user's Desktop:
   `ARISE-MIGRATION-<date>.txt` with file count and bytes per top-level folder.
3. `rsync -aHX --progress` each folder into the share, with the skip list.
   Nothing is removed from the Mac. Re-running copies only what changed.
4. Writes the **after** manifest (same counts, measured on the share) next to
   the first one, and prints both side by side. If a folder's count differs,
   the script says so and exits non-zero. Compare before signing anything off.

Ownership on the share is fixed server-side by `arisectl user add` (the home
is owned by the domain user), so the files are the person's when they log in.

### First domain login

1. Log in as the domain user on the Mac (Ethernet still plugged in).
2. The LaunchAgents mount the share, link Desktop and Documents, and start
   the fifteen-minute sync. Open Finder: the Desktop shows the migrated files.
   Have them change their one-time password: dashboard → flame menu → Change
   password.
3. Open Proclaim / StreamYard / whatever they use and check it finds its
   data. Sign into mail and Keychain-held services again.
4. Fill in the row on `mac/CHECKLIST.md`. Leave the old local account in
   place for two weeks.

## When it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Bind: "Unable to add server. Node name wasn't found" | the Mac is not asking the DC for the church domain | run `bind-mac.sh --dns <server ip>` (writes `/etc/resolver/ad.arisecenla.com`; no router change), `dscacheutil -flushcache`, retry |
| Bind: "Authentication server could not be contacted" | clock skew | turn automatic time on, wait a minute |
| Login window spins, then "unable to log in" | Mac cannot reach the DC and no mobile account yet | plug in Ethernet for the *first* login of each person |
| Share mounts but files are read-only | home folder ownership | on the server: `arisectl user homefix <name>` |
| `rsync` stops on a long filename or an `Icon\r` file | SMB name limits | the script skips `Icon\r`; for the rest, rename on the Mac and re-run |
| Everything is slow | Wi‑Fi | Ethernet |
| `arise-home-sync.log` says "could not mount" for a local account | no saved password for the share | open `smb://arise-server/homes/<name>` once in Finder as that person and tick "Remember this password in my keychain" |
| `arise-home-sync.log` says "not reachable" away from church | no VPN on that Mac | install Tailscale on it (docs/REMOTE-ACCESS.md); the next run syncs |
| A file on the server is older than the one on the Mac after a sync | it was open in an app during the run (rsync skipped it, code 23/24 in the log) | save and close; the next run copies it |
