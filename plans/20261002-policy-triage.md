# Policy triage: one policy, a tactical scorecard, then the fixes

*(On implementation, copy to `plans/20261002-policy-triage.md` per the repo
convention.)*

## Context

Ten issues are open against `policy`. Three are already fixed and two are
substantially done — verified in code, not assumed — so the first value here is
closing them with their measurements rather than writing anything.

The rest is reshaped by Camille's point: **win-rate comparison is weak evidence when
both sides run the same policy.** A symmetric improvement largely cancels, which is
exactly what the last two runs showed — `DoctrinePolicy` ahead at both levels on both
seed sets, neither surviving Holm, while the thing the fixes targeted moved hard
(opportunity attacks conceded, 304 → 174 at level 5). Forty-five minutes a run to
measure the weakest signal available is the wrong trade.

Two decisions Camille settled:

* **A per-side tactical scorecard becomes the gate**, win rate demoted to a balance
  guard against #217's 7-8 rounds.
* **`LinearPolicy` is retired.** One policy. I flagged that this discards the only
  baseline to compare against; that is Camille's call and the scorecard is designed
  around it — comparison becomes *against committed baseline numbers* from the
  previous commit, which suits "fix, watch, iterate" better than a frozen rival does.

Working order throughout, per Camille: **apply fixes, watch a few combats, iterate,
and only then run anything long.**

## Triage, verified in code

| | state | disposition |
|---|---|---|
| **#258** `provokes_now` never applies to movement | **fixed**, `policy.py:249` | close with the 57 → 21 measurement |
| **#259** `hit_chance` for rows that cannot hit | **fixed**, `policy.py:179` | close; `hit_chance` returns `None` and the caller gates |
| **#263** `CONDITION_THREAT` is zeros | **done differently** — table deleted, `from_rules`/`ROUNDS_OF`/`denial` derive it from `conditions.Rules` | close with the rounds table; note duration *is* now read, which the issue asked for |
| **#260** a heal scored as friendly fire | **fixed and generalised** to buffs via `benefits()` | close once there is one policy — the "still live in LinearPolicy" caveat disappears with it |
| **#265** `closes_distance` uncapped, excludes charge | open, **worst remaining** | fix 1 |
| **#264** no precondition check, inert rows score +6.0 | open, largest single provocation source | fix 2 |
| **#231** self-targeted row paid `enemies_caught` | open, **confirmed still live** | fix 3, one line |
| **#266** ally-burst; action points scored by a constant | open | fix 4 |
| **#247** forced movement's sign depends on who it protects | **partly done** — `denial(pushed=)` prices "cannot reach" | narrow to the remaining half: a push in the *wrong* direction |
| **#213** win rate unreadable with random draws | open, `chargen` | comment: Camille's "comparisons are of limited value" is the stronger form of this; the scorecard supersedes what it asks for |

## Step 1 — the scorecard, because it is the gate for everything after

Extend **`scripts/doctrine.py`**, which already wraps the policy and counts per-term
firing, to emit a per-side quality report. Not a new script: it has the hooks.

Counted **separately for party and monsters**, so a symmetric gain shows up instead
of cancelling:

| what | why it is the gate |
|---|---|
| opportunity attacks conceded per fight | the measure that replicated across both runs |
| inert actions chosen | an action that could not accomplish anything — #264 |
| self-harm instances | caught in your own blast |
| decisions tied at the top, and tie size | 14.8% today, settled by `str(action)` |
| charge take-rate **by role** | #265's acceptance test: melee up, wizard stays 0 |
| `already_on` firings | turns spent re-casting a live buff |
| median rounds | the balance guard, against 7-8 |

**The baseline is committed**, as `scripts/fixtures/scorecard.json` or similar, so
"did this fix help" is answered against the previous commit's numbers rather than
against a second policy. That is what replaces the A/B, and it is also what makes the
loss of `LinearPolicy` survivable.

Seeds: a fixed set at level 10 (where the review was done) and level 5. Twelve fights
is enough for these counts — they rest on hundreds of events each — and runs in under
a minute, which is the point.

## Step 2 — retire `LinearPolicy`

One concrete policy. The surface is small: 34 references, 20 of them docstring prose
in `doctrine.py` comparing the two.

* Fold `LinearPolicy`'s body into the single policy. `features` and `WEIGHTS` stay in
  `policy.py` — they are the feature layer, not the rival.
* Drop `--policy` from `scripts/winrate.py` and `scripts/watch.py`, and `POLICIES`
  with it. `install`'s fallback becomes the one policy directly, which also removes
  the function-local import added to dodge the cycle.
* **Then fix shared defects in `features` in place**, once, instead of as overrides.
  #231 is the immediate beneficiary and `DoctrinePolicy.score`'s three existing
  overrides (`allies_caught`, and the two provocation terms it leaves alone) can
  collapse into honest code.
* Rewrite the docstring prose that compares the two, and the `engine/CLAUDE.md` line
  describing `policy.py` as "`Policy` protocol plus `LinearPolicy`".

**This merges 37 + 15 weights into one table of ~52**, which is the thing I argued
against when the second policy was created — "forty-five interacting hand-set numbers
cannot be moved one at a time, so a regression cannot be attributed". The scorecard is
the answer: attribution now comes from per-term firing counts and per-side tactical
outcomes, which is finer-grained than an A/B ever was. Worth stating in the module
docstring so the reversal is not silent.

## Step 3 — the fixes, in this order, watching between each

**Fix 1, #265 — `closes_distance`.** The worst one: uncapped at weight 2.0, so a
seven-square run collects +14, more than any attack term; and computed only for
`("move", "run")`, so a charge that moves *and* attacks earns nothing for the moving.
Behind both the 14.8% tie rate and a melee-only skirmisher charging on 6% of offers
while the brute takes 36%.

Recommended shape: **stop using it and let `reach_gained` do the job it was written
for** — it already measures "does this square let me attack, and how much", which is
the thing that actually matters, rather than squares travelled. Add `charge` and
`shift` to the kinds that get a closing figure. Then break remaining ties on
proximity to the highest-`threat` enemy, which is already computable.

Acceptance: ties well under 14.8%, `m2914`'s charge rate up toward the brute's, the
wizard's still 0.

**Fix 2, #264 — inert rows.** The largest single provocation source: one row at 84
occurrences at level 10, a minor-action utility that does nothing unless the target is
undead. `threat.row_effects` already runs a row on the scratch board and reports what
it lays, so "this row would accomplish nothing against this target" is answerable with
what exists. A row laying no effect, dealing no damage and declaring no attack is
inert and should score below ending the turn.

**Fix 3, #231 — one line.** `enemies_caught = len(targets) - friendly` with `friendly`
skipping the actor, so a `target=SELF` row is paid for catching an enemy that is
itself. Subtract the actor.

**Fix 4, #266 — action points and the ally burst.** Score an action-point grant by the
best action it unlocks rather than a flat 4.0; `worth_standing` has cut the option
count 83%, so the extra pass is affordable now. For the burst, score the best origin
*after a move* rather than only from where the creature stands — `_in_area` already
answers it for a hypothetical square.

**#247's remainder** is last and may not be worth doing: pricing a push in the wrong
direction needs the protected-ally notion that issue asks for, and `landing()`
currently assumes the pusher picks a sensible direction.

## Files

| path | what |
|---|---|
| `scripts/doctrine.py` | the per-side scorecard, and the committed baseline |
| `src/combat_engine/engine/policy.py` | `LinearPolicy` folded away; shared `features` defects fixed in place |
| `src/combat_engine/engine/doctrine.py` | the one policy; `closes_distance` and inert-row handling |
| `scripts/winrate.py`, `scripts/watch.py` | `--policy` removed |
| `src/combat_engine/engine/__init__.py`, `engine/CLAUDE.md` | the export and the component description |

## Verification

In the order the work happens, not at the end:

* **The scorecard, before and after each fix**, against the committed baseline. This
  is the gate. A fix that does not move its own target metric has not worked.
* **`uv run scripts/watch.py --seed N --level 10`** after each fix — read two or three
  fights and check the decisions changed the way they were meant to. This is how all
  five of the last round's defects were found and it is cheaper than any run.
* **`uv run scripts/doctrine.py`** — every weight still fires. A term that stops
  firing after a refactor is the "weight nothing consults" failure returning.
* **`replay verify`**, re-recorded in its own commit each time behaviour moves.
* **`check.py`, `leaks.py`, `ruff`**, and the wide audit once at the end — `engine/`
  is in `WIDE`. Baseline 9682 fire / 0 raise / 225 silent.
* **`winrate.py` once, at the very end**, and read only median rounds against #217's
  7-8. Not as evidence the policy improved — Camille's point is that it cannot be.

## Risks worth stating before starting

* **Retiring `LinearPolicy` discards the only comparison.** Camille's call, made with
  the cost stated. The mitigation is that the scorecard baseline is committed, so
  regressions are still catchable — but a *gradual* drift across many commits is
  easier to miss without a fixed rival, so the baseline file has to be kept honest.
* **One weight table of ~52.** See step 2. The scorecard is the answer and it is a
  weaker answer than an A/B for interactions between terms.
* **Fix 1 removes a term the current behaviour was built on.** `closes_distance` has
  been load-bearing since before any of this work; zeroing it could regress approach
  behaviour badly, and the scorecard must include something that would catch that —
  "turns where a melee creature neither attacked nor closed" is the candidate.
* **#264's inert test runs a row to find out.** Cached per `(caster, ref)`, but it is
  another Ledger pass and the first one on the hot path for *every* candidate row
  rather than only the ones already being measured.
