# Triage the issues, then fix engine before UI

## Context

Two asks. **Triage**: nine open issues carry only the `claude` label and
cannot be scheduled. **Then fix**: engine issues first, UI after.

The previous plan in this file (`finish the partials`) is complete and
has been replaced.

**One correction shaped this plan.** I sized the work from issue
*bodies* and not their *comment threads*, and the threads are where the
updates live. #110 reads "1,295 powers" in its body; its comments say
127, and the tree says **17**. #74's body says traps and terrain; its
comments say terrain landed and traps alone remain. #213's comments
carry a design direction from Camille — a doctrine-based feat/item
scorer with a `tested` field — that the body does not mention. Read the
comments before sizing anything here.

**One piece of self-inflicted scope.** Importing theme powers and wild
talents yesterday (fixing an extraction fault that left 20 feats unable
to resolve) added **189 undeclared rows** to the tree. Nobody asked for
them. Camille has chosen to write them; they are Phase 3, and they are
why the undeclared count looks worse than the real backlog.

---

## Phase 0 — Triage

Labels exist already; nothing new is created. Everything non-UI is
`engine`, per Camille's choice.

| issue | add |
|---|---|
| #222 relations emit no `ConditionApplied` | `engine` `bug` |
| #219 `side="ally"` means two opposite things | `engine` `bug` |
| #215 `item.slot` holds printed setting terms | `engine` `bug` |
| #216 audit credits the harness's own provocation | `engine` `bug` |
| #218 sub-option importer mints a second ref | `engine` `bug` |
| #221 compendium links the row it names | `engine` |
| #220 no way to mark a clause narrative | `engine` |
| #217 6–13 rounds against a 3–4 round goal | `balance` |
| #223 session summary | `documentation` |

#223 is a report, not a work item — label it and leave it as the
record.

---

## Phase 1 — Where the engine is wrong today

These three corrupt results wherever they are touched, so they come
first. #220 rides along because it is small and unsticks ten rows.

**#219 — `side="ally"` means two opposite things.**
`Cast._while_inside` (`engine/cast.py:5418`) resolves sides through
`query.team`, and behind it `c.grants_in`, `c.cover_in`, `c.resist_in`
and `c.ignores_difficult_in` treat `"ally"` as *the caster's side
including the caster*. `c.within` and `c.in_squares` were changed
yesterday so `"ally"` **excludes** the caster and `"team"` includes.
Same word, opposite meanings, one file apart — and 95 content call
sites reach the zone verbs.

Bring `_while_inside` onto the same two words. Every zone caller's card
prints "you and your allies", so they become `"team"`; confirm that per
call site rather than assuming, because the ones that do not are the
whole point.

**#205 — a range mod stretches the reach and not the penalty.**
`resolve._long_range` (`resolve.py:452`) asks
`distance_between(...) <= weapon.ranged[0]` — the weapon's printed
number, raw. `dsl._stretched` already reads a `"range"` modifier when
deciding what may be aimed at, so a stretched shot is legal and still
penalised from the unstretched distance. Ask the same modifier here.
Note `"long_range"` is itself already a modifier, so "no penalty at
long range" works and must keep working.

**#222 — a grab, a mark and a domination announce nothing.**
`Relations.set` writes the condition straight onto `Conditions`, and
`Effects.cure` (`durations.py:344`) clears the relational ones through
`relations.clear`. So `ConditionApplied`/`ConditionEnded` never fire for
`GRABBED`, `MARKED` or `DOMINATED`, and a row declared the obvious way
is armed, reads correctly and can never fire. Two rows were found dead
exactly so.

Do the **check first, the event second**. A tracker rule that fails a
row waiting on `ConditionApplied` for one of those three conditions is
cheap and stops the bug recurring; the list derives from where
`_apply_condition` is called, so it need not be hand-kept. Then sweep
for other dead rows. Only then decide whether to emit the event —
marks are laid constantly and the blast radius is unmeasured, which is
why it was not done in passing.

**#220 — say that a clause is narrative rather than missing.**
Add `narrative=(...)` beside `todo=`/`dropped=`/`out_of_combat` in
`dsl.py` (the marker tuples are validated at `dsl.py:856`): counted
done, named by the audit so it stays visible, never red. Give it the
discipline `out_of_combat` has — a reason in the docstring — so it
cannot become a way to make an awkward clause disappear.

Then re-aim the ten rows now pointing at `c.skill_circumstance()`, a
verb that would be a mistake to build: `f3577 i1004x1 i1519x1 i3246x1
i663x1 i802x1 i840x1 i903x1 p16548 p16687`.

---

## Phase 2 — Finish the nearly-done

**#110 — 17 class powers.** The whole remainder, by class:

```
p464b p465b p13984 p16281b p10354   Wizard
p13462b p13320b p13339b             Psion
p10744 p7399                        Rogue
p12426b Battlemind   p14510 Druid   p4396 Ranger
p5845 Sorcerer       p5591 Warden   p13887 Warlock
p3839 Shaman
```

`p3839` is the row **#173** exists for — a second spirit companion,
against four engine functions and five helpers that assume one. Leave
it marked; writing it is not this phase.

**#98 — small monster verbs.** The issue has accumulated across four
comments and several entries are already built (`ActionSpent`,
`c.phasing`, and `c.cannot_attack` was used by a content agent
yesterday). **Re-read every entry against the tree before building
anything** — this is the file that taught us a stale note is a marker
no instrument can see. What survives is likely `c.shares_space`,
`c.carrying`, `c.learn`, `c.arm_trigger`, `c.walk_zone`.

**#74 — put a trap on a board.** `Trap` exists
(`components.py:183`) with `ref` and `sprung`, and deliberately has no
`Health` and no `Side` so it stays out of `query.creatures`.
`content/terrain.dress(world, seed)` already lays pillars and rubble
and is already called from `scripts/fight.py` and `api/session.py` —
so this is a placement pass in a function that exists, seeded the same
way so `--seed 7` stays `--seed 7`. Four written monster rows
(`m301a4`, `m675a3`, `m2821a3`, `m264a6`) have never fired.

---

## Phase 3 — The 189 theme and wild-talent rows

Scope I created; Camille has chosen to write it. These are `Theme
Power` and `Wild Talent Power` rows imported yesterday, keyed in `cls`
by the theme's alias ref (`x7_…`) or the literal `wild talent`.

Before dispatching: confirm `scripts/spec.py` surfaces them (it filters
by class, and these are neither a class nor a race), and confirm
`chargen.loadout` does **not** deal them — nothing selects a theme, and
a theme power dealt to every character would be wrong. That was
verified once at import and must hold after any `spec.py` change.

Then a content wave in the established shape: explicit ref lists
generated immediately before dispatch, one agent per batch,
`docs/AUTHORING.md` plus `vocab.py --brief` as the brief.

---

## Phase 4 — UI

**#164 — at-wills should have a green bar. One line.**
The CSS is written (`web/style.css:875` — green, red, grey), the DTO
carries `usage` (`api/dto.py:68`), and the bar renders in three places.
`web/app.js:938` tests `usage.startsWith("at will")` **with a space**;
`engine/types.py:48` is `AT_WILL = "at-will"` **with a hyphen**. So
at-wills alone fall through to the default grey rule. Encounter, daily
and recharge all match. Fix the spelling, accept both.

While there, two dead branches in the same function: `sectionFor`
(`app.js:889`) tests `usage == "aura"` and `action == "trait"`/
`"triggered"`, none of which is ever emitted, so those headings cannot
render; and `COST_ORDER` (`app.js:58`) lists `"immediate"` where the
enum emits `immediate_interrupt`/`immediate_reaction`.

**#139 — make moves explicit. Medium; a projection problem, not an
engine one.** Movement is represented three ways: `engine/actions.py`
emits one `Action` per reachable square (already explicit); the default
UI renders all of them as 100-plus buttons with a **non-clickable
board**; and an opt-in "freeform" mode (off by default) hides them and
walks on a bare board click. The complaint is the third — and the
default is the first.

What is missing on the wire:
* `OptionDTO` has no `dest` (`dto.py:144`) — a move's destination
  exists only inside the label string `"move to (3, 4)"`.
* `MovementDTO` has no `run` (`dto.py:176`), so running is reachable
  only from the enumerated list; `session.walk_to` matches `"move"`
  and `"shift"` only.
* Two independent reachability computations (`world.reachable_paths`
  in `actions._movement`, `movement.reachable` in `render.movement`).
  Divergence shows as a square the board paints green and `walk_to`
  answers 409.

Smallest honest change: add `dest` to `OptionDTO`, add `run` to
`MovementDTO`, teach `walk_to`/`AimRequest` the run mode, and require a
selected move action before a board click walks. Confirm with Camille
whether "explicit" also means the enumerated list should collapse to
one Move row.

---

## Verification

* `uv run scripts/check.py --all` at every phase boundary. Expect green
  but for `todo` (12.0% against a 10% ceiling), `specs` (#215) and
  `audit` — and record `audit`'s number each time, since finishing rows
  *raises* it as they stop being refused in play.
* **Replays**: never `replay.py record` on sight. It keeps pinned feats
  now, so a re-record is honest — but still prove the diff inert before
  keeping it: normalise effect ids and any new event field, then show
  rolls, damage and outcomes identical. Phases 1 and 2 will move
  fixtures; Phase 4 must not.
* **Phase 3 only**: `leaks.py` and `leaks.py --specs` after every
  rebuild of `data/game.db`.
* **Phase 4**: `scripts/api_smoke.py` is a JSON contract test and would
  not have caught #164. `scripts/browser.py` is the only front-end test
  and is currently `paused=` in `check.py` — un-pause it for this phase
  or the UI work has no net.
* Per #216, `audit.py`'s "fires and does something" is weak for a row
  hanging clauses on a `Hit`. Drive new gates by hand with a positive
  **and** a negative control.

## Out of scope, and the re-plan point

Re-plan after Phase 2 rather than running straight on.

Not here: **#213** (the scorer Camille specified — the largest item and
what makes win rate readable, so it deserves its own plan), **#217**
(deferred by choice), **#216**/**#204**/**#209** (the instruments and
the board's gear), **#173** (plural companions), **#72** (a `World`
outliving one fight, plus a per-day count), **#89**'s policy half,
**#175**, **#179**, **#221**, **#218**.

Also noticed and not scheduled: the adventuring-day UI is ~150 lines of
`app.js` calling `POST /api/day` (a hard 501) and two routes that 404;
`NewEncounter.scale` is accepted and ignored; `SESSIONS` never evicts.
Worth their own issues if Camille wants them.
