# The network plan — three sites, one server, a Cisco switch

What the wires need to look like for the directory, the shares, the
dashboard and the VPN to work at Pineville, at Alexandria and at the Hub.
Most of what is here is a proposal until the Cisco model and the current
subnets are known (docs/QUESTIONS.md § The Pineville network). Where a
number is a proposal it says so.

---

## The IP plan

**Rule one: no two sites may use the same subnet.** A VPN joins networks
by routing: "send `192.168.20.0/24` through the tunnel." If Alexandria and
Pineville both use `192.168.1.0/24`, a Mac in Alexandria looking for
`192.168.1.10` finds its own router first and never reaches the server. The
tunnel is up, the pings fail, and the fault is invisible. Most home and
church routers default to `192.168.0.0/24` or `192.168.1.0/24`, so the odds
of a clash are high. Change the subnets once, before the VPN, and never
again.

Proposed plan (change the numbers, keep the shape):

| Site | Subnet | Router | Server / route box | DHCP range | Notes |
|---|---|---|---|---|---|
| Pineville | `192.168.10.0/24` | `.1` | the server `.10`, the Synology `.11` | `.100`–`.199` | the server is static; the Synology is static |
| Alexandria | `192.168.20.0/24` | `.1` | the Tailscale route box `.10` | `.100`–`.199` | |
| The Hub | `192.168.30.0/24` | `.1` | the server `.10` after the move | `.100`–`.199` | pick it now so the move is a config edit |
| VPN, WireGuard | `10.47.0.0/24` | the server `10.47.0.1` | | | only if WireGuard is used instead of Tailscale |
| VPN, Tailscale | `100.64.0.0/10` | assigned by Tailscale | | | every device gets one `100.x.y.z` for life |

The current Pineville subnet is `192.168.1.0/24` in `arise.toml.example`
and in several docs because that was the guess. If it really is `.1`, the
cheapest move is to leave Pineville on `.1` and give the other two sites
`.20` and `.30`. Renumbering Pineville is more work than renumbering an
empty Hub. Either way, `[[sites]] subnet` in `arise.toml` and
`--advertise-routes` on the route boxes must match whatever is true.

Static addresses, in this order of preference: a **DHCP reservation** on
whatever hands out addresses (the server keeps its MAC-based lease for
ever, and the router page is the one place to look), or a static address
in netplan on the server (INSTALL.md § Fixed address). The server and the
Synology both get one. Nothing else needs one.

---

## VLANs on the Cisco

"Multiple networks that all run through a Cisco switch" is VLANs: one
physical switch carrying several separate networks, each on its own ports
or Wi-Fi name. Which VLANs exist and whether the Cisco routes between them
is the information I need from you this week. Until then, a sensible layout
for a church of this size:

| VLAN | Name | What is on it | May reach the server? |
|---|---|---|---|
| 10 | **Staff** | the office Macs and PCs, the server, the Synology, printers | yes, everything |
| 20 | **Media** | the streaming Mac, StreamYard, Proclaim, the sound desk computer, cameras that feed the stream | yes, everything |
| 30 | **Kids check-in** | the check-in station or iPad, its label printer | the server on 445 and 53 only, and the dashboard |
| 40 | **Guest Wi-Fi** | visitors' phones | **no**, nothing; internet only |
| 50 | **IoT / building** | thermostats, door controllers, security cameras that record to their own box | **no** |
| 99 | **Management** | the switch's own admin page, the access points' controller | admins only; the server need not be on it |

Three things decide how much of this the Cisco can do by itself (question
10, the exact model):

- **A layer-2 switch** (most "Cisco Business" and all unmanaged ones)
  carries VLANs but cannot route between them. Then the **router** does the
  routing and the firewall rules, and every VLAN needs a trunk port to it.
  The server sits on one VLAN, and the router decides who may cross.
- **A layer-3 switch** (Catalyst and the bigger Cisco Business models)
  routes between VLANs itself, fast, and its access lists are the firewall
  between them. The router then only sees "the inside."
- **No VLANs at all**, one flat network, everything on `.1`: it works, and
  it is what most churches have. The server is reachable by the guest Wi-Fi
  then, which is the one thing to fix first (put the guest Wi-Fi on its own
  VLAN, or on the router's "guest network" feature, which is the same
  thing).

**The server's port** on the switch is an access port in the Staff VLAN. It
does not need a trunk. If the staff VLAN and the media VLAN both need the
server, the router (or the L3 switch) routes between them; the server
itself does not care.

### Firewall between VLANs and the server

What each VLAN must be allowed to send to the server's address. This is the
rule table for the router or the L3 switch; the server's own `ufw` (written
by `install.sh`) allows the same set from the LAN subnet and the VPN ranges
and nothing else.

| Port | Protocol | What | Staff | Media | Kids | Guest | IoT |
|---|---|---|---|---|---|---|---|
| 53 | TCP+UDP | DNS (the domain controller; every domain member needs it) | yes | yes | yes | no | no |
| 88 | TCP+UDP | Kerberos (logins) | yes | yes | yes | no | no |
| 123 | UDP | time (the DC is the time source for members) | yes | yes | yes | no | no |
| 135, 137–139 | TCP/UDP | RPC and NetBIOS (Windows joins, old SMB discovery) | yes | yes | yes | no | no |
| 389, 636 | TCP+UDP | LDAP, LDAPS (the directory) | yes | yes | yes | no | no |
| 445 | TCP | SMB (home folders and shares) | yes | yes | yes | no | no |
| 464 | TCP+UDP | Kerberos password change | yes | yes | no | no | no |
| 3268, 3269 | TCP | global catalog (AD lookups) | yes | yes | no | no | no |
| 4147 | TCP | the dashboard | yes | yes | yes | no | no |
| 443 | TCP | the dashboard over HTTPS via Caddy; Vaultwarden; Guacamole | yes | yes | no | no | no |
| 22 | TCP | SSH | admins' machines only | no | no | no | no |
| 8084 | TCP | Guacamole direct (prefer 443) | admins only | no | no | no | no |
| 3389, 5900 | TCP | RDP and VNC: **not to the server**. Guacamole on the server reaches *other* computers on these ports; they stay closed inbound to the server | | | | | |
| 51820 | UDP | WireGuard, **from the internet**, only if WireGuard is chosen instead of Tailscale | | | | | |

Guest and IoT get **nothing** toward the server, and nothing toward the
staff VLAN at all. Internet only. That one line is most of the security of
the whole building.

Tailscale needs no inbound rule anywhere: the server and the route boxes
make outbound connections and the tunnel comes up through them. If the
Cisco or the router blocks outbound UDP 41641, Tailscale falls back to a
relay and still works, slower.

---

## DNS, the part that decides whether AD works

A domain member finds its domain controller by asking DNS for
`_ldap._tcp.ad.arisecenla.church`. Only the server's DNS knows that
answer. So:

| Who | DNS server to use | How it gets it |
|---|---|---|
| Staff, Media, Kids VLANs at the site where the server is | the server (`192.168.10.10` in the plan), **only** that one | the DHCP server's DNS option for those VLANs |
| Guest, IoT | the router or `1.1.1.1`; they must not reach the server anyway | DHCP on those VLANs |
| Any device on Tailscale, anywhere | its normal DNS for everything, **the server for `ad.arisecenla.church`** | Tailscale admin → DNS → split DNS: nameserver `192.168.10.10`, restricted to `ad.arisecenla.church` (docs/REMOTE-ACCESS.md § (b)) |
| A whole remote site behind a route box | the server for `ad.arisecenla.church` | the site router's DHCP hands out the server as DNS, with the router itself second for when the tunnel is down; the server forwards everything else to `1.1.1.1` |
| WireGuard clients | the server through the tunnel | `DNS = 10.47.0.1` in the client config |

The server forwards everything that is not the realm to the forwarder in
`arise.toml` (`1.1.1.1` by default), so devices using it still reach the
internet. docs/DIRECTORY.md § DNS has the two `dig` checks; run them from
every site.

Public names (`arisecenla.church`, `www`) are untouched by any of this.

---

## A church across town: how Alexandria connects

Three ways. They are not exclusive.

**A. Tailscale on every device.** Install the app on each Mac and laptop,
sign in with the church's Tailscale login, set it to start at login. Each
device is its own tunnel to the server. Nothing to buy, nothing at the
Alexandria router. Cost: free (the Personal plan: one login, up to 100
devices; read the plan page before adding a second login). Weakness: a Mac
whose Tailscale is signed out is off the network and will not bind, and
printers, the check-in iPad and anything you cannot install an app on are
left out.

**B. One route box per site.** A Raspberry Pi 4 or a $100-class mini PC at
Alexandria, plugged into the staff VLAN, running
`tailscale up --advertise-routes=192.168.20.0/24` (and the server
advertising `192.168.10.0/24`). Approve both routes in the Tailscale
console. Now every device at Alexandria reaches the server by its LAN
address with nothing installed, and Pineville reaches Alexandria's
printers and Macs for Guacamole. The Alexandria router needs one static
route: `192.168.10.0/24 via 192.168.20.10` (the Pi). If the router cannot
take a static route, the Pi can instead be the DHCP server's default
gateway for the staff VLAN, or run as the site's DHCP server. Cost: the box
(estimate: $60 to $150), half a day the first time. Weakness: one box to
keep running; put it on the UPS.

**C. The site router's own VPN.** If the Alexandria router runs WireGuard
natively (UniFi, OPNsense, pfSense, MikroTik, GL.iNet do; ISP boxes do
not), it can be the WireGuard peer instead of a Pi, with the server as the
other end (docs/REMOTE-ACCESS.md § (b), WireGuard). No extra box. Weakness:
this is the self-hosted path, with the port forward and the public name it
needs; if you went with Tailscale for everything else, mixing the two is
more to understand than it is worth.

**Recommendation:** A for every laptop and phone that moves around, and B
for each fixed site (Alexandria now, Pineville after the server moves to
the Hub). That gives a laptop the church network from anywhere and gives a
building the server with nothing installed.

The same recipe, in order, for Alexandria:

1. Pick Alexandria's subnet (`192.168.20.0/24`), set it on the Alexandria router.
2. The route box on a static address, Tailscale installed, `tailscale up --advertise-routes=192.168.20.0/24 --accept-routes`.
3. Tailscale console: approve the route. Confirm the server advertises its own subnet and that is approved too.
4. Static route on the Alexandria router toward the server's subnet via the box.
5. Alexandria DHCP: DNS = the server's address, second entry the router.
6. From an Alexandria Mac: `ping 192.168.10.10`, then the two `dig` lines. Then bind it.
7. `arise.toml`: `[[sites]] alexandria` gets the real subnet and the box as `probe`. Campuses shows it green.

### The livestream and the tunnel

Do not send the Sunday stream through the VPN. StreamYard, YouTube and
Facebook are reached directly over each site's own internet; the VPN only
carries traffic to the server's subnet. Option B does this by itself
(only the server's subnet is routed through the box). What to avoid is a
full-tunnel VPN profile on the streaming Mac, and copying a service
recording to the server **during** the stream from the same connection.
Upload bandwidth is the scarce thing at both sites; the stream gets it
first.

### What to ask the ISP at each site

- The upload speed, in numbers, on paper. The stream and every sync out of
  that building share it.
- Whether the public address is static or changes. Tailscale does not care;
  WireGuard and a public dashboard door do.
- Whether the modem is also the router, and whether it can be put in
  bridge mode so your own router does the routing. ISP boxes rarely do
  VLANs, static routes or WireGuard.
- Whether inbound port forwarding is allowed at all (some fibre and all
  CGNAT-style connections block it). Again, Tailscale does not care.

---

## The picture

```
            INTERNET
   ┌───────────┼───────────────────────────┐
   │           │                           │
 Pineville   Alexandria                  The Hub (later)
 router .1   router .1                   router .1
   │           │                           │
 Cisco switch  switch                    switch
 ┌──┼──┬──┬──┐ ├─ route box .10 ──────┐    ├─ (the server .10, after the move)
 │  │  │  │  │ ├─ staff Macs          │    ├─ office Macs and PCs
 │  │  │  │  │ └─ check-in, printer   │    └─ laptops (Tailscale)
 │  │  │  │  └ VLAN 40 guest Wi-Fi  (no path to the server)
 │  │  │  └─── VLAN 30 kids check-in (53, 88, 445, 4147 to the server)
 │  │  └────── VLAN 20 media: streaming Mac, Proclaim, sound desk
 │  └───────── VLAN 10 staff: office Macs, PCs, printers
 └──────────── VLAN 10: THE SERVER .10 ── the Synology .11
                        │
                        └── Tailscale ───── every laptop and phone, anywhere
                            (100.x addresses; the route box carries 192.168.20.0/24;
                             the server carries 192.168.10.0/24)
```

Every arrow to the server is a tunnel the device holds a key for, or a VLAN
the Cisco was told may cross. Nothing on the church routers is forwarded
from the internet unless you choose WireGuard (one UDP port) or the public
dashboard door (443). The move to the Hub (docs/MOVING-DAY.md) swaps which
building has the server on its switch and which has a route box; the
Tailscale addresses, the split DNS rule and every laptop's setup stay as
they are.
