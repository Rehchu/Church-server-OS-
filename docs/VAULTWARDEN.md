# Vaultwarden: the admins' passwords and one vault per department (round 7, 117)

Bradly's answer: **admins, plus a vault for each department's shared
passwords**. Round 7, 15 says everyone in a department knows its department
account's password, and 16 that it changes whenever someone leaves that
department. The vaults are where those passwords live, so "everyone in the
department" means "everyone in its vault", and changing it is one edit.

Vaultwarden is the Bitwarden-compatible app already in the Store
(`templates/vaultwarden`), served at `https://vault.ad.arisecenla.com` behind
Caddy (the Bitwarden apps refuse plain http), on church Wi-Fi and Tailscale
only, like everything else.

## How it maps

| Vaultwarden | Arise |
|---|---|
| One **organization**, "Arise Church" | the church |
| **Owner** of it | Bradly; **Admin**: Kristina and the two pastors (the four admins) |
| One **collection** per department | Children's Department, Inedge, Media, Worship, Kids, Alexandria (`[storage] departments`) |
| A collection's members | the people in that department's group in Directory |
| A collection's items | the department account's password (e.g. `childrens.department`), and any other shared login that department uses |
| Each admin's own vault | their personal items; nobody else sees them |

Nobody's personal vault is visible to anyone else, the owner included: that
is how Bitwarden is built.

## Setting it up (once, about twenty minutes)

Do this at the closet, signed in as yourself, after the app is running
(`arisectl app list` shows `vaultwarden running`).

1. **Invite yourself.** Sign-ups are off from the start (`SIGNUPS_ALLOWED=false`
   in `templates/vaultwarden`): people are invited, never self-made. Open
   `https://vault.ad.arisecenla.com/admin`; it asks for the admin token, which
   the Store generated into `/etc/arise/secrets/apps/vaultwarden.env` (root
   only: read it on the box, never paste it anywhere). **Users** → **Invite
   User** → your church address.
2. **Your account.** Open `https://vault.ad.arisecenla.com` → **Create
   account** with that same address (an invited address may register; any
   other is refused). Pick a long master password: nobody, not even the
   server, can recover it. Vaultwarden has no mail set up here, so invitations
   do not arrive by email: tell each person to open the address and create
   their account with the address you invited.
3. **The organization.** In the web vault: **New organization** → name
   `Arise Church` → the free plan (Vaultwarden has no limits).
4. **Invite the other admins**: first in `/admin` → Invite User (so they may
   register), then in the organization (Members → Invite) as **Admin**: Kristina
   and the two pastors. Each chooses their own master password.
5. **The collections.** Organization → Collections → **New collection**, one
   per department, named exactly like the department folders.
6. **Invite each department's people** the same two ways (`/admin`, then the
   organization) as **User**, ticking only their department's collection (and **Hide passwords** off, since they need to
   type them).
7. **Put the department account passwords in.** For each department account:
   **New item** → Login → name `Children's Department (department account)`,
   username `childrens.department`, the password, collection: that department.

When someone leaves a department (round 7, 16): change that department
account's password in Directory, then edit the item in its collection. Remove
the person from the collection. They lose it on their next sync.

## Backups

Its data folder `/srv/arise/apps/vaultwarden` is in the nightly **App data**
job, and so goes to Arise-Home with the rest (round 7, 53). The vault is
encrypted with each person's master password; a backup without the master
passwords cannot be read. Nothing about it is in git.
