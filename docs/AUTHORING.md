# You are writing 4e-alike content as Python

Repo: `/Users/camille/proj/combat_engine`. Run everything with `uv run`.

## The one rule that is not negotiable

**You will never be told what anything is called, and you must never go and
find out.** Every row you write is identified by an id — `p1004`, `m237a2`.
The specs you get are mechanics only: the names and the flavour text have
been stripped out and live in a separate localisation file that the engine
never reads.

So: **do not** grep `game.db` for names, **do not** open the localisation
file, **do not** search the web, **do not** put a guessed name in a comment
or a docstring or a variable. If a spec says `m237` you write `m237`. This
is the whole legal basis of the project — a game system cannot be
trademarked but the prose it is printed in can.

You may read `game.db` for **numbers** (defences, hp, speed) if you need to,
though you almost never will: a monster's numbers load automatically.

## What you write

A row is a decorated function. The decorator header is **data** — the UI and
the AI policy read it without running anything. The body is plain Python
against a `Cast` context called `c`.

```python
@power(
    "p1004",                      # the id from the spec, nothing else
    level=1,
    cls="fighter",                # omit for monsters
    usage=ENCOUNTER,              # AT_WILL | ENCOUNTER | DAILY
    action=STANDARD,              # STANDARD | MOVE | MINOR | FREE | INTERRUPT | REACTION | OPPORTUNITY
    reach=Melee(1),               # Melee(n) | Ranged(n) | CloseBurst(n) | CloseBlast(n) | AreaBurst(n, within) | MeleeOrRanged(m, r) | PERSONAL
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(STR, vs=AC),    # for monsters: Attack(vs=AC, printed=6)
    damage=Damage("1d8", 3),      # monsters only -- see below
)
def p1004(c: Cast) -> None:
    """One or two lines on what it does and any judgement you had to make."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.prone()
```

**The body is called once per target.** `c.target` is the current one. Use
`c.first` to guard a line that should happen once for the whole power rather
than once per target.

Everything defaults to `c.target`; pass `on=` to aim somewhere else.

### A printed Trigger line must be declared, not just quoted

Many utility powers are immediate actions: "Trigger: An enemy attacks you
and has combat advantage against you." **`trigger="..."` alone is prose the
engine never reads** -- a row with only that can never fire. Declare it:

```python
@power(
    "p1122", ..., action=ActionType.IMMEDIATE_INTERRUPT,
    trigger="an enemy attacks you and has combat advantage against you",
    on=Trigger(AttackDeclared, targets_me, "an enemy attacks you"),
)
```

`on=Trigger(event, predicate, text)`. Ready-made predicates, all importable
from `combat_engine.engine`: `targets_me`, `by_me`, `about_me`, `not_me`,
`leaves_me_out`, `ally_within(n)`, `enemy_within(n)`,
`enemy_target_within(n)`, `by_melee`, `by_ranged`, `cursed_by_me`, and
`both(...)` to combine them. Events are in `engine/events.py`.

Inside the body, `c.trigger` is the event being answered and `c.cancel()`
stops it -- only an interrupt can, which is the printed rule.

If no predicate expresses the printed sentence, **say so in your report**
rather than approximating it. Thirteen rows were once declared with prose
triggers nothing read, and they looked finished.

### Things that cost other people time

Every one of these is a real hour somebody lost. They are all the same
shape: **a thing that is silently false**, which looks exactly like a rule
that never applies.

* **`about_me` reads `ev.actor` and only `ev.actor`.** Events that name
  their subject `target` -- `ConditionApplied` is the common one -- are
  false under it forever. Use `targets_me` there. `lint.py` now catches this
  statically, so a bad one fails the run rather than shipping.
* **A gate on a key the context does not carry is false, not an error.**
  The damage context has `target`, `power`, `opportunity`, `charge` -- and
  **no `attacker`, no `ranged`**. "Melee attacks deal N extra" has to gate
  on `get(ctx["power"]).reach.kind`.
* **Defaults differ, and not always on purpose.** `c.may(...)` asks
  **`c.target`** deliberately -- a heal asks whose surge is being spent.
  `c.speed_of()`, `c.save()`, `c.resist()` and `c.surge_value()` default to
  the **caster**. `c.bonus`, `c.penalty` and `c.forbid` still fall to
  `c.target`, so on a `target=NO_TARGET` self-buff they apply to nobody and
  return `None` while the row still audits as having done something. For a
  caster-side "you can", write `who=c.me`; for a caster-side modifier,
  `on=c.me`.
* **"Did this attack have combat advantage?" is `ev.result.advantage`**,
  read off the `Hit`. Asking `has_combat_advantage` again is too late: a
  one-shot grant has already been spent. The live `AttackResult` rides on
  the attack events as a plain attribute.
* **`query.enemies` filters out the dead**, so `ev.actor in enemies(...)`
  on a `Dropped` is false every time. Compare `team()` directly.
* **`c.suffering(label)`** matches by substring and leaves the caster out
  unless you pass `include_self=True`.
* **Ongoing damage of one type does not stack — the highest applies.**
  `c.ongoing` enforces it: a weaker burn of the same type is refused and
  the standing one is returned, a stronger one supersedes it. Different
  types stack normally. A row reading "if the target is already taking
  ongoing fire damage, increase it" therefore has exactly one hold to find.
* **A monster does not spend a healing surge unless its row says so.** It
  carries one per tier so that a leader line -- "an adjacent ally can spend
  a healing surge" -- has something to spend, and takes no second wind of
  its own. `c.spend_surge` and `c.surge` are the printed line saying so.
* **Two bonuses of the same `kind` do not add — the larger wins.** That is
  the printed stacking rule, and it makes "+1, or +2 while bloodied"
  written as a +1 plus a gated +1 come to **+1 forever**, which looks
  exactly like a working aura. It has to be a +1 and a gated **+2**.
* **`c.damage` maxes its dice on a critical.** A high-crit line that adds
  an extra *rolled* die inside the crit branch gets the maximum instead of
  a roll; `c.flat(c.roll("1d8"))` is the way to add one.
* **`MoveStart` fires before the creature has moved.** A reaction declared
  on it resolves where nothing has happened yet; "an adjacent enemy shifts"
  wants `MoveEnd`, which carries `kind_`.

### The vocabulary, beyond the basics

Grown one method at a time, each because a row was left out of the tree
naming it. `vocab.txt` is the authority; this is what is easy to miss.

* **Movement as a state:** `c.moving_as("climb")` -- what a creature is
  doing *now*, held past the end of the move, where `Movement.modes` only
  ever said what it *could* do. `query.moving_as(world, eid, mode)` is the
  same question from a `requires=` gate, which gets `(world, eid)` and no
  `Cast`.
* **Charge:** an action kind, with `charge` in the attack **and** damage
  contexts and on `AttackDeclared`/`AttackRolled`/`Hit`/`Miss`.
  `by_charge` is the predicate.
* **Sustain that pays out:** `until=When.SUSTAIN` with `sustain=MINOR`
  holds an effect; `c.on_sustain(effect, fn)` is what happens each time it
  is sustained. Without the second, the payout half of the printed line
  goes nowhere.
* **Relations:** `c.master`/`c.servants`/`c.bind`, `c.rider`/`c.mount`/
  `c.ride` (a mount carries its rider), `c.guard`/`c.guarding`/
  `c.is_guarded`. The audit board sets all three, so rows reading "its
  master" fire there.
* **Bringing things into a fight:** `c.summon(ref, at=)` puts a creature on
  the board **and** in the initiative order; `c.extra_turn(at=)` gives a
  solo a second slot.
* **Taking things away:** `c.forbid(ref, until=)` removes one row;
  `c.no_basic(until=)` removes what a row is *used as*, which is a
  different operation.
* **The rest:** `c.overrun(to=)` (trample), `c.shift(share=True)`,
  `Condition.SQUEEZING`, `c.phasing()`, `c.absorb(ev)`,
  `c.resist_forced(n)`, `c.half_healing()`, `c.bonus("crit_range", n)`,
  `c.zone(..., blocks_sight=True)` and the same on `c.hazard`,
  `ActionSpent(actor, cost)` from `Encounter.spend`.
* **`on=` takes one `Trigger` or a sequence**, so a printed line naming
  several things -- "pushed, pulled, slid, **or knocked prone**" -- declares
  all of it. Declaring half of it looks finished and is wrong.

### The full `Cast` surface

Run `uv run scripts/vocab.py`. It is generated from
the code, so it is current and complete. **If a method is not in it, it does
not exist.**

### Monsters specifically

* Numbers — hp, AC, Fort/Ref/Will, speed, ability scores, resistances —
  **load from the database. Never hand-write them.**
* The attack line goes in the header as `Attack(vs=AC, printed=6)`, printed
  exactly as the spec shows. The engine subtracts the level term itself.
* The damage line goes in the header as `Damage("1d10", 5)` and the body
  calls `c.hit()` to apply it. This matters: damage in the header is *data*,
  so an MM1 monster can be rescaled to MM3 maths later. Only reach for
  `c.damage(...)` in the body when the line is genuinely more complicated
  than one expression (e.g. "or 5 damage if it has combat advantage").
* A recharge power is `usage=Usage.RECHARGE, recharge=6` -- two fields, not
  a callable. `Damage(..., kind=LIMITED)` for a recharge or encounter power,
  `kind=MINION` for a minion's fixed damage. Import from
  `combat_engine.engine.monster_math`.
* A **minion** deals its damage on a hit and takes none of this specially —
  its 1 hp is in the database.
* Auras, regeneration and "the first time each round" are all in `vocab.txt`.

## A row with no combat consequence at all

Some utility powers are **narrative only**: the whole printed Effect is a
bonus to a skill check, or a ritual, or lighting a lamp. Those are not
failures to write and they are not yours to invent a combat effect for.

Declare them with `out_of_combat=True` and an empty-ish body -- see
`content/powers/wizard/level_0.py`, where all four cantrips do this. The
flag is the difference between *deliberately inert* and *not written yet*:
`audit.py` stops expecting the row to do anything, `actions.legal` stops
offering it in a fight, and `coverage.py` still counts it as done.

**A Prerequisite is not the same thing.** A row that merely requires
training in a skill is usually an ordinary combat power with an entry
requirement, and should be written properly. It is narrative-only when the
*Effect itself* is a skill bonus and nothing else.

## When you cannot say something

**Do not work around it and do not fake it.** If the `Cast` surface cannot
express a row:

1. Leave the row out entirely. No stub, no placeholder, no `pass`, no
   comment explaining the absence. `scripts/coverage.py` counts what is
   missing and a count cannot go stale.
2. Put it in your final report, naming **the exact `Cast` method or header
   field you wanted and what it should do**. The engine gets the method added
   centrally and your batch is re-run.

A row you half-wrote is worse than a row that is absent, because the absence
is counted and the half-row looks finished.

Equally: if you find something that looks like an **engine bug**, say so in
the report with the evidence. The last wave found a real one this way.

## Checking your work

```
uv run scripts/lint.py                     # must pass -- see below
uv run scripts/show.py <ref>               # renders one row's header
uv run scripts/audit.py p1004 p1008 ...    # YOUR refs -- this is the one to use
uv run scripts/audit.py <ref> --verbose    # what a row actually did
```

**Audit your own refs by name, not `--monsters` or `--class`.** Those fire
every row of that role or class -- several hundred now -- which costs twenty
to thirty seconds a run and tells you nothing about your batch that naming
your refs would not. Naming them takes under a second. `--class` is
repeatable if you really want a whole class.

`lint.py` is ruff plus two structural walks: a method defined twice in a
class (which ruff misses in a file the size of `cast.py`, and which once
silently disabled every conjuration in the game), and a declared trigger
whose predicate reads a field its event does not have.

`audit.py` is the one that matters. A row that raises is a bug; a row that
does **nothing** — no damage, no condition, no movement, no effect — is what
a wrong power looks like. **That check only started working recently**: the
board leaves effects live for its own setup, so every row counted as having
done something, and no row in the tree had ever actually been checked for
it. If yours reports SILENT, it is telling you something real. Get your rows to fire cleanly before you report.

## Style (the repo owner's, and it is enforced)

* Concise. Comments only where something is non-obvious.
* Docstrings explain **judgement calls**, not restatements of the spec.
* Never create test files.
* Match the surrounding code.

## Your report

Return, as your final message:
1. The ids you wrote, and the count.
2. The ids you left out, each with the one-line reason and the named `Cast`
   method or header field that would fix it.
3. Anything you think is an engine bug.

Nothing else — no preamble, no summary of the task.
