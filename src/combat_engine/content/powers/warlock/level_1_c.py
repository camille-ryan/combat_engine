"""Warlock, level 1: the rows from the books after the first, part two.

The conventions `level_1_b.py` sets out hold here too -- the two pact legs
the class carries, one `dtype` for a line printing two, and no refund for
"you do not expend this power".

Two shapes are new to this half.

`_missed_after` is how "the target makes a basic attack, and if it misses it
takes damage" is read: `c.grant_attack` returns whether the swing *happened*
and not whether it landed, so the `Miss` is caught off the bus for the
length of the call.

A curse is relational -- `c.cursed` asks whether *this* warlock cursed that
creature -- so a row whose printed Target is "each creature under your
curse" declares the restriction in the target's label, the reading
`level_1.py` uses for a target it cannot filter, rather than gating the body
on a state the board never reaches.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CHA,
    CON,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    MINOR,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Event,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    SavingThrow,
    Target,
    Trigger,
    When,
    World,
    power,
)
from combat_engine.engine.events import MoveEnd
from combat_engine.engine.query import distance_between, team

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

_CRIT_OR_SAVE = "an enemy within 10 squares scores a critical hit or saves"


def _enemy_near(world: World, me: int, who: int | None) -> bool:
    return (
        who is not None
        and team(world, who) is not team(world, me)
        and distance_between(world, who, me) <= 10
    )


def _enemy_crit(world: World, me: int, ev: Event) -> bool:
    return bool(getattr(ev, "critical", False)) and _enemy_near(
        world, me, getattr(ev, "attacker", None)
    )


def _enemy_saved(world: World, me: int, ev: Event) -> bool:
    return bool(getattr(ev, "saved", False)) and _enemy_near(
        world, me, getattr(ev, "actor", None)
    )


def _missed_after(c: Cast, who: int, mark: int) -> bool:
    """Hand `who` a basic attack at `mark` and say whether it missed.

    `c.grant_attack` answers whether the swing was taken, which is a
    different question -- so the `Miss` is watched for over the one call.
    """
    missed = [False]

    def note(ev: Miss) -> None:
        if ev.attacker == who:
            missed[0] = True

    sub = c.world.bus.on(Miss, note)
    try:
        c.grant_attack(who, on=mark)
    finally:
        c.world.bus.off(sub)
    return missed[0]


@power(
    "p1868",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(20),
    target=Target("enemy", everyone=True, label="Each creature in the burst under your curse"),
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=FORT),
)
def p1868(c: Cast) -> None:
    """No ability modifier on the damage, which is what the printed line says.
    The dark pact rider that would add Intelligence has no leg to ask for."""
    if c.target is not None and c.strike():
        c.damage("2d8", dtype=DamageType.NECROTIC)


@power(
    "p1881",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p1881(c: Cast) -> None:
    """The ally is bled first, because the bonus it buys is on this roll."""
    friends = sorted(c.within(1, side="ally"))
    paid = False
    if friends and c.may("bleed an ally", who=c.me):
        who = c.choose(friends, f"{c.ref}: which ally pays")
        if who is not None:
            c.flat(c.cha_mod, on=who)
            paid = True
    if c.strike(plus=2 if paid else 0):
        c.damage("3d8", c.cha_mod)
        if paid and c.cha_mod > 0:
            c.ongoing(c.cha_mod, DamageType.POISON)
    else:
        c.half_damage("3d8", c.cha_mod)


@power(
    "p1918",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p1918(c: Cast) -> None:
    """The spread is hung off the target's first *failed* save.

    `SavingThrow` names who rolled and whether it stood, but not which of
    several holds was being answered, so the latch is on the first failure
    of any -- which for a creature carrying only this one is the printed
    line exactly.
    """
    victim = c.target
    if not c.strike():
        c.ongoing(5, DamageType.POISON)
        return
    burn = c.ongoing(10, DamageType.POISON)
    if victim is None or burn is None:
        return
    spread_ = [False]

    def failed(ev: SavingThrow) -> None:
        if spread_[0] or ev.actor != victim or ev.saved:
            return
        spread_[0] = True
        for foe in c.within(2, of=victim, side="enemy"):
            if foe != victim:
                c.ongoing(5, DamageType.POISON, on=foe)

    burn.subs.append(c.world.bus.on(SavingThrow, failed))


@power(
    "p3403",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p3403(c: Cast) -> None:
    # "At maximum hit points" is asked before the arrow lands, not after.
    dice = "1d12" if c.missing() == 0 else "1d8"
    if c.strike():
        c.damage(dice, c.cha_mod, dtype=DamageType.PSYCHIC)


@power(
    "p3404",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE, Keyword.POISON],
    attack=Attack(CHA, vs=REF),
)
def p3404(c: Cast) -> None:
    """The advantage is read off the roll that was made, not asked again: a
    one-shot grant has been spent by then. The dark pact rider that widens
    the range to ten has no leg."""
    shot = c.strike()
    if not shot:
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.FORCE)
    if shot.advantage:
        c.flat(c.int_mod, dtype=DamageType.POISON)


@power(
    "p4051",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=WILL),
)
def p4051(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.NECROTIC)
        c.slowed()


@power(
    "p4052",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CON, vs=FORT),
)
def p4052(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.damage("2d6", c.con_mod, dtype=DamageType.COLD)
    if victim is None:
        return
    gone = [False]

    def stepped(ev: MoveEnd) -> None:
        if gone[0] or ev.actor != victim:
            return
        gone[0] = True
        # Rolled rather than dealt through `c.damage`, which would take the
        # maximum if this row's own hit happened to be a critical.
        c.flat(c.roll("2d6"), dtype=DamageType.COLD, on=victim)
        if c.build("infernal"):
            c.bonus("attack", 2, on=c.me, kind="power", until=When.EONT, once=True)

    c.watch(MoveEnd, stepped, until=When.EONT)


@power(
    "p4055",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
    trigger=_CRIT_OR_SAVE,
    on=(
        Trigger(Hit, when=_enemy_crit, text="an enemy within 10 squares scores a critical hit"),
        Trigger(SavingThrow, when=_enemy_saved, text="an enemy within 10 squares saves"),
    ),
)
def p4055(c: Cast) -> None:
    """"It cannot save against this until it has taken the ongoing damage at
    least once" is not written: `c.unsave` answers a save being rolled now,
    and nothing holds a saving throw back until a condition is met."""
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.penalty("save", 2, until=When.SAVE_ENDS)
    c.ongoing(5, DamageType.PSYCHIC)


@power(
    "p4062",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CON, vs=WILL),
)
def p4062(c: Cast) -> None:
    """The fall is an Effect line and lands either way; the hit is what stops
    the target getting up again."""
    if c.strike():
        c.damage("3d6", c.con_mod, dtype=DamageType.FIRE)
        c.prone(held=When.SAVE_ENDS)
    else:
        c.half_damage("3d6", c.con_mod, dtype=DamageType.FIRE)
        c.prone()


@power(
    "p4170",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CON, vs=FORT),
)
def p4170(c: Cast) -> None:
    # The vestige pact rider -- three temporary hit points per creature hit,
    # and they pile up -- has no leg to ask for.
    if c.target is not None and c.strike():
        c.damage("3d4", c.con_mod, dtype=DamageType.THUNDER)
        c.condition(Condition.DEAFENED)


@power(
    "p4277",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=WILL),
)
def p4277(c: Cast) -> None:
    # The star pact rider -- a penalty to the next save it makes this fight
    # -- has no leg to ask for.
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)


@power(
    "p4278",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CHA, vs=WILL),
)
def p4278(c: Cast) -> None:
    """"It treats all its enemies as concealed" is not written: concealment
    is a property of the creature being looked at, and there is nothing that
    grants it to a whole side from the looker's end."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)


@power(
    "p4279",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p4279(c: Cast) -> None:
    """Sustaining shoots again, at anybody in range rather than at the one
    first hit, which is what "any target in range" says."""
    if c.strike():
        c.damage("2d12", c.cha_mod, dtype=DamageType.RADIANT)
        if c.bloodied():
            c.blinded()

    def again() -> None:
        pool = sorted(f for f in c.enemies() if c.distance(f) <= 10)
        mark = c.choose(pool, f"{c.ref}: who the light finds") if pool else None
        if mark is not None and c.attack(c.cha_, WILL, on=mark):
            c.flat(c.cha_mod, dtype=DamageType.RADIANT, on=mark)

    beam = c.world.effects.apply(
        c.me, c.me, When.SUSTAIN, label=c.ref, sustain_cost=MINOR
    )
    c.on_sustain(beam, again)


@power(
    "p5902",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=REF),
)
def p5902(c: Cast) -> None:
    # The star pact rider would make the push 1 + Intelligence modifier.
    if c.target is not None and c.strike():
        c.damage("1d8", c.con_mod)
        c.push(2)


@power(
    "p5903",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CON, vs=REF),
)
def p5903(c: Cast) -> None:
    """Only the penalty to saves is written. "Cannot regain hit points" and
    "cannot gain temporary hit points" have no method -- `c.half_healing` is
    the nearest and it halves rather than forbids, which is a different and
    much weaker card."""
    if c.strike():
        c.damage("2d8", c.con_mod, dtype=DamageType.NECROTIC)
        c.penalty("save", 2)


@power(
    "p5904",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p5904(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.cha_mod)
        c.slowed()
        c.grants_advantage()


@power(
    "p5905",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p5905(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.slide(2)  # an Effect line, taken before the attack as printed
    if not c.strike():
        c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC)
        return
    near = sorted(w for w in c.within(1, of=victim) if w != victim)
    mark = c.choose(near, f"{c.ref}: who it swings at") if near else None
    if mark is not None and _missed_after(c, victim, mark):
        c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC)


@power(
    "p6855",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CON, vs=WILL),
)
def p6855(c: Cast) -> None:
    """"If it is already cursed, deal your curse damage to it instead" reaches
    into the class feature's own rider, which a power row cannot move, so
    only the placing half is written. The vestige augments have no leg."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d6", c.con_mod, dtype=DamageType.PSYCHIC)
    pool = sorted(
        {victim, *(f for f in c.within(3, of=victim, side="enemy") if c.can_see(f))}
    )
    mark = c.choose(pool, f"{c.ref}: who the curse settles on")
    if mark is not None and not c.cursed(mark):
        c.curse(on=mark)


@power(
    "p6856",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=REF),
)
def p6856(c: Cast) -> None:
    # The Khaeleth pact boon has no leg to ask for.
    extra = c.int_mod * len(c.within(1, side="ally"))
    if c.strike():
        c.damage("1d8", c.con_mod + extra)
    else:
        c.half_damage("1d8", c.con_mod + extra)


@power(
    "p6857",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CON, vs=REF),
)
def p6857(c: Cast) -> None:
    """"Cannot walk or run" is written as immobilised, which is the nearest
    card: it also stops a shift, which the printed line leaves alone. The
    Mount Vaelis pact boon has no leg to ask for."""
    if c.strike():
        c.damage("2d8", c.con_mod, dtype=DamageType.THUNDER)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.con_mod, dtype=DamageType.THUNDER)
        c.immobilized()


@power(
    "p7402",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p7402(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.cha_mod)
        c.slide(1)


@power(
    "p7428",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=FORT),
)
def p7428(c: Cast) -> None:
    """Sustaining squeezes whatever is still held. The minor action the
    printed line offers *after* sustaining -- one more attack on a creature
    beside somebody already caught -- is a second action on the same turn
    and has nowhere to go here.

    "Use your Fortitude or Reflex to escape" is the grab's own arithmetic
    and is not reachable from a row.
    """
    if c.target is not None and c.strike():
        c.damage("1d6", c.cha_mod)
        c.grab()
    if not c.last:
        return

    def squeeze() -> None:
        for foe in c.enemies():
            if c.is_(Condition.GRABBED, foe):
                c.damage("1d6", c.cha_mod, on=foe)

    hold = c.world.effects.apply(
        c.me, c.me, When.SUSTAIN, label=c.ref, sustain_cost=STANDARD
    )
    c.on_sustain(hold, squeeze)
