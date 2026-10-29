# The church Macs

The server is the church's own Active Directory. It is a Samba AD domain
controller on `arise-server` (realm `AD.ARISECENLA.COM`, NetBIOS `ARISE`).
There is no Microsoft licence and no Microsoft server anywhere, and no Apple
MDM or Apple certificate either (round 6, 1).

Bradly (Oct 29): "this should run like Active Directory and actually add and
remove user accounts from the local Macs on the network (not the private ones
that people own) ... We don't want to pay for Active Directory, we want the
server to be our own Active Directory."

This page covers:

- how a Mac becomes a church Mac
- what the server then does to it on its own
- what waits for an admin
- what it never does

The code is in:

- `server/arise_server/macs.py`
- `mac/helper/`
- the **Macs** app on the dashboard (admins only)

## Which Macs

Only a Mac enrolled with the one Terminal line below is a church Mac. That Mac
carries `church_owned` in the server's records, and enrolment is the only thing
that sets it.

A Mac nobody enrolled is never listed and never touched. That includes
Apostle Bryant's and Pastor Vanessa's own Macs, a volunteer's laptop, and any
Mac that was only bound by hand with `bind-mac.sh`. Personal Macs keep
Tailscale and the dashboard (docs/MAC-MIGRATION.md § Personal Macs).

## Watch mode first (round 7, 4)

The helper starts in **watch mode** (`[macs] watch = true`, the default). In
watch mode the helper still checks in every five minutes and reports what it
finds, and the server still makes the whole plan, but it hands out **no task**
except a notice (a notice changes nothing on the Mac). Each check-in's answer
starts with `WATCH <n>`: the number of tasks that would run.

The Macs app shows a **Watch mode** bar with what would happen on each Mac, line
by line ("would make levi.mercer and link levi to it", "would run: The church
apps"), and Needs You carries one line until it is switched on.

**Switch on** is in that bar, for admins only. It asks for the word `on` and the
admin's password again, and is written in the audit log (`macs.live`). It is
for the whole box, not per Mac. **Back to watch mode** is the same, with the
word `watch` (`macs.watch`). The switch is kept in the state file; it wins over
`[macs] watch` from then on.

## Enrolling a Mac (round 6, 37)

1. Open the **Macs** app and press **Enrol a Mac**. A name is optional: leave
   it empty and the Mac keeps the name it has (round 7, 35); type one
   (`OFFICE-MAC-02`) only to rename it. Press **Make the line**.
2. On the Mac, open Terminal, paste the line, and press Return. It asks for the
   Mac's own password (sudo), then for the domain administrator's password.

The line works **once**, for **one hour**. It looks like this:

```
curl -fsSL http://192.168.1.20:4147/ca.crt -o /tmp/arise-ca.crt &&
[ "$(shasum -a 256 /tmp/arise-ca.crt | cut -c1-64)" = "<the certificate's fingerprint>" ] &&
curl -fsSL --cacert /tmp/arise-ca.crt --resolve arise-server.ad.arisecenla.com:443:192.168.1.20 \
  https://arise-server.ad.arisecenla.com/mac/enrol.sh |
sudo bash -s -- --token <one-time> --dns 192.168.1.20 --name OFFICE-MAC-02 --server https://arise-server.ad.arisecenla.com
```

Why it looks like that:

- **The address, not the name.** A new Mac cannot look up
  `arise-server.ad.arisecenla.com` yet, so the line uses the server's address.
  Writing the `/etc/resolver` file that teaches it the name is the first thing
  enrolment does. Set `[macs] server_ip` if the guessed address is wrong.
- **The fingerprint check.** The church certificate comes first, and the line
  checks its fingerprint against the one the server printed. The script then
  arrives over HTTPS that the Mac can verify. Before Caddy has ever run, there
  is no certificate, and the line falls back to plain http on the church
  network.

What `mac/helper/enrol.sh` does, in order. It is safe to run again.

0. **A Time Machine backup** (round 7, 6). When the Mac has a Time Machine
   destination (`tmutil destinationinfo` names one), it runs
   `tmutil startbackup --block` before anything changes. When there is none, or
   the backup cannot run, it says so and goes on. `--no-backup` skips it.
1. **DNS.** It points the Mac at the server for the church domain only,
   through `/etc/resolver/ad.arisecenla.com`. No router is touched.
2. **The certificate.** It trusts the church certificate in the System
   keychain. macOS asks for approval once; a daemon cannot do this by itself.
3. **The domain.** It joins the domain with `mac/bind-mac.sh`, unchanged,
   which checks DNS, the SRV records and the clock first. The Mac keeps its
   name; only the domain's computer account takes a short plain form of it
   (15 letters, digits and dashes: "Office Mac 2" joins as `Office-Mac-2`),
   which the server keeps as the Mac's `ad_name` for **Cut off**.
4. **The key.** It trades the token for the Mac's own key. The key is kept in
   `/var/db/arise/helper.key` (root, 0600). The server keeps only its sha256.
5. **The helper.** It installs the helper at `/usr/local/arise/helper/`, with
   the LaunchDaemon `com.arisechurch.helper`, which runs at boot and every
   five minutes.
6. **The first check-in.** It runs the helper once. The server then hands out
   the first tasks:
   - the certificate check
   - the login window
   - `ariseadmin`
   - FileVault
   - the printers
   - the bookmarks
   - Tailscale
   - the welcome page, the Mac's settings, the church apps, the DNS filter
     (all below)
   - an account for every server user

   In watch mode these wait in the Macs app as "would run" until Switch on.

7. **Full Disk Access, by hand, once: Bradly, while enrolling** (round 7, 39).
   macOS hides everyone's Desktop and
   Documents even from root, and no script can grant the exception. Enrolment
   opens System Settings > Privacy & Security > Full Disk Access; add
   `/usr/local/arise/helper/arise-mac-helper` and `/bin/bash` there. Until
   then the Mac's card says **no Full Disk Access**, and no profile is ever
   removed from that Mac: the helper reports a folder it could not read, and
   the server refuses any listing that came back unread, has items but no
   files, or holds a file name with a tab or a line break.

At the end it lists the local accounts already on the Mac. Each is linked to a
server user by default (below); in watch mode that is only shown as "would
link" or "would make … and link" until Switch on.

### A Mac where you're not an admin (the office Mac)

Enrolment needs a Mac admin once. On the office Mac that is the pastor's account
(Oct 29).

1. The pastor signs in, or types their password while you sit at the Mac. Your
   own standard account cannot do this step: macOS refuses `sudo` from a
   standard account, even with an admin's password.
2. Terminal, paste the enrol line, Return. The pastor types their password
   for `sudo` and for the certificate prompt. You type the domain
   administrator's password, which is the server's.
3. Full Disk Access (step 7 above): macOS asks for an admin name and password.
   The pastor types theirs.

After that the hidden `ariseadmin` exists on that Mac. Its password is on the
Mac's card in the Macs app (Show admin password); use it for any later admin
prompt there instead of asking the pastor again. The pastor's own account is
linked (round 7, 23): it stays an admin, with the same password, files and
FileVault unlock, and its files sync to their server account.

## Accounts, on their own (the directory)

**Every server user gets an account.** Every enabled directory user gets a
mobile (AD) account made on every church Mac with:

```
/System/Library/CoreServices/ManagedClient.app/Contents/Resources/createmobileaccount -n <user> -v
```

So their face is on the login window before they ever sign in there. A new
user reaches every church Mac within about five minutes (one check-in).

A person who already has a **linked local account** on a Mac gets no second,
mobile account there (round 7, 25): they keep signing in to their own account,
which syncs as them.

Some users never get an account:

- the names in `[macs] exclude`
- the box's own accounts, whatever the config says: `administrator`,
  `krbtgt`, `guest`, `arise-rescue`, `arise`, `arise-kiosk`, `arise-git`,
  `arise-kb`, `ariseadmin`

**A disabled user's profile comes off by the checked path, and only that
path.** A user is disabled by hand or by offboarding's day-30 sweep. Their
profile then comes off every church Mac where they have one, like this:

1. The server queues `remove_profile` for each of those Macs. Offboarding
   queues it too, and puts the folder their files were moved to first in the
   list of places to look.
2. The helper sends the server a list of every file in their Desktop,
   Documents, Downloads, Pictures and Music (`[macs] sync_folders`, round 7, 42
   and 43). The list has the name, size and date of each file, never its
   contents. Library packages (`Photos Library.photoslibrary`,
   `Music Library.musiclibrary` and the rest, see docs/SYNC.md) are left out of
   the list, because they never sync.
3. The server checks each one against its own copy, in places the **server**
   chooses: their home, and where offboarding moved it. It never looks where
   the Mac says to. A file counts only when the server has it at the same
   size, and the copy on the Mac is not newer.
4. Only when every file counts does anything change. First the rest of their
   Mac folder (the library packages and whatever else does not sync) is kept as a
   compressed disk image in `/Users/Deleted Users/<user>-<date>.dmg` on that
   Mac, the way macOS's own Delete User can; if that copy cannot be made,
   nothing is removed. Then the account is deleted, with
   `sysadminctl -deleteUser`. Deleting the disk image later is Bradly's click. Otherwise the task is refused, says how many
   files are missing or newer on the Mac, and is tried again at the next
   check-in.

The server also refuses the check unless a removal of that person is really
waiting on that Mac. So a Mac's key is not a way to probe other people's
folders.

Some accounts are never removed by this path:

- **A signed-in person.** Their removal waits.
- **A local account.** Only AD accounts are removed this way.
- **An account with a home outside `/Users`.** It is left for an admin.
- **A profile that is only unused** (round 6, 5). It is never removed; only a
  disabled user's is.

## Accounts already on a Mac: linked by default (round 7, 23, 25, 26)

Every local account the helper finds is **linked** by default to a server user
(Bradly, round 7, 23, and his follow-up):

- **A clear match links to that user.** A clear match is a server user with the
  same short name, or `first.last` made from the account's full name where that
  server user's own name agrees (or none is on file).
- **No clear match: a server user is made, then linked.** Its name is
  `first.last` from the account's full name, `first.last2` when that name is
  already someone else's (row 12). It gets a temporary password, which waits in
  the Mac's 0600 secrets file until an admin presses **Show it once** in the
  Mac's card (password again, audited, then forgotten). The person chooses
  their own at the first sign-in (round 5, 5).
- **A full name that is not a first and a last name** (a one-word name such as
  "Media") waits for a choice by hand.

In watch mode none of this happens: the card says "would link kristina to
kristina.robinson" or "would make levi.mercer and link levi to it", and nobody
is made until Switch on. The box's own accounts (`[macs] exclude` and the list
below) are never linked.

The admin can still change any account's choice with **Choose…**. A new choice
cancels the default's open link and sync tasks for that account.

- **Convert** stays available per account.

- **Convert** (by hand only). The account becomes the server user.
  - The Mac's helper stops if the person is signed in.
  - It writes a rollback record: `/var/db/arise/convert/<old>.plist`, 0600,
    with the UID, groups, home, shell and password hash.
  - It deletes only the local record (`dscl . -delete`) and keeps the home.
    The home moves to `/Users/<first.last>` if that is free.
  - It runs `createmobileaccount -n <first.last> -h <home>` and gives the
    files to the AD uid.
  - Admin rights carry over only if the local account had them. Staff are
    standard users (round 6, 8).
  - **Undo** puts the local account back from the record. If
    `createmobileaccount` fails partway, the helper does the Undo by itself,
    so nobody is left without an account to sign in to.
  - It refuses when the account holds the Mac's Secure Token and FileVault is
    on (see "Not verified" below): Link is the answer there.
- **Link.** The local account stays exactly as it is. The Nextcloud client in
  that account signs in as the server user, so its synced folders go to that
  person's server home. This is the default.
- **Leave alone.** Nothing happens to it, ever.

The Macs app's **Choose…** suggests the default's server user. If the chosen
server user does not exist yet, it is made first with a temporary password,
shown to the admin once.

Convert and Link also queue the `nextcloud` task for that person.

**Retire** is refused until every local account on the Mac has a choice and
every AD account's files are on the server.

`mac/migrate-mac-user.sh` and `enroll-mac.sh --map` stay as they were. Use
them for a Mac that cannot run the helper, or to copy an old account's files
to the server once before converting it.

## The rest of what the helper does

| Task | What happens on the Mac |
|---|---|
| `login_window` | A list of faces, plus Other… (`[macs] login_window = "faces"`, or `"name"`), and the login window text, word for word: "Arise Church: sign in with your church account. Help: Bradly" (round 7, 27; `[macs] login_text`) |
| `welcome` | Round 7, 3: at each person's first sign-in on that Mac, `Welcome to Arise Church.html` on their Desktop: their login, where their files are (the synced folders), and who to ask (`[macs] help`: Bradly, Kristina, Ronnie). A small LaunchAgent (`com.arisechurch.session`, in every session) puts it there once, and shows waiting notices |
| `mac_settings` | Guest User on (round 7, 33; macOS wipes it at sign-out). App Store installs need an admin (round 7, 30): `restrict-store-require-admin-to-install` in `com.apple.appstore`. Staff stay standard users. **No screen lock and no automatic sign-out are ever set** (round 7, 28 and 29) |
| `apps` | Round 7, 31: the church apps from each maker's own address, refused unless signed by the expected Developer ID team and notarized (below) |
| `dnsfilter` | Round 7, 71 and 72: every network service's DNS goes to a malware and adult filter (Cloudflare for Families). `/etc/resolver/ad.arisecenla.com` keeps the church domain on the server. The servers each had before are kept; **DNS filter off** in the card puts them back. Personal devices are never touched |
| `notice` | Round 7, 84: a Mac notification for one person, shown now if they are signed in, else at their next sign-in. Goes out in watch mode too |
| `ariseadmin` | A hidden admin with a random password. The password is changed every 30 days and kept on the server. If the server cannot be reached, the new password is kept on the Mac (root only) and sent at the next check-in |
| `filevault` | `fdesetup enable -defer`: FileVault turns on at the next sign-in, and the recovery key goes to the server after that |
| `printers` | `lpadmin`, from `[macs] printers` |
| `bookmarks` | A **Church** folder in Chrome (managed bookmarks), and `.webloc` links in `/Library/Arise/Church Links` for Safari |
| `certificate` | Checks that the church certificate is trusted. Trusting it needs a person at the Mac, so enrolment does that part |
| `updates` | Overnight, 01:00 to 05:00, once a night, never during a service. Turns on Apple's automatic security responses and installs security-labelled updates. Asks for a restart in a dialog. Never a new macOS |
| `tailscale` | Installs Tailscale if it is missing and turns on "use Tailscale subnets" (`--accept-routes`), so a laptop off-site reaches the server at its church address through the route the server advertises (docs/REMOTE-ACCESS.md): check-ins, Nextcloud and the shares carry on away from church. Someone signs it in once with the church login; the server's route is approved once in the Tailscale admin |
| `nextcloud` | Runs `/usr/local/arise/helper/tasks/nextcloud.sh --user <first.last> --local <short name> --server <url>`. The Nextcloud work supplies that script; until it exists, the task reports *skipped* |
| `retire` | Checks every AD account's files as above, then `dsconfigad -remove`, then removes the helper. Erasing the Mac is Bradly's to do |

The ariseadmin password and the FileVault key are kept in
`/etc/arise/secrets/macs/<mac>.json` (0600, root). To see one, an admin
presses **Show admin password** or **Show FileVault key** and types their
password again (remembered for five minutes). Each look is written in the
audit log; the value never is.

**Cut off** is for a lost or stolen Mac (round 6, 11):

- the Mac's key stops working at once
- its waiting tasks are cancelled
- its computer account is disabled (`samba-tool user disable NAME$`)

The app then lists what to revoke by hand: the Mac's Tailscale machine, and
each person's Nextcloud sessions on it. There is no remote erase.

**Never during a service.** On Sundays at 10:30 and Mondays at 19:00, the
server answers every check-in with `HOLD` and hands out nothing. On `HOLD` the
helper also quits the Nextcloud client in each signed-in session, so it does
not use the church's upload during the stream, and reopens it at the first
check-in after the service (round 7, 92). In watch mode there is no `HOLD`
(nothing on the Mac changes) and nothing goes out.

## The church apps (round 7, 31)

Nextcloud, Firefox, Google Chrome and Zoom go on every church Mac. Each is
downloaded from its maker's own address and installed only when
`pkgutil --check-signature` shows "Developer ID Installer: … (TEAM)" for the
expected team and `spctl` says it is notarized. An app already there, signed by
that team, is left alone.

| App | Apple Team ID | Download |
|---|---|---|
| Firefox | `43AQ936H96` (Mozilla) | `https://download.mozilla.org/?product=firefox-pkg-latest-ssl&os=osx&lang=en-US` |
| Google Chrome | `EQHXZ8M8AV` (Google) | Google's `googlechrome.pkg` at `dl.google.com/chrome/mac/stable/` |
| Zoom | `BJ4HAAB9B3` (Zoom Video Communications) | `https://zoom.us/client/latest/ZoomInstallerIT.pkg` |
| Nextcloud | `NKUJUXUJ3B` (Nextcloud GmbH) | the `nextcloud` task installs the client |

Source for the Team IDs: Installomator's labels, which the Mac admin community
keeps against each maker's signing identity
(`github.com/Installomator/Installomator`, `fragments/labels/firefoxpkg.sh`,
`googlechromepkg.sh`, `zoom.sh`, `nextcloud.sh`), checked Oct 29.

**Proclaim is not in the list yet.** It belongs only on the media Mac (the
**This is the media Mac** box in its card), but its Team ID could not be
confirmed from a source we trust: one third-party app catalogue gives a value,
nothing from Faithlife or Installomator does. Rather than guess, it is left out.
To add it, on a Mac with Proclaim installed run
`codesign -dv --verbose=4 /Applications/Proclaim.app 2>&1 | grep TeamIdentifier`
and add it to `[macs] apps` with `media_only = true` (the example is in
`config/arise.toml.example`). An entry without a real 10-character Team ID is
ignored.

## The disk, a silent Mac, and telling a person something

- **The disk** (round 7, 40). Each check-in reports how full the Mac's disk is.
  At 90% the person at the Mac gets a notification ("This Mac's disk is nearly
  full"), and Bradly gets one alert line: a push and Discord #alerts, once a
  week per Mac. The card and Needs You show it too.
- **A silent Mac** (round 7, 82). A church Mac not heard from in three days is a
  Needs You line (`macs.silent_macs()` gives the list).
- **Notices** (round 7, 84). `notices.notify_person(user, title, body,
  kind="info")` in `server/arise_server/notices.py` is the one call other parts
  of the server make to tell a staff member something: an email to their
  personal address (`mail.send_one`), and a Mac notification on every church
  Mac where they have an account (mobile, or a linked local account). The
  notification is shown with `osascript` taking the text as arguments, so the
  text is never read as AppleScript.

## What the helper never does

- erase a Mac, or delete a local account
- read the contents of anyone's files (a removal compares names, sizes and
  dates)
- remove a profile the server has not confirmed is safely on the server
- act on a Mac nobody enrolled
- install a new macOS version
- set a screen lock or an automatic sign-out (round 7, 28 and 29)
- install an app that is not signed by its maker's expected team
- touch a personal Mac's DNS (or anything else on it)
- put a secret in its log (`/var/log/arise-helper.log`), a task or a result

## Syncing files: Nextcloud, with the old agent as the fallback

macOS removed the home sync of mobile accounts in 10.12 (Sierra). A mobile
account still caches the login, but nothing copies the files back.

Round 6, 13 and 14, are the plan, with round 7, 42 and 43: Desktop, Documents,
Downloads, Pictures and Music sync through the Nextcloud client, which the
`nextcloud` task sets up (library packages excluded: docs/SYNC.md). Until that is in, and on
any Mac where it is not running, `mac/arise-home-sync.sh` keeps doing the job
every 15 minutes.

The checked removal compares against the person's home on the server
(`/srv/arise/homes/<user>/Desktop`, `…/Documents`). So whatever syncs the
files has to land them there.

## The protocol, for whoever works on it

The helper is bash 3.2, the bash macOS ships, so the server speaks plain text.

**Server to helper.** Each answer is lines:

```
TASK <id> <kind> k=v k=v
HOLD <reason>
WATCH <n>          watch mode: n tasks would run (only notices follow)
NONE
```

The values are percent-encoded, so each `k=v` is one word.

`GET /api/macs/agent/config` gives the configuration tasks one item a line:
`LOGIN`, `LOGINTEXT`, `PRINTER`, `BOOKMARK`, `APP <name> <bundle> <team> <url>`,
`DNS`, `HELP`, `FOLDERS`, `CHURCH`.

**Helper to server.** The helper posts forms with `curl --data-urlencode`. Its
own door is `/api/macs/agent/*`, opened by the header
`X-Arise-Mac: <mac_id>:<key>`. Only an active, church-owned Mac with the right
key gets in.

**Files.** `/mac/<name>` serves only the helper's own files: `enrol.sh`, the
helper, its plist, `bind-mac.sh`, `migrate-mac-user.sh`, and `nextcloud.sh`.

## Not verified on a real Mac yet

There is no Mac where this was built. `tests/test_mac_scripts.py` reads every
script for anything bash 3.2 (the one macOS ships) cannot run, and runs the
helper's own functions with stand-ins for `dscl`, `stat -f`, `sysadminctl`,
`fdesetup` and `softwareupdate`. Point `ARISE_BASH32` at a bash 3.2.57 binary
to run them under the real version; this box runs them under its own bash.

**Checked against the documentation (Oct 29), and fixed where they were wrong:**

- An empty array under `set -u` (`"${ca[@]}"`) stops bash 3.2 dead with
  "unbound variable"; only bash 4.4 changed that (bash CHANGES, 4.4 a.). It
  would have stopped every check-in to a server without a certificate yet. Every
  such expansion is now `${a[@]+"${a[@]}"}`, and the test fails on a new one.
- `dig` reads `/etc/resolv.conf` only and never sees `/etc/resolver/<domain>`,
  so `bind-mac.sh` could not find the server on a Mac that keeps the router's
  DNS. It asks `dscacheutil -q host` (the system resolver, the one
  `dsconfigad` uses) and points `dig` at the domain's nameserver for the SRV
  records.
- macOS 15.4 replaced rsync 2.6.9 with openrsync, which takes only part of
  rsync's options. `migrate-mac-user.sh` no longer passes `-X` (rsync 3's; Apple's
  2.6.9 says `-E`): it asks `rsync --help`. The old home-sync stands down when
  its rsync has no `--backup-dir`, rather than overwrite a server copy.
- `curl -H @file` and `-H @-` need curl 7.55 (macOS 10.13 and later).
- The Full Disk Access link
  `x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles`
  opens the pane on Sonoma and Sequoia; the admin still presses + and adds the
  helper. It is opened in the signed-in person's session (`open` as root has no
  window).
- `fdesetup status` says "FileVault is Off, but will be enabled after the next
  restart." when it is deferred: only "FileVault is On" counts as on now.
- The task loop reads the server's answer on stdin, and `enrol.sh` arrives
  through `curl | sudo bash`: a command that reads stdin would have eaten the
  next tasks, or the rest of the script. Tasks get `</dev/null`, and `enrol.sh`
  runs from a `main` that bash has read in full.
- `sysadminctl` exits 0 even when it did nothing, so a removal and `ariseadmin`
  are checked against the account record afterwards, never its exit code.
- Retire removed its files after `launchctl bootout`, which ends the script
  itself; the files go first now, then the job.
- Updates: a new macOS is an upgrade, and macOS installs updates within its own
  version (Apple's platform guide), so "Install macOS updates" is on and the
  helper installs, itself, only patches for the macOS the Mac runs (minor
  versions, Security Updates, Rapid Security Responses / Background Security
  Improvements, Safari). On Apple silicon a macOS update wants a volume
  owner's password, which root alone cannot give: those wait for macOS's own
  overnight install.
- `ariseadmin`: an account with a Secure Token keeps FileVault in step only when
  its password is changed with the old one, so the helper keeps the current one
  (root, 0600) and uses `dscl . -passwd` with it.

**Still for a first run on one church Mac:**

- `createmobileaccount`'s options (`-n`, `-h <home>`, `-v`): Apple publishes no
  manual page for it; the helper uses the forms admins have used for years.
- whether "Install macOS updates" (`AutomaticallyInstallMacOSUpdates`) ever
  offers a new major macOS on its own. Apple's guide says upgrades need the
  person; nothing tests the key itself.
- whether the restart notice reaches the person (`launchctl asuser` plus
  `sudo -u`, kept alive by `AbandonProcessGroup`)
- `createmobileaccount -h <home>` on a converted account
- whether a converted account gets a Secure Token. Until that is tried, the
  helper refuses to Convert an account that holds a Secure Token when
  FileVault is on, or when it is the only token holder on the Mac: deleting
  the local record takes the token with it, and nothing can give the new
  account one without a holder's password. The card then says **Choose Link
  instead**. To convert such a Mac anyway, first give `ariseadmin` a token by
  hand (`sudo sysadminctl -secureTokenOn ariseadmin -password - -adminUser
  <holder> -adminPassword -`), then Convert, then grant the new account one
  the same way.
- restoring a password hash (`ShadowHashData`) on Undo. If it does not take,
  the message says to reset the password as `ariseadmin`.
- `dsconfigad -force -remove` on Retire
- Chrome reading `/Library/Managed Preferences` without an MDM
- the Tailscale download address
- `sysadminctl -deleteUser` asking for an admin's Secure Token on newer macOS
- `samba-tool user disable NAME$` for a computer account

**Round 7, also for that first run:**

- `restrict-store-require-admin-to-install` without an MDM. Apple documents it
  as an MDM restriction ("Require admin password to install or update apps");
  the helper writes it to `/Library/Preferences` and `/Library/Managed
  Preferences`, and whether the App Store reads it from there on current macOS
  is not proven.
- `LoginwindowText` on the login window
- the session LaunchAgent (`/Library/LaunchAgents/com.arisechurch.session.plist`)
  writing the welcome page and showing notices, and `osascript display
  notification` run through `launchctl asuser`
- `networksetup -setdnsservers` per service, and `Empty` on DNS filter off
- `tmutil destinationinfo` / `startbackup --block` at enrolment
- `pkgutil --check-signature` and `spctl -a -t install` on each app's package,
  and Chrome's and Zoom's packages installing with `installer -pkg`
- quitting and reopening the Nextcloud client in each session for a service
- `sysadminctl -guestAccount on`
