"""Converting a monster between the two sets of maths 4e was printed under.

Monster Manual 1 and 2 ran on one set of numbers; Monster Manual 3 and the
Monster Vault revised them. The revision is famous for the right reason:
MM1 monsters do too little damage and fights take too long. `MM3` rescales
an older row to the newer curve without touching what the row *does*.

**What actually differs, measured against this corpus rather than recalled.**
Standard monsters, heroic tier, first at-will attack:

    damage        lvl 1 both about 7; by lvl 10, MM1 11.5 and MM3 17.3
    brute attack  MM1 +4.1 over level, MM3 +4.7
    soldier       MM1 +5.4, MM3 +5.2 -- other roles converge on +5.0
    solo hp       MM1 3.9x a standard monster, MM3 3.4x
    AC, other defences, standard hit points    the same in both

So this is, in the main, a **damage** conversion. Defences and hit points
come off the stat block already and need nothing done to them.

Two tables describe the revision, and they disagree. `MM3` is the published
design formula. `FITTED` is a least-squares fit to the 154 MM3 rows in this
corpus -- what actually got printed. `scripts/mm3.py` puts them side by side
and is how the numbers get argued with using evidence.

`TO_MM3` uses the **fitted** one, and the reason is the recharge line: the
published `12 + level x 1.5` wants 27 damage at level 10 where the books
average 14. Converting an old monster on that formula would roughly double
every recharge attack in the game. `TO_MM3_PUBLISHED` is there for anyone
who wants the stated intent instead.

Nothing is converted unless asked for. The default is `AS_PRINTED`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .rng import average

#: What a damage expression is for. MM3 scales these differently: a
#: recharge power hits harder than an at-will, and a minion hits for half.
NORMAL = "normal"
LIMITED = "limited"
MINION = "minion"


@dataclass(frozen=True)
class Table:
    """One book's idea of what a monster's numbers should be.

    Only `damage` is consulted at the moment, because it is the only one the
    corpus says really moved. The rest are here because they are part of the
    same published claim and `scripts/mm3.py` reports on all of them -- when
    one of them earns its keep, it is already written down.
    """

    name: str
    #: Average damage a standard attack should do at this level.
    damage: object
    #: And a recharge or encounter attack.
    limited: object
    #: Attack bonus over level, by role. Reported, not yet applied.
    attack: dict[str, float] = field(default_factory=dict)
    #: Hit points as a multiple of a standard monster's, by rank.
    rank_hp: dict[str, float] = field(default_factory=dict)

    def target(self, level: int, kind: str, *, role: str = "") -> float:
        """What a `kind` of attack should average at this level.

        **`role` reaches the brute column**, which is the second of the two
        printed axes `#1010` lists and the only one this signature can
        carry. DMG2 p133 prints two damage columns, standard and brute, and
        `by_level.minion_damage` has taken `brute=` since it was written with
        nothing able to ask for it -- *"`Table.target` takes a three-valued
        `kind` with no notion of role"*, in its own words. Now it does.

        Keyword-only and defaulted, so `scripts/mm3.py` and every other
        caller keeps its meaning: no role is the standard column, which is
        what they were already getting.

        **The artillery rule is still out of reach and this is why.** *"Artillery
        minions deal 25% less damage on multitarget and melee attacks"* needs
        the role **and the shape of the attack**, and nothing on this path
        carries whether the attack is melee or multitarget. A third axis, not
        a third value -- left on `#1010`.

        **A minion reads a printed table rather than half this curve.** This
        used to be `out / 2`, which was quoting the book -- DMG2 prints
        *"Minion damage is roughly half of a standard creature's damage"* in
        the same paragraph as the table -- but "roughly" is doing real work:
        half the curve is a continuous line through a step function, so the
        error changes sign inside every band. Mean absolute difference 0.38
        over 30 levels, worst `+0.99` at level 9 against `-0.60` at level 10.

        So this follows `etl/CLAUDE.md`'s rule one layer up: never derive a
        number the page prints. `#1010`.
        """
        if kind == LIMITED:
            return float(self.limited(level))
        out = float(self.damage(level))
        if kind != MINION:
            return out
        # Imported here rather than at module level: `by_level` is below
        # every component and imports nothing, so either direction is safe,
        # but a module-level import in `engine/` widens an audit batch and
        # this file is reached by the whole corpus.
        from combat_engine.by_level import minion_damage

        try:
            return float(minion_damage(level, brute=role == "brute"))
        except ValueError:
            # Outside the printed bands. The old approximation is the honest
            # fallback -- it is what the book's own prose says -- rather than
            # clamping to the top band, which would under-deal silently.
            return out / 2


#: Attack bonus over level, by role, as published. Reported by
#: `scripts/mm3.py` rather than applied -- the corpus says the real gap is
#: about half a point, not two.
#:
#: **The vs-AC row, all six of them.** The printed table has two attack rows
#: and this used to mix them: five cells came off *attack vs. AC* and
#: `artillery` off *attack vs. other defenses*, which is 5 where the vs-AC
#: row says 7. Read from the book rather than corrected by pattern --
#:
#:     attack vs. ac              skirmisher +5  brute +3  soldier +7
#:                                lurker +5  controller +5  artillery +7
#:     attack vs. other defenses  +3  +1  +5  +3  +4  +5
#:
#: **It was not a typo, which is why it survived.** +5 is also artillery's
#: measured corpus figure (+5.1), so the wrong value sat beside a number
#: that appeared to confirm it, and `mm3.py` reported that role's
#: published-versus-measured gap as **zero** where it is about -1.9 -- the
#: same shape as soldier's -1.7. The one column whose job is to carry the
#: book's claim was silently agreeing with the corpus instead.
#:
#: Two printed oddities, both verified and neither to be smoothed: the
#: table's footnote is *"reduce the attack bonus by 2 for powers that affect
#: multiple creatures"*, and controller's vs-other value is **+4** where
#: every other role's second row is exactly 2 below its first. #973.
ATTACK_OLD = {
    "brute": 3, "soldier": 7, "artillery": 7,
    "lurker": 5, "skirmisher": 5, "controller": 5,
}  # fmt: skip
ATTACK_MM3 = dict.fromkeys(ATTACK_OLD, 5)


#: Monster Manual 1 and 2. Damage scaled poorly, which is the whole reason
#: the revision happened.
OLD = Table(
    name="MM1/MM2",
    damage=lambda level: 4 + level * 0.6,
    limited=lambda level: (4 + level * 0.6) * 1.25,
    attack=ATTACK_OLD,
    rank_hp={"standard": 1.0, "elite": 2.0, "solo": 5.0, "minion": 0.0},
)

#: Monster Manual 3 and the Monster Vault, as the design notes describe it.
MM3 = Table(
    name="MM3 (published)",
    damage=lambda level: 8 + level,
    limited=lambda level: 12 + level * 1.5,
    attack=ATTACK_MM3,
    rank_hp={"standard": 1.0, "elite": 2.0, "solo": 4.0, "minion": 0.0},
)

#: Monster Manual 3 as it was actually printed, fitted to the 154 MM3 rows
#: in this corpus by least squares. `scripts/mm3.py` is where the two are
#: put side by side.
#:
#: The standard-damage formula above runs two to three points hot across
#: heroic tier. The limited-damage one is not close: `12 + level x 1.5` says
#: 27 at level 10 and the books say 14, so converting an older monster with
#: it would roughly double every recharge attack in the game. That is the
#: reason this table exists and is the one `TO_MM3` uses.
FITTED = Table(
    name="MM3 (as printed)",
    damage=lambda level: 6.6 + 0.82 * level,
    limited=lambda level: 9.1 + 0.61 * level,
    attack=ATTACK_MM3,
    rank_hp={"standard": 1.0, "elite": 2.0, "solo": 3.4, "minion": 0.0},
)

BOOKS = {"MM1": OLD, "MM2": OLD, "MM3": FITTED, "": OLD}


@dataclass(frozen=True)
class Math:
    """Which maths a fight is played under."""

    name: str
    #: None leaves every row exactly as its book printed it.
    to: Table | None = None

    @property
    def on(self) -> bool:
        return self.to is not None

    def convert(
        self, expr: str, *, book: str, level: int, kind: str = NORMAL,
        role: str = "",
    ) -> str:
        """Rescale a printed damage expression to the target maths.

        The shape of the expression is kept and its size is changed: `2d8+2`
        stays two eight-sided dice and gains a flat bonus. Keeping the dice
        keeps the spread -- a brute that swings wildly goes on swinging
        wildly -- and moving the flat part is what the revision did anyway.
        """
        if self.to is None:
            return expr
        source = BOOKS.get(book, OLD)
        if source is self.to:
            return expr
        want = self.to.target(level, kind, role=role)
        have = average(expr)
        if have <= 0:
            return expr
        return _retune(expr, want - have)

    def describe(self) -> str:
        return self.name


#: As written. Every monster keeps the numbers its book gave it.
AS_PRINTED = Math("as printed")

#: MM1 and MM2 rows rescaled to the MM3 curve the books actually show.
TO_MM3 = Math("MM3 damage", FITTED)

#: The same, on the published design formula. Hits appreciably harder,
#: especially for recharge attacks. Kept because it is somebody's stated
#: intent and worth being able to play.
TO_MM3_PUBLISHED = Math("MM3 damage (published formula)", MM3)

PRESETS = {
    "printed": AS_PRINTED,
    "mm3": TO_MM3,
    "mm3-published": TO_MM3_PUBLISHED,
}

_DICE = re.compile(r"^\s*(\d*)d(\d+)\s*(?:([+-])\s*(\d+))?\s*$", re.I)


def _retune(expr: str, delta: float) -> str:
    """Shift a dice expression's flat part by `delta`, keeping the dice."""
    m = _DICE.match(expr)
    if not m:
        return expr
    count = int(m.group(1) or 1)
    faces = int(m.group(2))
    flat = int(m.group(4) or 0) * (-1 if m.group(3) == "-" else 1)
    flat = max(0, round(flat + delta))
    return f"{count}d{faces}" + (f"+{flat}" if flat else "")


#: Hit points a monster gains per level, by role. DMG p.184, the
#: "Monster Statistics by Role" table, read off the page.
#:
#: Verified against the printing rather than transcribed from an issue --
#: the AC and other-defence columns on the same table came out exactly as
#: the book has them (`level + 14` for a skirmisher, `+ 16` for a soldier,
#: `+ 12` for the other defences of every role), which is what says this
#: column was read correctly too.
#:
#: **Only the per-level figure is here**, because that is all a level
#: *adjustment* needs. The baselines belong to whoever creates a monster
#: from scratch, and this engine never does -- every creature comes off a
#: printed page with its numbers already on it.
HP_PER_LEVEL: dict[str, int] = {
    "brute": 10,
    "skirmisher": 8,
    "soldier": 8,
    "controller": 8,
    "lurker": 6,
    "artillery": 6,
}

#: The book's own ceiling on this operation, and therefore the code's.
#:
#:     "This process works best for adjusting a monster's level up to five
#:      higher or lower. Beyond that, the monster changes so much that
#:      you'd do better to start with another creature of the desired role
#:      and level range."
#:
#: So beyond five this refuses rather than clamping: "start with another
#: creature" is a decision for the caller that picks creatures, and
#: clamping would silently field a creature five levels out while
#: reporting it had been fitted.
LEVEL_REACH = 5


def adjust_level(world: object, eid: int, by: int) -> bool:
    """Move a spawned creature's level by `by`, the way the DMG says. #972

        "Just increase its attack rolls, defenses, and AC by 1 for every
         level you add. For every two levels, increase the damage it deals
         with its attacks by 1. The monster also gains extra hit points at
         each level, based on its role."

        "Decreasing a monster's level works like increasing it, but in
         reverse."

    Returns True when it was applied, False when it refused -- which is the
    answer a caller needs, because the printed alternative to a refusal is
    to go and pick a different creature.

    **Modifiers, not rewritten numbers.** A monster's attack bonus and
    defences are not fields on the creature: `query.defence` reads
    `Defenses.base` plus a level term plus `Mods`, and the attack bonus is
    in each row's own header. So the adjustment is three standing `Mod`s and
    one change to `Health`, which also means `scripts/show.py` and the wire
    can report *why* a number moved rather than finding it mysteriously
    different from the page.

    **Untyped, so it stacks with everything and with nothing twice.** `Mods`
    buckets typed bonuses by kind and takes the larger; a level adjustment
    is not a printed bonus of any type, and two adjustments of the same
    creature would be a caller error rather than something to silently take
    the max of. The label carries the delta so a second call is visible.

    Three things it deliberately does not touch:

    * **the level itself**, because nothing stores a spawned creature's
      level as mutable state -- `stats.level` comes off the stat block, and
      `world.scaling`'s level term reads it. Changing the numbers is what
      the printed rule says to do, and is what every reader of those
      numbers will see;
    * **XP**, which is a budget question the story side prices (`#962`);
    * **the damage expression**, where `Math.convert` rewrites dice. The
      printed adjustment is a flat `+1 per two levels`, so it is a damage
      modifier rather than a retune -- and `_retune` moves the flat part of
      an expression, which would double-count against a `Mod`.
    """
    from .components import Health, Mod, Mods
    from .query import stat_block
    from .types import DEFENCES

    if by == 0 or abs(by) > LEVEL_REACH:
        return False
    row = stat_block(world, eid)
    role = str((row or {}).get("role") or "").strip().lower()
    per_level = HP_PER_LEVEL.get(role)
    if per_level is None:
        # **A role this table does not name gets nothing**, rather than a
        # guessed 8. The table has six roles; a creature whose role column
        # is empty or says something else -- a minion template, a hazard --
        # has no printed hp-per-level, and inventing one is the thing
        # `etl/CLAUDE.md` forbids one layer down.
        return False

    mods = world.get(eid, Mods)
    if mods is None:
        return False
    label = f"level{by:+d}"
    mods.items.append(Mod(what="attack", value=by, kind="untyped", label=label))
    for d in DEFENCES:
        mods.items.append(
            Mod(what=d.value, value=by, kind="untyped", label=label))
    # **Toward zero, both ways.** "For every two levels" means a three-level
    # boost is +1 and not +1.5, and a three-level drop is -1. `int()` on a
    # negative quotient would floor to -2, so the halving is done on the
    # magnitude and the sign put back.
    damage = (abs(by) // 2) * (1 if by > 0 else -1)
    if damage:
        mods.items.append(
            Mod(what="damage", value=damage, kind="untyped", label=label))

    health = world.get(eid, Health)
    if health is not None:
        gained = per_level * by
        # A drop may not take a creature to nothing: one hit point is the
        # floor `loader.spawn` already uses for a printed hp of zero.
        health.max_hp = max(1, health.max_hp + gained)
        health.hp = max(1, min(health.hp + gained, health.max_hp))
    return True
