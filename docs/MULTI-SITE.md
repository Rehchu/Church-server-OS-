# Three sites, one server

Use `docs/NETWORK.md` for the existing network, `docs/SETUP-GUIDE.md` for
setup order and `docs/MOVING-DAY.md` before moving the server. No router,
switch or Google Mesh settings change at any site. No port forwarding,
router DHCP changes, VLAN redesign or router-based VPN is part of this plan.

| Site | Current role | Access |
|---|---|---|
| **Arise Church Pineville** (`pineville`) | Main campus and current home of the server and Synology | Existing LAN where reachable; Tailscale where NAT prevents access |
| **Arise Church Alexandria** (`alexandria`) | One church Mac | Tailscale on that Mac; no route box required |
| **The Apostolic Hub** (`hub`) | Future office and eventual server location | Tailscale per approved computer; verify the move before changing its role |

Each site is a `[[sites]]` block in `arise.toml`. Subnet and probe entries
are observations, not instructions to change the network. Use a reachable,
approved device as the probe and verify it across the intended path. A ping
or a green site card does not validate AD, SMB or application access.

## Pineville and the server address

The current server provides AD, DNS, home folders, shares, apps and backup
scheduling. The YouTube automator runs on the designated runner until
Bradly deliberately changes that assignment.

The installer now leaves DHCP enabled by default. Converting a DHCP lease
to a static address does not reserve it, and a router reservation is outside
the owner's permitted scope. A production DC still needs a verified stable
endpoint/address strategy. The advanced `--pin-ip` option is appropriate
only after independently confirming the address is outside DHCP allocation.
If a safe static address cannot be established without changing the network,
record that unresolved prerequisite rather than promising collision-free
operation. See `INSTALL.md` and `docs/NETWORK.md`.

## Alexandria and the Hub clients

Install Tailscale on each approved remote client and verify its startup,
authentication and DNS behavior. Church-owned Macs are enrolled and AD-bound
through `docs/MACS.md`; existing local accounts are linked by default and
keep their local passwords. Converted/mobile accounts behave differently
and must be tested individually. Personal Macs are never helper-enrolled
or domain-bound; they use Tailscale and the Nextcloud app/web as authorized.
No MDM is part of this workflow.

An internet or VPN outage makes server files and services unreachable.
Linked local accounts still log in; previously used mobile domain accounts
may use cached credentials. A new domain login and password changes need a
reachable DC. Locally synced files remain available; check synchronization
and conflicts when connectivity returns. The helper is not a guarantee that
every profile can log in offline before its first successful sign-in.

Measure latency and throughput between sites. Their geographic distance and
ISP plan do not establish usable upload speed. Keep large recording/editing
work local; verify any overnight transfer finishes without impacting services.

## DNS at every site

- Routers keep their existing DHCP and DNS settings.
- On an enrolled church Mac, `/etc/resolver/ad.arisecenla.com` sends the
  church domain to its intended reachable DC. Other names continue using
  the Mac's existing resolver configuration.
- On Tailscale clients, use the approved tailnet split-DNS rule for
  `ad.arisecenla.com`. The server's Tailscale address can provide a stable
  DNS endpoint, but test that AD and app records also return addresses the
  remote client can reach. Do not assume split DNS routes private subnets.
- If LAN subnets overlap, per-device Tailscale addresses avoid relying on
  routing those overlapping subnets. Do not renumber the routers to fix it.
- macOS `dig` does not exercise `/etc/resolver`. Check system name lookup
  with `dscacheutil -q host -a name arise-server.ad.arisecenla.com`, then
  check SRV records by querying the intended server explicitly:
  `dig @<dns-ip> _ldap._tcp.ad.arisecenla.com SRV`.

Follow a DNS check with a real domain login, share access and HTTPS app
request from each site. A public resolver used as a generic secondary DNS
server cannot answer the private AD domain and is not an AD failover plan.

## A second domain controller and Arise-Home

The later owner plan puts the second node at Arise-Home first, then
Alexandria when another PC is available. `docs/NODES.md` distinguishes that
future design from implemented capabilities. An off-site restic copy is a
backup; it is not an automatically available directory or app replica.

A second DC needs a distinct hostname, working bidirectional connectivity,
correct AD DNS, synchronized clocks and a verified replication/recovery
procedure. Samba directory replication does not itself provide Sysvol or
file/app replication. Do not run a one-line domain join and assume the site
is ready. Changes to client split resolvers stay on the clients/tailnet,
not the site's router. Any takeover needs tested fencing and a deliberate
operator procedure; a failed heartbeat alone must not start two primaries.

## The Campuses app

Dashboard → Campuses and `arisectl sites` show configured sites, probe
results and computers whose reported addresses match a site's subnet.
Tailscale addresses and NAT can make physical-site inference incomplete.
Update the observations in `arise.toml` and check real access separately.
