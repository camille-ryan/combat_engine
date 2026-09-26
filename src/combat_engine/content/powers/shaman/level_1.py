"""Shaman, level 1.

The spirit companion exists now -- `c.companion`, `c.call_companion`,
`c.dismiss_companion`, `c.move_companion` and `reach=Melee(1,
from_="companion")` -- so the rows that are built round it are here with
the rest. "Melee spirit 1" is the header range measured from the spirit;
the roll is the shaman's, taken `from_` the spirit's square.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageRolled,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    UpTo,
    When,
    Window,
    power,
    spread,
)

from ._spirit import (
    at_range,
    beside,
    beside_spirit,
    catches_spirit,
    friends,
    granted_hit,
    pick_foe,
    send_spirit,
)

PRIMAL = [Keyword.PRIMAL]
PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
SPIRIT_MELEE = Melee(1, from_="companion")


@power(
    "p3876",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p3876(c: Cast) -> None:
    """The zone is laid down where the target stood. Its two printed clauses
    are both grants of an action -- move the zone, slide everyone in it --
    and there is no verb for either, so the zone itself is all of it."""
    at = c.there
    if c.strike():
        c.damage("2d10", c.wis_mod)
        c.slide(2)
    else:
        c.half_damage("2d10", c.wis_mod)
    if at is not None:
        c.zone(spread({at}, 1), until=When.ENCOUNTER)


@power(
    "p3886",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.COLD],
    attack=Attack(WIS, vs=FORT),
)
def p3886(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("1d10", c.wis_mod, dtype=DamageType.COLD)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me:
                c.save(on=mate, bonus=5)


@power(
    "p4783",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p4783(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.PSYCHIC)
        mate = c.choose(c.allies(), "who the target grants combat advantage to")
        if mate is not None:
            c.grants_advantage(until=When.EONT, to=mate)


@power(
    "p5393",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.HEALING],
    attack=Attack(WIS, vs=FORT),
)
def p5393(c: Cast) -> None:
    """Regeneration has no verb of its own, so it is a watch on the
    beneficiary's own turn start, gated on being bloodied. The printed
    escape clause -- end it as a minor action for 10 hit points -- is a
    minor action nobody can spend, and is dropped."""
    if c.strike():
        c.damage("1d8", c.wis_mod)
    else:
        c.half_damage("1d8", c.wis_mod)
    if not c.first:
        return
    for mate in dict.fromkeys([c.me, *c.in_squares(c.area(), side="ally")]):

        def tick(ev: object, who: int = mate) -> None:
            if getattr(ev, "actor", None) == who and c.bloodied(on=who):
                c.heal(2, on=who)

        c.watch(TurnStart, tick, until=When.ENCOUNTER, on=mate)


@power(
    "p5554",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.POISON],
    attack=Attack(WIS, vs=REF),
)
def p5554(c: Cast) -> None:
    """"Until this ongoing damage ends" is read off the burn itself rather
    than given its own clock -- the allies' bonus is held for the encounter
    and gated on the hold still being live."""
    victim = c.target
    if not c.strike():
        return
    c.damage("2d8", c.wis_mod)
    burn = c.ongoing(5, DamageType.POISON)
    if burn is None or victim is None:
        return
    for mate in c.allies():
        c.bonus(
            "attack", 2, on=mate, until=When.ENCOUNTER, kind="power",
            when=lambda ctx, v=victim, b=burn: (
                ctx.get("target") == v and not b.ended
            ),
        )


@power(
    "p9743",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p9743(c: Cast) -> None:
    """"Difficult terrain for your enemies" is one rough zone plus everyone
    on my side ignoring that label. The cover the zone grants has no verb
    and is left out; the slide does not force the square outside the burst,
    which the world's decider picks."""
    if c.first:
        c.zone(c.area(), until=When.ENCOUNTER, difficult=c.ref)
        for mate in dict.fromkeys([c.me, *c.allies()]):
            c.ignores_difficult(c.ref, on=mate, until=When.ENCOUNTER)
    if c.strike():
        c.slide(2)
        c.prone()
    else:
        c.slide(1)


# -- the rows built round the spirit ----------------------------------------


@power(
    "p11357",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1, from_="companion"),
    target=EACH_ENEMY,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p11357(c: Cast) -> None:
    """Cover has no verb of its own. What it is printed as is -2 to the
    attacker's roll, so it is written here as +2 to the ally's defences
    against anything thrown, close or area -- and gated on the ally still
    standing beside the spirit, which is how the printed line reads."""
    if c.strike(from_=c.companion()):
        c.damage("1d6", c.wis_mod)
        c.prone()
    if not c.first:
        return
    for mate in friends(c):
        for what in (AC, FORT, REF, WILL):
            c.bonus(
                what, 2, on=mate, until=When.ENCOUNTER, kind="cover",
                when=lambda ctx, w=mate: at_range(ctx) and beside_spirit(c, w),
            )


@power(
    "p11363",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(WIS, vs=WILL),
)
def p11363(c: Cast) -> None:
    """The penalty is an Effect line, so it lands whether the attack did or
    not, and it is read off whoever the target swings at."""
    victim = c.target
    if c.strike(from_=c.companion()):
        c.damage("2d6", c.wis_mod, dtype=DamageType.PSYCHIC)
    if victim is not None:
        c.penalty(
            "attack", 2, on=victim, until=When.EONT,
            when=lambda ctx: beside_spirit(c, ctx.get("target")),
        )


@power(
    "p12866",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p12866(c: Cast) -> None:
    mate = c.target
    c.dismiss_companion()
    foe = pick_foe(c, mate)
    if mate is not None and foe is not None:
        c.grant_attack(mate, on=foe, attack_bonus=2, damage_bonus=c.int_mod)


@power(
    "p12867",
    level=1,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.FIRE],
    attack=Attack(WIS, vs=REF),
)
def p12867(c: Cast) -> None:
    """"Can choose to deal fire damage" is the type on the damage as it is
    rolled, rewritten in the interrupt window; the choice is taken as made,
    since that is what the row was used for."""
    burning = [c.me, *beside(c)] if c.build("elemental") else []
    if c.strike(from_=c.companion()):
        c.damage("1d8", c.wis_mod, dtype=DamageType.FIRE)
        c.vulnerable(5, DamageType.FIRE, until=When.EONT)
    for who in dict.fromkeys(burning):

        def recolour(ev: Any, w: int = who) -> None:
            if ev.source == w:
                ev.dtype = DamageType.FIRE

        c.watch(
            DamageRolled, recolour, until=When.EONT, on=who, window=Window.BEFORE
        )
    c.dismiss_companion()


@power(
    "p12868",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1, from_="companion"),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p12868(c: Cast) -> None:
    """The zone goes down before the spirit does, since the burst is
    measured from the spirit. "Heavily obscured" is the sight-blocking
    flag; `c.burns` also bites on entering the zone, which is the nearest
    the engine has to "starts its turn within"."""
    if c.first:
        fog = c.zone(c.area(), until=When.EONT, blocks_sight=True, sustain=MINOR)
        c.burns(fog, 5)
    if c.strike(from_=c.companion()):
        c.blinded(until=When.SAVE_ENDS)
    else:
        c.penalty("attack", 2, until=When.EONT)
    if c.last:
        c.dismiss_companion()


@power(
    "p3778",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p3778(c: Cast) -> None:
    """The Perception half of the printed bonus is a skill check and has
    nowhere to go."""
    if not c.strike(from_=c.companion()):
        return
    c.damage("2d8" if c.level >= 21 else "1d8", c.wis_mod)
    for mate in friends(c, with_me=True):
        c.bonus(
            "attack", 1, on=mate, until=When.EONT, kind="untyped",
            when=lambda ctx, w=mate: beside_spirit(c, w),
        )


@power(
    "p3780",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p3780(c: Cast) -> None:
    if not c.strike(from_=c.companion()):
        return
    c.damage("2d8" if c.level >= 21 else "1d8", c.wis_mod)
    for mate in friends(c, with_me=True):
        c.bonus(
            AC, 1, on=mate, until=When.EONT,
            when=lambda ctx, w=mate: beside_spirit(c, w), kind="power")


@power(
    "p3783",
    level=1,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p3783(c: Cast) -> None:
    """`c.grants_advantage` takes no gate, so the advantage is handed out
    against the enemies standing by the spirit when the row goes off rather
    than read continuously, and the melee-only restriction goes with it.
    The second swing is the printed Effect."""
    if c.strike():
        c.damage("1d8", c.wis_mod)
    for foe in beside(c, "enemy"):
        c.grants_advantage(on=foe, until=When.EONT, to="allies")
    again = c.choose(c.enemies(), "who the second attack is aimed at")
    if again is not None and c.strike(on=again):
        c.damage("1d8", c.wis_mod, on=again)


@power(
    "p3784",
    level=1,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p3784(c: Cast) -> None:
    if not c.strike(from_=c.companion()):
        return
    c.damage("2d8", c.wis_mod)
    for mate in friends(c, with_me=True):
        for what in (AC, FORT, REF, WILL):
            c.bonus(
                what, 5, on=mate, until=When.EONT, kind="untyped",
                when=lambda ctx, w=mate: (
                    bool(ctx.get("opportunity")) and beside_spirit(c, w)
                ),
            )


@power(
    "p3786",
    level=1,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p3786(c: Cast) -> None:
    if not c.strike(from_=c.companion()):
        return
    c.damage("1d10", c.wis_mod)
    for mate in friends(c, with_me=True):
        for what in (AC, FORT, REF, WILL):
            c.bonus(
                what, 2, on=mate, until=When.EONT,
                when=lambda ctx, w=mate: beside_spirit(c, w), kind="power")


@power(
    "p3878",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p3878(c: Cast) -> None:
    """The printed target line is two pools -- the burst, and everything
    standing by the spirit. The header carries the burst; the second pool
    is attacked by hand, once, and only for whoever the burst missed."""
    if c.strike():
        c.damage("3d6", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.prone()
    else:
        c.half_damage("3d6", c.wis_mod, dtype=DamageType.PSYCHIC)
    if not c.first:
        return
    for foe in beside(c, "enemy"):
        if foe in c.targets:
            continue
        if c.strike(on=foe):
            c.damage("3d6", c.wis_mod, dtype=DamageType.PSYCHIC, on=foe)
            c.prone(on=foe)
        else:
            c.half_damage("3d6", c.wis_mod, dtype=DamageType.PSYCHIC, on=foe)


@power(
    "p5391",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.COLD, Keyword.TELEPORTATION],
    attack=Attack(WIS, vs=FORT),
)
def p5391(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("2d10" if c.level >= 21 else "1d10", c.wis_mod, dtype=DamageType.COLD)
        send_spirit(c, victim)


@power(
    "p5392",
    level=1,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(WIS, vs=FORT),
)
def p5392(c: Cast) -> None:
    """`c.resist` takes no gate, so the resistance goes to whoever is
    standing by the spirit as the row goes off rather than being read
    continuously."""
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.THUNDER)
        if c.con_mod > 0:
            for mate in dict.fromkeys([c.me, *beside(c)]):
                c.resist(c.con_mod, on=mate, until=When.EONT)
    if not c.build("protector"):
        return
    spirit = c.companion()
    pool = [c.me, *[a for a in c.within(5, side="ally") if a != spirit]]
    who = c.choose(list(dict.fromkeys(pool)), "who gains temporary hit points")
    if who is not None:
        c.temp_hp(c.con_mod, on=who)


@power(
    "p5432",
    level=1,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p5432(c: Cast) -> None:
    """"Slowed during that turn" is the hold ending with the turn it began
    in, which is `When.EOT` read from the creature that just started."""
    if not c.strike():
        return
    c.damage("2d6", c.wis_mod)

    def grip(ev: Any) -> None:
        foe = getattr(ev, "actor", None)
        if foe not in c.enemies() or not beside_spirit(c, foe):
            return
        if c.build("world speaker"):
            c.immobilized(on=foe, until=When.EOT)
        else:
            c.slowed(on=foe, until=When.EOT)

    c.watch(TurnStart, grip, until=When.EONT, on=c.me)


@power(
    "p5440",
    level=1,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p5440(c: Cast) -> None:
    """A mark belongs to whoever is named, so this one is the spirit's. The
    build clause raises the standing -2 to 1 + Constitution, which is the
    difference laid on top, gated the way a mark's penalty is: it costs the
    target only when it leaves its marker out."""
    spirit = c.companion()
    victim = c.target
    if not c.strike(from_=spirit) or victim is None:
        return
    c.damage("2d6", c.wis_mod)
    c.mark(until=When.EONT, by=spirit if spirit is not None else c.me)
    extra = (1 + c.con_mod) - 2
    if c.build("protector") and extra > 0 and spirit is not None:
        c.penalty(
            "attack", extra, on=victim, until=When.EONT,
            when=lambda ctx, s=spirit: ctx.get("target") != s,
        )


@power(
    "p5451",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p5451(c: Cast) -> None:
    """Three payouts, growing, then the effect is spent: the count is the
    hold, and the watch stops paying once it reaches three."""
    if c.strike():
        c.damage("2d10", c.wis_mod)
    paid = [0]

    def swell(ev: Any) -> None:
        if paid[0] >= 3 or ev.attacker not in friends(c):
            return
        if ev.target not in c.enemies() or not beside_spirit(c, ev.target):
            return
        paid[0] += 1
        c.flat(c.roll(f"{paid[0]}d6"), on=ev.target)

    c.watch(Hit, swell, until=When.ENCOUNTER, on=c.me)


@power(
    "p5510",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p5510(c: Cast) -> None:
    """Flanking with the spirit has no verb -- `c.cannot_be_flanked` is the
    only thing the engine says about flanking -- so that clause is left
    out."""
    plus = c.int_mod // 2 if c.bloodied() else 0
    if c.strike(from_=c.companion(), plus=plus):
        c.damage("2d10" if c.level >= 21 else "1d10", c.wis_mod)


@power(
    "p5538",
    level=1,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.COLD],
    attack=Attack(WIS, vs=REF),
)
def p5538(c: Cast) -> None:
    """"An attack that includes your spirit companion in the area" is the
    attacking row's own area recomputed at the moment of the roll."""
    if not c.strike(from_=c.companion()):
        return
    c.damage("2d10", c.wis_mod, dtype=DamageType.COLD)
    for mate in friends(c):
        c.bonus(
            "attack", 1, on=mate, until=When.EONT,
            when=lambda ctx: catches_spirit(c, ctx), kind="power")


@power(
    "p6521",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p6521(c: Cast) -> None:
    if not c.strike(from_=c.companion()):
        return
    c.damage("2d8" if c.level >= 21 else "1d8", c.wis_mod)
    for mate in beside(c):
        if mate != c.me:
            c.temp_hp(c.con_mod, on=mate)


@power(
    "p9734",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL,
)
def p9734(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    nearby = beside(c)
    pool = [
        a
        for a in dict.fromkeys([*nearby, *friends(c)])
        if a != c.me and (a in nearby or c.distance(a) <= 3)
    ]
    mate = c.choose(pool, "who swings")
    if mate is not None and granted_hit(c, mate, victim):
        c.grants_advantage(on=victim, until=When.EONT, to="allies")


@power(
    "p9735",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(WIS, vs=FORT),
)
def p9735(c: Cast) -> None:
    spirit = c.companion()
    near = [a for a in c.within(2, side="ally") if a != c.me and a != spirit]
    if spirit is not None:
        near += [
            a
            for a in c.within(2, of=spirit, side="ally")
            if a != c.me and a != spirit
        ]
    if c.strike():
        c.damage("2d8" if c.level >= 21 else "1d8", c.wis_mod, dtype=DamageType.THUNDER)
    mate = c.choose(list(dict.fromkeys(near)), "who makes the saving throw")
    if mate is not None:
        c.save(on=mate)


@power(
    "p9736",
    level=1,
    cls="shaman",
    usage=AT_WILL,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p9736(c: Cast) -> None:
    spirit = c.companion()
    near = (
        [a for a in c.within(2, of=spirit, side="ally") if a != c.me and a != spirit]
        if spirit is not None
        else []
    )
    if c.strike(from_=spirit):
        c.damage(
            "2d6" if c.level >= 21 else "1d6", c.wis_mod, dtype=DamageType.PSYCHIC
        )
    mate = c.choose(near, "who shifts")
    if mate is not None:
        c.shift(2, who=mate)


@power(
    "p9738",
    level=1,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p9738(c: Cast) -> None:
    victim = c.target
    if not c.strike(from_=c.companion()) or victim is None:
        return
    c.damage("1d10", c.wis_mod)
    pool = [a for a in friends(c) if c.adjacent_to(victim, a)]
    mate = c.choose(pool, "who swings")
    if mate is not None:
        c.grant_attack(
            mate, on=victim, attack_bonus=c.int_mod if c.build("stalker") else 0
        )


@power(
    "p9739",
    level=1,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=REF),
)
def p9739(c: Cast) -> None:
    """The spirit walks before the attack, which is why the range the
    header measures is the one it has after the move."""
    c.move_companion(2 + c.dex_mod if c.build("watcher") else 3)
    if not c.strike(from_=c.companion()):
        return
    c.damage("1d8", c.wis_mod, dtype=DamageType.LIGHTNING)
    if c.dex_mod <= 0:
        return

    def arc(ev: Any) -> None:
        if ev.attacker in friends(c) and beside_spirit(c, ev.target):
            c.flat(c.dex_mod, dtype=DamageType.LIGHTNING, on=ev.target)

    c.watch(Hit, arc, until=When.EONT, on=c.me)


@power(
    "p9740",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=UpTo(2, "ally"),
    keywords=PRIMAL,
)
def p9740(c: Cast) -> None:
    """`c.no_advantage` takes no gate, so the standing half goes to the
    allies beside the spirit as the row goes off."""
    mate = c.target
    foe = pick_foe(c, mate)
    if mate is not None and foe is not None:
        c.grant_attack(mate, on=foe)
    if not c.first:
        return
    for friend in beside(c):
        c.no_advantage(on=friend, until=When.ENCOUNTER)


@power(
    "p9741",
    level=1,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p9741(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.condition(
            Condition.DAZED,
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.PSYCHIC),
        )
    else:
        c.dazed(until=When.EONT)
        c.slowed(until=When.SAVE_ENDS)
    if victim is not None:
        c.penalty(
            "save", 5, on=victim, until=When.ENCOUNTER,
            when=lambda ctx, v=victim: beside_spirit(c, v),
        )
