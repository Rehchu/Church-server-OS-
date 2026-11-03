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
| Encryption | LUKS; passphrase at boot on the expected TPM 1.2 hardware (H3/H6) | chosen in the Ubuntu installer; optional LAN SSH unlock; TPM 2.0 only if verified usable | `sudo arisectl encrypt status` |
| System snapshots | before every update, five kept (r3 23) | Timeshift, rsync mode, `/timeshift` on the root disk | `sudo arisectl snapshot create "note"` |
| Reinstall | from the Synology's backup (r3 24) | docs/REINSTALL.md | a dead box: the install USB, then `sudo bash /opt/arise-src/installer/install.sh --restore <repo>` (`arisectl` is gone with the disk) |
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

## Sign-in PINs (round 7, 160 to 162)

Each person may set a PIN of 4 to 8 digits for themselves, in **My Profile →
Sign-in PIN**, after typing their full password. Typing it at sign-in counts
for ten minutes; after that, or in a PIN session, the sheet asks for it again.

- **Admins (160):** the PIN works on the sign-in page and the lock screen,
  anywhere the dashboard answers (church Wi-Fi, Tailscale).
- **Staff (162):** the PIN opens the phone checklist (`/checklist`), on the
  phone it was set on, and nothing else. A random mark in a cookie
  (`arise_pin_device`, 400 days, httponly) ties it to that phone; the server
  keeps only the mark's sha256. A PIN session that asks for anything but
  `/api/auth/`, `/api/public/`, `/api/health` or `/api/checklist/` gets 403,
  even with `[web] staff_access = "portal"`.
- **Never by PIN (161):** a PIN session has no "typed the password recently"
  stamp (`fp`) and no reauth stamp (`ra`). `POST /api/auth/reauth` checks the
  password and never a PIN. So deletes, emptying a Trash, the FileVault and
  ariseadmin reveals, the Pastors emergency look and the YouTube renewal ask
  for the full password. A leader's password reset on the checklist asks for
  the leader's own password every time.

**Refused PINs:** one digit again and again (`1111`), a repeated chunk
(`1212`, `123123`), runs up or down (`1234`, `4321`), the keypad column
`2580` and its reverse, the PINs people choose most often, the birthday on
file as MMDD or DDMM, and the end of the mobile number on file.

**Stored:** `/var/lib/arise/pins.json`, mode 0600, one bcrypt hash per
person (bcrypt cost 10; verify performance on the actual hardware). A name with no
PIN costs the same time against a dummy hash. The PIN is never stored, never
logged and never sent back in an answer, and admins never see one.

**Guessing:** the device that guesses waits, the same throttle as passwords,
by address and never by account (round 4, 27). Separately, ten wrong PINs
for one account, from any devices, switch that account's PIN off. Bradly
gets Discord #alerts and a push, and the audit log gets `auth.pin.off`. The
password always works, and the next full-password sign-in switches the PIN
back on. A password change, an admin or leader reset, or disabling the
account also switches the PIN off, because they all go through
`revoke_sessions`. Deleting or renaming the account removes it.

**Admins:** Directory → **Sign-in PINs** lists who has one, what it opens,
and whether it is switched off. **Remove** deletes it, and the audit log
records `auth.pin.remove` with the admin's name. Nobody can see or set
someone else's PIN.

**The domain never sees a PIN.** It is checked against the hash on this
box. Kerberos and Samba still check passwords only. A password sign-in runs
`kinit` into a memory-only cache (`MEMORY:arise-login`) that is thrown away
straight after, so no Kerberos ticket outlives the sign-in either way. What
differs for a PIN session:

- No `fp` stamp, so setting or changing a PIN asks for the password.
- No reauth stamp until the password is typed.
- A staff PIN session reaches the checklist only.
- The audit log says `auth.pin` instead of `auth.login`.

The rest is the same: the session cookie, two-step (the six digits are still
asked after a PIN), the new-device email, and the home folder. A Mac sign-in,
a share mount and the Nextcloud app's device passwords never take a PIN.

**Full password for administration:** the root Terminal requires a recent full
password after PIN sign-in. Administrator mutation routes use
`require_recent_admin`, which checks both the role and the password recheck.
The dashboard handles the reauthentication prompt and retries once.

Rules: `server/arise_server/pins.py`. Tests: `tests/test_pins.py`, plus the
PIN steps in `tests/ui/sweep.js`.

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

## Encryption: LUKS and the boot passphrase

H3 replaces round 3's automatic TPM-unlock assumption. The primary HP
EliteDesk 800 G1 SFF is expected to have TPM 1.2, which clevis cannot use for
TPM 2.0 unlock. Plan for **a passphrase at every boot**. H6 permits TPM binding
if the actual hardware has a usable TPM 2.0; verify its version and a successful
restart before relying on unattended unlock.

1. In the Ubuntu Server storage screen, identify the intended disk, choose
   an LVM layout and **Encrypt the LVM group with LUKS**. Review the final
   plan before confirming disk erasure. Encryption is chosen at installation;
   the later ariseOS wizard does not encrypt an existing plain root filesystem.
2. Write the passphrase on the closet card by hand, as the owner chose.
   Bradly and Kristina know it (round 7, 58). Keep it available for recovery
   even if TPM 2.0 binding is later possible.
3. Boot with the install USB removed and test the passphrase at the keyboard.
   Check `sudo arisectl encrypt status`. A successful VM test does not verify
   the HP's firmware, disk encryption, TPM or physical recovery path.

On passphrase boot, power-on-after-AC-loss stops at unlock. Scheduled updates
must not restart the server automatically when unattended unlock is unknown
or unavailable. Plan a supervised restart outside services, with someone able
to unlock it. The full OS, Samba DNS, dashboard and Tailscale start only after
that step.

### Optional SSH unlock on the church LAN

Set this up only after the keyboard recovery path works:

```sh
sudo arisectl encrypt ssh --network dhcp --authorized-keys /path/to/owner-public-keys
```

The file contains **bare RSA (at least 2048-bit), ECDSA or Ed25519 public
keys**, not private keys, FIDO keys, certificates or lines with
`authorized_keys` options. The command requires an explicit boot-network
choice and creates a restricted initramfs SSH service on port 2222, forced
to `cryptroot-unlock` without forwarding or a general shell. Review the
command's result and test a supervised reboot before relying on it.

From a permitted church LAN computer, use `ssh -p 2222 root@<boot-lan-ip>`.
Record and verify the early-boot SSH host-key fingerprint locally. DHCP may
assign an address different from the running server's address. Do not assume
`arise-server` resolves while its own DNS is locked, or that its Tailscale
address works before boot. The normal OS firewall is also unavailable at
this stage; use the trusted church LAN and verify actual reachability. No
router, DHCP or port-forward change is part of this setup. Retain the local
keyboard if the preboot network is unavailable.

TPM 2.0 binding, when applicable under H6, uses `sudo arisectl encrypt tpm`.
It does not remove the recovery passphrase. Firmware or Secure Boot changes
can affect measured boot and require the passphrase; verify recovery before
such maintenance. Physical LUKS, TPM and early-boot SSH remain installation
rehearsal checks, not claims established by mocked or VM-only tests.

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
Video and audio files are skipped to reduce scan load, as are Trash and
caches. Those exclusions are coverage gaps, not proof the files are harmless. A found file is **moved** to `/srv/arise/.quarantine/<date>/`
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

## Staff email: forwarding and the Inbox (built)

The Postfix and Dovecot plan of Oct 28 was replaced by what is built: **no mail server on the
box, and no inbound port** (rule 7). Mail to `first.last@arisecenla.com` (H10) arrives at
Resend through the domain's MX at `@`. Every five minutes `arise-mailfwd.timer` asks Resend,
over an outgoing call, for what arrived, and `mailfwd.py` sends each message on through Resend
to the personal email on the person's profile: From the church's verified address
("<sender> via Arise Church IT"), Reply-To the original sender. No message is stored here; the
forwarding log keeps who, from whom, the subject and when, never the body, root only. A forward
that fails is retried for about half an hour, then Discord #alerts says so. `sudo arisectl mail
forward` lists every person and where their mail goes; `forward export <first.last>` is a
leaver's record.

People in `[inbox] users` (Kristina, H11) are left out of forwarding and read their mail in the
**Inbox** app (`inbox.py`) instead: they sign in with their own church account and the server
picks the inbox from who is signed in, never from the browser. Mail stays in Resend; email HTML
is shown in a sandboxed frame with no scripts. The Inbox needs the server's Resend key to have
full access (`sudo arisectl mail key`; on the private install disc, H9), and `sudo arisectl mail
inbox check` proves it on install day.

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


## Independent-review corrections

TOTP challenges contain only a random reference; the waiting session remains in
server memory and is released once after a valid code. Challenges expire after
five minutes, three failures, or a server restart. Signed JSON is not encryption.

With Caddy enabled the application binds loopback; remote browsers use HTTPS.
The port-80 endpoint serves only the public CA certificate. Enrollment verifies
its installer-supplied SHA256 fingerprint before trusting it.

Folder compression checks each descendant and refuses filesystem links during
reading. Public archive links never include the Pastors folder, including when
a parent directory was selected. Emergency-access responses report actual
notification delivery failures; contact the pastors directly if email fails.

The audit file is append-only by application convention, not immutable against
root. Write failures are exposed in upkeep; state and audit history are included
in backups. Independently protected or offline copies remain necessary against
a compromised source server.
