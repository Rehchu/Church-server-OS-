"""The Mac side, without a Mac (docs/MACS.md).

macOS ships bash 3.2, so the scripts in mac/ may use nothing newer. These tests do two things:

* read the scripts for what bash 3.2 cannot run (bash 4 features, and the one that bites quietly:
  an empty "${a[@]}" under `set -u` is an unbound-variable error before bash 4.4), and for the
  ordering rules that keep the helper safe;
* run the helper's own functions (taken out of the file) with stand-ins for the macOS commands
  (dscl, stat -f, sysadminctl, fdesetup, softwareupdate) on PATH.

They run under the bash named by ARISE_BASH32 when it is set (a bash 3.2.57 built from source is
the real test), else under this machine's bash, which proves the logic but not the version.
"""
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAC = ROOT / "mac"
HELPER = MAC / "helper" / "arise-mac-helper"
SCRIPTS = [HELPER, MAC / "helper" / "enrol.sh", MAC / "helper" / "tasks" / "nextcloud.sh", MAC / "bind-mac.sh",
           MAC / "migrate-mac-user.sh", MAC / "enroll-mac.sh", MAC / "mount-home.sh", MAC / "arise-home-sync.sh"]
BASH = os.environ.get("ARISE_BASH32") or shutil.which("bash")
# Arrays these scripts create with elements and never empty, so a plain "${a[@]}" is safe there.
ALWAYS_FULL = {"opts", "RSYNC_META"}


def functions(src: str, *names: str) -> str:
    """The text of the named shell functions, one-liners or blocks ending in a line `}`."""
    out, lines = [], src.splitlines()
    for n in names:
        i = next(k for k, line in enumerate(lines) if line.startswith(f"{n}() {{"))
        first = re.sub(r"\s+#.*$", "", lines[i]).rstrip()
        if first.endswith("}"):                       # a one-liner
            out.append(lines[i])
            continue
        j = next(k for k in range(i + 1, len(lines)) if lines[k] == "}")
        out.append("\n".join(lines[i:j + 1]))
    return "\n".join(out)


class Bash32Rules(unittest.TestCase):
    def test_every_script_parses(self):
        for f in SCRIPTS:
            r = subprocess.run([BASH, "-n", str(f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{f.name}: {r.stderr}")

    def test_nothing_newer_than_bash_32(self):
        newer = {
            r"\bdeclare -A\b|\blocal -A\b": "associative arrays (bash 4)",
            r"\$\{[A-Za-z_]+(,,|\^\^)\}": "case conversion ${x,,} (bash 4)",
            r"\bmapfile\b|\breadarray\b": "mapfile (bash 4)",
            r"\|&": "|& (bash 4)",
            r"&>>": "&>> (bash 4)",
            r";;&": ";;& (bash 4)",
            r"\bcoproc\b": "coproc (bash 4)",
            r"\b(local|declare) -n\b": "namerefs (bash 4.3)",
            r"\bwait -n\b": "wait -n (bash 4.3)",
            r"@[QEPAa]\}": "${x@Q} transformations (bash 4.4)",
            r"\[\[? -v ": "-v tests (bash 4.2)",
            r"printf '%\(": "printf %(...)T (bash 4.2)",
        }
        for f in SCRIPTS:
            src = f.read_text()
            for rx, what in newer.items():
                hits = [i + 1 for i, line in enumerate(src.splitlines()) if re.search(rx, line) and not line.lstrip().startswith("#")]
                self.assertFalse(hits, f"{f.name}:{hits}: {what}")

    def test_no_bare_array_expansion_under_set_u(self):
        # macOS's bash 3.2: `set -u; a=(); echo "${a[@]}"` is "a[@]: unbound variable" (fixed in
        # bash 4.4, CHANGES a.). ${a[@]+"${a[@]}"} is the form that works in every version.
        for f in SCRIPTS:
            src = f.read_text()
            if not re.search(r"^set -[a-z]*u", src, re.M):
                continue
            for i, line in enumerate(src.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                for m in re.finditer(r'(?<!\+)"\$\{([A-Za-z_]+)\[@\]\}"', line):
                    self.assertIn(m.group(1), ALWAYS_FULL, f"{f.name}:{i}: bare \"${{{m.group(1)}[@]}}\" under set -u")

    def test_the_guarded_form_keeps_words_and_survives_empty(self):
        r = subprocess.run([BASH, "-c", 'set -u; e=(); a=("OBS Studio" x); n(){ echo $#; }; n ${e[@]+"${e[@]}"}; n ${a[@]+"${a[@]}"}'],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["0", "2"])


class HelperOrdering(unittest.TestCase):
    src = HELPER.read_text()

    def test_tasks_never_read_the_servers_answer(self):
        self.assertIn('"t_$kind" "$id" "$rest" </dev/null', self.src)

    def test_retire_removes_its_files_before_it_unloads_itself(self):
        r = self.src[self.src.index("t_retire() {"):]
        self.assertLess(r.index("rm -rf /Library/LaunchDaemons/com.arisechurch.helper.plist"), r.index("launchctl bootout"))
        self.assertIn("launchctl bootout system/com.arisechurch.helper", r)

    def test_removal_checks_the_record_not_sysadminctls_exit_code(self):
        rm = self.src[self.src.index("t_remove_profile() {"):self.src.index("t_convert_local() {")]
        self.assertNotIn("sysadminctl -deleteUser \"$user\" >>\"$LOG\" 2>&1 ||", rm)
        self.assertIn('if ! dscl . -read "/Users/$user" >/dev/null 2>&1; then', rm)
        self.assertIn("in_use", rm)

    def test_ariseadmin_keeps_the_new_password_before_setting_it(self):
        a = self.src[self.src.index("t_ariseadmin() {"):self.src.index("t_filevault() {")]
        self.assertLess(a.index('> "$p"'), a.index("sysadminctl -addUser"))
        self.assertIn('dscl . -passwd /Users/ariseadmin "$cur" "$pw"', a)
        self.assertIn('value@$p', a)                       # from the file, never the command line

    def test_enrol_reads_the_whole_script_before_running(self):
        e = (MAC / "helper" / "enrol.sh").read_text()
        self.assertTrue(e.rstrip().endswith('main "$@" </dev/null'))
        self.assertLess(e.index("main() {"), e.index('step "1. '))
        self.assertIn('"$BASE/arise-mac-helper" </dev/null', e)

    def test_bind_does_not_ask_dig_for_a_scoped_domain(self):
        b = (MAC / "bind-mac.sh").read_text()
        self.assertIn("dscacheutil -q host -a name", b)
        self.assertNotIn('dig +short "$DC_HOST"', b)

    def test_migrate_uses_only_flags_this_rsync_has(self):
        m = (MAC / "migrate-mac-user.sh").read_text()
        self.assertNotIn("-aHX", m)
        self.assertIn("--extended-attributes", m)


class Round7(unittest.TestCase):
    """Round 7's Mac answers, read from the scripts (docs/ANSWERS.md, Round 7)."""
    src = HELPER.read_text()
    enrol = (MAC / "helper" / "enrol.sh").read_text()

    def test_no_screen_lock_and_no_automatic_sign_out(self):
        # rows 28 and 29: never set either, anywhere on the Mac side
        for f in SCRIPTS:
            s = f.read_text()
            for key in ("askForPassword", "autoLogOutDelay", "idleTime", "screensaver"):
                self.assertNotIn(key, re.sub(r"#.*", "", s), f"{f.name}: {key}")

    def test_mac_settings(self):
        ms = self.src[self.src.index("t_mac_settings() {"):]
        ms = ms[:ms.index("\n}\n")]
        self.assertIn("sysadminctl -guestAccount on", ms)                                 # row 33
        self.assertIn("restrict-store-require-admin-to-install -bool true", ms)           # row 30
        self.assertNotIn("dseditgroup -o edit -a", ms)                                     # nobody is made an admin

    def test_notices_are_never_parsed_as_applescript(self):
        sn = functions(self.src, "show_notice")
        self.assertIn("'on run argv'", sn)
        self.assertIn('"$3" "$4"', sn)
        self.assertNotIn('\\"$3', sn)

    def test_apps_check_the_signature_first(self):
        a = self.src[self.src.index("t_apps() {"):]
        a = a[:a.index("\n}\n")]
        self.assertLess(a.index("pkg_ok"), a.index("installer -pkg"))
        p = functions(self.src, "pkg_ok")
        self.assertIn("pkgutil --check-signature", p)
        self.assertIn("Developer ID Installer", p)

    def test_service_pause(self):
        # row 92: a service pauses Nextcloud in every session, and the next visit without one reopens it
        self.assertRegex(self.src, r"\n  HOLD\*\) nc_pause;")
        main = self.src[self.src.index("HOLD*) nc_pause"):]
        self.assertIn("nc_resume", main)
        self.assertIn('"$DB/nc-paused"', functions(self.src, "nc_pause"))

    def test_enrol_keeps_the_name_and_backs_up_first(self):
        # row 35: the name changes only with --name
        i = self.enrol.index('scutil --set ComputerName "$NAME"')
        self.assertIn('if [ -n "$NAME" ]', self.enrol[max(0, i - 300):i])
        self.assertIn('scutil --get ComputerName', self.enrol)
        # row 6: Time Machine first when a destination answers, before the bind
        self.assertLess(self.enrol.index("tmutil startbackup --block"), self.enrol.index('bash "$TMP/bind-mac.sh"'))
        self.assertIn("--no-backup", self.enrol)

    def test_dns_filter_keeps_the_church_domain_on_the_server(self):
        d = self.src[self.src.index("t_dnsfilter() {"):]
        d = d[:d.index("\n}\n")]
        self.assertIn("networksetup -setdnsservers", d)
        self.assertIn("dns-before", d)                                                      # reversible
        self.assertNotIn("/etc/resolver/ad.arisecenla.com", re.sub(r"#.*", "", d).replace('[ -f "/etc/resolver', ""))   # left alone


@unittest.skipUnless(BASH, "no bash here")
class HelperFunctions(unittest.TestCase):
    """The helper's functions themselves, with fake macOS commands on PATH."""
    src = HELPER.read_text()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "bin").mkdir()

    def fake(self, name: str, body: str):
        p = self.tmp / "bin" / name
        p.write_text("#!/bin/bash\n" + textwrap.dedent(body))
        p.chmod(0o755)

    def run_fn(self, names, call, env=None):
        prog = "set -u\nlog() { :; }\nDB=%s\n%s\n%s\n" % (self.tmp, functions(self.src, *names), call)
        e = dict(os.environ, PATH=f"{self.tmp / 'bin'}:{os.environ['PATH']}", **(env or {}))
        return subprocess.run([BASH, "-c", prog], capture_output=True, text=True, env=e)

    def test_urldec_and_arg(self):
        r = self.run_fn(["urldec", "arg"], 'arg user "kind=x user=jane.doe"; echo; arg note "note=a%20b%2Ac%5Cn"; echo; arg nope "a=1" || echo missing')
        self.assertEqual(r.stdout.splitlines(), ["jane.doe", "a b*c\\n", "missing"], r.stderr)

    def test_accounts_lines(self):
        self.fake("dscl", '''
            if [ "$2" = -list ]; then printf 'root 0\\n_spotlight 89\\njane.doe 1203456\\nlevi 502\\nariseadmin 503\\n'; exit 0; fi
            u="${3#/Users/}"
            case "$4" in
              AuthenticationAuthority) [ "$u" = jane.doe ] && echo "AuthenticationAuthority: ;LocalCachedUser;/Active Directory/ARISE/ad.arisecenla.com:jane.doe" ;;
              OriginalNodeName) [ "$u" = jane.doe ] && printf 'OriginalNodeName:\\n /Active Directory/ARISE/ad.arisecenla.com\\n' ;;
              NFSHomeDirectory) echo "NFSHomeDirectory: /Users/$u" ;;
              RealName) [ "$u" = levi ] && printf 'RealName:\\n Levi Mercer\\n' || echo "RealName: Jane Doe" ;;
            esac''')
        self.fake("dseditgroup", '[ "$4" = levi ] && exit 0; exit 1')     # -o checkmember -m <user> admin
        self.fake("stat", 'echo levi')
        r = self.run_fn(["console_user", "home_of", "is_mobile", "accounts"], "accounts")
        self.assertEqual(r.stdout.splitlines(), ["jane.doe|mobile|1203456|0|/Users/jane.doe|0|Jane Doe|",
                                                 "levi|local|502|1|/Users/levi|1|Levi Mercer|"], r.stderr)

    def test_home_of_keeps_a_space(self):
        self.fake("dscl", 'echo "NFSHomeDirectory: /Users/Media Booth"')
        r = self.run_fn(["home_of"], "home_of media")
        self.assertEqual(r.stdout.strip(), "/Users/Media Booth")

    def test_filevault_state(self):
        for text, want in (("FileVault is On.", "on"), ("FileVault is Off.", "off"),
                           ("FileVault is Off, but will be enabled after the next restart.", "off"),
                           ("FileVault is On.\nDeferred enablement appears to be active for user 'jane'.", "on")):
            self.fake("fdesetup", f"printf '%s\\n' {text!r}")
            self.assertEqual(self.run_fn(["fv_state"], "fv_state").stdout.strip(), want, text)

    def test_secure_token_status_is_read_from_stderr(self):
        self.fake("sysadminctl", '[ "$2" = levi ] && echo "2026-10-29 sysadminctl[1] Secure token is ENABLED for user Levi Mercer" >&2 || echo "Secure token is DISABLED for user $2" >&2')
        r = self.run_fn(["has_token"], "has_token levi && echo yes; has_token jane.doe || echo no")
        self.assertEqual(r.stdout.split(), ["yes", "no"], r.stderr)

    def test_updates_stay_within_this_macos(self):
        listing = textwrap.dedent('''\
            Software Update Tool

            Finding available software
            Software Update found the following new or updated software:
            * Label: macOS Sequoia 15.1.1-24B91
            \tTitle: macOS Sequoia 15.1.1, Version: 15.1.1, Size: 1830000KiB, Recommended: YES, Action: restart,
            * Label: macOS Tahoe 26.0.1-25A362
            \tTitle: macOS Tahoe 26.0.1, Version: 26.0.1, Size: 7000000KiB, Recommended: YES, Action: restart,
            * Label: Safari18.1.1SequoiaAuto-18.1.1
            \tTitle: Safari, Version: 18.1.1, Size: 160000KiB, Recommended: YES,
            * Label: Security Update 2024-006 Ventura-22H221
            \tTitle: Security Update 2024-006 Ventura, Version: 22H221, Size: 2000000KiB, Recommended: YES, Action: restart,
            * Label: Background Security Improvement 26.0.1 (a)
            \tTitle: Background Security Improvement, Version: 26.0.1 (a), Size: 9000KiB, Recommended: YES,
            * Label: Command Line Tools for Xcode-16.1
            \tTitle: Command Line Tools for Xcode, Version: 16.1, Size: 750000KiB, Recommended: YES,
            ''')
        (self.tmp / "su.txt").write_text(listing)
        r = self.run_fn(["pick_updates"], f'pick_updates 15 < "{self.tmp / "su.txt"}"')
        self.assertEqual(r.stdout.splitlines(), ["macOS Sequoia 15.1.1-24B91", "Safari18.1.1SequoiaAuto-18.1.1",
                                                 "Security Update 2024-006 Ventura-22H221",
                                                 "Background Security Improvement 26.0.1 (a)"], r.stderr)

    def test_manifest_with_a_bsd_stat(self):
        # BSD stat -f "%N<TAB>%z<TAB>%m" on top of GNU stat
        self.fake("stat", '''
            [ "$1" = -f ] || exec /usr/bin/stat "$@"
            shift 2; for f in "$@"; do printf '%s\\t%s\\t%s\\n' "$f" "$(/usr/bin/stat -c %s "$f")" "$(/usr/bin/stat -c %Y "$f")"; done''')
        home = self.tmp / "home"
        (home / "Desktop" / "sub").mkdir(parents=True)
        (home / "Desktop" / "a.txt").write_text("hi\n")
        (home / "Desktop" / "sub" / "b.txt").write_text("x\n")
        (home / "Desktop" / ".DS_Store").write_text("")
        (home / "Documents").mkdir()
        (home / "Documents" / "odd\tname.txt").write_text("")
        # a library package never syncs (round 7, 43), so the check leaves it out, inside and all
        (home / "Pictures" / "Photos Library.photoslibrary" / "originals").mkdir(parents=True)
        (home / "Pictures" / "Photos Library.photoslibrary" / "originals" / "IMG_1.heic").write_text("x")
        (home / "Music" / "Music Library.musiclibrary").mkdir(parents=True)
        (home / "Music" / "Music Library.musiclibrary" / "Library.musicdb").write_text("x")
        (home / "Music" / "song.m4a").write_text("x")
        r = self.run_fn(["skipped_pkg", "find_skip", "manifest"], f'{self.skip_line()}\nmanifest "{home}" Desktop,Documents,Downloads,Pictures,Music')
        lines = r.stdout.splitlines()
        self.assertIn("Desktop/a.txt\t3", "\n".join(lines))
        self.assertIn("#folder\tDesktop\tread\t1\t0", lines, r.stderr)
        self.assertIn("#folder\tDocuments\tread\t1\t1", lines)       # the name with a tab is counted
        self.assertIn("#folder\tDownloads\tabsent\t0\t0", lines)
        self.assertIn("#folder\tPictures\tread\t0\t0", lines)        # only the library: nothing to sync
        self.assertIn("#folder\tMusic\tread\t1\t0", lines)
        self.assertIn("Music/song.m4a\t1", r.stdout)
        self.assertNotIn("library", r.stdout.lower().replace("#folder", ""))
        self.assertNotIn(".DS_Store", r.stdout)

    def skip_line(self) -> str:
        return next(ln for ln in self.src.splitlines() if ln.startswith("SKIP_PKGS="))

    def test_library_packages_are_skipped_and_match_nextclouds_list(self):
        r = self.run_fn(["skipped_pkg"], self.skip_line() + '\nfor n in "Photos Library.photoslibrary" "Music Library.musiclibrary" '
                        '"iMovie Library.imovielibrary" "Photo Booth Library" "Photos notes.txt" "photoslibrary"; do '
                        'skipped_pkg "$n" && echo skip || echo keep; done')
        self.assertEqual(r.stdout.split(), ["skip", "skip", "skip", "skip", "keep", "keep"], r.stderr)
        # the patterns stay patterns even with a matching file in the current folder
        (self.tmp / "x.photoslibrary").mkdir()
        r = subprocess.run([BASH, "-c", "set -u\n%s\n%s\nfind_skip" % (self.skip_line(), functions(self.src, "find_skip"))],
                           capture_output=True, text=True, cwd=self.tmp)
        self.assertIn("*.photoslibrary", r.stdout.splitlines()); self.assertNotIn("x.photoslibrary", r.stdout)
        nc = (MAC / "helper" / "tasks" / "nextcloud.sh").read_text()
        m = re.search(r"^NC_SKIP='([^']*)'", nc, re.M)
        self.assertTrue(m, "nextcloud.sh has NC_SKIP")
        self.assertEqual(set(m.group(1).split()) - {"Photo", "Booth", "Library"},
                         set(self.skip_line().split("'")[1].split()))


if __name__ == "__main__":
    unittest.main()
