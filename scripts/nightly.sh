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
# **Is a sweep due?** The schedule fires hourly now, because a calendar time
# does not survive a closed lid: `StartCalendarInterval` is deferred to the
# next wake and dropped if there is none, which cost three of seventeen
# nights outright. #871.
#
# So the hour is decided here instead, where it can be reasoned about:
#
#   * nothing to do unless the last real sweep is more than 20 hours old;
#   * normally only between 01:00 and 07:00, so a 110-minute job never starts
#     in the middle of somebody's working day;
#   * **unless it is more than 48 hours stale**, which means the overnight
#     window has already been missed twice and catching up matters more than
#     the inconvenience.
#
# "The last real sweep" is the newest dated log whose first word is not
# SKIPPED -- a skip is not a verdict, so a run of skips must not read as
# recency. A `--fast` smoke test passes this gate unconditionally.
#
# **A not-due exit writes no dated log**, because 23 of them a day is the
# noise `--history` exists to avoid -- but it does touch a heartbeat, so
# "the agent is alive and not due" stays distinguishable from "the agent is
# not running at all", which is the hole #871 is about.
if [ "${1:-}" != "--fast" ]; then
    LAST=0
    for f in $(ls -t logs/nightly-2*.log 2>/dev/null); do
        case "$(head -1 "$f" | awk '{print $1}')" in
            SKIPPED|MOVED) continue ;;
            *) LAST=$(stat -f %m "$f" 2>/dev/null || echo 0); break ;;
        esac
    done
    NOW=$(date +%s)
    AGE=$(( (NOW - LAST) / 3600 ))
    HOUR=$(date +%H)
    DUE=no
    if [ "$AGE" -ge 48 ]; then
        DUE="overdue by ${AGE}h"
    elif [ "$AGE" -ge 20 ] && [ "$HOUR" -ge 1 ] && [ "$HOUR" -le 7 ]; then
        DUE="due, ${AGE}h since the last sweep"
    fi
    if [ "$DUE" = "no" ]; then
        printf 'not due %s -- last sweep %sh ago, hour %s\n' \
               "$(date '+%F %T')" "$AGE" "$HOUR" > logs/nightly-heartbeat
        exit 0
    fi
    echo "${DUE}"
fi

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
# **The tolerance was "the sha alone moved" and it was too narrow to work.**
# It held only on a night when no row had been declared since the previous
# committed sweep -- the opposite of the normal case here. The 2026-10-23
# sweep moved three fields:
#
#     sha    81f5229 -> 402e66d
#     refs    21,405 -> 21,407      two rows declared in between
#     fired   19,672 -> 19,675
#
# so the guard read it as a real edit and 10-24 refused. Over seventeen
# nights that is **8 of the 11 failures**; the other three never fired at
# all (#871).
#
# **What it is really protecting against is a hand-tuned baseline**, which
# `nightly.sh` has always said: "a human-edited baseline, or one whose
# `silent_refs` differ, is a real edit and still blocks". So the test is now
# that question directly -- the two **per-ref lists** must not have moved --
# rather than a line count that stands in for it. `sha`, `refs`, `fired`,
# `never` and `known_quiet` are counts a sweep legitimately rewrites.
#
# The sweep still reports what moved in its `-- baseline --` section, so a
# row changing sides is read by a human either way; this only stops the
# bookkeeping from gating the next night. #867, #469.
LEDGER=scripts/fixtures/audited.json
DIRTY=$(git status --porcelain)
if [ -n "$DIRTY" ] \
   && [ -z "$(git status --porcelain -- . ":(exclude)$LEDGER")" ] \
   && [ -z "$(git diff -U0 -- "$LEDGER" \
              | grep '^[-+][^-+]' \
              | grep -E '"(silent_refs|refused_refs)"|^[-+] +"[a-z]+:?[a-z0-9:_-]+",?$')" ]; then
    echo "note: $LEDGER differs from HEAD only in counts the sweep rewrites"
    echo "      -- its own bookkeeping, not an edit. The per-ref baseline"
    echo "      (silent_refs, refused_refs) is unchanged. Sweeping anyway."
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
# **A row can leave the list two ways and only one of them is news.** It
# starts doing something, or it stops being audited at all -- `todo=`, or a
# sibling of a defective row, which drops the whole compendium entry. The
# second is a withdrawal, not an improvement, and the two lists alone cannot
# tell them apart: the sweep records what it found, and a row nobody offered
# was not found silent.
#
# This said "1 row(s) DO SOMETHING now: m1091a4" on 2026-10-16. That row does
# nothing of the kind -- `m1091a1` prints an attack line with no defence,
# which defects the whole `m1091` block, so the row is refused in play. The
# sweep now records the refused set beside the silent one and the two
# departures are reported apart.
refused = set(after.get("refused_refs", []))
left = was - now
withdrawn, healed = sorted(left & refused), sorted(left - refused)
fresh = sorted(now - was)

# **The refused set was read only to classify a silent departure, so a
# change to it was invisible.** On 2026-10-18 at `3fba7f0` this printed
# "only the sha moved -- bookkeeping, nothing to read" while two rows
# (`f2470`, `f3317`) had stopped carrying `todo=` and become usable in play.
#
# That is the change with the widest blast radius in this repo: un-refusing
# a feat makes it drawable, which re-rolls every chargen draw and moves
# every audit board, and it has cost a bisect-by-file before. A row
# *arriving* in the set is worse news -- something that used to play is now
# refused, either a new marker or a defective entry swallowing a sibling --
# and the sweep said nothing about either direction. #681.
was_ref = set(before.get("refused_refs", []))
now_ref = set(after.get("refused_refs", []))
un_refused, newly_refused = sorted(was_ref - now_ref), sorted(now_ref - was_ref)

# The counters, printed only when one of them moves, so a bookkeeping run
# stays quiet. `refs` moving at all means the corpus changed under the
# sweep, which is worth seeing beside a verdict about it.
counters = [
    (k, before.get(k), after.get(k))
    for k in ("refs", "fired", "never", "silent", "raises")
    if before.get(k) != after.get(k)
]

if not left and not fresh and not un_refused and not newly_refused \
        and not counters:
    print("   only the sha moved -- bookkeeping, nothing to read")
else:
    if un_refused:
        print(f"   {len(un_refused)} row(s) are NO LONGER REFUSED and so are"
              f" drawable now -- this re-rolls every chargen draw:")
        print(f"      {' '.join(un_refused)}")
    if newly_refused:
        print(f"   {len(newly_refused)} row(s) became REFUSED in play --"
              f" a new marker, or a defective sibling taking the block:")
        print(f"      {' '.join(newly_refused)}")
    if counters:
        print("   counters that moved:")
        for k, a, b in counters:
            print(f"      {k}: {a} -> {b}")
    if healed:
        print(f"   {len(healed)} row(s) DO SOMETHING now, and left the list:")
        print(f"      {' '.join(healed)}")
    if withdrawn:
        print(f"   {len(withdrawn)} row(s) left the list by being REFUSED in"
              f" play, not by working:")
        print(f"      {' '.join(withdrawn)}")
    if fresh:
        print(f"   {len(fresh)} row(s) went SILENT and were added -- read these:")
        print(f"      {' '.join(fresh)}")
print("   `scripts/fixtures/audited.json` is modified and NOT committed.")
PY
    fi
} 2>&1 | tee -a "$LOG"

cp "$LOG" logs/nightly-latest.log

# **A sweep the tree moved under certifies nothing, and that is not RED.**
# The dirty-tree refusal above is the same argument made before the run, and
# it stops there because nothing can make commits wait 43 minutes. So HEAD is
# read again here.
#
# This is not hypothetical. The 2026-10-16 log is headed `at 9d79a18` and its
# `audit` line reports a watermark written at `a60c4b6` -- a commit made five
# hours later, with four commits in between -- and the check died on
# `tokenize.TokenError: unterminated string literal`. That is precisely what
# `audit._source_of`'s own note predicts for a file whose line numbers move
# under an already-imported module, and all three of its call sites already
# guard it; the crash was somewhere else and unattributable. A reader
# following the log would have gone looking for a broken string in the tree.
# There is none.
#
# Reported like SKIPPED rather than like RED, for #543's reason: a
# non-verdict must never erase a real one, so `logs/NIGHTLY-FAILED` is left
# exactly as it was and the exit is 0. "Nothing to certify" is the honest
# answer either way -- the difference is only whether the obstacle arrived
# before the run or during it.
AFTER=$(git rev-parse --short HEAD)
if [ "$AFTER" != "$AT" ]; then
    MOVED=$(git rev-list --count "${AT}..${AFTER}" 2>/dev/null || echo "?")
    {
        echo
        echo "MOVED $(date '+%F %T') -- the tree moved under this sweep:"
        echo "      started at ${AT}, ended at ${AFTER}, ${MOVED} commit(s) landed"
        echo "      A sweep across two trees certifies neither, so this is not"
        echo "      a verdict and logs/NIGHTLY-FAILED is left untouched."
        echo "      Any crash above is suspect: audit._source_of's note says"
        echo "      an already-imported module whose lines have moved raises"
        echo "      from inside inspect.getblock."
    } | tee -a "$LOG"
    cp "$LOG" logs/nightly-latest.log
    exit 0
fi

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

# ----------------------------------------------------------------------------
# Re-record the impact map, which is what lets a session's per-commit run
# narrow instead of sweeping 23,062 rows. #853, #865.
#
# **After the verdict, always.** The marker and the exit code above are the
# night's product and must not wait 83 minutes behind an artifact, nor be
# affected if the recording dies. Everything below is additive.
#
# **#853 proposed folding this into the sweep itself "for the overhead rather
# than a second sweep". That premise is false and the measurement is why this
# is a separate run:** recording is ~4.3x (4.6 rows/s against 19.8), so there
# is no version of this that rides along free -- it is a second 83-minute job
# either way, and switching the gate's own sweep into a recording run would
# slow the gate and move every timing it reports.
#
# Three preconditions, each of which would otherwise produce a map that
# narrows *wrongly* rather than one that is merely stale:
#
#   * a clean sweep. A red one means rows are raising, and a row that raises
#     records only the lines it reached before raising -- so its ref lists
#     come out short, in the direction that omits rows from a later selection.
#   * HEAD where the sweep started. `_build_map` parses every engine file from
#     disk at the end to turn lines into functions, so a tree that moved
#     attributes this run's coverage to the *new* file's line numbers. Same
#     fault the MOVED check above exists for, one artifact further on.
#   * a clean tree, for the reason the dirty-tree refusal at the top gives:
#     a map attributable to no commit cannot be checked against one.
#
# And the same question is asked again afterwards, because 83 minutes is a
# long window: if the tree moved under the recording, the map is **deleted**
# rather than left in place. `impact._load` fails open with no map, so
# deleting costs a night of wide sweeps and keeping a misattributed one costs
# a silently wrong selection. Not a close call.
if [ "${1:-}" = "--fast" ]; then
    echo "map: not recorded -- --fast is the smoke test" | tee -a "$LOG"
elif [ "$VERDICT" -ne 0 ]; then
    echo "map: not recorded -- the sweep was red, and rows that raise record" \
         "short ref lists" | tee -a "$LOG"
elif [ -n "$(git status --porcelain -- . ":(exclude)$LEDGER")" ]; then
    echo "map: not recorded -- the tree is dirty beyond the ledger" | tee -a "$LOG"
else
    {
        echo
        echo "-- impact map --"
        echo "recording at ${AT} -- about 87 minutes"
        PYTHONUNBUFFERED=1 uv run scripts/impact.py --record 2>&1 \
            | grep -Ev '^#   [0-9]+/' || true
        ENDED=$(git rev-parse --short HEAD)
        if [ "$ENDED" != "$AT" ]; then
            rm -f logs/impact.json
            echo "   DISCARDED -- the tree moved from ${AT} to ${ENDED} during"
            echo "   the recording, so the line-to-function attribution is"
            echo "   against files the coverage was not taken from. No map"
            echo "   means every engine change audits every row, which is the"
            echo "   safe direction."
        fi
    } 2>&1 | tee -a "$LOG"
    cp "$LOG" logs/nightly-latest.log
fi

exit "$VERDICT"
