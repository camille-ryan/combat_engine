"""Battlemind, level 7."""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
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
    Budget,
    Cast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Miss,
    Position,
    Powers,
    Trigger,
    TurnStart,
    UpTo,
    When,
    Window,
    both,
    enemy_within,
    hits_me,
    leaves_me_out,
    power,
    targets_my_side,
)

from . import PSIONIC_WEAPON, shift_beside


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
    """Neither augment is written: Augment 1 is the Special that lets the row
    stand in for an opportunity attack, which is what a row is *used as* and
    not something a body decides, and Augment 2 is a close burst. "The target
    cannot gain combat advantage" is dropped too -- `c.grants_advantage` hands
    advantage out and nothing takes it away."""
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
    """"Hits or misses" is two event classes on one hold, and "the first
    time" is a latch rather than `once=`, which would be spent by the wrong
    half of the pair.

    Augment 1 replaces the rider with the target hitting itself, which is
    `c.as_though_hit_by` -- the printed line is "it hits itself with that
    attack", not "it attacks itself", so nothing is rolled. Augment 2 keeps
    the damage and hands you the target's next melee attack to aim: an
    interrupt on `AttackDeclared`, where `c.redirect` moves it."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.con_mod)
    if spent == 1:
        known = c.world.get(victim, Powers)
        if known is not None and known.basic:
            c.as_though_hit_by(known.basic, on=victim, by=victim)
        return
    if spent == 2:

        def steer(ev: AttackDeclared) -> None:
            if ev.attacker != victim:
                return
            pool = [x for x in c.within(1, of=victim) if x != victim]
            aim = c.choose(sorted(pool), "whom it attacks instead") if pool else None
            if aim is not None:
                ev.target = aim

        c.watch(
            AttackDeclared, steer, window=Window.BEFORE, until=When.EONT,
            on=victim, once=True, label=c.ref,
        )
        return
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
    """Augment 1 is an Effect -- a step in after the attack, hit or miss.
    Augment 2 buys a weapon die and drops Wisdom from the damage."""
    spent = augment(c)
    victim = c.target
    if c.strike():
        if spent == 2:
            c.damage(c.w(), c.con_mod)
        else:
            c.damage(0, c.con_mod + c.wis_mod)
        c.prone()
    if spent == 1 and victim is not None:
        shift_beside(c, 2, victim)


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
    """The price -- "you don't get your normal standard action on your turn"
    -- is the budget itself, emptied at the start of that turn: both augments
    buy it back, which is most of what they are for.

    Augment 1 steps into the square the target was pushed out of and leaves
    you with the opening. Augment 2 pushes by Charisma, knocks the target
    down and holds it there until its own turn starts, which is what
    `c.prone(held=)` says."""
    spent = augment(c)
    victim = c.target
    if c.strike():
        c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod, dtype=DamageType.FORCE)
        was = c.world.get(victim, Position).square if victim is not None else None
        c.push(c.cha_mod if spent == 2 else 1)
        if spent == 1 and was is not None:
            c.shift(1, to=was)
            c.grants_advantage(on=victim, until=When.EONT)
        if spent == 2:
            c.prone(held=When.SONT)
    if spent:
        return

    def tax(ev: TurnStart) -> None:
        if ev.actor != c.me:
            return
        budget = c.world.get(c.me, Budget)
        if budget is not None:
            budget.standard = 0

    c.watch(TurnStart, tax, until=When.SONT, once=True)


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
    """Standing in two squares at once is dropped -- a creature has one
    `Position` -- and both augments are built on that same double: which
    square you keep when it ends, and putting the second one five squares
    away. With no double to speak of there is nothing for either to say."""
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
    """The printed reach is weapon + 1. Both augments lengthen it to weapon
    + 3, which is the header and measured before the body runs, so Augment
    2's pull is not written on its own either."""
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
    """The rider on the class's own step power is dropped -- that row is a
    class feature with its own id, which this spec does not name -- and both
    augments are only louder versions of that same rider, so neither is
    written either."""
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
    """`c.swap` is the one method that changes two creatures over, so the
    teleport reads as a swap. Both augments mark the target and reach further
    for the ally -- 3 squares, then 5 -- and neither will trade places with
    the target itself."""
    spent = augment(c)
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.con_mod)
    if spent:
        c.mark(until=When.EONT)
    reach = {0: 1, 1: 3, 2: 5}[spent]
    mates = [a for a in c.within(reach, side="ally") if a != c.me]
    pool = mates if spent else [victim, *mates]
    partner = c.choose(pool, "who you change places with") if pool else None
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
    """`c.run_at` is the printed "move your speed to a square adjacent to the
    triggering enemy". The price -- no standard action next turn -- is the
    budget emptied at the start of that turn; Augment 2 buys it back.

    Augment 1 penalises the attack this interrupts: `once=True`, because the
    penalty is spent on the roll it was bought for. Augment 2 takes the blow
    instead, which is `c.redirect` on the event being answered."""
    spent = augment(c)
    foe = c.target
    if foe is None:
        return
    c.run_at(foe)
    if c.strike():
        c.damage(c.w(2) if spent == 2 else c.w(), c.con_mod)
        if spent == 1:
            c.penalty("attack", c.cha_mod, on=foe, until=When.EOT, once=True)
        elif spent == 2:
            c.redirect(to=c.me)
    if spent == 2:
        return

    def tax(ev: TurnStart) -> None:
        if ev.actor != c.me:
            return
        budget = c.world.get(c.me, Budget)
        if budget is not None:
            budget.standard = 0

    c.watch(TurnStart, tax, until=When.SONT, once=True)


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
    """Augment 1 steps you toward the next target between swings, which is
    why it is on every target but the last. Augment 2 adds the modifier to
    the damage and moves the mark into an Effect, so it lands on a miss
    too."""
    spent = augment(c)
    if c.strike():
        c.damage(c.w(), c.con_mod if spent == 2 else 0)
        if spent != 2:
            c.mark(until=When.EONT)
    if spent == 2:
        c.mark(until=When.EONT)
    if spent == 1 and not c.last:
        nxt = c.targets[c.index + 1]
        shift_beside(c, 1, nxt)
