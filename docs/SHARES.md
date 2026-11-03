# Shares: the Church folder, the department folders, Pastors, Shared with me

Round 5 (docs/ANSWERS.md, rows 12 to 20, 23 and 36). The staff and volunteers
work on their Macs, not on the dashboard, so **every rule here is on the
server's disk first**: POSIX ACLs on the folders, and Samba share lines that
agree with them. A Mac connecting over SMB gets exactly the same yes or no as
the dashboard. The dashboard is the administrators' view of the same rules.

Code: `server/arise_server/sharing.py`. Settings: `[storage]` in
`/etc/arise/arise.toml` (`config/arise.toml.example` lists every key).

## Who can do what

| Folder | Path | Everyone | Staff | The department's account | Department members | Admins |
|---|---|---|---|---|---|---|
| **Church** (row 16) | `/srv/arise/shares/church` | read and write | read and write | read and write | read and write | read and write |
| **A department** (row 17): `childrens-department`, `inedge`, `media`, `worship`, `kids`, `alexandria` | `/srv/arise/shares/<name>` | nothing | read and write | read and write its own | read only | read and write |
| **Pastors** (row 18) | `/srv/arise/pastors` | nothing, not even its name | nothing | nothing | nothing | **nothing** |
| **Shared with me** (row 19) | `/srv/arise/shared/<person>` | their own | their own | their own | their own | their own |

- **The department's account** is the login named like the folder
  (`media`, `inedge`, `childrens-department` or `childrens.department`), plus
  any extra login in `department_accounts`. The booth Mac (`media-mac`) is
  there for `media`, so it keeps writing the media folder.
- **Members of a department** are the people in its group, which the
  installer makes title-cased: `Childrens-Department`, `Inedge`, `Media`,
  `Worship`, `Kids`, `Alexandria`.
- **Alexandria** (row 36) is a department from day one: an `Alexandria`
  group and an `alexandria` folder, ready for the third site.
- **Pastors** is for Apostle Bryant Sanders and Pastor Vanessa Sanders only
  (`[storage] pastors`).

### What a department volunteer notices

Before round 5 a volunteer in the Media group could write the media share.
Now **department members read; staff and the department's account write**
(row 17). A volunteer who should edit has to be in Staff, or use the
department's account. This is the one rule that takes something away; it
is what row 17 says.

## On the server: how it is enforced

`sudo arisectl share folders` writes all of it, and the installer runs it
once:

```
sudo arisectl share folders --dry-run   # print the share lines and the ACL commands, change nothing
sudo arisectl share folders             # asks, then applies
```

What that does, in order:

1. **The ACLs** on each folder (`chgrp`, `chmod 2775` or `2750`, `setfacl`
   with default entries so new files inherit them):
   - Church: group `Domain Users`, `rwx` for the group, inherited.
   - Each department: group = the department's group with `r-x`,
     `g:Staff:rwx`, `g:Domain Admins:rwx`, `u:<the account>:rwx`, others
     `---`.
   - Pastors: `root:Pastors`, `u:bryant.sanders:rwx`,
     `u:vanessa.sanders:rwx`, the group and others `---`.
   An account that does not exist yet is left out of the ACL, because
   `setfacl` refuses a whole line over one unknown name. **Run it again
   after you add the pastors' accounts or a department account.**
2. **The share lines** go into `/etc/samba/arise-folders.conf`, included
   from `smb.conf` (a dated `.bak` copy is made the first time the include is
   added). Names come from config: the NetBIOS name from `[directory]`,
   never typed into the code.
3. **`testparm -s`** checks the result. If it refuses, the old
   `arise-folders.conf` is put back and nothing is reloaded.
4. `smbcontrol all reload-config`: the Macs see the change at their next
   connect.

`config/samba/smb.conf.template` no longer defines the department shares;
they all live in `arise-folders.conf` so there is one place for them.
Department shares use `access based share enum`, so a Mac lists only the
shares that person can open.

The dashboard has the same thing: **Directory → Shares → Folders and
permissions…** shows the share lines and the ACL commands, and **Apply**
(asks for your password again) runs them.

## The Pastors folder

- It lives at `/srv/arise/pastors`, **outside** `/srv/arise/shares`, so no
  share above it reaches it.
- The `[pastors]` share has `browseable = no`: no Mac lists it. The pastors
  connect to `smb://arise-server.<your realm>/pastors` by typing it once in
  Finder → Go → Connect to Server, then keep it in the sidebar.
- The dashboard's own root process refuses it to everyone else, admins
  included: Finder, Spotlight, Recents, the Trash, Storage's file lists, Get
  Info, Previous Versions, Share Link and Share with… all act as if it does
  not exist. Storage still counts its size in the disk total.
- **Root can technically read any file on the box.** That cannot be
  prevented; it is logged instead. auditd watches the folder
  (`/etc/audit/rules.d/arise-pastors.rules`). Every read or write by anyone,
  root included, is in the audit log:

  ```
  sudo ausearch -k arise-pastors -i          # everything
  sudo ausearch -k arise-pastors -i -ui 0    # root only
  ```

  The nightly backup reads the folder as root at 03:00 (restic), so those
  lines are expected every night. Anything else as root is someone looking.
- Claude on the box never opens it (CLAUDE.md, rule 11c).
- It is backed up by its own job (`pastors` in `/etc/arise/backups.yaml`).

## Shared with me (row 19)

Right-click a file or folder in Finder → **Share with…** → a person, or a
group (`@Worship`), and **Open and copy** or **Open and edit**.

What happens on the server:

1. **An ACL on the item** for that person or group (`setfacl -m`; for a
   folder, recursively and as the default for new files), plus traverse
   (`--x`) on each folder above it up to the home or share folder, so they
   can reach it without seeing the folder's other files. A path where they
   already had their own entry (a department ACL, say) is left alone.
2. **A link** in their own folder: `/srv/arise/shared/<them>/Setlist (from
   bradly).pdf`. On their Mac that is the **shared** share
   (`smb://arise-server.<realm>/shared`); Samba follows the link, and the
   ACL decides what they can do there. In the dashboard it is the **Shared
   with me** section of the Finder sidebar.
3. **A notice**: push to their devices, and an email to their personal email
   (from their profile) through Resend.
4. **An audit entry**: `files.share`.

The record is `/var/lib/arise/shared-with.json`. **Shared by me** in the
Finder sidebar lists what you share, with **Stop sharing**. Admins see every
share there and can stop any of them. Stopping takes back exactly what the
share added (the ACL entries and the link) and is audited as
`files.share.revoke`.

Rules:
- **Members share only their own files** (their home). Staff and admins can
  share from anywhere they can open.
- Staff and admins pick from a list of people and groups; members type a
  name.
- **A group share reaches the people in the group when you share.** The ACL
  is on the group, so on the server and on a Mac a person added to the group
  later can open it, but the link in their shared folder and the notice go
  only to the members at that moment. To give a newcomer the link, share
  again.

## An admin opening someone else's home (row 20)

Allowed, and recorded: every time an administrator lists or opens a folder
in another person's home through the dashboard, the audit log gets
`files.home.open` with the owner and the path. It is recorded **at most once
per folder per 10 minutes per admin**, so browsing does not flood the log.
Your own home is never recorded.

## Homes on the server or the Synology (row 12)

`[storage] homes_on = "server"` (the default) keeps homes at
`/srv/arise/homes`. `"synology"` puts them at
`<nas mount>/arise/homes` (`/mnt/synology/arise/homes`): the dashboard, the
quota, the backups and the installer's `[homes]` share line all follow it.
A `[directory] homes_path` other than `/srv/arise/homes` is taken as set by
hand and wins over `homes_on`. This waits for Friday's disk sizes.

Moving existing homes is a copy, not a setting: stop Samba, `rsync -aAX`
the homes across, check, change `homes_on`, rerun
`sudo bash installer/install.sh` for the share line, start Samba. Nothing is
deleted from the old place; that is Bradly's click.

## The network scan (row 23)

The device list (Network, `/api/devices*`) is for administrators only. A
member or staff account gets 403 on every device route
(`tests/test_sharing.py`).

## What is not verified here

The tests (`tests/test_sharing.py`) pin the share lines, the ACL plan, the
grant and revoke plans, the Pastors rule in every listing, the quota, the
backup target and the audit throttle. They run real `setfacl` on a temp
folder where it is installed. Not verified on a real domain yet:
- a Mac opening the `shared` share and following a link into another home
  (it depends on `wide links` and the traverse ACLs above the item);
- `getent` seeing domain accounts for the ACL plan (it needs winbind's NSS,
  which the domain controller has);
- auditd lines for a real root read.
