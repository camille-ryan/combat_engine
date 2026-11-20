# The writable wave: 44 rows, and what the fan-out actually measured

Written 2026-11-20, continuing `plans/20261119-what-is-left-after-powers.md`.
Every number here was measured in this session unless it says otherwise.

**Read `logs/20261119-2250-agent-fanout-results.md` beside this.** It is
untracked and holds the raw per-row and per-issue reports, ~2,400 lines,
with a header explaining what it is and is not. This file is the
conclusions; that one is the evidence.

## What the plan asked for, and what it turned out to be

The handoff asked for an agent fan-out to find rows *"marked as requiring
functionality that exists now"*. Two fan-outs ran.

### Fan-out A -- 154 marked feat/item rows, 10 read-only agents

166 markers, one question each: does the facility this marker names already
exist?

```
WRITABLE_NOW   48      the facility exists; writable today
ONE_KWARG      16      the verb exists, one parameter missing
WRONG_LAYER    42      the gap is real but NOT where the marker points
NEEDS_ENGINE   59      real as stated
UNCLEAR         1
```

**64 of 166 (39%) needed no engine work or one parameter.** The plan
predicted 15-23% of rows from `triage.py`'s unbiased figure. This slice was
deliberately *not* unbiased -- it was the `probable`/`UNJUDGED`/`mis-marked`
set, with the 191 rows already judged `real` excluded -- so 39% is the rate
on the slice most likely to move, and it says the slice was chosen well
rather than refuting the 15-23%.

**The 42 `WRONG_LAYER` findings are the result worth planning around, and
they were not predicted.** A marker pointing at the wrong layer is *worse*
than a correct one: build what it names and you land a facility while the
row stays exactly as unwritable. Three cases were caught where that would
have happened:

* `c.phasing(when=)` on two rows -- `c.phasing` is a movement **mode**; the
  gate belongs in `movement.may_enter`'s context, which carries neither the
  move kind nor the originating row. A `when=` on `c.phasing` would have
  gone green on a verb neither row can call;
* `f2609`'s `flanked_by(from_square=)` -- neither of the two readers could
  ever pass it;
* `f3249`'s parameter on an offer that merges every "shift" grant and never
  learns which enemy.

**So the next pass over markers should sort on layer, not on existence.**
"Does it exist" has now been asked of the whole high-yield slice; "is it
where the marker says" has not, and it is the question that costs an engine
change when you get it wrong.

### Fan-out B -- 120 open non-`question` issues, 8 read-only agents

Every open non-`question` issue citing an issue that has since closed.

```
LIVE                 96
PREMISE_STALE         2      #505, #1143
CANDIDATE_TO_CLOSE   22
```

**The plan had the two forms backwards.** It called Form 2 -- parked on a
blocker that has since closed -- *"the high-yield form"*, quoting
`CLAUDE.md`'s hand sweep that found 9 of 63 on 2026-11-02. **It paid 2 of
120.** Six of the eight agents gave the same reason independently: every
closed citation they read was **provenance** -- a precedent, a predecessor,
a split-from, a control, a mirror -- and where a blocker genuinely had
moved, the thread had already re-read it and re-scoped itself in its own
comments. `#1039` re-checked four closed citations on-thread as each moved;
`#730` re-scoped four times.

**That is the repo's put-new-state-in-a-comment convention working, and it
has closed off the form the plan was about to pay agents for.**

What paid instead was **Form 3** -- the gap closing in the tree, usually
from another direction entirely, leaving the citing issue open behind it.
`#1085` alone moved three.

### And a third failure mode neither the plan nor `CLAUDE.md` names

**The stale part is the *last comment*.** Four cases:

| issue | what the bottom of the thread says that is false |
|---|---|
| `#838` | re-prices a fix an **earlier** comment records as built and **reverted** with numbers, and claims a cleanup is outstanding that landed three weeks ago |
| `#948` | its six "writable now" rows -- 1 of 6 has actually landed |
| `#1238` | "not reachable today, deliberately" is false now that vials deal with `rng.choice` |
| `#400` | its load-bearing marker claim is false at HEAD |

The repo's first rule says read the comments because the body is stale.
These say the bottom of the thread can be stale too, and **nothing flags
it**. `#838` is the dangerous one: a planner reading only the last comment
rebuilds a fix two sessions already threw away.

## The write wave: 44 rows, 3 correctly left alone

13 authoring agents, partitioned so no two shared a file -- **including the
target file of a `#550` clause**, which is the part that is easy to get
wrong, since several feats write their clause into another row's body in a
different directory.

```
f2033 f2880 f1552 f1652 f1114 f1021 i3525x1 i1825x1 i2801p1 i2656x1
i1371p1 i1690x1 i834x1 i3484x1 i2478p1 i2122p1 i1737x1 i3188p1 i3491p1
i3569p1 i1478x1 i1431p1 f3756 f3702 f3319 f3793 f3797 f1296 f1303 f1306
f2994 f795 f1713b f2766 f788 f759 f753 f763 f1858 f2972 f469 f2030 f682
f631b
```

**The three refusals are the quality signal.**

* **`f1876`** -- the triage candidate was refuted by measurement.
  `query.acting_independently` is `Companion.commanded != world.round`, but
  `Cast.command` stamps that field **before it rolls**, so the gate reads
  False for both kinds of attack. A uniformly dead gate.
* **`i2413x1`** -- no marker fits. The engine already behaves as the card
  demands, so `todo=` refuses a correct and inert property; `narrative=`
  means *no combat meaning* and this clause's circumstance **is** combat.
  The agent declined to invent an attribution, which was right.
* **`f1305`** -- a genuine dependency one layer down: `p2473` captures its
  area at cast time, so a cloud moved by the clause would blind the squares
  it left.

## Gate state

```
ruff check .                      All checks passed
lint.py (every touched file)      clean
todo.py                           clean -- 574 unfinished, no ARRIVED
rules.py                          clean
audit.py over the 44 + 8 hosts    0 raise, 0 newly silent
42 files, +3895 / -878            content, plus 3 instrument files
```

## Two instrument findings that cost real time

**`lint.py` could not survive a fan-out.** Three agents independently
crashed it, and one was piping the traceback through `grep -v` and reading
the truncated run as a pass. `inspect.getsource` raises
`tokenize.TokenError` on a file edited after import; the two sites that read
a row's body caught only `(OSError, TypeError)`. Fixed with a named
`_UNREADABLE` tuple, planted both ways.

**The audit board poses a trap only inside `_provoke`, and `_provoke` is
never entered for a row that already fires.** `#1402`. So *nothing* that
asks about taking a trap out of action can fire -- including `actions.py`'s
own `disable` branch, the engine's standard action for it. Instrumented:
`_pose_a_trap` called **0** times for `i1371p1` while the row fired 48.

**Two fixes were built for that and both were wrong**, and the record is
the useful part: the posed trap prints no countermeasure (true; only 130 of
631 do; irrelevant, the pose is unreachable), and its DC is unbeatable
(also true at some levels; also irrelevant). The second was measured over
all 84 rows `_wants_a_trap` reaches, **moved no verdict**, and was reverted
rather than landed -- an instrument change load-bearing nowhere should not
be in the tree.

## Issues filed: 5

```
#1399  engine/bug       Cast.surrender passes "skill:intimidate" where skills.py
                        is keyed on the bare name -- loses the ability modifier,
                        the trained +5, and every skill:intimidate bonus content lays
#1400  engine/bug       c.bonus(once=) on a skill key ignores the when= gate the
                        damage branch honours. LATENT: 0 rows carry both today
#1401  etl/bug/items    item_block.usage flattens "Encounter, N Charges/Day"; 3 of 3,752
#1402  instruments/bug  the trap pose is unreachable for a firing row
#1403  engine/bug       Trap.sprung is set only by the walked-onto handler, so a trap
                        fired through traps.fire can be fired again
```

`#1401` carries a correction to **its own body**: I had "corrected" the
triage by grepping the brief for `charge`, seeing a `5`, and concluding the
per-day pool was present. Those are per-**use** prices. The original reading
was right.

## What is still owed, in order

1. **`drivers` rules.** Each un-marked row owes one with a plant. 10 are
   written, run and planted; the remaining 34 are in flight with 7 agents
   writing to separate scratch files for the controller to merge, because
   `drivers.py` is one shared file.
2. **A `replay` re-record**, scoped to **named** rows rather than the
   batch. Two agents *measured* that their un-refused feats move nothing --
   all carry a `term` atom and `chargen.meets` returns False for every
   `term` (`#1160`), confirmed over a 9-class x 5-level x 5-race grid. The
   rows that **do** move the draw: `f795`, `f2766`, `f1296`, `f788`,
   `f759`, `i1737x1`.
3. **An `audited.json` baseline write**, its own commit -- `i1690x1` and
   `i834x1` leave `refused_refs`, `i2122p1` enters `never_refs`, `f753`
   changes bucket.
4. **One wide sweep.** Owed anyway at 24+ commits, and `scripts/audit.py`
   is in `audit.WIDE`, so the `KNOWN_SILENT` edit widens it regardless.
   Commit the batch **before** launching it or the 35 minutes buy a verdict
   naming no sha.
5. **The push, and then immediately `gh issue reopen 1397`** -- two
   unpushed commits contain the text `Closes #1397 is NOT claimed` and
   GitHub ignores the negation.

## The 22 close candidates are candidates, not closes

None was closed. Closing carries a required measurement and a statement of
what was *not* done, and each wants paying for individually. The agents
recorded, per issue, the one thing somebody must verify first -- that is the
cheapest form this work will ever be in, and it is in the log file.

## One rule for the next session, learned the hard way here

**An agent's *mechanism* is as unreliable as its *existence* claim, and a
surviving conclusion is not evidence the reasoning survived.** `i1478x1`'s
agent said `c.shift` would make the row inert because `PRONE` sets
`no_shift`. Planted, that was false -- a prone creature still answers
`can_shift` True, and `hp = 0` does not change it either. The row was
right and the *rule* was too weak: the card's "including when you fall
unconscious" is the only place the two verbs diverge, because a slide is
forced movement and consults neither gate.

So: **a rule whose assertions all stay green under the wrong
implementation is not a weak plant, it is a rule that does not yet test the
clause it names.**

---

# Closed out, 2026-11-20. What landed and what is left

## Pushed

```
14d0f927  44 marked rows written, and the markers were wrong about where the gap was
4cc164a7  A dead row-minting helper the wide run found, and a reference to an
          issue that did not exist yet
4f4f3f09  Move the audit watermark to 14d0f927b: 34 rows leave the refused bucket
```

`origin/master` and `master` agree; the tree is clean.

**The landmine fired and was handled.** `#1397` went `OPEN -> CLOSED` on the
push, exactly as the previous handoff predicted, because two older commits
carry the text `Closes #1397 is NOT claimed` and GitHub ignores the
negation. Reopened immediately, with a comment recording the measurement so
the thread does not read as resolved, and restating that **30 power rows
citing a colliding ref are still unread**. No other issue was closed by the
push -- checked, all 8 filed this session are OPEN.

## The wide sweep

One sweep for 44 rows, which is the cadence. Launched on a clean tree so
the verdict names a sha.

```
audit        1922s   watermark written at 14d0f927b
drivers      1011s   8,669 assertions hold, 0 do not
replay         22s   8 of 8 identical
leaks / cited / specs / seams / cards / keywords / targets / legs   clean
```

Three red, and none of it this batch's doing:

* **`questions`** -- two rulings arrived during the session. Both are now
  acted on and the instrument is clean: 3 parked, 0 answered, 0 without a
  plain-language version.
* **`bonuses`** -- `#1405`. It reads the **enclosing row's** card for a
  `#550` clause, so a feat-kinded bonus written into a power reports the
  power as wrong. Both findings are rows that are right; one of the two is
  pre-existing. The fix is available for free: attribute the `kind=` to the
  ref the clause is credited to.
* **`types`** -- drift that already landed, which the run says itself.

## The two rulings

**`#1389` -- answered, acted on, tag dropped.** Camille: *"yes. characters
should be able to die out of combat. [...] Ensure that disease removal is
available though. Remove disease ritual, endurance checks, and heal
checks."* The ruling unblocks the four `affliction.tick(dies=)` rows **and
puts a precondition in front of them**, measured:

```
endurance checks       EXIST   affliction.tick rolls the disease's own
                               printed check at every extended rest
heal checks            ABSENT  the only Heal check in story/ stabilises a
                               dying ally
remove disease ritual  ABSENT  no reader anywhere; game.db holds 360
                               ritual rows and none is read for this
```

One of three. **The kill waits on the other two**, by the ruling's own
wording. The skill-challenge widening wants its own issue -- story scope,
names no row.

**`#1395` -- re-asked, not acted on, and that is the right state.** Camille
did not pick an option: *"Explain why each candidate defect is actually a
defect."* Done, per row, against each ref's stored spec rather than against
the row's docstring, because the docstring is the thing making the claim:

```
3 real      m1107a0  a pull with no distance
            m4004a3  a vulnerability with no amount
            m5581a6  removes two traits the page never grants -- checked
                     every ability and the creature's own columns
4 not       m2245a0  the page prints a complete effect and no roll
            m2783a3  same
            m815a3   same
            i1431p1  OUR importer drops a number the page prints (#1401)
1 judgement m3617a3  an unspecified granted attack, not an absent fact
```

**The earlier pick is withdrawn.** The case for a seventh marker is three
rows, not eight, and two of those three are one sentence on a monster that
otherwise plays -- which is what *"only when nothing survives"* is about.
Camille's signal held: the three real ones are all magazine-sourced.

And one correction posted on the thread: I had grouped `m815a3` as a
different kind of thing, reasoning it was a rider needing no attack line.
Read raw, it is a power of its own with its own action and usage, so it is
the **same** pattern as the other two -- three rows showing one thing, not
two patterns agreeing. The verdict held and the reasoning did not, which is
the third time that happened this session.

## Issues filed: 8

```
#1399  engine       Cast.surrender's "skill:intimidate" prefix loses the ability
                    modifier, the trained +5, and every bonus content lays
#1400  engine       c.bonus(once=) on a skill key ignores the when= gate. LATENT
#1401  etl          item_block.usage drops "N Charges/Day" (3 of 3,752)
#1402  instruments  the trap pose is unreachable for a row that already fires
#1403  engine       Trap.sprung is set only by the walked-onto handler
#1404  engine       a target=SELF row's bare c.basic() attacks its own bearer
#1405  instruments  bonuses.py reads the enclosing card for a #550 clause
#1406  instruments  the credit census cannot read a parametrised c.credit block
```

## What the next session should pick up

1. **`#1389`'s two missing cure paths**, then `dies=` on the four rows.
   The ruling is recorded as a quote and the precondition is measured.
2. **`#1405`**, which is small and keeps a default-run gate green.
3. **The 42 `WRONG_LAYER` markers.** The highest-value unasked question in
   the tree: "does it exist" has now been asked of the whole high-yield
   slice; "is it where the marker says" has not, and getting that wrong
   costs an engine change that leaves the row unwritable.
4. **The 22 close candidates** in `logs/20261119-2250-agent-fanout-results.md`,
   each with the one thing somebody must verify first. None was closed --
   closing carries a required measurement.
