# Making the install USB

Two ways. Both end with a USB stick that boots the old PC into the Ubuntu
Server 24.04 installer. If `autoinstall.yaml` is on the stick the install
runs itself (Path C in INSTALL.md); if not, you answer the installer's
questions by hand (Path A).

**You need:** an 8 GB or larger USB stick (it gets wiped), and the ISO:

```
https://releases.ubuntu.com/24.04/
→ ubuntu-24.04.x-live-server-amd64.iso   (about 3 GB)
```

Check the download before writing it. The `SHA256SUMS` file on the same page
has the right value:

```powershell
# Windows PowerShell
Get-FileHash .\ubuntu-24.04.3-live-server-amd64.iso -Algorithm SHA256
```
```bash
# Mac
shasum -a 256 ~/Downloads/ubuntu-24.04.3-live-server-amd64.iso
```

---

## On Windows — Rufus

1. Download Rufus from https://rufus.ie (the portable .exe is fine).
2. Plug in the stick. In Rufus: **Device** = the stick. Double-check the
   size; Rufus will erase it.
3. **Boot selection** → SELECT → the Ubuntu ISO.
4. Leave **Partition scheme** on *GPT*, **Target system** *UEFI (non CSM)*
   unless the old PC is BIOS-only (Rufus usually guesses right; if the PC
   will not boot it, come back and pick *MBR / BIOS or UEFI*).
5. START. When asked, choose **Write in ISO Image mode**. Wait for READY.
6. **For the hands-off install only:** open the stick in File Explorer and
   copy `autoinstall.yaml` from this folder to its root, next to `casper`
   and `boot`. Edit it first and put your password hash in
   (`openssl passwd -6` on any Mac/Linux terminal; Windows has no built-in
   way, use the Mac at church or Git Bash's `openssl`).
7. Eject.

## On a Mac — dd

```bash
# 1. find the stick. It is the one whose size matches, e.g. /dev/disk4.
diskutil list

# 2. unmount it (NOT eject)
diskutil unmountDisk /dev/disk4

# 3. write the ISO. rdisk is faster than disk. This takes a few minutes and
#    prints nothing until it finishes. Ctrl-T shows progress.
sudo dd if=~/Downloads/ubuntu-24.04.3-live-server-amd64.iso of=/dev/rdisk4 bs=4m status=progress

# 4. macOS will say the disk is unreadable — that is normal for a Linux ISO.
#    Click Ignore, then:
diskutil eject /dev/disk4
```

**For the hands-off install** the stick written by `dd` is read-only, so you
cannot drop `autoinstall.yaml` on it afterwards. Do it from Rufus on Windows,
or use the second-stick method: write `autoinstall.yaml` (and an empty file
named `meta-data`) to a *second*, FAT32 stick with the volume label
`CIDATA`, and plug both in. Ubuntu's installer looks there too.

---

## Booting the old PC from it

1. Plug the stick into a rear USB port (front ports on old PCs are often
   USB 1.1 and the boot takes forever).
2. Power on and hammer the boot-menu key: **F12** on most Dells and Lenovos,
   **F8** on ASUS, **F11** on MSI, **Esc** or **F9** on HP. If you get the
   BIOS instead, look for *Boot order* and put USB first.
3. If it refuses to boot: in the BIOS turn **Secure Boot** off and make sure
   **UEFI** (not Legacy) is on. Ubuntu boots with Secure Boot on, but old
   firmware sometimes blocks it anyway.
4. "Try or Install Ubuntu Server" → with `autoinstall.yaml` present it asks
   one confirmation ("continue with autoinstall?") and runs; without it,
   follow INSTALL.md Path A.

The install wipes the chosen disk. Anything still on the old Windows PC that
you want is gone after this. Back it up first.
