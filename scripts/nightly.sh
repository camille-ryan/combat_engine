#!/bin/bash
# The wide sweep, once a night, so it stops being a gate on every engine commit.
#
# `check.py --all` is ~43 minutes and `audit._changed` widens to all 21,304
# rows for any change under `engine/` or `etl/` -- so an engine change has no
# narrow option, and one session paid five sweeps, two of them for changes
# that were comments only. The sweep is a *net*, not a gate: everything that
# runs in seconds (replay, drivers, cards, bonuses, legs, leaks, todo) already
# runs per commit, and what this adds is "0 raise across every row". #469.
#
#   install:  launchctl bootstrap gui/$UID ~/Library/LaunchAgents/combat-engine-nightly.plist
#   by hand:  uv run bash scripts/nightly.sh
#   smoke:    scripts/nightly.sh --fast     (skips the two that start a server)
#
# Reads nothing, commits nothing, and leaves three things behind:
#
#   logs/nightly-<date>T<hhmm>.log   the full run, stamped to the minute
#   logs/nightly-latest.log   the most recent, whatever its verdict
#   logs/NIGHTLY-FAILED       exists if and only if the last run was red
#
# The fourth and most important signal needs no file: a wide sweep writes
# `scripts/fixtures/audited.json`, so the next `check.py` in any session stops
# printing "wide sweep owed since <sha>" on its own. Nobody has to remember to
# look.

set -u -o pipefail
cd "$(dirname "$0")/.." || exit 2
mkdir -p logs

# **Timestamped to the minute, not the day.** Dated only to the day, a manual
# run and the scheduled one share a filename -- and the second `tee` truncates
# the first's log while it is still being written. That happened the first time
# this was exercised: a trace run wiped the real run's output and left an empty
# file that read like a crash.
STAMP=$(date +%Y-%m-%dT%H%M)
LOG="logs/nightly-${STAMP}.log"

# **And refuse to run beside another sweep.** Two at once share ten worker
# processes, so both crawl and neither number means anything -- the measured
# cost of that confusion was a sweep projected at 84 minutes that was really
# contention.
if pgrep -f "scripts/check\.py" >/dev/null 2>&1; then
    echo "SKIPPED $(date '+%F %T') -- a check.py is already running" | tee "$LOG"
    cp "$LOG" logs/nightly-latest.log
    exit 0
fi

# **A dirty tree makes the result unattributable.** The sweep's whole value is
# "every row was fine at commit X"; run it over uncommitted edits and it says
# nothing about any commit. Refused rather than run anyway.
if [ -n "$(git status --porcelain)" ]; then
    {
        echo "SKIPPED $(date '+%F %T') -- the tree is dirty, so a sweep would"
        echo "be attributable to no commit. Uncommitted:"
        git status --porcelain
    } | tee "$LOG"
    cp "$LOG" logs/nightly-latest.log
    exit 0          # not a failure; there was simply nothing to certify
fi

AT=$(git rev-parse --short HEAD)
BEFORE=$(git show "HEAD:scripts/fixtures/audited.json" 2>/dev/null)

{
    echo "nightly wide sweep -- $(date '+%F %T') at ${AT}"
    echo
    # **`PYTHONUNBUFFERED`, or the log is blind until the run ends.** Python
    # block-buffers stdout through a pipe, so `tee` received nothing for
    # thirty-seven minutes and the log held only the header -- which reads
    # exactly like a crash, and is how this was misdiagnosed the first time.
    # A 43-minute job has to be watchable while it runs.
    if [ "${1:-}" = "--fast" ]; then
        PYTHONUNBUFFERED=1 uv run scripts/check.py --all --fast
    else
        PYTHONUNBUFFERED=1 uv run scripts/check.py --all
    fi
} 2>&1 | tee "$LOG"
VERDICT=${PIPESTATUS[0]}

# **The baseline moving is the news, and the sha moving is not.** A sweep
# always rewrites `audited.json`'s `sha`; that is bookkeeping. What matters is
# whether any row changed sides, so the two are reported apart and the file is
# left exactly as the sweep wrote it -- re-recording it to keep the tree clean
# would be the same mistake as re-recording a replay fixture to clear a
# divergence.
{
    echo
    echo "-- baseline --"
    if [ -z "$(git status --porcelain scripts/fixtures/audited.json)" ]; then
        echo "   unchanged"
    else
        printf '%s' "$BEFORE" > /tmp/ce-audited-before.json
        uv run python - <<'PY'
import json
import pathlib

before = json.loads(pathlib.Path("/tmp/ce-audited-before.json").read_text())
after = json.loads(pathlib.Path("scripts/fixtures/audited.json").read_text())
was, now = set(before.get("silent_refs", [])), set(after.get("silent_refs", []))
healed, fresh = sorted(was - now), sorted(now - was)
if not healed and not fresh:
    print("   only the sha moved -- bookkeeping, nothing to read")
else:
    if healed:
        print(f"   {len(healed)} row(s) DO SOMETHING now, and left the list:")
        print(f"      {' '.join(healed)}")
    if fresh:
        print(f"   {len(fresh)} row(s) went SILENT and were added -- read these:")
        print(f"      {' '.join(fresh)}")
print("   `scripts/fixtures/audited.json` is modified and NOT committed.")
PY
    fi
} 2>&1 | tee -a "$LOG"

cp "$LOG" logs/nightly-latest.log
if [ "$VERDICT" -eq 0 ]; then
    rm -f logs/NIGHTLY-FAILED
    echo "clean at ${AT}" | tee -a "$LOG"
else
    {
        echo "FAILED at ${AT} -- see logs/nightly-${STAMP}.log"
        date '+%F %T'
    } > logs/NIGHTLY-FAILED
    echo "RED at ${AT}; wrote logs/NIGHTLY-FAILED" | tee -a "$LOG"
fi
cp "$LOG" logs/nightly-latest.log
exit "$VERDICT"
