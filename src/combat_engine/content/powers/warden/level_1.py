"""Warden, level 1: the at-wills and the encounter attacks.

The class's whole shape is here: mark something, then make its mark hurt.
`c.marked(who)` asks whether *this* warden laid it, which is the reading
every one of these rows wants -- "one enemy marked by you".

The forms are in `level_1_b.py`.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.events import ZoneExited
from combat_engine.engine.grid import blast
from combat_engine.engine.query import squares

from . import bites_enemies, rough_for_enemies, zone_named

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]


# -- at-will ----------------------------------------------------------------


@power(
    "p5095",
    level=1,
    cls="warden",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5095(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.bonus(AC, 1, on=c.me, until=When.EONT, kind="power")


@power(
    "p5096",
    level=1,
    cls="warden",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5096(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.temp_hp(c.con_mod, on=c.me)


@power(
    "p5097",
    level=1,
    cls="warden",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5097(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.pull(1)


@power(
    "p5098",
    level=1,
    cls="warden",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5098(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.slowed(until=When.EONT)


@power(
    "p9814",
    level=1,
    cls="warden",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9814(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        beside = [a for a in c.within(1, side="ally") if a != c.me]
        if beside:
            c.temp_hp(c.wis_mod, on=c.choose(beside, "which ally is shored up"))


@power(
    "p9815",
    level=1,
    cls="warden",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p9815(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.LIGHTNING)
        near = [e for e in c.within(2, side="enemy") if e != c.target and c.marked(e)]
        if near:
            who = c.choose(near, "which marked enemy the thunder reaches")
            c.flat(c.con_mod, dtype=DamageType.THUNDER, on=who)


@power(
    "p13601",
    level=1,
    cls="warden",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p13601(c: Cast) -> None:
    """The Effect line is a damage bonus to one named class feature's attack,
    and the warden's chassis carries no ref for that feature to gate on, so
    only the Hit line is written. `c.bonus("damage", when=..., kind="power")` would say it
    the moment the feature has an id."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.grants_advantage(until=When.SONT)


@power(
    "p9965",
    level=1,
    cls="warden",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9965(c: Cast) -> None:
    """The mark is an Effect, so it lands whether or not the swing does. The
    Special -- usable in place of a melee basic attack when you charge -- is
    a designation, not a charge: `charges=True` would say this row *is* one."""
    c.mark(until=When.EONT)
    if c.strike():
        c.damage(c.w(), c.str_mod)


# -- encounter --------------------------------------------------------------


@power(
    "p11071",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p11071(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        seen = [e for e in c.enemies() if c.marked(e) and c.can_see(e)]
        if seen:
            who = c.choose(seen, "which marked enemy the thunder pins")
            c.flat(c.str_mod, dtype=DamageType.THUNDER, on=who)
            c.immobilized(on=who, until=When.EONT)


@power(
    "p13602",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(2),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p13602(c: Cast) -> None:
    """One enemy in the blast is attacked; the rest are marked either way and
    splashed only on a hit."""
    area = c.area()
    caught = c.in_squares(area, side="enemy")
    for e in caught:
        c.mark(on=e, until=When.EONT)
    if c.strike():
        c.damage(c.w())
        for e in caught:
            if e != c.target:
                c.flat(c.str_mod, on=e)


@power(
    "p5099",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5099(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        spikes = c.zone(spread({c.there}, 1), until=When.EONT)
        bites_enemies(c, spikes, 5, until=When.EONT)


@power(
    "p5100",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p5100(c: Cast) -> None:
    if c.first:
        rough_for_enemies(c, c.area(), until=When.EONT)
    if c.strike():
        c.damage(c.w(), c.str_mod)


@power(
    "p5101",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(STR, vs=FORT),
)
def p5101(c: Cast) -> None:
    """The secondary is a close blast 3, which nothing aims for a secondary
    attack, so the blast is laid out by hand towards the primary target and
    rolled on the header's alternate line."""
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod, dtype=DamageType.THUNDER)
    if c.build("f1s0"):
        c.push(c.con_mod)
    area = blast(squares(c.world, c.me), 3, c.there)
    c.branch = 1
    for who in c.in_squares(area, side="any"):
        if who == c.me:
            continue
        if c.strike(on=who):
            c.damage("1d6", dtype=DamageType.THUNDER, on=who)
            c.push(1, on=who)
    c.branch = 0


@power(
    "p5102",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5102(c: Cast) -> None:
    extra = c.wis_mod if c.build("f1s3") else 0
    if c.strike():
        c.damage(c.w(), c.str_mod + extra)
    again = c.choose(c.enemies(), "who the second swing goes to")
    if again is not None and c.strike(on=again):
        c.damage(c.w(), c.str_mod + extra, on=again)


@power(
    "p5567",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5567(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    amount = 5 + (c.wis_mod if c.build("f1s1") else 0)

    def on_hit(ev: Hit) -> None:
        if ev.target != c.me or ev.attacker not in c.enemies():
            return
        near = [a for a in c.within(3, side="ally") if a != c.me]
        if near:
            c.temp_hp(amount, on=c.choose(near, "which ally the spirit shields"))

    c.watch(Hit, on_hit, until=When.EONT)


@power(
    "p9816",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9816(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        for e in [e for e in c.enemies() if c.marked(e)]:
            if e != c.target:
                c.flat(c.con_mod, on=e)
            if c.build("f1s2"):
                c.slide(1, on=e)


@power(
    "p9817",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9817(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        for e in c.within(3, side="enemy"):
            c.pull(2, on=e)


@power(
    "p9819",
    level=1,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(STR, vs=AC),
)
def p9819(c: Cast) -> None:
    """The zone is an Effect line, so it is laid before the attack and stands
    whether or not anything is hit. The prone rider is per target, so each
    one that is hit gets its own watch on leaving."""
    if c.first:
        c.zone(c.area(), until=When.EONT)
    ground = zone_named(c, c.ref)
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod)
    victim = c.target
    if ground is None or victim is None:
        return

    def on_exit(ev: ZoneExited) -> None:
        if ev.zone == ground and ev.actor == victim:
            c.prone(on=victim)
            if c.build("f1s0"):
                c.flat(c.con_mod, on=victim)

    c.watch(ZoneExited, on_exit, until=When.EONT)
