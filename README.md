# ariseOS / Arise Server

**v0.9.0 "Leviticus"** — the new look: rounded, glass, the newest macOS feel.

Arise Church's Ubuntu Server 24.04 operating layer: Samba Active Directory,
church file shares, an administration desktop, Docker applications, Mac
management and backups. Fixed realm: `AD.ARISECENLA.COM`; NetBIOS: `ARISE`.

## Install from an ISO

Use the **full ariseOS ISO**, not the plain Ubuntu ISO by itself. Boot the
computer or an empty VirtualBox VM from it and choose **Install ariseOS**.
Select the intended disk on the storage screen, choose encrypted LVM, review
and confirm the disk changes, then enter your identity. After reboot, the
ariseOS setup screen configures the server and opens its desktop automatically.
**No shell commands are needed during this installation.** Internet access is
required to obtain Ubuntu packages and any applications you select.

The setup screen defaults to the five requested apps: Nextcloud, Vaultwarden,
Uptime Kuma, Netdata and File Browser. It also offers a directory-only test
installation or all app templates. The kiosk is enabled automatically. Failed setup returns to an
on-screen retry rather than marking a partial installation complete.

The small `ariseos-addon.iso` is an alternative: attach it **alongside** an
Ubuntu Server 24.04 ISO. It is not independently bootable. Both media routes
run the same ariseOS setup. See [INSTALL.md](INSTALL.md) and
[VirtualBox instructions](docs/VIRTUALBOX.md).

## Current validation status

This development branch contains fixes from an independent source review.
Unit tests and isolated media construction checks do not establish a successful
bare-metal installation. A full ISO boot, complete first-boot installation,
real Samba login, kiosk launch and a fresh-machine restore must pass before
production deployment. See [review and acceptance record](docs/INDEPENDENT-REVIEW.md).

## Working on the application

Python 3.11 or newer; plain HTML/CSS/JavaScript, with no frontend build step.
Use a virtual environment for the dependencies in `server/requirements.txt`.
From `server/`, `python -m arise_server --demo` serves sample data for development.
The demo works without root and uses an ephemeral per-process signing key
when a persistent key cannot be written. A real installation requires its
persistent signing key and fails closed if it is unavailable.

From the repository root, run `python -m unittest discover -s tests -v`.
The existing browser suite is `node tests/ui/sweep.js`; it requires Playwright
and a browser and exercises the static sample UI, not real Samba or Docker.

[Media build instructions](installer/MAKE-USB.md) explain how to create a
single ISO from a verified Ubuntu base. A build of uncommitted reviewed changes
must explicitly use `--working-tree`; ordinary release builds use the committed
source. New files must be tracked before export. Credentials must never enter
an image or the repository.

## Operations and requirements

- The owner decision record is [ANSWERS.md](docs/ANSWERS.md); later answers
  supersede earlier ones. Deliberate choices are not implementation defects.
- The current target is the HP EliteDesk 800 G1 SFF; the Dell OptiPlex 3010
  is the spare. The Synology DS216 has two bays and an ext4 filesystem.
  On the expected TPM 1.2 hardware, the encrypted disk needs its passphrase
  at every boot. Services start after unlocking; unattended updates must not
  leave the server waiting for an unavailable operator.
- Do not change routers, switches or the Google Mesh. No public application
  endpoint or router port forward is required. Remote access uses Tailscale.
- Do not freeze a DHCP lease and call it a reservation. The installer retains
  DHCP by default; verify a stable directory endpoint before production use.
- Enroll only church Macs. They use Samba AD plus the helper; linked existing
  accounts retain their local passwords. Personal Macs are never enrolled.
  There is no MDM requirement. See [MACS.md](docs/MACS.md).
- Passwords and PINs have the recorded throttles; optional TOTP must finish
  before a session is released. Administrator changes require a recent full
  password. Production browser access uses HTTPS; port 4147 is the local
  backend behind Caddy. The public HTTP certificate endpoint cannot log in.
- Backups include application state and audit history. A domain backup must be
  fresh and verified; app data must be backed up consistently. Restore original
  data and credentials before starting apps. See [BACKUPS.md](docs/BACKUPS.md)
  and [REINSTALL.md](docs/REINSTALL.md).
- Deleting users, shares and app data requires explicit action. The separately
  approved Trash aging and backup/snapshot retention remain automated.
- App limits account for all services in each stack and reserve system memory.
  Available templates are not a promise that every application can run together.

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [Security](docs/SECURITY.md) ·
[Directory](docs/DIRECTORY.md) · [Network](docs/NETWORK.md) ·
[Shares](docs/SHARES.md) · [Sync](docs/SYNC.md) · [Store](docs/STORE.md) ·
[Synology](docs/SYNOLOGY.md) · [Automator](docs/AUTOMATOR.md) ·
[CLI](docs/CLI.md) · [Hardware](docs/HARDWARE.md) ·
[Roadmap](docs/ROADMAP.md) · [Agent rules](CLAUDE.md).

MIT license: [LICENSE](LICENSE).
