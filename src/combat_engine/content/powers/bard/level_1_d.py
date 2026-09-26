"""Bard, level 1: the rows that hang an effect on the caster's own aura."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.powers.bard._shared import (
    aura_allies,
    by_basic,
    in_aura,
    while_in,
)
from combat_engine.engine import *

MARTIAL = [Keyword.MARTIAL]


def _on_basic_hit(c: Cast, pay: Callable[[int], None]) -> None:
    """The four at-wills' shared shape: a stance, then a payout on each hit.

    "Until the end of the encounter or until you use another bard at-will
    attack power" is a stance -- one at a time, ended by the next one -- so
    `c.stance` says both halves. The watcher cannot itself be held for
    `When.STANCE`: that would be a second stance effect, `Effects.stance_of`
    returns the first it finds, and the next at-will would end one of the
    pair and leave the other paying out for the rest of the fight.
    `held.ended` is the honest guard.

    The aura is read when the payout lands rather than when the stance is
    taken, which is what "one of your allies in the aura" is asking.
    """
    held = c.stance(label=c.ref)

    def paid(ev: Any) -> None:
        if held.ended or ev.attacker != c.me or ev.target not in c.enemies():
            return
        if not by_basic(c, ev):
            return
        friends = aura_allies(c)
        if not friends:
            return
        ally = c.choose(friends, "an ally in the aura")
        if ally is not None:
            pay(ally)

    c.watch(Hit, paid, until=When.ENCOUNTER, label=c.ref)


@power(
    "p14447",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14447(c: Cast) -> None:
    _on_basic_hit(c, lambda ally: c.temp_hp(c.cha_mod, on=ally))


@power(
    "p14448",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14448(c: Cast) -> None:
    """`once` is "his or her *next* damage roll"; the duration is the outside
    edge of it."""
    _on_basic_hit(
        c,
        lambda ally: c.bonus(
            "damage", 4, on=ally, until=When.EONT, kind="power", once=True
        ),
    )


@power(
    "p14449",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14449(c: Cast) -> None:
    _on_basic_hit(
        c,
        lambda ally: c.bonus(
            "attack", 2, on=ally, until=When.EONT, kind="power", once=True
        ),
    )


@power(
    "p14450",
    level=1,
    cls="bard",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14450(c: Cast) -> None:
    """"All defenses" is four keys, not one, and the bonus is not spent by a
    roll, so no `once` here."""

    def pay(ally: int) -> None:
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, 2, on=ally, until=When.EONT, kind="power")

    _on_basic_hit(c, pay)


@power(
    "p14454",
    level=1,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14454(c: Cast) -> None:
    """`query.has_combat_advantage` reads `unflankable` off the creature being
    flanked, so a zone modifier of that key is the printed line with its
    geometry. `side="ally"` covers the caster too, which the first sentence
    does not say either way.

    The extra damage is a `DamageRolled` listener because that Decision's
    `amount` is read back after the emit -- the supported way to make one
    attack land harder. The `c.note` is load-bearing: `c.watch` only spends a
    `once` hold when the handler did something the log can see, and bumping a
    field announces nothing.
    """
    zone = c.my_aura()
    if not zone:
        return
    c.grants_in(zone, "unflankable", 1)

    def harder(ev: Any) -> None:
        if ev.source not in aura_allies(c) or ev.target not in c.enemies():
            return
        ev.amount += c.roll("2d10")
        c.note(f"{c.ref}: extra damage from the aura")

    c.watch(DamageRolled, harder, until=When.ENCOUNTER, once=True)


@power(
    "p14455",
    level=1,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14455(c: Cast) -> None:
    """The +4 half cannot go through `c.grants_in`: it takes no `when=`, and a
    second power bonus of the same key would come to +4 always or +2 always,
    since the larger of a type wins. So the base +2 is the zone modifier and
    the other +2 is added to the roll when the target is bloodied, for the
    printed +4. `c.grants_in(..., when=)` is in the report.
    """
    zone = c.my_aura()
    if not zone:
        return
    c.grants_in(zone, "damage", 2)

    def bloodied_too(ev: Any) -> None:
        if ev.target not in c.enemies() or not c.bloodied(on=ev.target):
            return
        if not in_aura(c, ev.source) or ev.source not in (*c.allies(), c.me):
            return
        ev.amount += 2

    c.watch(DamageRolled, bloodied_too, until=When.ENCOUNTER)


@power(
    "p14456",
    level=1,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p14456(c: Cast) -> None:
    """Granting combat advantage is a relation rather than a modifier, so
    `c.grants_in` cannot carry it and `while_in` does the same bookkeeping for
    a thing that is not a number.
    """
    zone = c.my_aura()
    if not zone:
        return
    while_in(
        c,
        zone,
        lambda who: c.grants_advantage(on=who, to="allies", until=When.ENCOUNTER),
        side="enemy",
    )

    def daze(ev: Any) -> None:
        if ev.target not in c.enemies() or not in_aura(c, ev.target):
            return
        if c.may("daze that enemy"):
            c.dazed(on=ev.target, until=When.SAVE_ENDS)

    c.watch(DamageApplied, daze, until=When.ENCOUNTER, once=True)
