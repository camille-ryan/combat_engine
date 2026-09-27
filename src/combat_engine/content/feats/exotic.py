"""The exotic weapon chains: a proficiency feat and three powers each.

Every one of these is printed the same way. One feat grants proficiency
with a weapon and a rider on hitting with it; three more each "swap a
power you know" for a named card. The swap is 4e's retraining and means
"you have this power instead", so the parent is a plain `c.grant_row`
and the card beside it is an ordinary attack row.

**None of them carry a marker, and every one of them will report
UNUSED.** That is correct and is worth stating plainly, because the two
look alike from the summary line. The rows are complete: the attack, the
damage, the condition and the Requirement are all written. What is
missing is the *weapon* -- `chargen` deals sixteen and none of them is a
bola, a net or a whip -- so the Requirement is false for every character
the engine can currently build.

That is a chassis gap rather than a row gap, so it is tracked once as an
issue rather than marked on twelve rows. A `todo=` here would be a lie in
the other direction: it would say the engine cannot express these, and it
plainly can.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    Ability,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    When,
    power,
)
from combat_engine.engine.query import holding

WEAPON = [Keyword.WEAPON]


def _hit_with(what: str):  # noqa: ANN202
    """A hit landed with one named weapon, for a feat's own rider."""

    def when(world, me: int, ev) -> bool:  # noqa: ANN001
        return ev.attacker == me and bool(holding(world, me, what))

    return when


_hit_with_a_net = _hit_with("net")
_hit_with_a_whip = _hit_with("whip")


def _wielding(what: str):  # noqa: ANN202
    """A printed Requirement naming one weapon.

    False for every character `chargen` can build today, because it deals
    no such weapon -- which is why every row using this reports UNUSED
    rather than silent.
    """

    def gate(world, eid: int) -> bool:  # noqa: ANN001
        return bool(holding(world, eid, what))

    return gate


def _swap(ref: str, card: str):  # noqa: ANN202
    """"You can swap a power you know for X" -- you have X instead."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card} in place of a power of that level."
    return parent


# -- the bola ---------------------------------------------------------------


@power("f959", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.forgo_damage()",),
       proficiency=("w:bola",))
def f959(c: Cast) -> None:
    """The weapon exists now and `chargen` deals it. What is left is the
    shape of the rider: the immobilise is bought by giving the damage up,
    and the critical's knockdown rides inside that same choice, so
    neither half can be laid without the trade."""


_swap("f960", "f960b")


@power("f960b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Ranged(10, by_weapon=True), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
       requires=_wielding("bola"), requires_text="you must be wielding a bola")
def f960b(c: Cast) -> None:
    """The 11th and 21st steps are out of scope."""
    if c.strike().hit:
        c.damage(c.w(2), c.dex_mod)
        c.condition(Condition.IMMOBILIZED, until=When.EONT)
        if c.crit:
            c.prone()


_swap("f961", "f961b")


@power("f961b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def f961b(c: Cast) -> None:
    """Regain the use of the other card in the chain."""
    c.restore_use("f960b")


_swap("f962", "f962b")


@power("f962b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Ranged(10, by_weapon=True), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
       requires=_wielding("bola"), requires_text="you must be wielding a bola")
def f962b(c: Cast) -> None:
    """"Knocked prone and cannot stand" is prone plus the rooted-to-the-
    floor half, which is what `Condition.PINNED` says."""
    if c.strike().hit:
        c.damage(c.w(2), c.dex_mod + c.str_mod)
        c.prone()
        c.condition(Condition.PINNED, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.dex_mod + c.str_mod)
        c.prone()
        c.condition(Condition.PINNED, until=When.EONT)


# -- the net ----------------------------------------------------------------


@power("f963", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a weapon attack using a net",
       on=Trigger(Hit, _hit_with_a_net, "you hit with a net"),
       proficiency=("w:net",))
def f963(c: Cast) -> None:
    """Both halves. `AT_WILL` because the card prints no limit, and an
    encounter budget on "when you hit" would spend the feat on the first
    blow of the fight."""
    c.condition(Condition.SLOWED, on=c.trigger.target, until=When.EONT)


_swap("f964", "f964b")


@power("f964b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=CloseBurst(1), target=EACH_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.STR, vs=FORT),
       requires=_wielding("net"), requires_text="you must be wielding a net")
def f964b(c: Cast) -> None:
    if c.strike().hit:
        c.damage(c.w(1), c.str_mod)
        c.condition(Condition.SLOWED, until=When.EONT)
        c.penalty("attack", 2, until=When.EONT)


_swap("f965", "f965b")


@power("f965b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=WEAPON,
       requires=_wielding("net"), requires_text="you must be wielding a net")
def f965b(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.EONT, kind="power")
    c.bonus(REF, 2, on=c.me, until=When.EONT, kind="power")


_swap("f966", "f966b")


@power("f966b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(5), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.STR, vs=REF),
       requires=_wielding("net"), requires_text="you must be wielding a net")
def f966b(c: Cast) -> None:
    """Reach 5 whatever the weapon says, which the header carries rather
    than the body -- `Melee(5)` is the printed Special line."""
    if c.strike().hit:
        c.damage(c.w(1), c.str_mod)
        c.grab()
        c.penalty("attack", 5)
    else:
        c.half_damage(c.w(1), c.str_mod)
        c.condition(Condition.IMMOBILIZED, until=When.EONT)


# -- the whip ---------------------------------------------------------------


@power("f967", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit a target with a whip",
       on=Trigger(Hit, _hit_with_a_whip, "you hit with a whip"),
       once_per_round=True, dropped=("c.penalty(against=)",))
def f967(c: Cast) -> None:
    """The penalty plays and "once per round" is the header's own field.

    Dropped: "against a target of your choice". A penalty is laid on the
    creature taking it and nothing narrows one to the attacks it makes
    against one particular enemy, so this is the whole of its attack
    rolls -- wider than the card, and said so rather than left silent."""
    c.penalty("attack", 2, on=c.trigger.target, until=When.EONT)


_swap("f968", "f968b")


@power("f968b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(2), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
       requires=_wielding("whip"), requires_text="you must be wielding a whip")
def f968b(c: Cast) -> None:
    """"Knock prone **or** pull 1" is a choice, and the scorer has no way
    to weigh one against the other -- prone is taken, because it costs the
    target its whole move to undo and a single square does not."""
    if c.strike().hit:
        c.damage(c.w(2), c.dex_mod)
        c.prone()
