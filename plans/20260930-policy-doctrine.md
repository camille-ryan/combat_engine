# The policy learns to score threat, position and healing

*(On implementation, copy to `plans/20260930-policy-doctrine.md` per the repo
convention.)*

## Context

`docs/AI_DOCTRINE.md` is the charter for what the AI should weigh. Almost none of
it is implemented. `policy.features` computes **44 features** against **37
weights** and every one of them is an action-kind flag or a hit-chance term:
there is nothing for *where a square is good*, nothing for *how dangerous a
creature is*, and nothing for *whether a heal is worth casting*. The doctrine
asks for exactly those three.

What is there instead is actively wrong in places. A heal is currently priced by
`allies_caught: -7.0` — the term that stops you fireballing your own party —
because a heal "catches" allies, so the scorer reads healing the wounded as
friendly fire. And `render._threat` promises in its docstring "how dangerous this
creature is, as a share of one character's health" while the code returns a
**hit probability**; nothing in the engine computes creature threat at all.

Two decisions Camille settled before this was written:

* **The new scoring lands as a second policy**, `DoctrinePolicy`, selectable
  beside `LinearPolicy` — so every claim is an A/B on the same seeds and the
  fixtures stay still until the new one earns the default.
* **#249 is fixed first.** Threat is the foundation the other two axes rest on,
  and expected damage is currently out by ~3x on conditional strikers (rogue:
  model 5.70, simulated 15.23). Building position and removal on a number with a
  3x class-dependent bias would make monsters deprioritise exactly the
  characters the doctrine says to shut down first.

Camille's framing for this pass: threat is **best-case 3-round damage**, HP
damage is **part of threat removal**, and the condition threat modifiers are set
to **0** for now so they can be tuned later.

## The one architectural constraint, found while planning

`expect.expected` **mutates the world it measures on.** Every verb the `Ledger`
does not override runs for real, so marks, pushes and conditions land on the
board, on every path explored. Its own docstring says to "hand this a board kept
for measuring and not one being played". Fixing #249 makes this sharper: once a
`Hit` is emitted, riders deal *real damage* to the target.

There is **no world clone or snapshot facility** in the engine (`grep` for
`clone`/`snapshot`/`deepcopy` across `engine/` returns nothing), and adding one
is not viable here — bus subscriptions hold closures over the original world.

So: **the policy must never call `expected` on the live board.** That is what
shapes step 1 below, and it happens to match the doctrine — "best case" damage is
a hypothetical about a creature and its powers, not a fact about the current
board. It is computed once on a scratch board and cached.

## Step 0 — fix #249, the rider gap

`Ledger.attack` builds an `AttackResult` directly instead of going through
`resolve.attack`, so **no `Hit` is emitted and nothing that watches for one
fires** — sneak attack, the fighter's mark, item and feat riders.

Two halves, because riders arrive by two different routes:

**Emit the outcome.** `Ledger.attack` emits `Hit`/`Miss` with `result`, `among`
and `branch` set the way `resolve.py:330` does, and sets
`AttackResult.advantage` from `query.has_combat_advantage` — without that the
model does not move between advantage on and off at all, which is the measured
symptom.

A rider armed by *the power's own body* closes over the **same** `Cast`
(`c.watch(Hit, rider, ...)` then `c.flat(...)` inside it — see
`content/powers/battlemind/level_1.py:545`), so its damage lands in the Ledger's
own `lines` and stays exact. That half needs nothing further.

**Capture foreign-Cast riders.** A class feature is armed at fight start by
`Encounter._arm_traits` with its *own* `Cast` — this is what a rogue's extra
damage is — so its `c.damage` rolls for real and never touches the Ledger's
lines. Close it at the single funnel: all dice go through `world.rng.roll`
(`cast.py:5851`). During each path, swap in a roller returning the **mean** of
the expression and sum `DamageApplied.amount` for blows whose `source` is the
attacker. `DamageApplied` is "damage that actually came off hit points", so this
is the post-resistance figure.

No double counting, and this is worth checking rather than assuming: the
Ledger's own `damage` records instead of calling `deal_damage`, so during a
Ledger run every `DamageApplied` comes from a foreign cast.

**How this is known to have worked**: the three measured lines in `expect.py`'s
docstring are the test. The rogue with advantage must move from 5.70 toward the
simulated 15.23, the rogue without advantage must stay near 5.83, and the
fighter (all damage in its body) must not move from 8.15 at all. Those numbers
go into the commit.

## Step 1 — `engine/threat.py`, a cached per-creature figure

New module. One public call:

```python
def threat(world, eid) -> float   # best-case 3-round damage, share of the
                                  # opposing side's hp pool
```

* **Best case over 3 rounds** = the three highest `expected` figures among the
  creature's usable rows, which is one daily plus encounters plus at-wills
  falling out naturally rather than being special-cased.
* **Normalised by the opposing team's hp pool**, per the doctrine's "divided by
  the party total hp pool". A share, not a raw number, so a weight means the same
  thing at level 1 and level 10 — the same reasoning `render._threat`'s docstring
  gives and does not implement.
* **Computed on a scratch board and cached per `(ref, level)`**, never on the
  live world, per the constraint above. Measured cost: **4 ms per creature**, 36
  ms for a full encounter, so a cache keyed on the creature's kind is ample.
* **Condition modifiers are a table of zeros**, exactly as asked:

```python
CONDITION_THREAT: dict[Condition, float] = {...}   # all 0.0 for now
```

  A table of zeros that is actually consulted is the point — it makes the tuning
  a one-line edit later, and `todo.py`-style honesty demands it be visibly zero
  rather than absent.

Two things to state in the module docstring rather than discover later: only 2 of
a level-5 fighter's 33 known refs return a non-zero figure (the rest are
utilities, features, and rows `expect` cannot evaluate standing still), and
ongoing damage is absent from `expected` entirely. So threat is a floor, not a
measurement.

## Step 2 — `engine/doctrine.py`, the three axes

`DoctrinePolicy` reuses `policy.features` for the action-kind flags it still
needs, and adds three groups. **Nothing in `policy.py`'s `WEIGHTS` changes.**

### Threat removal — and HP damage is part of it

One term, not two, per Camille's instruction. My action's expected damage
against a target's *current* hp is the share of that target's threat I remove:

```
removal = min(1.0, expected_damage / target.hp) * threat(world, target)
```

A killing blow removes all of a creature's threat; half its hp removes half.
This is what makes a striker finish a bloodied enemy instead of opening on a
fresh one, and it needs no new concept for "kill" — the clamp does it. Condition
effects enter through `CONDITION_THREAT` and therefore contribute nothing yet.

The doctrine's §1 warning applies and goes in the docstring: this is *threat
reduction* and it is **not** the same axis as *target redirection*. A defender
immobilising the enemy beside it removes almost no threat and does its job
perfectly. Redirection is not in this pass.

### Position

Reuses the helpers that already exist rather than adding geometry:

| what | helper |
|---|---|
| flanking, and setting one up | `query.can_flank`, `query.flankers`, `query.flanked_by` |
| being flanked — a bad square | `query.flanked_by` |
| cover and concealment | `query.cover_between`, `query.concealment_of` |
| difficult going | `world.difficult(for_)` (`ecs.py:113`), `world.rough()` (`ecs.py:85`) |
| hostile zones | `zones.difficult_squares()` (`zones.py:165`), plus `Zone.owner` |

**"Hostile terrain" has to be approximated, and the plan should say so.** A
`Zone` records `owner`, `label`, `squares`, `aura`, `difficult` and
`blocks_sight` — it does **not** record that it deals damage; the damage lives in
the row's own watcher. So the readable proxy is *a zone an enemy owns*, and that
is what gets scored. File the gap as its own issue rather than papering it.

The OA half is already landed and stays as it is: `provokes_now`,
`provokes_avoidably` and `leaves_melee` went in last session and took move
provocations from 57 to 21.

### Healing

Two problems, and the first is the reason healing currently scores badly.

**A heal is not friendly fire.** `allies_caught: -7.0` is what prices it today.
`DoctrinePolicy` must separate "this attack catches allies" from "this power
targets an ally deliberately", and the signal for the second is the row's own
body: it calls `c.heal`, `c.surge` or `c.temp_hp` (`cast.py:1699`, `1703`,
`1714`). Read it the way `chargen._leans_on` reads `c.<ability>_mod` — from the
source, because no header field says so. That is established precedent in this
repo, not a new trick. (#260 asks for a header signal; this does not wait on it.)

**What a heal is worth** is hp restored, capped by what the target can actually
take back — healing 20 onto a character 5 below full is worth 5 — and scaled by
how close that ally is to dropping. A heal on a bloodied ally about to be focused
is worth far more than the same hp on a scratched one, which is the doctrine's
surge-saturation point. `Health.bloodied` is already a field and
`my_hp_fraction`/`targets_bloodied` are already computed in `features`.

## Step 3 — `winrate.py --policy`

`scripts/winrate.py` hardcodes `LinearPolicy()` in `one()`. Add
`--policy linear|doctrine`, defaulting to `linear`, threaded through `run` and
`one` the way `--draw` already is.

Its docstring already carries the rules this comparison has to obey and they are
not restated here: correct for multiple comparisons, ~80 seeds a cell to see 25%
against 8%, and **prefer hit rate and OA counts over win rate** because they rest
on thousands of events rather than one outcome per fight. Under Holm, none of the
level-5 draw comparisons rejected at 40 seeds — so the policy A/B needs the
seed budget stated up front, not after the fact.

## Files

| path | what |
|---|---|
| `src/combat_engine/engine/expect.py` | emit `Hit`/`Miss`, set `advantage`, capture foreign-cast rider damage |
| `src/combat_engine/engine/threat.py` | **new** — cached best-case 3-round damage, `CONDITION_THREAT` |
| `src/combat_engine/engine/doctrine.py` | **new** — `DoctrinePolicy`: removal, position, healing |
| `src/combat_engine/engine/__init__.py` | export the new policy |
| `scripts/winrate.py` | `--policy linear\|doctrine` |
| `docs/AI_DOCTRINE.md` | record what is implemented and what is still absent |

`src/combat_engine/engine/policy.py` is **not** retuned. `LinearPolicy` and its
37 weights stay exactly as they are, which is what keeps the A/B meaningful and
the fixtures still.

## Verification

* **Step 0 is verified by the three measured lines** in `expect.py`'s docstring —
  rogue with advantage, rogue without, fighter. Stated above; both figures go in
  the commit whichever way they move.
* **`uv run scripts/winrate.py --policy linear` against `--policy doctrine`**, same
  seeds, level 5, reporting hit rate and OAs provoked alongside win rate.
  Median rounds against the 7–8 target, and a sharp fall is a **finding** rather
  than a success.
* **`uv run scripts/audit.py --changed`**, and the wide run because `engine/` is in
  `WIDE`. The bar is the current baseline: **9,682 fire / 0 raise / 225 silent**.
  Step 0 makes real damage land during audits, so a movement in `silent` is the
  number to watch.
* **`replay verify`.** `LinearPolicy` stays the default precisely so fixtures do
  not move. If any do, step 0 changed live behaviour and that is a bug in step 0,
  not a fixture to re-record.
* **`uv run scripts/check.py`**, `leaks.py`, `ruff check .`.

## Risks worth stating before starting

* **Step 0 changes live combat, not just the model.** Emitting `Hit` from a
  `Ledger` is only safe because the Ledger is never run on a played board — which
  is true today and is exactly what step 1's scratch-board design preserves. Any
  future caller that hands `expected` a live world becomes a damage bug. Worth a
  loud docstring and an assertion.
* **Threat is a floor.** Ongoing damage is absent, `c.trigger` rows evaluate to
  zero, and most of a character's known refs score nothing. Do not read it as
  "how dangerous this creature is" in an absolute sense.
* **Damage-derived threat does not track role** — measured: it puts the fighter
  2nd of 8 and the rogue 7th. `notes/DOCTRINE.md` §5 is explicit that controller
  value cannot be derived from damage. This pass builds the damage axis because
  that is what was asked for; it is not the whole of threat.
* **Hostile terrain is approximated** by enemy zone ownership, because a zone does
  not know whether it hurts.
* **The doctrine wants two threat axes and this delivers one.** Reduction, not
  redirection. A defender scored on reduction alone plays like a striker, and
  §1 of the notes calls that out as the most load-bearing point in them.

## Not in this plan

* **Target redirection** — the defender's half of §1. Needs the protected ally's
  position, which no power header carries (#247).
* **Retuning `LinearPolicy`'s 37 weights.** Held fixed deliberately.
* **Making `DoctrinePolicy` the default.** It ships selectable and earns the
  default on measurement, not on being new.
* **Fixing `render._threat`** to mean what its docstring says. Filed, not fixed
  here — it is a wire-layer reader and this pass has no need of it.
* **Condition threat values.** The table ships as zeros by instruction.
* **#253, #256, #260, #244** — all would improve the inputs; none blocks this.
