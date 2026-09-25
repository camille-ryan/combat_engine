"""Paladin, level 3: encounter attacks.

`p13447` is declared on `Hit` and on `Miss` rather than on the printed
"you target an enemy with an at-will weapon attack". A free action resolves
in the *after* window, which for `AttackDeclared` is after the roll and its
consequences -- so the printed moment has already passed by the time the row
could run, and the half of the row that asks whether the attack hit has
nothing to read. Answering both outcomes fires exactly once per attack and
knows which one happened.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    NO_TARGET,
    ONE_CREATURE,
    REACTION,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Event,
    Gear,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    Relation,
    Trigger,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import DamageApplied
from combat_engine.engine.grid import distance, spread
from combat_engine.engine.query import adjacent, team
from combat_engine.engine.query import squares as squares_of

from .marks import burning_mark

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


def _str_or_cha(c: Cast) -> tuple[int, int]:
    """"Strength or Charisma": the better of the two. See `level_1_b.py`."""
    if c.cha_ > c.str_:
        return c.cha_, c.cha_mod
    return c.str_, c.str_mod


def _has_bow(world: World, eid: int) -> bool:
    """"Requirement: you must be wielding a bow"."""
    gear = world.get(eid, Gear)
    bow = gear.ranged if gear is not None else None
    return bow is not None and bow.group == "bow"


def _holds_a_mark(world: World, eid: int) -> bool:
    """"One creature marked by you" -- there has to be one."""
    return bool(world.relations.targets(Relation.MARKED_BY, eid))


@power(
    "p10099",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.NECROTIC, Keyword.FEAR],
    attack=Attack(STR, vs=FORT),
)
def p10099(c: Cast) -> None:
    """It bolts under its own power, so `c.flee` rather than a push: the
    printed line is "it moves", which provokes on the way out.
    """
    victim = c.target
    bonus, mod = _str_or_cha(c)
    if victim is None or not c.attack(bonus, FORT):
        return
    c.damage(c.w(2), mod, dtype=DamageType.NECROTIC)
    bolted: list[bool] = []

    def run(ev: DamageApplied) -> None:
        if bolted or ev.target != victim or ev.amount <= 0:
            return
        bolted.append(True)
        c.flee(c.speed_of(victim), on=victim)

    c.watch(DamageApplied, run, until=When.SONT, on=c.me, label=f"{c.ref} rout")


@power(
    "p10248",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[*DIVINE_WEAPON, Keyword.COLD],
    attack=Attack(STR, vs=AC),
)
def p10248(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod, dtype=DamageType.COLD)
    if c.marked():
        c.immobilized()
    else:
        c.slowed()


@power(
    "p12304",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RANGED],
    attack=Attack(CHA, vs=AC),
    requires=_has_bow,
)
def p12304(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        burning_mark(c)


@power(
    "p1243",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1243(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.mark()


_AT_WILL_SWING = "you attack an enemy with an at-will weapon power"


def _my_at_will_weapon_attack(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return (
        p is not None
        and p.usage is Usage.AT_WILL
        and Keyword.WEAPON in p.keywords
        and getattr(ev, "target", None) != me
    )


@power(
    "p13447",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.RADIANT],
    trigger=_AT_WILL_SWING,
    on=[
        Trigger(Hit, when=_my_at_will_weapon_attack, text=_AT_WILL_SWING),
        Trigger(Miss, when=_my_at_will_weapon_attack, text=_AT_WILL_SWING),
    ],
)
def p13447(c: Cast) -> None:
    """"Psychic and radiant damage" is one packet of two types, which the
    engine's `DamageType` cannot hold; it is dealt as the first of the two
    printed rather than twice. See the report.
    """
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is None:
        return
    c.flat(c.cha_mod, dtype=DamageType.PSYCHIC, on=victim)
    if isinstance(ev, Hit):
        c.invisible(to=victim, until=When.EONT)


@power(
    "p1568",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(CHA, vs=WILL),
)
def p1568(c: Cast) -> None:
    """The allies' healing is its own sentence and carries no "if you are
    bloodied", so bloodied friends are picked up whether the paladin is
    hurt or not. Only the caster's own line waits on being bloodied.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.cha_mod)
    amount = 5 + c.wis_mod
    if c.bloodied(on=c.me):
        c.heal(amount, on=c.me)
    for friend in c.within(5, side="ally"):
        if friend != c.me and c.bloodied(on=friend):
            c.heal(amount, on=friend)


@power(
    "p2259",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2259(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.push(max(0, c.wis_mod))


@power(
    "p3694",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(CHA, vs=AC),
)
def p3694(c: Cast) -> None:
    if c.first:
        c.save(on=c.me, bonus=c.wis_mod)
    if c.strike():
        c.damage(c.w(2), c.cha_mod)


_ADJACENT_FOE_HITS_ALLY = "an enemy adjacent to you hits your ally"


def _adjacent_foe_hits_ally(world: World, me: int, ev: Event) -> bool:
    struck = getattr(ev, "target", None)
    foe = getattr(ev, "attacker", None)
    if struck is None or foe is None or struck == me:
        return False
    if team(world, struck) is not team(world, me):
        return False
    return team(world, foe) is not team(world, me) and adjacent(world, me, foe)


@power(
    "p7250",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(CHA, vs=AC),
    trigger=_ADJACENT_FOE_HITS_ALLY,
    on=Trigger(Hit, when=_adjacent_foe_hits_ally, text=_ADJACENT_FOE_HITS_ALLY),
)
def p7250(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        c.immobilized()


@power(
    "p7251",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(CHA, vs=WILL),
    requires=_holds_a_mark,
)
def p7251(c: Cast) -> None:
    """The secondary swings a weapon while the row is declared an implement
    power, so the proficiency has to be added by hand: `c.cha_` only counts
    it for a row carrying `Keyword.WEAPON`, and this one does not carry it
    because the primary is not one.

    The pull names its destination -- "to a square adjacent to you" is an
    instruction rather than a direction.
    """
    victim = c.target
    if victim is None or not c.marked(victim) or not c.strike():
        return
    mine = squares_of(c.world, c.me)
    beside = [
        sq
        for sq in spread(mine, 1) - mine
        if c.world.grid.inside(sq)
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
    ]
    if beside:
        landing = min(beside, key=lambda sq: (distance(sq, c.there), sq))
        c.pull(max(1, c.distance(victim)), on=victim, to=landing)
    gear = c.world.get(c.me, Gear)
    prof = gear.main.proficiency if gear is not None and gear.main is not None else 0
    if c.attack(c.cha_ + 2 + prof, AC, on=victim):
        c.damage(c.w(2), c.cha_mod, on=victim)


@power(
    "p7252",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7252(c: Cast) -> None:
    """The Special line -- this row in place of a melee basic attack -- has
    no header field; see the report."""
    bonus, mod = _str_or_cha(c)
    if c.attack(bonus, AC):
        c.damage(c.w(2), mod)
        c.condition(Condition.IMMOBILIZED)


@power(
    "p7253",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p7253(c: Cast) -> None:
    """"5 temporary hit points for each target hit" accumulates across a
    body that is called once per target, and temporary hit points do not
    stack -- the larger pool wins. So each hit asks for five more than is
    standing, which comes to five per hit.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    health = c.world.get(c.me, Health)
    c.temp_hp((health.temp if health is not None else 0) + 5, on=c.me)


@power(
    "p754",
    level=3,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,  # the healing keyword was errata'd off this row
    attack=Attack(CHA, vs=AC),
)
def p754(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        amount = 5 + c.wis_mod
        for friend in c.within(5, side="ally"):  # the ally pool has the caster in it
            c.temp_hp(amount, on=friend)
