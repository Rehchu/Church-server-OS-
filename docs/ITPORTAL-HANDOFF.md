# The IT portal: what changes in AriseHub (round 7, 118 and 119)

Bradly's answers: staff ask for IT help through **the IT portal on AriseHub**,
and its tickets reach him **in Discord** (118); the church's equipment list
lives **in the IT portal** too (119).

The ariseOS side is done here: the Help app, the closet card and the Mac welcome
text point staff to the portal (`[upkeep] it_portal_url`, default
`https://itportal.myfaithtech.com`, the address AriseHub's own launcher uses).
The Discord side lives in the AriseHub repo, which is pull-only from this
server (CLAUDE.md rule 13: its `main` deploys the live site). So the change is
written out below for a session working in AriseHub to make. Nothing here
edits that repository.

## The change in AriseHub (arise-it-portal)

Every new ticket, from the public form and from signed-in staff, already goes
through one function: `arise-it-portal/worker/src/lib/notify.ts`,
`notifyNewTicket()`. It emails the super-admins and never throws. Add one post
to Discord beside the email.

1. **A new Worker secret** on the `arise-it` Worker, `DISCORD_TICKETS_WEBHOOK`:
   a webhook URL for the Discord channel Bradly picks (his `#alerts`, or a new
   `#tickets`). It is a credential: it goes in with `wrangler secret put` or the
   dashboard, never in a file in the repo. Read the AriseHub CLAUDE.md section on
   error 10215 first: the newest version must be the deployed one before a
   secret can be added.

2. **`arise-it-portal/worker/src/types.ts`**, in `interface Env`:

   ```ts
   // Round 7, 118 (ariseOS): new tickets also post one line to Discord. Unset = no post.
   DISCORD_TICKETS_WEBHOOK?: string;
   ```

3. **`arise-it-portal/worker/src/lib/notify.ts`**, at the end of the `try`
   block in `notifyNewTicket()`, after `sendTicketNotification` (keep its result):

   ```ts
   const mailed = await sendTicketNotification(env, { /* unchanged */ });
   if (env.DISCORD_TICKETS_WEBHOOK) {
     // One plain line, the house style of ariseOS's Discord posts: no embeds, no pings.
     const line = `New IT ticket #${ticket.id} (${ticket.priority}, ${ticket.category}) from ${requesterName || "someone"}` +
       `${campus?.name ? " at " + campus.name : ""}: ${ticket.subject.slice(0, 150)}\n${baseUrl}/requests/${ticket.id}`;
     try {
       await fetch(env.DISCORD_TICKETS_WEBHOOK, {
         method: "POST",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({ content: line.slice(0, 1900), allowed_mentions: { parse: [] } }),
       });
     } catch (err) {
       console.error("discord ticket post failed", err);   // fail-soft, like the email
     }
   }
   return mailed;
   ```

   `allowed_mentions: { parse: [] }` matters: a ticket subject typed by the
   public must never be able to ping `@everyone`.

4. **A test** in `tests/` (AriseHub's pure-function style): the line builder
   pulled out as a small pure function (`ticketDiscordLine(ticket, requester,
   campus, baseUrl)`), pinned to stay under 1,900 characters, to name the
   ticket's link, and to be posted with `parse: []`.

5. Deploys through a merge to `main` (Workers Builds); a branch build is only a
   preview (AriseHub CLAUDE.md).

## The equipment list (119)

Already there: the portal's **Assets** (`routes/assets.ts`), **Consumables**,
**Licenses** and **Locations** pages are the equipment list. Nothing is built
on the server for it; the Help app links there. Cameras, mics and laptops go in
as assets, one campus each.

## What staff see

- **On a church Mac:** the welcome page on the desktop (round 7, 3) ends with
  "Something not working? The IT portal: https://itportal.myfaithtech.com, or
  call Bradly, Kristina or Ronnie."
- **On the closet card:** the same line under "Staff with a Mac problem".
- **In the Help app:** `GET /api/help/contacts` gives the portal address and
  who to call; the Help app shows them at the top.
