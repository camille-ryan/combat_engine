"""Psion, level 0: the class features.

None of the six prints an Augment line, so the rule the rest of the class
follows -- write Augment 0, name the dropped clauses -- has nothing to do
here. Three of them move objects, conjure objects or send a sentence, and
carry `out_of_combat=True` rather than an invented combat effect.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    STANDARD,
    Cast,
    CloseBurst,
    Keyword,
    Ranged,
    When,
    power,
)

PSIONIC = [Keyword.PSIONIC]
PSIONIC_CONJURATION = [Keyword.PSIONIC, Keyword.CONJURATION]


@power(
    "p11267",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p11267(c: Cast) -> None:
    """The target is an object of twenty pounds or less, and the engine has
    no objects -- only creatures, conjurations and squares. Everything the
    row does is done to one."""
    c.note(f"{c.ref}: lifts and moves a small object, and keeps it aloft")


@power(
    "p11268",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC,
)
def p11268(c: Cast) -> None:
    """"But not into hindering terrain" is a constraint on the destination
    and the destination is the decider's: `to=` names one square outright,
    which is a different sentence. Named in the report."""
    c.slide(3 if c.level >= 21 else 2 if c.level >= 11 else 1)


@power(
    "p13300",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=PSIONIC_CONJURATION,
)
def p13300(c: Cast) -> None:
    """"The fragment occupies its square, and you and your allies can move
    through it" is the printed opt-in to `solid=True`: a conjuration lets
    everybody through by default, and this one only lets a side through.
    The engine's solidity has no side, so enemies and allies are both
    stopped; the allied half is the loss and is named in the report.

    "You can see, hear and use psion powers as if you were in its space" is
    `from_=` on one attack at a time, not a standing property, so it is not
    written. Nor is "if it takes any damage it disappears": nothing takes a
    conjuration off the board early.
    """
    c.conjure(
        label=c.ref,
        until=When.ENCOUNTER,
        sustain=None,
        speed=c.speed_of(),
        solid=True,
    )


@power(
    "p13301",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=PSIONIC_CONJURATION,
    out_of_combat=True,
)
def p13301(c: Cast) -> None:
    """A weapon or a piece of adventuring gear. `Gear` is set at build time
    and the object here is equipment rather than anything on the board."""
    c.note(f"{c.ref}: conjures one mundane object, no larger than a person carries")


@power(
    "p8224",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC,
)
def p8224(c: Cast) -> None:
    """"The next creature that attacks it" is anybody at all; the relation
    names one beneficiary each, so `to="allies"` is as wide as it goes.
    `once=True` is the "next" part.

    The level lines widen the target to two and then three creatures. The
    header's count is a number, not a function of level, so the base is
    written and the widening is named in the report.
    """
    c.grants_advantage(until=When.EONT, to="allies", once=True)


@power(
    "p8225",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=PSIONIC,
    out_of_combat=True,
)
def p8225(c: Cast) -> None:
    """Twenty-five words, and a reply. There is no combat effect at all."""
    c.note(f"{c.ref}: sends a silent message, and hears one back")
