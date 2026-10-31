# Wix DNS for arisecenla.com, step by step (round 7, 131)

Bradly asked to be walked through it. This page is every DNS record ariseOS
needs at Wix, in the order to add them, with what each Wix screen shows. You
only change DNS at Wix for **arisecenla.com**; `arisecenla.church` is at
GoDaddy, nobody has access to it, and nothing here needs it (round 7, 133).

Nothing below points at the server. Rule 7 holds: the box is not reachable
from the internet, and none of these records changes that.

| Part | What it is for | Records | When |
|---|---|---|---|
| 1 | Resend **sends** from `mail.arisecenla.com`: reset links, notices, newsletters ("Arise Church IT", round 7, 132) | 3, plus 1 optional | now |
| 2 | Staff addresses `first.last@ad.arisecenla.com` **arrive** at Resend so the box can forward them (round 7, 155) | 1 MX | when you turn forwarding on |
| 3 | Check them | none | after each part |

Values marked **(from Resend)** are only shown on Resend's own pages: copy
them from there, never from this page or a chat. Everything else is exact.

The screen names below are what Wix and Resend called them when this was
written. Both rename buttons now and then; the order of the steps does not
change.

## Before you start: open the two tabs

1. **Resend.** Sign in at resend.com with the **church's** Resend account, not a
   personal one (Bradly, Oct 31, ANSWERS H8). Leave this tab open; it is where
   values come from. Make the API key on install day, not before: sending access
   only, for `mail.arisecenla.com`.
2. **Wix.** Sign in at wix.com → the church site → **Settings** (left menu,
   near the bottom) → **Domains**. You see `arisecenla.com` with a **⋯** button
   on its right (Domain Actions). Click **⋯** → **Manage DNS Records**.

   What you see: one box per record type, top to bottom: **A (Host)**,
   **CNAME (Aliases)**, **MX (Mail Exchange)**, **TXT (Text)**, then SPF, NS
   and the rest. Each box has the records already there and a **+ Add Record**
   link under it. There is one **Save** button at the bottom of the page.

   If Wix says the DNS is not managed here ("connected by pointing"), stop:
   the records go wherever `arisecenla.com`'s name servers are, and part 3's
   `dig NS` line shows where. Tell Claude what it says.

**Leave every record that is already there alone.** The website's A and
CNAME records and any mail the church already gets at `arisecenla.com` stay
exactly as they are. Every record below sits on a subdomain (`mail`,
`send.mail`, `ad`), so none of them can touch the website or the root
domain's mail.

## Part 1: sending (mail.arisecenla.com)

**In Resend:** left menu **Domains** → **Add Domain** → Name
`mail.arisecenla.com` → Region: leave **North Virginia (us-east-1)** → **Add**.
Resend opens the domain's page with a **DNS Records** table. Keep it open.

**In Wix**, add each row. Where Resend's Name ends in `.arisecenla.com`, type
only the part before it: Wix adds the rest.

| # | Wix box | Host name (type this) | Value | Priority |
|---|---|---|---|---|
| 1 | **TXT** → + Add Record | `resend._domainkey.mail` | the long key starting `p=` **(from Resend)**, pasted in one piece | |
| 2 | **TXT** → + Add Record | `send.mail` | `v=spf1 include:amazonses.com ~all` | |
| 3 | **MX** → + Add Record | `send.mail` | `feedback-smtp.us-east-1.amazonses.com` | `10` |
| 4 (optional) | **TXT** → + Add Record | `_dmarc.mail` | `v=DMARC1; p=none;` | |

Rows 2 and 3 are what Resend shows for a us-east-1 domain; **if Resend's table
differs, Resend's wins.**

What Wix shows when you add an MX record: it may offer a list of mail
providers (Google Workspace, Microsoft 365, "Other"). Choose **Other** (or
"custom"). It may warn that changing MX records affects your email: this one
is only for `send.mail`, so the church's existing mail is not affected; go on.

TTL: leave whatever Wix suggests (usually 1 hour). Then **Save** at the bottom.

**Back in Resend:** **Verify DNS Records**. Each row turns **Verified** within
minutes to a few hours.

**On the server** (Claude can do this part): `[mail] from_email` in
`/etc/arise/arise.toml` becomes an address at `mail.arisecenla.com`, and the
Resend API key goes into `/etc/arise/secrets/resend-api-key` (never into a doc
or a chat). `sudo arisectl mail status` then says configured.

## Part 2: receiving for staff addresses (ad.arisecenla.com)

Only when you are ready to turn forwarding on (round 7, 155).

`ad.arisecenla.com` is the church domain inside the building: the server
answers for it there, and that does not change. On the internet it has no
records yet. This part adds **one MX record** so that mail sent to
`first.last@ad.arisecenla.com` from anywhere lands at Resend, which keeps it
until the box asks for it (every five minutes, an outgoing call).

**In Resend:** left menu **Receiving** (it may say **Inbound**; in 2026 it was
still a beta, so it may need switching on for the account) → **Add domain**
(or "Custom domain") → `ad.arisecenla.com`. Resend shows **one MX record**:
a host name and a priority **(from Resend)**.

**In Wix:**

| Wix box | Host name | Points to | Priority |
|---|---|---|---|
| **MX** → + Add Record | `ad` | the MX host Resend showed **(from Resend)** | the priority Resend showed (it must be the lowest number for `ad`; there is no other MX for `ad`, so it is) |

**Save.** Back in Resend, **Verify**.

Then on the server: `[mailfwd] enabled = true` in `/etc/arise/arise.toml`.
`sudo arisectl mail forward` lists every person, whether they have a personal
email on their profile, and whether their mail will be forwarded. Send a test
to your own church address from your phone; within five minutes it is in your
personal inbox, from "<sender> via Arise Church IT", and a reply goes straight
to the sender.

Inside the building nothing changes: a church Mac still asks the server about
`ad.arisecenla.com` (its resolver file) and never sees this record.

## Part 3: check

DNS takes from minutes to a few hours. From the box or any Mac (Terminal):

```
dig +short NS  arisecenla.com                            # Wix's servers: *.wixdns.net
dig +short TXT resend._domainkey.mail.arisecenla.com     # the p=... key
dig +short TXT send.mail.arisecenla.com                  # "v=spf1 include:amazonses.com ~all"
dig +short MX  send.mail.arisecenla.com                  # 10 feedback-smtp.us-east-1.amazonses.com.
dig +short TXT _dmarc.mail.arisecenla.com                # "v=DMARC1; p=none;" (if added)
dig +short MX  ad.arisecenla.com @1.1.1.1                # part 2: Resend's MX host (ask a public resolver:
                                                         # inside the church the server answers for "ad")
```

An empty answer means the record is not there yet, or the host name has a
typo. docs/EMAIL-DNS.md has the "if something is wrong" list.

## What never goes into Wix

- Anything pointing at the server's address. The box is not on the internet.
- Records for the website you didn't add. Leave them.
- A second `v=spf1` record on the same host name (only one is allowed).
