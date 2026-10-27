# Mac checklist — one sheet per Mac

Print one of these per Mac. Keep it in the Media folder on the server when done.

| | |
|---|---|
| Computer name (label on the Mac) | `________________` (15 chars max, letters/digits/dashes) |
| macOS version (Apple menu → About This Mac) | `________________` |
| Local account being migrated | `________________` |
| Domain account (new) | `________________` |
| Date | `____ / ____ / 2026` |
| Done by | `________________` |

## Before

- [ ] Mac plugged into **Ethernet** (not Wi‑Fi)
- [ ] `dig +short _ldap._tcp.ad.arisecenla.church SRV` prints a line in Terminal
- [ ] Automatic date & time on
- [ ] The domain user exists: `arisectl user list` on the server shows them, and their home folder exists
- [ ] Local user's data size noted: `du -sh /Users/<local>` → `________ GB`
- [ ] Photos Library present? size `________ GB` (it stays local afterwards)
- [ ] The person knows their new username and has set a password (`arisectl user passwd`)
- [ ] Anything in Keychain they need (Wi‑Fi passwords, app logins) written down or exported

## Bind

- [ ] `sudo ./bind-mac.sh --computer-name <NAME> --test-user <domainuser>` finished with "Bound."
- [ ] `dsconfigad -show` lists the domain and the computer name
- [ ] Login Options → "Name and password" set
- [ ] `/Library/LaunchAgents/com.arisechurch.mounthome.plist` and `/usr/local/arise/mount-home.sh` installed

## Migrate

- [ ] Local user logged **out**
- [ ] `--dry-run` reviewed
- [ ] `sudo ./migrate-mac-user.sh --from <local> --to <domain>` finished with "Finished."
- [ ] Manifest compared: before vs after counts match (allowing for the skip list)
- [ ] Size moved: `________ GB`, time taken: `________ min`

## After (first domain login, Ethernet still in)

- [ ] Logged in as the domain user; `/Volumes/<user>` mounted by itself
- [ ] Desktop and Documents show the migrated files (they are links into the share)
- [ ] Proclaim / StreamYard / OBS / whatever this Mac is for opens its data
- [ ] Mail signed in again
- [ ] A test file saved on the Desktop appears on the server under `/srv/arise/homes/<user>/Desktop`
- [ ] Logged out and back in **on Wi‑Fi** — login still works (mobile account cached)
- [ ] Person shown where their files are and told the old account stays for two weeks

## Two weeks later

- [ ] No missing-file reports
- [ ] Old local account removed by Bradly (System Settings → Users & Groups), with "Don't change the home folder" chosen the first time, deleted for real the second
