# Finishing the content, level by level

## Context

Level 1 is done — 111 powers, 101 monster abilities, 29 stat blocks — and
the work is now tracked as 76 GitHub issues. What is left:

| | remaining | of |
|---|---|---|
| PHB1 powers | **216** | 326 |
| MM1–3 monster abilities, heroic | **2,528** | ~2,630 |

The decision is to go **level by level** — level 2's powers *and* its
monsters, then level 3, and so on — so each level ends with a fight that is
genuinely balanced at that level, and to keep going until something needs
judgement.

Before any of that, some of it is not writable. Measuring the remaining 216
powers against the vocabulary that exists:

- **193** can be written today.
- **23** need a concept the engine does not have: conjuration (12),
  sustain (12), stance (5), polymorph (1).

And two things the exploration turned up that are worse than "not yet
written":

**72 rows print a range line covering both melee and ranged** — "Strength
vs. AC (melee) or Dexterity vs. AC (ranged)" — spread across cleric (5),
ranger (20), rogue (29) and warlord (12). Eleven are already declared as
*one branch only*, silently. This is not a level-1 curiosity; it is the
shape of every future ranger, rogue and warlord level, and a third of the
remaining work.

**13 rows declare a trigger that nothing reads.** `on=Trigger(...)` exists
and works, but only 3 of 216 rows use it. Ten of the thirteen name a
sentence the existing events and predicates already express — in one case
the exact predicate is written three lines away on a sibling monster. The
gap is un-wired declarations, not missing capability.

---

## Confirmed bugs, found while sizing this

Three, all verified by running them rather than by reading:

1. **Nothing can sustain a sustained effect.** `Effects.sustain()` exists
   (`durations.py:242`) and the expiry rule works, but **no caller anywhere**
   — no action, no `Cast` method. Traced live: the wizard's `p185` zone is
   created on round 1 and ends at the start of round 3 with "not sustained",
   and there is nothing the player can do about it. This ships today.

2. **Both defender marks punish an attack that *did* include them.** A burst
   is announced once per target, so `p805`'s guard `if ev.target == me:
   return` only skips that one announcement — the damage has already landed
   off a different target's row. Same shape in `p7419` (fighter riposte) and
   a third time in `resolve._mark_penalty`, whose docstring describes the
   intended rule and whose code does not implement it.

3. **A dual-range row is declared as one branch** with no marker that the
   other exists — 11 rows so far, correct-looking and half-right.

---

## Phase 1 — make the remaining rows writable

Nothing here is speculative: every item is blocked content or a verified
bug. Ordered by how many rows it unblocks.

### 1a. Dual-range powers — 72 rows (issue #70)

The branches disagree on four independent things — range, whether it
provokes, which weapon `c.w()` rolls, and which ability attacks — read at
four unrelated points. There is no channel to carry the choice.

`origin` is the precedent: it exists only for areas and is threaded
end-to-end through `_aimings` → `Action.origin` → `use(origin=)` →
`Cast.origin` → `area_of` → the wire → `session.aim`. A branch needs the
same length of thread.

- `Range` gains a paired kind; `Melee`/`Ranged` stay as they are.
- `Attack` and `Damage` accept a second, ranged variant.
- `Action` gains the branch; `_aimings` (`actions.py:105`) emits one option
  per branch per target, which is what makes both reachable from the board.
- `Power.provokes` is a zero-argument property (`dsl.py:273`) and must
  become a question about a *use*; `Attack.bonus_for` (`dsl.py:167`) builds
  a synthetic `Cast` with no branch slot; `resolve._is_ranged`
  (`resolve.py:165`) takes only a ref. Each needs a parameter it does not
  have — this is the part that ripples and should be done carefully.
- `PowerDTO.option_label` already exists and is always `None`
  (`render.py:456`): it is where "melee" / "ranged" goes on the card.

Then rewrite the 11 already-declared half-rows.

### 1b. Actions can name a subject that is not the actor — prerequisite

`Action.kind` is `power | move | shift | stand | second_wind | end`
(`actions.py:31`), and `legal()`/`perform()` know only those. There is no
way to say *"spend a minor to sustain effect 17"*, *"spend a move to walk
the sphere 6"* or *"spend a standard to make it attack"*. Both 1c and 1d
need this and neither can be done without it, so it comes first.

`Action` gains a subject — a live effect id, or a non-creature entity id —
alongside the existing `ref`/`targets`/`origin`.

### 1c. Sustain — 12 rows, and bug 1 (new issue)

**Sustained by default.** An effect that needs a minor to sustain does not
lapse because you forgot to click it; it lapses only if you spent that
minor on something else. At the owner's turn end, if the action the effect
names is still unspent, it sustains itself and consumes it. Two effects
both wanting a minor means one of them lapses, which is correct — there is
only one minor.

That inverts the printed rule's failure mode. The book makes forgetting the
default and sustaining the exception; this makes persisting the default and
losing it the consequence of a choice you actually made. An explicit
`sustain` action still exists, for sustaining early or for choosing which
of two effects gets the minor.

`Effect` gains the action its sustain costs. `When.SUSTAIN`,
`Effect.sustained` and the expiry rule at `durations.py:274` are already
right and stay as they are; what changes is that something finally calls
`Effects.sustain()` (`durations.py:243`), which today is dead code.

The caster's card must show a sustained effect and what it costs —
`render.py:150` lists effects per actor, and a zone's effect is owned by
the *zone entity*, so the caster currently never sees it.

### 1d. Conjurations — 12 rows (issue #71)

**An entity, in the `Trap` mould** — `Position`, no `Health` — with a zone
hung off it for its footprint. Three things fall out for free:

- *Occupies its square*: `Grid.occupant` and `movement._clear` are
  eid-keyed and need no change. This is the clause `p916` cannot say today.
- *Attacks from its own position*: `resolve.attack` takes an arbitrary
  attacker eid and derives cover and reach from its squares. `query.can_act`
  already short-circuits for `Trap` (`query.py:152`), which is the one patch
  a Health-less attacker needed.
- *"Adjacent to the sphere"*: `Zones.aura` already takes an owner and
  `refresh` only asks that owner for a `Position` (`zones.py:137`) — it
  never checks that it is a creature, and self-ends when it despawns.
  `Cast.aura` hard-codes `self.me` (`cast.py:1344`); that one-argument gap
  is the whole change.

**Ship them un-attackable first.** Giving a conjuration `Health` so it can
be targeted also hands it an initiative slot, a turn, and a vote on whether
the fight is over — `creatures = having(Health, Position)` (`query.py:32`)
is simultaneously the initiative roster, the target pool, the win condition
and the render roster. Splitting that predicate is the single biggest piece
of work here and **neither `p1435` nor `p916` gives the thing hit points**,
so it defers entirely.

The cost of deferring: no `Health` means no token (`render.py:123`,
`wire.py:186`), so the conjuration is drawn as its aura footprint rather
than as a creature. Acceptable to start; a `ConjurationDTO` is the honest
fix later.

Note `Trap` is declared and **never instantiated** — it is a shape, not a
working example, so this will be the first time that route is exercised.

### 1e. Stances — 5 rows (new issue)

`When.STANCE` exists in the enum and in `_UNREACHABLE` and nothing sets it.
Needs `c.stance(...)`, plus the one rule that makes a stance a stance:
assuming one ends the one you were in.

### 1f. Wire the dead triggers — 13 rows, and bug 2 (issue #73)

Ten are wiring only. Two small predicates cover most of the rest: a
melee-vs-ranged test (`resolve._is_ranged` already does the lookup) and
"cursed by me" for the three warlock pact boons.

The two marks need attack-level rather than target-level announcement —
the events carry a scalar `target` and the full list lives only in
`Cast.targets`. Fix `_mark_penalty` at the same time, since it is the same
bug in the engine's own code.

### 1g. Polymorph — 1 row (new issue)

One warlock level-10 row. Included because you asked for all four, and it
is the one item here whose cost is plausibly larger than its value — worth
dropping if it turns out to want a subsystem.

**Order within phase 1:** 1b before 1c and 1d, since both need it. 1a is
independent and is the largest, so it can run alongside. 1f is mostly
wiring and can go any time.

**Gate:** `check.py --all` clean, and the 11 half-written dual rows rewritten
with both branches, before any content wave starts.

---

## Phase 2 — the levels, in order

Per level N: powers first (they are few and they change what the party can
do), then monsters (they are many), then a fight at that level.

| level | powers | monster abilities | monsters |
|---|---|---|---|
| 2 | 32 | 139 | 39 |
| 3 | 34 | 193 | 46 |
| 4 | — | 202 | 53 |
| 5 | 28 | 241 | 58 |
| 6 | 32 | 229 | 53 |
| 7 | 33 | 247 | 59 |
| 8 | — | 253 | 60 |
| 9 | 28 | 184 | 45 |
| 10 | 28 | 194 | 43 |
| 11–13 | — | 646 | 145 |

Levels 4 and 8 are score-increase levels with no powers.

### The loop, per level

1. `scripts/spec.py --class <c> --level N` per class; `--monsters N` for the
   monsters, split by role.
2. Fan out to agents — one per class for powers (3–6 rows each), one per
   role for monsters (30–60 abilities each). Each gets the sanitised specs,
   a **freshly generated** `scripts/vocab.py`, the target file, and
   `briefs/PRELUDE.md`.
3. Agents report what they could not say as a named missing `Cast` method.
   Add it centrally, re-run that batch. Never work around, never stub.
4. `scripts/audit.py` on the new rows; `scripts/check.py --all` for the
   level.
5. Re-record fixtures, add one at the new level, commit, close the issues
   from the commit (`Closes #N`).

### What makes a level done

`coverage.py` full for that level and `audit.py` clean — not a row count and
not my say-so. A monster stays all-or-nothing: fieldable only once every
ability on its block is written.

---

## Stopping

Runs until it runs out, checking in only for real blockers. The things most
likely to stop it, in order of likelihood:

- **A concept that recurs and was not planned for.** Dual-range was exactly
  this — it looked like a dozen rows and is seventy-two. If another turns
  up at level 5 or 7, it comes back to you rather than being worked around.
- **Balance** (issue #75). The party wins 3–6 of 10 at level 1 with correct
  maths, and you have said not yet. Fights at higher levels will show this
  more sharply, and it is a judgement call, not a bug.
- **The day clock** (issue #72) — a decision about whether the engine is
  encounter-scoped, not something to guess at.

---

## Cost, honestly

Level 1 was ~212 rows and took nine agents. The remaining 2,744 rows is
roughly thirteen times that. Monsters dominate: **92% of what is left**.
Powers are finite and close 57 issues; the monster tail is where this could
run indefinitely, and `check.py --history` is the instrument for noticing if
the checks themselves start to cost more than they catch.

`audit.py --changed` already keeps the edit loop at ~3s; the full sweep
grows toward ~5 minutes at completion, which is the known curve (issue #76).

---

## Verification

Per wave: `uv run scripts/check.py --all` — ruff, audit, leaks, replay,
fight, api_smoke, browser. Per level, additionally:

- `scripts/coverage.py --monsters --max-level N --list` — what is blocking
  each unfielded monster
- `scripts/fight.py --level N` — a real fight at the new level, read by eye
- `scripts/transcript.py` — if a fight looks wrong, the log is on disk

Phase 1 needs verification that content waves do not: each of its items is a
rule change, and a rule change moves every row at once. So each lands with a
demonstration run against the real thing rather than an assertion — the way
`risk_along` was checked against what `step` actually does, and the way the
sustain bug above was found. `audit.py` widens to the full sweep
automatically whenever `engine/` is touched, which is exactly this case.

## Housekeeping

Copy this to `./plans/20260924-finishing-the-content.md` at the start, per
your workflow. New issues to open before starting: sustain (1c), the action
subject (1b), stances (1e), polymorph (1g) — the rest already have numbers.
