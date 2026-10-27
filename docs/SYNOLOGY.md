# The Synology — four bays, joined to the domain, holding the real data

The old PC is the brain: it authenticates people, runs the dashboard, the
automator and the apps. The **Synology is where the bytes live**: four drives
in RAID, the home folders, the media archive, the restic repository. One old
disk in a PC should never be the only copy of anything.

**Model unknown.** Bradly has not said which Synology it is yet. Read these off
it before going further, from DSM → Control Panel → Info Center:

| Read off the NAS | Why it matters |
|---|---|
| Model (e.g. DS923+, DS423, DS224+) | "+" models support Btrfs snapshots and Docker; "j"/value models may not |
| DSM version (7.x) | the menus below are DSM 7 |
| Drive count and sizes | decides SHR vs SHR-2 |
| Current RAID / volume type | if it already has data on it, nothing below reformats it |

## 1. RAID — the decision for four bays

| Layout | Survives | Usable space (4 × 4 TB) | When |
|---|---|---|---|
| **SHR (1-drive redundancy)** | one drive failing | ~12 TB | the default; good enough with the off-site copy in place |
| SHR-2 (2-drive redundancy) | two drives failing | ~8 TB | if the church would rather lose a third of the space than ever rebuild from backup |
| RAID 10 | one drive per mirror pair | ~8 TB | faster, same loss as SHR; no benefit here |

Recommendation: **SHR with 1-drive redundancy**, **Btrfs** file system (needed
for snapshots), and a replacement drive on the shelf. A rebuild on a 4 TB
drive takes most of a day; during it a second failure loses the volume. That
is what the restic copy and the off-site copy are for (section 6).

If the NAS already holds data on a volume, leave it; add the shared folders to
the existing volume.

## 2. Join the NAS to the domain

The NAS must use the server for DNS, like everything else.

1. DSM → Control Panel → Network → General → **DNS server: the server's IP**
   (uncheck "get automatically" if the router hands out something else).
   Set a **static IP** on the NAS too.
2. Control Panel → **Domain/LDAP** → Domain → **Join**:
   - Domain: `ad.arisecenla.church`
   - DNS server: the server's IP (it asks again)
   - Account: `administrator` (or Bradly's Domain Admin) and password
3. DSM checks the domain, lists `ARISE\Domain Users` etc. Click **Join**.
4. Control Panel → User & Group → **Domain Users** tab now lists everyone in
   AD. Permissions on shared folders are granted to domain users and groups
   from here.

If the join fails on "unable to find domain", it is DNS on the NAS (step 1).
If it fails on the clock, Control Panel → Regional Options → Time → sync with
`arise-server.ad.arisecenla.church`.

## 3. Shared folders

Two shared folders on the volume:

| Folder | Purpose | Permissions |
|---|---|---|
| **`homes`** (DSM's User Home service) | one home folder per domain user, created the first time they connect | each user: their own; `Domain Admins`: read/write all |
| **`arise`** | the church's data: `media/` (graphics, loops, thumbnails, the podcast art), `shares/` (staff, leadership, kids), `arise-backups/` (the restic repository, the DC's offline backups) | `Media` group: `media/`; `Staff`/`Leadership` as named; `arise-backups/`: the server's service account only |

Turn on **Control Panel → User & Group → Advanced → Enable user home service**
and tick "Enable home service for domain users". That is what makes
`\\synology\homes\<user>` exist.

When the NAS is joined and `homes` exists, set in `/etc/arise/arise.toml`:

```toml
[directory]
homes_path = "/mnt/synology/homes"
```

and `arisectl user add` makes homes there instead of on the PC's disk.

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

Macs connect as `smb://synology/homes/<user>`; Kerberos from the domain login
means no password prompt.

## 5. Mounting it on the server

The server mounts the `arise` share at `/mnt/synology` for the restic repo and
the media backup paths. `install.sh` writes the fstab line; `arisectl nas
mount` does the same by hand.

**SMB/CIFS (default):**

```
# /etc/arise/secrets/synology.cred   (mode 0600)
username=arise-server
password=<the service account's password>
domain=ARISE

# /etc/fstab
//synology.ad.arisecenla.church/arise  /mnt/synology  cifs  credentials=/etc/arise/secrets/synology.cred,uid=arise,gid=arise,vers=3.0,iocharset=utf8,_netdev,nofail  0  0
```

`arise-server` is a domain service account created by `install.sh` for this
(not Bradly's login, so a password change does not break backups).

**NFS** (faster for restic, no credentials file): Control Panel → File
Services → NFS → enable; on the `arise` shared folder → Edit → NFS
Permissions → add the server's IP, read/write, "map root to admin" off,
squash "no mapping". Then:

```
synology.ad.arisecenla.church:/volume1/arise  /mnt/synology  nfs  defaults,_netdev,nofail  0  0
```

Pick one. `[nas] protocol` in `arise.toml` records which.

`arisectl nas status` shows: mounted or not, free space, and if `dsm_url` is
set in `arise.toml`, the NAS's own health (volume status, drive temperatures,
last Hyper Backup result) through the DSM API with the read-only account in
`/etc/arise/secrets/dsm.json`.

## 6. The three copies (3-2-1)

| Copy | Where | Protects against |
|---|---|---|
| **1. The data itself** | the NAS volume, SHR | one drive dying |
| **2. restic snapshots** | `/mnt/synology/arise-backups/restic` — the server's folders (automator, config, GitHub mirror, homes if they are on the PC) and the NAS's own `media/` and `shares/` | deleted or overwritten files, ransomware on a Mac, "it was fine yesterday" |
| **3. Off-site** | **Hyper Backup** on the NAS → a USB drive that goes home with Bradly, **or** a cloud bucket (Backblaze B2, Synology C2, Google Drive) | the building: fire, theft, flood, a power surge that takes the NAS and the PC together |

Copy 2 living on the same NAS as copy 1 is deliberate: it is a *version
history*, not a disaster copy. Copy 3 is the disaster copy.

**Hyper Backup** (Package Center → install): create a task, source =
`homes`, `arise`, destination = the USB drive (`usbshare1`) or the cloud
account, schedule nightly 04:30 (after restic has finished at ~03:30), keep
versions with Smart Recycle, **client-side encryption on**, write the key down
on paper. Test a restore once in the first week.

**Snapshot Replication** (if the model is Btrfs-capable; Package Center →
Snapshot Replication): hourly snapshots of `homes` and `arise`, keep 24
hourly / 7 daily / 4 weekly. This is the fastest "I deleted it ten minutes ago"
fix and costs almost no space. If the package is not offered for this model,
restic's snapshots do the same job a day coarser.

## 7. Things to check once a month

- Storage Manager: volume **Healthy**, no drive "Warning"; SMART quick test scheduled weekly.
- Hyper Backup: last run **Succeeded**, with the date.
- `arisectl backup status` on the server: last night green.
- The USB off-site drive actually left the building.
