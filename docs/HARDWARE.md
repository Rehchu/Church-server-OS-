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

## Oct 27 2026: the box is a Dell OptiPlex, and it gets wiped

Bradly confirmed the old PC will be wiped (install path A). It is believed to be a
Dell OptiPlex; model and specs to follow. The service tag on its sticker, put into
dell.com/support, answers every line above at once. `docs/PRE-WIPE.md` is the
checklist for the days before the wipe: specs, the two credential files if the
automator runs there today, the USB stick, the F12/F2 boot steps.

## Oct 30 2026 (later): the server is the HP EliteDesk 800 G1 SFF

Bradly: "The other windows pc is an hp elite desk 800 g1 SFF", then "EliteDesk" and "Free to
wipe" (docs/ANSWERS.md, H6). The OptiPlex 3010 below is now the spare.

| | What it has | What it means |
|---|---|---|
| CPU | Intel 4th generation (Haswell), usually a 4-core i5-4570 or i5-4590, sometimes an i7-4770 | about twice the OptiPlex's power. AVX2, so the Store's heavier apps (BookStack, Jellyfin, even Immich) are realistic; the core five stay the default (H4) |
| Memory | DDR3-1600, **4 slots, 32 GB** most (Q87 chipset) | 8 GB runs the core five; **16 GB** (2 × 8 GB, about $20 used) gives room for the Store. Non-ECC desktop DIMMs, 240-pin |
| Disk | one 3.5-inch bay, plus a slim optical bay; **SATA only** (no M.2) | the same 500 GB 2.5-inch SATA SSD (H5), with a 3.5-inch adapter or the bracket HP uses |
| TPM | Infineon TPM 1.2 | HP's community support says the 800 G1's chip isn't on HP's 1.2 to 2.0 upgrade list, so the disk passphrase is typed at boot (H3). `arisectl encrypt status` shows the version |
| Graphics | Intel HD 4600 (on the CPU), DisplayPort and VGA | fine for the closet monitor; a DisplayPort-to-HDMI cable if the monitor is HDMI |
| Network | Intel gigabit (I217-LM) | fine |

**Before the wipe** (it's free to wipe, H6):

1. Write down from its sticker the **product number** and serial; hp.com/support with them
   lists the exact CPU, memory and BIOS.
2. From Windows, install the **newest BIOS** from that HP page (a SoftPaq), while Windows is
   still there to run it.
3. Look in Windows: Settings → System → About (CPU and memory) and Device Manager → Security
   devices (the TPM). Send them to Claude.

**In the BIOS** (F10 at the HP logo; names shift a little between BIOS versions):

1. **Storage → Storage Options → SATA Emulation: AHCI**.
2. **Storage → Boot Order:** UEFI boot sources on, Legacy off if offered; the Ubuntu stick
   boots either way.
3. **Advanced → Power-On Options → After Power Loss: On**. After a power cut it turns
   itself back on and waits at the passphrase. Without this it stays off.
4. **Security → Device Security → Embedded Security Device: Device available**; the TPM is on, even
   though clevis can't use a 1.2 chip.
5. Leave Secure Boot as it is; Ubuntu boots with it on or off.
6. **F9** at the logo is the one-time boot menu for the USB stick (F12 on the Dell).

**Shopping list** (H5, for the EliteDesk):

- one 500 GB 2.5-inch SATA SSD (Crucial MX500, Samsung 870 EVO or WD Blue SA510);
- memory **only if** About shows less than 16 GB: 2 × 8 GB DDR3-1600 desktop DIMMs (PC3-12800,
  non-ECC);
- for the DS216: two NAS drives, one now and one later (docs/SYNOLOGY.md).

The OptiPlex 3010 can hold a second restic copy, or wait on the shelf as the spare server.
The installer runs on it unchanged.

## Oct 30 2026: the OptiPlex 3010 (now the spare), and the Synology is a DS216

Bradly: "The optiplex is a 3010 with windows 7 and an i3 processor, the synology is a ds216."
His choices on the same day are rows H1 to H5 in docs/ANSWERS.md.

**The OptiPlex 3010** (2012):

| | What it has | What it means |
|---|---|---|
| CPU | Intel Core i3, 3rd generation (likely i3-3220: 2 cores, 4 threads, 3.3 GHz) | plenty for the domain, the shares, the dashboard and the core five apps. No AVX2: Ollama, Immich's face search and Frigate would crawl. They stay in the Store, off |
| Memory | DDR3, 2 slots; Dell lists **8 GB** as the most | buy 2 × 4 GB DDR3-1600 (about $15 used). Many 3010s run 16 GB (2 × 8 GB), but Dell doesn't promise it: try it only if a pair is cheap |
| Disk | probably a spinning hard drive | buy a **500 GB SATA SSD** (about $30). There is **no M.2 slot**: a plain 2.5-inch SATA SSD, in the drive bay or a 3.5-inch adapter |
| TPM | none, or a 1.2 chip | the disk passphrase is typed at boot (H3). `arisectl encrypt status` says which |
| Graphics | Intel HD (on the CPU) | fine for the closet monitor's desktop |
| Network | gigabit Ethernet | fine |

**Before the wipe, in the BIOS** (F2 at the Dell logo):

1. Update the BIOS first, to the newest one on dell.com/support for the service tag (from Windows 7, before the wipe).
2. **System Configuration → SATA Operation: AHCI**.
3. **Boot Sequence:** UEFI if it is offered, with Legacy off; the Ubuntu stick boots either way.
4. **Power Management → AC Recovery: Power On** (or Last State). After a power cut the box turns itself back on and waits at the passphrase. Without this it stays off.
5. Leave Secure Boot as it is; Ubuntu boots with it on or off.

**Shopping list** (Bradly: "Yes, both"):

- one 500 GB 2.5-inch SATA SSD (any known brand: Crucial MX500, Samsung 870 EVO, WD Blue SA510);
- 2 × 4 GB DDR3-1600 desktop memory (non-ECC, 240-pin "PC3-12800" DIMMs);
- for the DS216: two NAS drives, one now and one later (docs/SYNOLOGY.md).

The SSD holds Ubuntu, the apps and `/srv/arise`. If the old hard drive is still good, it can stay in as a second disk: `arisectl backup` keeps a second restic copy on it.

## Round 7 (Oct 29): what is known now

- **Internet at Pineville:** Optimum Business, the highest plan (127).
- **The Synology:** on the Netgear Nighthawk, router A (128), the same network
  as the server, so it mounts directly.
- **Alexandria:** one church Mac (134).
- **The old PC:** "just there existing, unused" (126); nothing on it has to
  keep running.
- **Disk health:** SMART's own verdict and 80 °C for the CPU (137); a disk is
  replaced when its health check warns, not on a calendar (138).
  `sudo arisectl upkeep health` reads every disk; a warning is a red line in
  Needs You and one post to Discord `#alerts`. `smartmontools` is installed
  by the installer's care step.
- **Spare parts:** none kept (142).
