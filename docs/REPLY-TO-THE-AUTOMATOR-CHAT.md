# Reply to the automator chat (paste from the line below)

---

ariseOS has carried out SERVER_HANDOFF.md (8326b4a). Nothing on the server
flips `runner.json`; the PC stays the runner. Status and findings:

**Built** (Church-server-OS branch `claude/arise-server-os`): your
`arise-nightly.sh` unchanged; your section 7 units under ariseOS's names
`arise-automator.service` / `.timer` (same contents: `User`, `EnvironmentFile`,
`ProtectSystem=strict`, `Persistent=false`, 02:05 America/Chicago); a
`arise-automator-preview.service` that runs the wrapper with `--plan-only` as
the same user behind the same lock; `/etc/arise/arise.env`; logrotate for
`last-run.log`; a read-only deploy key with GitHub's published host keys
pinned; `arisectl automator setup | signin | preview | cutover`.
`signin` runs `authorize_headless.py` as the job's user. `cutover` shows your
section 9 list with what the server can check ticked.

**Placed differently, same variables** (least privilege on a box that also
runs the domain and the backups):

| | Handoff | ariseOS |
|---|---|---|
| user | `arise` | `arise-yt` (`arise` already owns the Docker apps' data) |
| `ARISE_REPO` | `/opt/arise/ARISE_YouTube_Updater` | `/srv/arise/automator/ARISE_YouTube_Updater` |
| `ARISE_TOKEN`, `ARISE_CLIENT_SECRET` | `/etc/arise/secrets/` | `/etc/arise/secrets/youtube/` (0700 arise-yt) |
| `ARISE_STATE_DIR` | `/var/lib/arise` | `/var/lib/arise/automator` |
| `ReadWritePaths` | the three above | the three above, ariseOS paths |

No backup job takes `/etc/arise/secrets/youtube`, and the automator job also
excludes `**/token.json`, `**/client_secret*.json` and `**/deploy_key*`. A
test in ariseOS scans its own repo for real `1//0`, `GOCSPX-` and `ya29.`
shapes. Your repo's `main` scanned clean too; the only hit was
SERVER_HANDOFF.md naming the prefixes.

**Section 3, answered:** all four in-checkout state files are **tracked** on
`main`: `_starfix_state.json`, `_tx_run.json`, `_retitle_report.txt` and
`_ss_fix_report.txt`, plus **162 files in `transcripts/`**. Per your note,
ariseOS untracks nothing. A proposal for Bradly to decide on the PC: either
untrack them (`.gitignore` + `git rm --cached`) or move those scripts' writes
into `ARISE_STATE_DIR`.

**Section 8, the numbers on ariseOS's cap:** enabled tonight are
`sunday-playlist-reassign` (3,500), `vertical-twin-titles` (400),
`pull-transcripts` (2,500) and `strip-markdown-stars` (2,000). Under 4,000,
reassign runs alone and nothing else fits. With it off, 400 + 2,500 fit and
stars does not. Under 2,000 (Pacific Sun/Mon), only `vertical-twin-titles`
fits. So `strip-markdown-stars` will not run on the server at the current
caps unless reassign is off and pull-transcripts is skipped that night.

**One bug found in ariseOS and fixed:** its old "preview" passed `--dry-run`
to `arise_daily.py` and ran it as root. Previews now go through the unit as
`arise-yt` with `--plan-only`, so a root-owned refreshed token can never
happen.

**Not done, waiting on Bradly:** Publish the OAuth app, create the
"ariseOS server" Desktop client, add the deploy key, sign in once, decide on
the tracked state files and on `sunday-playlist-reassign`, and say where
Whisper's recordings come from. Nothing here has run against the real
channel yet: the server isn't built, and this sandbox can't reach Google.
