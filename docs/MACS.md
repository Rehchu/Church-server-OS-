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

## Enrolling a Mac (round 6, 37)

1. Open the **Macs** app and press **Enrol a Mac**. Type the name on the Mac's
   label (`OFFICE-MAC-02`) and press **Make the line**.
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

1. **DNS.** It points the Mac at the server for the church domain only,
   through `/etc/resolver/ad.arisecenla.com`. No router is touched.
2. **The certificate.** It trusts the church certificate in the System
   keychain. macOS asks for approval once; a daemon cannot do this by itself.
3. **The domain.** It joins the domain with `mac/bind-mac.sh`, unchanged,
   which checks DNS, the SRV records and the clock first.
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
   - an account for every server user

7. **Full Disk Access, by hand, once.** macOS hides everyone's Desktop and
   Documents even from root, and no script can grant the exception. Enrolment
   opens System Settings > Privacy & Security > Full Disk Access; add
   `/usr/local/arise/helper/arise-mac-helper` and `/bin/bash` there. Until
   then the Mac's card says **no Full Disk Access**, and no profile is ever
   removed from that Mac: the helper reports a folder it could not read, and
   the server refuses any listing that came back unread, has items but no
   files, or holds a file name with a tab or a line break.

At the end it lists the local accounts already on the Mac. Nothing happens to
them until an admin chooses (below).

## Accounts, on their own (the directory)

**Every server user gets an account.** Every enabled directory user gets a
mobile (AD) account made on every church Mac with:

```
/System/Library/CoreServices/ManagedClient.app/Contents/Resources/createmobileaccount -n <user> -v
```

So their face is on the login window before they ever sign in there. A new
user reaches every church Mac within about five minutes (one check-in).

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
2. The helper sends the server a list of every file in their Desktop and
   Documents (`[macs] sync_folders`). The list has the name, size and date of
   each file, never its contents.
3. The server checks each one against its own copy, in places the **server**
   chooses: their home, and where offboarding moved it. It never looks where
   the Mac says to. A file counts only when the server has it at the same
   size, and the copy on the Mac is not newer.
4. Only when every file counts does anything change. First the rest of their
   Mac folder (Downloads, Pictures, Music: what does not sync) is kept as a
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

## Accounts already on a Mac: Convert, Link, or Leave alone

Each local account the helper finds waits in the Mac's card as **waiting for
your choice**. Nothing is automatic. The admin presses **Choose…**:

- **Convert.** The account becomes the server user.
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
  that account signs in as the server user, so its Desktop and Documents sync
  to that person's server home.
- **Leave alone.** Nothing happens to it, ever.

The Macs app suggests a server user from the account's full name, for example
"Kristina Robinson" becomes `kristina.robinson`. It is only a suggestion. If
the chosen server user does not exist yet, it is made first with a temporary
password. The admin sees that password once, and the person chooses their own
at the first sign-in (round 5, 5).

Convert and Link also queue the `nextcloud` task for that person.

**Retire** is refused until every local account on the Mac has a choice and
every AD account's files are on the server.

`mac/migrate-mac-user.sh` and `enroll-mac.sh --map` stay as they were. Use
them for a Mac that cannot run the helper, or to copy an old account's files
to the server once before converting it.

## The rest of what the helper does

| Task | What happens on the Mac |
|---|---|
| `login_window` | A list of faces, plus Other… (`[macs] login_window = "faces"`, or `"name"`) |
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
server answers every check-in with `HOLD` and hands out nothing.

## What the helper never does

- erase a Mac, or delete a local account
- read the contents of anyone's files (a removal compares names, sizes and
  dates)
- remove a profile the server has not confirmed is safely on the server
- act on a Mac nobody enrolled
- install a new macOS version
- put a secret in its log (`/var/log/arise-helper.log`), a task or a result

## Syncing files: Nextcloud, with the old agent as the fallback

macOS removed the home sync of mobile accounts in 10.12 (Sierra). A mobile
account still caches the login, but nothing copies the files back.

Round 6, 13 and 14, are the plan: Desktop and Documents sync through the
Nextcloud client, which the `nextcloud` task sets up. Until that is in, and on
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
NONE
```

The values are percent-encoded, so each `k=v` is one word.

**Helper to server.** The helper posts forms with `curl --data-urlencode`. Its
own door is `/api/macs/agent/*`, opened by the header
`X-Arise-Mac: <mac_id>:<key>`. Only an active, church-owned Mac with the right
key gets in.

**Files.** `/mac/<name>` serves only the helper's own files: `enrol.sh`, the
helper, its plist, `bind-mac.sh`, `migrate-mac-user.sh`, and `nextcloud.sh`.

## Not verified on a real Mac yet

There is no Mac where this was built. These steps follow Apple's documented
tools but were checked only with `bash -n`, and need a first run on one church
Mac before the rest:

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
