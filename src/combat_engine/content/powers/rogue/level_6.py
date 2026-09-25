"""Rogue, level 6: utility, and every row of it printed behind a skill.

The Prerequisite lines gate *taking* these at character creation rather
than using them, so none is declared as a `requires` -- the reading
`level_2.py` settled.

Two rows are their check and nothing else and carry `out_of_combat=True`.
`p1506` is one of them for a second reason as well: nothing announces the
loss of cover or concealment, so its printed Trigger has no event to hang
`on=` from and is kept as prose for the card, the way `p922` is.

The rows printed in the later books follow below. Nothing in the model
holds concealment as a state between two creatures, so where a row grants
it the -2 it buys on that creature's attack rolls is what is applied.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBurst,
    Dropped,
    Event,
    Gear,
    Hit,
    Keyword,
    Melee,
    Miss,
    Relation,
    Trigger,
    When,
    Window,
    World,
    both,
    by_melee,
    power,
    spread,
    targets_me,
    would_hit_me,
)
from combat_engine.engine.events import DamageRolled, EnterSquare
from combat_engine.engine.query import adjacent, enemies, team
from combat_engine.engine.query import squares as squares_of

MARTIAL = [Keyword.MARTIAL]

_HIT_AGAINST_WILL = "you are hit by an attack against your Will"


def _would_hit_my_will(world: World, me: int, ev: Event) -> bool:
    return would_hit_me(world, me, ev) and getattr(ev, "vs", None) is WILL


@power(
    "p1042",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1042(c: Cast) -> None:
    """A mark is a relation, not a condition somebody applied, so shaking it
    off is clearing whatever is holding it -- from every marker at once,
    since the row names the condition rather than one enemy's claim."""
    for marker in c.world.relations.sources(Relation.MARKED_BY, c.me):
        c.world.relations.clear(Relation.MARKED_BY, marker, c.me, c.ref)
    c.shift(c.speed_of())


@power(
    "p1043",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_HIT_AGAINST_WILL,
    on=Trigger(AttackRolled, when=_would_hit_my_will, text=_HIT_AGAINST_WILL),
)
def p1043(c: Cast) -> None:
    """Raised on the roll, which is the window where the defence is read
    again -- so the +2 applies to the very attack that triggered it. `Hit`
    would be too late: by then the comparison has been made."""
    c.bonus(WILL, 2, on=c.me, until=When.EONT)


@power(
    "p365",
    level=6,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p365(c: Cast) -> None:
    """The move is the climb. The check is not rolled, so what is left is
    the +4, and it is granted only while the rogue is actually on a wall --
    `c.moving_as` asks what it is doing, where `Movement.modes` only ever
    said what it could do."""
    if c.moving_as("climb"):
        c.bonus("speed", 4, on=c.me, until=When.EOT)
    c.move(c.speed_of())


@power(
    "p1397",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p1397(c: Cast) -> None:
    c.note("p1397: +2 to Charisma checks for each target until your next turn ends")


@power(
    "p1506",
    level=6,
    cls="rogue",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="you are hidden and lose cover or concealment against an enemy",
    out_of_combat=True,
)
def p1506(c: Cast) -> None:
    c.note("p1506: stay hidden from that enemy, and need no cover to stay so")


MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _would_hit_my_body(world: World, me: int, ev: Event) -> bool:
    """Hit by an attack against AC or Reflex, read on the roll -- the window
    where the defence is looked at again."""
    return would_hit_me(world, me, ev) and getattr(ev, "vs", None) in (AC, REF)


def _my_melee_crit(world: World, me: int, ev: Event) -> bool:
    return (
        getattr(ev, "attacker", None) == me
        and bool(getattr(ev, "critical", False))
        and by_melee(world, me, ev)
    )


def _i_felled_it(world: World, me: int, ev: Event) -> bool:
    """"Reduce an enemy to 0 hit points with a melee attack."

    `Dropped` names only who went down, so who put them there is read off
    the `DamageApplied` that did it.
    """
    who = getattr(ev, "actor", None)
    if who is None or team(world, who) is team(world, me):
        return False
    for e in reversed(world.bus.log):
        if e.kind == "DamageApplied" and getattr(e, "target", None) == who:
            return getattr(e, "source", None) == me and by_melee(world, me, e)
    return False


def _ally_closed_on_my_enemy(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is not team(world, me):
        return False
    return any(
        adjacent(world, me, foe) and adjacent(world, who, foe)
        for foe in enemies(world, me)
    )


@power(
    "p10172",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_WEAPON,
    requires=_light_blade,
    requires_text="needs a light blade",
    trigger="you are hit by a melee attack",
    on=Trigger(
        AttackRolled, both(would_hit_me, by_melee), "you are hit by a melee attack"
    ),
)
def p10172(c: Cast) -> None:
    """Raised on the roll, which is where the defence is read again, so the
    bonus reaches the very attack that triggered it -- the reading `p1043`
    settled. `once=True` spends it when that blow lands or misses."""
    for wall in (AC, FORT, REF, WILL):
        c.bonus(wall, c.cha_mod, on=c.me, until=When.EOT, once=True)
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None:
        c.grants_advantage(on=attacker)


@power(
    "p10762",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p10762(c: Cast) -> None:
    me = c.me
    seen = sorted(foe for foe in c.enemies() if c.can_see(foe))
    chosen = c.choose(seen, "who loses sight of you") if seen else None
    if chosen is not None:
        c.penalty(
            "attack", 2, on=chosen, until=When.EONT,
            when=lambda ctx: ctx.get("target") == me,
        )


@power(
    "p10763",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL,
)
def p10763(c: Cast) -> None:
    if c.target is not None and c.can_see(c.target):
        c.grants_advantage()


@power(
    "p10764",
    level=6,
    cls="rogue",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.MARTIAL, Keyword.FEAR],
    trigger=(
        "you score a critical hit against an enemy with a melee attack "
        "or reduce an enemy to 0 hit points with a melee attack"
    ),
    on=[
        Trigger(Hit, _my_melee_crit, "you score a critical hit with a melee attack"),
        Trigger(
            Dropped, _i_felled_it, "you reduce an enemy to 0 hit points with a melee attack"
        ),
    ],
)
def p10764(c: Cast) -> None:
    c.penalty("attack", 2)
    c.grants_advantage(to="allies")


@power(
    "p12724",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="you are hit by an attack against your AC or Reflex",
    on=Trigger(
        AttackRolled,
        _would_hit_my_body,
        "you are hit by an attack against your AC or Reflex",
    ),
)
def p12724(c: Cast) -> None:
    """The halving is written on `DamageRolled`, which carries a mutable
    amount and is emitted before the blow lands. The latch is kept by hand:
    `once=` on a watch spends on the log growing, and changing a number
    logs nothing."""
    me = c.me
    spent: list[bool] = []

    def halve(ev: DamageRolled) -> None:
        if spent or ev.target != me:
            return
        spent.append(True)
        ev.amount //= 2

    c.watch(
        DamageRolled, halve, until=When.EOT, window=Window.BEFORE, on=c.me,
        label=f"{c.ref} halves",
    )


@power(
    "p2289",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p2289(c: Cast) -> None:
    """The longer duration is for a target already carrying the penalty from
    one of the rogue's rattling attacks, which the model has no keyword for,
    so what is written is the base line."""
    seen = sorted(foe for foe in c.enemies() if c.can_see(foe))
    chosen = c.choose(seen, "who you have read") if seen else None
    if chosen is not None:
        c.grants_advantage(on=chosen, until=When.SONT)


@power(
    "p4483",
    level=6,
    cls="rogue",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="a melee or a ranged attack misses you",
    on=Trigger(Miss, targets_me, "a melee or a ranged attack misses you"),
)
def p4483(c: Cast) -> None:
    """A reaction runs after the attack has resolved, so "the target is also
    targeted by the triggering attack" is that attack being made again at
    the new creature -- the row it was, where that row can still be used,
    and the attacker's basic where it cannot.

    The creature is chosen in the body rather than declared as a target: the
    dispatcher aims a single-enemy row at whoever caused the event, and the
    printed line says explicitly that this one is somebody else.
    """
    attacker = getattr(c.trigger, "attacker", None)
    pool = sorted(x for x in c.within(1) if x not in (c.me, attacker))
    victim = c.choose(pool, "who the blow finds instead") if pool else None
    if victim is not None and attacker is not None:
        row = getattr(c.trigger, "power", "") or ""
        if not c.grant_attack(attacker, on=victim, ref=row):
            c.grant_attack(attacker, on=victim)
    c.shift(1)


@power(
    "p4484",
    level=6,
    cls="rogue",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p4484(c: Cast) -> None:
    """"While you can see the enemy" is asked of the attack rather than
    stored, because both creatures move. Choosing a new enemy is using the
    row again, and taking a stance ends the one before it."""
    c.stance()
    seen = sorted(foe for foe in c.within(5, side="enemy") if c.can_see(foe))
    chosen = c.choose(seen, "who you keep your eye on") if seen else None
    if chosen is None:
        return

    def watched(ctx: dict) -> bool:
        return ctx.get("attacker") == chosen and c.can_see(chosen)

    c.bonus(AC, 2, on=c.me, until=When.STANCE, when=watched)


@power(
    "p4485",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.FEAR],
)
def p4485(c: Cast) -> None:
    """Two halves of one line. `DamageRolled` says nothing about what kind
    of attack dealt it, so the opportunity attacks are noted as they are
    declared and the halving reads that list."""
    me = c.me
    reckless: list[int] = []

    def noticed(ev: AttackDeclared) -> None:
        if ev.target == me and getattr(ev, "opportunity", False):
            reckless.append(ev.attacker)
            c.grants_advantage(on=ev.attacker)

    def halve(ev: DamageRolled) -> None:
        if ev.target == me and ev.source in reckless:
            ev.amount //= 2

    c.watch(
        AttackDeclared, noticed, until=When.EOT, window=Window.BEFORE, on=c.me,
        label=f"{c.ref} sees them coming",
    )
    c.watch(
        DamageRolled, halve, until=When.EOT, window=Window.BEFORE, on=c.me,
        label=f"{c.ref} halves",
    )


@power(
    "p4486",
    level=6,
    cls="rogue",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p4486(c: Cast) -> None:
    """The way out of the stance is an Athletics check to jump, and the
    model has neither, so what is written is the bonus and the stance."""
    c.stance()
    c.bonus(REF, 1, on=c.me, until=When.STANCE)


@power(
    "p4487",
    level=6,
    cls="rogue",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger="an ally enters a square adjacent to an enemy adjacent to you",
    on=Trigger(
        EnterSquare,
        _ally_closed_on_my_enemy,
        "an ally enters a square adjacent to an enemy adjacent to you",
    ),
)
def p4487(c: Cast) -> None:
    """"Any other square adjacent to the enemy" names its destination, so it
    is aimed rather than handed to the decider."""
    mover = getattr(c.trigger, "actor", None)
    together = sorted(
        foe
        for foe in c.enemies()
        if c.adjacent(foe) and (mover is None or adjacent(c.world, mover, foe))
    )
    foe = c.choose(together, "which of them you slip round") if together else None
    if foe is None:
        return
    standing = squares_of(c.world, foe)
    room = sorted(
        sq
        for sq in spread(standing, 1) - standing
        if sq != c.here
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    )
    where = c.choose(room, "where you come round to") if room else None
    if where is not None:
        c.shift(to=where)
