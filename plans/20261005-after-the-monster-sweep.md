# After the monster sweep

The plan at `fizzy-humming-walrus.md` is complete through Stage 2. Its Stage 3
is stale in three ways and one of its central conclusions is now wrong, so this
re-sizes what is left rather than continuing against figures that no longer
describe the tree.

## What the sweep changed

```
                     plan start        now
monsters             2,626/13,432     13,432/13,432 declared
all rows             10,700/23,890    20,342/23,890 written (85%)
declared, unfinished 1,478            2,638
distinct symbols     662              986
single-row symbols   416              623
audit raises         0                0
```

Cost: **2,425 tokens a row over 12,329 rows**, against the plan's 2,803
estimate. The one thing worth carrying forward: batch size dominated
everything. A 254-row wave ran 1,595/row where 112-row waves ran 3,008,
because the ~110k fixed cost per agent is paid whole however few rows it gets.
The plan called bigger batches "cheaper on paper and unproven in practice" —
254 in one agent is now proven.

## The three stale pillars

**1. "13 rows are ready right now" — it is 2, and neither is cheap.**
`blocked.py` reports two READY, and both say in their own notes that the
*named* symbol arrived while a residual clause did not: one needs a
vulnerability that names an attacker rather than a damage type, the other has
no Hit line in the import at all. So the plan's step 6 — "the cheapest thing
on the board, and overdue" — is empty. Delete it rather than go looking.

**2. "There is no small set of verbs that unblocks most of it" is now wrong.**
That was true of 662 symbols over 1,480 rows. It is not true of what the sweep
left:

```
top   1 symbol  names   247 row-slots
top   5         names   490
top  10         names   632      <- more than the plan's top 50 (527)
top  25         names   918
top  50         names 1,241
all 986         names 2,974
```

The reason is a side effect of the sweep's discipline. Every wave was told to
reuse a symbol already in the tree rather than coin one, so 1,166 new markers
concentrated instead of fragmenting. Leverage is now good where the plan
assumed it was poor, and that inverts the recommendation: the first ten
symbols are worth building deliberately, not "the first ~50 and stop".

**3. The deferred list grew from 3 items to 18.** Fifteen issues were filed
during the sweep, each with a driven measurement. Several are bigger than
anything in the original Stage 3.

## Recommended order

### A. The two correctness defects in shipped content

**Corrected:** an earlier draft of this called #385 "the only" one. #381 is the
same class and a comparable size, and leaving it in the deferred pile was
wrong.

```
#385  354 rows   a close burst or blast damages the creature using it
#381  407 calls  a melee-reach row swings at any distance
```

Both are shipped behaviour that is wrong in play and invisible to every
instrument — `audit` asks whether a row does something (it does), `cards`
compares against the printed words (which are faithfully transcribed). Do them
first, and separately from each other, because each moves `replay`.

354 close bursts and blasts written `target=EACH_CREATURE` damage the creature
using them. Four committed rows driven on the board all emit `DamageApplied`
against their own caster; two lose hit points (15 and 7).

The engine is correct and the headers are wrong — ten cards genuinely say
"include you", and exactly one of the 355 (`p9652`) is one of them. So 354
headers change to `EACH_OTHER` and `p9652` stays.

It changes behaviour, so `replay` will move and the re-record belongs in its
own commit. Also check the nine "include you" cards that are *not* written
`EACH_CREATURE` — each may be the same bug pointing the other way.

**#381** is the harder of the two to scope. `dsl.use(targets=[...])` applies no
reach check where `candidates()` does, and the two disagree outright: at ten
squares `candidates()` offers a target zero times and `use` rolls the attack
anyway, hits, and deals damage. `c.basic(on=)` and `c.use_power(ref, on=)` both
go straight through it — 863 explicit-target calls in `content/`, **407 of them
on a melee-reach row**, which is the set that can be wrong.

The fix is not "make `use` refuse": some callers legitimately bypass legality —
a granted swing, an opportunity attack out of turn, a death throe from a
creature that cannot act. Either check in the two content-facing verbs, or
check in `use` with an explicit opt-out for those paths. **Measure how many of
the 407 currently resolve out of reach before choosing**: a handful means the
stricter fix is affordable, hundreds means some of those rows are wrong and
want their own triage.

### B. The top ten symbols, in leverage order

Not fifty. Ten, measured:

| symbol | rows | what it is |
|---|---|---|
| `Target.kind` | 247 | a printed target carrying a condition — immobilized, prone, bloodied, grabbed |
| `Damage(dtypes=)` | 89 | one blow of two types |
| `c.grab(dc=)` | 64 | a printed escape DC |
| `c.contract(ref)` | 47 | **blocked behind #389 — there is no disease table** |
| `c.in_form()` | 43 | a creature with more than one shape |
| `c.ignores_difficult(when=)` | 33 | a narrowed terrain waiver |
| `c.pre_empt(ref, clause)` | 30 | a row that modifies another row's offer |
| `etl.monster.attack_defence()` | 29 | the spec lost the defence; an ETL fix, not a verb |
| `c.as_weapon()` | 26 | an implement used as a weapon |
| `c.race_option()` | 24 | a racial choice chargen does not model |

`Target.kind` alone is worth more than the plan's whole top-50 estimate, and
it is one coherent piece of work: a target filter that can ask what a creature
is suffering. Start there.

Two of the ten are not engine work at all — `c.contract(ref)` needs an ETL
extraction first (#389) and `etl.monster.attack_defence()` is a parser fix.
Sequence those with the ETL, not with the verbs.

### C. Traps and companions — unchanged, still the largest undeclared block

736 rows, 0% declared, and the reason is unchanged: six or seven engine
changes before the first row can be written. The plan's analysis still holds
and should be read as written. It is the right next *project* once B is in.

### D. The rest of the filed work

Fifteen issues came out of the sweep (#377–#391). They are **not** all "after"
the work above — three sit inside it, and one got cheaper the moment the sweep
ended. Placed rather than listed:

**Inside A** — #385, #381. Both above.

**Inside B, not after it** — #389 and the two ETL data faults. `c.contract(ref)`
is the fourth-largest symbol at 47 rows and **cannot be built at all** until
#389 lands: there is no disease table in `game.db`, so the ref the marker names
has nowhere to come from. Whoever builds the verb first will finish it and find
nothing to pass it. #377 and #378 are name-resolution faults in the same
component and pair naturally with `etl.monster.attack_defence()` (29 rows),
which is also a parser fix rather than a verb.

**Cheaper now than it was** — #379, names reaching author briefs. Its entire
blast radius was what a content agent is shown, and the monster sweep was the
thing issuing briefs. With that finished there are no monster briefs left to
leak into, so the urgency drops sharply even though the bug is unchanged. It
becomes a prerequisite again the day traps and companions need briefs (C), and
the fix is known-hard: widening `by_word` closes it and wrecks cards, proven.

**Genuinely after, in rough order of what a wave would hit again** — #387 (no
humanoid on the audit board, 17 rows silent by construction), #390 and #384
(what a row may refuse, and three markers naming a verb nobody will write),
#380 (`c.resist(when=)` cannot ask the one question it documents), #383
(`c.shift`/`c.jump` land in the lowest board square), #386 (`SurgeSpent` is not
a `Decision`, 12 rows), #391 (a one-line reader mirror).

**One piece of debt not on the tracker**, because it is a content fix rather
than a gap: three rows carry `todo=("c.stay_hidden()",)` and the capability
exists via `AttackDeclared`'s AFTER window. The marker names a verb nobody will
ever write, so `todo.py` can never fire on it — invisible to every instrument,
which is the worst shape a marker can have. `f1396`, `m5281a1`, `p14213`.
Recorded on #390.

## What not to do

* **Do not sweep the 623 single-row symbols.** The plan's reasoning survives
  intact here: past the top of the curve it is one verb per row, which costs
  the same as writing the row and should be judged case by case.
* **Do not re-measure the sweep.** 13,432/13,432 with 0 raise is recorded in
  `fixtures/audited.json` at 23,007 rows; a full sweep is ~19 minutes and
  tells you nothing new unless an instrument changed.
* **Do not widen the audit board casually.** `KNOWN_SILENT` carries 235
  hand-argued entries and an explicit warning: two of them record that
  dressing the board would cost every other monster its legal shift. #387 is
  the one case worth doing, and it needs a full sweep to validate.

## Verification, unchanged

`uv run scripts/check.py` — all 13. `audit` raises **0** is the line that must
not move. `replay verify` 7 of 7. For B, `blocked.py --group` is the measure:
each symbol built should move its row count to zero, and `todo.py` goes red
the moment a symbol arrives with rows still unfinished — which is the signal
that the rows behind it are now writable.
