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

## Addressing without changing routers

The installer now retains DHCP by default. Copying the leased address into a
static netplan file does not reserve it: when the lease expires the DHCP server
can allocate it elsewhere. No script can promise a permanent LAN address while
ignoring that allocation policy. `arisectl doctor` compares the configured and
local addresses; it does not detect duplicate hosts on the wire.

`--pin-ip` is only for an address already verified outside the existing DHCP
pool or otherwise reserved by the existing network policy. It is not a request
to change a router. If no such address is available, keep DHCP and validate a
stable client endpoint/address-change procedure before making this the live DC.
Tailscale gives enrolled devices stable overlay endpoints; LAN DNS, Samba
registration, firewall scopes and client resolvers still need a tested plan.

Record each site's actual subnet from its devices. Overlapping local subnets
can make advertised LAN routes ambiguous; use tested direct Tailscale endpoints
where appropriate rather than prescribing router renumbering. Examples such as
192.168.1.0/24 in configuration are not measurements of the church network.

---

## The Pineville network as it is, kept as it is (Bradly, Oct 28)

Facts from round 7 (127, 128, 134):

| What | Answer |
|---|---|
| Pineville's internet | Optimum Business, the highest plan |
| Where the Synology is plugged in | the Netgear Nighthawk, **router A** (the server's own network, so it mounts directly; no Tailscale package needed on it) |
| Alexandria | one church Mac (enrolled like any other; it reaches the server over Tailscale) |

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
Netgear B or the Mesh can normally talk *upstream* through its router's NAT, subject to guest isolation and non-overlapping address ranges.
Everything the directory, the shares, the dashboard and the Mac agents do
is started by the client, so it all works from the office and from the
Mesh. **Bradly's rule: no router, switch or Mesh setting changes, at all.**
So every setting lives on the server or on the Mac, never on a router:

| Instead of | On the server or the Mac |
|---|---|
| a DHCP reservation on Netgear A | **DHCP stays active by default.** An optional static address must already be known safe under the existing allocation policy; see Addressing above. Neither pinning a lease nor doctor guarantees that another device will not receive that address |
| the routers handing out the server as DNS | each church Mac gets a **per-domain resolver file**, `/etc/resolver/ad.arisecenla.com`, written by `mac/bind-mac.sh --dns <server ip>` (and by `enroll-mac.sh --dns`). Only names in the church domain are asked of the server; everything else keeps the router's DNS. Nothing on the Mesh or the Netgears knows the server exists |
| any route or port forward | **Tailscale**, which works from behind any number of routers with nothing opened. The subnet route is approved in the Tailscale admin console, not on a router |
| reaching the media Mac through the Mesh's NAT | the media Mac runs the **Tailscale app**; Guacamole and anything else use its Tailscale address |
| moving the Synology onto the switch | if it is on Netgear A's network, nothing to do. If it is behind the Mesh or Netgear B, install the **Tailscale package on the Synology** (it is in DSM's Package Center) and the server mounts it by its Tailscale address. No cable moves |

Second DNS option, for any Mac on Tailscale: the Tailscale admin console's
split DNS rule (docs/REMOTE-ACCESS.md step 5) sends `ad.arisecenla.com`
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

**Why Router A's own page does not show them.** A consumer router's
"attached devices" page lists what it handed an address to and still
remembers. A device with a fixed address, one that got its address from
Netgear B or the Mesh, or one the router has forgotten, is simply not on
the page even though it is on the wire. The ARP scan asks the wire itself,
so it finds everything that answers on Netgear A's network, whatever
address it has and whoever gave it.

**Seeing what the ARP scan cannot: the tools, all open source, all on the
server, none of them changing a router.**

| Tool | What it adds | Where |
|---|---|---|
| `arp-scan` | the hourly list of everything on Netgear A's wire | built into the Network app and `arisectl devices scan` |
| `nmap` | the same sweep a different way, plus `nmap -sn` / `nmap -O <ip>` by hand to guess what an unknown device is | installed; the Network app falls back to it if arp-scan is missing |
| the **Netgear attached-devices API** (`pynetgear`) | what the office Netgear *itself* says is attached, behind its NAT, read with its admin password. The office Mac and the printer at 10.0.0.x appear this way | `[[routers]]` in arise.toml; Network app § Behind the other routers; `arisectl devices behind` |
| **NetAlertX** (Docker template) | a presence timeline per device and an alert the moment something new appears on the wire | Apps → Templates → netalertx, port 20211 |
| **Uptime Kuma** (template) | "is it up" pings for the devices that matter: the Synology, the printer, the routers | already in the templates |
| `snmpwalk` + **LibreNMS** | only if the switch turns out to be managed: SNMP shows which MAC is on which port, and LibreNMS graphs it. An unmanaged switch has no SNMP, so this waits for the sticker | not installed until the switch is known |

**What no tool can do, said plainly:** list the Google Mesh's clients
from the server. Google offers no local device-list API; the Mesh's
clients are in the Google Home app on your phone, and that stays the way to
see them. The Mesh shows on the wire as one device.

**The security cameras on the switch (PoE, not working, invisible to
Router A).** Three causes, in the order to check them, and the server
tests two of them:

1. **No power.** A PoE camera draws its power from the switch port. A
   switch that is not a PoE switch (most unmanaged ones are not) gives it
   nothing, and a camera with no power is invisible to every tool there is.
   Check: the switch's label says PoE or 802.3af/at, and the port LED comes
   on when the camera is plugged in; the camera has its own LED too. No
   PoE: a PoE switch for the cameras (an estimate: $60 to $150 for 8 ports)
   or one PoE injector per camera. That is new hardware next to the
   switch, not a change to any router.
2. **Parked on another address range.** Installers leave cameras on their
   factory address (Hikvision 192.168.0.64, Dahua 192.168.1.108, and so
   on) or on whatever network the NVR they came with used. The camera is
   powered and on the wire but has an address Netgear A's network cannot
   reach, so the router never lists it. The Network app's **Wide scan**
   ARPs the common ranges and marks such devices *stray*, and **Find
   cameras** (ONVIF discovery, which ignores addresses) lists every powered
   ONVIF camera with a *reachable / not from this network* flag. The fix is
   on the camera: from a laptop temporarily set to the camera's range, open
   the camera's web page and give it an address in Netgear A's network
   (DHCP is fine; the Network app then names it by MAC). Still nothing on
   any router.
3. **They belong to an NVR.** Cameras that came with a recorder are often
   plugged into the recorder's own PoE ports, on the recorder's private
   network, and are meant to be seen only through it. Then the recorder is
   the device on the switch, not the cameras.

Once a camera is powered and reachable, **Frigate** (Apps → Templates)
records it to the Synology, shows live views in a browser, and detects
people and cars; `arisectl devices cameras` and `nmap -p 554 <ip>` are the
by-hand checks.

**The NDI cameras** sit on their own unmanaged switch, which plugs into the
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
and the switch. The helper pauses Nextcloud during a service once live management is enabled.
Verify that pause on the actual media Mac. Legacy sync and other applications
need their own measured limits; do not assume a sync is always small.
Nothing on the server side touches the stream: the server's own big jobs
(03:00 backup, 04:00 mirror) run at night.

**Tailscale** from the server advertises only Netgear A's subnet. Devices
behind B and the Mesh are not reachable from Alexandria or home by their
LAN address, which is fine: nothing needs to reach them, they reach the
server. Alexandria's Mac and the personal Macs reach the server over
Tailscale regardless of where they are.

**Still needed:** measure the existing addressing and reachability without
changing the routers. The installer reads its current lease and subnet;
`arisectl info` prints them. A lease does not reveal the DHCP allocation pool
or guarantee a permanent address. Before an explicit static pin, verify the
address is outside that pool and unused, or covered by an existing reservation.
Check the Hub's actual addressing before planning routes between the sites.

## Validate the existing network

The server sits on Netgear A's wire. Do not change the routers, switches, Mesh,
streaming Mac connection or VLAN configuration. From one device behind each
router, verify the intended server address resolves, DNS SRV queries answer,
and an authenticated SMB/Nextcloud operation succeeds. An ARP scan on A cannot
inventory devices behind the other NATs. Guest-network isolation must be
measured; a network name alone does not prove isolation.

The host firewall must allow the intended LAN and Tailscale clients and deny
unneeded access. Docker published ports require their own effective firewall
checks because they can bypass UFW input rules; the installer supplies a
DOCKER-USER policy. Check IPv4 and any enabled IPv6 separately. The AD services
include TCP/UDP 53 and 88, TCP 135/139/445/636/3268/3269, UDP 137/138, TCP/UDP 389
and 464 and dynamic RPC TCP 49152–65535. UDP 123 requires an actual configured
time service, not only a firewall allowance.

## DNS and time

For church Macs, the enrollment script writes `/etc/resolver/ad.arisecenla.com`
pointing at the validated server endpoint. Other names continue to use the
Mac's normal resolvers; the optional DNS filter is a separate setting. For
Windows, the join script uses an NRPT rule for the same domain. For Tailscale
clients, configure and test split DNS for that domain using an endpoint those
clients can reach. Approve advertised subnet routes in Tailscale when used.

A second public/router DNS server is not an AD failover resolver: it does not
know the private AD zone. Use another authoritative DC/resolver or scoped DNS
when that capability is needed. On Macs, `dig` does not exercise the scoped
system resolver; test the system resolver and directed SRV queries separately.

The DC must answer its LDAP/Kerberos SRV records and forward external names;
Docker containers that use AD also need verified DNS and LDAPS trust. Confirm
Samba owns its intended port 53 bindings and systemd-resolved does not compete.
All clients need accurate clocks. This installer installs chrony for the
server's own clock; it does not configure a DC NTP service for clients or
Samba-signed time. Keep server and clients independently synchronized with
their working time sources and verify their offsets before testing domain
sign-in. Do not point clients at the DC for NTP until a separately configured
service has passed actual client checks.

## Alexandria and remote laptops

Alexandria's Mac and authorized remote laptops use Tailscale directly; no route
box or router edit is part of the current setup. Enable the required routes and
split DNS in Tailscale, and verify DNS, sign-in and a file transfer from outside
the building. A local subnet overlapping an advertised church subnet is a test
case, not a reason to silently change either router.

Shared church login and device removal are owner decisions. Protect that login
and recovery access, check current Tailscale plan terms, and revoke departing
devices in its console. The shared login does not provide individual identity.
The livestream keeps its normal internet route; do not select a VPN exit node.
An approved split tunnel to the server is different from sending the stream
through a full tunnel.

Church Macs use AD binding plus the helper and Nextcloud; existing linked local
accounts retain their local login. Personal Macs are never enrolled or bound.
The client sync supplies offline local files. Legacy Desktop/Documents symlinks
to an SMB mount have no offline-cache guarantee and must not be combined with
Nextcloud for the same folders.

## Future sites and recovery

A move requires a measured new address, DNS records, client resolver/route
updates, NAS reachability and a tested rollback. Stable Tailscale identity does
not automatically update an old LAN address embedded in netplan or client
configuration. Follow the current no-router-change rule when evaluating any
older moving-day proposal. Multi-node automatic takeover is not implemented;
see docs/NODES.md for why a timeout alone cannot safely fence the old writer.
