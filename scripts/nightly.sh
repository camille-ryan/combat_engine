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
# Reads nothing, commits nothing, and leaves three things behind. It tolerates
# exactly one pre-existing modification -- its own ledger, when the sha is all
# that moved -- because refusing that made each sweep disable the next one;
# see the guard below.
#
#   logs/nightly-<date>T<hhmm>.log   the full run, stamped to the minute
#   logs/nightly-latest.log   the most recent ATTEMPT, including a skip
#   logs/NIGHTLY-FAILED       written on a red sweep, removed on a green one
#
# **That third line used to say "exists if and only if the last run was red",
# and it was false.** Both skip paths below `exit 0` without touching the
# marker -- correctly, since a skip is no verdict and must not erase a real
# one -- so a red sweep followed by any number of skips leaves a file that the
# stated invariant says describes the last run. Live on 2026-10-13: the marker
# read `FAILED at 227e2b0` while the last attempt had skipped on a dirty tree,
# two days and 60 commits later. A session following the documented one-line
# check concludes "the last run was red"; the last run did not run.
#
# So the marker is evidence about *a* sweep, not the latest attempt, and
# `check.py` now reconciles the two every run -- `_nightly_state` reads this
# log's mtime and its first word, and says SKIPPED, RED or clean in words with
# the age beside it. That is the #543 signal; do not go back to reading the
# marker's existence.
#
# The other signal needs no file at all: a wide sweep writes
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
# **A pid and `kill -0`, not a `pgrep` pattern.** This was
# `pgrep -f "scripts/check\.py"`, which is a substring match over every
# command line on the machine -- so a session that merely *grepped* for
# check.py during this window matched it. On 2026-10-15 at 03:07 one did,
# and the sweep skipped with nothing running: the log said "a check.py is
# already running" while `pgrep -af` found none. A whole night's net lost
# to a false positive, and silently, because a skip is not a failure.
#
# `check.py` writes its own pid to `logs/check.pid` and removes it on the
# way out. A stale file -- a sweep that was killed -- reads as not running,
# which is the safe direction: the worst case is two sweeps contending,
# which is loud, against a skip that looks like a clean night.
LOCKFILE="logs/check.pid"
if [ -f "$LOCKFILE" ] && kill -0 "$(cat "$LOCKFILE" 2>/dev/null)" 2>/dev/null; then
    echo "SKIPPED $(date '+%F %T') -- a check.py is already running (pid $(cat "$LOCKFILE"))" | tee "$LOG"
    cp "$LOG" logs/nightly-latest.log
    exit 0
fi

# **A dirty tree makes the result unattributable.** The sweep's whole value is
# "every row was fine at commit X"; run it over uncommitted edits and it says
# nothing about any commit. Refused rather than run anyway.
#
# **Except its own ledger, and leaving that out made the sweep disable the
# next one.** A sweep always rewrites `audited.json`'s `sha` -- the bottom of
# this script says so and calls it bookkeeping -- and this script does not
# commit it, correctly. But nothing else does either, so the tree stays dirty
# and *tomorrow night refuses to run*. Measured on the record:
#
#   2026-10-12 02:19  swept at 227e2b0, left audited.json modified
#   2026-10-13 03:07  SKIPPED -- the tree is dirty:  M audited.json
#   2026-10-14 02:18  only ran because it was kicked by hand
#
# One sweep per two nights at best, and the gap is invisible: a skip is not a
# failure, so nothing goes red and `logs/NIGHTLY-FAILED` still describes some
# older run. The guard was refusing a tree whose only edit was the previous
# sweep's own output.
#
# So the ledger is excluded **only when the sha is the single thing that
# moved**. A human-edited baseline, or one whose `silent_refs` differ, is a
# real edit and still blocks -- which is the case the guard exists for, since
# `audit.py` reads that file as its per-ref baseline and a hand-tuned one
# would certify nothing.
# **Not stashed, and the first draft of this did stash it.** Putting the
# ledger aside for the run means popping it afterwards on top of the file the
# sweep has just rewritten -- a conflict, over the one file whose whole job is
# recording the run. The flag below leaves it exactly where it is: its `sha`
# is bookkeeping `audit.py` reads for "owed since", never part of the per-ref
# baseline, so the sweep behaves identically either way.
LEDGER=scripts/fixtures/audited.json
DIRTY=$(git status --porcelain)
if [ -n "$DIRTY" ] \
   && [ -z "$(git status --porcelain -- . ":(exclude)$LEDGER")" ] \
   && [ "$(git diff -U0 -- "$LEDGER" | grep -c '^[-+][^-+]')" = "2" ] \
   && [ "$(git diff -U0 -- "$LEDGER" | grep -c '^[-+][^-+].*\"sha\"')" = "2" ]; then
    echo "note: $LEDGER differs from HEAD by its sha alone -- the previous"
    echo "      sweep's own bookkeeping, not an edit. Sweeping anyway; see"
    echo "      the comment above this check."
    DIRTY=""
fi
if [ -n "$DIRTY" ]; then
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
