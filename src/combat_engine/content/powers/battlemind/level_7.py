"""Battlemind, level 7."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    FORT,
    INTERRUPT,
    ONE_CREATURE,
    REACTION,
    STANDARD,
    Attack,
    AttackDeclared,
    Cast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Miss,
    Trigger,
    UpTo,
    When,
    both,
    enemy_within,
    hits_me,
    leaves_me_out,
    power,
    targets_my_side,
)

from . import PSIONIC_WEAPON


@power(
    "p11169",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p11169(c: Cast) -> None:
    """Base form. Augment 1 (use it for an opportunity attack) and Augment 2
    (a burst) are dropped: no power points. "The target cannot gain combat
    advantage" is dropped too -- `c.grants_advantage` hands advantage out and
    nothing takes it away."""
    if c.strike():
        c.damage(c.w(), c.con_mod)


@power(
    "p11170",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(CON, vs=AC),
)
def p11170(c: Cast) -> None:
    """Base form; both augments are dropped. "Hits or misses" is two event
    classes on one hold, and "the first time" is a latch rather than `once=`,
    which would be spent by the wrong half of the pair."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.con_mod)
    fired: list[int] = []

    def sting(ev: Hit | Miss) -> None:
        if fired or ev.attacker != victim or ev.target not in c.allies():
            return
        fired.append(1)
        c.flat(c.wis_mod, dtype=DamageType.PSYCHIC, on=victim)

    held = c.watch(Hit, sting, until=When.EONT, on=victim)
    held.subs.append(c.world.bus.on(Miss, sting, owner=c.me))


@power(
    "p11171",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=FORT),
)
def p11171(c: Cast) -> None:
    """Base form. Augment 1 (a step in afterwards) and Augment 2 (1[W]) are
    dropped: no power points."""
    if c.strike():
        c.damage(0, c.con_mod + c.wis_mod)
        c.prone()


@power(
    "p12425",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FORCE],
    attack=Attack(CON, vs=AC),
    trigger="an enemy hits you",
    on=Trigger(Hit, hits_me, "an enemy hits you"),
)
def p12425(c: Cast) -> None:
    """Base form; both augments are dropped. So is the base form's price --
    "you don't get your normal standard action on your turn" -- because
    nothing on `Cast` spends somebody's action for them. That makes this row
    cheaper than printed."""
    if c.strike():
        c.damage(c.w(), c.con_mod, dtype=DamageType.FORCE)
        c.push(1)


@power(
    "p13051",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p13051(c: Cast) -> None:
    """Base form; both augments are dropped. Standing in two squares at once
    is dropped as well: a creature has one `Position`."""
    if c.strike():
        c.damage(c.w())


@power(
    "p13052",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p13052(c: Cast) -> None:
    """Base form -- the printed reach is weapon + 1. Augment 1 (weapon + 3)
    and Augment 2 (a pull) are dropped: no power points."""
    if c.strike():
        c.damage(c.w(), c.con_mod)


@power(
    "p13053",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p13053(c: Cast) -> None:
    """Base form; both augments are dropped. The rider on the class's own
    step power is dropped too -- that row is a class feature with its own id,
    which this spec does not name."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.mark(until=When.EONT)


@power(
    "p13054",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=AC),
)
def p13054(c: Cast) -> None:
    """Base form; both augments are dropped. `c.swap` is the one method that
    changes two creatures over, so the teleport reads as a swap."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.con_mod)
    mates = [a for a in c.within(1, side="ally") if a != c.me]
    partner = c.choose([victim, *mates], "who you change places with")
    if partner is not None:
        c.swap(partner)


@power(
    "p2634",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
    trigger="an enemy within 5 squares of you targets an ally with an attack",
    on=Trigger(
        AttackDeclared,
        both(enemy_within(5), targets_my_side, leaves_me_out),
        "an enemy within 5 squares of you targets an ally with an attack",
    ),
)
def p2634(c: Cast) -> None:
    """Base form; both augments are dropped, and so is the price the base form
    pays -- losing next turn's standard action, which nothing on `Cast` can
    take. `c.run_at` is the printed "move your speed to a square adjacent to
    the triggering enemy"."""
    foe = c.target
    if foe is None:
        return
    c.run_at(foe)
    if c.strike():
        c.damage(c.w(), c.con_mod)


@power(
    "p2635",
    level=7,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p2635(c: Cast) -> None:
    """Base form. Augment 1 (a step between targets) and Augment 2 (full
    damage, the mark as an Effect) are dropped: no power points."""
    if c.strike():
        c.damage(c.w())
        c.mark(until=When.EONT)
