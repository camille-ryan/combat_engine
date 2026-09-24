"""Monster abilities, level 3: the brutes and the soldiers beside them.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=8)` and `Damage("2d6", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defense,
    Health,
    Ident,
    Keyword,
    Melee,
    Position,
    Powers,
    Ranged,
    Relation,
    Size,
    UpTo,
    Usage,
    When,
    World,
    distance,
    power,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    Dropped,
    Hit,
    Miss,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import alive, distance_between, flanked_by, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    ally_within,
    both,
    by_melee,
    hits_me,
    targets_me,
)

#: The four defences, for the rows whose bonus is to all of them at once.
ALL_DEFENCES = (Defense.AC, Defense.FORT, Defense.REF, Defense.WILL)

#: "Medium size or smaller" -- `Size` is a `StrEnum`, so it does not order.
NO_BIGGER_THAN_MEDIUM = (Size.TINY, Size.SMALL, Size.MEDIUM)


def _same_row(c: Cast, who: int, ref: str) -> bool:
    """Is that creature another of this stat block?

    By id. A body is never told what anything is called, and `c.is_kind`
    answers about type words -- goblin, undead -- which several different
    stat blocks share.
    """
    ident = c.world.get(who, Ident)
    return ident is not None and ident.ref == ref


def _kin(c: Cast, radius: int, ref: str) -> list[int]:
    """Allies of the same stat block within `radius`, leaving the caster out."""
    return [
        a
        for a in c.within(radius, side="ally")
        if a != c.me and _same_row(c, a, ref)
    ]


def _is_kind(world: World, who: int, word: str) -> bool:
    """`Cast.is_kind` for a trigger predicate, which runs before any `Cast`
    exists. The type words are read off the stat block either way."""
    return Cast(world=world, me=who, ref="").is_kind(word, on=who)


def _taking_ongoing(c: Cast, who: int | None, dtype: DamageType) -> bool:
    """Is that creature already carrying ongoing damage of this type?"""
    if who is None:
        return False
    return any(
        eff.ongoing is not None and eff.ongoing[1] is dtype
        for eff in c.world.effects.of(who)
    )


def _holding(world: World, eid: int) -> list[int]:
    """Whoever this creature has hold of."""
    return list(world.relations.targets(Relation.GRABBED_BY, eid))


def _beside(c: Cast, square: tuple[int, int], who: int) -> bool:
    """Would standing on that square put the caster next to that creature?"""
    pos = c.world.get(who, Position)
    return pos is not None and distance(square, pos.square) <= 1


# -- m241 -------------------------------------------------------------------


@power(
    "m241a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 5),
)
def m241a0(c: Cast) -> None:
    """Bloodied swaps the dice rather than adding to them, so the header
    keeps the printed line that rescales and the larger expression is rolled
    in the body instead."""
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("2d10", 5)
    else:
        c.hit()


_M241_MISSED = "the m241 is missed by a melee attack"


@power(
    "m241a2",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M241_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M241_MISSED),
)
def m241a2(c: Cast) -> None:
    c.shift(1)


# -- m248 -------------------------------------------------------------------


@power(
    "m248a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m248a0(c: Cast) -> None:
    """The printed damage line is untyped and only the ongoing is necrotic,
    which is why the header carries no `dtype`."""
    if not c.strike():
        return
    c.hit()
    c.ongoing(5, DamageType.NECROTIC)
    if c.size_of() in NO_BIGGER_THAN_MEDIUM:
        c.prone()


_M248_DOWN = "the m248 drops to 0 hit points"


@power(
    "m248a1",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    trigger=_M248_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M248_DOWN),
)
def m248a1(c: Cast) -> None:
    """One last bite, fired through m248a0 so that line stays in one place.

    `Dropped` is announced before `_check_down` lays the unconscious hold
    on, so the creature is still able to answer its own death -- which is
    the only window this row has.
    """
    use(c.world, c.me, "m248a0", targets=[c.target], spend=False)


@power(
    "m248a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m248a2(c: Cast) -> None:
    """A critical takes it apart outright.

    `Hit` is announced before the damage is rolled, so answering it takes the
    rest of the hit points off first and the critical's own damage lands on a
    thing that is already down -- which is the printed order.
    """
    me = c.me

    def shatter(ev: Hit) -> None:
        if ev.target != me or not ev.critical:
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.flat(health.hp, on=me)

    c.watch(Hit, shatter, until=When.ENCOUNTER, on=me, label="m248a2")


# -- m277 -------------------------------------------------------------------


@power(
    "m277a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 4),
)
def m277a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()
        c.mark()


@power(
    "m277a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 4),
)
def m277a1(c: Cast) -> None:
    """The step is an Effect line, so it is taken whether or not the swing
    landed -- but only where it can end beside another of its own kind, which
    is what "provided" means. No such square, no step.

    The printed Requirement is the weapon in its hands; a monster has no
    `Gear`, so gating the row on one would refuse it forever.
    """
    if c.strike():
        c.hit()
    kin = _kin(c, 10, "m277")
    if not kin:
        return
    spots = [
        sq
        for sq in c.world.reachable_squares(c.me, 1)
        if any(_beside(c, sq, other) for other in kin)
    ]
    if spots:
        c.shift(1, to=spots[0])


_M277_SAVEABLE = "the m277 suffers an effect that a save can end"


def _save_ends_on_me(world: World, me: int, ev: ConditionApplied) -> bool:
    """A save-ends effect landing on this creature.

    `ConditionApplied` is the only announcement an effect makes, so this
    catches the ones carrying a condition and misses a bare ongoing-damage
    effect, which announces nothing at all. See the report.
    """
    return ev.target == me and ev.duration == When.SAVE_ENDS.value


@power(
    "m277a2",
    level=3,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M277_SAVEABLE,
    on=Trigger(ConditionApplied, when=_save_ends_on_me, text=_M277_SAVEABLE),
)
def m277a2(c: Cast) -> None:
    c.save(on=c.me)


@power(
    "m277a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m277a3(c: Cast) -> None:
    """A standing bonus rather than an action, whatever the section line says.

    Who it is standing beside is the whole condition and changes every time
    anything moves, so the gate is asked at the moment of the attack rather
    than when the trait is armed.
    """
    c.bonus(
        Defense.AC,
        2,
        until=When.ENCOUNTER,
        on=c.me,
        when=lambda _ctx: bool(_kin(c, 1, "m277")),
    )


# -- m2799 ------------------------------------------------------------------


def _empty_handed(world: World, eid: int) -> bool:
    return not _holding(world, eid)


def _has_hold(world: World, eid: int) -> bool:
    return bool(_holding(world, eid))


@power(
    "m2799a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 3),
    requires=_empty_handed,
    requires_text="the m2799 must not have a creature grabbed",
)
def m2799a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m2799a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 3, dtype=DamageType.ACID),
    requires=_has_hold,
    requires_text="the m2799 must have a creature grabbed",
)
def m2799a1(c: Cast) -> None:
    """The printed target is "a creature grabbed by the m2799", which no
    `Target` can say, so the header takes one enemy and the body aims at
    whoever is actually being held."""
    held = _holding(c.world, c.me)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(5, DamageType.ACID, on=victim)


_M2799_DOWN = "the m2799 drops to 0 hit points"


@power(
    "m2799a2",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=8),
    trigger=_M2799_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M2799_DOWN),
)
def m2799a2(c: Cast) -> None:
    """A death spasm that knocks down and deals no damage at all."""
    if c.strike():
        c.prone()


_M2799_KIN_DOWN = "an ally within 10 squares of the m2799 drops to 0 hit points"


@power(
    "m2799a3",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2799_KIN_DOWN,
    on=Trigger(Dropped, when=ally_within(10), text=_M2799_KIN_DOWN),
)
def m2799a3(c: Cast) -> None:
    """The printed line names one family of stat blocks rather than a type
    word, and nothing can ask that -- `_same_row` matches this stat block
    alone, which is narrower. Any ally within 10 is the nearest thing
    sayable; see the report."""
    c.bonus("attack", 2, until=When.EONT, on=c.me)


# -- m291 -------------------------------------------------------------------


@power(
    "m291a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 6),
)
def m291a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m291a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 10, kind=LIMITED),
)
def m291a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m291a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 7),
)
def m291a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# -- m2979 ------------------------------------------------------------------


@power(
    "m2979a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2979a0(c: Cast) -> None:
    """Five separate modifiers: one names a single thing, and "all defenses"
    is four of them. Each is gated at the moment it is read, because who it
    is standing near changes every turn.
    """
    me = c.me

    def escorted(_ctx: object) -> bool:
        return any(
            c.is_kind("drow", on=a) for a in c.within(5, side="ally") if a != me
        )

    c.bonus("attack", 2, until=When.ENCOUNTER, on=me, when=escorted)
    for which in ALL_DEFENCES:
        c.bonus(which, 2, until=When.ENCOUNTER, on=me, when=escorted)


def _crit_line(c: Cast, dice: str, bonus: int) -> None:
    """A printed "or NdX + n on a critical hit" line.

    It *replaces* the damage rather than adding to it, and it is a roll --
    so it is applied flat, past the engine's own rule that a critical maxes
    the declared dice, which would read the wrong number off this header.
    """
    if c.crit:
        c.flat(c.roll(dice) + bonus)
    else:
        c.hit()


@power(
    "m2979a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 2),
)
def m2979a1(c: Cast) -> None:
    if not c.strike():
        return
    _crit_line(c, "3d8", 2)
    c.mark()


@power(
    "m2979a2",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 2, kind=LIMITED),
)
def m2979a2(c: Cast) -> None:
    """The poison the target is already taking is raised in place rather than
    a second helping being laid on top, which is what "increases by 5" says
    and is the difference between one saving throw and two."""
    if not c.strike():
        return
    _crit_line(c, "3d8", 2)
    for eff in c.world.effects.of(c.target):
        if eff.ongoing is not None and eff.ongoing[1] is DamageType.POISON:
            eff.ongoing = (eff.ongoing[0] + 5, DamageType.POISON)


#: The three kinds the blast goes round.
_M2979_SPARED = ("drow", "goblin", "spider")


@power(
    "m2979a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d10", dtype=DamageType.THUNDER, kind=LIMITED),
)
def m2979a3(c: Cast) -> None:
    """Everything in the blast, minus three kinds -- not "enemies": an ally
    that is none of the three is caught, which is the printed line."""
    if any(c.is_kind(word) for word in _M2979_SPARED):
        return
    if c.strike():
        c.hit()


_M2979_ESCORT = "an attack is made against a drow ally adjacent to the m2979"


def _adjacent_drow_ally(world: World, me: int, ev: AttackDeclared) -> bool:
    """The printed line names a kind as well as a side, and no ready-made
    predicate reads a type word."""
    who = getattr(ev, "target", None)
    if who is None or who == me:
        return False
    if team(world, who) is not team(world, me):
        return False
    if distance_between(world, me, who) > 1:
        return False
    return _is_kind(world, who, "drow")


@power(
    "m2979a4",
    level=3,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2979_ESCORT,
    on=Trigger(AttackDeclared, when=_adjacent_drow_ally, text=_M2979_ESCORT),
)
def m2979a4(c: Cast) -> None:
    """"Hits or misses" means the blow is taken over before it is rolled,
    which is the one window `c.redirect` works in."""
    c.redirect(to=c.me)


_M2979_MISSED = "the m2979 is missed by a melee attack"


@power(
    "m2979a5",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2979_MISSED,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M2979_MISSED),
)
def m2979a5(c: Cast) -> None:
    c.shift(1)


# -- m298 -------------------------------------------------------------------


@power(
    "m298a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 6),
)
def m298a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# -- m3031 ------------------------------------------------------------------


@power(
    "m3031a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3031a0(c: Cast) -> None:
    """Whether the victim is burning changes between one swing and the next,
    so the gate is read at the moment of the damage rather than stored."""
    c.bonus(
        "damage",
        2,
        until=When.ENCOUNTER,
        on=c.me,
        when=lambda ctx: _taking_ongoing(c, ctx.get("target"), DamageType.POISON),
    )


@power(
    "m3031a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m3031a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


# -- m3039 ------------------------------------------------------------------

#: The hold m3039a1 lays down and m3039a0 reads. The two printed lines are
#: separate rows and neither can reach the other's closure, so the coupling
#: between them is a label on an effect.
_M3039_STIFLED = "m3039a1 stifled"


@power(
    "m3039a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3039a0(c: Cast) -> None:
    """Regeneration, written out: the engine holds no such thing."""
    me = c.me

    def regenerate(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        health = c.world.get(me, Health)
        if health is None or health.hp <= 0:
            return
        if any(eff.label == _M3039_STIFLED for eff in c.world.effects.of(me)):
            return
        c.heal(5, on=me)

    c.watch(TurnStart, regenerate, until=When.ENCOUNTER, on=me, label="m3039a0")


@power(
    "m3039a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3039a1(c: Cast) -> None:
    """The burn that switches the regeneration off. A named hold with no
    mechanical content of its own is exactly what `c.effect` is for."""
    me = c.me

    def scald(ev: DamageApplied) -> None:
        if ev.target != me or ev.dtype is not DamageType.RADIANT or ev.amount <= 0:
            return
        c.effect(_M3039_STIFLED, until=When.EONT, on=me)

    c.watch(DamageApplied, scald, until=When.ENCOUNTER, on=me, label="m3039a1")


@power(
    "m3039a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d10", 3),
)
def m3039a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3039a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d12", 5, dtype=DamageType.NECROTIC),
)
def m3039a3(c: Cast) -> None:
    if c.strike():
        c.hit()


_M3039_STRUCK = "the m3039 is hit while a m3039 ally is within 5 squares"


def _hit_with_kin_near(world: World, me: int, ev: Hit) -> bool:
    probe = Cast(world=world, me=me, ref="m3039a4")
    return hits_me(world, me, ev) and bool(_kin(probe, 5, "m3039"))


@power(
    "m3039a4",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3039_STRUCK,
    on=Trigger(Hit, when=_hit_with_kin_near, text=_M3039_STRUCK),
)
def m3039a4(c: Cast) -> None:
    """Sharing the blow out between two of them.

    `Hit` is announced before the damage is rolled, and `DamageRolled`
    carries a mutable `amount` -- so the half that is taken off here is the
    same half that is handed to the other one, which is the only way a row
    reading "each take half damage" can be written. The watcher is armed for
    this turn only and fires once, so a second blow is not split for free.
    """
    me = c.me
    kin = _kin(c, 5, "m3039")
    if not kin:
        return
    friend = min(kin, key=c.distance)

    def split(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        share = ev.amount // 2
        ev.amount -= share
        if share:
            c.flat(share, dtype=ev.dtype, on=friend)

    c.watch(
        DamageRolled, split, until=When.EOT, on=me, once=True, label="m3039a4"
    )


_M3039_DOWN = "the m3039 drops to 0 hit points"


@power(
    "m3039a6",
    level=3,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M3039_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M3039_DOWN),
)
def m3039a6(c: Cast) -> None:
    """The printed target is "one living creature", not one ally, so the
    burst is read for everybody standing in it and the choice is made rather
    than aimed."""
    nearby = [
        w for w in c.in_squares(c.area()) if w != c.me and alive(c.world, w)
    ]
    if not nearby:
        return
    c.heal(10, on=c.choose(sorted(nearby), "who is mended"))


# -- m371 -------------------------------------------------------------------


@power(
    "m371a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 1),
)
def m371a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.ACID)


@power(
    "m371a2",
    level=3,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m371a2(c: Cast) -> None:
    c.shift(4)


# -- m416 -------------------------------------------------------------------


@power(
    "m416a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
)
def m416a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


# -- m476 -------------------------------------------------------------------


@power(
    "m476a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m476a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none means."""
    if c.strike():
        c.hit()


# -- m4851 ------------------------------------------------------------------


@power(
    "m4851a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4851a1(c: Cast) -> None:
    """Shared sight, hearing and speech, and nothing else. Declared inert
    rather than given an invented mechanic."""
    c.note("m4851a1: its master sees, hears and speaks through it")


@power(
    "m4851a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 4),
)
def m4851a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


# -- m4925 ------------------------------------------------------------------

#: The two shapes m4925a4 moves between, as the label on the form effect.
_M4925_JACKAL = "m4925a4 jackal"
_M4925_HUMAN = "m4925a4 human"

#: What m4925a0 pays out against.
_M4925_OPENINGS = (Condition.DAZED, Condition.HELPLESS, Condition.PRONE)


def _not_wearing(label: str):  # noqa: ANN202
    """A Requirement of "must be in <this> form", written as the absence of
    the other one.

    The stat block never says which shape it starts a fight in, so neither
    row is gated on a form being *present*: both are open until m4925a4 has
    actually picked one, and from then on exactly one of them is shut.
    """

    def check(world: World, eid: int) -> bool:
        return not any(eff.label == label for eff in world.effects.of(eid))

    return check


@power(
    "m4925a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4925a0(c: Cast) -> None:
    """An extra die rather than a flat bonus, so it is rolled as the blow
    lands instead of riding along as a damage modifier."""
    me = c.me

    def press(ev: Hit) -> None:
        if ev.attacker != me:
            return
        if any(c.is_(cond, on=ev.target) for cond in _M4925_OPENINGS):
            c.damage("1d6", on=ev.target)

    c.watch(Hit, press, until=When.ENCOUNTER, on=me, label="m4925a0")


@power(
    "m4925a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d6", 2),
    requires=_not_wearing(_M4925_HUMAN),
    requires_text="the m4925 must be in jackal form",
)
def m4925a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4925a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("4d4", 4),
    requires=_not_wearing(_M4925_JACKAL),
    requires_text="the m4925 must be in human form",
)
def m4925a2(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "2d4", 20)


@power(
    "m4925a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4925a3(c: Cast) -> None:
    """m4925a1 twice into one creature, and the daze for landing both.

    The row that prints the bite is used rather than copied, so its damage
    line stays in one place. `use` reports whether a power went off and not
    whether it hit, so the hits are counted off the bus for the pair.
    """
    victim = c.target
    if victim is None:
        return
    landed: list[str] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            landed.append(ev.power)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        for _ in range(2):
            use(c.world, c.me, "m4925a1", targets=[victim], spend=False)
    finally:
        c.world.bus.off(sub)
    if len(landed) == 2:
        c.dazed(on=victim)


@power(
    "m4925a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4925a4(c: Cast) -> None:
    """Either shape, and taking one ends the other.

    The form carries no conditions and no movement modes because the printed
    line says the creature keeps its statistics; all it is here is the label
    the two attack rows read their Requirement off. There is no polymorph
    keyword to declare, and the Insight check to see through it is a skill
    check with no combat content.
    """
    for eff in list(c.world.effects.of(c.me)):
        if eff.label in (_M4925_JACKAL, _M4925_HUMAN):
            c.world.effects.end(eff, "changed shape")
    shape = c.choose([_M4925_JACKAL, _M4925_HUMAN], "which shape")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=shape)


# -- m495 -------------------------------------------------------------------

#: What ending its turn shakes off.
_M495_SHAKEN_OFF = (Condition.DAZED, Condition.STUNNED, Condition.DOMINATED)


@power(
    "m495a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m495a0(c: Cast) -> None:
    """The whole effect ends, not just the condition: a save-ends hold
    carrying a daze and ongoing damage together is one printed effect, and
    ending half of it would leave a hold nothing could ever clear."""
    me = c.me

    def shake_off(ev: TurnEnd) -> None:
        if ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if any(cond in _M495_SHAKEN_OFF for cond in eff.conditions):
                c.world.effects.end(eff, "m495a0")

    c.watch(TurnEnd, shake_off, until=When.ENCOUNTER, on=me, label="m495a0")


@power(
    "m495a3",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("3d10", 4, dtype=DamageType.COLD),
)
def m495a3(c: Cast) -> None:
    """The Miss line is its own expression rather than half the Hit line, so
    it is rolled here instead of declared with `half_on_miss`."""
    if c.strike():
        c.hit()
    else:
        c.damage("1d10", dtype=DamageType.COLD)


@power(
    "m495a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 4),
)
def m495a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m495a5",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m495a5(c: Cast) -> None:
    """m495a4 twice, through the row that prints it. `UpTo(2)` is what lets
    the two swings land on different creatures; pointed at one, that creature
    takes both, which is the same two attacks either way."""
    use(c.world, c.me, "m495a4", targets=[c.target], spend=False)
    if c.first and c.last:
        use(c.world, c.me, "m495a4", targets=[c.target], spend=False)


@power(
    "m495a6",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("3d8", 6, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m495a6(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


_M495_FLANKED = "an enemy hits the m495 while flanking it"


def _flanker_hit_me(world: World, me: int, ev: Hit) -> bool:
    """`hits_me` is half the printed sentence; `query.flanked_by` is the
    other half, and no ready-made predicate reads it."""
    return hits_me(world, me, ev) and flanked_by(world, me, ev.attacker)


@power(
    "m495a7",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d8", 4),
    trigger=_M495_FLANKED,
    on=Trigger(Hit, when=_flanker_hit_me, text=_M495_FLANKED),
)
def m495a7(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(5)


_M495_FIRST_BLOODIED = "the m495 is first bloodied"


@power(
    "m495a8",
    level=3,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M495_FIRST_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M495_FIRST_BLOODIED),
)
def m495a8(c: Cast) -> None:
    """`Powers.restore` is what a recharge is, so the breath comes back up
    and goes off at once. "First bloodied" needs no guard -- `Bloodied` is
    emitted on the crossing and nowhere else."""
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m495a6")
    use(c.world, c.me, "m495a6")


# -- m5032 ------------------------------------------------------------------


@power(
    "m5032a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 2),
)
def m5032a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5032a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5032a1(c: Cast) -> None:
    """m5032a0 twice into one creature, and the hold for landing both --
    counted off the bus, because `use` reports that a row went off and not
    that it hit."""
    victim = c.target
    if victim is None:
        return
    landed: list[str] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            landed.append(ev.power)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        for _ in range(2):
            use(c.world, c.me, "m5032a0", targets=[victim], spend=False)
    finally:
        c.world.bus.off(sub)
    if len(landed) == 2:
        c.grab(on=victim)


@power(
    "m5032a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d6", 2, dtype=DamageType.PSYCHIC),
)
def m5032a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5032a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("2d6", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5032a3(c: Cast) -> None:
    """"Recharge when first bloodied" has no spelling of its own -- the
    header carries the die, which is the closer of the two readings."""
    if c.strike():
        c.hit()
        c.mark(until=When.SAVE_ENDS)


@power(
    "m5032a4",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("1d6", 3, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m5032a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
