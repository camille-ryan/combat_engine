# The last thirteen powers

Written after taking the census 19 -> 13 in one run. Every row that could be
finished **without new infrastructure** now is. These thirteen cannot, and
this file records what each needs and what was measured, so the next session
starts from evidence rather than from a symbol name.

## Why this file exists rather than more rows

The dominant finding of the run was that **a marker's measurement is usually
right and its conclusion outlives it.** Five rows were finished by reading
the *verb* rather than the row:

| row | the marker said | what was true |
|---|---|---|
| `p4803` | `c.place_scenery()` — "nothing puts an unowned, self-moving token on the board" | a zone **is** owned, and `c.move_zone` had existed for ages |
| `p12340` | `c.no_reactions()` — "`can_react` reads conditions and nothing else" | `c.no_immediate` had landed, and its docstring **names `p12340`** as the case its `attacks=True` was built for |
| `m1171a1`, `m1178a1` | `Power.action_alt` missing | the field existed and `p14124` was using it |
| `p11546` | `c.heal_check()` | the row's own note proved no *body* could reach the clause — the gap was an action **offer** |

So before planning any subsystem below, re-run that check. It is cheap and it
was right five times:

```
uv run scripts/triage.py --symbol '<sym>'
uv run scripts/vocab.py --find <word> <word>        # separate words, ANDed
python -c "import sys;sys.path.insert(0,'scripts');import blocked as b;\
h=b._surface();print(b._one('<Owner>.<field>', h))"
```

**And do not trust a green `todo.py` alone.** It has two blind spots, one of
them now fixed:

* it fires only on the **named** symbol, so a need met under another name is
  invisible (`p12340`);
* `blocked._surface` indexed `dsl.Power` and **not** bare `Power`, so every
  `Power.<field>` marker answered False whether or not the field existed.
  Fixed in `a946920f`; the fix found **two** rows where I knew of one. #1231.

## The thirteen, by what they actually need

### Out of scope by existing ruling — 4 rows

| row | symbol | why |
|---|---|---|
| `p16059` | `policy.must_take_openings()` | AI policy. *"we are not working on AI policy AT ALL here"* |
| `p16539` | `c.must_take_opportunities()` | same clause, and the two rows **disagree about where it lives** — see #1385 |
| `p11470` | `c.zone(difficult_in_flight=)` | the flier rule, #1364 — 447 of 3,142 monsters |
| `p16597` | `etl.trap_rider` | ETL, #1367 — 303 of 631 trap rows carry dropped riders |

`p16539` is worth a ruling rather than a build: its docstring argues the
compulsion is a **rules** change (the window stops being declinable) where
`p16059`'s argues it is a `policy/` decision. `p16539` has the better
argument. One gap, two symbols, and the queue reads as two.

### Blocked on a missing subsystem — 5 rows

Each of these was measured this run. **Two were started and abandoned**,
because both would have shipped a field with no reader — which makes the row
*report* finished while changing nothing, and is worse than the marker.

**`p15894` — a time model.** `story.rest(hours=)`. `Party.rest(extended=)`
does all the mechanical work and the length lives only in its docstring
("five minutes, or six hours"). Nothing records or consumes hours:
`Party` has **one field, `sheets`**; there is no clock anywhere in `story/`.
*"You require only 4 hours to gain the benefits of an extended rest"* means
nothing until a day is a budget rests draw on. #1383.

**`p14141` — persisted effects, re-armed at encounter start.** The `Sheet`
field is three lines in the established style (`withheld`, `per_day`,
`afflictions`, `vestiges_used` are each one fixed field per mechanism) plus
the two mirrors in `_wear`/`harvest` and a `clear()` in the `extended` fork.
**That is the easy half.** `c.replace_roll` is an *event-time* verb — it
rewrites `result.natural` through `resolve.settle` and does nothing unless
called from a handler armed on `AttackRolled`/`SavingThrow`/`SkillCheck`. So
the faces persisting does not make them usable next fight; something must
**re-arm those watches**, and nothing does that for a power (`arm_traits`
arms declared *traits*).

The shortcut loses a printed property: the engine could read the faces at the
three roll sites the way `durations.save` reads `Powers.saves_twice`, but the
card **offers** them (`c.may(..., who=mate)`, because the DM-discretion
sentence is about declining trivial rolls). At engine roll time there is no
`Cast` and nobody to ask. #1378.

**`p13611` — a zone-visibility reader.** `c.zone(unnoticed=)`. Nothing in
`query.py` or `api/` asks whether a creature can *see* a zone; a zone is
visible to everyone or to no one. The field would have no reader, and the
mechanical consequence of "unnoticed" is partly *what the AI avoids*, which
touches the excluded policy area. #1382.

**`p16557` — a vehicle model.** `c.vehicle_speed()`. `triage`: *"nothing in
the vocabulary comes close"*. `c.in_vehicle()` is a **predicate** four other
rows carry and is deliberately not this: the clause needs a vehicle with a
speed a row can change, plus an 8-hour clock. Pointing the row at the
predicate would report it ready with the clause still unwritable. #1380.

**`p16005` — a standing refusal to attack.** `c.surrender()`. The compendium
settles the rule and prints **no DC** (`skill_use.dc` is `NULL`): forced to
surrender or cowed; explicitly not mind control, so it will not take an
action that harms it immediately; and on a failure the creature cannot be
tried again that encounter. None of that is a condition the engine holds —
it is a standing refusal, which is as much `policy` as engine. **The check
half is already sayable and deliberately unwritten**: a body could roll
`c.check("skill:intimidate", dc, against=foe)` today and have nothing to do
with the answer, and a row that rolls for no consequence is worse than a
dropped clause, because the roll shows in the log as the clause working.
#1379.

### Blocked on a substantial engine design — 4 rows

**`p16112` — re-publishing a combat-advantage grant.** `c.spread_advantage()`.
The card *copies* a grant rather than narrowing one. `c.grants_advantage`
writes `grants_ca_to` and `_has_combat_advantage` reads the same bucket, so a
gate asking "does this enemy already grant to a member" reads the copy it is
deciding whether to lay; and `query._IN_FLIGHT` answers False for a pair
already being asked, so the result depends on **which member asked first**.
There is no way to ask the question *excluding one effect*. #1377.

A partial route exists and was rejected for now: the **pair-specific** half
is mostly flanking, and `query.flanked_by` consults none of that bucket — so
the flanking case is writable today while the modifier-sourced case is not.
That would be a narrower `dropped=` rather than a finished row, which is
honest but does not move the census; worth doing only alongside a decision
about the exclusion capability.

**`p16497` — branch-aware triggered dispatch, plus `Power.body_alt`.**
A second printed *mode* of one card: no action, at the start of your turn,
only while dominated, expending the row to roll one save instead of laying
the bonuses. Three of the four header halves already exist —
`action_alt` (built this run), `requires_alt`, and the usage — so what is
missing is `body_alt` **and** a dispatcher that can fire a particular
*branch*: `_ask` builds `options = [ref, *variants, ""]` with no branch, and
`_answers` keys the window on `p.action` rather than `action_of(branch)`.

The `pNb` route was built and reverted and should not be retried: `cls=""`
means no draw deals it, `Powers.all` is `known` plus basics with no
derivation, and `triggers._answers` offers only what is in that list — so it
cannot fire, and a `drivers` rule calling the body directly cannot see that.
Deriving `pNb` inside `Powers.all` catches **216** rows, 212 of which their
parents already hand over conditionally. #1376.

**`p12236` — a header line that runs before targeting.**
`Power.effect_before`. A burst picks its targets before the body runs, so
*"before the attack, you move your speed"* cannot be a body clause: `dsl.use`
builds the `Cast` **after** `_auto_targets` settles the list, and for an
offered action the targets are settled earlier still — `actions.options`
prices every offer with resolved targets.

The shape is `Power.check`'s, but it must sit **earlier** than that field,
which `use` rolls after the target list is chosen. The open question is
target **re-resolution**: an offer whose targets were pre-resolved must
re-pick them after the move, or the move happens and the burst catches
whoever was adjacent before it. Note `Attack.bonus_for` already builds a
throwaway `probe = Cast(...)` before the real one, so a pre-targeting `Cast`
is established practice. I could not get the row offered on the audit board
to measure this. #1381.

**`p12162` — a creature or a square out of a use at announce time.**
`c.drop_target(at_use=)`, `(square=)`. Two clauses, one absence. *"Or your
square"* is **squares** rather than creatures; and an area power whose
**Effect** line reaches the character without rolling an attack is never
answered at all.

Measured, so it is not retried: `c.drop_target(c.me)` off a `PowerUsed`
interrupt reads right and returns **False** every time — `dsl.use` calls
`cast.used()` (which announces `PowerUsed`) *above* `_RUNNING.append(cast)`,
so at the one moment the row is offered the use is not on the stack
`dsl.running_below` reads. That ordering is deliberate and heavily
documented: the card spends the action and the use whether anything lands,
and there are early returns between the two. Moving the push earlier means
widening the `try/finally` that pops it. Note `c.add_target`'s docstring
claims an interrupt *"runs while the power it answers is still walking its
target list"* — true only for an interrupt on something the **body** emits.
#1374.

## Suggested order, cheapest first

1. **`p16539`'s symbol** — a ruling, not a build. #1385.
2. **`p12236`** — one field, one call site, and one real question
   (re-resolution). The smallest of the engine designs.
3. **`p14141`** — the `Sheet` field is trivial; scope the work as "re-arm
   persisted effects at encounter start", which is general and would serve
   more than this row.
4. **`p16497`** — `body_alt` is easy; branch-aware triggered dispatch is the
   piece, and it would also make `action_alt` reachable from a trigger.
5. **`p15894`** — a time model is a `story/` subsystem with its own value
   beyond this row.
6. Then `p12162`, `p16112`, `p13611`, `p16557`, `p16005`.

## Rules this run re-learnt the hard way

* **A `--tries`-derived seed range changes coverage, not just sample size.**
  `miss_rides` used `max(6, SAMPLE // 10)`, passed at `--tries 40` and failed
  the wide sweep at 250 — 6 seeds reached none of the quiet boards and 25
  reached one. Quote both figures in any rule that scales its seeds.
* **A board that cannot pose the clause is a skip, not a failure.** Seed 9 of
  25 lands `p9433`'s hold and then produces no swing at all.
* **`Cast._who` defaults to `c.target`.** A new verb whose clause is about
  *you* must default to `self.me` — `c.miss_lands_on` did not, and in `p9433`
  `c.target` **is** the creature named by `on=`, so the guard refused the hold
  and the row laid nothing while every other clause worked.
* **A control that cannot distinguish the two implementations is not a
  control.** Four plants passed in this run on fixtures that posed only one
  case: a melee-only swing set, an always-adjacent helper, a never-released
  hold, a single saving throw where the row rolls one.
