#!/usr/bin/env bash
# arise-nightly.sh — the Linux twin of automator/run-daily.bat.
# Pull, then run. Logs every step itself so a run that dies before Python starts
# still leaves a trace. Never runs twice at once.
#
# From SERVER_HANDOFF.md section 6 in Rehchu/arise-youtube-automation, as written
# and tested by the session that maintains the automator; unchanged here except
# for this header. arise-automator.service runs it as arise-yt with
# /etc/arise/arise.env; arise-automator-preview.service runs it with --plan-only.
set -uo pipefail

REPO="${ARISE_REPO:-/opt/arise/ARISE_YouTube_Updater}"
PY="${ARISE_PYTHON:-/opt/arise/venv/bin/python}"
STATE="${ARISE_STATE_DIR:-/var/lib/arise}"
LOG="$STATE/last-run.log"
mkdir -p "$STATE"
exec >>"$LOG" 2>&1
echo "============================================================="
echo " Arise automator - started $(date '+%F %T %Z') as $(id -un) on $(hostname)"
echo "============================================================="

exec 9>"$STATE/.nightly.lock"
if ! flock -n 9; then
  echo " another run holds the lock - not starting a second one"; exit 0
fi

cd "$REPO" || { echo " FAILED: $REPO missing"; exit 1; }

MODE=()
if git fetch --quiet origin main && git merge --ff-only --quiet origin/main; then
  echo " repo at $(git rev-parse --short HEAD) ($(git log -1 --format=%cd --date=iso))"
else
  # Stale holds.json or runner.json must never drive writes. Plan only.
  echo " WARNING: could not fast-forward to origin/main - running PLAN ONLY"
  MODE=(--plan-only)
fi

touch "$STATE/.run-started"
"$PY" -u automator/arise_daily.py "${MODE[@]}" "$@"
RC=$?
echo " arise_daily.py exited with $RC at $(date '+%T')"
if [ ! "$STATE/LATEST_REPORT.md" -nt "$STATE/.run-started" ]; then
  echo " WARNING: no new LATEST_REPORT.md - the run did not finish"; RC=1
fi
echo " ended $(date '+%F %T %Z')"
exit $RC
