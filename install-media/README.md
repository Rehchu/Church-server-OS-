# The ariseOS install disc (download)

`ariseos-addon.iso` is the small add-on disc (about 2 MB, label CIDATA). Attach it next to the
plain Ubuntu Server 24.04 ISO (VirtualBox: a second optical drive) and Ubuntu's installer asks
"Continue with autoinstall?": type `yes`. `ariseos-addon.zip` is the same for a Rufus USB stick
(unzip onto the stick's root). Steps: installer/MAKE-USB.md and docs/VIRTUALBOX.md.

To download on GitHub: open the file, then **Download raw file** (the arrow at the top right).
Check it against `SHA256SUMS` if you like (PowerShell: `Get-FileHash ariseos-addon.iso`).

**What's on it:** the code of the commit it was made from (`/arise/VERSION` on the disc names it),
the autoinstall file and its checksums. **No keys and no passwords.** It is safe to share.

**Not here, on purpose:** the private disc (`ariseos-addon-private.iso`, ANSWERS H9), which also
carries the church's Resend key. This repository is public, so that one stays on Bradly's PC and
USB stick only; `.gitignore` refuses it.

It goes stale as the code moves on: make a new one with `bash scripts/make-install-media.sh`
and copy `dist/ariseos-addon.*` here, or ask Claude to.
