#!/usr/bin/env bash
# ariseOS: make the install media (installer/MAKE-USB.md).
#
#   bash scripts/make-install-media.sh                 the add-on disc and the USB files
#   bash scripts/make-install-media.sh --full          also the one ariseOS ISO (about 3 GB)
#   bash scripts/make-install-media.sh --full --ubuntu-iso ~/ubuntu-24.04.3-live-server-amd64.iso
#   bash scripts/make-install-media.sh --test-identity a TEST build: the identity is filled
#                                                      in (user tester), so a VM run is fully
#                                                      unattended. Never for a real box.
#
# Out, in dist/ (git-ignored):
#   ariseos-addon.iso    a small disc labelled CIDATA: user-data, meta-data, autoinstall.yaml
#                        and arise/ (the code). Attach it next to the plain Ubuntu ISO
#                        (VirtualBox: a second optical drive); the installer finds it.
#   ariseos-addon.zip    the same files for a Rufus-written Ubuntu USB stick: unzip them
#                        onto the stick's root, next to casper/ and boot/.
#   ariseos-<v>-amd64.iso  (--full) the official Ubuntu 24.04 server ISO with ariseOS inside:
#                        the first boot-menu entry installs ariseOS by itself; "Install by
#                        hand" is the plain Ubuntu installer. Its boot records are Ubuntu's own.
#   SHA256SUMS           of everything above.
#
# The media carries the code (the repo is private: no git clone during the install) and no
# password: Ubuntu asks who you are, and the first-boot wizard asks for the domain password.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"
FULL=0
UBUNTU_ISO=""
TEST_IDENTITY=0
UBUNTU_REL="https://releases.ubuntu.com/24.04"
while [ $# -gt 0 ]; do
  case "$1" in
    --full) FULL=1; shift ;;
    --ubuntu-iso) UBUNTU_ISO="$2"; shift 2 ;;
    --test-identity) TEST_IDENTITY=1; shift ;;
    --out) OUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done
say() { printf '  %s\n' "$*"; }
die() { printf '  ! %s\n' "$*" >&2; exit 1; }
command -v xorriso >/dev/null || die "xorriso is needed: sudo apt install xorriso (Mac: brew install xorriso)"
command -v zip >/dev/null || die "zip is needed: sudo apt install zip"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$ROOT/server/arise_server/__init__.py" | head -1)"
[ -n "$VERSION" ] || die "no VERSION in server/arise_server/__init__.py"

STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$OUT" "$STAGE/arise"

# 1. the code: the committed tree (git archive), so nothing local or secret rides along
if git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  if [ -n "$(git -C "$ROOT" status --porcelain -- . ':!dist' 2>/dev/null)" ]; then
    say "note: uncommitted changes are NOT on the media (it carries the last commit)"
  fi
  git -C "$ROOT" archive --format=tar.gz -o "$STAGE/arise/ariseos-src.tar.gz" HEAD
  COMMIT="$(git -C "$ROOT" rev-parse --short HEAD)"
else
  tar -czf "$STAGE/arise/ariseos-src.tar.gz" -C "$ROOT" --exclude=.git --exclude=dist --exclude=node_modules .
  COMMIT="not a git checkout"
fi
printf 'ariseOS %s (%s), made %s\n' "$VERSION" "$COMMIT" "$(date -u +%Y-%m-%dT%H:%MZ)" > "$STAGE/arise/VERSION"
(cd "$STAGE/arise" && sha256sum ariseos-src.tar.gz > SHA256SUMS)

# 2. the autoinstall config: as committed, or with a TEST identity for an unattended VM run
cp "$ROOT/installer/autoinstall.yaml" "$STAGE/autoinstall.yaml"
if [ "$TEST_IDENTITY" = 1 ]; then
  command -v openssl >/dev/null || die "openssl is needed for --test-identity"
  HASH="$(openssl passwd -6 -salt ariseostest arise-test-only)"
  python3 - "$STAGE/autoinstall.yaml" "$HASH" <<'PY'
import sys
p, h = sys.argv[1], sys.argv[2]
s = open(p).read()
s = s.replace("  interactive-sections:\n    - identity\n",
              "  # TEST BUILD: the identity is filled in so a VM run needs no typing. Never for a real box.\n"
              "  identity:\n    realname: ariseOS test\n    username: tester\n    hostname: arise-server\n"
              f"    password: \"{h}\"\n", 1)
open(p, "w").write(s)
PY
  say "TEST build: user tester, password arise-test-only (a VM only)"
fi
python3 - "$STAGE/autoinstall.yaml" <<'PY' || die "autoinstall.yaml does not parse"
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
assert isinstance(d, dict) and "autoinstall" in d, "no autoinstall: key"
PY
{ echo "#cloud-config"; sed '1{/^#cloud-config/d}' "$STAGE/autoinstall.yaml"; } > "$STAGE/user-data"
printf 'instance-id: ariseos-%s\nlocal-hostname: arise-server\n' "$VERSION" > "$STAGE/meta-data"

SUF=""; [ "$TEST_IDENTITY" = 1 ] && SUF="-TEST"
# 3. the add-on disc (CIDATA) and the USB files
rm -f "$OUT/ariseos-addon$SUF.iso" "$OUT/ariseos-addon$SUF.zip"
xorriso -as mkisofs -quiet -V CIDATA -J -r -o "$OUT/ariseos-addon$SUF.iso" \
  "$STAGE/user-data" "$STAGE/meta-data" "$STAGE/autoinstall.yaml" -graft-points "arise=$STAGE/arise" >/dev/null 2>&1 \
  || die "xorriso could not make the add-on disc"
(cd "$STAGE" && zip -q -r "$OUT/ariseos-addon$SUF.zip" autoinstall.yaml arise)
say "add-on disc: dist/ariseos-addon$SUF.iso ($(du -h "$OUT/ariseos-addon$SUF.iso" | cut -f1))"
say "USB files:   dist/ariseos-addon$SUF.zip ($(du -h "$OUT/ariseos-addon$SUF.zip" | cut -f1))"

# 4. the one ISO (--full)
if [ "$FULL" = 1 ]; then
  FREE_KB="$(df -Pk "$OUT" | awk 'NR==2{print $4}')"
  [ "${FREE_KB:-0}" -ge $((8 * 1024 * 1024)) ] || die "--full needs about 8 GB free next to dist/ (the Ubuntu ISO and the new one); $((FREE_KB / 1024 / 1024)) GB free"
  if [ -z "$UBUNTU_ISO" ]; then
    command -v curl >/dev/null || die "curl is needed to fetch the Ubuntu ISO (or pass --ubuntu-iso)"
    SUMS="$(curl -fsSL "$UBUNTU_REL/SHA256SUMS")" || die "could not read $UBUNTU_REL/SHA256SUMS"
    NAME="$(printf '%s\n' "$SUMS" | grep -o 'ubuntu-24\.04[.0-9]*-live-server-amd64\.iso' | sort -V | tail -1)"
    [ -n "$NAME" ] || die "no live-server ISO listed in $UBUNTU_REL/SHA256SUMS"
    UBUNTU_ISO="$OUT/$NAME"
    if [ ! -f "$UBUNTU_ISO" ]; then say "downloading $NAME (about 3 GB)"; curl -fL --progress-bar -o "$UBUNTU_ISO.part" "$UBUNTU_REL/$NAME" && mv "$UBUNTU_ISO.part" "$UBUNTU_ISO"; fi
    WANT="$(printf '%s\n' "$SUMS" | awk -v n="*$NAME" -v m="$NAME" '$2==n||$2==m{print $1}')"
    GOT="$(sha256sum "$UBUNTU_ISO" | cut -d' ' -f1)"
    [ "$WANT" = "$GOT" ] || die "$NAME does not match Ubuntu's SHA256SUMS (got $GOT); delete it and run again"
    say "$NAME matches Ubuntu's SHA256SUMS"
  fi
  [ -f "$UBUNTU_ISO" ] || die "no Ubuntu ISO at $UBUNTU_ISO"
  # the boot menu: a first entry with `autoinstall` (no "continue?" question), the rest as Ubuntu made them
  xorriso -osirrox on -indev "$UBUNTU_ISO" -extract /boot/grub/grub.cfg "$STAGE/grub.orig.cfg" >/dev/null 2>&1 \
    || die "could not read /boot/grub/grub.cfg from the Ubuntu ISO"
  python3 - "$STAGE/grub.orig.cfg" "$STAGE/grub.cfg" <<'PY'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
s = open(src).read()
m = re.search(r'(?ms)^menuentry\s+"[^"]*"\s*\{.*?^\}', s)
if not m:
    sys.exit("no menuentry in grub.cfg")
first = m.group(0)
lin = re.search(r'(?m)^\s*linux\s+(\S+)(.*)$', first)
if not lin:
    sys.exit("no linux line in the first menuentry")
args = lin.group(2)
args = args.replace("---", "autoinstall ---", 1) if "---" in args else args + " autoinstall"
entry = re.sub(r'^menuentry\s+"[^"]*"', 'menuentry "Install ariseOS (ERASES this computer\'s largest disk)"', first, count=1)
entry = entry.replace(lin.group(0), f"\tlinux\t{lin.group(1)}{args}", 1)
hand = re.sub(r'^menuentry\s+"[^"]*"', 'menuentry "Install by hand (the plain Ubuntu installer)"', first, count=1)
s = s[:m.start()] + entry + "\n" + hand + "\n" + s[m.end():]
# never boot the erasing entry by itself: wait for a choice
s = re.sub(r'(?m)^set timeout=.*$', 'set timeout=-1', s) if re.search(r'(?m)^set timeout=', s) else "set timeout=-1\n" + s
open(dst, "w").write(s)
PY
  FULL_ISO="$OUT/ariseos-$VERSION-amd64$SUF.iso"
  rm -f "$FULL_ISO"
  xorriso -indev "$UBUNTU_ISO" -outdev "$FULL_ISO" -volid ARISEOS_2404 \
    -map "$STAGE/arise" /arise -map "$STAGE/autoinstall.yaml" /autoinstall.yaml \
    -map "$STAGE/grub.cfg" /boot/grub/grub.cfg \
    -boot_image any replay >/dev/null 2>&1 || die "xorriso could not make $FULL_ISO"
  say "the ariseOS ISO: dist/$(basename "$FULL_ISO") ($(du -h "$FULL_ISO" | cut -f1))"
fi

(cd "$OUT" && sha256sum ariseos-*.iso ariseos-*.zip 2>/dev/null | grep -v ubuntu > SHA256SUMS) || true
say "checksums: dist/SHA256SUMS"
sed 's/^/    /' "$OUT/SHA256SUMS"
