"""Artificer: the four dailies that enchant something somebody is holding.

A weapon is not an entity here, and for these four it does not need to be.
"Any attack that uses the target as a weapon or an implement" has to be
answered at the moment damage is rolled, and the damage context carries the
row's ref and nothing about what was swung -- so even with a weapon to point
at, the question would still be put to the *row*. It is, the way
`with_keyword` puts every other artificer rider, and the enchantment is hung
on the creature holding the thing. `p1406` and `p11619` decided this for the
cleric first and these follow them.

Exact for a creature wielding one thing and generous for a creature wielding
two, which a `Target` side of its own would not have fixed: the gap is in
the damage context rather than in the target line.

All four print the same second sentence -- the wielder may end the
enchantment early to get one more thing out of it. That is a real choice and
is offered as one, with **keeping** the daily as the answer a fight nobody is
playing gives: the decider takes the first option, and cashing a daily's
whole duration in on the first hit is not what a player would do unprompted.
"""

from __future__ import annotations

from collections.abc import Iterable

from combat_engine.engine import (
    AC,
    DAILY,
    MINOR,
    Cast,
    DamageRolled,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    Target,
    When,
    get,
    power,
)

from . import with_keyword

#: The printed target line, over a pool of the creatures that could be
#: holding one. The label is what a card renders; the side is what the
#: engine aims at, and the gap between them is the module docstring.
_WEAPON_OR_IMPLEMENT = Target("ally", 1, label="One weapon or implement")
_WEAPON = Target("ally", 1, label="One weapon")


def _uses_it(ref: str, *words: Keyword) -> bool:
    """Was that attack one the enchantment rides on?

    The event carries the row's id and the row carries the keywords, which
    is the same lookup `with_keyword` does for a modifier -- written twice
    because one is handed a context dict and the other an event.
    """
    row = get(ref) if ref else None
    return row is not None and any(w in row.keywords for w in words)


def _spent(c: Cast, wielder: int, holds: Iterable[Effect | None], what: str) -> bool:
    """The free action all four print: end the enchantment for one more thing.

    Every hold the row laid goes, not just the one that noticed -- `p7656`
    lays two and ending half of it would leave the enchantment running
    after the card says it is over.
    """
    live = [e for e in holds if e is not None and not e.ended]
    if not live or not c.may(what, who=wielder, default=False):
        return False
    for eff in live:
        c.world.effects.end(eff, f"{c.ref} spent")
    return True


@power(
    "p7639",
    level=1,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=_WEAPON_OR_IMPLEMENT,
    keywords=[Keyword.ARCANE, Keyword.COLD],
)
def p7639(c: Cast) -> None:
    """Extra *cold* damage rather than a damage bonus: the type is what the
    line is for, and `c.bonus("damage", ...)` folds into whatever the attack
    already deals. The price of a separate packet is that it is dealt by the
    artificer rather than by the wielder."""
    wielder = c.target
    if wielder is None:
        return
    cold = c.con_mod
    holds: list[Effect | None] = []

    def bites(ev: Hit) -> None:
        if ev.attacker != wielder or not _uses_it(
            ev.power, Keyword.WEAPON, Keyword.IMPLEMENT
        ):
            return
        c.flat(cold, dtype=DamageType.COLD, on=ev.target)
        if _spent(c, wielder, holds, "end the enchantment to hold that creature"):
            c.immobilized(on=ev.target, until=When.SAVE_ENDS)

    holds.append(c.watch(Hit, bites, until=When.ENCOUNTER, on=wielder, label=c.ref))


@power(
    "p7649",
    level=5,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=_WEAPON,
    keywords=[Keyword.ACID, Keyword.ARCANE],
)
def p7649(c: Cast) -> None:
    """A weapon and not an implement, where the other three say either -- so
    the gate is the same one short a keyword."""
    wielder = c.target
    if wielder is None:
        return
    softened = c.con_mod
    holds: list[Effect | None] = []

    def burns(ev: Hit) -> None:
        if ev.attacker != wielder or not _uses_it(ev.power, Keyword.WEAPON):
            return
        c.ongoing(5, DamageType.ACID, on=ev.target, until=When.SAVE_ENDS)
        if _spent(c, wielder, holds, "end the enchantment to soften that creature"):
            c.penalty(AC, softened, on=ev.target, until=When.SAVE_ENDS)

    holds.append(c.watch(Hit, burns, until=When.ENCOUNTER, on=wielder, label=c.ref))


@power(
    "p7656",
    level=9,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=_WEAPON_OR_IMPLEMENT,
    keywords=[Keyword.ARCANE, Keyword.HEALING, Keyword.RADIANT],
)
def p7656(c: Cast) -> None:
    """"Deals radiant damage" recolours the attack rather than adding to it,
    which is the damage type on the roll: `DamageRolled` carries a mutable
    one and the resolver reads it back off the event. Two holds, because the
    recolouring and the healing answer different moments, and ending the
    enchantment has to take both."""
    wielder = c.target
    if wielder is None:
        return
    con = c.con_mod
    holds: list[Effect | None] = []

    def recolour(ev: DamageRolled) -> None:
        if ev.source == wielder and _uses_it(
            ev.detail, Keyword.WEAPON, Keyword.IMPLEMENT
        ):
            ev.dtype = DamageType.RADIANT

    def mends(ev: Hit) -> None:
        if ev.attacker != wielder or not _uses_it(
            ev.power, Keyword.WEAPON, Keyword.IMPLEMENT
        ):
            return
        c.heal(con, on=wielder)
        if not _spent(c, wielder, holds, "end the enchantment to daze that creature"):
            return
        c.dazed(on=ev.target, until=When.SAVE_ENDS)
        if c.may("spend a healing surge", who=wielder):
            c.surge(on=wielder, bonus=con)

    holds.append(
        c.watch(DamageRolled, recolour, until=When.ENCOUNTER, on=wielder, label=c.ref)
    )
    holds.append(c.watch(Hit, mends, until=When.ENCOUNTER, on=wielder, label=c.ref))


@power(
    "p7659",
    level=10,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=_WEAPON_OR_IMPLEMENT,
    keywords=[Keyword.ARCANE],
)
def p7659(c: Cast) -> None:
    """The minor action is put in the wielder's hands rather than watched
    for: `c.give` is a one-shot somebody else spends on their own turn, which
    is what "the target's wielder can end the effect" is. Nothing is spent
    when there is nothing to shake off -- the ending is the price of the
    removal, so with no removal to buy there is no reason to pay it."""
    wielder = c.target
    if wielder is None:
        return
    rides_on = with_keyword(Keyword.WEAPON, Keyword.IMPLEMENT)
    holds = [
        c.bonus(
            "attack", 1, on=wielder, until=When.ENCOUNTER, kind="power", when=rides_on
        ),
        c.bonus("damage", c.con_mod, on=wielder, until=When.ENCOUNTER, when=rides_on),
    ]

    def shake_off(spender: int) -> None:
        stuck = next(
            (
                e
                for e in c.world.effects.of(spender)
                if e.when is When.SAVE_ENDS and not e.ended
            ),
            None,
        )
        if stuck is None:
            c.note(f"{c.ref}: nothing a save can end")
            return
        for eff in holds:
            if eff is not None and not eff.ended:
                c.world.effects.end(eff, f"{c.ref} spent")
        c.world.effects.end(stuck, c.ref)

    c.give(fn=shake_off, on=wielder, cost=MINOR)
