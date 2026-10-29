# Discord: the server's monitoring room

Bradly uses Discord for server monitoring and alerts, not as the church's
chat (round 4, 89 and 101). The server posts into four channels through
four webhooks. Nothing is read from Discord; it is one-way.

## What to set up in Discord (five minutes)

1. A server (or the one you have), with four text channels:

   | Channel | What lands there |
   |---|---|
   | `#alerts` | failures (backup, stream, domain, disk at 75%, UPS), security (a new device, `arise-rescue` used, a virus found), updates waiting |
   | `#sunday` | the all-green an hour before each service (Sunday, Alexandria's 10:00, Glory Night, and Calendar events that count as a service), the live link the moment the stream starts, the nudge if a list has open items |
   | `#weekly` | the Monday 07:30 report: backups, storage, the Macs, sign-ins, updates, and the channel's progress to 1,000 subscribers and 4,000 public watch hours ("not available yet" until the box has the automator's numbers) |
   | `#daily` | the 06:00 morning report (Claude's, from the box's own data) |

2. For each channel: channel settings → Integrations → Webhooks → New
   Webhook → name it `ariseOS` → Copy Webhook URL. Four URLs.

3. The URLs are secrets. They go on the server only, in
   `/etc/arise/secrets/discord.toml`:

   ```toml
   alerts = "https://discord.com/api/webhooks/..."
   sunday = "https://discord.com/api/webhooks/..."
   weekly = "https://discord.com/api/webhooks/..."
   daily  = "https://discord.com/api/webhooks/..."
   ```

   `sudo arisectl notify test alerts` posts a test line to one channel;
   Settings → Notifications has a Test button per channel. Never paste a
   webhook URL into a chat, a doc or the repo: anyone holding it can post as
   the server.

4. Until the file exists, the dashboard says "Discord: not set" and keeps
   everything in the dashboard and the push to Bradly's phone.

## Posting rules

- The all-green (round 7, 78-80) posts an hour before each service: "All
  green: services up, backups ok, Synology mounted, nothing needs you", or
  each thing that needs someone, then every department's checklist (done of
  total). It posts once per service (the key is the date and the service),
  from the dashboard's own reminders loop, which checks every minute.
- Settings → Reports shows which channels are set (never the addresses) and
  the Monday report as it would post; `arisectl report weekly` posts it now.

- Every post is plain text with the time, one line of what happened and the
  command that fixes it; no embeds, no pings.
- The same event never posts twice; a repeat failure posts once a day with
  "still failing since …".
- `#daily` is the one exception to "no daily note" (round 2): the note was
  turned off for the dashboard and the phone, not for Discord.
