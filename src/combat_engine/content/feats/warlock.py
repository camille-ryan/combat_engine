"""Warlock feats.

The curse is `cf:warlock-f4` and it is named by ref in three of these
prerequisites, so "an enemy cursed by you" is a real question --
`Relation.CURSED_BY` holds it and `cursed_by_me` is already a predicate.
That is what makes half this list writable.

The other half rides on a pact feature -- one per pact, four pacts --
and each is named in prose with no ref, which is what the opaque term
in their own prerequisites records from the other side.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Relation,
    When,
    power,
)

FEATURE = ("c.class_feature()",)


def _cursed_by(c: Cast, who: int | None) -> bool:
    return who is not None and c.world.relations.holds(
        Relation.CURSED_BY, c.me, who
    )


@power("f435", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f435(c: Cast) -> None:
    """Combat advantage against bloodied enemies you have cursed. Asked
    per attack rather than at arming: both halves change during a fight,
    and a curse moves from creature to creature."""
    me = c.me
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            _cursed_by(c, ctx.get("target"))
            and c.bloodied(on=ctx.get("target"))
        ),
    )


@power("f1112", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.curse(stack=)",))
def f1112(c: Cast) -> None:
    """The second half -- combat advantage against anything carrying more
    than one curse -- needs to count curses from different casters, and
    the relation table answers "is it cursed by *me*" and not "by how
    many". The first half, cursing what somebody else has cursed, is a
    restriction `c.curse` does not impose, so there is nothing to lift."""
    me = c.me
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: _cursed_by(c, ctx.get("target")),
    )


@power("f746", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f746(c: Cast) -> None:
    """Radiant resistance while concealed. `c.resist` takes a gate and
    the damage context carries the type, so both halves are sayable."""
    from combat_engine.engine.query import concealment_of
    from combat_engine.engine.types import DamageType

    me = c.me
    c.resist(
        5 + c.stats.level // 2, DamageType.RADIANT, on=me,
        until=When.ENCOUNTER,
        when=lambda ctx: concealment_of(c.world, me, ctx) > 0,
    )


@power("f745", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_damage_dealt()",))
def f745(c: Cast) -> None:
    """A saving throw whenever you *deal* damage with a power of two
    keywords. `DamageApplied` names the source, but the keyword belongs
    to the power and the row needs both at once with nothing announcing
    the pair."""


@power("f744", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_miss_all()",))
def f744(c: Cast) -> None:
    """Recover an encounter power by hurting yourself when it misses
    every target. `Miss` is announced per target and nothing says a use
    missed them all."""


@power("f695", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.curse(nearest=False)",))
def f695(c: Cast) -> None:
    """Lifts the nearest-enemy restriction on the curse, as a reaction.
    `c.curse` imposes no such restriction, so there is nothing to lift
    and the reaction has no printed effect of its own."""


def _feature(ref: str, what: str) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=FEATURE)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} The feature is named in prose with no ref."


def _boon(ref: str, what: str) -> None:
    """A pact boon, raised or lengthened from outside the row that pays it.

    Both legs have refs now and both are declared: the prerequisites name
    `cf:warlock-f1s5` and `cf:warlock-f1s2`, the first pays through
    `cf:warlock-f1c10` and the second through `cf:warlock-f1`'s own
    `Dropped` watch. Neither number is reachable -- one is an argument to
    `c.bonus` inside a card, the other a literal inside a closure -- and
    that is `c.on_pact_boon()`, which nine rows already name. It is not
    the feature, and it never was.
    """
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=("c.on_pact_boon()",))
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} {_boon.__doc__}"


_boon("f292", "Raises a pact boon's bonus to a d20 roll.")
_boon("f293", "Lengthens a pact boon's teleport.")


@power("f291", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_use(p2095)",))
def f291(c: Cast) -> None:
    """Raises the temporary hit points one named power pays. The power
    *is* named by ref -- what is missing is a way to add to what another
    row grants after it has granted it."""
