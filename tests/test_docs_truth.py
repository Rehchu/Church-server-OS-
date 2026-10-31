"""The docs say what the code does.

Pins the parts a machine can check: every `arisectl` verb a doc names exists,
every timer in CLAUDE.md's table exists with that time (and every timer is in
the table), the directory is never under arisecenla.church, and the version
the README states is the one the code reports.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ([ROOT / "README.md", ROOT / "INSTALL.md", ROOT / "CLAUDE.md"]
        + sorted((ROOT / "docs").glob("*.md")) + sorted((ROOT / "installer").glob("*.md")))

# Named in docs as decided but not built yet (each doc says so): not a broken reference.
NOT_BUILT = {("node", None),            # docs/NODES.md: the two-node work, v0.8.1
             ("mail", "forwards")}      # docs/SECURITY.md: the internal mail server, decided, not built


def cli_verbs() -> dict:
    """verb -> (its sub-commands, or None, and whether the sub-command is required)."""
    out = {}
    for line in (ROOT / "cli" / "arisectl").read_text().splitlines():
        m = re.search(r'add_parser\("([a-z0-9-]+)"\)', line)
        if not m:
            continue
        ch = re.search(r'add_argument\("sub"([^)]*)\)', line)
        subs = set(re.findall(r'"([^"]+)"', re.search(r"choices=\[([^\]]*)\]", ch.group(1)).group(1))) if ch and "choices" in ch.group(1) else None
        required = bool(ch) and 'nargs="?"' not in ch.group(1)
        out[m.group(1)] = (subs, required)
    return out


class DocsTruth(unittest.TestCase):
    def test_every_arisectl_verb_in_the_docs_exists(self):
        verbs = cli_verbs()
        self.assertIn("doctor", verbs)
        bad = []
        for d in DOCS:
            for i, line in enumerate(d.read_text().splitlines(), 1):
                # in backticks, or a code line that starts with the command
                spans = re.findall(r"`([^`]*arisectl[^`]*)`", line)
                if re.match(r"\s*(sudo\s+)?arisectl\s", line):
                    spans.append(line)
                for span in spans:
                    for m in re.finditer(r"arisectl\s+([a-z][a-z0-9-]*)(?:\s+([a-z][a-z0-9-]*))?", span):
                        v, sub = m.group(1), m.group(2)
                        if (v, None) in NOT_BUILT or (v, sub) in NOT_BUILT:
                            continue
                        if v not in verbs:
                            bad.append(f"{d.relative_to(ROOT)}:{i}: no verb '{v}'")
                            continue
                        subs, required = verbs[v]
                        if subs and required and sub and sub not in subs:
                            bad.append(f"{d.relative_to(ROOT)}:{i}: '{v} {sub}' is not one of {sorted(subs)}")
        self.assertEqual(bad, [], "\n".join(bad))

    def test_the_timer_table_matches_the_units(self):
        text = (ROOT / "CLAUDE.md").read_text()
        table = text[text.index("## The timers"):text.index("Do not schedule anything during a service")]
        rows = re.findall(r"^\| ([^|]+) \| `([^`]+)` \|", table, re.M)
        self.assertGreater(len(rows), 10)
        named = set()
        for when, unit in rows:
            when = when.strip()
            if unit == "arise-monitor-off/on.timer":
                pairs = [("arise-monitor-off.timer", "23:00"), ("arise-monitor-on.timer", "06:00")]
            else:
                pairs = [(unit, when)]
            for u, w in pairs:
                f = ROOT / "config" / "systemd" / u
                self.assertTrue(f.exists(), f"{u} is in CLAUDE.md's table but not in config/systemd")
                named.add(u)
                cal = " ".join(re.findall(r"^OnCalendar=(.+)$", f.read_text(), re.M))
                if w == "hourly" or w == "monthly":
                    self.assertIn(w, cal, u)
                elif w.startswith("every ") and w.endswith(" min"):
                    n = w.split()[1]
                    self.assertRegex(cal, r"\*:0{0,2}/" + n + r"(?!\d)", u)
                else:
                    day = re.match(r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) ", w)
                    hhmm = re.search(r"(\d\d:\d\d)", w).group(1)
                    self.assertIn(hhmm + ":00", cal, f"{u}: CLAUDE.md says {w}, the unit says {cal}")
                    if day:
                        self.assertTrue(cal.startswith(day.group(1)), f"{u}: CLAUDE.md says {w}, the unit says {cal}")
        have = {p.name for p in (ROOT / "config" / "systemd").glob("*.timer")}
        self.assertEqual(sorted(have - named), [], "timers missing from CLAUDE.md's table")

    def test_the_directory_is_never_under_arisecenla_church(self):
        bad = []
        for d in DOCS + [ROOT / "site" / "index.html", ROOT / "site" / "boot.html"]:
            for i, line in enumerate(d.read_text().splitlines(), 1):
                if re.search(r"ad\.arisecenla\.church|AD\.ARISECENLA\.CHURCH", line) and d.name not in ("ANSWERS.md",) and not d.name.startswith("QUESTIONS"):
                    bad.append(f"{d.relative_to(ROOT)}:{i}")
        self.assertEqual(bad, [], "the realm is AD.ARISECENLA.COM (round 5, 1)")

    def test_the_readme_states_the_version_the_code_reports(self):
        init = (ROOT / "server" / "arise_server" / "__init__.py").read_text()
        version = re.search(r'VERSION = "([^"]+)"', init).group(1)
        codename = re.search(r'CODENAME = "([^"]+)"', init).group(1)
        readme = (ROOT / "README.md").read_text()
        self.assertIn(f'**v{version} "{codename}"', readme)
        top = re.search(r"^## (v\S+) \"([^\"]+)\"", (ROOT / "CHANGELOG.md").read_text(), re.M)
        self.assertEqual((top.group(1), top.group(2)), (f"v{version}", codename))

    def test_backup_retention_in_the_docs_is_the_configs(self):
        from_cfg = re.findall(r"^keep_(daily|weekly|monthly) = (\d+)", (ROOT / "config" / "arise.toml.example").read_text(), re.M)
        keep = dict(from_cfg)
        self.assertEqual((keep["daily"], keep["weekly"], keep["monthly"]), ("30", "12", "24"))
        stale = [str(d.relative_to(ROOT)) for d in DOCS
                 if d.name != "ANSWERS.md" and re.search(r"\b14/8/12\b|keep 14 daily", d.read_text(), re.I)]
        self.assertEqual(stale, [])


if __name__ == "__main__":
    unittest.main()
