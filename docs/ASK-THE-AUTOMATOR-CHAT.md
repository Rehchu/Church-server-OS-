# What to ask the automator chat about YouTube access for the server

Bradly asked for this (round 4, question 97). Paste the block below into the
Claude chat that looks after the Arise YouTube automator. It knows the
automator's code, its Google project and its quota; the server side only
knows what it needs. Bring the answers back here and the decision gets made.

---

**Paste from here:**

The Arise Church server (ariseOS, an Ubuntu box in the church closet) is
going to run the nightly automator job from 02:05 Central instead of my PC.
The PC keeps the working copy and its own backups; the server pulls the repo
and runs the job. I need to decide how the server signs in to YouTube.
Please answer each of these from what you know of the automator:

1. **Which Google Cloud project and OAuth client does the automator use
   today?** Is it a "Desktop app" client (`client_secret*.json`) or
   something else? Is that file in the repo, or only on the PC?

2. **Which scopes does `token.json` carry?** (`youtube`,
   `youtube.force-ssl`, `youtube.upload`, `youtube.readonly`, others?)
   Does anything in the nightly job need a scope beyond those?

3. **Can a second machine use the same OAuth client with its own
   `token.json`?** I would prefer the server to do a one-time consent of
   its own and keep its own token in `/etc/arise/secrets/`, so either
   machine can be revoked alone. Does the automator's auth code support a
   console/headless consent flow (no browser on the server; I can paste a
   URL and a code), or does it assume a local browser?

4. **Quota.** The project's 10,000 units a day are shared by every token on
   that project. If the server runs the nightly job (about 2,000 units) and
   I still do Sunday and Monday work from chat sessions, what is the safe
   budget per side, and should the server's job refuse to run when the
   day's remaining quota is below a threshold?

5. **The hold list (`holds.json`) and the song bank.** If the repo is the
   source of truth and the server pulls it at 04:00, is there anything the
   nightly job writes back into the repo folder (reports, work lists,
   `_pull_queue.json`) that would conflict with my edits on the PC? What
   should the server commit, and what should stay local to it?

6. **Transcripts.** The PC pulls public captions (zero quota, sometimes
   IP-blocked). The server will transcribe recordings itself with Whisper
   overnight and use captions only as a fallback. Which files does the
   chapter extraction expect (`work/out/<id>.json`), and what shape, so the
   Whisper output can be written into the same place?

7. **Two machines, one channel.** List every step that must be true before
   the server's timer is switched on and the PC's is switched off, so the
   job never runs twice in one night, and what to check the next morning.

8. **Revocation and rotation.** If the server's token ever leaks, what is
   the exact sequence to revoke just that token in the Google account
   without breaking the PC's?

Answer in a numbered list that matches these numbers. Where you are not
sure, say so rather than guess.

**Paste to here.**
