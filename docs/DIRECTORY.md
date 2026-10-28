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
VPN): Directory → Users → **Add**. Username (short, lower case, letters and
digits: `jsmith`), full name, a first password, groups. The row shows green
when the home folder exists. Members can then change their own password under
flame menu → Change Password.

**2. The desktop on the closet monitor**: it is the same dashboard, full
screen, so it is the same Directory app. Spotlight (⌘Space, or Ctrl+Space on
the Windows keyboard) → type `directory` → Enter → Users → Add.

**3. SSH, from any Mac or PC**:

```bash
ssh bradly@arise-server
sudo arisectl user add jsmith --display "Jane Smith" --groups Staff,Media
#   prompts for the first password; add --password P to give it on the line
sudo arisectl user passwd jsmith          # change it later
sudo arisectl group addmember Leadership jsmith
sudo arisectl user list
```

A Mac with people already on it does not need any of this: `mac/enroll-mac.sh`
creates every local account's twin in the directory for you
(docs/MAC-MIGRATION.md, "The automatic way").

## The names, and why not `.local`

| | |
|---|---|
| Realm (Kerberos / DNS) | `AD.ARISECENLA.CHURCH` |
| NetBIOS (short) name | `ARISE` |
| Domain controller | `arise-server.ad.arisecenla.church` |

The realm is a **subdomain of the domain the church already owns**
(`arisecenla.church`). That is Microsoft's and Samba's recommended practice: it
never collides with a public name, and the public website at
`arisecenla.church` keeps resolving normally because the DC only answers for
`ad.arisecenla.church`.

Do **not** use `arise.local`. macOS reserves the `.local` suffix for Bonjour
(mDNS). A Mac asked to find a `.local` domain controller tries multicast first,
waits, and the bind either times out or works one day and not the next. This is
the single most common reason Mac–AD binding fails, and renaming a realm after
the fact means rebuilding the domain.

## DNS on the church network — read this before anything else

AD does not work unless every device asks the **domain controller** for DNS.
Devices find the DC by looking up SRV records (`_ldap._tcp.ad.arisecenla.church`,
`_kerberos._tcp...`) that only the DC's DNS holds.

On the church router (the one handing out DHCP):

1. Set the **DNS server** that DHCP gives out to the server's static IP (for
   example `192.168.1.10`). Only that one. Do not list `8.8.8.8` as a second
   DNS: some devices round-robin between the two and then bind flakily.
2. The server **forwards** everything that is not `ad.arisecenla.church` to
   `1.1.1.1` (`dns_forwarder` in `arise.toml`), so the internet keeps working.
3. Give the server a **static IP** (or a DHCP reservation) so that address
   never changes.

Check from any Mac on the network:

```bash
dig +short arise-server.ad.arisecenla.church
dig +short _ldap._tcp.ad.arisecenla.church SRV
```

Both must print an answer. Empty output means the Mac is not using the DC for
DNS; nothing below will work until that is fixed.

If the server is ever off, devices lose DNS. That is the price of being the
DC. The `install.sh` sets the DC to forward, and a second DNS entry in DHCP
pointing at the router is acceptable **only** if the router itself forwards to
the server for `ad.arisecenla.church` (most consumer routers cannot). Otherwise
keep one DNS and keep the server on.

## Organisational units and groups — the proposal

Keep it small. A church of this size does not need a tree of OUs.

```
DC=ad,DC=arisecenla,DC=church
├── OU=People
│   ├── OU=Staff
│   └── OU=Volunteers
├── OU=Computers
│   ├── OU=Macs
│   └── OU=PCs
└── OU=Groups
```

Groups (security groups, created by `install.sh`):

| Group | Who | What it unlocks |
|---|---|---|
| `Staff` | paid staff and pastors | the `staff` share, their own home share |
| `Leadership` | the senior pastors and whoever they name | the `leadership` share |
| `Media` | Bradly and the media team | `media` share (graphics, loops, thumbnails), the StreamYard/Proclaim Macs |
| `Volunteers` | everyone else with a login | their home share only |
| `Kids-Check-in` | people who may run the check-in iPad/PC | the check-in machine login |
| `Domain Admins` | **Bradly only** | everything; also the account that binds Macs |

The pastors in `CLAUDE.md` get accounts when Bradly makes them. The
examples below use a made-up person on purpose.

## Password policy

Samba's defaults after `samba-tool domain provision`:

| Setting | Default | |
|---|---|---|
| Minimum length | 7 | fine |
| Complexity | on | upper + lower + digit or symbol |
| Maximum age | 42 days | **too short for a church** — people forget, Bradly gets the call |
| Lockout | off | |

The installer sets these once:

```bash
samba-tool domain passwordsettings set --max-pwd-age=0        # never expires
samba-tool domain passwordsettings set --min-pwd-length=10
samba-tool domain passwordsettings set --complexity=on
```

If you later turn lockout on (`--account-lockout-threshold=10`) and someone
locks themselves out, unlock them with:

```bash
arisectl user enable <name>
# or directly
samba-tool user unlock <name>
```

See the current policy any time with `samba-tool domain passwordsettings show`.

## Adding people

**From the CLI**, on the server (or over SSH):

```bash
sudo arisectl user add jsmith --display "Jane Smith" --groups Staff,Media
sudo arisectl user passwd jsmith       # prompts; the person can also change it in the dashboard
sudo arisectl group addmember Leadership jsmith
sudo arisectl user list
```

Under the hood that is `samba-tool user create`, `samba-tool group addmembers`
and a `mkdir` + `chown` of `/srv/arise/homes/jsmith` (or the NAS home when
`homes_path` points there).

**From the dashboard**: Directory → Users → **Add**. Same fields, same result,
and the row shows green once the home folder exists.

**Removing** someone is Bradly's click, twice: the dashboard asks for the
username typed back before `samba-tool user delete` runs, and it never deletes
the home folder. Disable instead of delete when someone leaves; their files
stay readable to Domain Admins.

## Joining a Windows PC

Windows 10/11 **Pro** or better (Home edition cannot join a domain):

1. Make sure the PC's DNS is the server (it will be, from DHCP).
2. Settings → System → About → **Domain or workgroup** → Change → Domain:
   `ad.arisecenla.church`.
3. Credentials: `ARISE\administrator` (or Bradly's Domain Admin account).
4. Reboot. Log in as `ARISE\jsmith`.

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
