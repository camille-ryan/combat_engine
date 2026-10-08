# Instruments

`scripts/` belongs to no component. Each file plays the real thing and reports
what it saw. `check.py` runs them.

Global rules are in the root `CLAUDE.md`.

## The rule that matters

**Never loosen an instrument to make a number look better.** If a check goes
red, either the code is wrong or the check's *definition* is — say which, with
evidence, and change the one that is wrong.

Both directions have happened here and both were caught by being explicit:

* A check was over-broad: `_check_area_aiming` failed two rows for offering
  nowhere to aim, and the first diagnosis was that the check read "burst" too
  widely. Probing the render layer **refuted that** — close bursts normally
  serve 88 squares — and the check was right. Reverting the edit found the
  real bug.
* A verdict was too generous: `audit.py` credited a row with the harness's own
  provocation, so 173 rows reported `ok` on borrowed evidence. Fixing it moved
  them to SILENT, which **looks** like damage and is the instrument starting
  to work.

So when a number moves the wrong way, say so plainly in the commit with both
figures. A silently narrowed check is worse than a red one.

**And a check that cannot pass is the same failure pointed the other way.**
`audit.py` wrote `silent: 223` into `fixtures/audited.json` and then failed for
finding 223, because the verdict compared the count against zero and nothing ever
read the file back. `check.py` therefore reported `FAIL audit` on every run whose
scope reached any of those rows — which, since an `engine/` change widens to the
whole tree, was most runs. The one run that mattered would have looked identical
to the two hundred that did not.

The fix is **not** raising the number. It is a per-ref baseline that may not get
worse: a silent row not on the list is red, a listed row that works is red, a
listed row still silent is named and passes. That is *stricter* than a count,
which cannot tell a narrow run whether its silent rows are the known ones and
cannot see ten rows healing while ten others break. The same shape as
`localise.KNOWN_LABEL_DRIFT`, `cards.KNOWN` and `leaks.DEFERRED` — tightened when
it improves, red when it regresses, never a bare allowance. #372.

## Rules

* **An instrument must not skip itself quietly.** A check that runs on half
  its runs is not a check. Pin the seed, and report a skip as a skip rather
  than passing.

  **And make the total reconcile, because the rule alone did not hold.**
  `browser.py` has a `Checks.skip` whose docstring quotes this rule, and
  **eight sites in the same file were still breaking it**: seven wrote
  `check.that(True, "... (skipped)")` — the parenthetical admitting it while
  `that(True, ...)` increments `passed` — and one cluster sat under a bare
  `if spot:` with no `else`, so two checks vanished with nothing recorded.

  None of that was found by a failing check. It was found by arithmetic: a run
  printed `55 passed, 0 failed, 1 skipped` where every other run said 57, and
  **55 + 1 ≠ 57**. So the summary now prints `(of N asked)` and
  passed + failed + skipped has to come to the same N every run. A check that
  disappears cannot hide behind a plausible headline.

  Worth copying to any instrument with a conditional check. A count of passes
  says nothing about how many questions were asked.
* **Prove a new check is load-bearing** by breaking the thing it watches and
  confirming it goes red. A check that has never failed has never been shown
  to work.
* **Measure before optimising.** `audit.py`'s ten minutes were blamed on
  `chunksize`; benchmarking showed the current setting is already the best
  available and repeat runs of the same config vary 15%. The conclusion is in
  `_changed`'s docstring so it is not re-derived.
* **`--history` exists because the previous attempt grew a suite nobody could
  afford to run.** An instrument that has caught nothing in dozens of runs
  should justify its seconds.

  **`leaks.py --history` is deliberately not in `check.py`**, and the reason is
  that rule applied to itself. The commit half reports 17 messages that name
  something and **cannot ever go green** -- a pushed message is append-only, and
  `#438` made old messages into findings by importing 90 build-option names into
  the index. A line printing 17 every run is the noise `--history` exists to
  prevent. The issue half needs the network and would hold the suite red until
  20 issues are edited.

  Same call `localise.py --drift` gets, for the same reason: *"every legitimate
  ETL change moves a value, so a gate on it would be red most of the time and
  get ignored."*

  **The gate that is worth having is pre-commit**, which is the one moment a
  message is still editable:

      uv run scripts/leaks.py --history --staged    # reads .git/COMMIT_EDITMSG

  Proven by writing a racial trait's printed name into a staged message: exit 1,
  naming the ref. #447.
* **Kill a spawned server by process group.** `self.proc` is the `uv`
  wrapper, not the server; `terminate()` orphaned the uvicorn underneath and
  69 of them accumulated over three and a half days. `start_new_session=True`
  plus `killpg`.
* Use `$CLAUDE_JOB_DIR/tmp` or a uniquely named scratch file. The scratchpad
  is shared and two agents have overwritten each other's.
* **Do not change the tree while an instrument is reading it.** Twice in one
  session a result was misread because of this, and both times the first
  diagnosis was that the instrument was flaky:

  * `audit.board` was edited mid-run, so mount rows passed and failed between
    runs. Not non-determinism -- the board had changed under them.
  * A content file was edited during a full sweep, and `audit.py` reported a
    **raise** on a row in it. The row is fine: `inspect.getsource` reads the
    file from disk, so shifting line numbers under a function imported earlier
    makes `getblock` tokenize from the wrong offset and die on an unterminated
    string. It did not reproduce on a stable tree.

  The second one is the worse trap, because a raise is the one number this
  project treats as inviolable -- so a spurious one costs real time, and a real
  one hidden among spurious ones costs more. A full sweep is ~750s: wait it out,
  and do not start a content wave underneath it either.

  **And `scripts/build.py` counts as changing the tree.** `etl.build` opens with
  `GAME.unlink(missing_ok=True)` -- the database is deleted and rebuilt from
  scratch, by design, because that is the only way to be sure what is in it. So
  a rebuild started under a running sweep pulls `data/game.db` out from under
  every worker reading it. Never run the two together.

* **A stalled sweep and a slow one look identical, and two obvious diagnostics
  lie.** `audit.py` prints a progress line to stderr every 200 rows for exactly
  this reason (#343). Before reaching for `ps`, know that:

  * **the parent sits at 0.0% CPU for the whole of a healthy sweep** -- it is
    blocked in `pool.map` -- so "the parent is idle" says nothing;
  * **the ten processes doing the work do not match the instrument's name.**
    Their command line is the multiprocessing bootstrap, so
    `pgrep -f scripts/audit.py` finds one process and `pgrep -f
    multiprocessing.spawn` finds the sweep.

  A `SIGTERM` to the parent now takes the workers with it -- measured, 10 to 0
  -- and does **not** take the caller's shell, which an earlier `killpg` version
  of the same fix did.

## What each is for

| | |
|---|---|
| `check.py` | runs every instrument; `--fast`, `--all`, `--history` |
| `audit.py` | fire every declared row; catches raises and silent rows |
| `lint.py` | ruff, plus two structural walks. Python only — never `web/` |
| `leaks.py` | has a printed name got into the repo, a spec, a commit message or an issue; `--specs`, `--history`, `--issues`, `--staged` |
| `blocked.py` | unfinished rows and what each waits on; the work queue |
| `todo.py` | are the markers still true; fails when a wanted symbol arrives |
| `coverage.py` | written / not written / half-written on purpose |
| `localise.py` | does every heroic row carry the localisation fields it needs; `--freeze`, `--drift`, `--snapshot`, `--rules` |
| `cards.py` | does a monster ability's header say the numbers its stat block prints — attack, defence, damage, range, usage |
| `drivers.py` | one mechanic's printed rule on a board built for it; positive and negative controls |
| `replay.py` | the regression net over `fixtures/`; `record`, `verify` |
| `api_smoke.py` | play an encounter over HTTP |
| `browser.py` | drive the real page in headless Chromium |
| `spec.py` | the sanitised brief handed to an author |
| `vocab.py` | the generated `Cast` surface — the authority on what exists |
| `fight.py` | play a whole fight and print the log |
| `show.py` | one row, printed text beside emitted events |
| `build.py` | rebuild `data/game.db` |
| `bonuses.py`, `legs.py`, `mm3.py`, `issues.py`, `progress.py`, `waves.py`, `transcript.py` | narrower checks and ledgers |

## Freezing the localisation

`localization/` is git-ignored and must stay so, so the freeze is a **manifest
of digests** in `fixtures/localisation.json` -- never the names. `--drift`
compares the file against it and names the ref and field that moved.

* **Re-freeze only once every change is explained.** The manifest is there to
  make a changed value visible; re-freezing to clear it is the same mistake as
  re-recording a fixture to clear a divergence.
* **`--drift` is not in `check.py`**, for the reason the rest of `localise.py`
  is not: every legitimate ETL change moves a value, so a gate on it would be
  red most of the time and get ignored.
* **The snapshot is the half a manifest cannot do.** A manifest detects loss; it
  cannot undo it, and once possessive, plural and alias forms are
  hand-corrected this file holds work that exists nowhere else -- the compendium
  carries none of those three fields. `--snapshot` writes a whole copy to
  git-ignored `logs/localization/`, and a restore has been proven end to end:
  emptying the file and copying a snapshot back gives a byte-identical
  localisation and a clean `--drift`.

## Re-recording fixtures

`replay.py record` rewrites the regression net, so it is the one command that
can hide a bug rather than find one. Before recording:

1. Show the diff is what you intended. **Normalise first** — positional event
   references (`Hit#1049`) and effect ids renumber whenever anything is
   inserted ahead of them, so a real comparison substitutes those out.
2. Say whether every change is an *insertion* or whether behaviour moved.
3. Record in its **own commit**, with nothing else in it, naming what moved
   and why. A re-record mixed with other work is where a regression hides.
