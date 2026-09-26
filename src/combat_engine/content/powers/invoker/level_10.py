"""Invoker, level 10: the utilities."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    DamageApplied,
    Health,
    Hit,
    Keyword,
    Miss,
    PowerUsed,
    Ranged,
    Summon,
    SurgeSpent,
    Trigger,
    When,
    both,
    enemy_within,
    get,
    hits_me,
    power,
)


def _my_area_power(world: Any, me: int, ev: Any) -> bool:
    """"You use an area or a close attack power." `by_melee` lumps close
    attacks in with melee ones and `by_ranged` lumps areas in with ranged
    ones, so neither says this."""
    if getattr(ev, "actor", None) != me:
        return False
    p = get(getattr(ev, "power", ""))
    return p is not None and p.reach.kind in (
        "area_burst",
        "close_burst",
        "close_blast",
    )


@power(
    "p11298",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.ZONE],
)
def p11298(c: Cast) -> None:
    """A zone that stays centred on the caster is an aura, and an aura
    takes no `blocks_sight`, so the heavily obscured half of the printed
    line is not written -- the moving half is the one the row is for."""
    swarm = c.aura(3, until=When.SUSTAIN, sustain=MINOR)

    def bite(ev: Bloodied, z: int = swarm) -> None:
        if ev.actor in c.world.zones.occupants(z):
            c.dazed(on=ev.actor, until=When.EOTNT)

    c.watch(Bloodied, bite, until=When.ENCOUNTER)


@power(
    "p2886",
    level=10,
    cls="invoker",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.FEAR],
    trigger="an enemy within 5 squares of you makes an attack roll against you",
    on=Trigger(
        AttackDeclared,
        both(hits_me, enemy_within(5)),
        "an enemy within 5 squares attacks you",
    ),
)
def p2886(c: Cast) -> None:
    """The shove waits for the attack to finish, which is both outcomes of
    it, so the latch is shared between the two watches."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    if foe is None:
        return
    c.penalty("attack", 2, on=foe, until=When.EOT, once=True)
    shoved: list[int] = []

    def recoil(after: Hit | Miss, by: int = foe) -> None:
        if shoved or getattr(after, "attacker", None) != by:
            return
        shoved.append(1)
        c.push(3, on=by)

    c.watch(Hit, recoil, until=When.EOT)
    c.watch(Miss, recoil, until=When.EOT)


@power(
    "p3351",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.DIVINE],
)
def p3351(c: Cast) -> None:
    """Nothing announces an ally being *offered* a surge, only one being
    spent, so this answers the spend: the ally's surge goes back into its
    pool and the caster's comes out instead, which leaves the board where
    the printed line leaves it."""

    def cover(ev: SurgeSpent) -> None:
        who = ev.actor
        if who == c.me or who not in c.within(10, side="ally"):
            return
        if not c.may("spend a surge on that ally's behalf", who=c.me, default=False):
            return
        if not c.spend_surge(on=c.me):
            return
        theirs = c.world.get(who, Health)
        if theirs is not None:
            theirs.surges += 1

    c.watch(SurgeSpent, cover, until=When.ENCOUNTER)


@power(
    "p7193",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.ZONE],
)
def p7193(c: Cast) -> None:
    """Written to the erratum: the bonus lasts to the *end* of the ally's
    next turn. It is gated on the attacker, so it only helps against the
    creature that dealt the damage."""
    ground = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR)
    mine = {c.me, *c.allies()}

    def avenge(ev: DamageApplied, z: int = ground) -> None:
        mate = ev.target
        if mate not in mine or mate not in c.world.zones.occupants(z):
            return
        c.bonus(
            "attack",
            2,
            on=mate,
            kind="power",
            until=When.EOTNT,
            when=lambda ctx, foe=ev.source: ctx.get("target") == foe,
        )

    c.watch(DamageApplied, avenge, until=When.ENCOUNTER)


@power(
    "p7194",
    level=10,
    cls="invoker",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE],
    trigger="you use an area or a close attack power and an ally is in the area",
    on=Trigger(PowerUsed, _my_area_power, "you use an area or a close attack power"),
)
def p7194(c: Cast) -> None:
    """`PowerUsed` carries the targets but not the origin, so the second
    half of the printed trigger -- the ally standing *in* the area -- has
    nothing to measure against and is not declared; the burst 10 target
    line carries the rest of it."""
    c.shift(c.int_mod, who=c.target)


@power(
    "p11296",
    level=10,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
    summon=Summon(speed=6, modes=("fly",)),
)
def p11296(c: Cast) -> None:
    """Its one command heals rather than attacks, and `c.command` rolls the
    header's `summon=` attack line, so there is nothing for it to read. The
    command is dropped -- see the report -- and what is written is the creature
    arriving. `Summon.modes` carries no speed, so the printed "fly 8" is set
    from the body."""
    angel = c.summon_inline(get(c.ref).summon, at=c.origin)
    if angel:
        c.mode("fly", 8, on=angel, until=When.ENCOUNTER)
