# Mac checklist — one sheet per Mac

Print one of these per Mac. Keep it in the Media folder on the server when done.

| | |
|---|---|
| Computer name (label on the Mac) | `________________` (15 chars max, letters/digits/dashes) |
| macOS version (Apple menu → About This Mac) | `________________` |
| Which kind | ☐ new / empty Mac   ☐ Mac with people already on it |
| Local accounts on it | `________________  ________________  ________________` |
| Date | `____ / ____ / 2026` |
| Done by | `________________` |

## Before (both kinds)

- [ ] Mac plugged into **Ethernet** (not Wi‑Fi)
- [ ] `dig +short _ldap._tcp.ad.arisecenla.church SRV` prints a line in Terminal
- [ ] Automatic date & time on
- [ ] The `mac/` folder from the repo copied to the Mac (Desktop is fine)
- [ ] The `ARISE\administrator` password to hand
- [ ] For `enroll-mac.sh` over SSH: `ssh bradly@arise-server` works without a password (`ssh-copy-id` first)

## A new or empty Mac

- [ ] `sudo ./bind-mac.sh --computer-name <NAME> --test-user <someone>` finished with "Bound."
- [ ] `sudo ./enroll-mac.sh --computer-name <NAME> --no-migrate` (installs the two LaunchAgents; no local people to copy)
- [ ] Login Options → "Name and password" set
- [ ] A domain user logged in once on Ethernet; `/Volumes/<user>` appeared by itself

## A Mac with people already on it

- [ ] Everyone logged **out** (fast user switching counts)
- [ ] Each person's data size noted: `du -sh /Users/<name>` → `________ GB`
- [ ] Photos Library present? size `________ GB` (it stays local afterwards)
- [ ] Anything in Keychain they need (Wi‑Fi passwords, app logins) written down or exported
- [ ] `sudo ./enroll-mac.sh --computer-name <NAME> --dry-run` reviewed: the right people listed, nobody missing
- [ ] `sudo ./enroll-mac.sh --computer-name <NAME>` finished with "Done"
- [ ] One-time passwords written down and handed over in person; `/var/root/arise-enrol-passwords-*.txt` deleted
- [ ] Each migration manifest (`ARISE-MIGRATION-<date>.txt` on the old Desktop) compared: before vs after counts match, allowing for the skip list
- [ ] Size moved: `________ GB`, time taken: `________ min`
- [ ] "LEFT FOR A HUMAN" list from the script is empty, or each line done

## After (first domain login of each person, Ethernet still in)

- [ ] Logged in as the domain user; `/Volumes/<user>` mounted by itself
- [ ] Desktop and Documents show the migrated files (they are links into the share)
- [ ] Changed the one-time password: dashboard → flame menu → Change Password
- [ ] Proclaim / StreamYard / OBS / whatever this Mac is for opens its data
- [ ] Mail signed in again
- [ ] A test file saved on the Desktop appears on the server under `/srv/arise/homes/<user>/Desktop`
- [ ] `~/Library/Logs/arise-home-sync.log` has a "sync done" line
- [ ] Logged out and back in **on Wi‑Fi** — login still works (mobile account cached)
- [ ] Person shown where their files are, shown the dashboard address, and told the old account stays for two weeks

## Two weeks later

- [ ] No missing-file reports; no "conflicts" folder under `~/Library/Application Support/Arise/` with anything in it (or it was looked at)
- [ ] Old local account removed by Bradly (System Settings → Users & Groups), with "Don't change the home folder" chosen the first time, deleted for real the second
