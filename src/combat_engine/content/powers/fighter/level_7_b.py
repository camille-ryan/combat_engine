"""Fighter, level 7: the encounter attacks the later books added.

Two notes.

**"An enemy adjacent to you moves away"** is `MoveStart`, not `MoveEnd`: an
interrupt has to resolve while the creature is still standing there, and by
`MoveEnd` it is gone. Everything else here that watches movement wants the
other one.

**"You hit an enemy with a melee basic attack"** is read off the ref the
event carries against `Powers.basic`, which is what that creature's basic
attack actually is -- a monster points it at one of its own rows.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    Attack,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    Keyword,
    Melee,
    MoveEnd,
    Powers,
    Trigger,
    TurnStart,
    UpTo,
    When,
    Window,
    World,
    by_me,
    by_melee,
    power,
)
from combat_engine.engine.events import DamageRolled, Hit, MoveStart
from combat_engine.engine.query import adjacent, allies, team

from .grips import hand_free, has_shield, heavy_rider, two_handed, two_melee

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL = [Keyword.MARTIAL]


def _hit_my_friend_in_melee(world: World, me: int, ev: Any) -> bool:
    """"An enemy hits an ally with a melee attack" -- read off the roll,
    because the penalty this answers has to land before the blow does."""
    result = getattr(ev, "result", None)
    attacker = getattr(ev, "attacker", None)
    struck = getattr(ev, "target", None)
    if not (result and result.hit) or attacker is None or struck is None:
        return False
    if team(world, attacker) is team(world, me) or struck == me:
        return False
    return struck in allies(world, me) and by_melee(world, me, ev)


def _walked_away_from_me(world: World, me: int, ev: Any) -> bool:
    """"An adjacent enemy moves away from you." `MoveStart` is the only
    moment it is still adjacent, which is what an interrupt needs."""
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    return getattr(ev, "kind_", "") in ("walk", "shift", "run") and adjacent(world, me, who)


def _my_basic_landed(world: World, me: int, ev: Any) -> bool:
    known = world.get(me, Powers)
    return (
        by_me(world, me, ev)
        and known is not None
        and getattr(ev, "power", "") == known.basic
    )


_HIT_MY_FRIEND = "an enemy hits an ally with a melee attack"
_WALKED_AWAY = "an enemy next to you moves away"
_MY_BASIC_LANDED = "you hit an enemy with a melee basic attack"


@power(
    "p10336",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10336(c: Cast) -> None:
    """The two weapon riders are alternatives, not a list. Sheathing one
    weapon and drawing another before the attack has no expression; see the
    report."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    if c.wielding("axe"):
        for foe in sorted(e for e in c.within(1, of=victim, side="enemy") if e != victim)[:2]:
            c.flat(c.con_mod, on=foe)
    if c.wielding("heavy blade"):
        c.grants_advantage(until=When.EONT)


@power(
    "p10502",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10502(c: Cast) -> None:
    """Bloodied is asked before the blow, which is the printed order -- "if
    the target is bloodied" describes the creature that was swung at."""
    already = c.bloodied()
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod + heavy_rider(c))
    if already:
        c.dazed(until=When.EONT)


@power(
    "p10503",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=hand_free,
    requires_text="needs a hand free",
)
def p10503(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    c.dazed(until=When.EONT)
    if c.attack(c.str_, FORT):
        c.damage(c.w(1))
        c.prone()


@power(
    "p10504",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10504(c: Cast) -> None:
    """"As the first action you take during your turn" is the start of it,
    which is where the watcher sits; adjacency is asked there rather than
    now."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod + heavy_rider(c))
    me = c.me

    def follow_up(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not adjacent(c.world, me, victim):
            return
        if c.may("open with a swing", who=me):
            c.basic(on=victim)

    c.watch(TurnStart, follow_up, until=When.EONT, on=me, once=True, label=c.ref)


@power(
    "p10505",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10505(c: Cast) -> None:
    """The Special line -- swinging this instead of a basic attack when
    charging -- has no header field; see the report."""
    if not c.can_see():
        return
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p10506",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p10506(c: Cast) -> None:
    """The second swing is an Effect line, so it comes whether the first
    landed or not. The Special line -- using this in place of a basic attack
    -- has no header field; see the report."""
    if c.strike():
        c.damage(c.w(1), c.str_mod)
    if c.attack(c.str_, AC):
        c.damage(c.w(1, hand="off"), c.str_mod)


@power(
    "p12196",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=FORT, plus=4),
    requires=has_shield,
    requires_text="needs a shield",
    charges=True,
)
def p12196(c: Cast) -> None:
    """"You move your speed; at one point during this movement you can make
    the attack." The move is aimed rather than wandering, which is what
    `c.run_at` is -- and `charges=True` so the row is offered while the
    target is still a run away.
    """
    victim = c.target
    if victim is None:
        return
    if not c.adjacent(victim):
        c.run_at(victim)
    if c.strike(on=victim):
        c.damage("1d10", c.str_mod, on=victim)
        c.slide(1, on=victim)
        c.prone(on=victim)


@power(
    "p12851",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p12851(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.str_mod + c.dex_mod)
    me = c.me

    def shove(ev: MoveEnd) -> None:
        who = ev.actor
        if who in (me, victim) or who not in c.enemies():
            return
        if adjacent(c.world, who, victim) and c.may("shove it along", who=me):
            c.slide(1, on=who)

    c.watch(MoveEnd, shove, until=When.EONT, on=me, label=c.ref)


@power(
    "p2111",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p2111(c: Cast) -> None:
    """Two swings at the one creature, and the second is worth more when the
    first also landed."""
    first = bool(c.strike())
    if first:
        c.damage(c.w(1), c.str_mod)
        c.slowed(until=When.EONT)
    if c.attack(c.str_, AC):
        c.damage(c.w(1, hand="off"), c.str_mod + (c.dex_mod if first else 0))
        c.slowed(until=When.EONT)


@power(
    "p2133",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_HIT_MY_FRIEND,
    on=Trigger(AttackRolled, _hit_my_friend_in_melee, _HIT_MY_FRIEND),
)
def p2133(c: Cast) -> None:
    """The blow still lands; half of it arrives. Nothing on `Cast` shaves a
    number off damage in flight, so the amount is cut on `DamageRolled`,
    which is what `p1441` does."""
    ev = c.trigger
    swinging = getattr(ev, "attacker", None)
    friend = getattr(ev, "target", None)
    if not c.strike():
        return
    c.damage(0, c.str_mod + heavy_rider(c))
    if swinging is None or friend is None:
        return
    me = c.me

    def soften(blow: DamageRolled) -> None:
        if blow.source == swinging and blow.target == friend and blow.amount > 0:
            blow.amount //= 2

    c.watch(
        DamageRolled, soften, until=When.EOT, window=Window.BEFORE, on=me, once=True,
        label=f"{c.ref} shielded",
    )


@power(
    "p2466",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p2466(c: Cast) -> None:
    result = c.strike()
    if not result:
        return
    c.damage(
        c.w(1, hand="main" if c.first else "off"),
        c.str_mod + (c.dex_mod if result.advantage else 0),
    )
    c.push(1 + max(0, c.dex_mod))


@power(
    "p4330",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4330(c: Cast) -> None:
    """"Cannot stand up" is `Condition.PINNED`, which is the hold `c.prone`
    lays on top of prone for exactly this sentence."""
    flat = c.is_(Condition.PRONE)
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod + (c.dex_mod if flat else 0))
    if flat:
        c.condition(Condition.PINNED, until=When.EONT)


@power(
    "p856",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_WALKED_AWAY,
    on=Trigger(MoveStart, _walked_away_from_me, _WALKED_AWAY),
)
def p856(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    c.slowed(until=When.EOTNT)
    if c.wielding("flail") or c.wielding("pick"):
        c.immobilized(until=When.EOTNT)


@power(
    "p988",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
    trigger=_MY_BASIC_LANDED,
    on=Trigger(Hit, _my_basic_landed, _MY_BASIC_LANDED),
)
def p988(c: Cast) -> None:
    """A polearm or a spear trades the slow for a fall -- "instead", so only
    one of them happens."""
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    if c.wielding("polearm") or c.wielding("spear"):
        c.prone()
    else:
        c.slowed(until=When.EONT)


@power(
    "p9998",
    level=7,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=-2),
    requires=two_handed,
    requires_text="needs a two-handed weapon",
)
def p9998(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    for foe in sorted(e for e in c.within(1, side="enemy") if e != victim):
        c.flat(c.con_mod, on=foe)
