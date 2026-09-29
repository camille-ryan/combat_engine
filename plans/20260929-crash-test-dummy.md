# A crash test dummy (#243)

## Why it is the right call

The issue was filed off a real divergence and I was on the wrong side of it for
several hours. Building a closed-form damage model I checked it against the
simulation and the two disagreed by a third. The maths was right both times.
The board was wrong: the target creature carries an immediate interrupt that
fires on being hit and makes the attacker reroll, so a third of landed hits were
turned back into misses.

    AttackResult(hit=False, natural=5, total=12, rolls=[18, 5])
                                                       ^^^^^^^
                                     the 18 hit, the reroll missed

Nothing about that is visible from outside. The hit rate was 67% as predicted,
the per-hit damage was 13.07 as predicted, and the total was still two thirds of
what it should be, because 154 of 404 hits quietly stopped being hits.

`scripts/expect.py` landed today with the workaround in it, and the workaround
is exactly what the issue asks to replace:

```python
foe = loader.spawn(world, DUMMY, (5, 6), team=Team.ENEMY)
world.need(foe, Powers).known.clear()      # <- strip the interrupt
hp.max_hp = hp.hp = 24 + 8 * level         # <- overwrite every number
d.values[Defense.AC] = level + 14
```

That is a real creature with everything about it deleted. It works, it is
undocumented at every call site that copies it, and the next instrument to be
written will not know to do it.

## The numbers, measured rather than recalled

Standard rank, conjurations and the two refused rows excluded.

Defences, over **1,997** standard monsters:

| | |
|---|---|
| AC | level + 13.92 |
| Fort | level + 12.12 |
| Ref | level + 11.96 |
| Will | level + 11.29 |
| Initiative | level + 0.46 |

So: **AC level+14, Fort level+12, Ref level+12, Will level+11.** Will is a point
softer than the other two across the whole corpus, which is worth keeping rather
than flattening — a row that targets Will should measure as slightly better,
because against real monsters it is.

Hit points. The per-level means against `24 + 8L`:

    lvl    1     5    10    12
    mean  28.0  62.3 103.7 117.2
    24+8L   32    64   104   120

A least-squares fit over all 1,997 is **8.13 x level + 20.8**. `24 + 8L` is
exact from about level 5 up and **four points high at level 1**.
`docs/AI_DOCTRINE.md` now names `24 + 8 x level`, so that is what the dummy
should use — but the discrepancy belongs in a comment, not swallowed.

Attack and damage, over **623** at-will monster attacks against AC:

| level | 1 | 3 | 5 | 7 | 10 | 12 |
|---|---|---|---|---|---|---|
| attack over level | 4.96 | 4.86 | 5.03 | 5.00 | 5.00 | 4.88 |

**level + 5**, flat, and it agrees with `monster_math.ATTACK_MM3` which is
already 5 for every role. That is a good sign: two independent routes to the
same number.

Damage should come from `monster_math.FITTED` and not from a fit of my own. A
blended fit over the corpus gives `0.57 x level + 7.2`, but that averages MM1
and MM3 rows together and the revision was *about* damage — MM1 does 11.5 at
level 10 where MM3 does 17.3. `FITTED.damage` is `6.6 + 0.82 x level`, already
least-squares fitted to the 154 MM3 rows, already the table `TO_MM3` uses, and
already argued with in `scripts/mm3.py`. Reusing it means the dummy moves if that
argument is ever settled differently.

## The one design question, and it already has a sanctioned answer

A dummy's attack bonus is `level + 5`, which varies with the dummy's level. The
header is static data:

```python
printed: int | None = None    # a monster's finished attack bonus, level included
```

`Attack.printed` cannot hold `level + 5`. The root `CLAUDE.md` says to resolve
anything per-caster *in the header* and never by making the body compute it —
but `Attack`'s own docstring names the exception:

> A power whose attack bonus depends on the situation ignores this and calls
> `c.attack(...)` with whatever it worked out.

So the dummy's basic attacks call `c.attack(world.scaling.trim(c.level + 5,
c.level), AC)` from the body. The cost is that the AI policy cannot read the
dummy's attack line without running it, which for a crash test dummy is the
right trade: nothing needs to plan the dummy's turn well.

The alternative is a new `Attack` field — something like `over_level=5` — which
is an engine change, widens `audit.py` to all 12,197 rows, and buys a policy
read nobody needs yet. Not worth it for two rows. If monster rows ever want to
be written level-relative, that is the issue to file then.

## Shape

`src/combat_engine/content/dummy.py`, because the two basic attacks have to be
registered rows and rows live in content. It cannot use `loader.spawn`, which
reads a database row, so it assembles the components itself the way `loader`
does — and the level term comes out of the defences the same way, with
`scale="monster"`, or bounded scaling will not bound the dummy.

```python
MBA = "dummy:mba"       # melee basic attack, no rider
RBA = "dummy:rba"       # ranged basic attack, no rider

def spawn(world, level, square, *, team=Team.ENEMY) -> int
```

Two rows, hand-written, no markers: both are fully implemented or they are not
worth having.

## What has to change to make it load-bearing

Filing it is not the same as using it. The issue's second sentence is the real
requirement — *correctness tests for player options should only be tested
against the crash test dummy* — so:

* `scripts/expect.py` drops its `target()` hack and calls `dummy.spawn`.
* The scratch comparisons behind today's numbers get re-run against the dummy,
  and the figures restated. They should barely move — Will goes from level+11
  to level+11 and the NADs from a flat level+11 to 12/12/11 — but "should barely
  move" is a prediction and it costs one run to check it.
* `audit.py` provokes rows with its own harness. Whether it should use the dummy
  is a separate question from this issue and probably a bigger win; it is where
  the 173-rows-on-borrowed-evidence bug came from. Not in this plan.

## Verification

* The dummy's own numbers, printed by level and compared against the table
  above. A dummy that does not sit on the measured line is the one thing this
  cannot get wrong.
* `expect.py` re-run before and after the switch, both figures shown. Any
  movement beyond the NAD change is the hack having been hiding something.
* `replay verify` unchanged — the dummy is new and nothing in the fixtures uses
  it, so any movement means it was registered in a way that perturbs the
  registry.
* `audit.py --calls 'c.attack('` covers the two new rows cheaply; the wide run
  is not needed because nothing existing changes.

## Not in this plan

* Switching `audit.py` over. Bigger, separate, and it interacts with that
  instrument's verdict logic.
* An elite or solo dummy. The issue asks for one standard creature and a
  `rank_hp` multiplier is a later argument.
* Giving the dummy resistances or a role. The point of it is that it has none.
