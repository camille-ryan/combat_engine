# Threat reduction measured in rounds, derived from what a condition does

*(On implementation, copy to `plans/20261001-threat-rounds.md` per the repo
convention.)*

## Context

`DoctrinePolicy` scores threat removal from **hit points only**:

```python
dealt = T.row_damage(world, actor, action.ref)
share = min(1.0, dealt / health.hp)
removed += share * T.threat(world, t)
```

So control is worth nothing. An end-of-next-turn immobilise and a save-ends
immobilise score **identically — both zero** — and so does immobilising a melee
creature that is already in your face, which is the case
`notes/DOCTRINE.md` §1 calls the most load-bearing distinction in the notes.
`threat.CONDITION_THREAT` was supposed to carry this and **is read by nothing**
(715e998).

Camille's model for this pass, and it is the whole design: **threat is rounds of
damage, and an effect removes rounds.** Killing removes 3. An EoNT immobilise on a
melee enemy adjacent to nobody removes 1. Save-ends removes 1.8. A melee creature
with a ranged backup loses only the *differential* between the two. An attack
debuff removes a hit-chance-weighted share. And a creature's hit chance, for threat
purposes, is against the best target it can reach **after moving**.

Two decisions Camille settled before this was written:

* **Derive the denial from `conditions.Rules`, and delete `CONDITION_THREAT`.**
  Not a hand-set number per condition — the mechanical consequence is already in
  the kernel and a single number per condition cannot express the adjacency case
  that prompted this.
* **Include enablement**, not only denial: `grants_ca`, `Rules.defences` and a
  plain AC debuff raise *party* damage, and they are currently worth zero.

## What the kernel already provides, so nothing here is guessed

This model needs no new declarations, which is the reason it is worth building.

| what | where |
|---|---|
| what a condition mechanically does | `conditions.Rules` — `cannot_move`, `cannot_act`, `one_action`, `no_standard`, `attack`, `defences`, `weakened`, `speed_cap`, `halve_speed`, `grants_ca` |
| the conditions an effect imposes | `Effect.conditions` (`durations.py:80`) |
| its duration | `Effect.when` |
| the modifiers it lays, and on whom | `Effect.mods: list[tuple[eid, Mod]]`; `Mod.what` is `"attack"`, `"damage"`, `"speed"` or a `Defense` |
| what is on a creature now | `world.effects.of(eid)` |
| the save | `durations.py:567` — `roll.total + bonus >= 10` |

**1.8 is not a guess and should be derived, not typed.** A save is d20+bonus ≥ 10,
so 11 faces in 20 succeed: 55%, and the expected number of the target's turns a
save-ends effect survives is `1 / 0.55 = 1.82`. That is Camille's 1.8×, and writing
it as `1 / SAVE_CHANCE` means it tracks the rule if the rule is ever read again.

`Rules` covers every case in the spec: `cannot_move` is the immobilise, `attack` is
the attack debuff, `weakened` is damage halved, `speed_cap` is slowed, and
`grants_ca` and `defences` are the enablement half.

## Step 0 — a prerequisite bug, found while planning

**`row_damage` measures every row on one shared board and the conditions left
standing by earlier rows inflate later ones.** `expect.expected` restores hit points
after each path and nothing else, and `threat._BOARDS` caches one board per caster,
so a row that knocks the target prone or marks it makes every row measured after it
look better.

Measured on a level-5 fighter, 37 rows, shared board against a fresh one per row:

    p4316   8.80  vs  6.35   +2.45   (+39%)
    p4312  10.85  vs  9.45   +1.40
    p4324  19.73  vs 18.57   +1.15
    ...    7 of 37 rows differ, every delta positive

So the shipped threat figures are systematically high and order-dependent. This
pass leans much harder on `row_damage`, so it is fixed first: reset the scratch
board's effects between rows — `world.effects` cleared and re-armed, or a fresh
board per row and the cache keyed per `(caster, ref)` rather than per caster.
Whichever is cheaper once measured; correctness is not in question.

## Step 1 — `threat.py`: rounds, and the best target reachable after moving

**`expected_vs(world, eid, ref, target)`** — what one row would deal to a *real*
target. `row_damage` prices against the baseline; scaling it by the ratio of live
hit chance to baseline hit chance gives the live figure without a second Ledger run:

```
expected_vs = row_damage(ref) * hit_chance(world, eid, target) / hit_chance(baseline)
```

Both halves are available: `Power.hit_chance` live (it returns `None` for a row
with no attack line — gate on that, per #259) and the same call on the scratch board.

**`per_round(world, eid, *, constraint=None)`** — the best single round of damage,
against the best target it can reach. Camille's rule: the best target it can
**currently hit after moving**. Reachability approximated as
`distance(here, target) <= speed + reach.size` rather than a Dijkstra per candidate
square — `movement.reachable` exists and is the exact answer, but this is asked per
enemy per turn and a square of error does not change which target is best. The
approximation goes in the docstring, not in a comment.

`constraint` is what makes denial computable, and it is a small record rather than a
flag: no movement, a speed cap, no standard action, an attack penalty, damage
halved. With no constraint the creature may move; with `cannot_move` it may only use
rows that reach a target from where it stands — which is exactly the melee/ranged
differential Camille described, falling out rather than special-cased.

**`threat(world, eid)`** keeps its signature and its meaning — `ROUNDS` best rows
against the best reachable target, as a share of the opposing pool — so
`DoctrinePolicy`'s existing weight still means what it meant. It becomes
**board-dependent**, because the best reachable target is, so the cache key gains
the round: `(id(world), eid, world.round)`.

## Step 2 — `threat.py`: what a row does, read off the effects it lays

**`row_effects(world, eid, ref)`** runs the row on a **fresh** scratch board and
reads `world.effects.of(target)` afterwards, returning per effect: its `when`, its
`conditions`, and any `Mod` it laid on the target. Cached per `(caster, ref)`.

This is why no header field is needed and why #263's option 3 is not taken: the row
is run and the answer observed. It is safe on the scratch board, which is the whole
reason that board exists, and `Ledger` already lets conditions land for real —
its docstring says so.

Two things it cannot see, and both belong in the docstring rather than being
discovered later:

* **`Mod.when` is a closure** and its own docstring calls it "un-introspectable". A
  modifier gated on a circumstance reads as though it always applies. Over-counts.
* A condition applied on a **miss**, or on a branch the dictated hit did not take,
  is not observed. Under-counts.

**`ROUNDS_OF: dict[When, float]`** — how many of the affected creature's turns a
duration covers. `SAVE_ENDS` is `1 / SAVE_CHANCE`; `EONT`, `EOTNT`, `SONT`, `SOTNT`
are 1; `ENCOUNTER`, `STANCE`, `SUSTAIN` cap at `ROUNDS`; `INSTANT` is 0.

**`EOT` is asymmetric and is the one entry worth stating.** "End of this turn" ends
before the enemy acts, so it denies **nothing** — but a defence debuff lasting that
long still helps every ally who acts later this round. So denial reads `EOT` as 0
and enablement as ~0.5, and that is two lookups rather than one table being wrong
for half its callers.

## Step 3 — `threat.py`: denial and enablement, both in rounds

**`denial(world, eid, effects)` → rounds of the creature's own damage removed.**

```
free      = per_round(eid)                      # unconstrained
pinned    = per_round(eid, constraint=from_rules(conditions, mods))
per_turn  = max(0.0, 1 - pinned / free)         # share of a round lost
rounds    = ROUNDS_OF[when] * per_turn
```

Every case in the spec falls out of one expression:

| case | why |
|---|---|
| immobilised, melee only, nobody adjacent | `pinned = 0` → a whole round |
| immobilised, already adjacent | `pinned ≈ free` → **nearly nothing**, which is §1 |
| immobilised, has a ranged backup | `pinned = ranged` → the differential |
| stunned, dying, petrified | `cannot_act` → `pinned = 0` |
| attack debuff of N | hit chance falls by `N/20`, so `pinned/free` is the ratio of hit chances — "hit chance weighted" |
| weakened | `Rules.weakened` halves damage → `pinned = free/2` |
| slowed | `speed_cap=2` shrinks the reachable set, so it bites only when the target is far |

**`enabled(world, eid, effects)` → rounds of *party* damage gained.** `grants_ca` is
+2 to hit, `Rules.defences` and a `Mod` whose `what` is a `Defense` are the printed
debuff. Worth the resulting rise in party hit chance across the party's own best
round:

```
gain = ROUNDS_OF[when] * (hit_after - hit_before) / hit_before * per_round(my_side)
```

Note the denominator differs from denial's: this is a share of the **enemy's** pool,
because it is party damage, and denial is a share of **ours**.

## Step 4 — `doctrine.py`

`threat_removed` becomes the sum of the damage part and the denial part, in rounds:

```
rounds  = min(1.0, dealt / hp) * ROUNDS                    # hit points, as now
rounds += denial(target, row_effects(actor, ref))          # control
removed = min(rounds * per_round(target), threat_hp(target)) / our_pool
```

The `min` is the cap that keeps a kill worth 3 rounds and no more. **Camille's
figures are the acceptance test**: a kill 3 rounds, an EoNT immobilise on an
isolated melee enemy 1, save-ends 1.8, and a creature with a ranged backup only the
differential.

One new term, `party_enabled`, weighted at `SHARE` like the rest, so the AC debuff
and `grants_ca` stop scoring zero.

`CONDITION_THREAT` and `condition_threat()` are **deleted**, per Camille's call.
Nothing reads them, and `from_rules` is what replaces them.

## Files

| path | what |
|---|---|
| `src/combat_engine/engine/threat.py` | the scratch-board fix, `expected_vs`, `per_round`, `row_effects`, `ROUNDS_OF`, `denial`, `enabled`; delete `CONDITION_THREAT` |
| `src/combat_engine/engine/doctrine.py` | `threat_removed` in rounds, `party_enabled`, docstring |
| `scripts/doctrine.py` | report rounds denied per condition, and a table of the acceptance cases below |
| `docs/AI_DOCTRINE.md` | what is implemented now |

`engine/policy.py` and `LinearPolicy`'s 37 weights are **not** touched, so
`--policy linear` stays the baseline.

## Verification

**The acceptance table is the point, and it goes in `scripts/doctrine.py` so it can
be re-run.** Build a board deliberately and assert the rounds figure against
Camille's numbers:

| case | expected |
|---|---|
| kill a full-health enemy | 3.0 rounds |
| EoNT immobilise, melee enemy, nobody adjacent | ≈1.0 |
| save-ends immobilise, same enemy | ≈1.8 |
| EoNT immobilise, melee enemy already adjacent to a character | ≈0.0 |
| immobilise a melee enemy holding a ranged attack | melee − ranged, not a full round |
| −2 to a target's attack, EoNT | ≈ 1 round × (0.10 / its hit chance) |

Then, in order:

* **`uv run scripts/doctrine.py`** — every term fires, and none of them fires on an
  action where it cannot pay. That instrument caught the `takes_flank` leak onto
  `end` and is the guard against the next one.
* **Step 0 re-measured**: the 7 inflated rows agree between a shared and a fresh
  board, and the level-5 fighter's best row reads 18.57 rather than 19.73.
* **`winrate.py --policy linear --policy doctrine`, 80 seeds, seeds 121-200** —
  fresh seeds, because 41-120 have now been used to confirm one result and reusing
  them turns a confirmation into a selection. The bar to beat is what the damage-only
  model measured: 60/80 at level 5 and 67/80 at level 10. Median rounds against
  #217's 7-8.
* **`replay verify`** will move — `DoctrinePolicy` is the default. Re-record in its
  own commit, and expect three of six to be byte-identical only if no fixture has a
  condition in it, which is unlikely.
* `check.py`, `leaks.py`, `ruff`, and the wide audit — `engine/` is in `WIDE`.
  Baseline 9681 fire / 0 raise / 226 silent.

## Risks worth stating before starting

* **Cost.** `per_round` is called for a constrained and an unconstrained case per
  candidate target per action, and `threat` is now board-dependent so it recomputes
  each round. Caching per `(eid, round)` and per `(caster, ref)` should hold it, but
  this is the first change here that could make a turn feel slow, and it should be
  timed rather than assumed.
* **`Mod.when` over-counts** a gated modifier, and a miss-branch condition
  under-counts. Both are in `row_effects`'s docstring, neither is fixable without
  the header field #263 discusses.
* **The ledger is still not conserved.** Per-action greedy scoring charges for the
  same threat again as a target weakens — measured, the shares over one kill sum to
  2.63 where a creature has 1.00 to give. The `min` cap bounds a single action, not
  a sequence. Unchanged by this pass and worth its own issue.
* **Enablement assumes focus fire** — that the party will attack the debuffed
  creature. `notes/DOCTRINE.md` §7 says focus fire is the assumed doctrine, so this
  is consistent, but it is an assumption and not a fact about the board.
* **`per_round` is a best case and the doctrine says so**, so denial computed from
  it is also a best case. It will overstate against a creature whose best row is
  situational.
