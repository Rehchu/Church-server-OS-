# Claude on the box

Bradly (Oct 28): "The chat will be accessible from Claude desktop when it's
installed on there. He can work on it from the server when it's up." So the
sessions he already has, the automator chat among them, carry on from ariseOS.
Claude on the box is Bradly's only (round 4, 44).

Checked against Anthropic's docs on Oct 28: code.claude.com/docs/en/desktop-linux
and code.claude.com/docs/en/claude-code-on-the-web.

## Three ways in

| Way | What it is | Where | Notes |
|---|---|---|---|
| **Claude Desktop** | Anthropic's desktop app, **Linux beta** (Ubuntu 22.04+, amd64/arm64): Chat, Cowork and Claude Code tabs | the closet monitor, opened from Assistants; on Arise-Home, his own desktop | Installed from Anthropic's apt repo, key fingerprint checked (`scripts/arise-claude-desktop-setup`, run by `install.sh --kiosk`). On the shared monitor it opens on Bradly's click only, asks him to sign in each time (the monitor's keyring is never unlocked, so no one inherits his sign-in) and closes when the screen locks. No Cowork on the closet box (it needs a QEMU/KVM virtual machine); no Computer Use or dictation in the Linux beta. |
| **claude.ai in Firefox** | the same account in the browser: claude.ai and claude.ai/code | Assistants → Claude, or any tab | Works today. claude.ai/code lists every web session, the automator chat included, and continues it. |
| **The `claude` command** | Claude Code in the Terminal app or over SSH | the box itself | Installed by `install.sh` (6e), signed in once with `/login` to Bradly's claude.ai account. `claude --teleport` pulls a web session down to the box; `claude -p "…" --cloud <session-id>` sends a follow-up to a web session from here. |

## Your account has full access (Oct 28)

"My login of Claude must have full file access to modify, update." So the box's
owner account, yours (`[owner] user` in arise.toml, set by install.sh from the
account that ran sudo, or `sudo arisectl owner setup NAME`):

- is in every ariseOS group (sudo, arise-conf, arise-repos, arise-claude, docker,
  adm, systemd-journal) and uses **sudo without a password**
  (`/etc/sudoers.d/arise-owner`, checked with `visudo` before it goes in);
- runs the 02:05 job (docs/AUTOMATOR.md), so its folders and the token are yours;
- has Claude Code set up for the box (`~/.claude/settings.json`, merged, never
  replaced): `/opt/arise`, `/srv/arise`, `/etc/arise`, `/var/lib/arise`,
  `/var/log/arise` and `/mnt/synology` added, file edits accepted without asking.
  Commands still ask; if you want no prompts at all, run `claude --permission-mode bypassPermissions`.
  The one thing it is told not to read is a credential file (`/etc/arise/secrets/`,
  `SAFE-CARD.txt`, the apps' `.env`): a credential must never enter a chat,
  your own rule. It can still check that a token is there and its mode.
- is the account Claude Desktop opens as on the closet monitor, so the app's
  Claude Code tab can change the box. It still opens only on your click,
  asks you to sign in each time (the keyring is never unlocked), and closes when
  the screen locks. Anyone else uses Claude in Firefox with their own account,
  with no access to the box.

Two cautions that come with it: anyone who has your Linux password, or who
reaches the monitor while Claude Desktop is open, can do anything on the box.
And `/opt/arise` is what Software Update replaces: change the OS in
`/srv/arise/repos/Church-server-OS-` (it syncs to GitHub) rather than in
`/opt/arise`, or the next update undoes it.

## The automator chat, from the server

The automator chat is a Claude Code **web session**: it runs in Anthropic's
cloud, and its commits and pushes happen there, through GitHub's connection to
that session, not from the box. So working on it from ariseOS needs nothing
new on the server.

- **Easiest:** open it in Claude Desktop's Code tab or at claude.ai/code in
  Firefox, and carry on. Its first job: **push the revision commit** ("Per-machine
  job state, server cap 6,000"); GitHub's `main` is still at "Server-ready automator".
- **Pulling it into the box's terminal** (`claude --teleport <session-id>`) is a
  copy, not the session: work done there stays local. Anthropic's docs say it
  needs a clean checkout of the same repo, the session's branch pushed, the
  same claude.ai account, and a git fetch that never prompts.

**The one rule that protects the nightly job:** never teleport into, check
out a branch in, or edit **`/srv/arise/automator/ARISE_YouTube_Updater`**.
That checkout is the job's (it runs as your account with a read-only key, `main` only); a branch
or a change there makes the next 02:05 pull fail and the night runs plan-only.
For hands-on work on the box, use a separate clone in Bradly's own home, with
his own GitHub access (for example `gh auth login`):

```
git clone https://github.com/Rehchu/arise-youtube-automation.git ~/work/arise-youtube-automation
cd ~/work/arise-youtube-automation && claude --teleport
```

The archive's clones (`/srv/arise/archive/`, docs/ARCHIVE.md) are read-only
mirrors too; they are for searching, never for working in.

## What was not verified here

Claude Desktop did not run in this sandbox (no display, and Anthropic's apt
repository was not installed here). The commands follow Anthropic's page as
fetched on Oct 28; the first real run is on the box. The beta's behaviour
under cage (a single-window Wayland kiosk) is untested: if it misbehaves
there, Claude stays available in Firefox and as the `claude` command, and
Arise-Home (a full desktop) is the natural home for the app.
