# Ideas you did not ask for

Each one: what it is, what it costs, and whether it is built. Prices are
estimates from memory and will have moved; check before buying.

| # | Idea | Cost | Status |
|---|---|---|---|
| 1 | A UPS with automatic shutdown | Pineville has one (answer 8) | **doing it**: SETUP-GUIDE day 1, once the UPS model is known |
| 2 | A second copy of the backups off-site | USB disk or ~$6/TB/month | not built; Bradly chose "nowhere yet" (answer 48) |
| 3 | Free Mac management (MDM) | free | not built |
| 4 | Printers through the server | free | not built |
| 5 | A church password manager | free | **template exists** (Vaultwarden) |
| 19 | Claude on the box | free with his claude.ai account | **built**: `install.sh` installs Claude Code; `claude` then `/login`; CLAUDE.md carries the house rules |
| 20 | A local, private AI with no account | free; slow on a CPU | **templates**: `ollama` + `open-webui`, off by default (docs/STACK.md § AI on the box) |
| 21 | The disk warning before the disk dies | free | **built**: smartd watches; `arisectl doctor` prints PASSED or FAILED per disk |
| 22 | Security updates without a surprise reboot | free | **built**: unattended-upgrades, security only, Automatic-Reboot off; needrestart lists what waits |
| 6 | A public status page | free | **template exists** (Uptime Kuma) |
| 7 | The check-in station as a locked kiosk | free | not built; there is no check-in station yet (answer 28) |
| 8 | Guest Wi-Fi with a welcome page, not on the server | depends on the router | not built, on purpose |
| 9 | Search the sermon transcripts from Spotlight | free | not built |
| 10 | Proclaim and StreamYard assets synced to the media Mac | free | **chosen** (answer 38); template exists (Syncthing) |
| 11 | A shared church calendar and mail | free | not built |
| 12 | A label printer for check-in | ~$100 | hardware |
| 13 | Old Macs donated to the church, re-enrolled in an hour | free | **the enrol script does it** |
| 14 | Password reset by text message | cents per text | not built |
| 15 | Digital signage from the server | a TV and a $40 stick | not built |
| 16 | The daily note to Discord or Slack | free | built; **off by Bradly's choice** (answer 49) |
| 17 | A second domain controller at Alexandria | an old PC | documented, not built |
| 18 | Sermon audio to Spotify from the server | free | not built |

---

**1. A UPS with automatic shutdown.** Doing it: Pineville already has a
UPS (answer 8), so this is a day-1 step in docs/SETUP-GUIDE.md, not an
idea. A domain controller that loses power mid-write can corrupt its
database; `nut` (Network UPS Tools, in Ubuntu) reads the UPS's USB cable
and shuts the server down cleanly before the battery dies. The Synology
plugs into the same UPS and can be told by the server (DSM supports a
network UPS master). One package, one config file, one line in
`install.sh` once the UPS model is known. The Hub has no UPS yet; that is
in the moving-day checklist.

**2. A second copy of the backups off-site.** The Synology sits next to the
server; a fire, a flood or a theft takes both. restic can keep a second
repository anywhere: a USB disk you take home once a month (free), or
Backblaze B2 (an estimate: around $6 per TB per month, and restic talks to
it natively). One more job in `backups.yaml` pointed at a `b2:` repository,
a key in `/etc/arise/secrets/`, the same 03:00 timer. The dashboard shows it
as one more row. Answer 48 was "nowhere yet"; until that changes, a fire
takes the server and the Synology together, and the `recordings` share has
no copy at all.

**3. Free Mac management.** Apple Business Manager is free for a church
(a D-U-N-S number and a letter on letterhead), and with it Macs the church
buys new arrive already assigned to you. Pair it with a free MDM (Fleet is
open source and self-hostable, or Apple's own Business Essentials at a few
dollars a Mac) and you can push the Tailscale app, the Caddy certificate,
the home-sync agent and a Wi-Fi profile to every Mac without touching it.
Not needed for ten Macs; worth it at twenty, or the day you want to lock a
lost laptop remotely.

**4. Printers through the server.** CUPS on the server, every printer added
once, and the Macs and PCs find them by name on every site through the
tunnel. The guest and kids VLANs print to it without reaching anything
else. Free, an afternoon, and it ends the "which Mac has the printer set
up" problem.

**5. A church password manager.** The Vaultwarden template is already in
Apps (docs/REMOTE-ACCESS.md § (e) gives it HTTPS). It is Bitwarden,
self-hosted: the StreamYard login, the YouTube account, the Synology admin,
the router page, shared with the people who need them and nobody else, and
in the nightly backup. Free; deploy it from the dashboard.

**6. A public status page.** Uptime Kuma (template exists) watches the
server, the Synology, the Alexandria route box, the stream page, the
website, and can publish a status page you link from the staff portal.
Free.

**7. The check-in station as a locked kiosk.** The same `cage` kiosk that
shows the Arise desktop on the closet monitor can show the check-in app
full screen on a small PC at the kids desk, with no way to get to a
desktop. One systemd unit; the URL changes. Free.

**8. Guest Wi-Fi with a welcome page.** A captive portal ("tap to agree")
for Sunday guests, done on the router or the access points (UniFi and
Meraki have it built in), and deliberately **not** on the server: the guest
network must not be able to reach the server at all (docs/NETWORK.md). The
one thing to do on the server side is nothing.

**9. Search the sermon transcripts from Spotlight.** The automator already
pulls transcripts for the channel (`work/` on the PC today, the server
tomorrow). Index them and Spotlight answers "where did Apostle Bryant say
'GAURD your heart'" with the video and the timestamp. A small job in the
server, a few hundred lines, no quota spent. I would build it the week the
transcripts are on the server.

**10. Proclaim and StreamYard assets on the media Mac.** The loops,
backgrounds and lower thirds are big and the media Mac needs them fast and
offline. The Syncthing template (exists) keeps a local copy on the media Mac
in two-way sync with the `graphics` share, so the share is the master, the
Mac is fast, and restic backs up the share nightly. Free. Question 38.

**11. A shared calendar and mail.** Google Workspace for Nonprofits is free
for a church (Gmail, Calendar, Drive under `arisecenla.church`). The
directory accounts and the Google accounts stay separate things unless
you want to go further later. Free, an application form.

**12. A label printer for check-in.** A Brother QL or Dymo on the kids VLAN,
printed to through CUPS (#4). Around $100.

**13. Donated Macs.** When someone gives the church an old Mac: wipe it,
run `mac/enroll-mac.sh`, and it is a church Mac with every account on it in
under an hour. The script is built; this is just a use of it. Keep the
activation-lock question (35) in mind: a Mac still tied to a donor's Apple
ID is a paperweight.

**14. Password reset by text.** A person who forgets their password texts
the server, gets a code, sets a new one in the portal. Twilio costs cents
per message. Not built; it would be a small addition to the portal's
"Change password" once a phone number is a field on the user. Until then,
the reset is you, in Directory → Users.

**15. Digital signage.** A TV in the lobby with service times, the verse of
the week, the YouTube latest, served from the server as one more kiosk
page (a $40 stick running the same `cage` + browser). Free apart from the
screen; a page to design in the church's style.

**16. The daily note.** Built: `arise-notify.timer` at 07:00 sends what
needs you (or "all clear") to a Discord or Slack webhook. Bradly chose none
(answer 49), so the webhook stays empty and nothing is sent; the Overview's
*Needs you* list is the alarm. Put a webhook in `arise.toml` and it is on.

**17. A second domain controller.** docs/MULTI-SITE.md § A second domain
controller at Alexandria: an old PC running Samba as a second DC so
Alexandria logins, new users and password changes survive the tunnel being
down. Documented; not needed on day one.

**18. Sermon audio to Spotify from the server.** Your notes say Spotify
wants 1920x1080 art and the podcast files are built on the PC today. The
automator's host moves to the server; the audio extract and the art could
run on the same 02:05 timer and drop into a `podcast` share for upload.
Free; it is the automator's work, not the server's, so it follows the
automator.
