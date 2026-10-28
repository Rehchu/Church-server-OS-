# The Finder: Trash, Previous Versions, Get Info, Recents, the editor, Open on my Mac

What v0.8 "Exodus" added to the Finder (app 01), from Bradly's round 3 answers
(docs/ANSWERS.md): the everyday things Windows Explorer and the macOS Finder
have that the portal did not. Everything here is scoped the same way the
Finder always was: `files.roots(who)` decides what a person may reach, so a
member only ever sees their own home and the shares their groups allow, and
an administrator sees everything.

## Trash (answer 1)

Deleting is no longer a delete. In the portal, **Move to Trash** (the context
menu, the File menu, or Delete / ⌘⌫ on a selected item) asks for the item's
name typed and then moves it into `<share>/.Trash/<user>/<its path inside the
share>`. On a Mac, deleting a file on any share lands in the same folder: every
share on this box carries Samba's `recycle` module
(`config/samba/smb.conf.template`, `shares.add_share` for new ones) with
`recycle:repository = .Trash/%U` and `recycle:keeptree`, so the two Trashes are
one. The Synology's `recordings` share keeps the Synology's own `#recycle`
instead, and says so in the template.

- **Trash** in the Finder sidebar lists your own items (an administrator sees
  everyone's, with who deleted it and whether it came from a Mac). **Put Back**
  returns an item to where it was; if that name is taken now, it comes back as
  `name (put back).ext` and the toast says so.
- **Empty Trash…** is an administrator's click and asks for the share's name
  typed. It takes every user's items in that share. The nightly backup skips
  `.Trash` (`config/backups.yaml.example`), so emptied is gone.
- `arise-trash.timer` runs `arisectl trash sweep --quiet` at 04:30 and removes
  anything that has sat in a Trash for 30 days. `arisectl trash list` shows
  what is there; `arisectl trash sweep --dry-run` shows what the next sweep
  would take; `arisectl trash empty <share>` asks for the name again.
- Naming follows Samba's: a second copy of `x.pdf` in the Trash is
  `Copy #1 of x.pdf`, so the Mac's and the portal's deletes never collide.
  The portal keeps a small manifest per user (`.arise-trash.json`) with the
  original path and who deleted what; a Mac's delete has no manifest and is
  shown with its keeptree path as the original.

Routes: `GET /api/files/trash`, `POST /api/files/trash` (root, path, confirm),
`POST /api/files/trash/restore` (base, user, rel), `POST /api/files/trash/empty`
(admin; share, confirm).

**smb.conf.** The template is the only thing this changes. On a box that is
already installed, the recycle lines are appended by hand to each share block
in `/etc/samba/smb.conf` (copy first, `testparm -s` after, CLAUDE.md rule 4);
`vfs objects` inside a share replaces the global list, which is why each block
repeats `acl_xattr fruit streams_xattr` before `recycle`.

## Previous Versions (answer 2)

Right-click a file, **Previous Versions…**: every nightly copy the restic
backup holds (`restic find --json`), with the backup time, the file's own date
and its size. **Restore** brings that copy back *beside* the live file as
`name (restored 2026-10-27).ext`; nothing is ever overwritten, and a second
restore of the same day is numbered. The modal names the backup job that
covers the file (homes, shares, automator, config) and says plainly when
nothing does: the recordings on the Synology are not in the restic backup.
Members may restore into their own roots; a read-only share (graphics for
Staff) says to ask the media team.

Routes: `GET /api/files/versions?root&path`, `POST /api/files/versions/restore`
(root, path, snapshot). `backups.versions_of`, `backups.restore_version`,
`backups.restored_name`, `backups.job_for`, `backups.parse_find`.

## Get Info (answer 16)

Kind, size (a folder's size is counted for three seconds and then says "at
least"), owner and group, created and modified, where it is, the `smb://`
address a Mac opens (with Copy), and **who can open it**: the share's valid
users and write list in words, or "a home folder: only this person". From
there, Previous Versions and, on a Mac, Open on my Mac.
`GET /api/files/info?root&path`.

## Recents (answer 16)

**Recents** in the sidebar: every file changed in the last seven days across
what you may browse, newest first, 200 at most, cached a minute. Right-click
for Quick Look, Show in folder, Edit, Download, Get Info, Previous Versions,
Share Link. `GET /api/files/recent`.

## The text editor (answer 15)

Double-click a `.txt .md .csv .json .yaml .yml .toml .log` file (1 MB or less)
and it opens in place: a plain editor, ⌘S / Ctrl+S saves, Tab indents, an
unsaved-changes guard on Close and Escape, and for Markdown a **Preview** tab
rendered on the server (`markdown` package; every `<` in the source is escaped
first and script-ish links are removed, so no HTML from a file ever runs in
the dashboard). Saving checks the file has not changed under you since you
opened it. Other kinds keep Quick Look. Read-only shares open read-only.
`GET /api/files/text`, `PUT /api/files/text` (root, path, text, mtime),
`POST /api/files/text/preview`.

## Compress (answer 16)

**Compress** on a file or folder downloads a zip (deflated, built in a temp
folder). Over 2 GB it refuses with the size and says to open it on the share.
`GET /api/files/zip?root&path`.

## Open on my Mac (answer 18)

On a Mac, the Finder toolbar and the folder's context menu carry **Open on my
Mac**: the browser opens `smb://arise-server.ad.arisecenla.church/<share>/<path>`
and the Mac's own Finder shows the same folder. A home is reached as
`smb://…/<user>`, Samba's `[homes]` answering to the person's name; a path
under `/srv/arise/shares` with no narrower share is reached through `shares`.
Folders no share reaches (the automator, the apps) say so. The button is
hidden on anything that is not a Mac. `finder.smb_path` is the pure mapping.

## Fonts (answer 39)

`Media/Fonts` on the media share (the installer makes it with a README) holds
the fonts the Proclaim graphics use. `mac/arise-home-sync.sh` installs any
`.ttf .otf .ttc` there that is newer than the Mac's copy into
`~/Library/Fonts` on its run, for anyone in the Media group; a person without
access to the share gets one log line, not an error. `mac/enroll-mac.sh` step
5b does a first copy into `/Library/Fonts` for the whole Mac when the share
can be mounted during enrolment, and leaves a TODO line when it cannot.

## Every home starts the same (Bradly, Oct 28)

A home folder is made with **Documents, Photos, Videos, Music, Downloads**
inside it the first time the person signs in: the dashboard's login calls
`files.ensure_home`, and the `[homes]` share's `root preexec` makes the same
five when a Mac connects first. Nothing that exists is touched.

For the administrator, the Finder sidebar carries an **Everyone** section:
*All Documents*, *All Photos*, *All Videos*, *All Music*, *All Downloads*.
Each shows every person's folder of that name side by side, each row labelled
with whose it is; double-click opens the item where it lives, and the context
menu offers Show in their folder, Get Info, Previous Versions and Move to
Trash. The route (`GET /api/files/all?folder=`) is administrator-only; a
member's roots never include another person's home, so a member never sees
one (pinned in the tests).

## Share links live until removed (Bradly, Oct 28)

A share link no longer expires unless a life is picked for it: the Share
dialog's default is "never (until removed)", with 1 day to a year as choices,
and `[links] days = 0` in `arise.toml` is that default (`max_days = 365` caps a
chosen life). The Shared Links list shows "never" for such a link; Remove
still stops it at once. `arisectl link sweep` only drops links that were given
a date.

## Uploads to 10 GB, resumable (Bradly, Oct 28)

Upload in the portal takes files up to **10 GB**. Anything over 8 MB goes up in
8 MB pieces (`POST /api/files/upload/start`, `PUT /api/files/upload/chunk`,
`POST /api/files/upload/finish`): each piece lands at the end of a
`.arise-upload-<token>.part` file beside the destination, and a toast shows
the progress. If the connection drops or the laptop closes, nothing is lost:
the browser retries on its own, and picking the **same file again later** (same
name, size and date, same folder, same person) resumes from where it stopped,
because `start` finds the part and answers with how much it already has. The
final rename happens only when every byte has arrived and the name is still
free. Part files nobody has touched for three days are dropped by the daily
Trash sweep. Smaller files use the plain upload as before.

## What is not verified here

No real Samba, restic, Mac or Synology was in the session: the recycle and
preexec lines were not run through `testparm`, a 10 GB upload was not sent
(the chunk path was exercised with a small file against the demo server and
the rules are pinned in the tests), `restic find` and `restore` were exercised
only through their parsers and the demo samples, and the font sync was not run
on a Mac. The portal paths (Trash, Put Back, Empty, Previous Versions, Get
Info, Recents, the editor, Compress, Open on my Mac) were walked with
Playwright on the demo server as an administrator and as a member.
