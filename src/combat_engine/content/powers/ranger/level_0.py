"""Ranger, level 0: the class features -- the shots and the stances.

A stance hangs everything it grants on the single `When.STANCE` effect
`c.stance()` returns. A second effect carrying that duration confuses
`Effects.stance_of`, so taking the next stance would end only one of them
and leave the rest standing for the fight. `_hold` is the modifier half of
that arrangement and `held.subs` is the trigger half.

Every "+N when you make a **basic attack**" gate reads `ctx["power"]`
against the two engine basics rather than the keywords: a creature whose
basic attack has been replaced still makes one, and a weapon power is not a
basic attack however much it looks like one.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DEX,
    ENCOUNTER,
    FORT,
    FREE,
    MELEE,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    RANGED,
    REF,
    SELF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    DamageRolled,
    Defense,
    Effect,
    Gear,
    Hit,
    Keyword,
    Melee,
    Miss,
    Mod,
    Mods,
    Ranged,
    Trigger,
    TurnEnd,
    When,
    World,
    power,
    spread,
)
from combat_engine.engine.query import squares

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
PRIMAL_STANCE = [Keyword.PRIMAL, Keyword.STANCE]

_BASICS = (MELEE, RANGED)


def _hold(
    c: Cast,
    held: Effect,
    what: str | Defense,
    value: int,
    *,
    when: Any = None,
) -> None:
    """Hang a modifier on the stance itself, so it goes when the stance does."""
    key = what.value if isinstance(what, Defense) else what
    mod = Mod(what=key, value=value, kind="power", when=when, label=c.ref)
    holder = c.world.get(c.me, Mods) or c.world.add(c.me, Mods())
    holder.items.append(mod)
    held.mods.append((c.me, mod))


def _is_basic(ctx: dict[str, Any]) -> bool:
    return ctx.get("power") in _BASICS


def _helpers(c: Cast, ctx: dict[str, Any]) -> int:
    """How many of my allies are standing next to the creature being hit."""
    foe = ctx.get("target")
    if foe is None:
        return 0
    return len([a for a in c.within(1, of=foe, side="ally") if a != c.me])


def _alone(c: Cast, ctx: dict[str, Any]) -> bool:
    foe = ctx.get("target")
    return foe is not None and not [
        e for e in c.within(1, of=foe, side="enemy") if e != foe
    ]


def _foe(c: Cast) -> int | None:
    """Who a Personal row's "make a ranged basic attack" shoots at."""
    seen = [f for f in c.enemies() if c.can_see(f)]
    return min(seen, key=lambda f: c.distance(f)) if seen else None


def _shot_hit(c: Cast, foe: int) -> bool:
    """Did the ranged basic land? `c.basic` reports that the row went off."""
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == foe:
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        c.basic(on=foe, ranged=True)
    finally:
        c.world.bus.off(sub)
    return bool(landed)


def _two_weapons(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.two_weapon


def _own_melee_basic(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power == MELEE and world.turn == me


# -- the shots ---------------------------------------------------------------


@power(
    "p13585",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p13585(c: Cast) -> None:
    """Only the shot is written. `c.basic` takes no `ignore_cover`, so the
    two cover and concealment clauses -- which are the whole row -- are
    dropped rather than approximated."""
    foe = _foe(c)
    if foe is not None:
        c.basic(on=foe, ranged=True)


@power(
    "p13586",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p13586(c: Cast) -> None:
    foe = _foe(c)
    if foe is None or not _shot_hit(c, foe):
        return
    pick = c.choose(["slide", "prone", "slow"], "the rider on the shot")
    if pick == "slide":
        c.slide(2, on=foe)
    elif pick == "prone":
        c.prone(on=foe)
    else:
        c.slowed(on=foe, until=When.SAVE_ENDS)


@power(
    "p13587",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p13587(c: Cast) -> None:
    """The penalty is a modifier held for the volley and taken off again:
    it belongs to these shots and not to the rest of the turn. A chosen
    enemy's square stands in for "a square within the attack's range", and
    the printed line does say each *creature* around it."""
    foe = _foe(c)
    if foe is None:
        return
    area = spread(squares(c.world, foe), 1)
    hurt = c.penalty("attack", 2, on=c.me, until=When.EOT)
    try:
        for who in c.in_squares(area):
            if who != c.me:
                c.basic(on=who, ranged=True)
    finally:
        if hurt is not None:
            c.world.effects.end(hurt, "volley over")


@power(
    "p13588",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p13588(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.dex_mod)
        if c.choose(["hold", "daze"], "the rider on the hit") == "daze":
            c.dazed(until=When.SAVE_ENDS)
        else:
            c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(), c.dex_mod)
        c.slowed(until=When.EONT)


@power(
    "p13619",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    once_per_round=True,
    requires=_two_weapons,
    requires_text="must be wielding two melee weapons",
    trigger="you hit with a melee basic attack on your turn",
    on=Trigger(Hit, _own_melee_basic, "you hit with a melee basic attack"),
)
def p13619(c: Cast) -> None:
    """The off hand's dice, which is what the printed parenthesis means."""
    if c.strike():
        c.damage(c.w(hand="off"), c.dex_mod)


# -- the stances -------------------------------------------------------------


@power(
    "p13589",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13589(c: Cast) -> None:
    """`DamageRolled` names no attacker, so "from attacks made against you"
    is narrowed only as far as "damage taken on your own turn". The free
    action to shift is taken as part of the hit rather than offered."""
    held = c.stance()

    def soften(ev: DamageRolled) -> None:
        if ev.target == c.me and c.turn_of() == c.me:
            ev.amount //= 2

    def step(ev: Hit | Miss) -> None:
        if ev.attacker == c.me and c.turn_of() == c.me:
            c.shift(2)

    held.subs.append(c.world.bus.on(DamageRolled, soften, owner=c.me))
    for kind in (Hit, Miss):
        held.subs.append(c.world.bus.on(kind, step, owner=c.me))


@power(
    "p13590",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13590(c: Cast) -> None:
    held = c.stance()

    def lonely(ctx: dict[str, Any]) -> bool:
        return _is_basic(ctx) and _alone(c, ctx)

    _hold(c, held, "attack", 1, when=lonely)
    _hold(c, held, "damage", 1, when=lonely)

    def step(ev: TurnEnd) -> None:
        if ev.actor == c.me:
            c.shift(1)

    held.subs.append(c.world.bus.on(TurnEnd, step, owner=c.me))


@power(
    "p13591",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13591(c: Cast) -> None:
    """Two judgements. The initiative bonus is dropped: nothing reads an
    "initiative" modifier, and the roll is made before anybody takes a
    stance anyway. "During your first turn" is read as the first round, and
    "opportunity attacks you provoke by moving" as any opportunity attack --
    the attack context says whether a swing is one, not what caused it."""
    held = c.stance()
    if c.wis_mod > 0:
        for defence in (AC, FORT, REF, WILL):
            _hold(
                c,
                held,
                defence,
                c.wis_mod,
                when=lambda ctx: bool(ctx.get("opportunity")),
            )
    _hold(c, held, "attack", 2, when=lambda ctx: c.world.round <= 1)


@power(
    "p13592",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13592(c: Cast) -> None:
    """Learning where hidden bloodied enemies are is knowledge rather than a
    combat effect, and nothing gives one creature another's position."""
    held = c.stance()

    def hurt(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return _is_basic(ctx) and foe is not None and c.bloodied(on=foe)

    _hold(c, held, "attack", 2, when=hurt)


@power(
    "p13593",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13593(c: Cast) -> None:
    """Combat advantage is read off the `Hit` rather than asked again: by
    damage time a one-shot grant has been spent, and the damage context
    carries no advantage flag at all. The two skill bonuses are not combat
    effects."""
    held = c.stance()

    def edge(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if ev.attacker == c.me and result is not None and result.advantage:
            c.bonus("damage", 2, on=c.me, until=When.EOT, once=True, kind="power")

    held.subs.append(c.world.bus.on(Hit, edge, owner=c.me))


@power(
    "p13594",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13594(c: Cast) -> None:
    held = c.stance()

    def big_foe(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return _is_basic(ctx) and foe is not None and c.size_of(on=foe).squares > 1

    def big_attacker(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.size_of(on=who).squares > 1

    _hold(c, held, "attack", 2, when=big_foe)
    for defence in (AC, FORT, REF, WILL):
        _hold(c, held, defence, 2, when=big_attacker)


@power(
    "p13595",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13595(c: Cast) -> None:
    """Only the speed is mechanical. There is no long-range band in the
    attack maths to ignore a penalty from, and Perception is a skill."""
    _hold(c, c.stance(), "speed", 2)


@power(
    "p13596",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13596(c: Cast) -> None:
    """A modifier's value is a fixed number, so "the bonus equals the number
    of your allies adjacent to it" is one gated modifier per count. Leaving
    a square next to an ally is not written: allies do not take opportunity
    attacks against you in the first place."""
    held = c.stance()

    def helped(ctx: dict[str, Any]) -> bool:
        return _is_basic(ctx) and _helpers(c, ctx) >= 2

    _hold(c, held, "attack", 1, when=helped)
    for count in range(2, 9):
        _hold(
            c,
            held,
            "damage",
            count,
            when=lambda ctx, n=count: _is_basic(ctx) and _helpers(c, ctx) == n,
        )


@power(
    "p13620",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13620(c: Cast) -> None:
    """"Your movement during a charge doesn't provoke" is dropped:
    `c.no_provoke` takes a creature and a duration and cannot be gated on
    what you are doing at the time."""
    held = c.stance()
    _hold(c, held, "damage", 2, when=lambda ctx: bool(ctx.get("charge")))

    def flatten(ev: Hit) -> None:
        if ev.attacker == c.me and getattr(ev, "charge", False):
            c.prone(on=ev.target)

    held.subs.append(c.world.bus.on(Hit, flatten, owner=c.me))


@power(
    "p13621",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13621(c: Cast) -> None:
    """The move action that shifts you to a bloodied enemy is dropped: a
    stance cannot add an action to the turn, only `c.grant_row` can, and
    there is no row to grant. Swimming is a skill."""
    held = c.stance()

    def hurt(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return _is_basic(ctx) and foe is not None and c.bloodied(on=foe)

    _hold(c, held, "attack", 2, when=hurt)


@power(
    "p13622",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_STANCE,
)
def p13622(c: Cast) -> None:
    """The cover and concealment clause wants a standing "ignore cover" on
    the creature; cover is worked out inside `resolve.attack` from the
    board, and only a power's own `ignore_cover` argument turns it off."""
    _hold(c, c.stance(), "speed", 2)
