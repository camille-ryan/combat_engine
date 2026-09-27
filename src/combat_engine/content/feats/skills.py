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
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
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
_narrative("f2562", "A bonus to every untrained check.")
_narrative("f3103", "A bonus to one social skill.")
_narrative("f2913", "A social bonus, and that skill read off a different ability.")
_narrative("f1062", "Perception, and checks made to avoid becoming lost.")
_narrative("f1258", "Rolling one skill twice.")
_narrative("f1271", "A bonus to one skill, larger when an ally helps.")
_narrative("f1284", "Training, and creating a diversion faster.")
_narrative("f1412", "Perception against a creature trying to hide.")
_narrative("f1528", "Which domain feats may be taken, and a knowledge bonus.")
_narrative("f1700", "Two athletic bonuses, and a ritual performed unaided.")
_narrative("f1785", "Hiding as a free action on turning invisible.")
_narrative("f1824", "A nature bonus, and reading beasts with it.")
_narrative("f1838", "Treating disease, and a ritual performed unaided.")
_narrative("f1840", "Rolling either of two skills twice.")
_narrative("f1844", "Knowing north, and rolling twice to find a way.")
_narrative("f1981", "A social bonus after a successful deception.")
_narrative("f1984", "Rerolling a check made against a trap.")
_narrative("f1989", "Two bonuses against one kind of creature.")
_narrative("f1349", "Reading a die's result as its average.")
_narrative("f1139", "Applying one power's bonus to a different social skill.")


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
       reach=PERSONAL, target=SELF, dropped=("c.low_light()",))
def f194(c: Cast) -> None:
    """The Perception half is narrative. Low-light vision is not -- it
    decides what a creature can see and therefore what it can attack --
    and there is no verb for it: `c.see_invisible` and `c.blindsight`
    exist, this does not."""


@power("f1864", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1864(c: Cast) -> None:
    """A social bonus that scales with the armour's enhancement bonus.
    Still only a skill, so still narrative -- but worth saying out loud
    that the *number* is a real one, read from a real column, and the
    row is inert because of where it lands rather than where it comes
    from."""


@power("f1075", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.silvered()",))
def f1075(c: Cast) -> None:
    """Rolling an Endurance check twice is narrative. Treating a weapon
    as silvered is not -- silver is what some creatures' resistances are
    written against -- and `Weapon` has no such property. One item block
    in the weapon slot wants the same symbol."""
