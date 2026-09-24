"""Monster abilities, level 6: the artillery, and then the minions.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=FORT,
printed=11)` and `Damage("2d6", 4)` -- and the engine takes the level back
out of the attack and rescales the damage. A minion's flat number says so
with `kind=MINION`, and its single hit point is in the database like every
other number.

Four things this file had to settle.

**A secondary attack off a primary one** is a second attack line and a
second damage line, and a row carries one of each. So the secondary's
printed bonus is trimmed by hand the way `Attack.bonus_for` trims the
header's -- the row still moves with whatever scaling the fight is on -- and
its damage is rolled with `c.damage`. The header keeps the primary, which is
what a policy forecasts from and what an edition conversion rescales.

**"Slide the target 3 squares toward the primary target"** names a direction
the slide op has no word for: a slide's destination is the decider's free
choice, which is right for "slide it 3" and would send this one anywhere.
`c.pull` anchored on the square the primary is standing in *is* "toward the
primary", and is what that sentence gets.

**"+11 vs. AC, or +12 vs. AC if the target is bloodied"** is one printed
attack line with a conditional point on it, not two lines. The header keeps
the +11 and the point goes on with `c.strike(plus=...)`, so the card still
prints the line and a policy still reads it -- unlike a two-expression
damage line, which has to give the header up.

**A solo's second initiative count** is a second slot in the order, which is
all `c.extra_turn` can say. The printed line gives it a free action at that
count rather than a whole turn, and there is no way to hand out a turn with
one action in it; nothing afterwards can tell the two slots apart either, so
the flight and the attack the line names are left to whatever the creature
does with the slot.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
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
    Bloodied,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Hit,
    Ident,
    Initiative,
    Keyword,
    Melee,
    Movement,
    Position,
    Powers,
    Ranged,
    Target,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    World,
    power,
    use,
)
from combat_engine.engine.events import Event
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import adjacent, allies, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    enemy_within,
    hits_me,
    targets_me,
)
from combat_engine.engine.types import Relation

#: The three conditions a solo's own turn shrugs off.
_MIND_HELD = (Condition.DAZED, Condition.STUNNED, Condition.DOMINATED)


def _same_row(c: Cast, who: int, ref: str) -> bool:
    """Is that creature another of this stat block? By id -- `c.is_kind`
    answers about type words, which several different blocks share."""
    ident = c.world.get(who, Ident)
    return ident is not None and ident.ref == ref


def _fly_speed(c: Cast) -> int:
    moves = c.world.get(c.me, Movement)
    return (moves.modes.get("fly") if moves else 0) or c.speed_of()


def _guarded_move(c: Cast, squares_: int) -> None:
    """Move, provoking nothing, and hand the exemption back afterwards.

    "This movement does not provoke opportunity attacks" is a duration no
    `When` names, so the exemption is taken down by hand the moment the move
    is over and a second move on the same turn provokes as it should.
    """
    guard = c.no_provoke()
    c.move(squares_)
    if guard is not None:
        c.world.effects.end(guard, "the move is over")


def _wounded_prey(c: Cast) -> int:
    """The conditional point on a "+11, or +12 if the target is bloodied"
    line. Asked of the target, which is what the printed sentence names."""
    return 1 if c.bloodied() else 0


# --------------------------------------------------------------------------
# m3103
# --------------------------------------------------------------------------


@power(
    "m3103a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 1),
)
def m3103a0(c: Cast) -> None:
    """The printed damage reads "1d81+", which is a mangled "1d8 + 1" and
    nothing else parses; no range is printed where the later rows print one,
    so this is the creature's melee attack."""
    if c.strike():
        c.hit()


@power(
    "m3103a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.FORCE, kind=LIMITED),
)
def m3103a1(c: Cast) -> None:
    """Pushed first and then knocked down, in the printed order: prone does
    not stop a push, but a creature shoved away from its friends and then
    dropped is what the sentence describes."""
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m3103a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d6", 4, dtype=DamageType.FORCE, kind=LIMITED),
)
def m3103a2(c: Cast) -> None:
    """One shot, and one or two more off whoever it lands near.

    The secondaries carry their own attack and damage lines and the header
    holds one of each, so the printed +11 is trimmed here the way
    `Attack.bonus_for` trims the header's and the force die is its own roll.
    The first secondary is compulsory where there is anybody to aim at --
    "one or two targets" -- and the second is the choice.

    The closing Effect counts **targets**, not creatures that were hit: a
    target the shot missed still makes its neighbour adjacent to another
    target, which is what the sentence says.
    """
    primary = c.target
    if primary is None:
        return
    pos = c.world.get(primary, Position)
    anchor = pos.square if pos is not None else c.here

    aimed = [primary]
    struck: list[int] = []
    if c.strike():
        c.hit()
        struck.append(primary)

    bonus = c.world.scaling.trim(11, c.level)
    pool = sorted(f for f in c.within(3, of=primary, side="enemy") if f != primary)
    for spare in (False, True):
        if not pool:
            break
        who = c.choose(pool, "another target near the first", optional=spare)
        if who is None:
            break
        pool.remove(who)
        aimed.append(who)
        if c.attack(bonus, FORT, on=who):
            c.damage("1d6", 4, dtype=DamageType.FORCE, on=who)
            c.pull(3, on=who, anchor=anchor)
            struck.append(who)

    for who in struck:
        if any(other != who and adjacent(c.world, who, other) for other in aimed):
            c.prone(on=who)


@power(
    "m3103a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.THUNDER, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.THUNDER),
)
def m3103a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m3103a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.THUNDER, Keyword.AREA],
    attack=Attack(vs=REF, printed=10),
    damage=Damage(
        "2d8", 4, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True
    ),
)
def m3103a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m3103a5",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m3103a5(c: Cast) -> None:
    """The save is against an ongoing damage effect by name, so the effect is
    picked here: `c.save` takes whichever save-ends hold comes first, and a
    daze would be shaken off in place of the burning the line names."""
    me = c.me
    c.temp_hp(6, on=me)
    for effect in c.world.effects.of(me):
        if effect.ongoing and effect.when is When.SAVE_ENDS:
            c.world.effects.save(effect)
            break
    if c.bloodied(on=me):
        c.heal(6, on=me)


# --------------------------------------------------------------------------
# m453
# --------------------------------------------------------------------------


@power(
    "m453a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 9),
)
def m453a0(c: Cast) -> None:
    if c.strike(plus=_wounded_prey(c)):
        c.hit()


@power(
    "m453a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
)
def m453a1(c: Cast) -> None:
    if c.strike(plus=_wounded_prey(c)):
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m453a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d6", 8, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m453a2(c: Cast) -> None:
    if c.strike(plus=_wounded_prey(c)):
        c.hit()
        c.ongoing(10, DamageType.PSYCHIC)


_M453_STRUCK = "an enemy within 10 squares of the m453 hits it with an attack"


@power(
    "m453a3",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    damage=Damage("1d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
    trigger=_M453_STRUCK,
    on=Trigger(Hit, when=both(hits_me, enemy_within(10)), text=_M453_STRUCK),
)
def m453a3(c: Cast) -> None:
    """No attack roll of its own: the whole of the printed Effect is damage
    to whoever just landed a blow, read off the trigger rather than left to
    the dispatcher's aim."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.hit(on=foe)


_M453_HAMMERED = "a melee attack hits the m453"


@power(
    "m453a4",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M453_HAMMERED,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_M453_HAMMERED),
)
def m453a4(c: Cast) -> None:
    """The printed line names no attacker, only the blow, so the trigger asks
    for a melee attack that landed on this creature and nothing else."""
    c.teleport(5)


# --------------------------------------------------------------------------
# m4853
# --------------------------------------------------------------------------


@power(
    "m4853a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4853a0(c: Cast) -> None:
    """Shared sight, hearing and speech, and nothing else. Declared inert
    rather than given an invented mechanic."""
    c.note("m4853a0: its master sees, hears and speaks through it")


@power(
    "m4853a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 7),
)
def m4853a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4853a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 3),
)
def m4853a3(c: Cast) -> None:
    """The printed range is 20/40; `Range` holds one number and the engine
    has no long-range penalty to apply, so the normal band is what is
    written."""
    if c.strike():
        c.hit()


@power(
    "m4853a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON, Keyword.AREA],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 3, kind=LIMITED),
)
def m4853a4(c: Cast) -> None:
    if c.strike():
        c.hit()


_M4853_OPENING = "an enemy is hit by the m4853's master"


def _my_master_hit_an_enemy(world: World, me: int, ev: Event) -> bool:
    """"An enemy is hit by the m4853's master."

    Two halves, and no ready-made predicate says either: whose blow it was
    is a `MASTER_OF` relation rather than anything on the event, and the one
    that was hit has to be an enemy of *this* creature rather than of the
    master.
    """
    held = world.relations.sources(Relation.MASTER_OF, me)
    if not held or getattr(ev, "attacker", None) != held[0]:
        return False
    who = getattr(ev, "target", None)
    return who is not None and team(world, who) is not team(world, me)


@power(
    "m4853a5",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 3),
    trigger=_M4853_OPENING,
    on=Trigger(Hit, when=_my_master_hit_an_enemy, text=_M4853_OPENING),
)
def m4853a5(c: Cast) -> None:
    """Aimed at whoever the master just hit, read off the trigger: the
    dispatcher aims a single-enemy row at the event's *attacker*, which here
    is the master and on this creature's own side."""
    foe = getattr(c.trigger, "target", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


# --------------------------------------------------------------------------
# m492
# --------------------------------------------------------------------------


@power(
    "m492a0",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
)
def m492a0(c: Cast) -> None:
    """Ending a turn in it, not entering it or starting there, so this is a
    `TurnEnd` watch rather than `c.hazard`, whose teeth bite at the other two
    moments. "While the m492 is bloodied" is asked as each turn ends rather
    than now: the aura stands the whole fight and only bites for part of
    it."""
    ring = c.aura(5, until=When.ENCOUNTER)
    me = c.me

    def arc(ev: TurnEnd) -> None:
        if ev.ghost or not c.bloodied(on=me) or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.flat(5, dtype=DamageType.LIGHTNING, on=ev.actor)

    c.watch(TurnEnd, arc, until=When.ENCOUNTER, on=me, label="m492a0")


@power(
    "m492a1",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m492a1(c: Cast) -> None:
    """Nothing holds this creature's mind for longer than its own turn."""
    me = c.me

    def clear(ev: TurnEnd) -> None:
        if ev.actor != me:
            return
        for effect in list(c.world.effects.of(me)):
            if set(effect.conditions) & set(_MIND_HELD):
                c.world.effects.end(effect, "m492a1")

    c.watch(TurnEnd, clear, until=When.ENCOUNTER, on=me, label="m492a1")


@power(
    "m492a2",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m492a2(c: Cast) -> None:
    """A solo acting twice a round: a second slot in the initiative order.

    The printed line gives it a free action at that count rather than a whole
    turn, and there is no way to hand out a turn with one action in it; what
    it does with the slot is then the policy's business, because nothing
    afterwards can tell one slot from the other.

    The last sentence is answered on the turn boundary for the same reason:
    if it cannot act for being stunned or dominated, the thing stopping it
    ends instead.
    """
    me = c.me
    init = c.world.get(me, Initiative)
    if init is not None:
        c.extra_turn(at=init.rolled + 10)

    def instead(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for effect in list(c.world.effects.of(me)):
            if set(effect.conditions) & {Condition.STUNNED, Condition.DOMINATED}:
                c.world.effects.end(effect, "m492a2")

    c.watch(TurnStart, instead, until=When.ENCOUNTER, on=me, label="m492a2")


@power(
    "m492a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("4d6", 5, dtype=DamageType.LIGHTNING),
)
def m492a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m492a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target("any", 2, label="One or two creatures"),
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5),
)
def m492a4(c: Cast) -> None:
    """One claw each, or both claws into one. How many targets the row was
    actually aimed at is what decides it, so the count is read off the target
    list rather than chosen."""
    swings = 2 if len([t for t in c.targets if t is not None]) == 1 else 1
    for _ in range(swings):
        if c.strike():
            c.hit()


@power(
    "m492a5",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.AREA],
    attack=Attack(vs=REF, printed=11),
    damage=Damage(
        "2d10", 5, dtype=DamageType.LIGHTNING, half_on_miss=True
    ),
)
def m492a5(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m492a6",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(10),
    target=Target("any", 3, label="Up to three creatures in the blast"),
    keywords=[Keyword.LIGHTNING, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage(
        "3d8", 8, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True
    ),
)
def m492a6(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


_M492_CLAWED = "an enemy hits the m492 with a melee attack"


@power(
    "m492a7",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=9),
    trigger=_M492_CLAWED,
    on=Trigger(Hit, when=both(hits_me, by_melee), text=_M492_CLAWED),
)
def m492a7(c: Cast) -> None:
    """No damage at all -- the whole of the hit is the fall. The flight is an
    Effect line, so it is taken once the burst is done and whether or not
    anybody was caught in it; a burst that finds nobody still runs the body
    once, with no target.

    Half *its* speed is half its fly speed, which is the faster of the two
    numbers on the block and the one the printed line is about.
    """
    if c.target is not None and c.strike():
        c.prone()
    if c.last:
        _guarded_move(c, max(1, _fly_speed(c) // 2))


_M492_BLED = "the m492 is first bloodied"


@power(
    "m492a8",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M492_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M492_BLED),
)
def m492a8(c: Cast) -> None:
    """"First bloodied" needs no latch of its own: `Bloodied` is announced
    once and the row is an encounter power. Recharging is giving the use back
    -- `Powers.restore` -- and the breath is then used normally, so it spends
    that use again and goes back on the die."""
    known = c.world.get(c.me, Powers)
    if known is None:
        return
    known.restore("m492a6")
    use(c.world, c.me, "m492a6")


# --------------------------------------------------------------------------
# The minions. A minion deals its printed number on a hit and its single hit
# point is in the database; `kind=MINION` is what says the number is flat
# because the creature is one, which is how it rescales.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# m314
# --------------------------------------------------------------------------


@power(
    "m314a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage(bonus=5, kind=MINION),
)
def m314a0(c: Cast) -> None:
    if c.strike():
        c.hit()


#: The four defences the huddle protects.
_M314_DEFENCES = (AC, FORT, REF, WILL)


@power(
    "m314a1",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m314a1(c: Cast) -> None:
    """Tougher shoulder to shoulder with its own kind.

    Who is standing beside it changes every time anybody moves, so this is a
    gated modifier asked as each defence is looked up rather than a bonus put
    on and taken off. The gate ignores the context entirely -- it is about
    the board, not about the attack -- and "another of these" is an `Ident`
    match, because `c.is_kind` answers about type words that several blocks
    share.
    """
    me = c.me

    def shoulder_to_shoulder(ctx: dict[str, Any]) -> bool:
        return any(
            a != me and _same_row(c, a, "m314") and adjacent(c.world, a, me)
            for a in allies(c.world, me)
        )

    for defence in _M314_DEFENCES:
        c.bonus(defence, 2, until=When.ENCOUNTER, on=me, when=shoulder_to_shoulder)
