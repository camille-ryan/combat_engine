"""Bard, level 9: the dailies."""

from __future__ import annotations

from combat_engine.content.powers.bard._shared import free_near, gap, square_of
from combat_engine.engine import *
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]
ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]
MISFORTUNES = ("slowed", "psychic damage", "combat advantage")


def _no_opportunities(c: Cast, victim: int, until: When) -> None:
    """"The target can't take opportunity actions."

    Vetoed at the window rather than by taking a row away: an opportunity
    attack is whichever row the creature uses, and `c.no_provoke` is the other
    end of the same sentence -- it protects a mover, not this.
    """

    def veto(ev: OpportunityWindow) -> None:
        if ev.actor == victim:
            ev.cancel("the target cannot take opportunity actions")

    c.watch(
        OpportunityWindow, veto, until=until, window=Window.BEFORE, on=victim,
        label=f"{c.ref} no opportunities",
    )


@power(
    "p2977",
    level=9,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE_IMPLEMENT,
)
def p2977(c: Cast) -> None:
    """The hold is the whole of what the minor action buys. The opportunity
    attack printed beside it is `p2977b`, which reads this hold as its
    Requirement -- the attack line went with it."""
    c.effect(c.ref, until=When.SUSTAIN, on=c.me, sustain=MINOR)


@power(
    "p2979",
    level=9,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(CHA, vs=WILL),
)
def p2979(c: Cast) -> None:
    """The zone's own effect is what `c.on_sustain` hangs the re-choice on --
    `c.zone` hands back an entity id, and the hold lives on the zone."""
    if c.strike():
        c.damage("1d10", c.cha_mod)
    else:
        c.half_damage("1d10", c.cha_mod)
    if not c.first:
        return
    ring = c.zone(c.area(), label="p2979", until=When.SUSTAIN, sustain=MINOR)
    picked = [c.choose(list(MISFORTUNES), "which misfortune") or MISFORTUNES[0]]

    def bite(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        if picked[0] == "slowed":
            c.slowed(on=ev.actor, until=When.EOTNT)
        elif picked[0] == "psychic damage":
            c.flat(c.cha_mod, dtype=DamageType.PSYCHIC, on=ev.actor)
        else:
            c.grants_advantage(on=ev.actor, to="allies", until=When.EOTNT)

    def rechoose() -> None:
        picked[0] = c.choose(list(MISFORTUNES), "which misfortune") or picked[0]

    c.watch(TurnStart, bite, until=When.ENCOUNTER, on=c.me, label="p2979")
    zone = c.world.get(ring, Zone)
    c.on_sustain(zone.effect if zone is not None else None, rechoose)


@power(
    "p3464",
    level=9,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=REF),
)
def p3464(c: Cast) -> None:
    """The Effect is dropped: it hands the ally a move action it does not have,
    and nothing grants an action."""
    if c.strike():
        c.damage(c.w(3), c.cha_mod)


@power(
    "p4999",
    level=9,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p4999(c: Cast) -> None:
    """The hold goes on; the ally attacking from the target's square does not.
    `c.strike(from_=)` moves the caster's own swing and there is no way to
    lend that to somebody else."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.effect("p4999", until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)


@power(
    "p5000",
    level=9,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p5000(c: Cast) -> None:
    """The aftereffect is dropped -- a hold that begins when another one is
    saved against has nowhere to be declared."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", 2, on=victim, until=When.SAVE_ENDS)
        _no_opportunities(c, victim, When.SAVE_ENDS)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        _no_opportunities(c, victim, When.EONT)


@power(
    "p5001",
    level=9,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.THUNDER],
    attack=Attack(CHA, vs=AC),
)
def p5001(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.cha_mod, dtype=DamageType.THUNDER)
        c.slide(2)

    def herd(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        row = get(ev.power)
        if row is None or row.usage is not Usage.AT_WILL:
            return
        mates = [a for a in c.allies() if a != c.me]
        for mate in sorted(mates, key=lambda a: gap(c, a, ev.target)):
            spot = free_near(c, square_of(c, mate))
            if spot is not None:
                c.slide(2, on=ev.target, to=spot)
                return

    c.watch(Hit, herd, until=When.ENCOUNTER, on=c.me, label="p5001")


@power(
    "p5695",
    level=9,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p5695(c: Cast) -> None:
    """The concealment clause is dropped; the combat advantage is the half that
    can be said."""
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage("2d6", c.cha_mod, dtype=DamageType.RADIANT)
    c.grants_advantage(to="allies", until=When.SAVE_ENDS)


@power(
    "p5696",
    level=9,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.HEALING],
    attack=Attack(CHA, vs=AC),
)
def p5696(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.cha_mod)
    else:
        c.half_damage(c.w(3), c.cha_mod)
    mend = c.cha_mod

    def reward(ev: Hit) -> None:
        if ev.target != victim or ev.attacker not in c.allies():
            return
        if c.may("regain hit points rather than roll a saving throw", who=ev.attacker):
            c.heal(mend, on=ev.attacker)
        else:
            c.save(on=ev.attacker)

    c.watch(Hit, reward, until=When.ENCOUNTER, on=c.me, label="p5696")


@power(
    "p5701",
    level=9,
    cls="bard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=WILL),
)
def p5701(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("2d8", c.cha_mod)
    else:
        c.half_damage("2d8", c.cha_mod)
    held = c.effect("p5701", on=victim, until=When.SAVE_ENDS)
    if held is None:
        return

    def opening(ev: Miss) -> None:
        if ev.attacker != victim or held.ended:
            return
        for who in [c.me, *c.allies()]:
            if gap(c, who, victim) <= 1:
                c.provoke(who, on=victim, why="p5701")

    c.watch(Miss, opening, until=When.ENCOUNTER, on=c.me, label="p5701")
