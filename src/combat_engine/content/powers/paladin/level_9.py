"""Paladin, level 9: daily attacks.

`p2260`'s Special line is an entry condition rather than anything the body
does, so it is a `requires=` gate: the row is simply not offered while a
friend is standing within five squares. That makes it unusable on a board
where the party is together, which is the printed card.

`p1264`'s Effect prints a duration for the slow and none for the sentence
that keeps applying it. An undated effect is instantaneous, and an
instantaneous version of that sentence is no effect at all, so it is read as
lasting the encounter.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    CHA,
    CON,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    FORT,
    INTERRUPT,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Event,
    Health,
    Hit,
    Keyword,
    Melee,
    OpportunityWindow,
    Ranged,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    by_melee,
    by_ranged,
    power,
)
from combat_engine.engine.events import DamageApplied, DamageRolled
from combat_engine.engine.grid import distance, spread
from combat_engine.engine.query import allies as allies_of
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.query import squares as squares_of

from .marks import burning_mark

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


def _str_or_cha(c: Cast) -> tuple[int, int]:
    """"Strength or Charisma": the better of the two. See `level_1_b.py`."""
    if c.cha_ > c.str_:
        return c.cha_, c.cha_mod
    return c.str_, c.str_mod


def _beside(c: Cast, who: int) -> list[tuple[int, int]]:
    theirs = squares_of(c.world, who)
    return [
        sq
        for sq in spread(theirs, 1) - theirs
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    ]


@power(
    "p10100",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        *DIVINE_WEAPON, Keyword.NECROTIC, Keyword.PSYCHIC, Keyword.HEALING,
    ],
    attack=Attack(STR, vs=AC),
)
def p10100(c: Cast) -> None:
    """"Necrotic and psychic damage" is one packet of two types, which
    `DamageType` cannot hold; it is dealt as the first of the two printed
    rather than as two packets, which would double it. See the report.
    """
    victim = c.target
    bonus, mod = _str_or_cha(c)
    if c.attack(bonus, AC):
        c.damage(c.w(3), mod, dtype=DamageType.NECROTIC)
        burning_mark(c)
    else:
        c.half_damage(c.w(3), mod, dtype=DamageType.NECROTIC)
    health = c.world.get(victim, Health) if victim is not None else None
    if health is None or health.hp > 0:
        return
    if c.may("spend a healing surge", who=c.me) and c.spend_surge(on=c.me):
        c.heal(2 * c.surge_value(), on=c.me)


@power(
    "p10252",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.NECROTIC],
    attack=Attack(STR, vs=AC),
)
def p10252(c: Cast) -> None:
    """The secondary rolls longhand: one header carries one attack line, and
    this one's second is a different ability against a different defence.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        if victim is not None:
            for foe in sorted(
                e for e in c.within(1, of=victim, side="enemy") if e != victim
            ):
                if c.attack(c.str_, WILL, on=foe):
                    c.damage(c.w(1), c.cha_mod, dtype=DamageType.NECROTIC, on=foe)
                    burning_mark(c, on=foe)
    else:
        c.half_damage(c.w(2), c.str_mod)
    burning_mark(c, on=victim)


@power(
    "p11051",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p11051(c: Cast) -> None:
    """The Effect is armed after the swing, in the order the card prints
    them, so it is the *next* melee hit that splashes rather than this one.
    It lands whether this attack did or not.
    """
    me = c.me
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    if not c.first:
        return

    def splash(ev: Hit) -> None:
        if ev.attacker != me or not by_melee(c.world, me, ev):
            return
        for foe in sorted(f for f in c.within(1, side="enemy") if f != ev.target):
            c.flat(max(0, c.wis_mod), dtype=DamageType.RADIANT, on=foe)

    c.watch(Hit, splash, until=When.EONT, on=me, label=f"{c.ref} backwash")


def _no_friends_near(world: World, eid: int) -> bool:
    """"You cannot use this power if any allies are within 5 squares of you"."""
    return not any(distance_between(world, eid, a) <= 5 for a in allies_of(world, eid))


@power(
    "p1264",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=WILL),
)
def p1264(c: Cast) -> None:
    """The Effect is armed first: it is owed whether or not the burst caught
    anything, and the body runs once with no target when it did not."""
    if c.first:
        me = c.me

        def dawn(ev: TurnStart) -> None:
            if not ev.ghost and ev.actor in c.enemies() and c.adjacent(ev.actor):
                c.slowed(on=ev.actor)

        c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=c.ref)
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)


@power(
    "p1269",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=FORT),
)
def p1269(c: Cast) -> None:
    """The secondary rolls longhand: the header carries one attack line and
    the splash is the same numbers aimed somewhere else.

    The push is measured from the paladin, which is where the printed "you
    push the target" puts the anchor -- not from the creature they were
    standing next to.
    """
    victim = c.target
    if not c.strike():
        c.half_damage("1d10", c.cha_mod, dtype=DamageType.RADIANT)
        return
    c.damage("1d10", c.cha_mod, dtype=DamageType.RADIANT)
    if victim is None:
        return
    for foe in sorted(e for e in c.within(1, of=victim, side="enemy") if e != victim):
        if c.attack(c.cha_, FORT, on=foe):
            c.damage("1d10", c.cha_mod, dtype=DamageType.RADIANT, on=foe)
            c.push(3, on=foe)


@power(
    "p13562",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p13562(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.str_mod, dtype=DamageType.THUNDER)
    else:
        c.half_damage(c.w(3), c.str_mod, dtype=DamageType.THUNDER)
    if victim is None:
        return
    for foe in sorted(e for e in c.within(2, of=victim, side="enemy") if e != victim):
        c.prone(on=foe)


@power(
    "p13563",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=REF),
)
def p13563(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod, dtype=DamageType.RADIANT)
        c.ongoing(5, DamageType.RADIANT)
    else:
        c.half_damage(c.w(1), c.str_mod, dtype=DamageType.RADIANT)


@power(
    "p13824",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=ANY_CREATURE,
    keywords=[
        *DIVINE_WEAPON, Keyword.NECROTIC, Keyword.FEAR, Keyword.TELEPORTATION,
    ],
    attack=Attack(STR, vs=WILL),
)
def p13824(c: Cast) -> None:
    """The choice is the target's, so it is `c.may(..., who=victim)`: the
    creature deciding whether to run is the one that would be running.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(3), c.str_mod, dtype=DamageType.NECROTIC)
        if victim is not None:
            if c.may("run rather than reel", who=victim):
                c.flee(c.speed_of(victim), on=victim)
            else:
                c.dazed(until=When.SAVE_ENDS, on=victim)
    else:
        c.half_damage(c.w(3), c.str_mod, dtype=DamageType.NECROTIC)
    if not c.first:
        return
    empty = [
        sq
        for sq in sorted(c.area())
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    if empty:
        dest = c.choose(empty, "where the dark puts you")
        if dest is not None:
            c.teleport(distance(c.here, dest), to=dest)


@power(
    "p13825",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[*DIVINE_WEAPON, Keyword.PSYCHIC],
    attack=Attack(STR, vs=FORT),
)
def p13825(c: Cast) -> None:
    """"Cannot shift or make opportunity attacks (save ends both)" is one
    effect: `c.rooted` is the first half, and the second is a refusal hung
    on the same hold, so one saving throw ends both. `c.no_basic` is the
    wrong instrument -- it takes away granted swings and basic attacks too.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.PSYCHIC)
        held = c.rooted(until=When.SAVE_ENDS)
        if held is not None:

            def refuse(ev: OpportunityWindow) -> None:
                if ev.actor == victim:
                    ev.cancel("cannot make opportunity attacks")

            held.subs.append(
                c.world.bus.on(
                    OpportunityWindow, refuse, window=Window.BEFORE, owner=c.me
                )
            )
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.PSYCHIC)
    health = c.world.get(victim, Health)
    if health is not None and health.hp <= 10:
        c.stunned(until=When.EONT)


@power(
    "p16479",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(CON, vs=AC),
)
def p16479(c: Cast) -> None:
    """The aura is lit and nothing more: concealment is not a thing the
    engine has, so the clause that takes it away has nothing to take. The
    aura itself is real -- it is on the board and it follows the paladin.
    See the report.
    """
    if c.cha_ > c.con_:
        bonus, mod = c.cha_, c.cha_mod
    else:
        bonus, mod = c.con_, c.con_mod
    if c.attack(bonus, AC):
        c.damage(c.w(3), mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(3), mod, dtype=DamageType.RADIANT)
    if c.first:
        c.aura(3, until=When.ENCOUNTER, label=f"{c.ref} daylight")


@power(
    "p2260",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=WILL),
    requires=_no_friends_near,
)
def p2260(c: Cast) -> None:
    """No `requires_text`: `chargen.build_for` reads the word "requirement"
    out of the refusal to decide which build can hold a row, and a custom
    message hides it -- the lesson `ranger/level_7.py` records.

    The weakening is an Effect line, so it lands on the misses too.
    """
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.RADIANT)
    c.weakened(until=When.SAVE_ENDS)


@power(
    "p3274",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(STR, vs=WILL),
)
def p3274(c: Cast) -> None:
    """"Save ends both" is one hold: the mark rides on the burn rather than
    bringing a second effect and a second saving throw with it.
    """
    if not c.strike():
        c.half_damage("2d6", c.str_mod, dtype=DamageType.THUNDER)
        burning_mark(c)
        return
    c.damage("2d6", c.str_mod, dtype=DamageType.THUNDER)
    burn = c.ongoing(5, DamageType.THUNDER)
    if burn is None:
        burning_mark(c, until=When.SAVE_ENDS)
    else:
        burning_mark(c, hold=burn)


@power(
    "p7260",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=FORT),
)
def p7260(c: Cast) -> None:
    """A solid obstacle is a square the shove could not have continued into
    -- a wall, or the edge of the board. The extra die is rolled rather than
    added to the attack's own, so a critical does not maximise it.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.str_mod)
    c.push(5)
    theirs = squares_of(c.world, victim)
    walled = any(
        not c.world.grid.inside(sq) or not c.world.grid.passable(sq)
        for sq in spread(theirs, 1) - theirs
    )
    if walled:
        c.flat(c.roll(c.w(1)), on=victim)


def _ally_hurt_within(radius: int, *, weapon: bool = False):  # noqa: ANN202
    """An enemy within `radius` has just damaged an ally of mine.

    Declared on `DamageRolled` rather than on the printed `Hit`: both rows
    below move or reduce the damage, and by the time a `Hit` is announced
    the only thing left to change is a number that has not been made yet.
    """

    def check(world: World, me: int, ev: Event) -> bool:
        struck = getattr(ev, "target", None)
        foe = getattr(ev, "source", None)
        if struck is None or foe is None or struck == me:
            return False
        if getattr(ev, "amount", 0) <= 0:
            return False
        if team(world, struck) is not team(world, me):
            return False
        if team(world, foe) is team(world, me):
            return False
        if distance_between(world, me, foe) > radius:
            return False
        return not weapon or by_melee(world, me, ev) or by_ranged(world, me, ev)

    return check


_ALLY_STRUCK_AT_TEN = "an enemy within 10 squares hits your ally with a melee or ranged attack"


@power(
    "p7261",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_ALLY_STRUCK_AT_TEN,
    on=Trigger(
        DamageRolled,
        when=_ally_hurt_within(10, weapon=True),
        text=_ALLY_STRUCK_AT_TEN,
    ),
)
def p7261(c: Cast) -> None:
    """"Hits you instead of the ally" is the damage moving, which is what
    `c.absorb` does -- an attack that hits for nothing is not stepped in
    front of, because there is nothing to take.

    The row is declared with no target and finds the enemy on the event:
    a `DamageRolled` names its attacker `source`, which the dispatcher's
    own targeting does not read.
    """
    foe = getattr(c.trigger, "source", None)
    if foe is None:
        return
    c.absorb()
    landing = _beside(c, c.me)
    if landing:
        c.pull(
            max(1, c.distance(foe)),
            on=foe,
            to=min(landing, key=lambda sq: (distance(sq, c.here), sq)),
        )
    if c.strike(on=foe):
        c.damage(c.w(2), c.str_mod, on=foe)
        burning_mark(c, on=foe, until=When.ENCOUNTER)


_ALLY_STRUCK_AT_FIVE = "an enemy within 5 squares hits your ally"


@power(
    "p7262",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=FORT),
    trigger=_ALLY_STRUCK_AT_FIVE,
    on=Trigger(
        DamageRolled, when=_ally_hurt_within(5), text=_ALLY_STRUCK_AT_FIVE
    ),
)
def p7262(c: Cast) -> None:
    ev = c.trigger
    foe = getattr(ev, "source", None)
    if foe is None:
        return
    ev.amount //= 2
    if c.strike(on=foe):
        c.damage("3d6", c.cha_mod, dtype=DamageType.RADIANT, on=foe)
    else:
        c.half_damage("3d6", c.cha_mod, dtype=DamageType.RADIANT, on=foe)


@power(
    "p7263",
    level=9,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(CHA, vs=AC),
)
def p7263(c: Cast) -> None:
    """The hold sits on the target, because a save-ends effect is rolled by
    whoever is carrying it, and the watcher hangs off that hold so the two
    end together.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.cha_mod)
    recoil = c.effect(f"{c.ref} recoil", until=When.SAVE_ENDS, on=victim)
    if recoil is None:
        return
    me = c.me

    def sear(ev: DamageApplied) -> None:
        if ev.source == victim and ev.amount > 0 and ev.target != victim:
            c.flat(c.roll("2d6"), dtype=DamageType.RADIANT, on=victim)

    recoil.subs.append(c.world.bus.on(DamageApplied, sear, owner=me))
