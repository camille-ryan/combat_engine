"""Invoker, level 6: the utilities."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    ANY_CREATURE,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageApplied,
    DamageRolled,
    Defense,
    Keyword,
    PowerUsed,
    Ranged,
    SavingThrow,
    Trigger,
    TurnStart,
    Usage,
    When,
    both,
    by_melee,
    by_ranged,
    either,
    enemy_within,
    get,
    hits_me,
    power,
)
from combat_engine.engine.query import distance_between, team


def _at_my_ally(world: Any, me: int, ev: Any) -> bool:
    """Aimed at somebody on my side who is not me. `targets_my_side`
    counts the caster, and both rows here print "your ally"."""
    who = getattr(ev, "target", None)
    return who is not None and who != me and team(world, who) is team(world, me)


def _near_me(squares: int) -> Callable[[Any, int, Any], bool]:
    """Whoever the event is about is within range -- either side of the
    fight, which no ready-made predicate says."""

    def check(world: Any, me: int, ev: Any) -> bool:
        who = getattr(ev, "actor", None)
        return who is not None and distance_between(world, me, who) <= squares

    return check


def _my_ally_hurt_near_me(world: Any, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    return _at_my_ally(world, me, ev) and distance_between(world, me, who) <= 10


@power(
    "p11290",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE, Keyword.STANCE],
)
def p11290(c: Cast) -> None:
    c.stance(label=c.ref)

    def bless(ev: PowerUsed) -> None:
        if ev.actor != c.me:
            return
        p = get(ev.power)
        if p is None or p.cls != "invoker":
            return
        if p.usage not in (Usage.ENCOUNTER, Usage.DAILY):
            return
        mates = [a for a in c.within(10, side="ally") if a != c.me and c.can_see(a)]
        picked = c.choose(mates, "who is shielded") if mates else None
        if picked is None:
            return
        for d in Defense:
            c.bonus(d, 2, on=picked, until=When.EONT)

    c.watch(PowerUsed, bless, until=When.STANCE)


@power(
    "p2862",
    level=6,
    cls="invoker",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE],
    trigger="an enemy within 10 squares of you makes an attack roll against your ally",
    on=Trigger(
        AttackDeclared,
        both(enemy_within(10), _at_my_ally),
        "an enemy within 10 squares attacks your ally",
    ),
)
def p2862(c: Cast) -> None:
    """The penalty is spent on the one roll it is printed for -- `once=True`
    on an attack modifier ends it when the die is read -- and the slide
    waits for the damage rather than for the hit, because the printed line
    says "hits and deals damage"."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    mate = getattr(ev, "target", None)
    if foe is None or mate is None:
        return
    c.penalty("attack", 3, on=foe, until=When.EOT, once=True)

    def steady(hurt: DamageApplied, who: int = mate, by: int = foe) -> None:
        if hurt.source == by and hurt.target == who:
            c.slide(1, on=who)

    c.watch(DamageApplied, steady, until=When.EOT, once=True)


@power(
    "p2883",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=MOVE,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE, Keyword.TELEPORTATION],
)
def p2883(c: Cast) -> None:
    far = 3 + c.int_mod if c.build("preservation") else 3
    c.teleport(far, who=c.target)


@power(
    "p2884",
    level=6,
    cls="invoker",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ANY_CREATURE,
    keywords=[Keyword.DIVINE],
    trigger="a creature within 10 squares of you makes a saving throw",
    on=Trigger(
        SavingThrow, _near_me(10), "a creature within 10 squares makes a saving throw"
    ),
)
def p2884(c: Cast) -> None:
    """`SavingThrow` is announced before it is acted on and the result is
    read back off the event, which is the only way to say "rerolls and must
    use the new result" -- `c.unsave` only forces a failure."""
    ev = c.trigger
    if ev is None:
        return
    ev.natural = c.roll("1d20")
    ev.saved = ev.natural + ev.bonus >= 10


@power(
    "p2885",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.CONJURATION],
)
def p2885(c: Cast) -> None:
    """The symbol's 5-square reach is an aura hung on the conjuration, so
    "within 5 squares of the symbol" is a membership test rather than a
    distance measured from the caster."""
    symbol = c.conjure(at=c.origin, until=When.SUSTAIN, sustain=MINOR)
    ring = c.aura(5, on=symbol, until=When.SUSTAIN, sustain=MINOR)
    for mate in (c.me, *c.allies()):
        c.bonus(
            "save",
            2,
            on=mate,
            kind="power",
            until=When.ENCOUNTER,
            when=lambda ctx, w=mate, z=ring: w in c.world.zones.occupants(z),
        )

    def comfort(ev: TurnStart, z: int = ring) -> None:
        if ev.ghost:
            return
        if ev.actor in (c.me, *c.allies()) and ev.actor in c.world.zones.occupants(z):
            c.temp_hp(5, on=ev.actor)

    c.watch(TurnStart, comfort, until=When.ENCOUNTER)


@power(
    "p3348",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
    trigger="an ally within 10 squares of you takes damage from an attack",
    on=Trigger(
        DamageRolled, _my_ally_hurt_near_me, "an ally within 10 squares takes damage"
    ),
)
def p3348(c: Cast) -> None:
    """`c.absorb` moves the damage and leaves everything else the attack
    did where it landed, which is exactly what the printed line asks."""
    ev = c.trigger
    if ev is None:
        return
    pool = [c.me, *[a for a in c.within(10, side="ally") if a != c.me]]
    bearer = c.choose(pool, "who takes it instead")
    if bearer is not None:
        c.absorb(ev, on=bearer)


@power(
    "p7177",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p7177(c: Cast) -> None:
    """Held as an aura so that an ally who steps in later is covered and
    everyone loses it together when the aura lapses."""
    ring = c.aura(1, until=When.SUSTAIN, sustain=MINOR)
    for mate in (c.me, *c.allies()):
        for d in (Defense.AC, Defense.REF):
            c.bonus(
                d,
                2,
                on=mate,
                until=When.ENCOUNTER,
                when=lambda ctx, w=mate, z=ring: w in c.world.zones.occupants(z),
            )


@power(
    "p7178",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.CONJURATION],
)
def p7178(c: Cast) -> None:
    """"In the angel's space or adjacent to it" is an aura of 1 on the
    conjuration. Dismissing the angel to halve a blow is a second, printed
    immediate interrupt and is not this row."""
    angel = c.conjure(at=c.origin, until=When.SUSTAIN, sustain=MINOR, speed=5)
    ring = c.aura(1, on=angel, until=When.SUSTAIN, sustain=MINOR)
    for mate in (c.me, *c.allies()):
        c.bonus(
            "ac",
            2,
            on=mate,
            kind="power",
            until=When.ENCOUNTER,
            when=lambda ctx, w=mate, z=ring: w in c.world.zones.occupants(z),
        )


@power(
    "p7179",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
    trigger="an enemy makes a melee or a ranged attack roll against you",
    on=Trigger(
        AttackDeclared,
        both(hits_me, either(by_melee, by_ranged)),
        "an enemy makes a melee or ranged attack against you",
    ),
)
def p7179(c: Cast) -> None:
    c.temp_hp(5 + c.wis_mod, on=c.me)
    c.bonus("ac", 2, on=c.me, kind="power", until=When.EONT)


@power(
    "p7180",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=CloseBlast(3),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.ZONE],
)
def p7180(c: Cast) -> None:
    """Growing the blast by 1 when sustained is not written: a zone's
    squares are fixed when it is made."""
    c.zone(
        c.area(),
        until=When.SUSTAIN,
        sustain=MINOR,
        difficult=True,
        blocks_sight=True,
    )


@power(
    "p11291",
    level=6,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p11291(c: Cast) -> None:
    """Both printed sentences are the one restore. A channel divinity row is
    held down by `group=CHANNEL_DIVINITY`, which refuses a second one while
    any sibling counts as used -- so handing the use back is also what lets
    the allowance be spent again, and there is nothing else to say."""
    spent = c.expended(group=CHANNEL_DIVINITY)
    if not spent:
        return
    pick = c.choose(spent, "p11291: which expended row comes back")
    if pick is not None:
        c.restore_use(pick)
