"""Fighter, level 6: utility.

Two rows, both defensive. The stance holds its three bonuses the way
`p1522` settled -- given `When.ENCOUNTER` and ended by hand when the stance
ends, because a second stance-clocked effect confuses `Effects.stance_of`.

The damage reduction is declared on `DamageRolled` rather than on the
printed `Hit`: that is the one moment the number exists and has not yet come
off anybody's hit points, and the emitter reads the amount back off the
event once the window closes.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    FORT,
    MINOR,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    Cast,
    Event,
    Keyword,
    Trigger,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import DamageRolled

MARTIAL = [Keyword.MARTIAL]

_HURT_BY_AN_ATTACK = "you are hit and damaged by an attack"


def _attack_damaged_me(world: World, me: int, ev: Event) -> bool:
    """Damage aimed at me that a declared row dealt.

    `targets_me` alone would also answer ongoing damage and a hazard, and
    the printed line says "by an attack" -- which is read off `detail`, the
    ref of whatever row is dealing it.
    """
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and get(getattr(ev, "detail", "")) is not None
    )


@power(
    "p1439",
    level=6,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p1439(c: Cast) -> None:
    stance = c.stance(label=c.ref)
    for defence in (FORT, REF, WILL):
        guard = c.bonus(defence, 2, on=c.me, until=When.ENCOUNTER)
        if guard is not None:
            stance.on_end.append(
                lambda g=guard: c.world.effects.end(g, "stance ended")
            )


@power(
    "p1441",
    level=6,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_HURT_BY_AN_ATTACK,
    on=Trigger(DamageRolled, when=_attack_damaged_me, text=_HURT_BY_AN_ATTACK),
)
def p1441(c: Cast) -> None:
    """The blow lands; less of it arrives.

    Nothing on `Cast` shaves a number off damage in flight -- `c.absorb`
    takes all of it and moves it -- so the event's amount is cut here, which
    is what `m3055a2` already does to share a grab's damage out.
    """
    ev = c.trigger
    if ev is None:
        return
    spared = min(getattr(ev, "amount", 0), 5 + c.con_mod)
    ev.amount -= spared
    c.note(f"p1441: {spared} damage turned aside")
