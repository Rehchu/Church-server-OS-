# Test fixtures

- `firefox-policies-schema.json`: Firefox's enterprise-policy schema, copied
  unchanged from mozilla-firefox/firefox
  (`browser/components/enterprisepolicies/schemas/policies-schema.json`, main,
  Firefox 161.0a1, Oct 28 2026). It is covered by the Mozilla Public License
  2.0 (https://mozilla.org/MPL/2.0/). The tests validate the policy that
  `scripts/arise-browser-policies.py` writes against it, so a renamed or
  retired policy fails the suite instead of failing silently on the box.
  Refresh it when Firefox's major version moves on.
- `ubuntu-24.04.5-live-server-grub.cfg`: `/boot/grub/grub.cfg` from
  `ubuntu-24.04.5-live-server-amd64.iso`, read from releases.ubuntu.com on
  Oct 29 2026. `tests/test_install_media.py` runs the boot-menu edit of
  `scripts/make-install-media.sh --full` on it. Refresh it with a new point release.
