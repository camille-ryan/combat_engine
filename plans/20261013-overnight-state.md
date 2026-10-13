# The overnight run, 2026-10-13, 02:40 to 10:00

`blocked.py` **1,615 → 1,503**. Eleven commits. Every instrument green and
the tree clean, so tonight's 02:07 nightly can finally sweep.

## The wide sweep got paid, after 56 commits

The headline of the night, because it was a reliability failure rather than
a code one. The nightly went **red** on the 12th (on a `todo` check since
fixed) and **did not fire at all** on the 13th — `nightly.sh` refuses a
dirty tree and the fan-out had 55 uncommitted files at 02:07. Two nights
lost, 56 commits unswept.

Run by hand on Camille's call: **0 raise**, 21,595 rows.

The 19 "newly silent" were **not** a regression, and the way that was
established is the reusable part: a worktree at `227e2b0` and the same 19
refs audited there gave **14 `TODO` and 5 firing, none silent**. A marked
row with an empty body is *refused*, so the baseline never mentioned it;
writing the clauses is what made them visible. All 19 now carry a per-row
reason, each read before it was excused.

**#543** is the gap that let it go unnoticed: a nightly that never ran is
indistinguishable from one that passed, because the only documented signal
is the red marker.

## What landed, by family

| family | rows | what it was |
|---|---:|---|
| `compendium.silvered` | **24 → 0** | 17 written, 4 re-pointed. Every spec printed its clause in full |
| `chargen.kind_words()` + `query.living()` | **10 → 0** | one gap, two symbols |
| `c.extend_move` | 3 | two one-line content fixes unblocked them |
| `c.bonus(once=)` | 9 | 7 skill keys + 2 shoves, each spent by the wrong roll |

Engine work: `query.kinds_of` defaults every character to natural humanoid
(#542); `query.living` + `Target(living=True)`; `c.gains_property`,
`c.struck_by_property`, `regeneration(unless_struck_by=, unless_damaged_by=)`;
`WeaponChanged`; `c.watch(once=)` fixed (#540); `c.bonus(once=)` dispatch
fixed (#544). Six new `drivers.py` rules, every one plant-tested.

## The three findings worth more than the rows

1. **#540 — `c.watch(once=True)` never spent** when the handler only rewrote
   a field on its own event. Three live rows, and the sharpest chose that
   shape *expressly* to avoid shaving every blow, which is what the bug made
   it do.
2. **#542 — no player character was humanoid.** `humanoid` is the second
   most-asked type word in the tree (22 sites) and read False for the whole
   party, so a monster raising slain humanoids raised nobody and a target
   line restricted to them was offered against an empty pool. Invisible
   because every creature on the audit board is a monster.
3. **#546 — `lint.py`'s unknown-context-key walk never runs over `engine/`.**
   `lint.py` is clean; `lint.py cast.py` reports a fault *in that file*.
   `_asked_for()` defaults to content only and a differently-scoped check
   inherited it. #547 is the live fault it cannot see.

## Four lessons, each paid for once

* **An unobservable effect gets an event, not a harness that diffs state.**
  `ZoneResized` settled this (#375) and `audit.py` says so in its own words.
  I proposed the opposite in #545 and retracted it; `WeaponChanged` did the
  job and let excuses be *deleted*.
* **A drivers rule that calls the facility survives the fix being reverted.**
  Two plants stayed green tonight for exactly that, and both times the rule
  was the incomplete half. Drive the row that calls it, and assert on what it
  **asks for** — `c.shift(n)` is "up to n" and a chooser picks the square.
* **A reason in `KNOWN_SILENT` can name the wrong kind of limit.** I wrote
  "not an event" for two rows; the event exposed one as a board gap and one as
  a second unannounced writer. Both came back corrected.
* **`audit.py --changed` is not narrow** after a run of commits — it measures
  from the last full sweep's sha. Pass refs explicitly, derived from the diff.

## Still Camille's call

**Nothing.** All three decisions I put up dissolved on checking: the milestone
rows are in `story/`'s charter with #72 closed, the compendium rows were 24
mislabelled markers plus ~21 settled by #360, and the humanoid question was a
convention the tree already demonstrated. #537's "hand-keep a table" framing
was mine and was wrong.

## Next, in order

1. **`c.race_option()` 23 rows — split the symbol first.** It serves at least
   three gaps: which of five trait *legs* (`f1521`), which *borrowed power*
   (`f2871`), and which *aspect* and **when** (`f3530`, a per-encounter choice
   rather than a build-time one). Building against it before splitting would
   repeat the `c.move_through()` mistake at scale.
2. **The rest of the `chargen.*` block** — `pact_blade` 15,
   `skill_training` 14, `armor_proficiency` 10, `power_choice` 9,
   `race_choice` 6. The largest block needing **no rebuild**, so it drags no
   wide sweep or re-record behind it.
3. **The `spec.*` / `etl.*` block, with #541's three faults** — ~85 rows plus
   the brief's name-substitution bugs, all in the same files and all needing
   the same rebuild. One sweep instead of nine.
4. **#539's split** — measure how many of the 70 dead `c.terrain()` gates
   guard a *penalty* or a Requirement rather than a bonus. Cheap, and it
   decides whether that is 70 dormant clauses or a live correctness bug.
5. **#546** — one line of scope, then read what it finds before deciding
   whether it is a fix or a baseline.

## What not to do

* **Do not run another fan-out over the same rows.** Eight agents already
  swept the whole queue once; their reports say the remainder is
  confirmed-blocked on named engine gaps, which agents cannot build. Build
  the gaps, then fan out again so there is something to write against.
* **Do not let the tree be dirty at 02:07.** That is what starved the net two
  nights running, and the authoring push is exactly when it is most needed.
* **Do not trust an agent's engine-gap list** without checking the code and
  `blocked.py --group`. One bin named a facility that had landed hours
  earlier and gave a row count 7x the real one.
