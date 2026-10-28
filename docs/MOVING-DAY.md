# Moving day — the server goes from Pineville to the Hub

The PC lives at Arise Pineville until the Apostolic Hub is built, then it
moves there. This is the plan for doing that with the least downtime, and
with a way back if the Hub is not ready after all. Read it the week before,
not the morning of.

What makes this easy: **Tailscale addresses do not change when the box
moves.** Every laptop, the split-DNS rule, the Alexandria route box and
every off-site person keep working exactly as before. What changes is the
server's LAN address, which building has it on the switch, and the fact
that Pineville becomes a remote site.

Expected downtime: the drive between the buildings plus about thirty
minutes at each end. Call it two hours (an estimate; measure your own
drive). Nobody at a bound Mac notices until they need a file that is not
cached.

---

## Before the day (the week before)

| Done | What | How you know |
|---|---|---|
| ☐ | Backups verified | Dashboard → Backups: every job green in the last 24 h; `sudo arisectl backup verify` (that is `restic check`) says ok; restore one file from a snapshot to your Mac and open it |
| ☐ | A second copy of the restic repo exists outside the Pineville building, even if it is a USB disk you carry (docs/IDEAS.md § Off-site copy) | you can see its snapshots with `restic -r <path> snapshots` |
| ☐ | The domain is backed up on its own (docs/DIRECTORY.md § Backing up the domain controller) | the `samba-tool domain backup offline` file is in the restic `config` job and on the USB disk |
| ☐ | `/etc/arise/arise.toml` and `/etc/arise/secrets/` copied to the USB disk | `ls` |
| ☐ | The Hub's subnet decided and set on the Hub router (docs/NETWORK.md: `192.168.30.0/24`); the server's new address decided (`192.168.30.10`); a DHCP reservation or a free static address for it | the router page |
| ☐ | The Hub has: a switch port on the right VLAN, a UPS, internet with a known upload speed, a closet that locks, a monitor and the Windows keyboard | you stood there |
| ☐ | Decided where the **Synology** goes (question 7). Moves with the server: it is the backup target and the home folder store, it should sit next to the server. Stays at Pineville: backups cross the VPN every night at 03:00 and the home folders are a WAN hop away, which is slow for everyone at the Hub. **Move it.** | |
| ☐ | A **route box for Pineville** bought and tested (docs/NETWORK.md option B): after the move Pineville is a remote site and its Macs and printers need the route. Test it at Pineville before the move by advertising a dummy route | Tailscale console shows it |
| ☐ | Everyone told the date and the two-hour window. Pick a weekday morning after the 03:00 backup, never a Sunday or Monday (Glory Night) | the daily note |
| ☐ | Photos of the back of the PC, the Synology, the switch ports they are in | your phone |

If any box is unchecked, do not move. There is no hurry a church cannot
survive.

---

## The day

**At Pineville, in order:**

1. Confirm last night's backup and automator ran: Dashboard → Overview.
2. Tell people it is happening (the daily note, or a message).
3. Close the dashboard for everyone: nothing to do; sessions just stop.
4. Shut down cleanly. Flame menu → **Shut Down…**, type the word; or
   `sudo arisectl` has no power verb, so `sudo systemctl poweroff` over SSH.
   Never pull the plug on a domain controller; Samba's database does not
   like it.
5. Shut down the Synology from DSM (Control Panel → Hardware & Power →
   Shutdown) if it moves.
6. Unplug, label the cables, drive.

**While it is off**, this is what happens at each site:

| | Works | Does not work |
|---|---|---|
| A bound Mac with a mobile account | login with the cached password, everything local, Downloads, the apps | the server home (Desktop and Documents show the last synced copy, read-only in effect), the shares, the dashboard, password changes, new users |
| A Windows PC joined to the domain | login with cached credentials | same list |
| Tailscale devices | the tunnel to each other | the server, so nothing useful |
| DNS at Pineville | **nothing**, if the server was the only DNS and the router does not forward. Internet looks down for staff devices. Guest Wi-Fi is fine | |
| The automator, backups, the daily note | — | all of it, for the window; they catch up on their next timer |

The DNS line is the one people feel. Two ways round it, pick one the week
before: give the Pineville DHCP a second DNS entry (the router) for the day,
or put the Pineville route box in place **before** the move with Tailscale's
split DNS carrying `ad.arisecenla.church`, so lookups for the realm fail
cleanly and everything else resolves through the router.

**At the Hub:**

1. Rack it, plug in the monitor and keyboard, switch port in the staff
   VLAN, the Synology beside it, both on the UPS. Power on. The monitor
   shows the Arise desktop, which will show *Needs you* for the NAS mount
   and probably a sample-data badge for anything that cannot reach its
   tool. That is expected until step 2 is done.
2. Log in at the monitor (Alt+F2 for a text login) or over Tailscale SSH
   (`ssh arise-server` works the moment Tailscale is up, which is the moment
   the box has internet; this is why Tailscale was worth it).
3. The new address. Edit netplan (INSTALL.md § Fixed address) to
   `192.168.30.10/24`, gateway `192.168.30.1`, DNS `127.0.0.1`; `sudo
   netplan apply`. Or if the Hub router has a DHCP reservation for the
   server's MAC, keep netplan on DHCP and just confirm the address.
4. `/etc/hosts`: the line for `arise-server.ad.arisecenla.church
   arise-server` carries the new address.
5. The domain's own DNS records: Samba registers the DC's address at start,
   but check and fix by hand:

   ```bash
   sudo samba_dnsupdate --verbose
   sudo samba-tool dns query 127.0.0.1 ad.arisecenla.church arise-server A
   sudo samba-tool dns query 127.0.0.1 ad.arisecenla.church @ ALL | grep -i 192.168
   ```

   Any record still showing `192.168.10.10` (or the old `.1.x`): delete and
   add it with `samba-tool dns delete` / `dns add`. The names `vault` and
   `remote` from docs/REMOTE-ACCESS.md § (e) are two of them.
6. `arise.toml`: in `[[sites]]`, the Hub's `subnet` is where the server
   is now; its `note` and Pineville's swap roles. `[system]` has no address
   in it, nothing to change there. `sudo systemctl restart arise-web`.
7. The Synology: same subnet, new address `192.168.30.11`, set in DSM;
   `/etc/arise/arise.toml` `[nas] host` updated if it is an address and not
   a name; `sudo arisectl nas mount`.
8. Tailscale: `sudo tailscale up --ssh --advertise-routes=192.168.30.0/24`
   (the new subnet, replacing the old one), approve the route in the
   console. Change the split-DNS nameserver in the Tailscale console from
   the old LAN address to `192.168.30.10`. This one line is what makes every
   remote Mac find the domain again.
9. Hub DHCP: DNS = `192.168.30.10` for the staff VLAN.
10. `sudo arisectl doctor`. Everything that was green before must be green
    now. The usual red lines after a move are the NAS mount (step 7), a DNS
    record (step 5) and the time (if the box was off long enough: `sudo
    chronyc makestep`).
11. From a Hub Mac: the two `dig` checks, then bind one Mac. From your
    laptop on a hotspot: the dashboard over Tailscale. From Alexandria: a
    file on a share.

**Back at Pineville**, the same day or the next:

12. The Pineville route box goes in: `tailscale up
    --advertise-routes=192.168.10.0/24 --accept-routes`, route approved, a
    static route on the Pineville router toward `192.168.30.0/24` via the
    box, DHCP DNS at Pineville = the server (`192.168.30.10`, reached through
    the box) with the router second.
13. A Pineville Mac: `ping 192.168.30.10`, the two `dig` checks, a login, a
    file saved to Documents turning up on the server. The home-sync agent
    carries on; it only needs the name `arise-server` to resolve.
14. `arise.toml` `[[sites]] pineville`: `probe` = the route box. Campuses
    shows both sites green.

---

## After

- Backups: run every job once by hand from the dashboard and read the rows.
  `restic check` once more.
- The automator runs that night at 02:05 as before; nothing in it knows
  the building.
- Guacamole connections that used LAN addresses of Pineville computers
  still work through the route box; ones that used the server's old
  address (the SSH connection to the server itself) need the new address.
- Caddy's certificate names did not change; the DNS records behind them did
  (step 5).
- Vaultwarden, Uptime Kuma and the other apps follow the server; their
  addresses are names, not numbers, if you set them up that way.
- Re-read docs/NETWORK.md with the Hub as "the site where the server is."
  Pineville's firewall table now applies to the Hub's VLANs.

---

## Rollback

If at step 10 the box is not healthy and the reason is the Hub (internet,
power, the switch), put it back:

1. Shut down cleanly.
2. Drive back, plug in where the photos say.
3. Netplan back to the Pineville address, `/etc/hosts`, `samba_dnsupdate`,
   the Tailscale route and split-DNS nameserver back to the old address,
   Pineville DHCP DNS back to the server. The same steps as the move, with
   the old numbers.
4. `arisectl doctor`.

Nothing in the move writes to the directory's data or the backups, so there
is nothing to restore. If the disk itself died in transit: a fresh install
(INSTALL.md), then docs/DIRECTORY.md § Recovering from the domain backup and
`arisectl backup restore latest` for the data. That is what the USB copy in
the checklist is for.

---

## The printed checklist

Print this half and take it with you.

```
BEFORE  ☐ backups green  ☐ restic check ok  ☐ one file restored
        ☐ domain backup + arise.toml + secrets on USB
        ☐ Hub subnet set  ☐ server address reserved  ☐ Synology address reserved
        ☐ Hub: switch port, UPS, internet, closet, monitor, keyboard
        ☐ Pineville route box tested  ☐ Pineville DHCP second DNS set for the day
        ☐ people told: date, window
PINEVILLE ☐ last night's jobs ok  ☐ Shut Down (typed)  ☐ Synology shut down
        ☐ cables labelled  ☐ photos
HUB     ☐ power, monitor shows the desktop  ☐ login (Alt+F2 or Tailscale SSH)
        ☐ netplan new address  ☐ /etc/hosts  ☐ samba_dnsupdate + check records
        ☐ arise.toml sites  ☐ Synology address + nas mount
        ☐ tailscale up --advertise-routes=<hub subnet>  ☐ route approved
        ☐ split DNS nameserver = new address  ☐ Hub DHCP DNS = server
        ☐ arisectl doctor green  ☐ dig from a Hub Mac  ☐ one Mac bound
        ☐ dashboard from a hotspot  ☐ a share from Alexandria
PINEVILLE AFTER ☐ route box advertising  ☐ static route on router
        ☐ DHCP DNS = server  ☐ ping + dig + login from a Pineville Mac
        ☐ Campuses: three sites green
AFTER   ☐ every backup job run by hand  ☐ restic check  ☐ daily note next morning
```
