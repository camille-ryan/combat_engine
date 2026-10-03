# Replace every static scoring weight with a measured one, in hit points

*(On implementation, copy to `plans/20261003-hp-scoring.md` per the repo convention.)*

## Context

The AI scorer is 58 weights over 50 features. **Seven are measured; 51 are hand-set
constants** — and measured here, over 1,637 decisions in twelve fights, the constants
are **90.2% of all weighted magnitude**:

```
term                           kind  share of all  mean when it fires   fired
is_power                     static        22.7%                6.00     556
enemies_caught               static        12.2%                2.53     707
expected_hits                static        11.0%                2.98     545
targets_bloodied             static         6.8%                3.11     323
is_end                       static         6.5%                2.00     474
hit_chance                   static         6.3%                1.71     545
threat_removed              derived         5.7%                1.62     513
shoved_from_prey             static         4.8%                8.07      87
closes_distance              static         4.6%                8.43      80
```

Camille's question is the one that opens this: *why are these still here when we
already calculate threat reduction from expected damage?* Three answers, all measured:

1. **They double-count.** `threat_removed` is `threat(t) × min(expected_vs, effHP) /
   capacity`, and `expected_vs` **already** scales by the live hit chance
   (`threat.py:627`). `hit_chance` + `expected_hits` re-apply that same quantity at
   **17.4%** against `threat_removed`'s **5.7%** — the constants outweigh the principled
   term that contains them, **3.1 to 1**. A `Memory` term multiplies by it a third time.
2. **They are load-bearing anyway.** `is_power` at 6.0 is the only thing stopping the AI
   passing its turn: `is_end` is −2.0 and `threat_removed` averages **1.62**. Remove one
   constant at a time and the AI gets worse — already recorded, with a measured term
   worth **0.58** where the decision needed **7**.
3. **Over half of all decisions are decided by constants alone.** With the 7 derived
   terms as the only live weights, **52.3% of decisions have no option scoring above
   zero**, and `shift`, `second_wind` and `coup_de_grace` drop to **zero uses**. They
   have no measured valuation at all.

So this cannot be a cleanup. It is one atomic re-expression of the whole table into one
unit, which is Camille's instruction and what the 52.3% makes unavoidable.

**Target behaviour.** Every score is **expected hit points of advantage, net**. `end` is
**0.001** — the floor. Anything that achieves nothing lands at or below zero and is
therefore never taken before passing.

**Not in scope, deliberately:** one-step lookahead. Positional actions get a proxy
(`best_from` ± opportunity-attack damage); #293 and #312 stay open. The consequence is
stated below and is not hidden.

## The unit, and the four denominators it replaces

The 7 "derived" terms are **not one currency** — they have four different denominators:
`T.capacity` (`threat_removed`), the **enemy's** `T.pool` (`party_enabled`,
`reach_gained`), **my own current hp** (`threat_conceded`, `ca_conceded`, `self_harm`),
and **my side's** `T.pool` (`healing_given`). All four go. Every term returns hit points.

`SHARE = 15.0` is deleted. It is an exchange rate between a health-fraction and a score,
it is explicitly fitted on level-5 numbers that have since moved by about 7× across
levels (`doctrine.py:289-292`), and in hit points nothing needs converting.

### Four primitives, all built from what exists

```python
# hp a blow buys: the fraction of t's remaining life taken, times what t would still do
hp_removed(ref, t) = (min(T.expected_vs(w, me, ref, t), T.effective_hp(w, t))
                      / T.effective_hp(w, t)) * T.potential(w, t) * T.ROUNDS

hp_denied(t, laid) = T.denial(w, t, laid) * T.potential(w, t)   # rounds -> hp
hp_enabled(t, laid) = T.enabled(w, t, laid)                     # already hp
hp_taken(foes)     = sum(T.expected_vs(w, foe, basic_of(foe), me) for foe in foes)
```

`hp_removed + hp_denied` is capped at `T.potential(t) * T.ROUNDS` — you cannot take more
from a creature than it had left to give.

**This one change fixes #325 on its own.** A creature's worth as a target stops being its
hit points and becomes **the damage it will still deal**. A minion has `effective_hp == 1`,
so any hit takes 100% of its remaining life and buys its whole `potential × ROUNDS`.
Measured today, a minion pack holds **1.0–1.7%** of modelled enemy capacity and deals
**32–68%** of the damage the party takes; under this formula those converge.

## Prerequisite: the denial model is blind to the commonest conditions

**`DAZED` scores 0.0 rounds of denial.** `threat.Pinned` reads 7 of `conditions.Rules`'
17 fields. `DAZED` is `grants_ca + one_action + no_reactions` — none of them in `Pinned` —
so `from_rules` returns a bare `Pinned()` and `_denial`'s guard (`threat.py:932`) skips it
entirely. Same for `DOMINATED`. `MARKED` is literally `Rules()` (#263).

So `hp_denied` is worthless until `Pinned` grows `one_action` (≈ lose two thirds of a
turn), `no_reactions`, `helpless`, `blind`, `grants_ca` and `defences`. **Do this first
and verify it against `scripts/doctrine.py --rounds-table`**, whose docstring holds
Camille's reference figures (kill 3 rounds, save-ends 1.8, stun 1, weakened 0.5, prone
~0.1). A dazed enemy should land near 0.67 rounds, not 0.

## The one term that is a modelling choice, not a measurement

Everything else reduces to hit points. **A limited row's cost does not.** Spending a
daily now costs what it would have been worth later, which no board state contains.

Proposal, and it should be called out as a choice: price the reservation against how
dangerous the fight still is.

```python
danger = T.capacity(w, other_team) / starting_capacity        # 1.0 -> 0.0 over the fight
cost   = value * (1.0 - danger) * RESERVE                      # RESERVE ~ 0.5
```

Early in a hard fight a daily is nearly free; against a nearly-dead enemy it is
expensive. That is #305's answer ("only use limited resources when threat is above some
threshold") expressed as a gradient rather than a threshold, and it replaces
`usage_daily` −3.0, `usage_encounter` −0.5 and the untabled `+6.0` desperation bonus.
`RESERVE` is the one surviving constant; say so plainly rather than hiding it.

## Per-kind valuations — all 21 kinds, because six collapse to zero without them

`features()`' own comments record **six separate incidents** where an unnamed action kind
scored zero, beat `end` at −2.0 and became the idle default. With `end` at +0.001 the
failure mode inverts: an unvalued kind scores 0, loses to `end`, and **disappears from
play**. Both are fatal, so every kind needs a number.

| kind | hit-point value | reuses |
|---|---|---|
| `power` | Σ enemies `hp_removed + hp_denied + hp_enabled` − Σ allies `expected_vs(me,ref,ally)` − `expected_vs(me,ref,me)` − `hp_taken(provoked)` + hp healed + hp of buff | all four primitives |
| `charge` | as `power`, plus `best_from` delta for the approach, minus OAs on the path | `_can_charge_from` |
| `coup_de_grace` | `hp_removed` of the kill; keeps the `Undying` clause from #318 | `_finishes` |
| `command` | as `power` **but damage rolled from `action.subject`** — `doctrine.py:1117` uses the owner's `expected_vs`, not the beast's. `features` fixed this for hit chance (`:201-212`); doctrine never did | existing bug, fix here |
| `move` / `shift` | `best_from_hp(dest) − best_from_hp(here)` − `hp_taken(OAs the path provokes)` | `best_from`, `_WALKS` |
| `run` | as `move`, minus the hp the conceded combat advantage hands over | `conceded` |
| `stand` | `(T.potential(me) − T.per_round(me, from_rules([PRONE]))) × rounds it applies` | `Pinned`, `_shortened` |
| `escape` | same shape for the grab, × the escape check's success probability | `Pinned` |
| `total_defence` | Σ foes `expected_vs(foe, basic, me) − expected_vs(foe, basic, me, attack=-2)` | `expected_vs(attack=)` |
| `second_wind` | `Health.surge_value` + the same defence-bonus delta as `total_defence` | `query.surge_value` |
| `hide` | hp of extra damage from the advantage gained, plus hp avoided by being untargetable | `T.enabled` |
| `action_point` | `T.per_round(me)` restricted to the granted cost | `per_round` |
| `sustain` | the zone's hp per round × rounds it will still run | `running`, `hurts` |
| `instinctive` | `T.potential(companion)` | `potential` |
| `wield` / `pick_up` | `best_from_hp(here, with the weapon) − best_from_hp(here)` | `_reaches_further` |
| `item` | `expected_vs` of the item's row | `expected_vs` |
| `drop` | hp the running effect is costing us | `running` |
| `delay` | **0.0** | — |
| `end` | **0.001** | — |

**`delay` scores 0 and will therefore never be chosen.** That is honest — delay's value
is entirely in what it enables, which is #312, and the current −6.0 is a guess that
`policy/__init__.py:616-619` already admits ("sometimes right and the scorer cannot tell
when"). Replacing a wrong number with a true zero is an improvement; say so in the commit
and leave #312 open.

### Three bugs to fix in the same pass, because the rewrite touches their lines

* **`hide` collects the attack target loop.** `legal` puts every enemy it could hide from
  into `targets` (`actions.py:230`), so hiding from three bloodied enemies scores about
  **+15** from `enemies_caught` and `targets_bloodied` before `is_hide`'s +2.0. The flank
  terms guard against this by naming `hide` (`doctrine.py:1215-1219`); the target loop
  does not.
* **`delay` collects `allies_caught` −7.0 or `enemies_caught` +2.0** depending on whose
  slot you pass (`actions.py:198`).
* **`sustain` and `drop` are penalised by construction.** `legal` draws them from effects
  this creature owns, so `running()` is always true, so `already_on` −4.0 **and**
  `inert_costs_turn` −6.0 both land on the two kinds whose entire point is an effect that
  is already running.

Also delete outright, as unable to discriminate: `nearest_enemy` (−0.1 on a quantity
identical for every option in a decision), `targets` (weight 0.0), and
`becomes_flanked`, computed for **every** action including `end` and `total_defence`
because `dest` falls back to the current square — the sibling leak in `takes_flank` was
found and fixed, this one was left.

## Files

| path | change |
|---|---|
| `src/combat_engine/policy/threat.py` | extend `Pinned` + `from_rules` to the 6 missing `Rules` fields; point `row_effects` at the caster and allies as well as the foe, so a buff can be priced at all; add `hp_removed`/`hp_denied` helpers beside `denial` |
| `src/combat_engine/policy/__init__.py` | gut `WEIGHTS` to the handful that survive; delete the 21 `is_*` flags and the dead features; `features()` keeps only what the new terms read |
| `src/combat_engine/policy/doctrine.py` | the bulk. `DOCTRINE` becomes the whole table; `doctrine_features` grows a per-kind valuation; delete `SHARE`, `inert_costs_turn`, the four override clauses, and the three untabled bonuses in `weigh` |
| `scripts/terms.py` | **new.** The per-term report above, promoted out of scratch. It is what would have caught #321 |
| `scripts/scorecard.py` | redefine `DERIVED` as a **declared set**, not `abs(w) == SHARE` — that float comparison already misclassifies `shoved_from_prey`, and with `SHARE` gone it breaks |
| `src/combat_engine/policy/CLAUDE.md`, `docs/AI_DOCTRINE.md` | both describe the old table by term name. `AI_DOCTRINE.md` is separately stale: it points at `engine/policy.py`, claims two policies exist, and tells you to run a deleted `--policy linear` |

**Two constraints the instruments encode, easy to break silently:** `scorecard.py:286,288`
read `self_harm` and `already_on` through `explain`, which filters to `DOCTRINE` — those
names must stay **in** `DOCTRINE` or the counters read zero with no error. `:308` reads
`allies_caught` through `weighed` **because** it is not in `DOCTRINE`. And `weighed` ends
with `f.update(doctrine_features(...))`, which overwrites the override clauses above it —
that works by luck today and must not be relied on.

**Do not convert `DoctrinePolicy`'s `__init__` work to `__post_init__`:** `scripts/doctrine.py`'s
`Watched` is deliberately not a dataclass and would silently lose every counter.

## Verification

**The acceptance test is the 52.3%.** Re-run the derived-only probe: *decisions where no
option scores above zero* must fall from **52.3% to near zero**. If it does not, some kind
still has no valuation and has silently dropped out of play.

Then, in order:

1. `uv run scripts/doctrine.py --rounds-table` — the condition model against Camille's
   figures. A dazed enemy near 0.67 rounds, not 0.
2. `uv run scripts/doctrine.py` — **"N of M terms never fired" must be 0**. This is the
   designated dead-weight detector and nothing runs it automatically; it is not in
   `check.py`.
3. `uv run scripts/terms.py` — static share must fall from **90.2%**, and no single term
   should hold `is_power`'s current **22.7%**.
4. `uv run scripts/scorecard.py` — the attrition numbers. Surges, dailies, action points,
   "dropped to 0 hp" and "with their second wind still unspent". **Report the mixed result
   as mixed**; round counts have a target band (#217) that disagrees with the scorecard's
   lower-is-better default, so the two instruments can call this good and bad at once.
   Time both arms back to back on an idle machine or make no claim about cost.
5. `uv run scripts/check.py --fast` — `replay verify` is the only hard gate and **all
   seven fixtures will diverge**. Re-record in its own commit, and say which divergences
   are repricings and which are tie-breaks.
6. **Four subagents, three fights per paradigm**, per `policy/CLAUDE.md` and Camille's
   standing instruction. Measure only what two raise independently.

**Named guards, each a probe:**

* the party wizard charges **zero** times (#293);
* with 4 party members and 1 enemy left, a single-target row still beats a blast (#266);
* provocations do not regress — switching the flat `provokes_now`/`provokes_avoidably` off
  once took provoking from −9.0 to −0.8 and provocations from **53 to 140**, so the
  measured `hp_taken` replacement has to be shown carrying that load;
* `web/app.js:986-993` pins a movement row at score **0** and sorts the human's options
  by score, so **a power that scores negative sorts below "walk"** on the page. Check the
  browser list, not just the numbers.

**Cost ceiling, from the existing profile:** anything per `(board, creature, ref)` is free
after the first call via `_ROWS`/`_EFFECTS`/`_BOARDS`; per `(board, round, creature,
square)` is affordable at ~30k calls a fight via `_BEST`/`_COVER`. **A new scratch-board
run per candidate action is not affordable** — `board()` is the expensive part and
uncached `per_round` already took one fight from 13s to 25s and an 80-seed comparison from
25 minutes to two hours.

## Risks

* **One unattributable step.** Accepted — Camille's call, and the 52.3% says the
  alternative does not exist. If it comes out worse, bisecting means re-doing it term by
  term anyway.
* **Both sides share one table.** `install` is called with `policies={}` everywhere, so a
  single `DoctrinePolicy` instance drives the party and the monsters. Every change helps
  or hurts both at once; this is why the scorecard counts per side.
* **`reach_gained` keeps its known flaw.** A difference of baselines cannot express "avoid
  this", only "anywhere but here" — netting friendly fire into it once made friendly fire
  *worse* (20 → 25) and was reverted. The proxy inherits that; #293 is where it is fixed.
* **hp-scaled scores are large.** A level-5 attack is ~10–15 hp and a standard monster's
  `potential × ROUNDS` is ~30–45, so scores move from today's 0–30 range into the tens.
  Nothing internal cares, but `api/render.py:411` ships `score` to the browser.
