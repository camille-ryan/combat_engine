"""Monster abilities, level 1.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=6)` and `Damage("1d10", 5)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    Condition,
    Damage,
    DamageType,
    Health,
    Hit,
    Keyword,
    Melee,
    Relation,
    TurnStart,
    Usage,
    When,
    power,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import SurgeSpent
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive

from . import aquatic_edge, settle


@power(
    "m145a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 5),
)
def m145a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        # The disease is a save at the end of the fight, not during it, so
        # it hangs on the encounter clock and rolls once when that runs out.
        c.condition(until=When.ENCOUNTER, save_mod=0)


@power(
    "m280a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d6", 4),
)
def m280a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1063a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d10", 4),
)
def m1063a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m206a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d8", 2),
)
def m206a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m206a1",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("3d6", 1, dtype=DamageType.FIRE, kind=LIMITED),
)
def m206a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2821a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m2821a0(c: Cast) -> None:
    """An aura 2 for the board to draw, and the rule hung off `SurgeSpent`.

    Who is inside is asked when the surge is spent rather than kept as a
    list: the aura travels with the creature and a stored membership would
    be stale the moment either of them moved.
    """
    c.aura(2, until=When.ENCOUNTER)

    def sicken(ev: SurgeSpent) -> None:
        if ev.actor in c.enemies() and c.distance(ev.actor) <= 2:
            c.weakened(until=When.EOTNT, on=ev.actor)

    c.watch(SurgeSpent, sicken, until=When.ENCOUNTER, on=c.me, label="m2821a0")


@power(
    "m2821a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2821a1(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m2821a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m2821a2(c: Cast) -> None:
    """A standing arrangement, not an action: it arms a watch on being hit
    critically and pays the attacker, and the watch runs for the fight."""
    me = c.me

    def reward(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            c.heal(3, on=ev.attacker)

    c.watch(Hit, reward, until=When.ENCOUNTER, label=f"{c.ref} crit")


@power(
    "m2821a4",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d8", 2),
)
def m2821a4(c: Cast) -> None:
    """The extra die against a prone target is a second expression, so it is
    rolled in the body rather than folded into the header's damage."""
    if c.strike():
        c.hit()
        if c.is_(Condition.PRONE):
            c.damage("1d6")


@power(
    "m2821a5",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires_text="replaces a melee basic attack on a charge",
    attack=Attack(vs=FORT, printed=4),
    damage=Damage("3d6", 6, kind=LIMITED),
)
def m2821a5(c: Cast) -> None:
    """The printed Requirement is a charge, which nothing here can test, so it
    is carried as text and the row is left usable. Prone is read before it is
    applied, or the extra die would always land."""
    if c.strike():
        was_prone = c.is_(Condition.PRONE)
        c.hit()
        if was_prone:
            c.damage("1d6")
        c.prone()
    else:
        c.flat(3, on=c.me)
        c.prone(on=c.me)


@power(
    "m2939a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m2939a0(c: Cast) -> None:
    """No range is printed on either of this creature's attack lines; melee 1
    is the default a stat block that gives none means."""
    if c.strike():
        c.hit()


@power(
    "m2939a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=5),
    damage=Damage("1d4", 4, dtype=DamageType.PSYCHIC),
)
def m2939a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized()


@power(
    "m2939a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m2939a2(c: Cast) -> None:
    """Settling on something helpless and finishing it, for a full meal.

    The header repeats m2939a0's line because a coup de grace is made with a
    melee basic attack and `c.coup_de_grace` rolls whatever the header
    declares. It also does the checking -- helpless or unconscious -- so the
    printed restriction on the target is not restated here.
    """
    settle(c)
    if not c.coup_de_grace():
        return
    c.hit()
    health = c.world.get(c.me, Health)
    if health is not None and not alive(c.world, c.target):
        c.heal(health.max_hp, on=c.me)


@power(
    "m2939a3",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="this creature makes an opportunity attack",
)
def m2939a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m441a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m441a0(c: Cast) -> None:
    """The grab's lightning is not part of the hit: it lands at the start of
    each of the grabber's own turns for as long as the grab holds, so it hangs
    off the turn clock and re-checks the relation every time."""
    if not c.strike():
        return
    c.hit()
    if c.size_of().squares > 1:  # Medium or smaller: one square on a side
        return
    c.grab()
    me, held = c.me, c.target

    def burn(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if c.world.relations.holds(Relation.GRABBED_BY, me, held):
            c.flat(5, dtype=DamageType.LIGHTNING, on=held)

    c.watch(TurnStart, burn, until=When.ENCOUNTER, label=f"{c.ref} grip")


@power(
    "m441a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d4", 3),
)
def m441a1(c: Cast) -> None:
    """"Save ends both" is one effect carrying both halves, so the victim gets
    one saving throw rather than two."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.POISON),
        )


@power(
    "m441a2",
    level=1,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="an enemy this creature has grabbed escapes",
)
def m441a2(c: Cast) -> None:
    """The printed line is "makes m441a1 against the enemy", so it uses that
    row rather than restating its numbers; free of charge, being an at-will."""
    use(c.world, c.me, "m441a1", targets=[c.target], spend=False)


@power(
    "m4879a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4879a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m4879a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 6),
)
def m4879a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4879a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m4879a2(c: Cast) -> None:
    """The Effect line moves before the attack, so the shift is guarded by
    `c.first` -- one shift for the power, not one per target."""
    if c.first:
        c.shift(c.speed_of(c.me))
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4879a3",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
)
def m4879a3(c: Cast) -> None:
    if c.strike():
        c.pull(2)
