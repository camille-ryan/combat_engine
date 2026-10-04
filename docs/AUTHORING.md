# You are writing 4e-alike content as Python

Repo: `/Users/camille/proj/combat_engine`. Run everything with `uv run`.

## Who this is for

**A content author**, usually one of several working at the same time. That
changes two rules, and they are the two this page and `FEAT_BRIEF.md` used to
disagree about:

* **Lint only your own file** -- `uv run ruff check --fix <your file>`, then
  `uv run scripts/lint.py` to check the tree's structure without rewriting
  it. A tree-wide `ruff --fix` has destroyed another agent's work.
* **Do not touch git.** Not `add`, not `commit`, not `stash`. The session
  that dispatched you commits.

The main session does the opposite of both -- it lints the tree and it
commits. `CONTRIBUTING.md` describes that side; this page describes yours.

## The one rule that is not negotiable

**You will never be told what anything is called, and you must never go and
find out.** Every row you write is identified by an id — `p1004`, `m237a2`.
The specs you get are mechanics only: the names and the flavour text have
been stripped out and live in a separate localisation file that the engine
never reads.

So: **do not** grep `game.db` for names, **do not** open the localisation
file, **do not** put a guessed name in a comment or a docstring or a
variable. If a spec says `m237` you write `m237`. This is the whole legal
basis of the project — a game system cannot be trademarked but the prose it
is printed in can.

**Searching the web for a *mechanic* you do not understand is encouraged.
Searching for a *name* is forbidden.** Those are different questions and only
the second one is a leak: "how does a close burst measure from a Large
creature" is a rule, and rules are not protectable. This passage used to say
"do not search the web" flatly, which contradicted `FEAT_BRIEF.md` telling
authors to look a rule up — and since that file sends you here first, the
flat version was the one being overridden anyway.

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
  So the two lists below are load-bearing, and this passage was wrong
  about them for two sessions -- it said the damage side had no `ranged`
  and no `advantage`, and three separate rows dropped a clause on the
  strength of it. Read them from `resolve.py`, not from here, if you are
  about to mark a row.

  The **damage** context (`resolve.deal_damage`): `target`, `power`,
  `opportunity`, `charge`, `granted_by`, `granted_via`, `dtype`,
  `dtypes`, `crit`, `advantage`, `ranged`.

  The **attack** context (`resolve.attack`) has all of those but the
  damage-only three, plus `attacker`, `action_point` and `branch`.

  Two that still catch people. Neither context carries an `attacker` on
  the damage side, so "damage against a creature *you* have marked" asks
  the board rather than the context. And `power` on the damage side is
  the `detail` of whatever rolled the blow -- which is the *row's* ref,
  so a striker's extra damage arrives under `cf:rogue-scoundrel-f4` and
  not under the attack that carried it. That is a feature: it is how a
  rider knows which feature paid.
* **Defaults differ, and the split is about whose thing it is.**

  **Yours, so they default to the caster:** `c.resist`, `c.stance`,
  `c.mode`, `c.watch`, `c.immovable`, `c.spend_surge`, `c.grant_row`,
  `c.ignores_difficult`, `c.speed_of`, `c.surge_value`,
  `c.see_invisible`, `c.ignore_cover`, `c.shift_as`.

  **Theirs, so they follow `c.target`:** `c.may` (a heal asks whose surge
  is being spent), `c.save` ("*the target* makes a saving throw"),
  `c.bonus`, `c.penalty`, `c.forbid`, `c.condition`, `c.cure`, `c.immune`,
  `c.no_cover`, `c.grant_action`, `c.initiative`.

  For the wrong side of either, name it: `on=c.me`, or `on=<who>`.

  This list is worth trusting only because it has been wrong twice. It
  described a caster default for `c.resist` and `c.save` while the code did
  neither, and a rage consequently installed itself on the creature being
  hit. If a default surprises you, check the code and fix whichever is
  wrong -- the note is not authority.
* **"Did this attack have combat advantage?" is `ev.result.advantage`**,
  read off the `Hit`. Asking `has_combat_advantage` again is too late: a
  one-shot grant has already been spent. The live `AttackResult` rides on
  the attack events as a plain attribute.
* **`query.enemies` filters out the dead**, so `ev.actor in enemies(...)`
  on a `Dropped` is false every time. Compare `team()` directly.
* **`c.suffering(label)`** matches by substring and leaves the caster out
  unless you pass `include_self=True`.
* **A row whose printed Effect *is* a charge declares `charges=True`.**
  Without it the engine measures the weapon's reach before the run and
  refuses the row whenever the target is further off than a sword -- which
  is every situation a charge is for.
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
* **`MoveStart` fires before the creature has moved, and that cuts both
  ways.** A reaction declared on it resolves where nothing has happened yet,
  so "an enemy shifts *to somewhere*" wants `MoveEnd`, which carries `kind_`.
  But the defender shape — "an **adjacent** enemy marked by you moves" —
  wants `MoveStart`, because by `MoveEnd` the enemy has left and
  `c.adjacent(ev.actor)` is false *precisely when the row should fire*.
  `MoveStart` carries `kind_` too, and it is the interrupt window an
  opportunity attack belongs in. Three battlemind rows were silently inert
  on `MoveEnd` before this sentence had its second half. **Ask where the
  creature has to be for the row to be true, then pick the event.**
  `Moved` now carries `kind_` as well, and it is the only one of the three
  that also carries `from_` -- so "an ally adjacent to you **before** the
  teleport" is asked there and nowhere else.
* **A `requires=` on a trait does not gate it -- it can kill it.**
  `turns.arm_traits_of` arms every `action=NONE` row **through `dsl.use`**,
  which calls `usable`, which evaluates `requires` via `can_branch`. There is
  no exemption for a no-action row. So a trait whose Requirement is false at
  the moment of arming is **refused once and never armed again for the whole
  fight** -- and a Requirement that could become true later (a rider mounting,
  a shape being taken, an ally arriving) never gets the chance.

  So: ask the Requirement **in the body**, inside the watch, where it is
  re-read every time the clause might pay. `requires_text` alone is safe and
  is what the card shows; `requires=` on a trait is only safe when the
  Requirement is a fact that cannot change during a fight.

  (An earlier version of this entry said the opposite -- that `requires=` on a
  trait is never consulted, so writing it was harmless. That was wrong in both
  halves, and the advice would have silently killed any trait gated on
  something that starts false. `audit.py` makes it hard to see: its trait
  branch counts the row as fired without calling `use`, so a trait refused by
  its own Requirement reports **SILENT rather than UNUSED**, which reads as a
  board limitation.)
* **Two of those fields are set at emission, not declared on the event**, and
  reading the dataclass will tell you they do not exist. `movement.py` does
  `moved.kind_ = kind` on every emission -- the comment there says "so
  `ev.kind_` is never missing" -- and `resolve.attack` does
  `landed.among = among or (target,)`, which is the whole target list of one
  use. Both are real and both are safe to read. Two authors in one afternoon
  checked `dataclasses.fields(...)`, found them absent, and concluded one that
  a doc was wrong and the other that a clause was unaskable; one of them marked
  a finished row as blocked. **Check the emission site, not the declaration.**
* **`PowerUsed` is announced *before* the body runs, and it is the same
  trap.** `dsl.use` calls `cast.used()` above `p.body(cast)`, so a row
  watching `PowerUsed` sees a world in which the power has not happened
  yet -- two wild-shape rows watched it and found the *previous* form
  still on. Targets are chosen before the body, so `ev.targets` is
  trustworthy there; anything the body *does* is not. If the row turns on
  the consequence rather than the declaration, watch what the body emits
  (`Hit`, `EffectApplied`, `Moved`) instead.
* **`PowerUsed.trigger` is the event the power was used in answer to**,
  and `PowerResolved` carries it too. It is `None` for an ordinary use.
  Reach for it rather than `ev.targets` whenever the row says "the
  triggering enemy" or "the triggering ally": an immediate action is
  routinely `NO_TARGET`, or declares `target=ONE_CREATURE` and then aims
  itself at a creature off its own trigger, so `ev.targets` names
  somebody it never touched. Twenty-one rows were blocked on this.
* **`Hit` does not declare `opportunity`.** `resolve.attack` sets it as a
  plain attribute afterwards, so a row must ask
  `getattr(ev, "opportunity", False)`. Same shape as `charge`, `vs`,
  `action_point`, `branch`, `granted_by`, `granted_via` and `hand` --
  every one of them a plain attribute, deliberately, so that none of them
  reaches the wire or a replay fixture. `hand` is `"main"` or `"off"` and
  is what a two-weapon rider's "when you hit with your off-hand weapon"
  reads; it was in the attack context and on nothing that announced the
  outcome.
* **`Bloodied` carries `source`**, the way `Dropped` does -- whoever
  crossed the creature's half-hit-point line, or None when nothing did.
  `by_me` reads it, so "whenever you bloody an enemy" is a declared
  trigger and no longer has to be routed off `DamageApplied` and
  re-derive the threshold by hand.
* **`DamageApplied.absorbed` is temporary hit points and nothing else.**
  Resistance is `resisted`, which is the points the target's resistance
  and immunity took off before any of it reached hit points. A row gating
  on `absorbed > 0` to mean "my resistance ate some of this" is false in
  every fight without temp hp, which is nearly all of them.
* **`c.grant_action` understands `shift`, `stand`, `escape` and
  `second_wind`, and silently eats anything else.** A word it does not
  know "is carried, costs nothing and does nothing", so a row written
  with one is finished-looking and inert -- check `actions.legal`
  against the word before you use it.

  This passage used to name only `shift` and `stand`, and offered "you
  can escape a grab as a minor action" as its example of a clause that
  must be a `dropped=`. That is now precisely the clause that works,
  and a row was left marked on the strength of the sentence. The list
  above is the one in `actions.legal`; when it grows, this grows.
* **A bonus's `kind` is the word the card prints in front of "bonus".**
  Not a guess, not a default, and not the class's name. Two of the same
  kind do not stack and the larger wins, so a wrong one is a number that
  is quietly too small in every fight. A plain "+1 bonus" with no type
  word is **untyped** — leave `kind=` off.

### The vocabulary, beyond the basics

Grown one method at a time, each because a row was left out of the tree
naming it. **`uv run scripts/vocab.py` is the authority** -- it is generated
from the code, so it cannot be stale; this page can be and has been. (This
line used to cite a `vocab.txt`, which has never existed.)

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
* **One row reaching another:** `c.use_power(ref, on=, spend=, again=)`
  uses a row *now*, at this row's action cost -- "as the wizard's
  p1227 power", "use p377 as an immediate reaction". It lends the row
  if the creature has not got it, and it leaves the borrowed row's last
  attack in `c.result`, so `c.landed` answers the printed "if you hit".
  `c.expend_row(ref)` is the opposite half: it spends a use and the row
  **never runs**, which is the price three dozen cards charge, and its
  False is the Requirement they print. `c.restore_use` hands one back
  and `c.expended(group=)` reads which are gone.
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

It ends with a **worked row per shape** — a declared trigger, a save-ends
rider, a charge, a monster header, a deliberately inert row. Those are real
rows picked out of the tree by what they are, so they are current too. They
are there so you do not go looking for a file to copy: **do not open a large
content file for style**. The examples are the style.

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
* **`half_on_miss=True` does nothing on its own. Write the branch.** The
  flag is declared data — `scripts/cards.py` reads it to check your header
  against the card, and **no line of the engine reads it at all.** The
  page's Miss sentence comes from the printed prose, not from the flag. So
  a row that sets it and writes a bare `if c.strike(): c.hit()` drops its
  Miss line in play and looks finished. Say it both ways:

  ```python
  damage=Damage("2d6", 4, half_on_miss=True),   # what the card prints
  ...
      if c.strike():
          c.hit()
      else:
          c.hit(half=True)                      # what actually happens
  ```

  Six rows had the header and not the branch. `lint.py` refuses that pair
  now, so you will be told rather than finding out in play.
* A **minion** deals its damage on a hit and takes none of this specially —
  its 1 hp is in the database.
* Auras, regeneration and "the first time each round" are all in
  `scripts/vocab.py`'s output.

### Magic items specifically

**A magic item is not a new kind of thing.** It is a base item the engine
already has, with properties laid on top: a magic longsword is the printed
longsword with an enhancement bonus and some rows attached. You never
declare a weapon, a weapon group or a suit of armour.

* **The numbers load from the database**, exactly as a monster's do. The
  level ladder, the enhancement bonus, the price, the slot, the critical
  rider and the base-item restriction are all columns, and `spec.py` prints
  them above the blocks with a line saying so. **Never hand-write one.** If
  your row's whole content is "+2 to attack and damage", there is nothing
  to write and the item is already finished by its columns.
* **The unit of work is a block, not an item.** An item's page has a
  Property and sometimes one or more Powers, and each is its own ref:
  `i601x1` for the first property, `i601p1` for the first power. Write the
  one you were given. An item with two powers is two pieces of work and
  either can land without the other.
* **An item's Power is an ordinary `@power` row** with `cls="item"`. It
  goes into `Powers.known` while the item is worn, so recharge, the action
  menu, the trigger dispatcher and `PowerUsed` all work on it unchanged —
  write it exactly as you would write a class power.
* **An always-on Property is `action=ActionType.NONE`** — a trait, armed
  once at the start of the fight. Not a chooseable row: a policy offered an
  at-will that re-applies its own state takes it every single turn, which
  once turned a twelve-round win into a thirty-round stalemate.
* "Critical: +1d6 damage per plus" is a column, not a body. So is the
  enhancement bonus. Both are already applied by `engine/equipment.py`.
* **A `Level 11:` or `Level 21:` line in a block is out of scope.** The
  page prints every tier and the project stops at 10, so write the
  heroic number and ignore the rest. Do not mark it `todo` — it is not a
  gap, it is paragon.

### Feats specifically

* **A feat is an ordinary row**, almost always a trait:
  `action=ActionType.NONE` with no trigger, armed once at the start of the
  fight.
* **`kind=` is whatever word the card prints in front of "bonus", and
  nothing else.** "A +2 feat bonus" is `kind="feat"`; "a +1 shield bonus"
  is `kind="shield"`; a plain "+1 bonus" with no type word is **untyped**,
  which is `c.bonus(...)` with no `kind=` at all. Only 9 of the first 80
  general feats printed the word "feat". Defaulting to it would have made
  eight untyped bonuses non-stacking and two typed ones the wrong type,
  in every fight, invisibly.
* **A feat that grants a power is a pair**: the feat's own ref, whose
  entire printed benefit is "you gain the `fNNNb` power", and the card
  `fNNNb` beside it. Write the card as an ordinary row and the parent as
  `c.grant_row("fNNNb")`. Both are in your brief; write both.
* **The prerequisite is not yours to write.** It is a column, parsed into a
  structured gate, and `chargen.meets` enforces it when the character is
  built. `Power.requires` is the wrong tool: that one is asked mid-fight of
  a creature on a board, and "you must be a fighter" does not change
  between rounds. Write the Benefit and nothing else.
* Your brief prints the gate above the benefit: `requires: dex>=13`,
  `has f173`, `has cf:cleric-templar-f0`, `trained acrobatics`,
  `proficient leather armor`, `level>=4`, joined with `&` and `|`. A
  clause shown as `q17` is one the engine cannot yet express, and
  `unparsed: 2` counts how many of those the gate has. **None of it is
  yours to write and none of it is a reason to skip the feat** — the
  Benefit is still worth writing whatever the gate says.
* A common shape is a rider on another row: "when you use *X*…". Declare
  it as `on=Trigger(PowerUsed, …)` against the ref the spec gives you,
  and read the note above about `PowerUsed` firing *before* the body.
* A feat whose whole benefit is a skill bonus or a ritual is
  `out_of_combat=True` with an empty body, like a cantrip that lights a
  torch. That is a finished row, not a skipped one.

## A row with no combat consequence at all

Some utility powers are **narrative only**: the whole printed Effect is a
bonus to a skill check, or a ritual, or lighting a lamp. Those are not
failures to write and they are not yours to invent a combat effect for.

Declare them with `out_of_combat=True` and an empty-ish body -- see
`content/powers/wizard/level_0.py`, where all four cantrips do this. The
flag is the difference between *deliberately inert* and *not written yet*:
`audit.py` stops expecting the row to do anything, `actions.legal` stops
offering it in a fight, and `coverage.py` still counts it as done.

`out_of_combat` and `todo=` are opposites and setting both is refused at
import: one says "finished, and deliberately does nothing", the other says
"unfinished". A row claiming both would be waved through by the audit's
inert branch and never looked at again.

`out_of_combat` is **per row**, and most items print a narrative line beside
a combat one. For a row that fights and also does something inert, the field
is `narrative=` — see "When the clause is not missing", below.

**A Prerequisite is not the same thing.** A row that merely requires
training in a skill is usually an ordinary combat power with an entry
requirement, and should be written properly. It is narrative-only when the
*Effect itself* is a skill bonus and nothing else.

## When you cannot say something

**Do not work around it and do not fake it.** Write the row anyway, and say
in the row itself what you could not say:

```python
@power("i601p0", ..., todo=("c.deals()",))
def _(c): ...
```

`todo=` takes **symbols, never prose** — `c.deals()`, `query.speed(world,
eid, ctx)`, `Keyword.RAGE`, `Dropped.source`. A sentence is refused at
import, because the whole point is that a tool can go and look for the
thing. Name every symbol you wanted, not just the first.

What that buys, and why it is not a stub:

* **It is refused in play.** `dsl.usable` returns `not finished yet` for any
  row with a `todo`, so it is exactly as inert as the absence it replaced —
  never offered, never chosen, never half-resolved.
* **It is counted partial and never done.** `coverage.py` prints three
  states and the percentage is done over total, so a marker cannot move the
  number.
* **It is named individually.** `audit.py` prints one `TODO` line per row,
  not a count.
* **It holds its issue open**, and `issues.py` lists the markers on the
  issue grouped by the symbol each wants.
* **It goes red when the gap closes.** `todo.py` fails the moment a named
  symbol exists, and fails if markers pass a tenth of the tree.

### When you can say *most* of it

The commonest case, and `todo=` is the wrong tool for it. A feat reading
"+2 damage when you charge, and +2 to bull rush attempts" has a first half
the engine can say and a second half it cannot. Marking the whole row
`todo` refuses it in play and throws the working half away.

So there is a second field, and it is the one you will reach for more
often:

```python
@power("f9", ..., dropped=("c.bull_rush()",))
def f9(c: Cast) -> None:
    """The bull rush half is dropped; nothing grants a bonus to one."""
    c.bonus("damage", 2, when=lambda ctx: ctx["charge"])
```

* **`todo=`** — nothing here works. The row is **refused in play**.
* **`dropped=`** — the row works and one named clause is missing. The row
  **is offered and does its job.**
* **`narrative=`** — the row works and one clause is not missing at all: it
  has no combat meaning. Counted done, never red, still listed. Below.

Both take symbols, both are counted partial and never done, both are named
by the audit, both hold their issue open, and both go red the day the
symbol arrives. The only difference is whether the row plays.

**Do not drop a clause silently in a docstring.** That was the old habit
and it is the exact failure this project is built to hunt: the row looks
finished, the count says finished, and a printed sentence is quietly gone.
A docstring is not queryable; `dropped=` is.

Setting both on one row is refused at import — they say opposite things.

Still put it in your final report, naming the symbol and what it should do.

### When the clause is not missing — it has nothing to do with a fight

`dropped=` says "this clause is absent and here is the symbol it waits on".
Some clauses are not waiting on anything. An item that gives a real bonus to
Will against illusions **and** +5 to picking locks has a second half that is
not a gap: nothing in a fight ever rolls Thievery, so a verb to hold the
bonus would be a mechanism nobody ever passes a purpose to — and a marker
naming a symbol that must never be built sits in the queue forever.

That is a third field:

```python
@power("i1", ..., narrative=("skill:thievery",))
def i1(c: Cast) -> None:
    """The Will half is exact. Opening a lock is the other clause, and no
    thievery check is rolled on a board, so the bonus has nowhere to go
    and nothing is missing."""
    c.bonus(WILL, 2, ...)
```

* **It takes `skill:<name>`, not a symbol** — the same key `c.bonus` takes,
  one of the seventeen skills, naming the skill whose *circumstance* is the
  narrative part. There is no symbol to name, which is the whole point. A
  sentence, an invented skill and a wishful verb are all refused at import.
* **Naming a skill the engine does consult is fine.** `skill:perception` is
  common. The claim is about the circumstance — "to detect illusions" — and
  never about the skill.
* **A reason in the docstring is required, not hoped for.** It must name
  the skill and say why that narrowing has no combat meaning. `power()`
  refuses the row without one, because this is the easiest of the three
  fields to reach for to make an awkward clause go away.
* **It is counted done and never goes red** — there is nothing to come back
  for. There was a marker budget it did not spend either; that gate is gone,
  and `todo.py`'s docstring says why.
* **It is still named.** `todo.py` lists every such row under the skill it
  narrows, so the set stays readable and a skill collecting excuses is
  visible.
* **It is audited like any other finished row**, so one that claimed this and
  then did nothing in a fight is caught silent. So is a `dropped=` row: this
  said a `dropped=` row was "exempt from the audit's run" and it never has
  been -- `audit.py` fires it deliberately, because the half that works has to
  be checked like anything else. The audit prints the dropped count on its own
  line, so "fires and does something" is not read as "finished".

`narrative=` with `todo=` is refused — a `todo` row is refused in play and
has no combat half for the clause to sit beside. `narrative=` with
`out_of_combat=True` is refused too: the row is already declared narrative
whole, and saying it again per clause draws a distinction against nothing.

`narrative=` with `dropped=` **is** allowed, and is the honest answer for a
row with both kinds of absence: `i802x1` balances and climbs trees
(narrative) and also softens a fall, which the engine really is missing.

**The test.** If building the mechanism would be work worth doing, it is a
`dropped=`. If building it would mean inventing a roll the engine never
makes, it is a `narrative=`. When in doubt it is a `dropped=` — that one
stays in a queue somebody reads.

**Leave a row out entirely only when there is nothing to decorate** — no
ref, no card. Then, and only then, `docs/blocked.json` records the reason.

A row you half-wrote *without* the marker is worse than a row that is
absent, because the absence is counted and the unmarked half-row looks
finished. The marker is what makes the difference.

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

### What checking should cost

Every tool call re-sends everything you have read and written so far, so the
call count is most of the bill. The last session ran 120 agents at a median
of 88 calls, and **no brief anywhere set a limit**. So:

* **Write a file in one `Write`.** Not a row at a time. A file built by
  twenty `Edit`s costs twenty passes over the whole context.
* **Read the spec, the vocabulary and this page. That is the reading.**
  Do not open a large content file to copy its style — `vocab.py` ends with
  worked rows for exactly that. Do not grep the tree for a row like yours.
* **Drive a row by hand only where a correct row and a broken one would look
  the same** — a trigger that may never fire, a default that may aim at the
  wrong creature. Not for every SILENT, and not for every UNUSED: a row the
  board simply cannot set up is fine, and saying so costs nothing.
* **About 150 tool calls for a class-sized batch.** If you pass it, stop and
  report what is left rather than pushing on. An unfinished batch is cheap to
  finish; an agent that ran twice as long as it needed to is not.

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
