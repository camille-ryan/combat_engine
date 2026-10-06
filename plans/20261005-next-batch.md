# The next batch

Written after #401 closed. The point of this plan is that **the target-filter work
is finished and the queue has reranked**, so the obvious next step — "keep
converting rows" — is the wrong one, and I can show that with numbers rather than
assert it.

## Where things stand

```
                        before #401    now
Target.relation                 92       0
Target.grants_ca                19       0
Target.flanked_by                4       0
Target.condition                62       0
Target.bloodied                 15       0
rows written             20,342      20,507  of 23,890  (86%)
declared, unfinished      2,638       2,473
undeclared                  910         910
```

188 rows moved onto a target line that states its restriction once. Seven commits,
`3f08095`..`cbf684a`, pushed.

**The top of `blocked.py --group` no longer contains a `Target.*` symbol at all:**

```
  89  Damage(dtypes=)
  64  c.grab(dc=)
  47  c.contract(ref)            <- blocked on #389, no disease table
  43  c.in_form()
  33  c.ignores_difficult(when=)
  30  Target.creature_kind
  30  c.pre_empt(ref, clause)
  30  etl.monster.attack_defence()
```

## The measurement that changes the plan

#361 says 2,863 monster abilities print a condition restriction, against the 62
that carried a marker. The natural reading is "2,800 rows still to convert". **It
is not.**

Three passes, each correcting the one before:

| signature | rows | why it is wrong |
|---|---:|---|
| a body mentioning a condition verb | 2,331 | `c.prone(...)` **imposes** prone. Counts every row that applies a condition as one that requires it — the same error as reading conditions out of Hit lines |
| tight: `requires_text` reading as a restriction, a re-pick helper, or two-arg `c.is_` | 472 | `requires_text` containing "creature" does not mean it restricts the *target* |
| hand-read sample of 30 of the 381 `requires_text` matches | **~165** | — |

In that sample, 21 of 30 are **caster** restrictions and belong in `requires=`
exactly where they are: "it must be bloodied" (×7), "it must not be grabbing a
creature", "it must have combat advantage against an adjacent enemy". Only ~6 were
genuine target restrictions.

So the remainder is **~165 rows**, dominated by the 78 re-pick and 13 `c.is_`
matches, which are the reliable signals. Treat 165 as an estimate from one 30-row
sample, not a count.

**Conclusion: converting the tail is no longer the biggest lever.** It is a
cleanup worth doing when something else is in the same files, not a project.

## A. Instruments first

Cheap, and each one is currently blind in a way that makes every later measurement
weaker.

**A1 — one AST walk covering #408 and #410.** Both are "a `def` nobody can see is
wrong":

* #408: a duplicate module-level `def`. `ruff`'s F811 is silent when the name is
  *used between* the two definitions, which is exactly when Python rebinds the
  earlier callers to the later function. Reproduced both ways.
* #410: a module-level `def` referenced nowhere. 26 of them, 2,751 scanned.

One pass collects `(scope, name)` and every `Name`/`Attribute`/`alias` use.
`lint.py` already walks `cast.py` for the duplicate case inside a class, so half
the machinery exists. Prove each half load-bearing by introducing the fault.

**A2 — #409: an `etl/` change audits zero rows.** `WIDE` holds `engine/`,
`chargen/`, `audit.py` and not `etl/`, so an extractor change selects nothing
while rewriting every number a monster row reads. Prefer widening on
`data/game.db`'s mtime over the source path: that is the real dependency and it
also catches `build.py` run against an unchanged tree, which option 1 misses.

**A3 — one bare `audit.py` full sweep, to refresh the watermark.**
`fixtures/audited.json` records `silent: 232` from an older bare run; recent scoped
runs have reported 200, then 175, as stale `KNOWN_SILENT` entries were retired.
Those numbers are **not comparable** — only a bare run writes the watermark — so
nothing currently knows the true figure. ~20 minutes, and it makes the next
regression legible.

## B. One wide batch: the engine gaps that unblock marked rows

Group these, verify each with narrow forms (`audit.py --calls`, `--sample`,
`lint.py <path>`, `replay.py verify`, hand-driven probes), and pay for **one**
`check.py` before committing the group as separate commits.

* **#399 — `Condition.DEAD`.** Camille asked for it. Unblocks `m4502a5` and
  retires `Target.condition`'s loose tenant. Must be *applied* with its event:
  `Relations.set` imposing a grab without emitting `ConditionApplied` left thirteen
  rows armed and unable to fire, and this is the same trap. Must not change what
  `can_act` or `alive` answer.
* **#405 — `c.dominate()`.** `Relation.DOMINATED_BY` has 15 readers and **one**
  writer; everything else goes through `Condition.DOMINATED`, so every reader is
  silently false. Check `vocab.py --brief` first — 15 of 21 wanted verbs in one
  issue already existed under another name.
* **`Target.creature_kind` (30 rows).** The hard one: `Cast.kinds_of` reads the
  compendium row through `Ident.ref` and the content loader, so lifting it into
  `query` touches the **engine→content seam**, which is already a known five-site
  leak. Do not add a sixth without saying so; if a sixth is needed, that is the
  issue to file.
* **`Target.ongoing` (8 rows).** Needs an ongoing-damage read in `query`, which
  does not exist. Smallest of the four and the only one with no prior art.

## C. #406 alone, not in a batch

`Rules.blind` is set for `Condition.BLINDED` and **read by nothing**, so a blinded
creature sees perfectly. The fix belongs in `query.unseen_by`, whose own docstring
argues for one place: *"so the sight and the combat advantage can never disagree."*

Kept out of B deliberately. Making blindness real reaches cover, concealment,
opportunity attacks and AI target choice, so **`replay` should move** — and a
re-record mixed with other work is where a regression hides. Normalise positional
event references first, say whether every change is an insertion or whether
behaviour moved, and record in its own commit.

## D. Content: the 174 undeclared rows

112 `cf:` features, 57 `rt:` traits, 5 powers. Ordinary content, no engine gap
named, the cheapest rows left. **`p4807` first** — another row's marker waits on
it. Check against #356 (290 named features printing into specs with no row behind
them) before starting; the 112 are probably its subject.

Coverage moves 20,507 → ~20,681 written and 910 → 736 undeclared.

## Not in this batch

* **Traps and companions, 736 rows, 0% declared.** Its own project, and #379 comes
  first because it needs author briefs.
* **#402, `browser.py` intermittency.** I tried and made it worse; three runs
  failed 2–4 checks where HEAD passes. What it ruled out is on the issue: the eight
  turns the animation check plays are **load-bearing for later checks**, so that
  check is also the thing advancing the fight. Pinning its seed breaks it outright.
  Needs the ordering coupling untangled first, which is more than a wait.
* **The ~165-row conversion tail.** See above. Do it opportunistically.
* **`localise.py --drift`** shows 2 changed and 8 dropped values on monster refs,
  predating the current rebuild. Deliberately outside `check.py` because every
  legitimate ETL change moves a value. **Do not re-freeze to clear it** — that is
  the mistake the manifest guards against. Explain each first.

## What not to do

* **Do not run the wide suite per change.** It is ~20 minutes, dominated by
  `audit.py`, and anything under `engine/` widens it to the whole tree. Batch, and
  pay once. I ran it six times in one session for work that needed it twice.
* **Do not edit the tree while a sweep reads it.** `inspect.getsource` reads from
  disk, so shifting line numbers under an imported function make `getblock`
  tokenize from the wrong offset and report a **spurious raise** — and a raise is
  the one number this project treats as inviolable.
* **Do not trust `UNUSED` as evidence a row works.** Two live raises
  (`Damage("0", n)` reaching `rng.roll`) survived sweep after sweep reporting 0
  raise, because every affected row needs a grab and the board never grabs. They
  were found by driving a row by hand. Every wave in this round was told to drive
  one, and that is why they were found.
* **Do not convert a row whose restriction is conditional or a disjunction.** Four
  and two rows respectively, each now marked. "While it has a creature grabbed,
  only that creature" is unconstrained when nothing is held; two of those four are
  the bite that *establishes* the grab.
* **Do not leave a marker naming a symbol that now resolves.** It can never go from
  absent to present, which is the worst shape a marker can have. Twelve were
  re-aimed this round for exactly that reason.

## Verification

* `uv run scripts/check.py` once per batch. **`audit` raises 0 is the line that
  must not move.**
* **A**: each new walk reports the fault before and nothing after. A3 rewrites the
  watermark; record the figure in the commit so the next reader can compare.
* **B**: `blocked.py --group` is the measure — each symbol built takes its row
  count to zero, and `todo.py` goes red the moment a symbol arrives with rows still
  unfinished, which is the signal the rows behind it are writable.
* **C**: the `replay` diff is the deliverable, in its own commit.
* **D**: `coverage.py --kind all --book ""`.
* Drive rows rather than trusting a verdict. Five defects this round were found
  only by driving, each reading as correct in source.

---

# Outcome

All four sections attempted. **A, B and C landed; D was mostly impossible and the
plan was wrong about why.**

```
cacf366  A1 A2   two defs nobody could see, and an etl change that audited nothing
bdd9134  B       dead is a condition, domination is a relation, a type line can be asked
10ba73a  B       re-record replay for Condition.DEAD: insertions only
7e3bb9f  C       a blinded creature stops seeing
632bd8e  D       coverage.py reads duplicate_of, so 72 aliases stop looking like work
6874f93  D       two rows out of 78 refs, because 74 of them already existed
```

A3's bare sweep ran inside `check.py --all`, which refreshed the watermark —
the first comparable figure in eight commits.

## What the plan got wrong

**Section D's premise.** It called the 174 undeclared features, traits and powers
"ordinary content, no engine gap named, the cheapest rows left". Of those 174:

* **72 features are aliases** — second printings of a card already declared under
  its `pNNNN` ref. `class_feature.duplicate_of` has recorded this since #218 and
  **nothing read it**. `coverage.py` does now, and the honest undeclared feature
  count is 39, not 112.
* **57 racial traits cannot be briefed at all.** `spec.py` answers "no such row"
  for every `rt:` ref, declared or not (#415). There is no legitimate input for
  them.
* **36 features and 3 powers have a printed name in their brief** (#356), so they
  cannot be handed to an author either.
* A further 6 are legs a parent feature already pays inline, recorded only in four
  module docstrings and so invisible to every instrument (#416).

**Two rows were genuinely writable** out of the 78 that cleared the name check, and
both were written. Three waves spent a full context each to establish that — twice
over, because the first two had no way to know.

**`p4807` first" was wrong too.** The database says `cf:barbarian-f2c0` is the
duplicate *of* `p4807`, so `p4807` is canonical and the tree declared the reprint.
Writing it would deal a barbarian the same daily twice.

## What the plan got right

The ordering. Instruments first was correct and paid immediately: the duplicate-def
walk found two real duplicates on its first run, and `coverage.py` reading
`duplicate_of` is what makes the remaining content work measurable at all. Had D
been attempted first, three waves would have written duplicate rows instead of
refusing them.

Keeping **#406 out of the batch** was right for the stated reason and wrong about
the outcome: `replay` did not move, because only 6 blinded-related events exist
across all seven fixtures. The net does not exercise blindness in either direction.

## Filed along the way

#411 (a character's race is discarded, so every row asking what a PC is answers
False), #412, #413, #414, #415, #416, #417, #418, #419. Closed: #381, #395,
#397-#399, #401, #403-#407, #410, and #408/#409 by the instruments commit.

## For the next pass

The cheap-content tail is gone as a category. What is left is either engine work
with rows behind it — `Damage(dtypes=)` 89, `c.grab(dc=)` 64, `c.in_form()` 43 —
or the blocked-brief issues above, of which **#419 is the best value**: one
extraction fix that both reveals more aliases and closes a name leak into an
author's brief.
