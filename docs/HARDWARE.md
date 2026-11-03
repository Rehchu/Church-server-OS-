# Hardware — the HP server, Dell spare and Synology

Bradly's Oct 30 answers H1–H6 in `docs/ANSWERS.md` set the hardware plan:

| Role | Confirmed model | Plan |
|---|---|---|
| **Primary: arise-server** | **HP EliteDesk 800 G1 SFF** | Free to wipe after preservation checks; Ubuntu Server 24.04 LTS. |
| Spare | Dell OptiPlex 3010, Windows 7, Core i3 | Keep as the spare; it is no longer the primary installation target. |
| NAS | Synology **DS216**, black, no suffix | Two bays, ext4, no Btrfs or Snapshot Replication. See `SYNOLOGY.md`. |

The exact installed CPU, RAM, disks and firmware still need checking. The HP
family commonly has a fourth-generation Intel CPU and DDR3 memory, but the
model name does not prove which processor, DIMMs or drives this unit contains.
Neither this document nor a successful VM boot certifies the physical hardware.

## Inventory before buying or wiping

Use Windows **System Information** (`msinfo32`), Device Manager and Disk
Management, or the BIOS inventory. Record the HP product/serial number and
check its matching service manual. Factory specifications do not establish
what is installed today. In PowerShell, where these commands are available:

```powershell
Get-CimInstance Win32_ComputerSystem | Select Manufacturer, Model, TotalPhysicalMemory
Get-CimInstance Win32_Processor | Select Name, NumberOfCores, NumberOfLogicalProcessors
Get-CimInstance Win32_PhysicalMemory | Select DeviceLocator, Capacity, Speed, PartNumber
Get-CimInstance Win32_DiskDrive | Select Model, Size, InterfaceType
Get-NetAdapter | Select Name, InterfaceDescription, LinkSpeed, Status
Confirm-SecureBootUEFI
Get-Tpm | Select TpmPresent, TpmReady
```

Older Windows versions may lack individual cmdlets. Read the corresponding
firmware/Device Manager screen instead. `Get-Tpm` presence alone does not prove
TPM 2.0; inspect the specification version in `tpm.msc` or firmware.

| Check | Why it matters |
|---|---|
| CPU model and core count | Verify Ubuntu and selected app-image compatibility; measure indexing, backup and media workloads. |
| Installed RAM and free DIMM slots | Choose compatible memory from the service manual, accounting for existing modules. |
| Disk model, capacity and health | Identify the disk to erase. Budget for Ubuntu, images, databases, logs, local files and update space. |
| Wired Ethernet and negotiated speed | Test the real link, DHCP and sustained transfers; a link light is insufficient. |
| UEFI, Secure Boot, TPM version | Record current settings and rehearse the actual USB boot and encrypted-disk unlock. |
| Cooling and power | Clean safely, check fan operation and temperatures, and identify the UPS. |

## Approved upgrades

H5/H6 selects a **500 GB 2.5-inch SATA SSD** for the HP system disk. Check the
SFF mounting bracket, power and SATA cables before ordering. If installed RAM
is below 16 GB, bring it to **16 GB with compatible DDR3** after checking the
actual slot layout and service manual; H6 suggests 2 × 8 GB DDR3-1600. Do not
buy another 16 GB if the unit already has sufficient compatible memory.
Prices and availability vary. Keep the original disk intact until its needed
files have been preserved and the new installation has passed its checks.

## Apps and capacity

H4 installs only **Nextcloud, Vaultwarden, Uptime Kuma, Netdata and File
Browser** by default. Other apps are available in the Store; `--apps all` is
an explicit option. Installed does not mean running: autostart settings and
the Store's memory admission checks still apply.

These are rehearsal starting points, not capacity guarantees. The Store
reserves 2 GB of physical RAM for the host, but container caps do not predict
actual peak use, filesystem cache, database growth, CPU or disk contention.

| RAM | Practical starting point |
|---|---|
| 2 GB | Below the planned rehearsal minimum; leave apps off. |
| 4 GB | Limited desktop/directory-only evaluation; measure memory and swap during backups. |
| 8 GB | Initial VM allocation if the host has enough free RAM; test the selected apps together. |
| 16 GB+ | More headroom; still measure. Immich, Frigate, AI and transcoding require their own sizing. |

A 64–120 GB SSD is suitable only for a measured core evaluation. The approved
500 GB SSD leaves more room, but monitor growth and preserve free space for
image pulls, updates and restores. Data moves to NAS storage only after the
intended layout has been configured and verified. A second disk is not
a backup until a backup job writes to it and a restore has been tested.

## Firmware and the first physical rehearsal

The HP normally uses **Esc/F9** for the boot menu and **F10** for setup;
the Dell spare normally uses **F12/F2**. Follow the prompts on the actual
machine. Use UEFI installation and inspect storage settings before changing
them. Changing SATA mode can prevent an existing Windows installation from
booting; finish preservation first. Ubuntu provides signed boot components,
but Secure Boot must be tested on this unit with the produced install media.
Do not assume a firmware update or a generic compatibility list proves it.

Check HP's model-specific firmware guidance. If an update is needed, use
stable power, the correct image and the vendor procedure; record settings
beforehand. After installation test Ethernet, USB keyboard, display, disk
health, suspend policy, restart and power restoration. Confirm the installed
system boots with the USB removed, and test the recovery passphrase.

The expected HP TPM is **1.2**, which does not provide clevis TPM 2.0 unlock.
H3 therefore means entering the LUKS passphrase at every boot. H6 allows
TPM binding if this actual machine has a usable TPM 2.0; verify successful
unlock before treating it as unattended. See `SECURITY.md` for the optional
LAN SSH unlock path and its preboot network requirements.

## Operation

Keep the server wired and powered continuously; domain logins, password
changes, server files and jobs depend on it. Existing cached mobile accounts
and linked local Mac accounts can still log in when it is unavailable.
Turning on **power on after AC loss** in firmware does not unlock LUKS: on
passphrase boot, someone must unlock it before services return. Keep a working
keyboard/monitor and the owner-approved closet recovery card available.

`sudo arisectl upkeep health` checks disks; inspect warnings and actual
measurements. SMART does not predict every failure. The owner chose health
warnings rather than a fixed replacement calendar, an 80 °C CPU warning,
and no spare parts stock. Verify backups and a restore before depending on
the machine. `PRE-WIPE.md` is the installation-day checklist.
