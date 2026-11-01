# Moving day — the server goes from Pineville to the Hub

The server stays at Pineville until the Hub is ready. Plan the move for the
quiet maintenance day Bradly chose, outside services, with a verified backup
and a way to return. Allow the whole day; travel time alone is not a reliable
downtime estimate.

The network rule applies at both buildings: **no router, switch or Google
Mesh configuration changes, no DHCP reservations, no port forwards and no
changes to other devices' addresses.** Configure the server and enrolled
clients only. Never treat example subnet numbers as the actual network.

Tailscale node addresses normally survive a change of physical location as
long as the node remains enrolled. Verify authentication, DNS and client
reachability before relying on this. A second functioning DC and file server
are not supplied merely by naming an Arise-Home node: `docs/NODES.md` marks
replication and takeover as future work.

## Before the day

- Verify every required backup job, run `sudo arisectl backup verify`, and
  restore representative files into a separate location. Follow
  `docs/BACKUPS.md` for the consistent domain and app backups. Keep a verified
  off-site copy outside the building before moving the original disks.
- Keep recovery credentials securely available to Bradly and Kristina, away
  from the machine. If carrying a recovery USB, encrypt it; verify its copy
  of configuration and domain recovery data without printing secrets.
- Record the current server network configuration, address, gateway, DNS
  records, NAS endpoint and Tailscale identity. Observe the Hub's existing
  network from a client there; do not alter it or prescribe a new subnet.
- Verify power, a working UPS, the existing network connection, internet,
  monitor, keyboard and a secure place for the server at the Hub. Photograph
  and label the server's existing cable connections for rollback.
- Decide whether the Synology moves. If it stays, verify its Tailscale path
  and measure remote file/backup throughput first. Moving it changes its
  physical network; let its existing network configuration obtain a valid
  address and verify its name/Tailscale endpoint before use.
- Put Tailscale on every approved client that needs the remote server and
  test it before the move. Church Macs remain domain-bound; existing linked
  local accounts keep their local passwords. Personal Macs are never
  enrolled in the helper or bound to AD.
- Configure and test domain-only resolution on the enrolled clients and in
  Tailscale. Prefer the server's reachable Tailscale address for remote DNS.
  Remove no working resolver until its replacement has been verified.
- Tell people the maintenance window. Close applications, let sync finish
  and verify its status before shutting down. A disconnected session does
  not prove its latest files were saved to the server.

## At Pineville

1. Check last night's backups and the designated automator runner's status.
2. Shut down the server cleanly from the dashboard, with its password and
   confirmation prompts. Never pull the power on a running domain controller.
3. Shut down the Synology from DSM if it is moving. Label the cables and move
   only the equipment agreed for this maintenance window.

While the server is off, linked local Mac accounts still log in. Previously
used mobile AD accounts may log in with cached credentials; test those
accounts beforehand. New domain logins, password changes, server files,
apps and backups wait. Local synced copies remain usable and changes may
need reconciling when sync returns. Ordinary internet DNS should continue
through each site's existing DNS; only the church domain uses split DNS.

## At the Hub

1. Connect the server, monitor, keyboard and UPS to the existing facilities.
   Start it and unlock LUKS at the local console. On the expected HP TPM 1.2,
   H3 requires the passphrase after every restart; Tailscale is unavailable
   before unlock. A previously tested early-boot SSH path may need a new
   LAN address at the Hub. Keep the keyboard recovery path available.
2. Check the actual address and default route. A static address from the old
   building may be invalid here: back up the server's netplan configuration
   and follow `INSTALL.md` to use DHCP on this network. `netplan try` from
   the local console provides a rollback window for changes.
3. DHCP is the current installer default. Before production domain use,
   verify the stable address/endpoint strategy. Pinning a DHCP lease does
   not reserve it; `--pin-ip` is only suitable for an address independently
   confirmed outside the allocation pool. If that cannot be established
   within the no-router-change rule, record the limitation instead of
   silently introducing a collision risk.
4. Check `/etc/hosts`, Samba's registered addresses and domain SRV records
   against the actual reachable server. `sudo samba_dnsupdate --verbose`
   requests registration; inspect its result. Identify individual stale
   records before any manual correction. Do not delete records merely
   because they contain an old-looking example subnet.
5. Reconnect Tailscale using the existing node identity. Verify split DNS
   points to a reachable nameserver. Do not copy obsolete subnet-route or
   router-DHCP commands from earlier versions of this guide. Reachability
   of DNS alone is insufficient: the addresses returned for LDAP, SMB and
   app names must also be reachable by every intended client.
6. Update the server's `[[sites]]` observations and NAS endpoint if needed.
   Mount the NAS and verify the expected mount and files before a backup;
   an empty local directory under `/mnt/synology` is not a successful mount.
7. Run `sudo arisectl doctor` and inspect each failed or untested check.
   Check time synchronization, directory, HTTPS dashboard, kiosk, NAS and
   the selected apps. Do not enable additional apps during the move.
8. From a Hub Mac, verify system resolution with
   `dscacheutil -q host -a name arise-server.ad.arisecenla.com`. For SRV
   records, query the intended DNS server explicitly with `dig @<dns-ip>
   _ldap._tcp.ad.arisecenla.com SRV`; macOS `dig` does not use the per-domain
   resolver file. Test a real login, an SMB file and Nextcloud sync.
9. Repeat HTTPS, directory and file checks from Pineville and Alexandria,
   and from an approved Tailscale device on a hotspot. No router setting
   changes are part of any of these checks.

## After and rollback

Run the required backups, inspect their results and restore a sample to a
separate location. Verify Guacamole uses the media Mac's reachable endpoint
and that the normal overnight jobs finish. The YouTube automator remains on
its designated runner until a separate deliberate cutover. Keep the existing
NDI/camera/streaming network unchanged; the move does not authorize rewiring.

If the Hub cannot pass these checks, shut down cleanly and return the server
to the recorded Pineville connection. Restore the server-side network and
NAS configuration as appropriate, recheck DNS/Tailscale and repeat the same
functional tests. Router configuration stays unchanged. If a disk failed,
use `docs/REINSTALL.md` and the verified domain backup; do not provision a
new domain over the recovery target.

## Printed checklist

```
BEFORE    backups verified; sample restored; recovery credentials available
          Hub power/network observed; original server settings recorded
          NAS location agreed; clients and split DNS tested over Tailscale
          users told; applications closed; sync complete
MOVE      clean server/NAS shutdown; equipment and cables labeled
HUB       actual address and route checked; stable endpoint limitation resolved
          server DNS/hosts checked; Tailscale and returned addresses reachable
          NAS mount verified; doctor and real login/file/sync checks passed
REMOTE    Pineville, Alexandria and approved hotspot client checks passed
AFTER     backup plus restore verified; overnight jobs checked
ROLLBACK  recorded server settings and original connection available
```
