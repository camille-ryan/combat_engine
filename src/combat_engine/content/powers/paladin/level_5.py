"""Paladin, level 5: daily attacks.

`p3275`'s secondary is an implement attack on a row that carries
`Keyword.WEAPON` for its primary, so `c.cha_` would hand it the longsword's
proficiency. It is built from the level term and the modifier instead, which
is what an implement attack is.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    DAILY,
    EACH_ENEMY,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Ranged,
    When,
    ZoneEntered,
    get,
    power,
)
from combat_engine.engine.events import DamageApplied, ZoneExited
from combat_engine.engine.grid import distance, spread
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.zones import Zone

from .marks import burning_mark

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]

_DEFENCES = (AC, FORT, REF, WILL)


def _beside(c: Cast, victim: int) -> list[tuple[int, int]]:
    """The free squares around a creature, for a row that names one."""
    theirs = squares_of(c.world, victim)
    return [
        sq
        for sq in spread(theirs, 1) - theirs
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    ]


@power(
    "p10249",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.NECROTIC, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p10249(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod, dtype=DamageType.NECROTIC)
        # One effect: "save ends both" is one saving throw.
        c.condition(Condition.WEAKENED, Condition.SLOWED, until=When.SAVE_ENDS)


@power(
    "p1252",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.ZONE],
    attack=Attack(CHA, vs=REF),
)
def p1252(c: Cast) -> None:
    """The bonus belongs to standing in the light, not to being in the burst.

    So it is applied on entry and taken away on exit, which is `p1255`'s
    arrangement for the same sentence -- four defences instead of one.
    Whoever is already inside gets it by hand: `c.zone` refreshes membership
    before it returns, so their `ZoneEntered` has been and gone.
    """
    if c.strike():
        c.damage("2d6", c.cha_mod)
    if not c.first:
        return

    me = c.me
    zone = c.zone(c.area(), until=When.ENCOUNTER)
    held = c.world.get(zone, Zone)
    inside: dict[int, list[Effect]] = {}

    def light(who: int) -> None:
        if who in inside or (who != me and who not in c.allies()):
            return
        inside[who] = [
            e
            for e in (
                c.bonus(d, 1, on=who, until=When.ENCOUNTER, kind="power")
                for d in _DEFENCES
            )
            if e is not None
        ]

    def unlight(who: int) -> None:
        for effect in inside.pop(who, []):
            c.world.effects.end(effect, "left the zone")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            light(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone:
            unlight(ev.actor)

    def cleanup() -> None:
        for who in list(inside):
            unlight(who)

    subs = [
        c.world.bus.on(ZoneEntered, entered),
        c.world.bus.on(ZoneExited, exited),
    ]
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)
        # The zone ending unsubscribes the pair above before it announces the
        # exits, so the bonuses come off here rather than there.
        held.effect.on_end.append(cleanup)
    for who in c.world.zones.occupants(zone):
        light(who)


@power(
    "p1267",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p1267(c: Cast) -> None:
    """The surge is part of the attack line and buys nothing back.

    `c.spend_surge` is the one that takes a surge and heals no hit points,
    and it is paid once for the use rather than once per target.
    """
    if c.first:
        c.spend_surge(on=c.me)
    if c.strike():
        c.damage(c.w(4), c.str_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(4), c.str_mod, dtype=DamageType.RADIANT)


@power(
    "p1274",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=FORT),
)
def p1274(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.RADIANT)
        c.vulnerable(5, DamageType.RADIANT, until=When.ENCOUNTER)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.RADIANT)


@power(
    "p13558",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.COLD],
    attack=Attack(STR, vs=FORT),
)
def p13558(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod, dtype=DamageType.COLD)
        c.penalty("damage", 5, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(3), c.str_mod, dtype=DamageType.COLD)
        c.penalty("damage", 5, until=When.EOTNT)


@power(
    "p13559",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FIRE],
    attack=Attack(STR, vs=AC),
)
def p13559(c: Cast) -> None:
    """The splash is an Effect line, so the neighbours burn on a miss too."""
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.str_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage(c.w(3), c.str_mod, dtype=DamageType.FIRE)
    if victim is None:
        return
    for foe in sorted(e for e in c.within(1, of=victim, side="enemy") if e != victim):
        c.flat(5, dtype=DamageType.FIRE, on=foe)


@power(
    "p13820",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(STR, vs=WILL),
)
def p13820(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.PSYCHIC)
        c.slide(2)
        _crush(c, victim, 10)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.PSYCHIC)
        c.slide(1)
        _crush(c, victim, 5)


def _crush(c: Cast, victim: int, amount: int) -> None:
    """"One enemy adjacent to the target at the end of the slide" -- asked
    after the slide, which is the whole point of sliding it."""
    near = sorted(e for e in c.within(1, of=victim, side="enemy") if e != victim)
    if near:
        c.flat(amount, on=c.choose(near, "who is crushed against it"))


@power(
    "p13821",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p13821(c: Cast) -> None:
    """"You grant combat advantage" is the relation the other way round, and
    it names one beneficiary at a time -- so it is granted once per enemy.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(4), c.str_mod)
        c.push(2)
        if victim is not None:
            landing = [sq for sq in _beside(c, victim) if distance(c.here, sq) <= 3]
            if landing:
                c.shift(3, to=min(landing, key=lambda sq: (distance(c.here, sq), sq)))
    else:
        c.half_damage(c.w(4), c.str_mod)
    if c.first:
        for foe in sorted(c.enemies()):
            c.grants_advantage(on=c.me, to=foe, until=When.SONT)


@power(
    "p3273",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p3273(c: Cast) -> None:
    """The tithe is recognised by the burn's own detail line, which is what
    `Effects._on_turn_start` puts on the damage it deals -- so it pays out
    on that burn ticking and on nothing else.

    The burn is an Effect line and lands whether the swing did or not.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    if victim is None:
        return
    burn = c.ongoing(5)
    if burn is None:
        return
    me, tag = c.me, str(burn)

    def tithe(ev: DamageApplied) -> None:
        if ev.target == victim and ev.detail == tag:
            c.heal(c.wis_mod, on=me)

    burn.subs.append(c.world.bus.on(DamageApplied, tithe, owner=me))


@power(
    "p3275",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p3275(c: Cast) -> None:
    """The secondary is an Effect line: it is made whether the first swing
    landed or not, and it provokes nothing, which is what the printed line
    says rather than what the range would give it.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    pool = sorted(e for e in c.within(5, side="enemy") if e != victim)
    if not pool:
        return
    foe = c.choose(pool, "who the light finds")
    if foe is None:
        return
    # An implement attack on a weapon row: half level and the modifier, with
    # no proficiency, which is what `c.cha_` would wrongly add here.
    if c.attack(c.world.scaling.pc(c.level) + c.cha_mod, WILL, on=foe):
        c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT, on=foe)
        c.heal(c.roll("1d6") + c.cha_mod, on=c.me)


@power(
    "p3726",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p3726(c: Cast) -> None:
    """"Against charm effects" is read off the attacking row's keywords at
    the moment the defence is looked up, which is what the defence context
    carries `power` for.
    """
    if c.strike():
        c.damage(c.w(3), c.cha_mod)
        burning_mark(c, until=When.ENCOUNTER)
    else:
        c.half_damage(c.w(3), c.cha_mod)
    if not c.first:
        return

    def charming(ctx: dict) -> bool:
        p = get(ctx.get("power") or "")
        return p is not None and Keyword.CHARM in p.keywords

    for d in _DEFENCES:
        c.bonus(d, 5, on=c.me, until=When.ENCOUNTER, when=charming)


@power(
    "p3730",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p3730(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.THUNDER)
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.THUNDER)
        c.slowed(until=When.EOTNT)


@power(
    "p7254",
    level=5,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p7254(c: Cast) -> None:
    """"If the target was already marked by you" is asked before the mark
    this row lays down, or it would be true of everything it touches.
    """
    victim = c.target
    already = c.marked()
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
    if victim is None:
        return
    burning_mark(c)
    if not already:
        return
    me = c.me
    mine = [me, *c.allies()]
    recoil = c.effect(f"{c.ref} recoil", until=When.SAVE_ENDS, on=victim)
    if recoil is None:
        return

    def sear(ev: DamageApplied) -> None:
        if ev.source == victim and ev.target in mine and ev.amount > 0:
            c.flat(c.wis_mod, dtype=DamageType.RADIANT, on=victim)

    recoil.subs.append(c.world.bus.on(DamageApplied, sear, owner=me))
