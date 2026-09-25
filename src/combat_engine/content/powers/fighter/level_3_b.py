"""Fighter, level 3: the encounter attacks the later books added.

Two of these are immediate interrupts whose printed trigger is "an enemy
hits or misses you". That is known only once the die is down, so they are
declared on `AttackRolled` rather than on `Hit`: `resolve.attack` re-reads
the defence and recomputes the outcome from `result` after that window
closes, which is what makes a penalty applied there able to turn a hit into
a miss. Declaring them on `Hit` would resolve them after the comparison had
already been made.
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
    REACTION,
    REF,
    STANDARD,
    STR,
    Attack,
    AttackRolled,
    Cast,
    CloseBurst,
    Keyword,
    Melee,
    MoveEnd,
    Trigger,
    When,
    World,
    by_me,
    by_melee,
    power,
    spread,
)
from combat_engine.engine.events import AttackDeclared, Hit, Miss
from combat_engine.engine.query import adjacent, allies, team
from combat_engine.engine.query import squares as squares_of

from .footwork import beside_me
from .grips import has_shield, heavy_rider, two_handed, two_melee
from .holds import grabbed_by, holds_somebody

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL = [Keyword.MARTIAL]


def _adjacent_foe_swinging(world: World, me: int, ev: Any, *, at_allies: bool) -> bool:
    attacker = getattr(ev, "attacker", None)
    struck = getattr(ev, "target", None)
    if attacker is None or attacker == me or team(world, attacker) is team(world, me):
        return False
    if not adjacent(world, me, attacker):
        return False
    if struck != me and not (at_allies and struck in allies(world, me)):
        return False
    return by_melee(world, me, ev)


def _swung_at_me(world: World, me: int, ev: Any) -> bool:
    """"An enemy adjacent to you hits or misses you with a close or a melee
    attack" -- `by_melee` answers all three reach kinds the sentence names."""
    return _adjacent_foe_swinging(world, me, ev, at_allies=False)


def _hit_me_or_mine(world: World, me: int, ev: Any) -> bool:
    """The same sentence, widened to an ally, and only for a blow that lands."""
    result = getattr(ev, "result", None)
    return bool(result and result.hit) and _adjacent_foe_swinging(
        world, me, ev, at_allies=True
    )


def _missed_me_or_mine(world: World, me: int, ev: Any) -> bool:
    struck = getattr(ev, "target", None)
    attacker = getattr(ev, "attacker", None)
    if attacker is None or attacker == me or team(world, attacker) is team(world, me):
        return False
    if struck != me and struck not in allies(world, me):
        return False
    return by_melee(world, me, ev)


def _i_hit_in_melee(world: World, me: int, ev: Any) -> bool:
    return by_me(world, me, ev) and by_melee(world, me, ev)


_SWUNG_AT_ME = "an enemy next to you hits or misses you with a close or melee attack"
_HIT_ME_OR_MINE = "an enemy next to you hits you or an ally with a melee attack"
_MISSED_US = "an enemy misses you or an ally with a melee attack"
_I_LANDED_ONE = "you hit an enemy with a melee attack"


@power(
    "p10334",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=has_shield,
    requires_text="needs a shield",
)
def p10334(c: Cast) -> None:
    """"The next time the target attacks you" is a one-shot watcher: whoever
    else is standing beside the fighter pays for the attempt."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    me = c.me

    def collateral(ev: AttackDeclared) -> None:
        if ev.attacker != victim or ev.target != me:
            return
        others = sorted(e for e in c.within(1, side="enemy") if e != victim)
        if others:
            c.flat(c.str_mod, on=c.choose(others, "who is shoved into the blow"))

    c.watch(
        AttackDeclared, collateral, until=When.EONT, on=me, once=True,
        label=f"{c.ref} answer",
    )


@power(
    "p10488",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p10488(c: Cast) -> None:
    """The Special line -- swinging this instead of a basic attack when
    charging -- has no header field; see the report."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    vacated = c.there
    if c.push(1) and vacated is not None:
        c.shift(1, to=vacated)
    if c.attack(c.str_, FORT):
        c.prone()


@power(
    "p10489",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10489(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    me = c.me

    def costly(ev: MoveEnd) -> None:
        if ev.actor == victim:
            c.flat(c.con_mod, on=victim)

    c.watch(MoveEnd, costly, until=When.EONT, on=me, once=True, label=f"{c.ref} toll")
    if c.wielding("axe") or c.wielding("pick"):
        vacated = c.here
        if c.shift(1) and vacated is not None:
            c.pull(1, to=vacated)


@power(
    "p10490",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=FORT, plus=2),
    requires=has_shield,
    requires_text="needs a shield",
    trigger=_SWUNG_AT_ME,
    on=Trigger(AttackRolled, _swung_at_me, _SWUNG_AT_ME),
)
def p10490(c: Cast) -> None:
    """The penalty goes on the triggering roll's own total, which the engine
    re-reads once this window closes; the counterswing is separate."""
    result = getattr(c.trigger, "result", None)
    if result is not None:
        result.total -= 4
    if c.strike():
        c.damage("2d6", c.str_mod)


@power(
    "p10491",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
    requires=holds_somebody,
    requires_text="needs a creature grabbed",
)
def p10491(c: Cast) -> None:
    """"One creature grabbed by you" is a narrowing the Target line cannot
    hold, so the header takes an enemy and the body swings at whoever is
    actually in the fighter's hands."""
    held = grabbed_by(c)
    victim = c.choose(held, "who is dragged along") if held else None
    if victim is None:
        return
    c.no_provoke(from_=victim, until=When.EOT)
    walked = c.move(c.speed_of())
    where = beside_me(c, victim)
    if walked and where is not None:
        c.slide(walked, on=victim, to=where)
    wall = any(
        sq in c.world.grid.blocking
        for sq in spread(squares_of(c.world, victim), 1) - squares_of(c.world, victim)
    )
    if c.strike(on=victim):
        c.damage(c.w(1), c.str_mod + (c.dex_mod if wall else 0), on=victim)
        c.prone(on=victim)


@power(
    "p10492",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p10492(c: Cast) -> None:
    """The follow-up is aimed at somebody the sweep already caught, so the
    pool is read off the burst *before* the step moves it."""
    if c.strike():
        c.push(1)
    if not c.last:
        return
    caught = sorted(c.in_squares(c.area(), side="enemy"))
    c.shift(1)
    second = c.choose(caught, "who the off-hand finishes") if caught else None
    if second is not None and c.attack(c.str_, AC, on=second):
        c.damage(c.w(2, hand="off"), c.str_mod, on=second)


@power(
    "p12193",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=FORT, plus=3),
    requires=has_shield,
    requires_text="needs a shield",
    trigger=_HIT_ME_OR_MINE,
    on=Trigger(AttackRolled, _hit_me_or_mine, _HIT_ME_OR_MINE),
)
def p12193(c: Cast) -> None:
    if c.strike():
        c.damage("1d10")
        c.weakened(until=When.EONT)


@power(
    "p12848",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p12848(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    shaken = {victim, *c.within(1, side="enemy"), *c.within(1, of=victim, side="enemy")}
    for foe in sorted(shaken):
        c.penalty("attack", 2, on=foe, until=When.EONT)


@power(
    "p2106",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_MISSED_US,
    on=Trigger(Miss, _missed_me_or_mine, _MISSED_US),
)
def p2106(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.grants_advantage(to="allies", until=When.EONT)


@power(
    "p2109",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2109(c: Cast) -> None:
    """A light blade or a spear buys a second step, and the printed choice
    is where to spend it -- both before, or one at each end."""
    nimble = c.wielding("light blade") or c.wielding("spear")
    after = nimble and c.may("keep a step back for afterwards", who=c.me)
    c.shift(1)
    if nimble and not after:
        c.shift(1)
    result = c.strike()
    if result:
        c.damage(c.w(2), c.str_mod + (c.dex_mod if result.advantage else 0))
    if after:
        c.shift(1)


@power(
    "p2131",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p2131(c: Cast) -> None:
    """No weapon dice: the blinding is the hit, and the heavy groups add a
    flat modifier on top."""
    if not c.strike():
        return
    c.blinded(until=When.EONT)
    c.damage(0, heavy_rider(c))


@power(
    "p226",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
    attack=Attack(STR, vs=FORT, plus=2),
    requires=has_shield,
    requires_text="needs a shield",
    trigger=_I_LANDED_ONE,
    on=Trigger(Hit, _i_hit_in_melee, _I_LANDED_ONE),
)
def p226(c: Cast) -> None:
    if c.strike():
        c.push(1)
        c.prone()


@power(
    "p4230",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4230(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.grants_advantage(until=When.EONT)


@power(
    "p4320",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
)
def p4320(c: Cast) -> None:
    """The Special line -- swinging this instead of a basic attack when an
    opportunity opens -- has no header field; see the report."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.str_mod)
    c.bonus(
        "attack", 4, on=c.me, until=When.EONT,
        when=lambda ctx: ctx.get("target") == victim,
    )


@power(
    "p4321",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires_text="must charge with this in place of the basic attack",
    charges=True,
)
def p4321(c: Cast) -> None:
    """A row whose printed Requirement *is* the charge, so the flag goes up
    by hand and `c.run_at` walks -- `c.charge_at` would reach the swing
    through `use`, which refuses to re-enter a row already in flight."""
    victim = c.target
    if victim is None:
        return
    if c.wielding("shield"):
        c.no_provoke(until=When.EOT)
    c.charge = True
    try:
        c.run_at(victim)
        if c.strike(on=victim):
            c.damage(c.w(2), c.str_mod, on=victim)
    finally:
        c.charge = False


@power(
    "p9995",
    level=3,
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
def p9995(c: Cast) -> None:
    """"You can use your second wind as a minor action" is a discount on
    what an action costs, and `actions.legal` builds the second wind at a
    fixed standard; nothing changes that. The rider is in the report."""
    if c.strike():
        c.damage(c.w(1), c.str_mod + c.con_mod)
