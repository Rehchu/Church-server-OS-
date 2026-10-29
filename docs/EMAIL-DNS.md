# The email records in Wix (round 6, 27)

Bradly adds these himself (round 6, 27). They let Resend send mail **from**
`mail.arisecenla.com` (round 5, 3): the Mail app's newsletters, password-reset
links, and later the internal mail server's forwards. With the MX of docs/WIX-DNS.md part 2 they are the only DNS
records ariseOS needs at Wix, and none of them points at the server (rule 7:
nothing on the box is reachable from the internet).

What does **not** change:

- The domain stays `AD.ARISECENLA.COM` (NetBIOS `ARISE`), and the server is its
  DNS inside the building (round 6, 25).
- Staff addresses are `first.last@ad.arisecenla.com` (round 6, 28), forwarded
  to each person's own email (round 7, 155). That needs **one** more record, an
  MX for `ad` pointing at Resend's receiving, added only when forwarding is
  turned on: docs/WIX-DNS.md, part 2. It points at Resend, never at the box.

**docs/WIX-DNS.md is the screen-by-screen walkthrough** of everything below
plus that MX record (round 7, 131). This page stays as the reference.
- The website's records (both addresses show the site, round 6, 26) and any
  mail the church already receives at `arisecenla.com` are left alone. Every
  record below sits on the `mail` subdomain, so none of them can disturb the
  root domain's mail or the site.

## 1. Add the domain in Resend and read its records

1. Sign in at **resend.com** → **Domains** (left side) → **Add Domain**.
2. Name: `mail.arisecenla.com`. Region: leave the default (North Virginia,
   `us-east-1`) unless there is a reason to pick another; the records below
   change with it.
3. Resend opens the domain's page with a **DNS Records** table. That table is
   where the values come from; keep this tab open. It shows three or four rows:

| Purpose | Type | Name Resend shows | Value (copy it from Resend) |
|---|---|---|---|
| **DKIM** (proves the mail is the church's) | TXT | `resend._domainkey.mail` | a long key starting `p=MIGfMA0GCSqGSIb3…`. Unique to this domain: always copy it from Resend's page, never from a doc |
| **SPF** (who may send) | TXT | `send.mail` | `v=spf1 include:amazonses.com ~all` |
| **SPF** (the bounce address) | MX | `send.mail` | `feedback-smtp.us-east-1.amazonses.com`, priority `10` |
| DMARC (optional, recommended) | TXT | `_dmarc.mail` | `v=DMARC1; p=none;` |

The rows above are what Resend shows for a `us-east-1` domain as of this
writing; **Resend's own table wins** if it differs (another region changes the
MX host, and the DKIM key is always different). If a row's Name already ends in
`.arisecenla.com`, drop that part when typing it into Wix: Wix adds it.

## 2. Type them into Wix's DNS

1. Sign in at **wix.com** → open the church site's dashboard → **Settings** →
   **Domains**.
2. Next to `arisecenla.com`, open the **⋯** menu (Domain Actions) →
   **Manage DNS Records**.
3. Wix shows one section per record type (A, CNAME, MX, TXT, …). For each row
   from Resend:
   - **TXT (DKIM):** in the **TXT** section, **+ Add Record**. Host name
     `resend._domainkey.mail`. Value: paste the whole key from Resend, nothing
     before or after it. TTL: leave the default.
   - **TXT (SPF):** **+ Add Record** again. Host name `send.mail`. Value
     `v=spf1 include:amazonses.com ~all`.
   - **MX:** in the **MX** section, **+ Add Record**. Host name `send.mail`.
     Points to `feedback-smtp.us-east-1.amazonses.com`. Priority `10`. If Wix
     asks about a mail provider, choose the "other" or custom option; this
     record is only for `send.mail`, so it does not replace any mail the root
     domain already gets.
   - **TXT (DMARC), optional:** Host name `_dmarc.mail`. Value
     `v=DMARC1; p=none;`.
4. **Save** (Wix's button is at the bottom of the page). Do not edit or delete
   any record that was there before.

Wix's screens move now and then; the names of the steps above are what they
were called at the time of writing. If Wix says the domain's DNS is not managed
there (the domain was connected "by pointing" rather than by its name servers),
the same four records go wherever the name servers point (step 3 shows where).

## 3. Check them

DNS can take from a few minutes to a few hours. Then:

1. **In Resend:** on the domain's page, **Verify DNS Records**. Each row turns
   **Verified**; the domain then says **Verified**.
2. **From the box or any Mac** (Terminal):

   ```
   dig +short TXT resend._domainkey.mail.arisecenla.com    # the p=… key
   dig +short TXT send.mail.arisecenla.com                 # "v=spf1 include:amazonses.com ~all"
   dig +short MX  send.mail.arisecenla.com                 # 10 feedback-smtp.us-east-1.amazonses.com.
   dig +short TXT _dmarc.mail.arisecenla.com               # "v=DMARC1; p=none;" (if added)
   dig +short NS  arisecenla.com                           # who serves the DNS: Wix's are *.wixdns.net
   ```

   An empty answer means the record is not there yet (or has a typo in the
   host name). Asking a public resolver directly skips the church's caches:
   `dig +short TXT send.mail.arisecenla.com @1.1.1.1`.
3. **Then on the server:** put the sending address into `/etc/arise/arise.toml`
   (`[mail] from_email = "news@mail.arisecenla.com"`, or another name at
   `mail.arisecenla.com`), and the Resend API key into
   `/etc/arise/secrets/resend-api-key` (never into a doc or a chat).
   `sudo arisectl mail status` shows the from address and whether the key is
   configured; the Mail app's **Send a test** sends one message to an address
   you choose.

## If something is wrong

- **Resend says "Failed" on DKIM:** the value was cut short or has a space or a
  quote added. Delete that one TXT record in Wix (the one you just added) and
  paste the value again in one piece.
- **SPF verified but mail lands in spam:** add the DMARC row; give it a day.
- **Two SPF records on the same name:** only one `v=spf1` TXT may exist per
  name. `send.mail` is new, so this only happens if the record was added twice.
