# Trying ariseOS in VirtualBox

A test box on Bradly's PC (Oct 29), long before the OptiPlex. It runs the real
installer in staging mode: the domain stays on the VM itself, nothing on the
home network is touched, and nothing on the PC changes but VirtualBox.

## 1. The VM

VirtualBox → **New**:

| Setting | Value |
|---|---|
| Name | arise-test |
| ISO | Ubuntu Server 24.04 LTS (ubuntu.com/download/server) |
| Unattended install | **Skip** (tick "Skip Unattended Installation") |
| Memory | 8192 MB (4096 works, slowly) |
| Processors | 4 (2 works) |
| Disk | 80 GB, VDI, dynamically allocated |

Then **Settings** before the first start:

- **System → Motherboard:** Enable EFI.
- **Display → Screen:** Graphics Controller VMSVGA, Video Memory 128 MB, 3D off.
  The VM's window is the closet monitor.
- **Network → Adapter 1:** NAT (keeps the VM's domain off the home network),
  then **Port Forwarding**:

| Name | Host port | Guest port | What |
|---|---|---|---|
| dash | 4147 | 4147 | the dashboard: http://localhost:4147 on the PC |
| https | 8443 | 443 | the dashboard through Caddy (church certificate) |
| ssh | 2222 | 22 | `ssh -p 2222 bradly@localhost` from the PC |

## 2. Ubuntu

Start the VM and install Ubuntu Server:

- Language and keyboard as usual; network stays on DHCP (NAT).
- Disk: use the whole disk. LVM is fine; encryption can be skipped on a test box.
- Your name: Bradly Dyer. **Server name: `arise-server`**. **User name: `bradly`**
  (the box's owner account; the automator runs as it).
- **Install OpenSSH server: yes.** Featured snaps: none.
- Reboot, sign in.

## 3. ariseOS

The repository is private, so git asks for your GitHub user name and a token
(a fine-grained token with read-only Contents on Church-server-OS- is enough;
type it at the prompt, never into a chat).

```
sudo apt update && sudo apt install -y git
sudo git clone -b claude/arise-server-os https://github.com/Rehchu/Church-server-OS-.git /opt/arise-src
cd /opt/arise-src
sudo bash installer/install.sh --staging --owner bradly --kiosk --no-tailscale
```

- It asks for the **domain Administrator password** (twice). Choose one for the
  test box only.
- It takes 15 to 30 minutes. The last screen lists what still needs you.
- `--staging`: the domain on loopback, no network scan (CLAUDE.md rule 8).
- `--kiosk`: after the reboot the VM window shows the Arise desktop, like the
  closet monitor.

Then:

```
sudo arisectl admin set-password      # the dashboard's admin password
sudo arisectl doctor                  # what is wrong, in order
sudo reboot                           # the VM window comes back as the closet monitor
```

On the PC, open **http://localhost:4147** for the dashboard in a browser.

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

```
cd /opt/arise-src && sudo git pull
sudo bash installer/install.sh --staging --owner bradly --kiosk --no-tailscale
```

The installer is safe to run again: a re-run changes only what changed.

## What a VM can't show

The TPM disk unlock, the real Synology, the routers and the church network,
Macs enrolling over the network (NAT keeps them out), and the OptiPlex's own
screen and power button. Those wait for the real box.
