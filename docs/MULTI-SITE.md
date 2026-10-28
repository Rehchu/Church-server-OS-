# Three sites, one server

The network plan (subnets, VLANs, the Cisco, how Alexandria connects) is
**docs/NETWORK.md**; the setup order is **docs/SETUP-GUIDE.md**; the day the
server moves from Pineville to the Hub is **docs/MOVING-DAY.md**. This page
is what each site is and what runs where.

| Site | What it is | What is there | How it reaches the server |
|---|---|---|---|
| **Arise Church Pineville** (`pineville`, kind `main`) | the main campus, 501 Ates Road | the server, the domain controller, the Synology, the media Mac (Proclaim, NDI), the staff Macs, behind the staff router (**for now**: the server moves to the Hub once it is built, docs/MOVING-DAY.md). Several routers, each its own network; the subnet is still to be photographed (docs/ANSWERS.md 12) | it is the LAN |
| **Arise Church Alexandria** (`alexandria`, kind `campus`) | the second campus | one Mac (answer 19), a router | Tailscale on that Mac (answers 19 and 21) |
| **The Apostolic Hub** (`hub`, kind `office`) | office and leadership, being built | laptops, people who move between sites; **later, the server** | Tailscale, one client per computer, until the server moves there |

Each site is a `[[sites]]` block in `arise.toml` (id, name, kind, address,
subnet, probe, services, note). The dashboard's **Campuses** app pings each
site's `probe` host and lists the domain computers whose address falls in
that site's subnet. Pick as the probe the one device at that site that is
always on: the router, or the Mac at the sound desk. Leave it blank and the
site just shows as "not monitored".

## Pineville: the main site (for now)

Everything that is a single copy of something lives here until the move: the directory
(`samba-ad-dc`), the home folders or the Synology that holds them, the
automator and its token, the backups. The server's LAN address should be
**fixed** (a DHCP reservation on the router, or a static address; see
INSTALL.md § Fixed address), because the other sites' DNS points at it.

## Alexandria: a campus with one Mac

Alexandria is one Mac today (answer 19), nobody streams from there (answer
22), and there is no place for an always-on box (answer 21). So that Mac is
its own tunnel, and that is the whole Alexandria setup:

- **Always-on VPN on the Mac.** Tailscale installed, signed in with the
  church login, set to start at login. The Mac binds to
  `AD.ARISECENLA.CHURCH` over the tunnel (the split-DNS rule in
  docs/REMOTE-ACCESS.md is what makes the realm resolve). Nothing to do at
  the Alexandria router. If its Tailscale is signed out, that Mac is off
  the church network until someone signs it in; the mobile account still
  logs in. docs/NETWORK.md § A church across town has the steps.
- **A site-to-site tunnel at the router**, for the day Alexandria has more
  than one device. WireGuard on the Alexandria
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

## The Apostolic Hub: office clients (until the server moves there)

No site infrastructure yet: each laptop runs Tailscale and signs in with
the church login. There are no Windows PCs (answer 31). A church Mac binds
over the tunnel; the first bind needs the tunnel up. Personal Macs (answer
34) are not bound: Tailscale and the dashboard only. People who move
between the Hub and Pineville keep one account and one home folder either
way.

## What runs where

| Thing | Pineville | Alexandria | Hub |
|---|---|---|---|
| domain controller, DNS, Kerberos | **the server** (until the move) | (a second DC, later, optional) | the server, after the move |
| home folders, shares | the server / the Synology | cached copies on each Mac | cached copies on each laptop |
| the dashboard, `arisectl`, the Terminal | the server | over the VPN | over the VPN |
| the automator, backups | the server | — | — |
| Guacamole | the server; one connection, the media Mac over VNC (answer 44) | — | — |
| VPN endpoint | the server (Tailscale node) | the one Mac | each computer |
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
- Site-to-site at a router (not used today): set that router's DHCP to
  hand out the server as DNS (with `1.1.1.1` as a second entry for when the
  tunnel is down).

Public names (`arisecenla.church`, `www`) are unaffected: the DC forwards
everything it is not authoritative for to the forwarder in `arise.toml`.

## A second domain controller at Alexandria

Superseded on Oct 28 by the node plan (docs/NODES.md): the second domain
controller is **Arise-Home** first, at Bradly's house, and Arise-Alexandria
when a third PC comes. The mechanics below still apply to either.

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
