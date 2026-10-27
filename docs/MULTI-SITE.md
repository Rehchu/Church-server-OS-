# Three sites, one server

| Site | What it is | What is there | How it reaches the server |
|---|---|---|---|
| **Arise Church Pineville** (`pineville`, kind `main`) | the main campus, 501 Ates Road | the server, the domain controller, the Synology, the media Mac, the lobby PC, the LAN `192.168.1.0/24` | it is the LAN |
| **Arise Church Alexandria** (`alexandria`, kind `campus`) | the second campus | the Macs that run the service there, a router | the VPN: always-on on each Mac, or one site-to-site tunnel at the router |
| **The Apostolic Hub** (`hub`, kind `office`) | office and leadership | laptops and office PCs, people who move between sites | the VPN, one client per computer |

Each site is a `[[sites]]` block in `arise.toml` (id, name, kind, address,
subnet, probe, services, note). The dashboard's **Campuses** app pings each
site's `probe` host and lists the domain computers whose address falls in
that site's subnet. Pick as the probe the one device at that site that is
always on: the router, or the Mac at the sound desk. Leave it blank and the
site just shows as "not monitored".

## Pineville: the main site

Everything that is a single copy of something lives here: the directory
(`samba-ad-dc`), the home folders or the Synology that holds them, the
automator and its token, the backups. The server's LAN address should be
**fixed** (a DHCP reservation on the router, or a static address; see
INSTALL.md § Fixed address), because the other sites' DNS points at it.

## Alexandria: a campus

Macs in Alexandria can be full members of the domain. Two ways to get them
"on the network":

- **Always-on VPN on each Mac.** Tailscale installed on the Mac, signed in,
  set to start at login. The Mac binds to `AD.ARISECENLA.CHURCH` over the
  tunnel (the split-DNS rule in docs/REMOTE-ACCESS.md is what makes the realm
  resolve). Simplest; nothing to do at the Alexandria router. Each Mac is
  its own tunnel, so if one Mac's Tailscale is signed out, only that Mac is
  off the network.
- **A site-to-site tunnel at the router.** WireGuard on the Alexandria
  router (or a small box behind it) with the whole `192.168.2.0/24` routed
  through it, and `192.168.1.0/24` routed back. Every device at Alexandria is
  then on the church network with nothing installed; printers and the
  check-in iPad included. One tunnel to watch instead of ten. The Alexandria
  router must support it (UniFi, OPNsense/pfSense, MikroTik, GL.iNet do; an
  ISP-supplied box usually does not). Tailscale can do this too: a Raspberry
  Pi in Alexandria running `tailscale up --advertise-routes=192.168.2.0/24`
  and the Pineville server advertising `192.168.1.0/24`.

**When the VPN is down** (internet out at either end): a Mac with a mobile
account still logs in with the cached password and the cached home folder.
What stops working is anything on the server: the home share does not mount,
Desktop and Documents show the last synced copy, the shares and the
dashboard are unreachable. The service in Alexandria still runs. When the
tunnel returns, the mobile account syncs. This is the reason mobile accounts
are recommended over true network homes in docs/MAC-MIGRATION.md.

**Latency.** Pineville to Alexandria is roughly 30 miles; over two consumer
internet connections expect 20–50 ms through the tunnel and whatever the
slower upload is (often 10–40 Mbit/s) as the ceiling. Fine for logins, the
dashboard, files of a few hundred MB, Guacamole. Not fine for editing a
40 GB service recording that lives in Pineville: copy it over, or keep the
media work local and let Syncthing move the finished pieces overnight.

## The Apostolic Hub: office clients

No site infrastructure: each laptop and office PC runs the VPN client and
signs in. Windows PCs join the domain the same way as in Pineville (Settings
→ System → Domain or workgroup), over the tunnel; the first join needs the
tunnel up. People who move between the Hub and Pineville keep one account and
one home folder either way.

## What runs where

| Thing | Pineville | Alexandria | Hub |
|---|---|---|---|
| domain controller, DNS, Kerberos | **the server** | (a second DC, later, optional) | — |
| home folders, shares | the server / the Synology | cached copies on each Mac | cached copies on each laptop |
| the dashboard, `arisectl`, the Terminal | the server | over the VPN | over the VPN |
| the automator, backups | the server | — | — |
| Guacamole | the server | reaches the Alexandria Macs over VNC | reaches the Hub PCs over RDP |
| VPN endpoint | the server (Tailscale node / WireGuard server) | router or Pi (site-to-site) or each Mac | each computer |
| Uptime Kuma monitors | the server | Alexandria's probe host | — |

## DNS at each site

The domain only works when `ad.arisecenla.church` resolves to the domain
controller. At Pineville the router hands out the server as the DNS server
(docs/DIRECTORY.md). Off-site:

- Tailscale: one split-DNS rule in the admin console (restrict
  `ad.arisecenla.church` to the server's address) covers every device.
- WireGuard: the client config carries `DNS = 10.47.0.1`, which is the
  server through the tunnel, so the device uses the DC for everything while
  the tunnel is up.
- Site-to-site at the Alexandria router: set the Alexandria router's DHCP to
  hand out the Pineville server as DNS (with `1.1.1.1` as a second entry for
  when the tunnel is down).

Public names (`arisecenla.church`, `www`) are unaffected: the DC forwards
everything it is not authoritative for to the forwarder in `arise.toml`.

## A second domain controller at Alexandria

Not needed on day one. Add one when Alexandria has more than a handful of
domain Macs and logins there must survive the tunnel being down (a cached
mobile account covers the common case; a second DC covers new users, password
changes and group policy while cut off).

On a small Ubuntu box in Alexandria, with the tunnel up:

```bash
sudo samba-tool domain join ad.arisecenla.church DC -U administrator --dns-backend=SAMBA_INTERNAL
```

Then point Alexandria's DHCP DNS at that box first and Pineville second.

The caveat: **Samba replicates the directory but not sysvol** (the folder
that carries group policy and logon scripts). Two DCs mean sysvol has to be
synced by hand or with a scheduled `rsync` from Pineville to Alexandria
(`/var/lib/samba/sysvol`), and only edited on the Pineville side. If you are
not using group policy, this costs nothing; if you are, it is a job to set
up and the Samba wiki page "Rsync based SysVol replication workaround" is the
reference.

## The Campuses app

Dashboard → Campuses. One card per site: name, kind, address, service times,
the probe's reply time (green under 100 ms, amber above, red when it does not
answer, grey when no probe is set), the VPN mode (local / site-to-site /
clients), and the domain computers whose address sits in that site's subnet.
`arisectl sites` prints the same table. The data is the `[[sites]]` blocks in
`arise.toml`; edit them there (address, probe host, service times) and restart
`arise-web`.
