"""Shaman, level 10 utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    AreaBurst,
    AttackDeclared,
    Cast,
    CloseBurst,
    Health,
    Hit,
    Keyword,
    Melee,
    Ranged,
    SavingThrow,
    TurnStart,
    When,
    power,
)

from ._spirit import beside, beside_spirit, friends, near_spirit

PRIMAL = [Keyword.PRIMAL]


@power(
    "p5402",
    level=10,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PRIMAL,
)
def p5402(c: Cast) -> None:
    c.slide(3)


@power(
    "p5403",
    level=10,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(1, 5),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p5403(c: Cast) -> None:
    """Moving the zone as a move action has no verb, so the zone stays
    where it was put."""
    rocks = c.zone(c.area(), until=When.ENCOUNTER)
    for mate in c.allies():
        for what in (AC, FORT):
            c.bonus(
                what, 2, on=mate, until=When.ENCOUNTER,
                when=lambda ctx, w=mate: w in c.world.zones.occupants(rocks),
            )


@power(
    "p9768",
    level=10,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p9768(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return

    def gift(ev: Any) -> None:
        if getattr(ev, "actor", None) == mate:
            c.temp_hp(c.wis_mod, on=mate)

    c.watch(TurnStart, gift, until=When.ENCOUNTER, on=mate)


@power(
    "p9769",
    level=10,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=PRIMAL,
)
def p9769(c: Cast) -> None:
    """"Until he or she attacks" is not a duration the engine has, so the
    hold is ended by hand off the attack that gives the creature away."""
    who = c.target
    hidden = c.invisible(on=who, until=When.EONT)
    if who is None or hidden is None:
        return

    def reveal(ev: Any) -> None:
        if ev.attacker == who and not hidden.ended:
            c.world.effects.end(hidden, "attacked")

    c.watch(AttackDeclared, reveal, until=When.EONT, on=who)


# -- the rows built round the spirit ----------------------------------------


@power(
    "p12534",
    level=10,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3, from_="companion"),
    target=NO_TARGET,
    keywords=[
        Keyword.PRIMAL, Keyword.FEAR, Keyword.HEALING, Keyword.ZONE
    ],
)
def p12534(c: Cast) -> None:
    """"The zone moves with the spirit companion" is an aura on the spirit
    rather than a zone on the ground -- an aura is the one area that
    follows a creature, and it goes when the creature does, which is the
    other half of the printed duration. Both riders read off the aura, so
    they stop paying when it is gone."""
    spirit = c.companion()
    if spirit is None:
        return
    dread = c.aura(3, on=spirit, until=When.EONT, sustain=MINOR)
    for foe in c.enemies():
        c.penalty(
            "attack", 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: f in c.world.zones.occupants(dread),
        )

    def mend(ev: Any) -> None:
        mate = getattr(ev, "actor", None)
        if mate not in friends(c, with_me=True):
            return
        if mate in c.world.zones.occupants(dread) and c.bloodied(on=mate):
            c.heal(5, on=mate)

    c.watch(TurnStart, mend, until=When.ENCOUNTER, on=c.me)


@power(
    "p12876",
    level=10,
    cls="shaman",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(5, from_="companion"),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p12876(c: Cast) -> None:
    """Lightly obscured is concealment, which has no verb -- the engine's
    sight flag blocks a line outright rather than softening it -- so the
    insubstantial half is the row."""
    mate = c.target
    c.dismiss_companion()
    if mate is not None:
        c.insubstantial(on=mate, until=When.EONT)


@power(
    "p5459",
    level=10,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p5459(c: Cast) -> None:
    """A saving throw is announced before it is acted on and `saved` is
    read back off the event, which is where a reroll goes: the new die
    replaces the old one, with the bonus the printed line gives the second
    and third rerolls."""
    paid = [0]

    def again(ev: Any) -> None:
        who = getattr(ev, "actor", None)
        if paid[0] >= 3 or ev.saved or who not in friends(c):
            return
        if not beside_spirit(c, who):
            return
        paid[0] += 1
        ev.natural = c.roll("1d20")
        ev.saved = ev.natural + ev.bonus + (paid[0] - 1) >= 10

    c.watch(SavingThrow, again, until=When.ENCOUNTER, on=c.me)


@power(
    "p6945",
    level=10,
    cls="shaman",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p6945(c: Cast) -> None:
    """There is no verb for giving a healing surge back -- `c.spend_surge`
    only takes one -- so the pool is written to directly. "Cannot be
    conjured again until the start of your next turn" wants the call's own
    id to take away, and the call is not a row here."""
    for mate in beside(c):
        pool = c.world.get(mate, Health)
        if pool is not None:
            pool.surges += 1
    c.dismiss_companion()


@power(
    "p9767",
    level=10,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p9767(c: Cast) -> None:
    """The second half spends an immediate interrupt to end the first, and
    there is no verb for spending one, so it is armed as a watch: the first
    blow it can answer ends the standing bonus and buys the bigger one."""
    held = []
    for mate in friends(c, with_me=True):
        for what in (AC, FORT, REF, WILL):
            kept = c.bonus(
                what, 2, on=mate, until=When.ENCOUNTER,
                when=lambda ctx, w=mate: near_spirit(c, w, 5),
            )
            if kept is not None:
                held.append(kept)
    spent = [False]

    def cover(ev: Any) -> None:
        mate = getattr(ev, "target", None)
        if spent[0] or mate not in friends(c) or c.distance(mate) > 10:
            return
        if not c.may("end the power to shield the ally", who=mate):
            return
        spent[0] = True
        for kept in held:
            if not kept.ended:
                c.world.effects.end(kept, "spent on one blow")
        for what in (AC, FORT, REF, WILL):
            c.bonus(what, 6, on=mate, until=When.EOT, once=True)

    c.watch(Hit, cover, until=When.ENCOUNTER, on=c.me)
