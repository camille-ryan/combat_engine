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

## Rules

* **An instrument must not skip itself quietly.** A check that runs on half
  its runs is not a check. Pin the seed, and report a skip as a skip rather
  than passing.
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
* **Kill a spawned server by process group.** `self.proc` is the `uv`
  wrapper, not the server; `terminate()` orphaned the uvicorn underneath and
  69 of them accumulated over three and a half days. `start_new_session=True`
  plus `killpg`.
* Use `$CLAUDE_JOB_DIR/tmp` or a uniquely named scratch file. The scratchpad
  is shared and two agents have overwritten each other's.

## What each is for

| | |
|---|---|
| `check.py` | runs every instrument; `--fast`, `--all`, `--history` |
| `audit.py` | fire every declared row; catches raises and silent rows |
| `lint.py` | ruff, plus two structural walks. Python only — never `web/` |
| `leaks.py` | has a printed name got into the repo, or into a spec |
| `blocked.py` | unfinished rows and what each waits on; the work queue |
| `todo.py` | are the markers still true; fails when a wanted symbol arrives |
| `coverage.py` | written / not written / half-written on purpose |
| `replay.py` | the regression net over `fixtures/`; `record`, `verify` |
| `api_smoke.py` | play an encounter over HTTP |
| `browser.py` | drive the real page in headless Chromium |
| `spec.py` | the sanitised brief handed to an author |
| `vocab.py` | the generated `Cast` surface — the authority on what exists |
| `fight.py` | play a whole fight and print the log |
| `show.py` | one row, printed text beside emitted events |
| `build.py` | rebuild `data/game.db` |
| `bonuses.py`, `legs.py`, `mm3.py`, `issues.py`, `progress.py`, `waves.py`, `transcript.py` | narrower checks and ledgers |

## Re-recording fixtures

`replay.py record` rewrites the regression net, so it is the one command that
can hide a bug rather than find one. Before recording:

1. Show the diff is what you intended. **Normalise first** — positional event
   references (`Hit#1049`) and effect ids renumber whenever anything is
   inserted ahead of them, so a real comparison substitutes those out.
2. Say whether every change is an *insertion* or whether behaviour moved.
3. Record in its **own commit**, with nothing else in it, naming what moved
   and why. A re-record mixed with other work is where a regression hides.
