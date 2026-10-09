"""Feats whose benefit is a skill and nothing else.

`out_of_combat=True` with an empty body is a **finished** row, not a
skipped one -- `docs/AUTHORING.md` names lighting a lamp as the example
-- and a hundred-odd heroic feats are exactly that: a bonus to a check,
training in a skill, rolling a check twice.

Every one of these was read rather than matched. That matters more here
than anywhere else in the corpus, because the family is full of rows
that *look* like skill feats and are not: one adds a bonus to
**initiative** beside two skills, one adds **saving throws against
charm**, one reads an armour's enhancement bonus. Those are written
properly below rather than waved through, and a regex over the word
"checks" would have made all three silently inert.

**Which skills a fight actually rolls, since the whole file turns on
it.** `engine/skills.py` reads `skill:<name>` off `Mods` for any check
anybody makes, and a blanket `skill` key for every check at once -- so
a bonus is only inert when nothing ever rolls the skill. Sweeping the
tree for `c.check` and `c.passive`, five skills are rolled in combat
and the rest are not: **Stealth** (going unseen, in the rogue's and the
ranger's features, three racial powers and an item), **Perception**
(passively, as the number Stealth is rolled against), **Bluff** (the
feint, rolled against passive **Insight**) and **Intimidate**. So the
five rows below that raise one of those lay a real modifier; the ones
that raise Athletics-to-climb, Streetwise, Thievery or a knowledge
skill are inert and say so.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Gear,
    SkillCheck,
    When,
    power,
)


def _narrative(ref: str, what: str) -> None:
    """A row with no combat consequence, declared rather than forgotten."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, out_of_combat=True)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = what


_narrative("f441", "A bonus to six knowledge skills.")
_narrative("f2562", "A bonus to every untrained check; there is no training model.")
_narrative("f1258", "Rolling one skill twice.")
_narrative("f1271", "A bonus to one skill, larger when an ally helps.")
_narrative("f1528", "Which domain feats may be taken, and a knowledge bonus.")
_narrative("f1700", "Two athletic bonuses, and a ritual performed unaided.")
_narrative("f1824", "A nature bonus, and reading beasts with it.")
_narrative("f1838", "Treating disease, and a ritual performed unaided.")
_narrative("f1840", "Rolling either of two skills twice.")
_narrative("f1844", "Knowing north, and rolling twice to find a way.")
_narrative("f1984", "Rerolling a check made against a trap.")
_narrative("f1349", "Reading a die's result as its average.")
_narrative("f1139", "Applying one power's bonus to a different social skill.")


def _skill(ref: str, skill: str, amount: int, why: str) -> None:
    """A bonus to a skill a fight really rolls, so a real modifier.

    `kind="feat"` is written out rather than passed in, and a card that
    prints no type word gets its own row rather than an argument here.
    `scripts/bonuses.py` reads the `kind=` out of the **source**, so a
    variable is invisible to it -- parameterising this helper made four
    correct rows report as omitting a type they plainly name.
    """

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF)
    def feat(c: Cast) -> None:
        c.bonus(f"skill:{skill}", amount, on=c.me, until=When.ENCOUNTER,
                kind="feat")

    feat.__name__ = ref
    feat.__doc__ = why


_skill("f3103", "intimidate", 4, "Intimidate, which the feint and three "
       "racial powers roll.")
_skill("f1062", "perception", 3,
       "Perception, which is what a hidden creature is measured against. "
       "The other half -- checks made to avoid becoming lost -- is "
       "narrative and stays where the rest of this file leaves it.")
_skill("f1412", "perception", 5,
       "Perception narrowed to checks opposed by a Stealth check, which "
       "in this engine is what every Perception question is: `c.passive` "
       "against somebody hiding, and nothing else asks. So the narrowing "
       "costs nothing and the number is laid whole.")
@power("f1989", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1989(c: Cast) -> None:
    """Perception and Insight, both narrowed to one kind of creature.

    Not written through `_skill`, because this card prints "+5 bonus"
    with no type word where the others print "+5 feat bonus", and the
    kind is the word the card prints and nothing else.

    The skill context carries `actor` and `skill` and nothing about who
    is being looked at, so the narrowing cannot be said -- and the
    Insight half is a passive number nothing would read it through. The
    Perception half is laid.
    """
    c.bonus("skill:perception", 5, on=c.me, until=When.ENCOUNTER)


@power("f2913", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2913(c: Cast) -> None:
    """Intimidate, and that skill read off Strength instead of Charisma.

    Both halves are one key. `skills.modifier` adds the skill's own
    ability modifier and then whatever is standing, so "use Strength in
    place of Charisma" is the difference between the two -- exact, not
    an approximation. A printed **can**, so it is taken only when it is
    an improvement.
    """
    c.bonus("skill:intimidate", 2, on=c.me, until=When.ENCOUNTER, kind="feat")
    if c.str_mod > c.cha_mod:
        c.bonus("skill:intimidate", c.str_mod - c.cha_mod, on=c.me,
                until=When.ENCOUNTER)


@power("f1284", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1284(c: Cast) -> None:
    """Training in Stealth, and creating a diversion faster.

    Both halves land outside what the engine has. There is no training
    model -- `engine/skills.py` says so and applies no +5 -- and no
    diversion action to make a minor one of, so neither is a number
    anything would read.
    """


@power("f1785", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_invisible()",))
def f1785(c: Cast) -> None:
    """A free Stealth check to hide whenever you turn invisible.

    Hiding is real -- rolled against the watchers' passive Perception in
    five places in the tree -- so this is not a narrative row. What is
    missing is the moment. `c.hide` *is* `c.invisible`: it calls it, on
    the same `HIDDEN_FROM` relation with the same `f"{ref} unseen"`
    label, so the one event announcing either cannot say which happened
    -- and a row that fired on hiding would answer by hiding again.
    """


@power("f1981", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1981(c: Cast) -> None:
    """A successful Bluff feeds the next Intimidate.

    Not a narrative row, though it reads like one: the feint rolls
    Bluff in four places in the tree and Intimidate in three more, and
    `SkillCheck` carries `success`, settled in the resolve callback --
    so the `Window.AFTER` this trait watches in sees a finished check.
    The Diplomacy half of "Diplomacy or Intimidate" is laid beside it;
    nothing rolls it in a fight, and leaving it out would make the row
    disagree with the card for no gain.
    """
    me = c.me

    def bluffed(ev: Any) -> None:
        if ev.actor != me or ev.skill != "bluff" or not ev.success:
            return
        for skill in ("diplomacy", "intimidate"):
            c.bonus(f"skill:{skill}", 3, on=me, until=When.ENCOUNTER,
                    once=True)

    c.watch(SkillCheck, bluffed, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} after a bluff")


@power("f3526", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3526(c: Cast) -> None:
    """**Not an out-of-combat row**, though two thirds of it is. The two
    skills have no consequence in a fight and the third number is
    initiative, which decides who goes first -- so the row is written
    for that and the skills are left where every other skill bonus in
    this file is left."""
    c.initiative(2, on=c.me)


@power("f1072", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1072(c: Cast) -> None:
    """Same shape as f3526: a knowledge bonus that does not matter here,
    and a saving throw bonus against one family of effects that does.
    The narrowing reads the effect's label, which the saving throw's
    context now carries."""
    c.bonus(
        "save", 2, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: "charm" in str(ctx.get("label", "")).lower(),
    )


@power("f194", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f194(c: Cast) -> None:
    """Low-light vision is the benefit: it decides what a creature can see
    and therefore what it can attack. The Perception half is a +1 that no
    roll in a fight is close enough for to matter, and is laid nowhere.

    This was `todo=` rather than `dropped=` precisely because nothing in the
    body landed -- a `dropped=` row would have been offered in play and done
    nothing. It lands now."""
    c.low_light()


@power("f1864", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1864(c: Cast) -> None:
    """A real Intimidate bonus, and the number is read rather than
    guessed: 1 plus the worn armour's enhancement.

    Found by what the magic *does* -- `Magic.enh_to` is `ac` or
    `defences` for a suit of armour and `attack_damage` for a weapon --
    rather than by a slot name, which is a string out of `game.db` that
    a content file should not be spelling. `c.enhancement` is the wrong
    reader here too: it finds the plus of the item *this row belongs
    to*, and this row belongs to no item.
    """
    gear = c.world.get(c.me, Gear)
    worn = [
        m for m in (gear.worn.values() if gear else ())
        if m.enh_to in ("ac", "defences")
    ]
    c.bonus("skill:intimidate", 1 + max((m.plus for m in worn), default=0),
            on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f1075", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("compendium.silvered",))
def f1075(c: Cast) -> None:
    """Rolling an Endurance check twice is narrative. Treating a weapon
    as silvered is not -- silver is what some creatures' resistances are
    written against -- and `Weapon` has no such property. Nine rows want
    the symbol, one of them an item block in the weapon slot.

    **`todo`, not `dropped`**, for f194's reason: neither half of the
    card leaves anything behind, so a row that played would be a row
    that did nothing.
    """
