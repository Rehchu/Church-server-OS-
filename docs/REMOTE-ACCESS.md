# Remote access — the server is in a locked closet

The PC goes in the closet, the door locks, and from then on every bit of
work on it happens from somewhere else: your Mac at the media desk, your
laptop at home, the iMac in Alexandria, the office PCs at the Apostolic Hub.
This page is the whole story of how that works and what it costs in
exposure. Nothing here opens the dashboard to the internet; a public door for
members is a separate decision, docs/SETUP-GUIDE.md § 9.

The existing network, direct Tailscale access from Alexandria's Mac, and
what happens when the server moves to the Hub are in **docs/NETWORK.md** and
**docs/MOVING-DAY.md**; the order to
set it all up is **docs/SETUP-GUIDE.md**. Only the four admins use the
dashboard; staff and volunteers reach their files through Nextcloud over
Tailscale (docs/SYNC.md, docs/ANSWERS.md round 5, 41).

Four doors, in the order you will use them:

| Door | What you get | From where |
|---|---|---|
| **SSH** | a terminal on the box | anywhere, over the VPN |
| **The VPN** | the church network on your laptop, wherever it is | anywhere |
| **Guacamole** | remote desktop (RDP, VNC, SSH) to any church computer, in a browser tab | anywhere, over the VPN |
| **The dashboard** | everything in `https://arise-server.ad.arisecenla.com`, including the Terminal app | anywhere, over the VPN |

The VPN is the door the other three sit behind. Set it up first.

---

## (a) SSH

`arise-web` is the dashboard; `ssh` is what you use when the dashboard is
the thing that is broken.

**Port.** `[remote] ssh_port` in `arise.toml`, 22 by default. Verify the effective host firewall rules. A rule allowing SSH from anywhere
is not limited by the existence of a VPN; LAN hosts can reach it too. No router
port is forwarded.

**Keys, not passwords.** On your Mac, once:

```bash
ssh-keygen -t ed25519 -C "bradly macbook"        # press Enter at the passphrase prompt, or set one
ssh-copy-id bradly@arise-server                  # type the account password this one last time
ssh bradly@arise-server                          # no password now
```

`ssh-copy-id` appends your public key to `/home/bradly/.ssh/authorized_keys`
on the server. Do it from every Mac you work from. Keep the private key
(`~/.ssh/id_ed25519`) on that Mac only; never email it.

**What the installer does to sshd.** It writes
`/etc/ssh/sshd_config.d/arise.conf`:

```
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no        # ONLY written once an authorized_keys file exists for the admin user
MaxAuthTries 4
X11Forwarding no
```

If no `authorized_keys` file exists yet when the installer runs, it leaves
password login **on** and says so loudly, so you cannot lock yourself out of
a PC in a locked closet. Run `ssh-copy-id` from your Mac, then run the
installer again (or add the line by hand and `systemctl reload ssh`).

**No fail2ban, no lockout.** Bradly's choice (round 3, 27): no address and no
account is ever locked out. The installer removes fail2ban if an earlier
run put it there. SSH is keys only (round 4, 33), so there is no password
to guess; the closet monitor and `arise-rescue` are the way in without a
key (docs/SECURITY.md).

**Never from outside.** Do not forward port 22 on the church router. SSH is
reachable over the VPN, and that is enough. If you ever need SSH without the
VPN, Tailscale SSH (below) is the way, not a port forward.

---

## (b) The VPN — two options

The VPN makes an off-site computer behave as if it were plugged into the
Pineville network: `arise-server` resolves, the shares mount, the dashboard
opens, a Mac can even bind to the domain. Two ways to do it. Pick one.

### Tailscale — recommended

Tailscale is WireGuard with the hard parts done for you: no port forward on
the church router, no dynamic DNS, no key files to carry around, works from
any Wi‑Fi (hotel, phone hotspot, Alexandria), and every device gets a stable
address and a name.

On the server, once:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh --advertise-routes=192.168.1.0/24   # the server's own LAN subnet; docs/NETWORK.md § The IP plan
```

(`install.sh --with-tailscale` does the first line and prints the second,
because the second opens a login link in a browser and needs you.)

Then:

1. Open the link it prints and sign in with **a church Google account**
   (round 7, 130: the tailnet belongs to the church, not to a person), so every
   device lands in the same network ("tailnet") and the account outlives any
   one person's job. Write which account it is on the closet card by hand.
2. In the admin console (login.tailscale.com → Machines → arise-server →
   Edit route settings) **approve the subnet route** `192.168.1.0/24`. That
   is what lets an off-site laptop reach the Synology, the printers and the
   Macs at Pineville, not just the server.
3. **Who gets it** (round 7, 129): the four admins' phones and laptops, and
   the staff laptops that go home. Not every church Mac: the ones that never
   leave the building don't need it. On each: install the Tailscale app (the
   Mac helper's Tailscale task does it on church Macs, with
   `--accept-routes`), sign in with the church login, and check it shows in
   the Machines list. A staff laptop is a church Mac, so it is enrolled
   (docs/MACS.md) and its Tailscale comes with the helper. A personal phone of
   an admin signs in to the same tailnet; a personal phone of staff gets the
   Nextcloud app and church Wi-Fi only (round 7, 36).
   When someone leaves, remove their devices in the admin console (Machines →
   … → Remove); Cut off in the Macs app does not touch Tailscale (round 7,
   153).
4. **MagicDNS** (DNS → MagicDNS, on by default): `arise-server` now resolves
   from any device on the tailnet, anywhere.
5. **Split DNS for the realm** (DNS → Nameservers → Add nameserver → Custom,
   nameserver = the server's LAN IP, *Restrict to domain*
   `ad.arisecenla.com`). This is what makes a **domain-bound Mac in
   Alexandria** find the domain controller: Kerberos and LDAP look up
   `ad.arisecenla.com` and get the real DC, through the tunnel.
6. `--ssh` turns on **Tailscale SSH**: `ssh arise-server` from any tailnet
   device, authenticated by your Tailscale login, with the sshd rules above
   still applying for plain SSH. Useful on a phone.

What you need to know before choosing it:

- **It is a third party.** Tailscale's coordination server hands out the keys
  and tells devices where each other are. Your traffic itself goes
  device-to-device, encrypted with WireGuard; Tailscale cannot read it. When
  two devices cannot reach each other directly, traffic is relayed through
  Tailscale's DERP servers, still encrypted end to end.
- **Plans.** Check current Tailscale pricing and organizational eligibility. A shared
  church login makes every device share one identity; do not infer eligibility
  or a free allowance from an old user/device count.
- **If Tailscale is unavailable**, local access and SSH recovery remain
  necessary. An alternative remote-access design needs separate testing and
  must respect the no-router-change rule; there is no automatic fallback.

The dashboard's **Remote** app reads `tailscale status` and shows every
device, online or not, and which site it belongs to.

### Other VPN designs

The approved setup is Tailscale with no router changes and no public listener.
The native WireGuard and wg-easy templates are legacy alternatives, not steps
to enable for this install. Changing to a design that requires router forwarding
is outside the current plan. Check current Tailscale terms instead of relying
on the old free-plan user/device figures in historical documents.

---

## (c) Remote desktop — Apache Guacamole

Guacamole is a remote desktop gateway that runs in a browser tab: no client
to install, and it reaches **any** church computer through the server, not
just the server itself. Deploy it with the `guacamole` template (Dashboard →
Apps → Guacamole → Install, or `arisectl app deploy guacamole`), then open
`http://arise-server:8084/guacamole` (or `https://remote.ad.arisecenla.com`
once Caddy is on).

First login is `guacadmin` / `guacadmin`. **Change it before you do anything
else** (top-right → Settings → Preferences). Then Settings → Connections →
New Connection:

| Target | Protocol | What to set | On the target first |
|---|---|---|---|
| The server | SSH | hostname `arise-server`, port 22, username, private key pasted in (or password if you left it on) | nothing |
| A Windows PC (lobby, office) | RDP | hostname or IP, port 3389, username `ARISE\user`, "Ignore server certificate" on | Settings → System → Remote Desktop → **on**; the user in "Remote Desktop Users" |
| A Mac (media Mac, Alexandria iMac) | VNC | hostname or IP, port 5900, the VNC password | System Settings → General → Sharing → **Screen Sharing** on → ⓘ → "VNC viewers may control screen with password" → set a password |
| The Synology | SSH or RDP (DSM web is easier: just open it over the VPN) | | |

Each connection can be shared with specific Guacamole users or groups.

**Guacamole users and the dashboard login are separate things.** The
dashboard has one admin; Guacamole has its own users. The useful setup is to
let Guacamole authenticate against the **domain**, so the same `ARISE`
accounts work, and the Remote Desktop Users group decides who sees what.
Add these lines to `guacamole.properties` (the template mounts it at
`/srv/arise/apps/guacamole/home/guacamole.properties`) and restart the app:

```
ldap-hostname: arise-server.ad.arisecenla.com
ldap-port: 636
ldap-encryption-method: ssl
ldap-user-base-dn: CN=Users,DC=ad,DC=arisecenla,DC=com
ldap-username-attribute: sAMAccountName
ldap-search-bind-dn: CN=guac-ldap,CN=Users,DC=ad,DC=arisecenla,DC=com
ldap-search-bind-password: <that account's password>
ldap-group-base-dn: CN=Users,DC=ad,DC=arisecenla,DC=com
ldap-member-attribute: member
```

`guac-ldap` is an ordinary domain user with no groups
(`sudo arisectl user add guac-ldap --display "Guacamole lookup"`); Guacamole
uses it only to search. Install the DC certificate authority in Guacamole’s
Java trust store and verify the DC hostname. Do not disable Samba’s strong
authentication requirement to make a plaintext simple bind work. A container
sharing the physical host is not a reason to send LDAP passwords unencrypted.
The LDAP extension has to be present in the Guacamole image's extensions
folder; the template's notes say where it goes and the version has to match
the Guacamole version.

Guacamole requires the remote computer to be awake. Configure its own Energy
Saver / Power settings if it must remain reachable; no router change or
Wake-on-LAN service is part of this setup.

---

## (d) The dashboard, from anywhere

Over the VPN use `https://arise-server.ad.arisecenla.com` with verified church
certificate trust and working split DNS. Caddy listens on 443; the application
backend on 4147 listens only on loopback. Do not use a raw Tailscale IP for an
HTTPS hostname unless the certificate actually covers it. Port80 exposes only
the public bootstrap certificate at `/ca.crt`; no authentication or management
API is served there. Verify its expected SHA256 before trusting it.

**The Terminal app** in the dashboard is a real shell on the server, running
as the user `arise-web` runs as, which is root on the Linux install. It is
there so that a locked-closet server never needs a monitor plugged in. Treat
it exactly like a root prompt: anyone who has the dashboard password has the
box. That is the reason the dashboard password is a real one and the
dashboard is never reachable from the internet.

---

## (e) HTTPS — Caddy with its own certificate authority

Three things want HTTPS: the Bitwarden apps (they refuse plain HTTP except on
localhost), Guacamole (clipboard and file transfer need a secure context),
and your own peace of mind on a hotel network. Caddy is **on by default since
v0.8** (round 3, 29; `--no-caddy` to skip, `--with-caddy` still accepted):
`install.sh` installs Caddy and `config/caddy/Caddyfile`, which proxies:

| Name | To |
|---|---|
| `arise-server.ad.arisecenla.com` (and plain `arise-server`) | the dashboard, :4147 |
| `vault.ad.arisecenla.com` | Vaultwarden, :8083 |
| `remote.ad.arisecenla.com` | Guacamole, :8084 |

`tls internal` means Caddy makes its own certificate authority on the server
and signs a certificate for each name. Browsers do not know that CA. The current dashboard enrollment line pins the root certificate’s SHA256
before trusting it. Standalone `bind-mac.sh` requires both `--ca-file` and
`--ca-sha256` to add certificate trust; `--dns` alone never trusts an HTTP-fetched
root. Obtain the fingerprint through a trusted connection, not from the same
unverified download. The Security app says whether the server certificate exists. By hand, once per Mac:

```bash
scp bradly@arise-server:/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt ~/Desktop/arise-ca.crt
sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain ~/Desktop/arise-ca.crt
```

(or double-click `arise-ca.crt`, add it to the System keychain, open it in
Keychain Access and set "When using this certificate" to Always Trust).
On a domain-joined Mac this can also be pushed with a configuration profile.
On Windows: double-click the `.crt` → Install Certificate → Local Machine →
Trusted Root Certification Authorities. On a phone, email yourself the file
and install it as a profile.

The names need DNS records in the domain's DNS so every device resolves
them to the server:

```bash
sudo samba-tool dns add 127.0.0.1 ad.arisecenla.com vault  A 192.168.1.10
sudo samba-tool dns add 127.0.0.1 ad.arisecenla.com remote A 192.168.1.10
```

(replace the address with the server's). Over Tailscale the split-DNS rule
from (b) sends those lookups to the same DNS, so they work off-site too.

---

## (f) From the closet to anywhere — the checklist

1. `ssh-copy-id` from your Mac. Confirm `ssh bradly@arise-server` needs no password.
2. Use the installer’s approved Tailscale and SSH-key settings. Inspect effective sshd and firewall policy after installation; do not enable WireGuard forwarding.
3. `sudo tailscale up --ssh --advertise-routes=192.168.1.0/24`, sign in, approve the route, set MagicDNS and the split DNS for `ad.arisecenla.com`.
4. Install Tailscale on your laptop and phone. From your phone's hotspot, open `https://arise-server.ad.arisecenla.com`. If it opens, the closet door can close.
5. Deploy Guacamole, change `guacadmin`, add the media Mac (VNC) and the lobby PC (RDP). Open each one from the laptop on the hotspot.
6. Trust the Caddy CA on your Mac; open `https://arise-server.ad.arisecenla.com`.
7. Turn off sleep on every computer you intend to reach.
8. `sudo arisectl doctor`, then the Remote app in the dashboard: SSH key-only, VPN up, Guacamole running.

**Exposure to verify.** No church router port is forwarded in this plan.
Remote access uses authenticated Tailscale devices; authorized LAN clients
also reach the server directly, so the VPN is not the entire access boundary.
Verify effective host/container firewall rules, DNS and certificate trust on
the actual installation. Revoke lost devices in Tailscale and their application
sessions. Other church machines' existing public listeners, stolen credentials
and an unlocked administrator session remain separate access paths.
