# Making the install media

The install takes two pieces: Ubuntu Server 24.04 and ariseOS. Ubuntu asks
who you are (your name, a user name, a password, the server name:
`arise-server`). Then it shows **Ubuntu's disk screen** (set to the largest disk: check it, and tick **Encrypt the LVM group with LUKS**, docs/SECURITY.md), **erases that disk**, installs itself and
ariseOS without more questions, and restarts. On that first boot the ariseOS
wizard comes up on the monitor. It asks whether the box is at the church or
at home, the domain password, the Synology and the rest, finishes the
install and restarts into the Arise desktop (INSTALL.md, Path C).

The media carries the code (the repo is private, so the install never runs
`git clone`) and no password.

**Back up the old PC first.** Whatever is on the disk you confirm is gone.

## 1. Make the files

On any Linux box or Mac with the repo (the server itself works, and so does
a VM). You need `xorriso` and `zip` (`sudo apt install xorriso zip`, or
`brew install xorriso` on a Mac).

```bash
bash scripts/make-install-media.sh            # the add-on disc and the USB files (a few MB)
bash scripts/make-install-media.sh --full     # also the one ariseOS ISO (about 3 GB, needs 8 GB free)
```

Out, in `dist/`:

| File | What | Use it for |
|---|---|---|
| `ariseos-<version>-amd64.iso` | the official Ubuntu 24.04 server ISO with ariseOS inside (`--full`) | **the easy way**: one file, one stick |
| `ariseos-addon.iso` | a small disc labelled `CIDATA` with the config and the code | VirtualBox (a second optical drive), or a second stick |
| `ariseos-addon.zip` | the same files for a Rufus stick | Windows and Rufus with the plain Ubuntu ISO |
| `SHA256SUMS` | their checksums | check a copy before writing it |

The media holds the last commit, not uncommitted changes (the script says so
when there are some).

`--full` downloads `ubuntu-24.04.x-live-server-amd64.iso` from
releases.ubuntu.com and checks it against Ubuntu's `SHA256SUMS` before using
it (or use one you already have: `--ubuntu-iso PATH`). Its boot records are
Ubuntu's own (`xorriso -boot_image any replay`), so it boots wherever the
Ubuntu ISO boots, BIOS or UEFI, Secure Boot on or off. Its boot menu:

1. **Install ariseOS (ERASES the disk you confirm)**: the hands-off install.
2. **Install by hand (the plain Ubuntu installer)**: no autoinstall (INSTALL.md, Path A).

The menu waits for a choice; it never starts the erasing entry by itself.

## 2. Write a stick (8 GB or larger; it gets wiped)

### The one ariseOS ISO (easiest)

- **Windows**: Rufus (https://rufus.ie). **Device** = the stick (check the
  size), **Boot selection** = `ariseos-<version>-amd64.iso`, START, and
  choose **Write in DD Image mode** when asked.
- **Mac**:

  ```bash
  diskutil list                          # find the stick, e.g. /dev/disk4
  diskutil unmountDisk /dev/disk4        # unmount, do not eject
  sudo dd if=dist/ariseos-0.8.0-amd64.iso of=/dev/rdisk4 bs=4m status=progress
  diskutil eject /dev/disk4              # "unreadable disk" before this is normal: Ignore
  ```

### The plain Ubuntu ISO plus the add-on (when there is no `--full` ISO)

Download `ubuntu-24.04.x-live-server-amd64.iso` from
https://releases.ubuntu.com/24.04/ and check it against the `SHA256SUMS`
file on that page (`Get-FileHash .\ubuntu-24.04.3-live-server-amd64.iso -Algorithm SHA256`
in PowerShell, `shasum -a 256` on a Mac).

- **Windows, one stick**: write the Ubuntu ISO with Rufus in **ISO Image
  mode** (GPT / UEFI unless the old PC is BIOS-only). Then unzip
  `ariseos-addon.zip` onto the stick's root, so `autoinstall.yaml` and the
  `arise` folder sit next to `casper` and `boot`. Eject.
- **Mac, two sticks**: `dd` the Ubuntu ISO to the first stick as above (a
  `dd` stick is read-only), and `dd` `dist/ariseos-addon.iso` to a second
  one. Plug in both. The installer finds the second by its `CIDATA` label.

With the plain Ubuntu ISO, the installer asks once, "Continue with
autoinstall?" Type `yes`.

## 3. Boot the old PC from it

1. Plug the stick into a rear USB port (front ports on old PCs are often
   USB 1.1, and the boot takes forever).
2. Power on and press the boot-menu key: **F12** on most Dells and Lenovos,
   **F8** on ASUS, **F11** on MSI, **Esc** or **F9** on HP. If the BIOS
   comes up instead, put USB first in *Boot order*.
3. If it refuses to boot, turn **Secure Boot** off in the BIOS and make sure
   **UEFI** (not Legacy) is on. Ubuntu boots with Secure Boot on, but old
   firmware sometimes blocks it anyway.
4. Pick **Install ariseOS**, answer the identity screen (server name
   `arise-server`), and leave it. It restarts by itself; take the stick out
   then. The first-boot wizard is on the monitor next.

To run the wizard again later: `sudo arisectl setup`.

## The manual way (no autoinstall)

Write the plain Ubuntu ISO with nothing added, answer the installer by hand
(INSTALL.md, Path A), then copy the repo onto the box and run
`sudo bash installer/install.sh` with the flags INSTALL.md lists. Every flag
still works without the wizard.
