# Testing ariseOS in VirtualBox

Use the complete ariseOS ISO from `scripts/make-install-media.sh --full`
(see `installer/MAKE-USB.md`). The target VM installs through on-screen
choices and opens the ariseOS desktop; no manual Ubuntu install, Git clone
or shell command is needed.

## Create a disposable VM

- Ubuntu 64-bit, 2–4 vCPUs, 8 GB RAM when the Windows host has adequate
  headroom. More assigned resources are not automatically faster.
- One empty dynamically allocated VDI of at least 80 GB, on a healthy disk
  with sufficient free host space. No physical disk passthrough.
- EFI enabled; VMSVGA, 128 MB video memory, 3D acceleration off.
- NAT; skip VirtualBox's unattended installer. Attach the complete ariseOS
  ISO as the optical disk.
- Optional HTTPS forward: **Host IP 127.0.0.1**, Host Port 8443,
  Guest Port 443. Optional SSH forward: Host IP 127.0.0.1, Host Port 2222,
  Guest Port 22. SSH needs an enrolled public key after ariseOS setup.

Start the VM, select **Install ariseOS**, select the empty virtual disk
on the Storage screen and review the final erase confirmation. Choose LVM
and LUKS encryption for a production-equivalent test. On Identity enter
`arise-server` and your owner username. After Ubuntu finishes, eject the
ISO so the next boot uses the disk.

On the ariseOS setup screen select **At home or in a test VM**. Leave the
NAS blank, choose Tailscale off for an isolated rehearsal, and choose
**Desktop and directory only** for the smallest first rehearsal. The normal
default is **Core five** (Nextcloud, Vaultwarden, Uptime Kuma, Netdata and
File Browser); test that selection next with adequate guest memory. Set the domain and dashboard
passwords in their prompts. Successful setup restarts into the desktop;
errors return to a Retry/Shutdown screen. Unlock LUKS at boot when prompted.

Staging binds Samba to guest loopback. The web backend is local-only;
Caddy provides HTTPS. The kiosk requires no host setup. An optional Windows
browser test through 8443 also needs the certificate hostname mapped locally
and the verified church CA trusted on Windows. Do not bypass certificate
verification or send login passwords over a raw HTTP forward.

## First functional checks

At the desktop, sign in, create a disposable directory test user, upload a
test file, move it to Trash and restore it. Restart from the desktop and
verify sign-in and file persistence. Configure a disposable local backup
target and restore a test file. Then install one small app from the Store,
verify its function and restart behavior, and add other apps individually.
Never enroll a church Mac or connect production data for the first rehearsal.

A VM does not prove the real Synology, Mac permissions, router topology,
HP EliteDesk 800 G1 display, SSD behavior, firmware fallback, TPM unlocking,
UPS behavior or hardware performance. The physical HP remains unvalidated.
A fresh-VM backup recovery test is separate from installation.

## If a soft lockup appears

A guest watchdog warning does not identify a cause. Record the guest kernel
and full incident stack, VirtualBox version and VBox.log, actual VM settings,
host/guest free space, host disk type, and Windows CPU/memory/disk load.
Check whether the guest recovered and whether Docker is still active.
Do not rerun the installer while the original one is running.

Stacks deploy one at a time; Docker may parallelize image layers within a
stack. Pull progress should now be visible. When diagnosing a lockup, select
directory-only for the initial rehearsal and add apps incrementally. Use the current supported
VirtualBox maintenance release and Ubuntu kernel before attributing a
kernel hang to one resource setting.

The turtle icon alone does not prove whether Windows Hyper-V/VBS is active;
check the actual backend in VBox.log. Do not disable Windows security or
the Linux watchdog as a speculative fix. KVM paravirtualization is suitable
for a Linux guest. Host I/O cache and fixed versus dynamic VDI are controlled
performance experiments, not guaranteed cures: change one setting only
with the VM powered off and a recoverable checkpoint.
