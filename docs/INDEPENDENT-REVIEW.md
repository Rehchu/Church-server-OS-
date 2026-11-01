# Independent review and installation acceptance record

Reviewed 2026-10-30. Baseline: `claude/arise-server-os` commit
`208e4d16ad0b338877d120d290800c7c2904d203`. Fixes are in the working
branch `fix/arise-install-readiness`; they have not been committed or pushed.
The latest uploaded brief references `20bfca5372e028e627b1e64a0d637fec0faf0b6e`.
Its four subsequent commits and changed documentation were reviewed separately
and incorporated where compatible with the earlier fixes. The original Git
baseline remains unchanged; the exported patch includes both sets of work.
The full ISO is a review build containing those working files, not a release
of the original commit. The media contains its own source archive checksum.

## Scope and authority

The review covered both uploaded Claude briefs, every repository Markdown
document, the text/license documentation, the inventories in Part B of the
second brief, and the relevant implementation and tests. Part C repeats the
repository documentation. This is not a claim to have audited every line of
application or dependency code. Findings were checked against source; a
statement in the brief was not accepted as proof.

The latest entries in [ANSWERS.md](ANSWERS.md) control conflicting older
instructions. In particular: no router/switch/mesh changes; no public app
port forwards; church Macs are AD-bound and helper-managed without MDM,
while linked local accounts keep their passwords; personal Macs are not
enrolled. Optional MFA, no account lockout, and the explicitly approved
Trash and snapshot retention remain owner decisions. The user's subsequent
instruction authorized fixing defects and building a full ISO with on-screen
installation and automatic desktop startup.

The latest H1–H6 decisions identify an HP EliteDesk 800 G1 SFF as the primary
server, a Dell OptiPlex 3010 as the spare, and a two-bay Synology DS216 using
ext4. They replace the old all-apps default with Nextcloud, Vaultwarden,
Uptime Kuma, Netdata and File Browser. The expected TPM 1.2 cannot perform
the documented TPM 2.0 unlock; the owner chose a passphrase at boot, with
optional restricted SSH unlock. H6 retains TPM unlocking if a real TPM 2.0
is found. Actual firmware, memory, CPU and disk condition still need inspection.

## Ten highest-priority findings

Severity below describes the original defect. "Fixed" means implemented and
covered by source inspection and focused tests; it does not mean every real
service integration has been exercised.

| Priority / severity | Location | Original problem and consequence | Change / remaining verification | Confidence |
|---|---|---|---|---|
| 1 / Critical | `server/arise_server/twofa.py` | A signed but readable pending-MFA token contained a usable session; knowing the first factor bypassed OTP. | Fixed: opaque challenge, session retained server-side, expiry, bounded attempts and single consumption. Regression checks reject pending tokens as sessions. | High; original reproduced with synthetic credentials. |
| 2 / High | `server/arise_server/main.py`, `auth.py`, `web/app.js` | PIN-only administrators could change accounts/privileges without the promised full-password recheck. | Fixed: shared recent-administrator dependency on administrative mutations and browser password prompt/retry. | High. |
| 3 / High | `finder.py`, `links.py`, new `archive_safe.py` | Zipping an allowed ancestor could export protected Pastors descendants or symlink targets. | Fixed: authorize every descendant; public archives exclude Pastors; descriptor-based no-follow reads prevent swapped symlink traversal. | High; original candidate selection reproduced. |
| 4 / High | `installer/autoinstall.yaml` | "Largest disk" silently selected an unintended disk, and automatic plain LVM omitted encryption. | Fixed: on-screen storage selection and destructive-action confirmation; choose encrypted LVM there. Two-disk and encrypted-install VM acceptance remain required. | High. |
| 5 / High | `installer/install.sh`, `scripts/arise-firstboot` | Live-installer bootstrap could change networking before Samba existed; no-start/no-apps were incomplete. | Fixed: defer Arise configuration until normal boot; on-screen wizard, retry on failure, core/essentials/all choice, honest flags and desktop readiness gate. | High for source; full installed-system acceptance remains. |
| 6 / High | `installer/install.sh`, `docs/REINSTALL.md`, `apps.py` | Restore could create a new domain after failure, replace app secrets and restore over running databases. | Fixed: missing/broken domain recovery stops; preserve original app secrets/data; no app startup before restoration. Fresh-machine recovery still must be rehearsed. | High. |
| 7 / High | `backups.py`, backup configuration and units | State/audit/leavers were omitted; stale domain backups and incomplete drills could report success; live DB copies were inconsistent. | Fixed: path coverage, fresh-domain requirements, truthful drill results, cold app backup with interrupted-restart recovery, verification timer. Separate homes/share/app jobs are not an atomic whole-server snapshot. | High. |
| 8 / High | `apps.py`, Nextcloud/Immich manifests | RAM budget counted estimated idle use while every service inherited a whole-app cap; advertised system reserve was unenforced. | Fixed: aggregate all service caps, reserve system headroom, guard manual starts and prioritize Nextcloud. Docker pull/extraction overhead is still outside running-container caps. | High; original cap arithmetic reproduced. |
| 9 / High | `mac/helper/enrol.sh`, `mac/bind-mac.sh`, `windows/join-arise.ps1` | Enrollment could replace a verified CA with an unverified HTTP download. | Fixed: explicit fingerprint verification and verified-root reuse; privileged downloads use verified HTTPS. Real Mac and Windows joining remain untested. | High. |
| 10 / High | `mac/helper/arise-mac-helper`, `macs.py` | Deferred FileVault escrow never retried; account deletion bypassed macOS refusal and could remove the last token holder. | Fixed: pending/retry escrow state; preserve accounts on refusal and refuse automatic removal of token holders or accounts with unknown token status. Real FileVault enable/login/reboot/escrow acceptance remains required. | High for control flow. |

## Additional findings and disposition

| Severity | Location | Problem / why it matters | Change or outstanding requirement | Confidence |
|---|---|---|---|---|
| High | Installer and network runbooks | Freezing a DHCP lease is not a reservation; another client can receive that address. | DHCP is retained by default; premature loopback DNS is avoided. A stable directory endpoint still needs evidence before church deployment; no router change is prescribed. | High. |
| High | `offboard.py` | Failed file transfer could still queue Mac removal and mark offboarding complete. | Retry failed stages, verify archive content, finalize only after required transfer succeeds. | High. |
| High | `sharing.py` | Executing `ssh true` rejects an intentionally SFTP-only backup account. | Probe the SFTP subsystem; verify against the real restricted offsite account. | High. |
| Medium | `auth.py` | Non-root demo generated a new signing key on each use; sessions failed immediately. | Stable per-process demo fallback; production requires a persistent key and fails closed. | High; reproduced by original test suite. |
| Medium | `audit.py`, `accounts.py` | Audit-write failures were silent; emergency access claimed notifications succeeded even when delivery failed. | Surface audit health failures, enforce log mode, record actual notification outcome/failures. Root can still alter a local log; failed email needs operator follow-up. | High. |
| Medium | `maintenance.py`, backups, updates, app actions | Backups, deployments and unattended upgrades could overlap each other or services. | Shared process lock and service-window checks; restic timeouts leave a cleanup allowance. Real transfer timings and reboot recovery still need acceptance. | High. |
| Medium | `apps.py`, `util.py` | App statistics parsed container names incorrectly; silent pulls appeared hung. | Compose project labels identify stats; serial pulls stream visible progress. | High. |
| Medium | `apps.py` | Autostart only changed metadata, not Docker behavior. | Apply actual restart policy and appropriate start state; verify a real Docker/host restart. | High. |
| Medium | `apps.py`, File Browser template | Alternate deployment names collided with fixed ports/data paths; File Browser file mounts/permissions were fragile. | Reject unsupported alternate names; writable directory mounts and copy-only legacy migration after a successful stop. | High. |
| Medium | Store/stack docs | File Browser was presented as domain ACL access; all apps were said to fit small machines. | Document separate service identity/login and measured resource limits. There are 26 templates, not 27. | High. |
| Medium | Installer, Caddy, VirtualBox docs | Plain dashboard port and staging binding disagreed with HTTPS testing instructions. | Loopback application backend, HTTPS proxy; HTTP serves only the public pinned CA. VM forwards, if used, bind Windows loopback. | High. |
| Medium | Media builder | Supplied base ISO was unverified; dirty source changes could be omitted. | Require trusted supplied checksum; explicit tracked-working-tree export; reject credential patterns; embed payload checksum. | High. |
| Medium | Mac SMB scripts | `/homes/user` did not match the configured dynamic per-user Samba share. | Use the per-user share path; actual SMB reconnect/permission tests remain. | High for mismatch. |
| Medium | Network/remote docs | NTP service and plaintext Guacamole LDAP guidance overstated installed behavior. | Require independently correct client time and verified encrypted LDAP; do not weaken Samba authentication. Validate real clients. | High for missing configuration; integration unrun. |
| Medium | `docs/NODES.md` | A heartbeat timeout plus replicated metadata was called fencing. | Correct design documentation; automated safe failover is not implemented or established. | High. |
| Medium | Install, restore, NAS and older setup docs | Stale branch, path, credentials, router and retention recipes contradicted current code/decisions. | Replace or mark superseded guidance, keep secrets out of examples/logs, point to current workflows. | High. |

## Answers to the original Claude brief A9

1. **Unsure — soft-lockup cause.** The watchdog message alone does not
   identify the cause. Preserve VBox.log and the guest stack, check actual
   virtualization backend, host paging/disk health/free space and guest
   resource pressure, then use a current maintenance release with a small
   core VM. Add one app at a time. Test host I/O cache only as a controlled
   change; it is neither a universal fix nor permission to disable flushes.
   A missing turtle icon does not prove Windows hypervisor features are absent.
2. **Unsure — fixed VDI benefit.** Preallocation can reduce growth/fragmentation
   overhead, but does not diagnose this failure. A dynamic VDI on a healthy SSD
   with adequate free space is a valid baseline; do not recreate disks first.
3. **Correct — visible pulls and a short initial list.** The original outer
   deployment loop was already sequential. Progress and bounded Compose
   parallelism are now visible; the wizard offers core, essentials or all.
4. **Correct concern, unproven live deployment.** One DC plus many apps shares
   an outage boundary. Check port 53 ownership, resolver handover, forward DNS,
   AD SRV records, hostname/hosts, clock synchronization, firewall rules,
   memory/disk pressure, service restart and real client authentication.
5. **Wrong premise.** Church Macs are AD-bound with a helper, no MDM; local
   linked accounts keep local passwords. Personal Macs are not enrolled.
   FileVault, Secure Token, Full Disk Access, updates and offline/sync behavior
   remain **Unsure** until representative physical-Mac tests pass.
6. **Correct with hardware conditions.** SHR can grow from one disk to two
   with redundancy, then larger usable capacity with equal-sized additions.
   There is no disk redundancy at one drive. Check the exact Synology model,
   DSM and drive compatibility before purchase. Prefer compatible CMR disks;
   the exact WD40EZAZ/WD40EZAX assertions are **Unsure** here without current
   manufacturer evidence. RAID is not an independent backup.
7. **Owner decision, not a defect.** No account lockout is deliberate.
   Per-IP dashboard throttling does not protect every SMB/Kerberos/LDAP path.
   Restrict management reachability, monitor failures, use optional MFA and
   test revocation. Do not silently change the chosen lockout policy.
8. **Wrong as originally implemented.** MFA token disclosure and missing
   administrator rechecks broke the boundary. Both are fixed above; PIN
   remains a convenience credential whose exposure and long sessions matter.
9. **Correct foundation, incomplete assurance.** Encrypted restic plus a
   second site and 30/12/24 retention is useful. Add proven application/domain
   restores and a separately protected offline/immutable copy. A source host
   with writable backup access can delete backups; encryption does not stop it.
10. **Owner decision.** Public source is not inherently unsafe. Staff details,
    operational layout and recovery procedures can live in private operations
    documentation. Repository visibility was not changed.
11. **Wrong/unsafe selection.** Largest-disk matching is inappropriate.
    The ISO now asks for disk selection and confirmation on screen. Use only
    an empty virtual disk for the first test; no physical-disk passthrough.
12. **Yes — fragile areas identified.** A single host/DC, unknown hardware,
    many app/database upgrade paths, manual Google consent renewal, unattended
    recovery promises and untested Mac integrations are substantial operating
    work. Start small and require the acceptance evidence below. Intentional
    convenience choices are recorded separately from code defects.

## Validation evidence

- The original source suite exposed session-signing and fixture-isolation
  defects. They were fixed rather than hidden by a permanent test secret.
- Latest hardware-update suite: **632 reported test methods, 628 passed,
  4 individual skips plus 1 skipped class**, exit 0. Unittest summarizes this
  as `OK (skipped=5)`; the run completed in 19.404 seconds after the HP/DS216
  changes and sample-data regeneration. The actual CIDATA build test ran
  with xorriso. The earlier pre-hardware run separately reported 596 methods
  (592 passed, the same skips); it is not evidence for the later changes.
  Remaining unavailable capabilities: external automator clone, two root-only
  checks, visudo, and real filesystem ACL tools.
- Original snapshot browser sweep: **413 passed, 1 Terminal check skipped,
  0 failed**. This is sample UI evidence, not an installed-service test or a
  full browser sweep of the later fixes.
- Focused browser checks against the changed working-tree dashboard: **8
  passed, 0 failed**. The current FastAPI demo rendered Overview and the
  Nextcloud catalogue's aggregate 2,688 MiB cap correctly. Simulated protected
  action responses verified full-password prompting, rejection, cancellation,
  preserving the original POST/body on one retry, ordinary authorization
  denial, and stopping after a second denial. No JavaScript page errors were
  observed. These checks exercise the current client without running real
  administrator operations; they do not establish Samba authentication.
- Hardware-update reboot UI: **5 focused checks passed, 0 failed**. The
  manual disk-unlock/person-ready warning appears before a power request;
  empty/wrong confirmation words are refused; cancellation sends nothing;
  full-password reauthentication remains required; and successful confirmation
  sends one simulated action with the original payload. All power requests
  were intercepted. No real reboot, initramfs SSH unlock or disk unlock was
  performed by these browser checks.
- Base image: official Ubuntu Server **24.04.5 amd64**, verified against its
  signed checksum list using the Ubuntu CD Image signing key. SHA-256:
  `97f3d7ffb032c3eb3b23d2c8be9cc76e60c2c1f2c0146ba5ba9fe01cafae0fd8`.
- Final ISO checksum and boot-smoke evidence are recorded beside the built
  artifact. A QEMU smoke, if recorded there, is not a VirtualBox installation.

## Acceptance still required before production

1. Complete the full ISO install in a disposable VirtualBox VM: storage and
   encryption selection, first reboot, on-screen setup, domain readiness,
   desktop launch, sign-in, shutdown and cold restart. Test failed setup/retry
   and two empty disks without any host physical-disk passthrough.
2. Exercise real directory login, role changes, DNS and time from a client;
   HTTPS trust and remote access; firewall reachability on IPv4/IPv6; and
   address renewal/change. Preserve the no-router-change requirement.
3. Deploy the essentials with real Docker, verify endpoints, credentials,
   autostart, resource accounting and reboot persistence. Test each additional
   template's supported version and upgrade path before trusting its data.
4. Back up to the actual Synology and SFTP-only offsite target. Restore onto
   a fresh isolated VM: same AD identity, users, passwords, ACLs, app databases,
   original app secrets, calendar/profiles/offboarding state and audit history.
   Demonstrate cold-backup restart recovery and service-window behavior.
5. Enroll a representative church Mac; verify CA trust, AD binding and linked
   local login, offline login/sync, conflict recovery, FileVault key escrow and
   recovery, token-holder safeguards, update authorization and profile removal.
   Windows VirtualBox does not establish Apple platform behavior.
   The Apple account tools still receive admin credentials in arguments;
   Nextcloud 3.14.3 accepts its device app password only as a command argument.
   Secure unattended input for the Apple tools and a supported alternative
   Nextcloud login remain unresolved; see [MACS.md](MACS.md). Verify Tailscale's
   real Apple signature/notarization checks too; Linux tests use stand-ins.
6. Test actual automator checkout/Google consent, mail and notification
   delivery, backup-password custody and the separately protected copy. Never
   include real tokens/passwords in test logs or installation media.

There is no claim here of a completed VirtualBox installation, a successful
real NAS/domain restore, or production readiness. The working ISO makes the
requested installation path available for that acceptance testing.

## Additional review of the latest hardware brief

The updated brief repeats most of the earlier material. Its full difference,
including the changed Part B inventories and Part C documents, was reviewed;
unchanged documentation retains the earlier coverage. Earlier findings about
MFA, archives, backups, memory limits and DHCP remain relevant. The newer
upstream storage-screen change independently addresses part of the original
largest-disk risk; the reviewed ISO continues to avoid a largest-disk rule.

- **Latest A9.6 — Wrong for this NAS:** a DS216 has two bays. Expansion to
  three or four internal drives is not this machine's plan. One disk has no
  disk redundancy; the second provides the chosen mirror. Its ext4 filesystem
  does not supply Synology Btrfs Snapshot Replication. Restic snapshot history
  and the independently protected offsite copy remain separate requirements.
- **Latest A9.11 — Correct with conditions:** Ubuntu 24.04's
  `dropbear-initramfs` uses `/etc/dropbear/initramfs/`; keys can be restricted
  to `cryptroot-unlock` with forwarding and PTY disabled. Package files were
  checked against signed Ubuntu archive metadata. The upstream implementation
  needed stronger key validation, readiness checks and a fail-closed decision
  on unattended reboots when encryption state is unknown. Merely writing a
  configuration file does not prove the running initramfs contains it. The
  storage screen and its LVM/LUKS checkbox were observed in BIOS and UEFI
  boots of the original reviewed ISO. A complete encrypted install and real
  SSH unlock still require a disposable VM or the target machine.
- **Latest A9.12 — Correct mechanism, fragile original implementation:**
  `discard` is a valid crypttab option for passing TRIM through dm-crypt.
  Enable it deliberately for the encrypted root SSD, preserve the original
  file, avoid unrelated volumes, and handle an initramfs rebuild failure.
  Discard reveals allocation patterns beneath encryption; it does not expose
  plaintext. The upstream edit was broader than the intended root SSD.
  Ubuntu's signed GRUB package has an embedded `/EFI/ubuntu` prefix, so a
  coherent fallback set can still locate the normal configuration there.
  A partial copy, stale sentinel file or missing companion binary must not be
  called a working fallback. Physical HP firmware and Secure Boot enforcement
  remain **Unsure** until tested; copying files is not that test.
- **Latest A9.13:** the original answer 12 still applies. For the now-known
  hardware, keep the five initial apps within the enforced aggregate budget,
  measure CPU/RAM/SSD pressure, and add heavy ML/transcoding stacks only after
  those measurements. No undocumented HP driver download is required merely
  because the box is an EliteDesk; confirm its actual PCI devices and supported
  kernel drivers during installation.

Early-boot SSH is explicit setup, not automatic exposure. Tailscale and the
normal firewall are not running in initramfs. Use a reachable, verified LAN
address and verify Dropbear's separate host key; the sole directory/DNS server
may be locked, so its normal hostname may not resolve. No router port forward
or public unlock endpoint is part of this design.
