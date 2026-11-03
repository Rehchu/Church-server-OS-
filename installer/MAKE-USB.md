# Making the ariseOS install media

The finished ISO provides an on-screen Ubuntu disk/encryption and identity
setup, followed by the ariseOS wizard and desktop. The target user does not
need to type shell commands. An internet connection is needed for package
installation; this is not an offline image with every app pre-downloaded.

## Build on a development machine

Required: Git, Python 3 with PyYAML, xorriso, zip, curl, and `sha256sum`
(coreutils). On Ubuntu: install `xorriso zip python3-yaml curl coreutils`.
On macOS, install equivalent tools; stock macOS lacks `sha256sum`.

**A private disc** (Oct 31, H9): `bash scripts/make-install-media.sh --secrets <folder>`
makes `ariseos-addon-private.iso`, which also carries the keys in that folder (today only
`resend-api-key`). The install puts them in `/etc/arise/secrets/` by itself, so nothing is
pasted on install day. Keep that disc on your PC and USB stick only: never GitHub, never a shared
folder. The plain disc has no keys and is the one to share.

**Back up the old PC first.** Whatever is on the disk you confirm is gone.

From a clean, tested Git checkout:

```bash
bash scripts/make-install-media.sh --full
```

For a reviewed change that has not been committed:

```bash
bash scripts/make-install-media.sh --full --working-tree
```

`--working-tree` includes the current contents of tracked files, including
reviewed staged additions and deletions. Untracked files are excluded.
It rejects sensitive filenames, external/special symlinks, and recognizable
credential material instead of silently adding local files. Review and
stage intended new source files before using it. The default build refuses
a dirty checkout so it cannot silently ship an old commit with new metadata.
No build changes Git history.

To reuse an Ubuntu ISO, verify it against Ubuntu's authoritative published
checksum list (and signature) first, then pass that expected SHA-256:

```bash
bash scripts/make-install-media.sh --full --working-tree \
  --ubuntu-iso /path/to/ubuntu-24.04-live-server-amd64.iso \
  --ubuntu-sha256 EXPECTED_64_CHARACTER_SHA256
```

The builder compares the supplied file with that checksum. Without a local
ISO it downloads from `https://releases.ubuntu.com/24.04/` and verifies the
image against that site's SHA256SUMS. TLS and checksum verification stay on.
The full image needs space for both source and remastered ISOs (at least
8 GB, plus sufficient margin for the actual image size).

Outputs in `dist/`:

- `ariseos-<version>-amd64.iso`: the complete bootable installer (`--full`).
- `ariseos-addon.iso`: CIDATA payload for use alongside a plain Ubuntu ISO.
- `ariseos-addon.zip`: payload for a Rufus ISO-mode Ubuntu USB.
- `SHA256SUMS`: checksums for the finished artifacts.

The source payload has its own checksum and version/source-snapshot marker.
Missing or damaged payloads stop installation instead of producing a false
success. The media preserves Ubuntu's boot records; BIOS/UEFI/Secure Boot
compatibility still requires a real boot test on the target configuration.

`--test-identity` is only for a disposable VM: it supplies a known test
account but still asks for disk selection. Never use a TEST artifact on
production hardware.

## Use the finished ISO

In VirtualBox, attach it as the boot optical disk and choose **Skip
Unattended Installation**. On physical hardware, write it to a verified
empty USB with Rufus **DD Image mode** (the USB will be erased). Boot it
from the computer's one-time boot menu. Keep unrelated disks disconnected.

Select **Install ariseOS (choose disk and encryption on screen)**. On Storage,
select the intended disk, LVM and encryption, and inspect the final disk
confirmation. On Identity create the local owner account. Remove/eject the
media on the first reboot and follow the ariseOS setup screens. Core five
apps are selected by default; directory-only remains an isolated-test choice.
The HP EliteDesk 800 G1 requires the disk passphrase after each restart;
keep its keyboard available. The final
reboot opens the desktop. See `INSTALL.md` for the complete screen sequence.

The ISO build, checksum verification, actual BIOS/UEFI boot, firstboot setup,
application readiness and recovery rehearsal are distinct checks. Do not
report an unexecuted VM boot as passed merely because media generation worked.
