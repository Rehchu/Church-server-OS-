# Macs — binding them to the domain and moving the data over

Two jobs, in this order, one Mac at a time:

1. **Bind** the Mac to `AD.ARISECENLA.CHURCH` so people log in with their
   church account.
2. **Migrate** whatever is in the old local account into that person's server
   home, then have them log in as the domain user for the first time.

Nothing in this document deletes a local account. The old account stays on the
Mac until Bradly removes it himself, after the person has used the new one for
a while.

## Before you start: the rules

- **Ethernet during migration.** Plug the Mac into the church switch. Copying
  a 60 GB home folder over Wi‑Fi takes hours and drops. On Ethernet it takes
  minutes to an hour.
- **Same network as the server**, and the Mac's DNS must be the server. Check
  with `dig +short _ldap._tcp.ad.arisecenla.church SRV` — it must print a line.
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
dsconfigad -add AD.ARISECENLA.CHURCH \
  -computer MEDIA-MAC-01 \
  -username administrator \
  -ou "OU=Macs,OU=Computers,DC=ad,DC=arisecenla,DC=church" \
  -mobile enable -mobileconfirm disable \
  -localhome enable -useuncpath enable \
  -groups "ARISE\Domain Admins"
```

and prints `dsconfigad -show`, then tests `id <user>` for a domain account.

### By hand, in Directory Utility (same result)

1. Finder → Go → Go to Folder → `/System/Library/CoreServices/Applications/`
   → **Directory Utility**. Click the padlock.
2. Active Directory → ✓ → Active Directory Domain: `ad.arisecenla.church`,
   Computer ID: the name on the label (e.g. `MEDIA-MAC-01`). Click **Bind**.
3. Credentials: `administrator`. Computer OU:
   `OU=Macs,OU=Computers,DC=ad,DC=arisecenla,DC=church`.
4. Before clicking OK, open **Show Advanced Options**:
   - **User Experience**: ✓ *Create mobile account at login*,
     ✗ *Require confirmation before creating a mobile account*,
     ✓ *Force local home directory on startup disk*,
     ✓ *Use UNC path from Active Directory to derive network home location*,
     protocol **SMB**.
   - **Administrative**: ✓ *Allow administration by*: `ARISE\Domain Admins`.
5. OK. Then **Login Options** in Users & Groups: set "Display login window
   as: Name and password" so a domain user can type their name.

Log out, log in as `jsmith` (short name is fine; `ARISE\jsmith` also works).
The first login makes the mobile account and a local home at
`/Users/jsmith`. That is expected and correct, see the next section.

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
sudo ./migrate-mac-user.sh --from oldbradly --to bdyer --dry-run   # look first
sudo ./migrate-mac-user.sh --from oldbradly --to bdyer             # do it
```

What happens:

1. Mounts `smb://arise-server/homes/bdyer` (prompts for the domain password)
   at `/Volumes/bdyer`.
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
2. The LaunchAgent mounts the share and links Desktop and Documents. Open
   Finder: the Desktop shows the migrated files.
3. Open Proclaim / StreamYard / whatever they use and check it finds its
   data. Sign into mail and Keychain-held services again.
4. Fill in the row on `mac/CHECKLIST.md`. Leave the old local account in
   place for two weeks.

## When it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Bind: "Unable to add server. Node name wasn't found" | DNS is not the DC | fix DHCP DNS, or set the Mac's DNS to the server by hand, `dscacheutil -flushcache`, retry |
| Bind: "Authentication server could not be contacted" | clock skew | turn automatic time on, wait a minute |
| Login window spins, then "unable to log in" | Mac cannot reach the DC and no mobile account yet | plug in Ethernet for the *first* login of each person |
| Share mounts but files are read-only | home folder ownership | on the server: `arisectl user homefix <name>` |
| `rsync` stops on a long filename or an `Icon\r` file | SMB name limits | the script skips `Icon\r`; for the rest, rename on the Mac and re-run |
| Everything is slow | Wi‑Fi | Ethernet |
