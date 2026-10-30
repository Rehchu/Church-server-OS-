# Before the wipe: the checklist for the HP EliteDesk 800 G1 SFF

Decision (Bradly, Oct 30 2026, docs/ANSWERS.md H6): the HP EliteDesk 800 G1 SFF is wiped and
becomes the server ("Free to wipe"). The Dell OptiPlex 3010 is the spare; the same steps work on
it with Dell's keys (F2 setup, F12 boot menu) and a Dell service tag instead of HP's numbers.

Everything below happens **while Windows is still on it**. Once the install starts, the disk is
gone.

## 1. Read the specs off it (two minutes)

- **The sticker** (back or bottom): the **product number** (like `F1M45UT`) and the **serial**.
  Put them into https://support.hp.com: the page lists the exact CPU, memory and disk as
  shipped, and the BIOS downloads.
- **Or in Windows:** Win+R, `msinfo32`, Enter. Read *System Model*, *Processor*, *Installed
  Physical Memory (RAM)*, *BIOS Mode* (UEFI or Legacy). Then Win+R, `tpm.msc` for the TPM's
  *Specification Version* (expect 1.2), and Win+R, `diskmgmt.msc` for the disks.

Send Claude: CPU, memory, disk size and type, BIOS mode, TPM version.

## 2. Update the BIOS while Windows can run the updater

On the HP support page for the product number: **BIOS → the newest "HP Business Desktop System
BIOS"** SoftPaq. Run it from Windows, let it restart. Nothing else on that page is needed.

## 3. Make sure nothing on it is the only copy

It's free to wipe (H6), so this is a last look, not a backup job:

- Anything in `C:\Users\...` (Desktop, Documents, Downloads, Pictures) that someone would miss:
  copy it to the Synology or a USB drive.
- Browser passwords saved on it: sign in to the browser's sync, or export them.
- It is not the automator's PC (the media PC on E: is), so no `token.json` to rescue here.

## 4. The parts (H5)

- The **500 GB 2.5-inch SATA SSD** goes in place of the old disk (the SFF has one 3.5-inch bay:
  use a 2.5-to-3.5 adapter, or HP's bracket). Keep the old disk: it holds Windows until the day.
- Memory **only if** step 1 shows less than 16 GB: 2 × 8 GB DDR3-1600 (PC3-12800, non-ECC,
  240-pin desktop DIMMs), in the slots HP's label inside the lid marks for two DIMMs.

## 5. The BIOS settings (F10 at the HP logo; the menu names shift a little between BIOS versions)

1. **Storage → Storage Options → SATA Emulation: AHCI** (not RAID or IDE).
2. **Storage → Boot Order:** UEFI boot sources on; Legacy off if offered.
3. **Advanced → Power-On Options → After Power Loss: On**. After a power cut the box starts by
   itself and waits at the disk passphrase (H3). Off means it stays off.
4. **Security → Device Security → Embedded Security Device: Device available.** It's a 1.2 chip, which the disk can't use,
   but `arisectl encrypt status` reports it.
5. Secure Boot can stay as it is; Ubuntu is signed. F10 again: save and exit.

## 6. On install day, in this order

1. Plug in **Ethernet**. A domain controller on Wi-Fi is a bad day, and the installer wants the
   network up.
2. Boot from the stick: power on and tap **F9** (HP's boot menu; F12 on the Dell), pick the USB
   under *UEFI Boot Sources*.
3. The install disc's two screens (installer/MAKE-USB.md):
   - **the disk:** check it's the new SSD, keep LVM, tick **Encrypt the LVM group with LUKS**,
     type the passphrase twice and write it on the safe card;
   - **you:** your name, server name `arise-server`, user `bradly`, a password.
4. It restarts and stops at **"Please unlock disk"**: type the passphrase. Then the ariseOS
   setup wizard runs on the screen (church or home, the domain password, the rest).
5. Then the "First boot" list in `INSTALL.md`: the dashboard password, the restic password (and
   on paper), mount the Synology, `sudo arisectl doctor`.
6. From your PC, add your SSH key so the passphrase can be typed from a church computer
   (docs/SECURITY.md), then `sudo arisectl encrypt ssh`.

## 7. What this PC's generation means

| It has | Expect |
|---|---|
| 8 GB | the domain, the dashboard, backups and the core five apps: comfortable |
| 16 GB | room for the Store's heavier apps (BookStack, Jellyfin, Immich) as well |
| a spinning disk | works, but slow and the part most likely to die: the SSD is the fix (H5) |
| a 4-core i5 (4th gen) | more than enough; it idles most of the day |
| Intel I217-LM network | supported by Ubuntu 24.04 out of the box |
