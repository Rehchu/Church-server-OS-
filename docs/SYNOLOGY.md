# The Synology — storage and backups alongside the server

The server authenticates people and runs the dashboard, automator and apps.
The current owner decision keeps homes, shares and apps on the server's disk;
the Synology holds media, recordings and backups. An optional NAS-home layout
needs explicit mounts and backup-path checks before use. One old disk should
never hold the only copy of important files.

**Confirmed model: Synology DS216**, black, no suffix (Oct 30, H2). It has
**two bays**, a small ARM CPU and 512 MB RAM. Use it for storage and backups;
run ariseOS and its apps on the HP. This model uses **ext4**, not Btrfs, and
has **no Snapshot Replication**. Restic supplies the versioned backup history.
The old four-drive plan does not fit this NAS.

Before changing anything, record DSM version, installed drive models/sizes,
health, pool/volume type and existing data from DSM. Menu names depend on
DSM version. Existing data must be copied and a restore verified before any
pool recreation; nothing below authorizes reformatting an existing volume.

## 1. Two drives, eventually mirrored

The owner plans one drive now and another next month. For a new empty pool,
start with **SHR and ext4**, then add a compatible second drive to obtain
one-drive redundancy. If both drives are available initially, two-drive SHR
or RAID 1 provides a mirror. Check the DS216 support/drive compatibility and
DSM's actual expansion options before buying or confirming a storage change.

| Stage | Example drives | Approximate usable capacity | Protection |
|---|---|---|---|
| First drive | 1 × 4 TB | 4 TB nominal, about 3.6 TiB before overhead | No drive redundancy. Keep independent copies of every important file. |
| Second drive, mirror healthy | 2 × 4 TB | 4 TB nominal, about 3.6 TiB before overhead | One drive may fail; deletion, ransomware or loss of the NAS still needs backups. |

There is no third or fourth bay. Larger drives require a supported replacement
and expansion procedure; adding a second drive to a mirror does not double
usable space. A mirror is not a separate document-backup disk.

Choose compatible **CMR NAS drives**, checking the exact part number rather
than the brand alone. Match or exceed the existing drive size as required by
DSM. Verify backups before adding/replacing a drive, inspect the proposed
operation in Storage Manager and wait for the pool to return to Healthy.
Rebuild time depends on drive health, size and load; do not promise a fixed
number of hours. During the first-drive stage, a drive failure loses the
NAS copy, including any recordings stored only there. Configure and verify
an independent off-site copy before treating that data as protected.

## 2. Join the NAS to the domain

For the optional domain join, the NAS must resolve the AD domain and have
a working time source. Leave its existing network address in place; the owner
forbids router/DHCP changes. Verify a reachable, stable DC endpoint first.

1. DSM → Control Panel → Network → General → **DNS server: the server's IP**
   (uncheck "get automatically" if the router hands out something else).
   Verify ordinary name resolution still works through the server's forwarders.
   Do not invent a static address or change the router's DHCP configuration.
2. Control Panel → **Domain/LDAP** → Domain → **Join**:
   - Domain: `ad.arisecenla.com`
   - DNS server: the server's IP (it asks again)
   - Account: `administrator` (or Bradly's Domain Admin) and password
3. DSM checks the domain, lists `ARISE\Domain Users` etc. Click **Join**.
4. Control Panel → User & Group → **Domain Users** tab now lists everyone in
   AD. Permissions on shared folders are granted to domain users and groups
   from here.

If the join fails, check domain DNS/SRV records, actual network reachability,
credentials and clock agreement. For a clock error, inspect Control Panel →
Regional Options → Time and verify its time source is reachable.

## 3. Shared folders

The `arise` share is mounted directly at `/mnt/synology`. Existing configuration
uses a nested `arise/` folder inside that share for some data:

| Server path | Path inside the NAS's `arise` share |
|---|---|
| `/mnt/synology/arise-backups/restic` | `arise-backups/restic` |
| `/mnt/synology/arise/media` | `arise/media` |
| `/mnt/synology/arise/recordings` | `arise/recordings` |
| `/mnt/synology/arise/leavers` | `arise/leavers` |

Do not flatten existing directories without updating configuration and checking
backups. A folder under this mount is not the NAS's separate `homes` share.

Optional DSM home service and data-share permissions:

| Folder | Purpose | Permissions |
|---|---|---|
| **`homes`** (DSM's User Home service) | one home folder per domain user, created the first time they connect | each user: their own; `Domain Admins`: read/write all |
| **`arise`** | `arise/media/`, `arise/recordings/`, `arise/leavers/`, `arise-backups/` as mapped above | Media access only where needed; leavers/backups restricted to authorized administrators and the server |

Turn on **Control Panel → User & Group → Advanced → Enable user home service**
and tick "Enable home service for domain users" if choosing DSM homes.
Normal users connect to their own `home` share; `homes` is the administrative
collection of home directories.

Homes currently remain on the server. If the owner later elects to store them
on the NAS, mount the intended storage explicitly and then set its real path,
for example a dedicated folder inside the `arise` share:

```toml
[directory]
homes_path = "/mnt/synology/arise/homes"
```

`arisectl user add` then makes homes there instead of on the PC's disk. This is
not DSM's separate user-home share. Verify domain ownership/ACL support before
using CIFS-backed homes; the ordinary server mount maps ownership to root.
`arisectl backup jobs` must show the same path (`source: homes` follows config).
Do not move existing homes simply to follow this example.

## 4. SMB for the Macs

Control Panel → File Services → SMB:

- **Enable SMB service** on; **Maximum SMB protocol: SMB3**, minimum SMB2.
- Advanced: **Enable Bonjour service discovery** — fine to leave on; Macs see
  the NAS in the Finder sidebar. (Bonjour on the NAS is harmless; the `.local`
  problem is about the *domain name*, not this.)
- Advanced: **Enable Opportunistic Locking** on, **SMB durable handles** on;
  "Enable Local Master Browser" off (the DC is the master).
- Advanced → "Enable macOS-friendly options" / `vfs_fruit` if the DSM version
  shows it: on. It makes Finder metadata and Time Machine behave.

For optional DSM homes, Macs connect as `smb://<nas-name>/home`, authenticated
as the intended domain user. For media, use `smb://<nas-name>/arise` and its
allowed subfolders. Test permissions and Kerberos; linked local Mac accounts
may need to enter their directory credentials. Server homes remain at
`smb://arise-server.ad.arisecenla.com/<user>`.

## 5. Mounting it on the server

The server mounts the `arise` share at `/mnt/synology` for the restic repo and
the media backup paths. `arisectl nas mount` mounts the configured share; it
does not write an fstab entry. `arise-nas-mount.service` handles startup mounting.

**SMB/CIFS (default):**

```
# /etc/arise/secrets/synology.cred   (mode 0600)
username=arise-server
password=<the service account's password>
domain=ARISE

# /etc/fstab
//synology.ad.arisecenla.com/arise  /mnt/synology  cifs  credentials=/etc/arise/secrets/synology.cred,uid=0,gid=0,file_mode=0660,dir_mode=0770,vers=3.0,iocharset=utf8,_netdev,nofail  0  0
```

Create or verify a dedicated NAS service account and its write access to the
backup paths. The example name alone does not create an account. Avoid using
Bradly's interactive login so his password changes do not break backups.

**NFS** (faster for restic, no credentials file): Control Panel → File
Services → NFS → enable; on the `arise` shared folder → Edit → NFS
Permissions → add the server's IP, read/write, "map root to admin" off,
squash "no mapping". Then:

```
synology.ad.arisecenla.com:/volume1/arise  /mnt/synology  nfs  defaults,_netdev,nofail  0  0
```

Pick one. `[nas] protocol` in `arise.toml` records which.

`arisectl nas status` shows: mounted or not, free space, and if `dsm_url` is
set in `arise.toml`, the NAS's own health (volume status, drive temperatures,
last Hyper Backup result) through the DSM API with the read-only account in
`/etc/arise/secrets/dsm.json`.

## 6. The three copies (3-2-1)

| Copy | Where | Protects against |
|---|---|---|
| **1. The data itself** | server homes/shares/apps; NAS media/recordings | primary working data; SHR redundancy only where configured |
| **2. restic snapshots** | `/mnt/synology/arise-backups/restic`, jobs in `docs/BACKUPS.md` | versioned recovery from accidental changes |
| **3. Off-site** | restic copy to **Arise-Home** over Tailscale (the current decision) | loss of the building or main hardware, once copying and recovery are tested |

For NAS-resident files, copies 1 and 2 share a failure domain. The source server
can modify both online backup targets, so this is not an immutable ransomware
defense. Consider a separately protected or offline copy with the owner.

**Optional additional protection, not configured by ariseOS:** if the owner
selects Hyper Backup (Package Center → install), create a task, source =
`homes`, `arise`, destination = the USB drive (`usbshare1`) or the cloud
account, schedule after verifying the restic run has finished, keep
versions with Smart Recycle, **client-side encryption on**, write the key down
on paper. Test a restore once in the first week.

**The DS216 cannot provide Btrfs Snapshot Replication.** Restic snapshots
are versioned backup records, not NAS filesystem snapshots. Recovery points
are only as recent as the last successful job; verify the actual schedule,
retention and a restore. The server's Timeshift OS snapshots are separate
and do not protect NAS files.

## 7. Things to check once a month

- Storage Manager: volume **Healthy**, no drive "Warning"; SMART quick test scheduled weekly.
- Arise-Home: last offsite copy succeeded and a restore works.
- If separately configured, Hyper Backup: last run **Succeeded**, with the date.
- `arisectl backup status` on the server: last night green.
- If an offline USB copy was selected, the drive actually left the building.
