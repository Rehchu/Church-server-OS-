# The directory — Arise Server as the church's Active Directory

The server runs **Samba as an Active Directory Domain Controller**. That is
not "like" Active Directory; it is the same protocol set Microsoft ships, so
Macs, Windows PCs and the Synology all join it the normal way and treat it as
AD. One account per person, one password, every device.

## What you get

| Piece | What it does for the church |
|---|---|
| **Kerberos** | Single sign-on. Log in once at the Mac; shares and the NAS open without a second password. |
| **LDAP** | The user and group database. The dashboard, `arisectl`, the NAS and the Macs all read from it. |
| **DNS** | The DC runs its own DNS for the realm. Every joined device finds the DC through it. This is the part that most often goes wrong, see below. |
| **Group Policy (GPO)** | Rules pushed to Windows PCs (wallpaper, drive maps, password rules). Macs ignore GPO; they get settings from the bind options instead. |
| **Home shares** | Each user has `\\arise-server\homes\<user>` (or the same folder on the Synology once it is joined). |

## Active Directory, and what makes this one better

First the honest part. This **is** Active Directory: Samba 4 implements the
same Kerberos, LDAP, DNS and SMB that a Windows Server domain controller
does. A Mac binds to it with Apple's own Directory Utility. A Windows 10 or 11
Pro PC joins it from the System dialog. The Synology joins it as an AD member.
Group Policy objects can be stored and applied to Windows PCs. One account,
one password, every device, and when someone leaves one click disables them
everywhere.

What a Windows Server domain does not give a church of this size, and this
does:

| | Windows Server AD | Arise Server |
|---|---|---|
| Where people see their files when they are not at church | nowhere without extra products | the **dashboard**: any member signs in from anywhere, browses their own home and the shares they belong to, uploads, downloads, shares a file with a link, changes their password |
| Creating a person | Active Directory Users and Computers on a Windows PC | three ways: the Directory app in the dashboard, the same desktop on the closet monitor, `arisectl user add` over SSH |
| Reaching it from Alexandria or the Hub | a site-to-site VPN appliance | Tailscale (or WireGuard) built in; the server is the same name from every campus |
| Backups of the domain itself | a separate backup product | restic nightly at 03:00, plus a weekly `samba-tool domain backup offline` |
| Where the Macs' work ends up | nowhere unless you buy into folder redirection scripts | the server home share at login and a fifteen-minute sync (docs/MAC-MIGRATION.md) |
| Which computer sits at which campus | not a concept | the Campuses app |
| Cost | a Windows Server licence plus CALs per person | the old OptiPlex |

What it does **not** do, so nobody expects it later: no Microsoft Entra ID
(Azure AD) sync, no Microsoft 365 accounts, no Intune or any other MDM (device
management, pushing settings and apps to Macs). If the church ever wants MDM,
the free option to look at is a self-hosted **MicroMDM** or **NanoMDM**; both
are an idea only, nothing here depends on them. Group Policy editing still
needs the RSAT tools on one Windows PC. See the full list at the end of this
document.

## Creating people, three ways

All three end in the same `samba-tool user create` and the same home folder;
pick whichever is in front of you.

**1. The dashboard, from anywhere** (`http://arise-server:4147`, or over the
VPN): Directory → Users → **Add**. Username (`first.last`, lower case:
`jane.smith`; answer 23), full name, a first password, groups. The row shows green
when the home folder exists. Members can then change their own password under
flame menu → Change Password.

**2. The desktop on the closet monitor**: it is the same dashboard, full
screen, so it is the same Directory app. Spotlight (⌘Space, or Ctrl+Space on
the Windows keyboard) → type `directory` → Enter → Users → Add.

**3. SSH, from any Mac or PC**:

```bash
ssh bradly.dyer@arise-server
sudo arisectl user add jane.smith --display "Jane Smith" --groups Staff,Media
#   prompts for the first password; add --password P to give it on the line
sudo arisectl user passwd jane.smith      # change it later
sudo arisectl group addmember Leadership jane.smith
sudo arisectl user list
```

A church Mac with people already on it does not need any of this:
`mac/enroll-mac.sh` creates every local account's twin in the directory for
you, as `first.last`, with `--map oldname=first.last` where the Mac's name
differs (docs/MAC-MIGRATION.md, "The automatic way").

## The names, and why not `.local`

| | |
|---|---|
| Realm (Kerberos / DNS) | `AD.ARISECENLA.COM` |
| NetBIOS (short) name | `ARISE` |
| Domain controller | `arise-server.ad.arisecenla.com` |

The realm is a **subdomain of the domain the church already owns**
(`arisecenla.church`). That is Microsoft's and Samba's recommended practice: it
never collides with a public name, and the public website at
`arisecenla.church` keeps resolving normally because the DC only answers for
`ad.arisecenla.com`.

Do **not** use `arise.local`. macOS reserves the `.local` suffix for Bonjour
(mDNS). A Mac asked to find a `.local` domain controller tries multicast first,
waits, and the bind either times out or works one day and not the next. This is
the single most common reason Mac–AD binding fails, and renaming a realm after
the fact means rebuilding the domain.

## DNS on the church network — read this before anything else

AD does not work unless every device asks the **domain controller** for the
church domain's names. Devices find the DC by looking up SRV records
(`_ldap._tcp.ad.arisecenla.com`, `_kerberos._tcp...`) that only the DC's
DNS holds.

**Bradly's rule (Oct 28): no router, switch or Mesh setting changes, at
all.** So the routers keep handing out whatever DNS they hand out today, and
the church domain is wired in on each device instead:

1. The server has a **static address** set in netplan on the server itself
   (INSTALL.md § 5), chosen outside Netgear A's DHCP range. Looking at that
   range on the router page is allowed; changing anything there is not.
2. Every church Mac gets a **per-domain resolver file**,
   `/etc/resolver/ad.arisecenla.com`, holding `nameserver <server ip>`.
   `mac/bind-mac.sh --dns <server ip>` writes it (and `enroll-mac.sh --dns`
   passes it through). macOS then asks the server only for names ending in
   `ad.arisecenla.com` and keeps the router's DNS for everything else, so
   the internet keeps working even when the server is off.
3. Any device on **Tailscale** gets the same thing from the tailnet's split
   DNS rule (docs/REMOTE-ACCESS.md step 5), wherever it is. The two do not
   conflict.
4. The server still **forwards** anything it is asked that is not the church
   domain to `1.1.1.1` (`dns_forwarder` in `arise.toml`), for its own sake.

Check from any Mac on the network:

```bash
dig +short arise-server.ad.arisecenla.com
dig +short _ldap._tcp.ad.arisecenla.com SRV
```

Both must print an answer. `dig` ignores `/etc/resolver`, so on a Mac that
uses the resolver file test with `dscacheutil -q host -a name
arise-server.ad.arisecenla.com` instead. Empty output means the Mac is not
asking the DC; nothing below will work until that is fixed.

If the server is ever off, the Macs lose only the church domain's names; the
internet keeps working because the router's DNS is untouched. That is the
one advantage of this layout over the usual "router hands out the DC" setup.

## Organisational units and groups — the proposal

Keep it small. A church of this size does not need a tree of OUs.

```
DC=ad,DC=arisecenla,DC=com
├── OU=People
│   ├── OU=Staff
│   └── OU=Volunteers
├── OU=Computers
│   ├── OU=Macs
│   └── OU=PCs
└── OU=Groups
```

Groups (security groups, created by `install.sh`) and the share each one
opens (answers 25, 27 and 37):

| Group | Who | What it unlocks |
|---|---|---|
| `Domain Admins` | Apostle Bryant Sanders, Pastor Vanessa Sanders, Kristina Robinson, Bradly | everything in the dashboard; also the account that binds Macs. SSH is Bradly's only |
| `Staff` | paid staff and pastors | the `staff` share, their own home share |
| `Leadership` | the senior pastors and whoever they name | the `leadership` share |
| `Media` | Bradly and the media team; the shared `media` login on the media Mac | the `media`, `graphics` and `recordings` shares, the StreamYard and Proclaim Macs |
| `Childrens-Department` | the Children's Department login | the `childrens-department` share, and `kids` |
| `Inedge` | the Inedge login | the `inedge` share |
| `Worship` | the worship / music login | the `worship` share |
| `Volunteers` | nobody today: volunteers use a department login (answer 24) | kept for the day that changes |
| `Kids-Check-in` | nobody today: there is no check-in station yet (answer 28) | the check-in machine login, later |

Other departments get the same shape when their names come. Bradly's rule
since round 4 (104): **everyone has their own account**; a department is a
*group* with its own share folder (and, when the mail server comes, its own
address), and being in the group is what opens it. The shared department
logins in the table above are the sample data's shape from round 1 and are
not needed. Round 4 (99) also adds a **staff tier** in the dashboard: anyone
in `Staff` or `Media` sees Photos, Notes and, later, the transcripts and the
calendar's edit buttons; that tier is the next block, not yet in the code. Nine shares in all today: `staff`, `leadership`,
`media`, `kids`, `graphics`, `childrens-department`, `inedge`, `worship`,
`recordings`. `recordings` is on the Synology, holds every Sunday's video
(answer 51), and is excluded from restic because a file of several GB a
week would swallow the backup history; the Synology's RAID is its
protection until there is an off-site copy. The examples below use a
made-up person on purpose.

## Password policy

Samba's defaults after `samba-tool domain provision`:

| Setting | Default | |
|---|---|---|
| Minimum length | 7 | fine |
| Complexity | on | upper + lower + digit or symbol |
| Maximum age | 42 days | **too short for a church** — people forget, Bradly gets the call |
| Lockout | off | |

Bradly's choice (answer 26, then round 3, 27): never expires, 12 characters
minimum, **no lockout**. The settings the installer's step 5b applies:

```bash
samba-tool domain passwordsettings set --max-pwd-age=0        # never expires
samba-tool domain passwordsettings set --min-pwd-length=12
samba-tool domain passwordsettings set --complexity=on
samba-tool domain passwordsettings set --account-lockout-threshold=0   # none (round 3, 27)
```

The dashboard shows these rules in words, with a strength meter, when
someone changes their password (`GET /api/me/password/rules`). Two-step
sign-in is optional per person on top (docs/SECURITY.md).

See the current policy any time with `samba-tool domain passwordsettings show`.

## Adding people

**From the CLI**, on the server (or over SSH):

```bash
sudo arisectl user add jane.smith --display "Jane Smith" --groups Staff,Media
sudo arisectl user passwd jane.smith   # prompts; the person can also change it in the dashboard
sudo arisectl group addmember Leadership jane.smith
sudo arisectl user list
```

Under the hood that is `samba-tool user create`, `samba-tool group addmembers`
and a `mkdir` + `chown` of `/srv/arise/homes/jane.smith` (or the NAS home when
`homes_path` points there).

**From the dashboard**: Directory → Users → **Add**. Same fields, same result,
and the row shows green once the home folder exists.

**Removing** someone is Bradly's click, twice: the dashboard asks for the
username typed back before `samba-tool user delete` runs, and it never deletes
the home folder. Disable instead of delete when someone leaves; their files
stay readable to Domain Admins.

## Joining a Windows PC

Bradly (round 4, 26): "add windows pc capabilities just in case we get them
at a location". The two Windows PCs the church has become the ariseOS nodes
(docs/NODES.md), so today this is still reference. The decided shape (67)
is a join script from the dashboard that joins, maps the shares as drives
and trusts the church certificate, nothing else; not yet built. Windows 10/11
**Pro** or better (Home edition cannot join a domain):

1. Make sure the PC's DNS is the server (it will be, from DHCP).
2. Settings → System → About → **Domain or workgroup** → Change → Domain:
   `ad.arisecenla.com`.
3. Credentials: `ARISE\administrator` (or Bradly's Domain Admin account).
4. Reboot. Log in as `ARISE\jane.smith`.

Macs: see `docs/MAC-MIGRATION.md`. The Synology: `docs/SYNOLOGY.md`.

## Backing up the domain controller

The `config` job in `backups.yaml` already covers the three things that *are*
the domain:

```
/etc/samba/smb.conf
/var/lib/samba/private      # sam.ldb and the rest of the directory database
/etc/arise
```

restic snapshots them nightly at 03:00. Also take a logical export now and then
(it is small and human-readable):

```bash
samba-tool domain backup offline --targetdir=/srv/arise/backups/dc-offline
```

`install.sh` adds that to a weekly timer. Those tarballs are inside the
`shares`/`backups` paths restic already snapshots.

## Recovering

**The server died, the disk is gone.** Reinstall Ubuntu + Arise Server with
`install.sh --skip-domain`, mount the Synology, restore the `config` job
(`arisectl backup restore latest --tag config --target /`, see docs/BACKUPS.md), and it
restores `/var/lib/samba/private` and `/etc/samba` before starting
`samba-ad-dc`. Same hostname, same IP, same realm; every joined device carries
on as if nothing happened (Kerberos tickets are good for 10 hours, so fix it
the same day). Alternatively use the offline tarball:

```bash
samba-tool domain backup restore --backup-file=<tar> --newservername=arise-server --targetdir=/var/lib/samba
```

**A single user's password is lost.** `arisectl user passwd <name>`.

**The DC is fine but a Mac says "unable to contact domain".** It is DNS. Run
the two `dig` lines above on that Mac.

## What this does not do

Honest list, so nobody expects it later:

- **No Microsoft Entra ID (Azure AD) sync.** Accounts here do not become
  Microsoft 365 accounts. If the church ever needs that, Entra Connect wants a
  Windows Server; Samba is not supported as a source.
- **No Exchange, no email.** Mail stays where it is (Google).
- **Group Policy editing needs RSAT on a Windows PC.** The DC *stores* GPOs
  and PCs *apply* them, but the editor (`gpmc.msc`) is a Windows tool. Install
  RSAT on one Windows 11 Pro PC joined to the domain and edit from there.
  Macs do not read GPO at all.
- **One DC.** A second DC (another old PC) is possible with
  `samba-tool domain join ... DC` and is the proper answer to "what if the
  server is off"; not in scope until there is a second box.
- **Samba's AD is one major version behind Microsoft's** on a few features
  (no Windows Server 2025 functional level). Nothing the church uses needs
  them.
