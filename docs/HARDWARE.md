# Hardware — what to send, what is enough, what to expect

The specs of the old PC are **not known yet** (Bradly, Oct 27 2026: "I'll
let you know system specs at a different date"). This page is what to
collect, and what each answer means for the install. The Synology's model is
also unknown; its page is `SYNOLOGY.md`.

## What to send

Open **Settings → System → About** on the old PC, and **Device Manager** for
the rest, or run this in PowerShell and paste the whole output:

```powershell
Get-CimInstance Win32_ComputerSystem | Select Manufacturer, Model, TotalPhysicalMemory
Get-CimInstance Win32_Processor | Select Name, NumberOfCores, NumberOfLogicalProcessors
Get-PhysicalDisk | Select FriendlyName, MediaType, Size, BusType
Get-NetAdapter | Select Name, InterfaceDescription, LinkSpeed, Status
Confirm-SecureBootUEFI
Get-Tpm | Select TpmPresent, TpmReady
```

| Item | Why it matters |
|---|---|
| **Make and model** | Tells me the BIOS key, whether it is UEFI, and what it is likely to have inside |
| **CPU** (name, cores) | 2 cores is enough. Anything from the last 12 years is fine. A Celeron/Atom is the one thing to flag |
| **RAM** (GB) | The number that decides the most — see the table |
| **Disks** (SSD or spinning, size, how many) | A spinning disk makes everything feel slow; an SSD is the single best upgrade. 64 GB is enough for the system; data lives on the NAS |
| **Network** (wired speed) | Must be wired. Gigabit is normal; 100 Mbit works but the first backup takes all night |
| **UEFI / Secure Boot / TPM** | Ubuntu handles all of them; I just need to know for the USB (MBR vs GPT) |
| **Free USB port on the back** | For the install stick |
| **Where it will sit** | On 24/7, plugged into the router or a switch by cable, somewhere the fan noise does not matter |

## Minimums

| | Server profile (Linux, everything) | Windows mode |
|---|---|---|
| CPU | 2 cores, x86-64 | 2 cores |
| RAM | **4 GB** | 4 GB |
| Disk | **64 GB SSD** (128 preferred) | 32 GB free |
| Network | **wired** Ethernet | wired |
| Recommended | 8 GB RAM once Docker apps are on | — |

## What you have → what to expect

| RAM | Directory + dashboard + automator + backups | Docker apps |
|---|---|---|
| 2 GB | Works, tight. The domain controller alone wants ~600 MB. No Docker. | No |
| **4 GB** | Comfortable. This is the normal case. | One or two light ones (file browser, uptime monitor). Not a photo library. |
| **8 GB** | Everything, with room. | All the templates, together. |
| 16 GB+ | Nothing more to say. | Anything you like. |

| Disk | What to expect |
|---|---|
| Spinning HDD only | Installs fine. Logins and the dashboard feel laggy. The first `restic` run of a big home folder takes hours. **Buy an SSD** — a 240 GB SATA SSD is about $20–30 and turns an old PC into a different machine. |
| SSD, 64–120 GB | Fine. Homes and shares go to the NAS, so the system disk stays small. |
| SSD, 240 GB+ | Fine, and homes can stay local until the NAS is set up. |
| Two disks | Ubuntu on the SSD; the other one becomes a second restic target (`arisectl backup` can keep a copy off the NAS too). |

| CPU | What to expect |
|---|---|
| Any Core i3/i5/i7, Ryzen, Xeon from 2012 on | Fine for everything. |
| Celeron / Pentium / Atom | Fine for the domain, the dashboard and the automator. Docker apps and the first big backup will be slow; the nightly run still finishes long before morning. |
| 32-bit only | Cannot run Ubuntu 24.04. Tell me; a different plan. |

## Two rules about the box itself

1. **Wired, always.** A domain controller on Wi‑Fi is a bad day: every Mac
   login, every file open, every DNS lookup on the network waits on that
   link, and when it drops at 2 AM so does the automator. If the only
   Ethernet is across the room, a $15 flat cable along the baseboard is
   the whole fix.
2. **On 24/7.** The automator runs at 2:05 AM, backups at 3:00, the mirror
   at 4:00. If the PC is off they run when it next boots (`Persistent=true`
   on every timer), but a domain controller that is off means nobody can
   log in. Turn off sleep in the BIOS (it is on by default on most desktops)
   and leave the power button alone.

## Things that are not a problem

- No monitor after the install. Everything is reachable over SSH and the
  dashboard.
- Old Windows licence. Path A wipes it; nothing on the server needs it.
- A noisy fan. Blow the dust out before it goes in the closet.
- A PC that is "too slow for Windows 11". Ubuntu Server with no desktop
  needs a fraction of that; the 4 GB row above is a 2013 machine.
