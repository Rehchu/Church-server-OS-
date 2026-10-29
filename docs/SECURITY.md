# Security: the safety basics

What keeps the box safe, what Bradly decided about each (docs/ANSWERS.md,
round 3), and the one command that fixes each when the Security app shows
amber. Built in v0.8 "Exodus". The Security app (31) and `arisectl security`
read the same facts.

| What | Decision | Where it lives | Fix when amber |
|---|---|---|---|
| Two-step sign-in | optional, per person; Microsoft Authenticator when they opt in (round 2, 11; Oct 28) | `/etc/arise/secrets/totp/<user>.json`, root only | `sudo arisectl twofa reset <user>` for a lost phone |
| Browsers never sign out | until they choose to (r3 38) | `[web] session_hours = 8760` | nothing; the closet monitor still locks at ten minutes |
| Break-glass admin | yes (r3 21); at the closet monitor only (Oct 28) | the local user `arise-rescue`; password in `/etc/arise/secrets/rescue-password`, on the closet card taped inside the closet, and with Kristina (round 7, 57 and 73) | `sudo arisectl rescue rotate` |
| SSH | keys only, password login off (Oct 28) | `/etc/ssh/sshd_config.d/arise.conf`; the admin's key enrolled by `install.sh --ssh-key` | re-run the installer with `--ssh-key` |
| Asking twice | delete a user, empty a Trash, shut down re-ask the password; a yes lasts five minutes (Oct 28) | `POST /api/auth/reauth`, `require_recent_auth`, `withReauth()` in the dashboard | nothing |
| The restic password | on the closet card, by hand (Oct 28), and Kristina knows it (round 7, 58) | `/etc/arise/secrets/restic-password` on the box | `sudo arisectl rescue card` rewrites the card; the restic line stays blank for the pen |
| Encryption | LUKS on the disk, the TPM unlocks it (r3 22) | chosen in the Ubuntu installer; clevis binds it | `sudo arisectl encrypt tpm` |
| System snapshots | before every update, five kept (r3 23) | Timeshift, rsync mode, `/timeshift` on the root disk | `sudo arisectl snapshot create "note"` |
| Reinstall | from the Synology's backup (r3 24) | docs/REINSTALL.md | `sudo arisectl reinstall <repo>` |
| Lockout | none (r3 27) | no fail2ban; domain lockout threshold 0 | nothing: his decision |
| Virus scan | weekly, quarantine, a report (r3 28) | ClamAV, `arise-clamscan.timer` Sunday 23:30 | `sudo arisectl scan status` |
| The church certificate | padlock on every Mac (r3 29) | Caddy's internal CA; `/ca.crt` | `sudo systemctl start caddy` |
| Logs | a year (r3 26) | journald 1 year / 4 GB; logrotate 52 weeks | nothing |

## Two-step sign-in

Optional. Anyone turns it on from the flame menu: **Two-step sign-in…** shows
a QR code once; Microsoft Authenticator (**+** → **Other account**) scans it;
they type the six digits it shows; done. From then on the sign-in page asks
for the code after the password. The code is plain TOTP: no Microsoft
account, no internet needed on the server, the phone's clock and the box's
clock only (`arisectl doctor` checks the clock).

What is stored: one root-only file per person under
`/etc/arise/secrets/totp/`. The secret is shown exactly once, at setup. It is
never sent to the browser again, never in a log, never in git.

Turning it off: the person's own password plus a current code, in the same
menu. A lost phone: Bradly on the box, `sudo arisectl twofa reset first.last`
(it asks for the name typed again). Admins see a small **two-step** badge on
each user in Directory; `arisectl twofa list` prints the names.

The pending login: after a correct password the server answers
`{need_code: true, pending: <signed token>}`. The token lives five minutes
and dies after three wrong codes; the session cookie is set only when the
code matches. Pure rules in `server/arise_server/twofa.py`, pinned in
`tests/test_arise_server.py` (class Safety).

## SSH: keys only

Bradly (Oct 28): password login over SSH is off, always. The installer writes
`PasswordAuthentication no` and enrols the admin's public key from
`--ssh-key 'ssh-ed25519 AAAA…'` (or `--ssh-key-file`). No key yet means SSH is
closed until one is added; the closet monitor still signs in, and Cockpit on
9090 is the second door. `DenyUsers arise-rescue` keeps the break-glass
account off SSH entirely.

## Asking twice

Three clicks re-ask the signed-in person's password: delete a user, empty a
Trash, shut the box down (restart too). `POST /api/auth/reauth` checks it the
same way sign-in does and stamps the session cookie (`ra`); for five minutes
after that the stamp satisfies `require_recent_auth`, the dependency those
routes use (`recent = Depends(require_recent_auth)` in `main.py`; other
dangerous routes can take the same one). Without the stamp the route answers
403 `{reauth: true}`, and the dashboard's `withReauth(fn)` turns that into a
password box and runs `fn` again. Sample mode never asks.

## The break-glass admin: arise-rescue

For the day the domain is down and nobody can sign in. A **local** Ubuntu
account, in `sudo`, that works **at the closet monitor only** (Alt+F2 for a
text login). Not over SSH: keys only there, and `DenyUsers arise-rescue`
closes it regardless (Bradly, Oct 28).

It never works in the dashboard: the dashboard signs people in against the
domain (Kerberos) or the one local admin hash, nothing else.

Its 24-character password is made by the installer (step 6j), written to
`/etc/arise/secrets/rescue-password` (root only), and printed on the **closet
card**, which is taped **inside the closet**, never on the door (round 7, 57
and 73). Kristina has a copy. `sudo arisectl rescue card` writes the card to
`/etc/arise/CLOSET-CARD.html` (root only) for printing at the closet monitor,
and a copy with the password left out to the staff share; it never prints the
password to the screen. `rescue rotate` rewrites both: print it again and
replace the card inside the closet and Kristina's copy.

If Bradly can't be reached, **Kristina follows the closet card** (round 7,
59); after her, Ronnie (141). The card names them; the phone numbers are
written on it by hand.

Every sign-in of arise-rescue is caught from the journal within a minute
(`security.rescue_watch`, started with the dashboard), appended to
`/var/log/arise/rescue.log`, and pushed to Bradly's phone with "if that was
not you: `sudo arisectl rescue rotate`". `arisectl rescue status` prints the
last uses.

## The restic password: the closet card only

Bradly (Oct 28): the restic password's paper copy is the **closet card**,
written on it by hand (the card prints a blank line for it). Kristina knows it
too (round 7, 58). On the box it is `/etc/arise/secrets/restic-password`, root
only. Lose all three and the backups cannot be read by anyone, Arise-Home's
copy included.

## Encryption: LUKS with the TPM

Bradly chose: encrypt the data disk, let the TPM unlock it (round 3, 22).
On one disk, "the data disk" is the Ubuntu root disk, so the choice is made
**in the Ubuntu Server installer**, not later:

1. Ubuntu Server 24.04 installer → *Guided storage configuration* → keep
   *Use an entire disk* → tick **Set up this disk as an LVM group** → tick
   **Encrypt the LVM group with LUKS** → type a passphrase twice.
2. Write that passphrase on the closet card by hand (it leaves a blank line
   for it), and give it to Kristina (round 7, 58). Without it and without the
   TPM the disk is a brick.
3. First boot asks for the passphrase once. Then `install.sh` (step 6j) finds
   the LUKS volume and a TPM 2.0 and asks the passphrase one more time to
   bind the disk to the TPM with clevis:

       clevis luks bind -d /dev/sda3 tpm2 '{"pcr_bank":"sha256","pcr_ids":"7"}'
       update-initramfs -u

   From the next boot the TPM hands over the key and the box starts alone.
   The passphrase keeps working as the fallback (a BIOS change, a new board,
   a Secure Boot change: PCR 7 moves and the TPM refuses; type the passphrase,
   then `sudo arisectl encrypt tpm` again).

`arisectl encrypt status` says which of the three is true: LUKS present, TPM
present, bound. `--no-tpm` on the installer skips the binding (someone types
the passphrase at every boot). No TPM in the Dell: enable it in the BIOS
(Security → TPM 2.0 Security, or PTT on Intel boards); most OptiPlexes since
2016 have one.

Not verified here: no LUKS disk and no TPM in this environment. The commands
are the documented clevis path for Ubuntu with initramfs-tools; the first run
on the real Dell is the test, with the passphrase on the closet card as the way
back if it does not take.

## System snapshots before updates

Timeshift in rsync mode, on the root disk, with `/srv/arise`, `/mnt`,
`/var/lib/docker`, `/var/lib/arise` and `/var/log` excluded: the church's
files are in the restic backup, the snapshot is the operating system. The
installer takes the first one; `arisectl snapshot create "before update"`
takes another (Software Update calls it before anything installs); the last
five are kept; `arisectl snapshot restore <name>` rolls the system back
(the name typed to confirm; refused during a service).

## The virus scan

ClamAV, Sunday 23:30, over `/srv/arise/homes` and `/srv/arise/shares`.
Video and audio files are skipped (hours of CPU, never carriers), so are the
Trash and caches. A found file is **moved** to `/srv/arise/.quarantine/<date>/`
with a manifest, never deleted; the report goes to
`/var/log/arise/clamscan-<date>.json`; Bradly gets a push. The Security app
lists quarantined files with a **Put back…** button that asks for the name
typed. Refused during a service. `arisectl scan run` by hand.

## The church certificate

Caddy sits in front of the dashboard on 443 with `tls internal`: it makes a
certificate authority on the box and signs the dashboard's certificate with
it. That root is the church certificate. The dashboard serves it read-only at
`http://arise-server:4147/ca.crt` (a root certificate is public by nature);
`enroll-mac.sh` and `bind-mac.sh --dns` fetch it and put it in the Mac's
System keychain as trusted, so every enrolled Mac shows the padlock on
`https://arise-server.ad.arisecenla.com`. Phones over Tailscale use
Tailscale's own certificate. Staging: Caddy binds 127.0.0.1 like the domain.
`--no-caddy` turns it off.

By hand on a Mac:

    curl -o root.crt http://arise-server:4147/ca.crt
    sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain root.crt

## An internal mail server: decided, not built yet

Bradly decided (Oct 28) on Postfix + Dovecot on the box for staff and the
department accounts, `first.last@ad.arisecenla.com`, with every message
forwarded out through Resend's SMTP relay to the person's personal address
(stored on their Directory account), Reply-To set to the original sender.
Nothing of it is built in v0.8. What it needs when it is:

- **A Resend SMTP relay credential** in `/etc/arise/secrets/resend-smtp`
  (root only, like the API key): `smtp.resend.com:465`, user `resend`, the
  key as the password. Postfix's `relayhost` and `sasl_password_maps` point
  at it; the From must be at the domain verified in Resend (the same rule the
  Mail app already enforces: never a gmail.com address).
- **No inbound port.** Nothing on this box is reachable from the internet
  (rule 7). Mail *to* `first.last@ad.arisecenla.com` is internal only
  (Macs and phones on the LAN or Tailscale); the outside world reaches people
  at their personal address, which is where the forward lands.
- **Dovecot IMAP on the LAN and Tailscale only** (ufw: 993 from the LAN
  subnet, the VPN subnets and 100.64.0.0/10; nothing else), authenticating
  against the domain through PAM/winbind so the password is the one they
  already have.
- **A personal address per person** in the Directory (an attribute on the
  user, e.g. `otherMailbox`), which the forward map is generated from
  (`arisectl mail forwards`), and a Directory field to edit it.
- **The forward itself** as a Postfix `virtual_alias_maps` entry per person
  plus a header rewrite that keeps the original sender in Reply-To, so a
  reply from the personal mailbox goes to the right place.
- **Backups**: `/var/mail` (or Dovecot's maildirs under `/srv/arise/mail`)
  added to the config job; **the scan**: ClamAV already covers `/srv/arise`.

## Decided, nothing built

- **No lockout** (round 3, 27): no fail2ban (the installer removes it if an
  earlier run put it there), domain lockout threshold 0. Everything is behind
  Tailscale or inside the building; a locked-out pastor on a Sunday is the
  worse outcome.
- **Logs a year** (26): journald `MaxRetentionSec=1year`, `SystemMaxUse=4G`;
  `/var/log/arise/*.log` weekly, 52 kept.
- **Browsers never sign out** (38): the cookie lasts a year. The monitor's
  ten-minute lock is unchanged.
- **MIT** (37): `LICENSE` at the root.
