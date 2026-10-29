# Discord: the server's monitoring room

Bradly uses Discord for server monitoring and alerts, not as the church's
chat (round 4, 89 and 101). The server posts into four channels through
four webhooks. Nothing is read from Discord; it is one-way.

## What to set up in Discord (five minutes)

1. A server (or the one you have), with four text channels:

   | Channel | What lands there |
   |---|---|
   | `#alerts` | failures (backup, stream, domain, disk at 75%, UPS), security (a new device, `arise-rescue` used, a virus found), updates waiting; round 7: a night with no backup (64), a church Mac silent three days (82), a disk whose health check warns or the CPU at 80 °C (137/138). **Bradly's alone** (round 7, 77): only he is in this channel |
   | `#sunday` | the Sunday all-green at the end of the checklist, the live link the moment the stream starts, the 9:30 nudge if the list has open items |
   | `#weekly` | the Monday morning summary; the monthly restore drill's line (round 7, 56); the January clean-up report (63, 139) |
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

- Every post is plain text with the time, one line of what happened and the
  command that fixes it; no embeds, no pings.
- The same event never posts twice; a repeat failure posts once a day with
  "still failing since …".
- `#daily` is the one exception to "no daily note" (round 2): the note was
  turned off for the dashboard and the phone, not for Discord.

## How the server posts (round 7)

`server/arise_server/discord.py` is the one place that posts. It reads the four
addresses from `/etc/arise/secrets/discord.toml` (never logs them, never returns
them: `GET /api/discord` and `sudo arisectl notify discord` say only which
channels are set). Each post can carry a key; a key is posted once, ever, so an
hourly check never repeats itself. Disk and heat warnings repeat at most once a
day while they stay true.

- `sudo arisectl notify test alerts` (or `sunday`, `weekly`, `daily`) posts one
  test line to that channel.
- `sudo arisectl upkeep hourly` runs the hourly checks by hand
  (`arise-upkeep.timer` runs them every hour).
- Settings → Notifications has the same Test button per channel
  (`POST /api/discord/test`).

Who reads which channel is Discord's own setting: make `#alerts` visible to
Bradly only (channel settings → Permissions → @everyone: View Channel off).
