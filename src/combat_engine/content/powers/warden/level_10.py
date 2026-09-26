"""Warden, level 10: the utilities.

Two of them are about taking a blow meant for somebody else. `c.absorb`
reads the damage off the event it is handed and zeroes it there, which is
why the trigger has to be `DamageRolled` -- the last point at which the
number is still a proposal -- and why the rest of the attack's effects
stay where they landed.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.query import distance_between, team

from . import has_shield

PRIMAL = [Keyword.PRIMAL]


def _ally_hurt_nearby(world: World, me: int, ev: DamageRolled) -> bool:
    who = ev.target
    return (
        who != me
        and team(world, who) is team(world, me)
        and distance_between(world, me, who) <= 2
    )


@power(
    "p13605",
    level=10,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.PRIMAL, Keyword.ILLUSION, Keyword.TELEPORTATION],
)
def p13605(c: Cast) -> None:
    """The teleport is hung on the end of the invisibility rather than on
    the clock, so it happens however the invisibility ran out -- the turn
    boundary or the attack that gave the target away."""
    who = c.target
    if who is None:
        return
    veil = c.invisible(on=who, until=When.EOTNT)
    if veil is None:
        return
    veil.on_end.append(lambda: c.teleport(3, who=who))

    def gave_away(ev: AttackDeclared) -> None:
        if ev.attacker == who:
            c.world.effects.end(veil, "made an attack")

    c.watch(AttackDeclared, gave_away, until=When.EOTNT, once=True)


@power(
    "p5130",
    level=10,
    cls="warden",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.TELEPORTATION],
)
def p5130(c: Cast) -> None:
    c.teleport(c.con_mod)


@power(
    "p5131",
    level=10,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
)
def p5131(c: Cast) -> None:
    c.surge(on=c.me, bonus=c.str_mod)


@power(
    "p5132",
    level=10,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p5132(c: Cast) -> None:
    c.slide(5)
    c.resist(5, until=When.EONT, on=c.target)
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, until=When.EONT)


@power(
    "p9866",
    level=10,
    cls="warden",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(2),
    target=ONE_ALLY,
    keywords=PRIMAL,
    trigger="an ally within 2 squares of you takes damage from an attack",
    on=Trigger(
        DamageRolled, _ally_hurt_nearby, "an ally within 2 squares takes damage"
    ),
)
def p9866(c: Cast) -> None:
    """Only the damage moves. Everything else the attack did has already
    been applied to the ally, which is the printed line."""
    c.absorb(c.trigger, on=c.me)


@power(
    "p9867",
    level=10,
    cls="warden",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=PRIMAL,
)
def p9867(c: Cast) -> None:
    kind = c.choose(
        [DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING, DamageType.THUNDER],
        "which element the warding turns",
    )
    amount = max(1, c.level // 2)
    c.resist(amount, kind, on=c.target, until=When.EONT)
    if c.first and c.me not in c.targets:
        c.resist(amount, kind, on=c.me, until=When.EONT)


@power(
    "p9869",
    level=10,
    cls="warden",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=PRIMAL,
    trigger="you start your turn",
    on=Trigger(TurnStart, about_me, "you start your turn"),
)
def p9869(c: Cast) -> None:
    """Giving up the class feature's own saving throw for the turn is the
    cost, and the chassis carries no ref for that feature to forbid."""
    c.save()


@power(
    "p9969",
    level=10,
    cls="warden",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=has_shield,
    requires_text="must be wielding a shield",
    trigger="you are hit with a melee attack",
    on=Trigger(
        AttackRolled,
        both(would_hit_me, by_melee),
        "a melee attack is about to hit you",
    ),
)
def p9969(c: Cast) -> None:
    """Raised on `AttackRolled`, not `Hit`: the defence is read again once
    the interrupt window closes, so a bonus put up here can still turn the
    blow aside -- which is the only way the "if the triggering attack
    misses" half can ever come true."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    vs = getattr(ev, "vs", None)
    if vs is not None:
        c.bonus(vs, 4, on=c.me, until=When.EONT)
    if foe is None:
        return

    def turned_aside(miss: Miss) -> None:
        if miss.attacker != foe or miss.target != c.me:
            return
        held = c.immobilized(on=foe, until=When.EONT)
        if held is None:
            return

        def walked_off(moved: MoveEnd) -> None:
            if moved.actor == c.me and not c.adjacent(foe):
                c.world.effects.end(held, "the warden moved away")

        c.watch(MoveEnd, walked_off, until=When.EONT)

    c.watch(Miss, turned_aside, until=When.EONT, once=True)


@power(
    "p5133",
    level=10,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[*PRIMAL, Keyword.ZONE],
)
def p5133(c: Cast) -> None:
    """`c.grants_in` is the zone-carries-a-modifier verb and cannot be used
    here: resistance is not a `Mod`, it lives in `Defences.resist`, which
    nothing reads a modifier into. So the zone's own entering and leaving
    are watched and `c.resist` is put on and taken off by hand -- the same
    shape `c.grants_in` has, with the one line that differs.

    Whoever is already standing in the burst when it is laid is covered:
    `Zones._spawn` refreshes before returning, so the occupants are known.
    """
    me, world = c.me, c.world
    vines = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER)
    amount = c.con_mod
    if amount <= 0:
        return
    held: dict[int, Effect] = {}

    def give(who: int) -> None:
        if who in held or team(world, who) is not team(world, me):
            return
        got = c.resist(amount, on=who, until=When.ENCOUNTER)
        if got is not None:
            held[who] = got

    def take(who: int) -> None:
        got = held.pop(who, None)
        if got is not None:
            world.effects.end(got, "left the zone")

    def on_enter(ev: ZoneEntered) -> None:
        if ev.zone == vines:
            give(ev.actor)

    def on_exit(ev: ZoneExited) -> None:
        if ev.zone == vines:
            take(ev.actor)

    for who in world.zones.occupants(vines):
        give(who)
    c.watch(ZoneEntered, on_enter, until=When.ENCOUNTER, on=me)
    c.watch(ZoneExited, on_exit, until=When.ENCOUNTER, on=me)
