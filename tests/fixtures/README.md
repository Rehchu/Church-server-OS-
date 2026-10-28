# Test fixtures

- `firefox-policies-schema.json`: Firefox's enterprise-policy schema, copied
  unchanged from mozilla-firefox/firefox
  (`browser/components/enterprisepolicies/schemas/policies-schema.json`, main,
  Firefox 161.0a1, Oct 28 2026). It is covered by the Mozilla Public License
  2.0 (https://mozilla.org/MPL/2.0/). The tests validate the policy that
  `scripts/arise-browser-policies.py` writes against it, so a renamed or
  retired policy fails the suite instead of failing silently on the box.
  Refresh it when Firefox's major version moves on.
