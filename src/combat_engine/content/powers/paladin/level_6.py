"""Paladin, level 6: utility. Nothing here rolls an attack.

`p1289` is telepathy and a better aid-another bonus. Neither is a thing
this engine holds -- there is no channel to talk on and no check to aid --
so it is declared inert rather than given an invented effect.

`p356` is the one with teeth: a standing arrangement that takes half of an
ally's damage for the rest of the fight, written on `DamageRolled` in the
interrupt window, which is where the number still exists and has not yet
come off anybody.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    FREE,
    MINOR,
    ONE_OTHER_ALLY,
    Cast,
    CloseBurst,
    Keyword,
    Ranged,
    When,
    Window,
    power,
)
from combat_engine.engine.events import DamageRolled

DIVINE = [Keyword.DIVINE]


@power(
    "p1279",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=DIVINE,
)
def p1279(c: Cast) -> None:
    c.bonus("damage", c.cha_mod, until=When.ENCOUNTER)


@power(
    "p1289",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(6),
    target=EACH_ALLY,
    keywords=DIVINE,
    out_of_combat=True,
)
def p1289(c: Cast) -> None:
    c.note("p1289: the targets speak mind to mind out to 20 squares, and aid better")


@power(
    "p356",
    level=6,
    cls="paladin",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_OTHER_ALLY,
    keywords=DIVINE,
)
def p356(c: Cast) -> None:
    """Half of whatever the ally takes arrives here instead.

    Ending it deliberately is a free action, which is `drop_cost` on the
    effect the watcher lives on -- the same door `c.form` uses to let a
    shape be stepped out of.

    "No power or effect can reduce the damage you take from this power" has
    no spelling: the paladin's half goes through `deal_damage` like anything
    else, so resistance still reads it. The line is left unwritten rather
    than approximated with an immunity the row does not grant.
    """
    friend = c.target
    if friend is None:
        return
    me = c.me

    def share(ev: DamageRolled) -> None:
        if ev.target != friend or ev.amount <= 0:
            return
        half = ev.amount // 2
        ev.amount -= half
        if half:
            c.flat(half, dtype=ev.dtype, on=me)

    bond = c.watch(
        DamageRolled,
        share,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label=c.ref,
    )
    bond.drop_cost = FREE
