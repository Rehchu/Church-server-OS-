# config/samba — what install.sh does with the template

`samba-tool domain provision` writes its own `/etc/samba/smb.conf`. It refuses
to run if one already exists, and it does not know about our shares. So the
installer does not ship a whole file; it provisions first, then merges:

1. **Appends** everything from the `# >>> arise-server shares` marker down
   (`[homes]`, `[shares]`) to the end of `/etc/samba/smb.conf`. The marker is
   how it knows it already did this, so a second run changes nothing.
2. **Inserts** the Mac lines (`vfs objects = acl_xattr fruit streams_xattr` and
   the `fruit:` options) under `[global]`, once, only if `fruit:model` is not
   already there.
3. Runs `testparm -s`. If that fails it stops and tells you which backup to
   restore (`/etc/samba/smb.conf.bak.<timestamp>`).

To change a share, edit `/etc/samba/smb.conf` on the server (not the
template) and `smbcontrol all reload-config`. Then copy the change back into
the template here so the next fresh install carries it.

Why `fruit` matters: without it Macs copying to the share get Finder errors
(-36, -43), lose Finder tags and resource forks, and Time Machine refuses the
share. Every `fruit:` line in the template has a comment saying what it does.

Why `.local` is never used: macOS owns `.local` for Bonjour. A domain called
`arise.local` makes Macs time out on every lookup. The realm is
`AD.ARISECENLA.CHURCH`, a subdomain of the church's own domain.
