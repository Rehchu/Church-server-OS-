# Remote access — the server is in a locked closet

The PC goes in the closet, the door locks, and from then on every bit of
work on it happens from somewhere else: your Mac at the media desk, your
laptop at home, the iMac in Alexandria, the office PCs at the Apostolic Hub.
This page is the whole story of how that works and what it costs in
exposure. Nothing here opens the dashboard to the internet; a public door for
members is a separate decision, docs/SETUP-GUIDE.md § 9.

Which VLAN may reach which port, how a whole site (Alexandria) joins
through one route box, and what happens to all of this when the server moves
to the Hub are in **docs/NETWORK.md** and **docs/MOVING-DAY.md**; the order to
set it all up is **docs/SETUP-GUIDE.md**. Members (not just the admin) can
sign in to the dashboard too; what they see is docs/SETUP-GUIDE.md § 6.

Four doors, in the order you will use them:

| Door | What you get | From where |
|---|---|---|
| **SSH** | a terminal on the box | anywhere, over the VPN |
| **The VPN** | the church network on your laptop, wherever it is | anywhere |
| **Guacamole** | remote desktop (RDP, VNC, SSH) to any church computer, in a browser tab | anywhere, over the VPN |
| **The dashboard** | everything in `http://arise-server:4147`, including the Terminal app | anywhere, over the VPN |

The VPN is the door the other three sit behind. Set it up first.

---

## (a) SSH

`arise-web` is the dashboard; `ssh` is what you use when the dashboard is
the thing that is broken.

**Port.** `[remote] ssh_port` in `arise.toml`, 22 by default. The firewall
the installer writes allows it from anywhere; the VPN is what keeps "anywhere"
small.

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

**fail2ban.** Installed and enabled with the `sshd` jail: five bad passwords
from one address and that address is banned for ten minutes. Over the VPN you
will never see it; it exists for the day someone forwards the port by
mistake.

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

1. Open the link it prints and sign in. Use **one** login for the church
   (a Google account works; `arisenow.church@gmail.com` is the obvious one)
   so every device lands in the same network ("tailnet").
2. In the admin console (login.tailscale.com → Machines → arise-server →
   Edit route settings) **approve the subnet route** `192.168.1.0/24`. That
   is what lets an off-site laptop reach the Synology, the printers and the
   Macs at Pineville, not just the server.
3. Install the Tailscale app on every off-site Mac, PC and phone and sign in
   with the same login. Each one shows up in the Machines list.
4. **MagicDNS** (DNS → MagicDNS, on by default): `arise-server` now resolves
   from any device on the tailnet, anywhere.
5. **Split DNS for the realm** (DNS → Nameservers → Add nameserver → Custom,
   nameserver = the server's LAN IP, *Restrict to domain*
   `ad.arisecenla.church`). This is what makes a **domain-bound Mac in
   Alexandria** find the domain controller: Kerberos and LDAP look up
   `ad.arisecenla.church` and get the real DC, through the tunnel.
6. `--ssh` turns on **Tailscale SSH**: `ssh arise-server` from any tailnet
   device, authenticated by your Tailscale login, with the sshd rules above
   still applying for plain SSH. Useful on a phone.

What you need to know before choosing it:

- **It is a third party.** Tailscale's coordination server hands out the keys
  and tells devices where each other are. Your traffic itself goes
  device-to-device, encrypted with WireGuard; Tailscale cannot read it. When
  two devices cannot reach each other directly, traffic is relayed through
  Tailscale's DERP servers, still encrypted end to end.
- **Plans.** The free Personal plan is for one user and up to 100 devices.
  A church with several people logging in from their own accounts is more
  than one user; read the current pricing page before you add the second
  person. One shared church login on the free plan works for a handful of
  machines, with the trade-off that everyone shares one identity.
- **If Tailscale goes away** (the company, your account), you fall back to
  the WireGuard option below. Nothing on the server depends on it except the
  tunnel.

The dashboard's **Remote** app reads `tailscale status` and shows every
device, online or not, and which site it belongs to.

### WireGuard — self-hosted, nothing in the middle

Plain WireGuard on the server. You own every key; nobody relays anything.
The price is the plumbing: a port forward, a public name, and a config file
per device.

On the server, `install.sh --with-wireguard` does this:

- installs `wireguard`, writes `/etc/wireguard/wg0.conf` with a fresh server
  key, `Address 10.47.0.1/24`, `ListenPort 51820`, and PostUp/PostDown rules
  that NAT the tunnel onto the LAN;
- enables `wg-quick@wg0`; opens `51820/udp` in the firewall.

Then you:

1. **Forward UDP 51820** on the Pineville router to the server's LAN IP.
   It is the only port the outside world ever sees.
2. **Give the church a public name.** Either a static IP from the ISP, or a
   dynamic DNS name updated by the router (most routers have a DDNS page;
   DuckDNS, No-IP and Cloudflare all work). Put it in `arise.toml`:
   `[remote] wg_endpoint = "arise.duckdns.org:51820"`.
3. **Add a device.** Dashboard → Remote → *Add WireGuard peer* → name it
   (`bradly-macbook`), or `sudo arisectl remote add-peer bradly-macbook`.
   Either way you get a client config:

   ```
   [Interface]
   PrivateKey = …
   Address = 10.47.0.2/32
   DNS = 10.47.0.1
   [Peer]
   PublicKey = …
   PresharedKey = …
   Endpoint = arise.duckdns.org:51820
   AllowedIPs = 10.47.0.0/24, 192.168.1.0/24
   PersistentKeepalive = 25
   ```

   Paste it into the WireGuard app (Mac App Store, Windows, iOS, Android) as a
   new tunnel. `DNS = 10.47.0.1` points the device at the DC's DNS while the
   tunnel is up, so `ad.arisecenla.church` resolves. The server keeps the
   peer's public key in `/etc/wireguard/peers/<name>.json`; it never sees the
   private key again, so if the config is lost, delete the peer and make a
   new one.
4. **Alexandria as a site.** Instead of a tunnel on every Mac there, run one
   tunnel at the site: WireGuard on the Alexandria router if it supports it
   (many do: UniFi, pfSense/OPNsense, GL.iNet, MikroTik), or on a small box
   (a Raspberry Pi, an old laptop) that the Alexandria router routes
   `192.168.1.0/24` and `10.47.0.0/24` through. Add it as a peer with
   `AllowedIPs = 10.47.0.2/32, 192.168.2.0/24` on the server side so
   Pineville can reach Alexandria too. Then every Mac in Alexandria is "on
   the network" without running anything. The Tailscale version of the same
   box is docs/NETWORK.md option B; after the server moves to the Hub,
   Pineville needs one as well (docs/MOVING-DAY.md).

**wg-easy** (the `wg-easy` template) is the same WireGuard with a web page
for adding devices and QR codes for phones. Use it *instead of* native
WireGuard, not alongside it: both want UDP 51820. If you deploy the template,
do not pass `--with-wireguard` to the installer.

### Which one

Tailscale, unless the third-party part bothers you or the plan does not fit.
It is what gets Bradly's laptop onto the church network from a hotel in five
minutes, and it is what lets a Mac in Alexandria stay domain-joined without
anyone touching the Alexandria router. WireGuard is there for the day that
answer changes, and the dashboard supports both.

---

## (c) Remote desktop — Apache Guacamole

Guacamole is a remote desktop gateway that runs in a browser tab: no client
to install, and it reaches **any** church computer through the server, not
just the server itself. Deploy it with the `guacamole` template (Dashboard →
Apps → Guacamole → Install, or `arisectl app deploy guacamole`), then open
`http://arise-server:8084/guacamole` (or `https://remote.ad.arisecenla.church`
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
ldap-hostname: arise-server.ad.arisecenla.church
ldap-port: 389
ldap-encryption-method: none
ldap-user-base-dn: CN=Users,DC=ad,DC=arisecenla,DC=church
ldap-username-attribute: sAMAccountName
ldap-search-bind-dn: CN=guac-ldap,CN=Users,DC=ad,DC=arisecenla,DC=church
ldap-search-bind-password: <that account's password>
ldap-group-base-dn: CN=Users,DC=ad,DC=arisecenla,DC=church
ldap-member-attribute: member
```

`guac-ldap` is an ordinary domain user with no groups
(`sudo arisectl user add guac-ldap --display "Guacamole lookup"`); Guacamole
uses it only to search. `ldap-encryption-method: none` is fine because the
traffic never leaves the server (Guacamole and the DC are on the same box).
The LDAP extension has to be present in the Guacamole image's extensions
folder; the template's notes say where it goes and the version has to match
the Guacamole version.

What Guacamole does not do: wake a sleeping computer. Turn off sleep on any
Mac or PC you want to reach from home (Energy Saver / Power settings), or
use Wake-on-LAN from the router.

---

## (d) The dashboard, from anywhere

Over the VPN the dashboard is just `http://arise-server:4147` (MagicDNS) or
`http://<tailscale ip>:4147` or `http://10.47.0.1:4147` (WireGuard). Same
login, same everything. The dashboard listens on every interface and the
firewall allows 4147 from the LAN and the VPN ranges; it is never forwarded
on the router.

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
and your own peace of mind on a hotel network. `install.sh --with-caddy`
installs Caddy and `config/caddy/Caddyfile`, which proxies:

| Name | To |
|---|---|
| `arise-server.ad.arisecenla.church` (and plain `arise-server`) | the dashboard, :4147 |
| `vault.ad.arisecenla.church` | Vaultwarden, :8083 |
| `remote.ad.arisecenla.church` | Guacamole, :8084 |

`tls internal` means Caddy makes its own certificate authority on the server
and signs a certificate for each name. Browsers do not know that CA, so once
per Mac:

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
sudo samba-tool dns add 127.0.0.1 ad.arisecenla.church vault  A 192.168.1.10
sudo samba-tool dns add 127.0.0.1 ad.arisecenla.church remote A 192.168.1.10
```

(replace the address with the server's). Over Tailscale the split-DNS rule
from (b) sends those lookups to the same DNS, so they work off-site too.

---

## (f) From the closet to anywhere — the checklist

1. `ssh-copy-id` from your Mac. Confirm `ssh bradly@arise-server` needs no password.
2. Run `sudo bash installer/install.sh --with-tailscale --with-caddy` (or `--with-wireguard`). Re-running it is safe.
3. `sudo tailscale up --ssh --advertise-routes=192.168.1.0/24`, sign in, approve the route, set MagicDNS and the split DNS for `ad.arisecenla.church`.
4. Install Tailscale on your laptop and phone. From your phone's hotspot, open `http://arise-server:4147`. If it opens, the closet door can close.
5. Deploy Guacamole, change `guacadmin`, add the media Mac (VNC) and the lobby PC (RDP). Open each one from the laptop on the hotspot.
6. Trust the Caddy CA on your Mac; open `https://arise-server.ad.arisecenla.church`.
7. Turn off sleep on every computer you intend to reach.
8. `sudo arisectl doctor`, then the Remote app in the dashboard: SSH key-only, VPN up, Guacamole running.

**What is exposed to the internet, in total.** With Tailscale: nothing. No
port on the church router is forwarded; the server makes outbound
connections only. With WireGuard: one UDP port, 51820, and WireGuard does
not even answer a packet unless it is signed by a known peer key, so a port
scan sees it as closed. In both cases: no SSH port, no dashboard port, no
RDP, no SMB, no DNS, nothing of the domain controller. Everything that can
talk to the server does so because it holds a key you gave it, and the
dashboard behind that still asks for its password. What is **not** covered:
a church computer that is itself exposed (a Windows PC with RDP forwarded
"for convenience"), a VPN key on a laptop that gets stolen (remove the device
in the Tailscale console or delete the peer file and `wg set wg0 peer <key>
remove`), and the dashboard password written on a sticky note in the closet.
