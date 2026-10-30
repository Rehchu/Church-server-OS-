# Trying ariseOS in VirtualBox

A test box on Bradly's PC (Oct 29), long before the OptiPlex. It runs the real
installer in staging mode: the domain stays on the VM itself, nothing on the
home network is touched, and nothing on the PC changes but VirtualBox.

## 1. The media

On a Linux box or Mac with the repo (`sudo apt install xorriso zip` first),
make the files (installer/MAKE-USB.md):

```
bash scripts/make-install-media.sh            # dist/ariseos-addon.iso, a few MB
bash scripts/make-install-media.sh --full     # or the one ISO: dist/ariseos-0.8.0-amd64.iso, about 3 GB
```

Copy what you made to the PC. With only the add-on, also download
`ubuntu-24.04.x-live-server-amd64.iso` from https://releases.ubuntu.com/24.04/.
No GitHub token is needed: the code is on the disc.

## 2. The VM

VirtualBox → **New**:

| Setting | Value |
|---|---|
| Name | arise-test |
| ISO | `ariseos-0.8.0-amd64.iso`, or the plain Ubuntu 24.04 server ISO |
| Unattended install | **Skip** (tick "Skip Unattended Installation") |
| Memory | 8192 MB (the EliteDesk will have 8 to 16 GB, H6) |
| Processors | 4, like the EliteDesk's i5 |
| Disk | 80 GB, VDI, dynamically allocated |

Then **Settings** before the first start:

- **System → Motherboard:** Enable EFI.
- **Storage** (only with the plain Ubuntu ISO): on the IDE or SATA controller,
  **Add optical drive** → `ariseos-addon.iso`. Two optical drives: Ubuntu and
  the add-on.
- **Display → Screen:** Graphics Controller VMSVGA, Video Memory 128 MB, 3D off.
  The VM's window is the closet monitor.
- **Network → Adapter 1:** NAT (keeps the VM's domain off the home network),
  then **Port Forwarding**:

| Name | Host port | Guest port | What |
|---|---|---|---|
| dash | 4147 | 4147 | the dashboard: http://localhost:4147 on the PC |
| https | 8443 | 443 | the dashboard through Caddy (church certificate) |
| ssh | 2222 | 22 | `ssh -p 2222 bradly@localhost` from the PC |

## 3. The install

Start the VM.

- The ariseOS ISO: pick **Install ariseOS** in the boot menu. The plain Ubuntu
  ISO: pick "Try or Install Ubuntu Server" and type `yes` at "Continue with
  autoinstall?".
- The two screens it asks:
  - **the disk:** the VM's one disk with LVM. Tick **Encrypt the LVM group with LUKS** and
    type a test passphrase to rehearse the real box (H3), or leave it unticked for a quicker
    test. Then Done → Continue.
  - **you:** your name Bradly Dyer, **server name `arise-server`**, **user name `bradly`**
    (the box's owner account; the automator runs as it), and a password.
- With encryption ticked, every start of the VM stops at "Please unlock disk": type the
  passphrase in the VM window.
- It wipes the VM's disk, installs Ubuntu and ariseOS, and restarts. If it
  boots back into the installer, remove the discs (Devices → Optical Drives)
  and restart.

On the first boot the **ariseOS setup** wizard is on the VM window:

- Where is this box: **At home or in a test VM** (staging: the domain on the
  VM only, no network scan, CLAUDE.md rule 8).
- Your account: `bradly`.
- The **domain Administrator password**, twice. Choose one for the test box only.
- The Synology: leave it empty. Tailscale: **No**. The desktop on this monitor:
  **Yes**. Discord: later.
- Go. It takes 15 to 30 minutes, then asks for the **dashboard password**,
  shows what still needs you (`arisectl doctor`) and restarts. The VM window
  comes back as the closet monitor.

On the PC, open **http://localhost:4147** for the dashboard in a browser.
Run the wizard again any time with `sudo arisectl setup`.

**Without the media** (the old way still works): install Ubuntu by hand, copy
the repo to `/opt/arise-src`, and run
`sudo bash installer/install.sh --staging --owner bradly --kiosk --no-tailscale`,
then `sudo arisectl admin set-password`.

## 4. What to try

- The VM window: the lock screen, signing in, your desktop after a restart (round 7, 107).
- Directory: make people (a duplicate first.last becomes first.last2), titles,
  a temporary password and its forced change, disable and enable.
- Shares, Finder: upload, Trash and Put Back, Previous Versions, Share with…
- Backups: there is no Synology, so point a backup target at a folder on the VM
  and run one; then the restore drill.
- The phone checklist: http://localhost:4147/checklist.
- The Macs app: the enrol line works only once a Mac can reach the VM, so read
  it but don't paste it on a church Mac.
- `sudo arisectl automations list`, `arisectl storage`, `sudo arisectl security`.

Copy anything that fails (the screen, or the output of `sudo arisectl doctor`)
into the chat. Doctor never prints a password; anything from
`/etc/arise/secrets/` stays out of the chat.

## 5. Updating it

Make the add-on again from the newer commit, attach it to the VM, and:

```
sudo mount -o ro "$(blkid -L CIDATA)" /mnt
(cd /mnt/arise && sha256sum -c SHA256SUMS) && sudo tar -xzf /mnt/arise/ariseos-src.tar.gz -C /opt/arise-src
sudo umount /mnt
sudo bash /opt/arise-src/installer/install.sh --staging --owner bradly --kiosk --no-tailscale
```

The installer is safe to run again: a re-run changes only what changed.

## What a VM can't show

The TPM disk unlock, the real Synology, the routers and the church network,
Macs enrolling over the network (NAT keeps them out), and the OptiPlex's own
screen and power button. Those wait for the real box.
