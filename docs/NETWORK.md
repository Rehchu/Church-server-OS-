# The network plan — three sites, one server, a Cisco switch

What the wires need to look like for the directory, the shares, the
dashboard and the VPN to work at Pineville, at Alexandria and at the Hub.
Bradly's answers are in docs/ANSWERS.md. What is known: Pineville has
several routers, each its own network; a separate router (not the ISP box)
hands out addresses; the Cisco is probably unmanaged; the guest Wi-Fi is
already separate; upload is over 50 Mbit/s; the public address is dynamic
and nothing will be forwarded; Alexandria is one Mac; the livestream is
StreamYard with NDI sources. The Pineville wiring (modem → Netgear A → switch → Netgear B, with a
Google Mesh off Netgear A) is in § The Pineville network as it is; Bradly
keeps it as it is. Still needed: a photo of each router's LAN page. Where
a number is a proposal it says so.

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
| Pineville, the staff network | `192.168.10.0/24` | `.1` | the server `.10`, the Synology `.11` | `.100`–`.199` | the server is static; the Synology is static. Pineville's other routers keep their own subnets, which must not clash with these either |
| Alexandria | `192.168.20.0/24` | `.1` | nothing: the one Mac runs Tailscale itself | `.100`–`.199` | only matters if a route box is ever added |
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

## The Pineville network as it is, kept as it is (Bradly, Oct 28)

What is there (his words, drawn out):

```
 internet ── modem ── Netgear A ──┬── unmanaged switch (Cisco or Netgear) ──┬── Netgear B (office)  → office Mac, wired
                                  │                                        └── whatever else is on the wire (the Network app lists it)
                                  └── Google Mesh (2 or 3 points) ──┬── the media / streaming Mac (Wi-Fi)
                                                                   └── a second unmanaged switch → the NDI cameras
```

Three boxes each hand out their own addresses, so this is three networks
stacked: Netgear B and the Mesh each sit *behind* Netgear A (double NAT).
A Mesh with more than one point cannot be put in bridge mode, so the
stack cannot be collapsed without re-wiring. **Bradly's decision: leave it
exactly as it is.** The plan below works with that, and says plainly what
cannot work across the stack.

**Where the server goes: wired into the switch, on Netgear A's network.**
That is the one network every other box can reach, because a device behind
Netgear B or the Mesh can always talk *upstream* through its router's NAT.
Everything the directory, the shares, the dashboard and the Mac agents do
is started by the client, so it all works from the office and from the
Mesh. **Bradly's rule: no router, switch or Mesh setting changes, at all.**
So every setting lives on the server or on the Mac, never on a router:

| Instead of | On the server or the Mac |
|---|---|
| a DHCP reservation on Netgear A | **nothing to choose**: the installer keeps the address Netgear A already handed the box and pins it in netplan on the server (INSTALL.md § 5). No router setting, no new IP, no existing device touched. The router still thinks it is an ordinary lease; `arisectl doctor` watches for the rare clash |
| the routers handing out the server as DNS | each church Mac gets a **per-domain resolver file**, `/etc/resolver/ad.arisecenla.church`, written by `mac/bind-mac.sh --dns <server ip>` (and by `enroll-mac.sh --dns`). Only names in the church domain are asked of the server; everything else keeps the router's DNS. Nothing on the Mesh or the Netgears knows the server exists |
| any route or port forward | **Tailscale**, which works from behind any number of routers with nothing opened. The subnet route is approved in the Tailscale admin console, not on a router |
| reaching the media Mac through the Mesh's NAT | the media Mac runs the **Tailscale app**; Guacamole and anything else use its Tailscale address |
| moving the Synology onto the switch | if it is on Netgear A's network, nothing to do. If it is behind the Mesh or Netgear B, install the **Tailscale package on the Synology** (it is in DSM's Package Center) and the server mounts it by its Tailscale address. No cable moves |

Second DNS option, for any Mac on Tailscale: the Tailscale admin console's
split DNS rule (docs/REMOTE-ACCESS.md step 5) sends `ad.arisecenla.church`
to the server for every device on the tailnet, wherever it is. The resolver
file covers Macs without Tailscale; the two do not conflict.

**Seeing everything on the switch.** The dashboard's **Network** app (16)
scans Netgear A's wire every hour (`arp-scan`, the same thing a network
engineer runs by hand) and lists every device: address, MAC, maker, a
guessed kind (Mac, NAS, printer, router, camera), whether it is joined to
the domain, when it was first and last seen. Name a device once and the
name follows its MAC through every address the router hands it. New
devices are flagged. What it cannot see, honestly: anything *behind* the
office Netgear or the Google Mesh. Each of those shows as one device (its
WAN side); the office Mac, the media Mac and the cameras' switch are on
their own networks on the far side of a NAT, invisible from this wire by
design. Those devices are known to the server another way: they join the
domain (Directory → Computers) or run Tailscale (Remote).

**The cameras** sit on their own unmanaged switch, which plugs into the
Mesh. So the NDI cameras and the streaming Mac are on the Mesh's network
together, which is the one thing NDI needs (discovery works between them).
The server is on a different network, which does not matter: nothing on
the server talks NDI.

**What works across the stack and what does not:**

| Works from the office and the Mesh | Does not work across the NAT |
|---|---|
| joining the domain, logging in, Kerberos, the home share, every share, the dashboard, share links, the home-sync agent, Tailscale | the server opening a connection *to* a Mac behind B or the Mesh: Guacamole remote desktop, `arisectl` pinging a computer, Wake-on-LAN |
| Spotlight, Sermons, Bible, uploads | Bonjour across networks: AirPrint, Screen Sharing discovery, NDI *discovery* between a camera on the switch and the Mac on the Mesh (an NDI source can still be added by its address by hand) |

So two of Bradly's answers get a workaround, not a change of mind:

- **Remote desktop into the media Mac** (answer 44): the media Mac runs the
  Tailscale app. Guacamole then connects to the Mac's Tailscale address
  (`100.x.y.z`), which does not care about the NAT in between. Same for
  any other Mac you ever need to reach from the server's side.
- **The Synology**: on Netgear A's network the server mounts it directly;
  behind the Mesh or Netgear B it runs the Tailscale package and is mounted
  by its Tailscale address. Either way no cable moves. Question 6 on Sunday
  says which.

**The livestream** (answer 50, and "leave it like it is set up"): the
streaming Mac stays on the Mesh Wi-Fi, cameras stay split across the Mesh
and the switch. The home-sync agent on that Mac runs every 15 minutes;
during a service it is a few megabytes at most, but if a frame ever drops
at 10:30 on a Sunday, the first thing to try is pausing the agent on that
Mac (`launchctl unload` the homesync plist) and the second is a cable.
Nothing on the server side touches the stream: the server's own big jobs
(03:00 backup, 04:00 mirror) run at night.

**Tailscale** from the server advertises only Netgear A's subnet. Devices
behind B and the Mesh are not reachable from Alexandria or home by their
LAN address, which is fine: nothing needs to reach them, they reach the
server. Alexandria's Mac and the personal Macs reach the server over
Tailscale regardless of where they are.

**Still needed:** nothing from the routers for day 1. The installer
reads the box's own address and subnet, and `arisectl info` prints them, so
`[[sites]] subnet` is filled from the server, not from a router page. The
Hub's subnet is chosen when the Hub's router exists; it only has to differ
from Pineville's, which the server will have told us by then.

## VLANs: later, not day 1

"Multiple networks that all run through a Cisco switch" was the first
reading. The answers say otherwise: the Cisco is probably **unmanaged**
(answer 11), and an unmanaged switch has no VLANs. The separate networks are
separate routers (answer 12). So day 1 is a **flat network** behind the
staff router: the server, the Synology, the staff Macs and the media
network on it; the guest Wi-Fi already on its own network (answer 17). That
works, and it is what most churches run.

VLANs come later, in one of two ways: the staff router does them itself if
it is one that can (UniFi, OPNsense, MikroTik and most business routers can;
ISP boxes cannot), or a managed gigabit switch replaces the Cisco (an
estimate: a 24-port managed gigabit switch is $150 to $300). The photo of
the Cisco sticker (answer 10) settles whether it is managed after all. When
VLANs arrive, this is the layout to build toward:

| VLAN | Name | What is on it | May reach the server? |
|---|---|---|---|
| 10 | **Staff** | the office Macs and PCs, the server, the Synology, printers | yes, everything |
| 20 | **Media** | the streaming Mac, StreamYard, Proclaim, the sound desk computer, cameras that feed the stream | yes, everything |
| 30 | **Kids check-in** | the check-in station or iPad, its label printer | the server on 445 and 53 only, and the dashboard |
| 40 | **Guest Wi-Fi** | visitors' phones | **no**, nothing; internet only |
| 50 | **IoT / building** | thermostats, door controllers, security cameras that record to their own box | **no** |
| 99 | **Management** | the switch's own admin page, the access points' controller | admins only; the server need not be on it |

Three things decide how much of this a switch can do by itself (the Cisco
sticker, answer 10):

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

### NDI, the livestream and the switch

The Sunday stream is StreamYard with the OBS virtual camera, NDI lower
thirds from the media Mac running Proclaim, and NDI cameras (answer 50).
NDI is the heaviest thing on the church network and the rule for it is
simple:

- Every NDI device (the cameras, the Proclaim Mac, the streaming Mac) sits
  on **one gigabit wired segment**. Never Wi-Fi. Typical figures, not
  measured here: a full-bandwidth NDI source is 100 to 200 Mbit/s each; NDI
  HX is a fraction of that. Three full sources on one gigabit switch is
  fine; on Wi-Fi it is not.
- NDI finds its sources by mDNS, which does not cross VLANs or routers. So
  the streaming Mac and every NDI source stay on the same network, with no
  VLAN between them, whatever else gets split off later.
- The server may share that switch. An unmanaged gigabit switch copes; the
  server's own traffic is small. The one rule: the 03:00 backup and the
  04:00 mirror never run during a service, and no large copy to the server
  from the streaming Mac during the stream.
- No VPN profile of any kind on the streaming Mac. StreamYard and YouTube
  are reached over the building's own internet (over 50 Mbit/s up, answer
  15), never through a tunnel.

When VLANs come, the media VLAN is "everything NDI plus the streaming Mac,"
and the server is reachable from it on the ports in the table below.

### Firewall between VLANs and the server

What each VLAN must be allowed to send to the server's address, once VLANs
exist. This is the rule table for the router or the L3 switch; the server's
own `ufw` (written by `install.sh`) allows the same set from the LAN subnet
and the VPN ranges and nothing else. On the day-1 flat network the `ufw`
rules are the only firewall, and the guest network is already elsewhere.

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
| 443 | TCP | the dashboard over HTTPS via Caddy (inside only, nothing forwarded from the internet, answer 36); Vaultwarden; Guacamole | yes | yes | no | no | no |
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
| The staff network at the site where the server is (and the Media and Kids VLANs, once they exist) | the server (`192.168.10.10` in the plan), **only** that one | the staff router's DHCP DNS option (answer 14) |
| Guest, IoT | the router or `1.1.1.1`; they must not reach the server anyway | DHCP on those VLANs |
| Any device on Tailscale, anywhere | its normal DNS for everything, **the server for `ad.arisecenla.church`** | Tailscale admin → DNS → split DNS: nameserver `192.168.10.10`, restricted to `ad.arisecenla.church` (docs/REMOTE-ACCESS.md § (b)) |
| A whole remote site behind a route box (Pineville after the move, if that is the choice) | the server for `ad.arisecenla.church` | the site router's DHCP hands out the server as DNS, with the router itself second for when the tunnel is down; the server forwards everything else to `1.1.1.1` |
| WireGuard clients | the server through the tunnel | `DNS = 10.47.0.1` in the client config |

The server forwards everything that is not the realm to the forwarder in
`arise.toml` (`1.1.1.1` by default), so devices using it still reach the
internet. docs/DIRECTORY.md § DNS has the two `dig` checks; run them from
every site.

Public names (`arisecenla.church`, `www`) are untouched by any of this.

---

## A church across town: how Alexandria connects

Alexandria is one Mac, there is no place there for an always-on box, and
nobody streams from there (answers 19, 21, 22). So Alexandria is **option
A**: Tailscale on that Mac. The other two ways stay here for Pineville after
the server moves to the Hub, and for the day Alexandria grows.

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

**What Bradly chose:** A, with one shared church Google login on every
device (answer 42), for Alexandria's Mac, the personal Macs and every
laptop; everyone with an account may use it from home (answer 43). B is the
open question for Pineville after the move (docs/MOVING-DAY.md). C is not
used.

The recipe for Alexandria's Mac, in order:

1. Tailscale console: the split-DNS rule, nameserver = the server's LAN
   address, restricted to `ad.arisecenla.church` (docs/REMOTE-ACCESS.md § (b)).
   Done once, for every device.
2. On the Mac: install Tailscale, sign in with the church login, set it to
   start at login.
3. `ping arise-server`, then the two `dig` lines from docs/DIRECTORY.md
   § DNS. Both must answer through the tunnel.
4. `mac/enroll-mac.sh` on it, exactly as at Pineville (docs/MAC-MIGRATION.md).
5. `arise.toml`: `[[sites]] alexandria` with the Mac's Tailscale name as
   `probe`. Campuses shows it green while the Mac is on.

If Tailscale on that Mac is signed out, that Mac is off the church network
until someone signs it in; a mobile account still logs in and works
locally. That is the whole cost of A for a one-Mac site.

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
  that building share it. Pineville is over 50 Mbit/s (answer 15);
  Alexandria is not measured yet (answer 20).
- Whether the public address is static or changes. Tailscale does not care;
  WireGuard and a public dashboard door do.
- Whether the modem is also the router, and whether it can be put in
  bridge mode so your own router does the routing. ISP boxes rarely do
  VLANs, static routes or WireGuard.
- Whether inbound port forwarding is allowed at all (some fibre and all
  CGNAT-style connections block it). Again, Tailscale does not care, and
  nothing is forwarded in this plan (answer 36).

---

## The picture

```
            INTERNET
   ┌────────────────┼───────────────────────────┐
   │                │                           │
 Pineville        Alexandria                  The Hub (later)
 several routers  router .1                   router .1
 ┌─ guest router ── guest Wi-Fi (already separate; no path to the server)
 ├─ other routers ── (their own networks; photos to come)
 └─ STAFF ROUTER .1 ── hands out addresses, DNS = the server
      │               │                           │
   Cisco (unmanaged,  the one Mac ── Tailscale   switch
   gigabit)           (no route box)             ├─ (the server .10, after the move)
   ├─ THE SERVER .10 ── the Synology .11          └─ laptops (Tailscale)
   ├─ staff Macs
   └─ NDI segment: cameras, Proclaim Mac, streaming Mac (wired, same switch, no VLAN between them)
                        │
                        └── Tailscale ───── every laptop, the personal Macs,
                            Alexandria's Mac, anywhere (100.x addresses;
                            the server advertises 192.168.10.0/24)
```

Every arrow to the server is a tunnel the device holds a key for, or a wire
on the staff router's network. Nothing on the church routers is forwarded
from the internet (answer 36). VLANs, when they come, split the staff
switch into the table above without changing any of this. The move to the
Hub (docs/MOVING-DAY.md) swaps which building has the server on its switch;
the Tailscale addresses, the split DNS rule and every laptop's setup stay as
they are.
