"""Monster abilities, level 3: the controllers and the minions beside them.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=7)` and `Damage("1d8", 7)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. A minion's flat damage says so with `kind=MINION`.

Several rows here are filed in the compendium as standard actions and are
plainly traits: a bonus while flanking, a knack for going unnoticed. Those
are written as traits -- `action=ActionType.NONE`, armed once when the
fight starts -- because that is what they do, and a trait offered as an
action is an action nobody would ever take.

Two shapes recur and are settled once.

A **standing modifier with a condition on it** is a gate on the modifier
rather than an effect put on and taken off as the board changes: the gate
is asked when the number is read, so nothing has to watch creatures walking
in and out of a zone and no stored list goes stale.

**Concealment has no state of its own in the engine.** Cover is geometry,
traced at the moment of the attack. The whole rules content of being
concealed is the -2 an attacker takes, so the one row that grants it grants
that number, gated on who is standing where.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
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
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Cover,
    Damage,
    DamageType,
    Ident,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Stats,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    ConditionApplied,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    MoveEnd,
    PowerUsed,
    SurgeSpent,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import cover_between, distance_between, flanked_by, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    by_ranged,
    targets_me,
)


def _conceal(c: Cast) -> None:
    """Unseen by every enemy whose line to the creature is blocked.

    There are no skill checks in the engine, so the printed Stealth check is
    taken as made; the cover is testable and is asked of each enemy
    separately, because one may have a clear line where another does not.
    """
    for foe in c.enemies():
        if not c.is_hidden(from_=foe) and cover_between(c.world, foe, c.me) is not Cover.NONE:
            c.hide(from_=foe)


def _vanish(c: Cast) -> None:
    """Gone from sight until it attacks or the clock runs out.

    Attacking gives it away whether or not the attack lands, so the watch is
    on the roll rather than on the hit, and it is torn down with the veil so
    a second vanishing does not inherit the first one's listener.
    """
    veil = c.invisible(until=When.EONT)
    if veil is None:
        return
    me = c.me

    def reveal(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(veil, "it attacked")

    seen = c.watch(AttackRolled, reveal, until=When.EONT, on=me, label=c.ref)
    veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))


def _same_stock(world: World, a: int, b: int) -> bool:
    """Two creatures off the same stat block. "One of its own kind beside
    it" is a relation between two `Ident.ref`s and nothing else says it."""
    one, two = world.get(a, Ident), world.get(b, Ident)
    return one is not None and two is not None and one.ref == two.ref


def _nonminion(world: World, eid: int) -> bool:
    """Minion-ness is a column on the stat block that reaches no component,
    so it is read off the row the same way `Cast.kinds_of` reads the type
    line. Anything with no stat block behind it is not a minion."""
    from combat_engine.content.loader import load

    ident = world.get(eid, Ident)
    if ident is None or not ident.ref.startswith("m"):
        return True
    try:
        return load(ident.ref).rank != "minion"
    except KeyError:
        return True


_SAVE_ENDS_ON_ME = "it is subjected to an effect that a save can end"


def _save_ends_on_me(world: World, me: int, ev: ConditionApplied) -> bool:
    """A save-ends effect landing on this creature.

    `ConditionApplied` is the only event any effect emits as it is applied,
    so a save-ends hold carrying no condition at all -- ongoing damage, a
    bare named hold -- cannot be seen and does not offer the row.
    """
    return ev.target == me and ev.duration == When.SAVE_ENDS.value


# --------------------------------------------------------------------------
# m235
# --------------------------------------------------------------------------


@power(
    "m235a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4"),
)
def m235a0(c: Cast) -> None:
    """No range printed where the next row prints Ranged 10, so this is the
    creature's melee attack."""
    if c.strike():
        c.hit()


@power(
    "m235a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 4, dtype=DamageType.RADIANT),
)
def m235a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m235a2",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=7),
)
def m235a2(c: Cast) -> None:
    """The target shifts, under its own power, rather than being slid: the
    printed line says shift, and a shift picks its own square."""
    if c.strike():
        c.shift(1, who=c.target)


@power(
    "m235a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=7),
)
def m235a3(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the hold."""
    if c.strike():
        c.slowed(until=When.SAVE_ENDS)


_M235_HURT = "the m235 takes damage"


@power(
    "m235a4",
    level=3,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger=_M235_HURT,
    on=Trigger(DamageApplied, when=targets_me, text=_M235_HURT),
)
def m235a4(c: Cast) -> None:
    _vanish(c)


@power(
    "m235a5",
    level=3,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m235a5(c: Cast) -> None:
    c.teleport(5)


@power(
    "m235a6",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m235a6(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: the moment it names
    is the initiative check, which is when a trait is armed anyway."""
    _conceal(c)


# --------------------------------------------------------------------------
# m238
# --------------------------------------------------------------------------


@power(
    "m238a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 1),
)
def m238a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m238a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 1),
)
def m238a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m238a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("3d6", 1, kind=LIMITED),
)
def m238a2(c: Cast) -> None:
    """The hit lands nothing: the declared damage is the price of moving,
    paid on each of the target's own turns that it moves, until it saves.

    The result of the triggering attack is cleared before the toll is
    charged, because a critical maxes the dice and the crit belonged to the
    attack rather than to the walking.
    """
    if not c.strike():
        return
    victim = c.target
    charged: dict[int, int] = {}

    def toll(ev: MoveEnd) -> None:
        if ev.actor != victim or c.world.turn != victim:
            return
        if charged.get(victim) == c.world.round:
            return
        charged[victim] = c.world.round
        c.result = None
        c.hit(on=victim)

    c.watch(MoveEnd, toll, until=When.SAVE_ENDS, on=victim, label="m238a2")


@power(
    "m238a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE, Keyword.AREA],
)
def m238a3(c: Cast) -> None:
    """A zone with two numbers in it, both written as gated modifiers.

    The penalty rides on every enemy and asks the zone whether that enemy is
    standing in it at the moment it attacks, so nobody has to watch the
    crowd move. The concealment is the same trick from the other end: it is
    a second penalty on the same attackers, asked about the *target*, since
    -2 to attack rolls against the concealed creature is the whole of what
    concealment means and the engine keeps no state for it.

    "Moving the zone up to 5 squares" when sustained has no expression --
    see the report.
    """
    zone = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR)
    ours = {c.me, *c.allies()}

    def in_the_fog(ctx: dict[str, Any]) -> bool:
        return ctx.get("attacker") in c.world.zones.occupants(zone)

    def shrouded(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim in ours and victim in c.world.zones.occupants(zone)

    for foe in c.enemies():
        c.penalty("attack", 2, on=foe, until=When.ENCOUNTER, when=in_the_fog)
        c.penalty("attack", 2, on=foe, until=When.ENCOUNTER, when=shrouded)


_ALLY_SLIPPED = "an ally uses m238a5"


def _ally_slipped(world: World, me: int, ev: PowerUsed) -> bool:
    return (
        ev.power == "m238a5"
        and ev.actor != me
        and team(world, ev.actor) is team(world, me)
        and distance_between(world, me, ev.actor) <= 10
    )


@power(
    "m238a4",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(10),
    target=NO_TARGET,
    trigger=_ALLY_SLIPPED,
    on=Trigger(PowerUsed, when=_ally_slipped, text=_ALLY_SLIPPED),
)
def m238a4(c: Cast) -> None:
    """The ally is read off the event rather than chosen: "the targeted ally"
    is the one that just slipped away, and a row aimed at `ONE_ALLY` would
    have had the dispatcher pick whichever friend happened to be nearest.

    `c.grant_attack` with no `ref` rolls whatever that creature's own basic
    attack is, which for a monster is one of its own abilities.
    """
    friend = getattr(c.trigger, "actor", None)
    if friend is None:
        return
    c.shift(2, who=friend)
    beside = sorted(c.within(1, of=friend, side="enemy"))
    foe = c.choose(beside, "the ally makes a melee basic attack") if beside else None
    if foe is not None:
        c.grant_attack(friend, on=foe)


_M238_MISSED_MELEE = "the m238 is missed by a melee attack"


@power(
    "m238a5",
    level=3,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M238_MISSED_MELEE,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_M238_MISSED_MELEE),
)
def m238a5(c: Cast) -> None:
    c.shift(1)


_M238_SHOT_AT = "the m238 is targeted by a ranged attack"


@power(
    "m238a6",
    level=3,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M238_SHOT_AT,
    on=Trigger(AttackDeclared, when=both(targets_me, by_ranged), text=_M238_SHOT_AT),
)
def m238a6(c: Cast) -> None:
    """`AttackDeclared` rather than the roll: `c.redirect` only works before
    the die is down, because after it there is a result that would have to
    be thrown out and rolled again against a different defence."""
    mine = c.world.get(c.me, Stats)
    if mine is None:
        return
    beside = sorted(
        a
        for a in c.within(1, side="ally")
        if a != c.me
        and (them := c.world.get(a, Stats)) is not None
        and them.level <= mine.level
    )
    friend = c.choose(beside, "the shot finds an ally instead") if beside else None
    if friend is not None:
        c.redirect(to=friend)


# --------------------------------------------------------------------------
# m276
# --------------------------------------------------------------------------


@power(
    "m276a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m276a0(c: Cast) -> None:
    """Gated on the company it keeps, asked when the defence is read."""

    def shoulder_to_shoulder(_ctx: dict[str, Any]) -> bool:
        return any(
            a != c.me and _same_stock(c.world, a, c.me) for a in c.within(1, side="ally")
        )

    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=shoulder_to_shoulder)


@power(
    "m276a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m276a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m276a2",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_SAVE_ENDS_ON_ME,
    on=Trigger(ConditionApplied, when=_save_ends_on_me, text=_SAVE_ENDS_ON_ME),
)
def m276a2(c: Cast) -> None:
    """`c.save` rolls against one save-ends effect and takes the first it
    finds, which is the triggering one in every case but a creature already
    carrying another -- and the engine offers no way to name which."""
    c.save()


# --------------------------------------------------------------------------
# m278
# --------------------------------------------------------------------------


@power(
    "m278a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 7),
)
def m278a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m278a1",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 12, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m278a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m278a2",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 10, dtype=DamageType.FORCE, kind=LIMITED),
)
def m278a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m278a3",
    level=3,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 8, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m278a3(c: Cast) -> None:
    """"Creatures in the blast" catches its own side as readily as anybody
    else's, and a blast never covers the creature it comes from, so
    `EACH_CREATURE` is the printed reading here rather than `EACH_OTHER`.

    Pushed first and put down where it lands, which is the printed order.
    """
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m278a4",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_SAVE_ENDS_ON_ME,
    on=Trigger(ConditionApplied, when=_save_ends_on_me, text=_SAVE_ENDS_ON_ME),
)
def m278a4(c: Cast) -> None:
    c.save()


# --------------------------------------------------------------------------
# m2823
# --------------------------------------------------------------------------


@power(
    "m2823a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m2823a0(c: Cast) -> None:
    """Who is inside is asked of the aura as the surge is spent: the aura
    travels with its owner and a stored list of members would be stale the
    moment either of them moved."""
    ring = c.aura(2, until=When.ENCOUNTER)

    def sicken(ev: SurgeSpent) -> None:
        if ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(ring):
            c.weakened(until=When.EOTNT, on=ev.actor)

    c.watch(SurgeSpent, sicken, until=When.ENCOUNTER, on=c.me, label="m2823a0")


@power(
    "m2823a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2823a1(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m2823a2",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m2823a2(c: Cast) -> None:
    """A reward for the attacker, not a defence: whoever crits drinks."""
    me = c.me

    def gorge(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            c.heal(3, on=ev.attacker)

    c.watch(Hit, gorge, until=When.ENCOUNTER, on=me, label="m2823a2")


@power(
    "m2823a3",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2823a3(c: Cast) -> None:
    """Said once per word, because the two sorts of going are two labels."""
    c.ignores_difficult("mud")
    c.ignores_difficult("shallow water")


@power(
    "m2823a4",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=7, kind=MINION),
)
def m2823a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2823a5",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage(bonus=4, dtype=DamageType.POISON, kind=MINION),
)
def m2823a5(c: Cast) -> None:
    """A blast that picks one creature out of itself, as printed."""
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m2878
# --------------------------------------------------------------------------


@power(
    "m2878a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m2878a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M2878_DROPS = "the m2878 drops to 0 hit points"


@power(
    "m2878a1",
    level=3,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger=_M2878_DROPS,
    on=Trigger(Dropped, when=about_me, text=_M2878_DROPS),
)
def m2878a1(c: Cast) -> None:
    """The nearest of its own sort that is not itself a minion. Ties break on
    the entity id so a replay of the same seed picks the same one."""
    kin = [
        w
        for w in c.within(5)
        if w != c.me and c.is_kind("devil", on=w) and _nonminion(c.world, w)
    ]
    if kin:
        c.heal(15, on=min(kin, key=lambda w: (c.distance(to=w), w)))


# --------------------------------------------------------------------------
# m3019
# --------------------------------------------------------------------------


@power(
    "m3019a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
)
def m3019a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3019a1",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3019a1(c: Cast) -> None:
    """Flanking is combat advantage and combat advantage is +2 here, so the
    printed +3 is that plus one -- written as the extra point rather than as
    a replacement, which nothing can express. The other half of the line,
    aiding another, is a skill action the engine does not have.
    """
    c.bonus(
        "attack",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: flanked_by(c.world, ctx["target"], c.me),
    )


@power(
    "m3019a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m3019a2(c: Cast) -> None:
    c.note("m3019a2: mimics sounds and voices; Insight against its Bluff sees through it")


# --------------------------------------------------------------------------
# m4926
# --------------------------------------------------------------------------

#: The two shapes m4926a3 chooses between, and the prefix its hold is
#: labelled with so the two attacks can read which one is in force.
_SHAPES = ("jackal", "human")
_SHAPE_LABEL = "m4926a3 "


def _in_shape(word: str):  # noqa: ANN202
    """A printed Requirement naming one of the two forms.

    A creature that has not changed shape yet is in whatever shape it was
    found in, which the stat block does not say -- so an undeclared form
    rules out neither attack. Once it has changed, the hold is the answer.
    """

    def gate(world: World, eid: int) -> bool:
        for effect in world.effects.of(eid):
            if effect.label.startswith(_SHAPE_LABEL):
                return effect.label.endswith(word)
        return True

    return gate


@power(
    "m4926a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4926a0(c: Cast) -> None:
    """Whether the blow had combat advantage is on the attack's own result,
    which is the only place that records it after the fact."""
    me = c.me

    def topple(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if ev.attacker == me and result is not None and result.advantage:
            c.prone(on=ev.target)

    c.watch(Hit, topple, until=When.ENCOUNTER, on=me, label="m4926a0")


@power(
    "m4926a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=5, kind=MINION),
    requires=_in_shape("jackal"),
    requires_text="the m4926 must be in its jackal shape",
)
def m4926a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4926a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=3, kind=MINION),
    requires=_in_shape("human"),
    requires_text="the m4926 must be in its human shape",
)
def m4926a2(c: Cast) -> None:
    """The opening is offered to everybody, not to the attacker alone, and it
    closes on the first attack that takes it -- so the hold is spent by a
    watch on the roll rather than by a duration, which could only count
    turns. `c.bonus(once=True)` does this for a modifier and there is no
    equivalent for a grant of combat advantage.
    """
    if not c.strike():
        return
    c.hit()
    opening = c.grants_advantage(to="allies", until=When.SONT)
    if opening is None:
        return
    victim = c.target

    def taken(ev: AttackRolled) -> None:
        if ev.target == victim:
            c.world.effects.end(opening, "the opening was taken")

    seen = c.watch(AttackRolled, taken, until=When.SONT, on=c.me, label="m4926a2")
    opening.on_end.append(lambda: c.world.effects.end(seen, "the opening is gone"))


@power(
    "m4926a3",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4926a3(c: Cast) -> None:
    """Two shapes and nothing else: the statistics do not change, so all the
    form is for is the Requirement on the two attacks above.

    Using it again ends the shape it was in, which `c.form` does not do for
    itself -- a polymorph is not a stance, and this one is printed as one.
    """
    for effect in list(c.world.effects.of(c.me)):
        if effect.label.startswith(_SHAPE_LABEL):
            c.world.effects.end(effect, "it changed shape again")
    shape = c.choose(list(_SHAPES), "which shape") or _SHAPES[0]
    c.form(until=When.ENCOUNTER, revert=None, label=f"{_SHAPE_LABEL}{shape}")


# --------------------------------------------------------------------------
# m499
# --------------------------------------------------------------------------


@power(
    "m499a0",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=6, kind=MINION),
)
def m499a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m4991
# --------------------------------------------------------------------------


@power(
    "m4991a0",
    level=3,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4991a0(c: Cast) -> None:
    c.note("m4991a0: no Stealth penalty for moving more than 2 squares or for running")


@power(
    "m4991a1",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 6),
)
def m4991a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4991a2",
    level=3,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=6),
)
def m4991a2(c: Cast) -> None:
    """No damage at all: the hit is four squares of walking and a daze."""
    if c.strike():
        c.slide(4)
        c.dazed(until=When.EONT)


@power(
    "m4991a3",
    level=3,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4991a3(c: Cast) -> None:
    """"Cannot see enemies other than the m4991" is the target's enemies --
    this creature's own side -- going unseen by it, one relation each, held
    on a single effect so they end together when it saves.

    `c.invisible` says exactly this and only ever about the caster, so the
    relations are laid by hand. See the report.
    """
    if not c.strike():
        return
    c.hit()
    blinkered = [(Relation.HIDDEN_FROM, friend, c.target) for friend in c.allies()]
    if blinkered:
        c.world.effects.apply(
            c.target,
            c.me,
            When.SAVE_ENDS,
            label=f"{c.ref} sees only the one",
            relations=blinkered,
        )


@power(
    "m4991a4",
    level=3,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m4991a4(c: Cast) -> None:
    c.note("m4991a4: appears as any Medium or Small humanoid; Insight sees through it")
