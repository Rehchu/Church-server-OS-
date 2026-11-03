# The Arise repos on the server

Bradly (Oct 28): "We would need designated folders for all the repos or
download all the arise repos to the server and keep them synced with GitHub
and the server." His choices: two-way, every 15 minutes, commits pushed
automatically; the 8 Arise repos; one fine-grained GitHub token.

## Where they are

`/srv/arise/repos/<name>`, one working folder per repo in `[github] repos`:

| Repo | Size (checked out, Oct 28) | Pushes from the server |
|---|---|---|
| Church-server-OS- | small (main holds only a README; ariseOS is on its PR branch) | all |
| Arise-Youtube-Automation | 97 MB, 1,075 files | **branches only, never `main`** |
| ProjectBackups | 4.2 GB, 2,395 files | all |
| AriseHub | 3 MB, 456 files | **none: pull only** |
| arisechurch | 70 MB, 506 files | all |
| ai-chat-backups | 1.7 GB, 6,135 files | all |
| arise-youtube | 3 MB, 49 files | all |
| arise-church-backup | 68 MB, 382 files | all |

About 6 GB checked out, about 12 GB with history. The disk plan waits for the
Dell's specs on Friday.

**Why two repos are held back** (change it in `[repos.policy]` in arise.toml):
- **AriseHub**: a push to `main` deploys the live site through Cloudflare
  Workers Builds, and even a branch push leaves an undeployed preview version
  that blocks Cloudflare secret changes (AriseHub's own CLAUDE.md). The server
  pulls it and never pushes it.
- **Arise-Youtube-Automation**: its `main` (holds, worklist, runner) is edited on
  the PC (SERVER_HANDOFF.md). Branches made here are pushed; `main` is not.

These are not the automator job's checkout (`/srv/arise/automator`, `main`
only, read-only key) and not the search archive's clones
(`/srv/arise/archive`). The three stay independent, as the handoff requires.
Work in these folders; leave the other two alone.

## What the sync does, every 15 minutes

`arise-repos.timer` → `arise-repos.service`, as the user `arise-git`, never
during a service. For each repo:

- **Not here yet**: clone it.
- **New commits on GitHub, none here**: fast-forward. Uncommitted edits here stay; if
  they collide with the incoming change, the pull stops and says so.
- **Commits here, none new on GitHub**: push them, if the policy allows.
- **Both**: stop and tell Bradly (a push to his phone). No merge, no rebase, ever.
- **A new branch made here**: pushed with its upstream set, if the policy allows.

It never commits for anyone, never force-pushes, never runs a repo's hooks,
and **refuses a push** that carries a file over 100 MB (GitHub's limit) or,
in any commit of the push, something shaped like a credential (Google,
GitHub, Anthropic, AWS, Resend keys, private keys, token files, `.env`). A
secret added and removed again is still refused, because the history would
carry it. The refusal names the file, never the secret.

## The token (Bradly, once)

github.com → Settings → Developer settings → Personal access tokens →
**Fine-grained tokens** → Generate:
- Repository access: **only select repositories**, the 8 above.
- Permissions: **Contents: read and write** (Metadata: read is added for you).
- Expiry: up to a year. The 04:00 backup mirror uses the same token.

On the server: `sudo install -m 0600 /dev/stdin /etc/arise/secrets/github-token`,
paste the token, Enter, Ctrl+D. The sync unit receives it as a systemd
credential; the file stays root-only, and the token never sits in a URL or a
repo's config.

## Who can work in them

The group `arise-repos`: Bradly's accounts (`bradly`, `bradly.dyer`) join it
at setup. Folders are group-writable. Claude on the box works here, as Bradly,
and **commits only when he says**: a commit here goes to GitHub within 15
minutes (the box's CLAUDE.md, rule 13).

## Backups

The `repos` job backs up `/srv/arise/repos` nightly, for what GitHub does not
have yet: uncommitted edits and commits a policy holds back. Build output and
credential-shaped files are excluded.

## Commands

```
sudo arisectl repos status            each repo: policy, branch, ahead/behind, uncommitted, last result
sudo arisectl repos sync              run a sync now (as arise-git, through the unit)
arisectl repos sync --dry-run         what a sync would do, changing nothing
sudo arisectl repos setup             the folders, the user and group (again any time)
```

The dashboard: `GET /api/repos`, and `POST /api/repos/sync` starts the unit.
