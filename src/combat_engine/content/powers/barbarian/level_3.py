"""Barbarian, level 3: the encounter attacks.

Two rows print a Requirement this build cannot meet -- two melee weapons,
and a two-handed reach weapon -- and the gates for both already exist on
the fighter, in `fighter/grips.py`. They are imported rather than rewritten;
the rows report UNUSED on a barbarian carrying one longsword, which is the
requirement doing its job.

Two print "When charging, you can use this power in place of a melee basic
attack". That is a property of what a charge *swings*, `Powers.basic`, and
there is no header field for it: `charges=True` says the opposite thing --
that the row **is** a charge. Both are written as the standard action they
also are, and the charge riders hanging off that Special line go with it.
See the report.

A build rider is gated on `c.build(...)` and the ungated half is what a
barbarian without that build gets, which is the warlord precedent in
`warlord/level_7_b.py`.
"""

from __future__ import annotations

from combat_engine.content.powers.fighter.grips import (
    reach_weapon,
    two_handed,
    two_melee,
)
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    MoveEnd,
    Position,
    When,
    World,
    power,
)
from combat_engine.engine.events import AttackDeclared
from combat_engine.engine.grid import blast, distance
from combat_engine.engine.query import squares as squares_of

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _two_handed_reach(world: World, eid: int) -> bool:
    """"A two-handed reach weapon" is both of the fighter's gates at once."""
    return two_handed(world, eid) and reach_weapon(world, eid)


def _square_of(c: Cast, who: int):  # noqa: ANN202
    pos = c.world.get(who, Position)
    return pos.square if pos is not None else None


@power(
    "p11562",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_handed_reach,
    requires_text="needs a two-handed reach weapon",
)
def p11562(c: Cast) -> None:
    """Reach 2: every weapon that satisfies the Requirement has the reach
    property, which is what "Melee weapon" comes to for this row."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)


@power(
    "p12278",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p12278(c: Cast) -> None:
    """The secondary is a close blast with no printed aim, so it is aimed at
    the creature the primary just hit -- `grid.blast` takes the nearest legal
    placement of the block from there."""
    foe = c.target
    if not c.strike() or foe is None:
        return
    c.damage(c.w(2), c.str_mod)
    area = blast(squares_of(c.world, c.me), 3, c.there)
    for who in sorted(c.in_squares(area, side="enemy")):
        if c.attack(c.cha_, WILL, on=who):
            c.penalty("attack", 2, on=who, until=When.EONT)


@power(
    "p14418",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14418(c: Cast) -> None:
    """"After its movement" is `MoveEnd`, not `MoveStart`, which fires
    before the creature has gone anywhere -- and the square to end in is
    picked from what the shift can actually reach, so a barbarian with
    nowhere to stand beside it simply does not go."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    me = c.me

    def follow(ev: MoveEnd) -> None:
        if ev.actor != victim or not c.may("close the gap", who=me):
            return
        far = c.speed_of()
        there = _square_of(c, victim)
        if there is None:
            return
        spots = sorted(
            sq for sq in c.world.reachable_squares(me, far) if distance(sq, there) <= 1
        )
        where = c.choose(spots, "where you land") if spots else None
        if where is not None:
            c.shift(far, to=where)

    c.watch(MoveEnd, follow, until=When.EONT, on=c.me, once=True, label=f"{c.ref} chase")


@power(
    "p14419",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p14419(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    for foe in sorted(c.within(1, of=victim, side="enemy")):
        if foe != victim:
            c.flat(5, dtype=DamageType.THUNDER, on=foe)


@power(
    "p4810",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p4810(c: Cast) -> None:
    """"Then one enemy adjacent to the target" is read after the push: the
    shove is what decides who is standing beside it by the time the word
    "then" arrives."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    c.push(2)
    c.prone()
    others = sorted(f for f in c.within(1, of=victim, side="enemy") if f != victim)
    caught = c.choose(others, "who the follow-through catches") if others else None
    if caught is not None:
        c.damage("1d8", c.str_mod, on=caught)


@power(
    "p4829",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4829(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    everyone = c.build("rageblood")
    for foe in sorted(c.within(1, side="enemy")):
        if everyone or c.bloodied(on=foe):
            c.flat(c.con_mod, on=foe)


@power(
    "p4830",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p4830(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.prone()


@power(
    "p4939",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4939(c: Cast) -> None:
    """Both halves of "you or the target" are asked before the blow lands,
    because the blow is what would bloody the target."""
    victim = c.target
    hurt = c.bloodied(on=c.me) or (victim is not None and c.bloodied(on=victim))
    if c.strike():
        c.damage(c.w(3 if hurt else 2), c.str_mod)


@power(
    "p4940",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4940(c: Cast) -> None:
    """The Special line -- swinging this instead of a basic attack when
    charging, and the bonus it pays for each opportunity attack taken on the
    way in -- has no header field; see the report."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)


@power(
    "p4941",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4941(c: Cast) -> None:
    """The build does not add a second penalty, it replaces the printed
    number -- two penalties of one kind do not stack anyway, so writing it
    as a replacement is both the rule and the sentence."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.penalty(AC, c.cha_mod if c.build("thaneborn") else 2, until=When.EONT)


@power(
    "p5215",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=two_melee,
    requires_text="needs two melee weapons",
)
def p5215(c: Cast) -> None:
    """"Adjacent to you at some point during the shift" is the two ends of
    it: the step is two squares, so anyone beside the barbarian before or
    after is somebody it passed. The shift is an Effect line and happens
    whether the main hand landed or not."""
    beside = set(c.within(1, side="enemy"))
    landed = c.strike()
    if landed:
        c.damage(c.w(1), c.str_mod)
    c.shift(2)
    beside |= set(c.within(1, side="enemy"))
    if not landed:
        return
    pool = sorted(beside)
    for prompt in ("who the off-hand catches", "who else the off-hand catches"):
        who = c.choose(pool, prompt, optional=True) if pool else None
        if who is None:
            return
        pool.remove(who)
        c.damage(c.w(1, hand="off"), on=who)


@power(
    "p5216",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5216(c: Cast) -> None:
    """The 5 damage is the price of the Miss line and is paid first: an
    ally that will not swing should not be charged for it, so the offer is
    made before the blood."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        return
    if victim is None:
        return
    friends = sorted(a for a in c.within(1, of=victim, side="ally") if a != c.me)
    who = c.choose(friends, "who takes the opening") if friends else None
    if who is None or not c.may("bleed for an ally's swing", who=c.me):
        return
    c.flat(5, on=c.me)
    c.grant_attack(who, on=victim)


@power(
    "p9566",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9566(c: Cast) -> None:
    """The watcher comes down before the swing: the openings that pay for
    the advantage are the ones this row's own move provoked, and a later
    one in the same turn is not the printed sentence."""
    victim = c.target
    if victim is None:
        return
    me = c.me
    openings: list[int] = []

    def counted(ev: AttackDeclared) -> None:
        if ev.target == me and getattr(ev, "opportunity", False):
            openings.append(ev.attacker)

    guard = c.watch(
        AttackDeclared, counted, until=When.EOT, on=c.me, label=f"{c.ref} run"
    )
    c.move(c.speed_of() + (c.con_mod if c.build("rageblood") else 0))
    c.world.effects.end(guard, "the run is over")
    if c.strike(advantage=True if openings else None):
        c.damage(c.w(2), c.str_mod)


@power(
    "p9567",
    level=3,
    cls="barbarian",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p9567(c: Cast) -> None:
    """"A blast 3 that includes the target": the block is aimed at the
    target's square and the target is caught whether or not the nearest
    legal placement reached it."""
    foe = c.target
    if not c.strike() or foe is None:
        return
    c.damage(c.w(1), c.str_mod)
    area = blast(squares_of(c.world, c.me), 3, c.there)
    steps = c.con_mod if c.build("thunderborn") else 1
    for who in sorted({*c.in_squares(area, side="enemy"), foe}):
        c.damage("1d6", dtype=DamageType.THUNDER, on=who)
        c.push(steps, on=who)
