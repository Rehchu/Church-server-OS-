# Installing ariseOS

The normal installation is entirely on screen: boot the ariseOS ISO, choose
the target disk and encryption, create your account, and complete the ariseOS
setup screens. No Terminal or shell command is needed on the target computer.
The ISO contains Ubuntu Server 24.04 and the ariseOS source snapshot. It
still needs an internet connection for Ubuntu and application packages.

## Before starting

Back up anything on the target disk. Disconnect disks that must not be
modified, especially backup disks. For a VirtualBox test, use a new empty
80 GB or larger virtual disk, NAT networking, 2–4 vCPUs and 8 GB RAM when the
Windows host has enough free resources. Attach the finished ariseOS ISO and
skip VirtualBox's own unattended installer. See `docs/VIRTUALBOX.md`.

## The on-screen installation

1. Boot the ISO and choose **Install ariseOS (choose disk and encryption on
   screen)**. The menu waits for your selection.
2. On Ubuntu's **Storage** screen, select the intended disk by its identity
   and size. Select **LVM** and **Encrypt the LVM group with LUKS**. Keep
   the disk passphrase somewhere separate from the computer. Review the
   final disk/partition list before confirming destructive changes.
   The media requires the disk screen and erase confirmation. Ubuntu may
   initially highlight the largest eligible disk: inspect it carefully. An isolated
   disposable VM can be tested without encryption, but that does not meet
   the production encryption requirement.
3. On **Identity**, enter your name, server name `arise-server`, username
   `bradly`, and a strong local password. Ubuntu installs, verifies the ariseOS
   payload and enables the firstboot setup screen. Remove/eject the ISO when
   it restarts so it boots from the installed disk.
4. Unlock the encrypted disk if prompted. On the ariseOS setup screen,
   choose **At home or in a test VM** for the rehearsal. The domain stays
   local to the machine. Choose **At the church** only on the intended
   production network.
5. Confirm the owner, choose the domain Administrator password, optionally
   enter the NAS address and enable Tailscale, and choose an app selection.
   **Core five** is the default: Nextcloud, Vaultwarden, Uptime Kuma,
   Netdata and File Browser. **Desktop and directory only** remains available
   for an isolated rehearsal; the full template collection is an explicit
   choice. More apps can be installed later from the Store.
6. Review the summary and choose **Go**. Package and app progress is visible.
   If setup fails, the screen explains that it is incomplete and offers
   **Retry setup** or **Shut down safely**. Completed work is retained.
7. Choose the dashboard password when prompted. Setup checks the local web
   service, domain and kiosk prerequisites before marking completion. It
   restarts into the ariseOS desktop. If it cannot pass these checks, it
   returns to setup instead of claiming success.

The firstboot wizard always installs the kiosk for this ISO workflow.
The HP EliteDesk 800 G1's TPM 1.2 cannot unlock LUKS, so its disk needs the
passphrase after every reboot. If another machine actually has TPM 2.0,
the installer offers binding with a one-time passphrase prompt; automatic
unlock applies only after binding succeeds. `--no-tpm` skips new binding.
Early SSH unlock is optional and requires approved keys and explicit boot
network configuration; it does not work through Tailscale. VM display behavior, disk
unlock and the complete firstboot handoff must be verified on the actual
VirtualBox host; a successful media build is not that verification.

## Network and credentials

No router, switch or Google Mesh setting is changed. DHCP remains enabled
by default: turning a live DHCP lease into a static address does not reserve
it. Before production AD use, verify the stable endpoint/address strategy
with the actual network. The advanced `--pin-ip` flag is only appropriate
for an address independently verified outside the DHCP allocation pool.

Staging keeps Samba on guest loopback. The dashboard backend binds locally
and Caddy provides HTTPS on the guest interface. For a host browser, use
a host-loopback 8443-to-443 NAT forward with the configured hostname and
the verified church CA. The kiosk works locally without host configuration.

The installer disables password SSH. Add your public key before depending
on SSH access; the on-screen installation requires none. Keep secret files,
passwords, `.env` contents and private keys out of chat and installation
logs. The restic password must be preserved, not regenerated on reinstallation.

## After the desktop appears

Use the dashboard to configure the NAS, backup destination, app accounts,
Tailscale, staff accounts and the other site-specific settings. Validate one
Mac and one app before enrolling everyone. Confirm a backup and restore
before placing the server into service. The YouTube job remains on its
existing designated runner until you deliberately migrate it.

A directory-only test does not claim Nextcloud or the other apps are running.
Choosing all templates downloads them sequentially and starts only those
that fit the app budget; available RAM is not a guarantee of performance.

On the first ISO boot, unused extents are assigned to the root filesystem
only for a single, ordinary ext4 root LV. Existing multi-volume or thin-LVM
layouts are left alone. The installer adds the CPU's microcode, enables
weekly SSD trimming, and permits discard only on an identified encrypted
root SSD. Discard reveals block-allocation patterns to someone examining
the encrypted disk; it does not reveal plaintext. Crypttab is backed up,
and all initramfs images are rebuilt before continuing.

On a mounted EFI system partition, a complete signed Ubuntu fallback is
staged if no fallback already exists. Existing bootloader files are
preserved. Verify HP firmware boot behavior and recheck the fallback after
shim/GRUB updates; these changes have not been validated on the physical HP.

## Advanced manual installation and recovery

The shell installer remains available for administrators. Obtain the
`claude/arise-server-os` branch (or the tested release branch containing
these changes); the repository's old `main` contains only a README.

```bash
sudo git clone --branch claude/arise-server-os https://github.com/Rehchu/Church-server-OS-.git /opt/arise-src
sudo bash /opt/arise-src/installer/install.sh --staging --owner bradly --kiosk --no-tailscale --no-apps
```

Omitting a domain password flag prompts securely. Never put a password in
`--admin-pass` on the command line. `--apps "nextcloud vaultwarden
uptime-kuma netdata filebrowser"` chooses the default core set; `--no-apps` selects none;
`--skip-docker` omits Docker; `--no-start` prepares services without starting
them. `--ssh-key-file PATH` enrolls an existing public key. Manual installs
leave root LV sizing unchanged unless `--grow-root` is explicitly supplied.

Recovery is a different workflow, documented in `docs/REINSTALL.md`.
Never run a normal installer first on a disaster-recovery target: that can
create a new directory rather than restore the original domain.

Build with `scripts/make-install-media.sh`; instructions: `installer/MAKE-USB.md`. Canonical decisions:
`docs/ANSWERS.md`. Installed code is `/opt/arise`, source `/opt/arise-src`,
configuration `/etc/arise`, data `/srv/arise`, logs `/var/log/arise`.
