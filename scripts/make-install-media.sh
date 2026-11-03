#!/usr/bin/env bash
# ariseOS: make the install media (installer/MAKE-USB.md).
#
#   bash scripts/make-install-media.sh                 the add-on disc and the USB files
#   bash scripts/make-install-media.sh --full          also the one ariseOS ISO (about 3 GB)
#   bash scripts/make-install-media.sh --full --working-tree --ubuntu-iso /path/to/ubuntu.iso --ubuntu-sha256 TRUSTED_SHA256
#   bash scripts/make-install-media.sh --secrets DIR   a PRIVATE disc that also carries the keys in DIR
#                                                      (only the names below), named ...-private.iso:
#                                                      the installer puts them in /etc/arise/secrets/
#                                                      by itself. Keep it off GitHub and out of shares.
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
WORKING_TREE=0
UBUNTU_SHA256=""
UBUNTU_ISO=""
TEST_IDENTITY=0
SECRETS_DIR=""
# The keys a private disc may carry, by file name in /etc/arise/secrets/ (Bradly, Oct 31, H9).
SECRET_NAMES="resend-api-key"
UBUNTU_REL="https://releases.ubuntu.com/24.04"
while [ $# -gt 0 ]; do
  case "$1" in
    --full) FULL=1; shift ;;
    --working-tree) WORKING_TREE=1; shift ;;
    --ubuntu-sha256) UBUNTU_SHA256="$2"; shift 2 ;;
    --ubuntu-iso) UBUNTU_ISO="$2"; shift 2 ;;
    --test-identity) TEST_IDENTITY=1; shift ;;
    --secrets) SECRETS_DIR="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done
say() { printf '  %s\n' "$*"; }
die() { printf '  ! %s\n' "$*" >&2; exit 1; }
command -v xorriso >/dev/null || die "xorriso is needed: sudo apt install xorriso (Mac: brew install xorriso)"
command -v zip >/dev/null || die "zip is needed: sudo apt install zip"
command -v sha256sum >/dev/null || die "sha256sum is needed (Linux: coreutils; Mac: brew install coreutils)"
python3 -c 'import yaml' 2>/dev/null || die "Python 3 and PyYAML are needed (Ubuntu: sudo apt install python3-yaml)"
[ -z "$UBUNTU_SHA256" ] || [[ "$UBUNTU_SHA256" =~ ^[a-fA-F0-9]{64}$ ]] || die "--ubuntu-sha256 must be a SHA-256 from a trusted Ubuntu checksum list"
VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$ROOT/server/arise_server/__init__.py" | head -1)"
[ -n "$VERSION" ] || die "no VERSION in server/arise_server/__init__.py"

STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$OUT" "$STAGE/arise"

# 1. Export an explicit source snapshot. Never include untracked local files.
if ! git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  die "Build from a Git checkout so the payload has an explicit tracked-file allowlist"
fi
COMMIT="$(git -C "$ROOT" rev-parse --short HEAD)"
if [ "$WORKING_TREE" = 1 ]; then
  say "REVIEW BUILD: includes current tracked working files, including staged additions; untracked files are excluded"
  python3 - "$ROOT" "$STAGE/arise/ariseos-src.tar.gz" <<'PYEXPORT'
import io, os, pathlib, re, subprocess, sys, tarfile
root = pathlib.Path(sys.argv[1]).resolve()
paths = subprocess.check_output(["git", "-C", str(root), "ls-files", "--cached", "-z"]).split(b"\0")
forbidden = {".env", "token.json", "client_secret.json", ".mcp.json", "id_rsa", "id_ed25519"}
secret = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|1//[A-Za-z0-9_-]{30,}|GOCSPX-[A-Za-z0-9_-]{20,}|ya29\.[A-Za-z0-9_-]{30,}")
with tarfile.open(sys.argv[2], "w:gz") as archive:
    for raw in sorted(set(paths)):
        if not raw:
            continue
        rel = pathlib.PurePosixPath(os.fsdecode(raw))
        if rel.is_absolute() or ".." in rel.parts or any(p in {".git", "dist", "node_modules", "venv", "secrets"} for p in rel.parts) or rel.name in forbidden:
            raise SystemExit(f"Refusing sensitive or generated tracked path: {rel}")
        path = root / rel
        if not path.exists() and not path.is_symlink():
            continue  # a tracked deletion belongs in this working snapshot
        if path.is_symlink():
            target = path.resolve()
            if not target.is_relative_to(root):
                raise SystemExit(f"Refusing symlink outside source: {rel}")
            raise SystemExit(f"Review build requires regular tracked files: {rel}")
        data = path.read_bytes()
        if secret.search(data):
            raise SystemExit(f"Possible credential in {rel}; build stopped without printing it")
        info = archive.gettarinfo(str(path), arcname=str(rel))
        info.uid = info.gid = 0; info.uname = info.gname = "root"
        archive.addfile(info, io.BytesIO(data))
PYEXPORT
  COMMIT="$COMMIT+reviewed-working-tree"
else
  [ -z "$(git -C "$ROOT" status --porcelain -- . ':!dist' 2>/dev/null)" ] || die "Working files differ from HEAD. Review them, then build with --working-tree, or build a clean commit."
  git -C "$ROOT" archive --format=tar.gz -o "$STAGE/arise/ariseos-src.tar.gz" HEAD
fi
printf 'ariseOS %s (%s), made %s\n' "$VERSION" "$COMMIT" "$(date -u +%Y-%m-%dT%H:%MZ)" > "$STAGE/arise/VERSION"
# 1b. a private disc: the keys Bradly chose to carry (H9). Never part of the tarball or its checksum
#     line, never printed; the file name says "private" so it isn't mistaken for the shareable disc.
if [ -n "$SECRETS_DIR" ]; then
  [ -d "$SECRETS_DIR" ] || die "--secrets: no folder $SECRETS_DIR"
  mkdir -p "$STAGE/arise/secrets"; chmod 700 "$STAGE/arise/secrets"
  n=0
  for f in $SECRET_NAMES; do
    if [ -s "$SECRETS_DIR/$f" ]; then install -m 600 "$SECRETS_DIR/$f" "$STAGE/arise/secrets/$f"; n=$((n + 1)); fi
  done
  [ "$n" -gt 0 ] || die "--secrets: none of ($SECRET_NAMES) in $SECRETS_DIR"
  say "private disc: $n key file(s) on it ($SECRET_NAMES); keep it off GitHub and out of shared folders"
fi
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
s = s.replace("  interactive-sections:\n    - storage\n    - identity\n",
              "  interactive-sections:\n    - storage\n  # TEST BUILD: identity supplied, but disk selection remains interactive.\n"
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

SUF=""; [ "$TEST_IDENTITY" = 1 ] && SUF="-TEST"; [ -n "$SECRETS_DIR" ] && SUF="$SUF-private"
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
  if [ -n "$UBUNTU_SHA256" ]; then
    GOT="$(sha256sum "$UBUNTU_ISO" | cut -d' ' -f1)"
    [ "${GOT,,}" = "${UBUNTU_SHA256,,}" ] || die "Supplied Ubuntu ISO does not match its trusted SHA-256"
  elif [ -z "${WANT:-}" ]; then
    die "--ubuntu-iso requires --ubuntu-sha256 from a verified Ubuntu checksum list"
  fi
  # the boot menu: a first entry with `autoinstall` (no "continue?" question), the rest as Ubuntu made them
  xorriso -osirrox on -indev "$UBUNTU_ISO" \
    -extract /boot/grub/grub.cfg "$STAGE/grub.orig.cfg" \
    -extract /md5sum.txt "$STAGE/md5sum.orig.txt" >/dev/null 2>&1 \
    || die "could not read the boot menu and integrity manifest from the Ubuntu ISO"
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
entry = re.sub(r'^menuentry\s+"[^"]*"', 'menuentry "Install ariseOS (choose disk and encryption on screen)"', first, count=1)
entry = entry.replace(lin.group(0), f"\tlinux\t{lin.group(1)}{args}", 1)
hand = re.sub(r'^menuentry\s+"[^"]*"', 'menuentry "Install by hand (the plain Ubuntu installer)"', first, count=1)
s = s[:m.start()] + entry + "\n" + hand + "\n" + s[m.end():]
# never boot an installation entry by itself: wait for a choice
s = re.sub(r'(?m)^set timeout=.*$', 'set timeout=-1', s) if re.search(r'(?m)^set timeout=', s) else "set timeout=-1\n" + s
open(dst, "w").write(s)
PY
  # Ubuntu's live media checker reads md5sum.txt. Keep its original entries
  # for untouched files, replace changed mappings, and cover the added payload.
  # This compatibility manifest does not replace the trusted base ISO SHA-256.
  python3 - "$STAGE" <<'PYMD5'
import hashlib, pathlib, re, sys
stage = pathlib.Path(sys.argv[1])
mapped = {"./boot/grub/grub.cfg": stage / "grub.cfg",
          "./autoinstall.yaml": stage / "autoinstall.yaml"}
for path in sorted((stage / "arise").rglob("*")):
    if path.is_file():
        mapped["./arise/" + path.relative_to(stage / "arise").as_posix()] = path
kept = []
seen = set()
for line in (stage / "md5sum.orig.txt").read_text().splitlines():
    if not line.strip():
        continue
    match = re.fullmatch(r"([0-9a-fA-F]{32}) [ *](.+)", line)
    if not match:
        raise SystemExit("Unsupported Ubuntu checksum manifest format; build stopped")
    name = match.group(2)
    normalized = "./" + name.removeprefix("./")
    if normalized == "./md5sum.txt" or normalized in mapped or normalized.startswith("./arise/"):
        continue
    if normalized in seen:
        raise SystemExit("Duplicate original media checksum path; build stopped")
    seen.add(normalized)
    kept.append(line)
for name, path in sorted(mapped.items()):
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    kept.append(f"{digest.hexdigest()}  {name}")
(stage / "md5sum.txt").write_text("\n".join(kept) + "\n")
PYMD5
  FULL_ISO="$OUT/ariseos-$VERSION-amd64$SUF.iso"
  rm -f "$FULL_ISO"
  xorriso -indev "$UBUNTU_ISO" -outdev "$FULL_ISO" -volid ARISEOS_2404 \
    -map "$STAGE/arise" /arise -map "$STAGE/autoinstall.yaml" /autoinstall.yaml \
    -map "$STAGE/grub.cfg" /boot/grub/grub.cfg -map "$STAGE/md5sum.txt" /md5sum.txt \
    -boot_image any replay >/dev/null 2>&1 || die "xorriso could not make $FULL_ISO"
  say "the ariseOS ISO: dist/$(basename "$FULL_ISO") ($(du -h "$FULL_ISO" | cut -f1))"
fi

(cd "$OUT" && sha256sum ariseos-*.iso ariseos-*.zip 2>/dev/null | grep -v ubuntu > SHA256SUMS) || true
say "checksums: dist/SHA256SUMS"
sed 's/^/    /' "$OUT/SHA256SUMS"
