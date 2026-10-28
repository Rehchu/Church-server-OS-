# Windows PCs on the Arise domain

Bradly kept Windows "just in case we get them at a location" (round 4,
answers 26 and 67): a join script, drive letters and the church certificate,
nothing else. No group policy is pushed.

## Before you start

- **Windows Pro.** Windows Home cannot join a domain. The script says so and
  stops; the shares still work without joining (`\\arise-server\shares` in
  File Explorer, signing in as `ARISE\first.last`).
- **The server's church address**, from the closet card or `arisectl info`.
- **A domain admin's password** (`ARISE\administrator`, or one of the four
  admins).

## Run it

Copy `join-arise.ps1` to the PC (a USB stick, or download it from the
dashboard's Help app). Open **PowerShell as Administrator** in that folder:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\join-arise.ps1 -ServerIp 192.168.1.20
```

It does six things and stops at the first that fails:

1. Checks the edition.
2. Adds one name-resolution rule (NRPT) so that only `*.ad.arisecenla.church`
   is asked of the server. The PC's own DNS, the router and the Mesh stay
   as they are. Over Tailscale the domain already resolves and no rule is added.
3. Trusts the church certificate, so `https://arise-server` shows the padlock.
4. Joins `AD.ARISECENLA.CHURCH` into `OU=PCs,OU=Computers` (the installer
   makes that OU). It asks for the domain admin.
5. Installs a sign-in script for every user that maps the shares they may
   open. A share someone cannot open is not mapped.
6. Offers the restart.

## The drive letters

| Letter | Share | Who gets it |
|---|---|---|
| H: | your home folder | everyone |
| S: | `shares` (the church folder) | everyone signed in |
| T: | `staff` | Staff |
| L: | `leadership` | Leadership |
| M: | `media` | Media |
| G: | `graphics` | Media |
| W: | `worship` | Worship, Media |
| K: | `kids` | Kids |
| J: | `childrens-department` | Children's Department |
| I: | `inedge` | Inedge |
| R: | `recordings` (on the Synology) | Media, admins |

## Undo

```powershell
Remove-Computer -UnjoinDomainCredential ARISE\administrator -Restart
Get-DnsClientNrptRule | Where-Object Namespace -contains '.ad.arisecenla.church' | Remove-DnsClientNrptRule -Force
Remove-Item C:\ProgramData\Arise -Recurse
Remove-Item "$env:ProgramData\Microsoft\Windows\Start Menu\Programs\StartUp\arise-drives.cmd"
```

## Not verified

This script was written and read carefully, not run: there was no Windows PC
or PowerShell in the build environment. Run it first on a PC that does not
matter, and tell Claude what it printed if any step fails.
