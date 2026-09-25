"""Fighter, level 2: the utilities the later books added.

Nothing here rolls an attack. Three notes that hold for the whole file.

**A Prerequisite is not a Requirement.** "You must have training in
Athletics" is an entry condition on taking the power, not on using it, and
the engine holds no skills -- so those rows are written as the ordinary
combat powers they are. The same goes for "you must be eladrin": the engine
has no races.

**A stance's riders** are given `When.ENCOUNTER` and ended by hand from
`stance.on_end`, because a second stance-clocked effect confuses
`Effects.stance_of`. That is `p1522`'s arrangement.

**`p10484` is absent.** Its whole content is "the reach of your next melee
weapon attack increases by 1", and the `reach` modifier is read only by
`movement._threat`, which is opportunity attacks; `dsl.area_of` takes the
printed size and nothing else, so the row would extend what the fighter
threatens and not what it can hit. See `docs/blocked.json`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Dropped,
    Health,
    Keyword,
    Melee,
    MoveEnd,
    Ranged,
    Relation,
    Trigger,
    When,
    World,
    by_melee,
    power,
    spread,
    targets_me,
)
from combat_engine.engine.events import DamageApplied, ForcedMove, Hit, Miss, SurgeSpent, TurnStart
from combat_engine.engine.movement import walk
from combat_engine.engine.query import adjacent, team
from combat_engine.engine.query import squares as squares_of

from .footwork import beside_me, close_by_shift, close_by_walk
from .grips import has_shield
from .holds import grabbed_by, holds_somebody, release

MARTIAL = [Keyword.MARTIAL]

#: What holds a creature well enough that "you make an escape attempt" or
#: "a saving throw against an effect that immobilizes or restrains you" has
#: something to answer.
_STUCK = (Condition.GRABBED, Condition.RESTRAINED, Condition.IMMOBILIZED)


def _weapon_attack(ctx: dict[str, Any]) -> bool:
    """The damage context names the row, so the keyword is a registry lookup."""
    from combat_engine.engine import get

    p = get(ctx.get("power", "") or "")
    return p is not None and Keyword.WEAPON in p.keywords


def _bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _something_holds_me(world: World, eid: int) -> bool:
    """Is there anything for this row to shake off?

    Not a printed Requirement: the row has two printed choices and both need
    something to answer, and a minor action that cannot do either is not one
    the interface should be offering.
    """
    return any(
        any(card in _STUCK for card in effect.conditions)
        or any(k is Relation.GRABBED_BY and t == eid for k, _s, t in effect.relations)
        for effect in world.effects.of(eid)
    )


def _felled_this_turn(world: World, eid: int) -> bool:
    """"You must have reduced a nonminion enemy to 0 hit points this turn."

    Read back off the log, which is the only thing that remembers: `Dropped`
    names who fell and not who felled them, while `DamageApplied` carries
    both the source and the hit points left.
    """
    for ev in reversed(world.bus.log):
        if isinstance(ev, TurnStart):
            return False
        if not isinstance(ev, DamageApplied) or ev.source != eid or ev.hp > 0:
            continue
        health = world.get(ev.target, Health)
        if health is not None and health.max_hp > 1:
            return True
    return False


def _shoved_me(world: World, me: int, ev: Any) -> bool:
    """"An enemy adjacent to you forces you to move"."""
    foe = getattr(ev, "source", None)
    return (
        getattr(ev, "target", None) == me
        and foe is not None
        and foe != me
        and team(world, foe) is not team(world, me)
        and adjacent(world, me, foe)
    )


def _floored_me(world: World, me: int, ev: Any) -> bool:
    """"An enemy adjacent to you knocks you prone"."""
    return getattr(ev, "condition", None) is Condition.PRONE and _shoved_me(world, me, ev)


def _has_the_drop_on_me(world: World, me: int, ev: Any) -> bool:
    """"An enemy attacks you and has combat advantage against you"."""
    return getattr(ev, "target", None) == me and bool(getattr(ev, "advantage", False))


def _missed_me_in_melee(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and by_melee(world, me, ev)


def _closed_on_me(world: World, me: int, ev: Any) -> bool:
    """"An enemy ends its move in a square adjacent to you"."""
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    return adjacent(world, me, who)


def _my_mark_fell(world: World, me: int, ev: Any) -> bool:
    """"An adjacent enemy marked by you drops to 0 hit points."

    `query.enemies` leaves the dead out, so the side is read off `team`
    directly -- the creature this fires for is by definition down.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is team(world, me):
        return False
    return world.relations.holds(Relation.MARKED_BY, me, who) and adjacent(world, me, who)


_KNOCKED_ABOUT = "an enemy next to you knocks you prone or shoves you"
_WITH_THE_DROP = "an enemy attacks you and has combat advantage against you"
_MISSED_IN_MELEE = "an enemy misses you with a melee attack"
_CAME_ALONGSIDE = "an enemy ends its move next to you"
_I_AM_HIT = "you are hit by an attack"
_MY_MARK_FELL = "an enemy next to you that you marked drops"


# -- stances and standing arrangements --------------------------------------


@power(
    "p10333",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10333(c: Cast) -> None:
    """Reckless: the damage is bought with the fighter's own armour.

    "This stance ends when you spend a healing surge" is a second ending on
    top of the stance clock, so it is a watcher on `SurgeSpent` rather than
    a duration.
    """
    me = c.me
    step = 6 if c.level >= 21 else 4 if c.level >= 11 else 2
    stance = c.stance(label=c.ref)

    def drop(ev: SurgeSpent) -> None:
        if ev.actor == me:
            c.world.effects.end(stance, "a surge was spent")

    riders = [
        c.bonus("damage", step, on=me, until=When.ENCOUNTER, when=_weapon_attack),
        c.penalty(AC, 2, on=me, until=When.ENCOUNTER),
        c.watch(SurgeSpent, drop, until=When.ENCOUNTER, on=me, label=c.ref),
    ]
    for rider in riders:
        if rider is not None:
            stance.on_end.append(lambda r=rider: c.world.effects.end(r, "stance ended"))


@power(
    "p4318",
    level=2,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p4318(c: Cast) -> None:
    """Rooted and armoured, with a step bought off every miss."""
    me = c.me
    stance = c.stance(conditions=[Condition.SLOWED], label=c.ref)

    def sidestep(ev: Miss) -> None:
        if ev.target == me and by_melee(c.world, me, ev) and c.may("sidestep", who=me):
            c.shift(1)

    riders = [
        c.bonus(AC, 2, on=me, until=When.ENCOUNTER),
        c.watch(Miss, sidestep, until=When.ENCOUNTER, on=me, label=c.ref),
    ]
    for rider in riders:
        if rider is not None:
            stance.on_end.append(lambda r=rider: c.world.effects.end(r, "stance ended"))


# -- minor actions ----------------------------------------------------------


@power(
    "p10485",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p10485(c: Cast) -> None:
    """Jumping, a running start and a softer landing: all three are skill
    checks and the engine rolls none of them."""


@power(
    "p10486",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_something_holds_me,
    requires_text="needs to be held by something",
)
def p10486(c: Cast) -> None:
    """Two printed choices, and the grab half is the one with no action
    behind it: a grab is a relation held up by an effect and ending the
    effect is the escape, which is `rogue/level_1_b.py`'s reading."""
    me = c.me
    grabs = [
        e
        for e in c.world.effects.of(me)
        if any(k is Relation.GRABBED_BY and t == me for k, _s, t in e.relations)
    ]
    stuck = [
        e
        for e in c.world.effects.of(me)
        if e.when is When.SAVE_ENDS
        and any(card in (Condition.IMMOBILIZED, Condition.RESTRAINED) for card in e.conditions)
    ]
    if grabs and (not stuck or c.may("wriggle free instead", who=me)):
        for effect in grabs:
            c.world.effects.end(effect, c.ref)
        for grabber in c.world.relations.sources(Relation.GRABBED_BY, me):
            c.world.relations.clear(Relation.GRABBED_BY, grabber, me, c.ref)
    elif stuck:
        c.world.effects.save(stuck[0])


@power(
    "p12192",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=MARTIAL,
    requires=has_shield,
    requires_text="needs a shield",
)
def p12192(c: Cast) -> None:
    c.push(3)
    near = sorted(c.within(1, side="enemy"))
    if near and c.may("call one out", who=c.me):
        c.mark(on=c.choose(near, "who is called out"))


@power(
    "p12670",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=MARTIAL,
)
def p12670(c: Cast) -> None:
    """Swinging at anybody else costs five, which the attack context can say
    because it names who is being swung at."""
    me = c.me
    c.penalty("attack", 5, until=When.EONT, when=lambda ctx: ctx.get("target") != me)


@power(
    "p12671",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_bloodied,
    requires_text="must be bloodied",
)
def p12671(c: Cast) -> None:
    c.temp_hp(15 if c.level >= 21 else 10 if c.level >= 11 else 5, on=c.me)


@power(
    "p12695",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.FEAR],
)
def p12695(c: Cast) -> None:
    c.grants_advantage(to=c.me, until=When.EONT)


@power(
    "p2012",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=has_shield,
    requires_text="needs a shield",
)
def p2012(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.EONT)
    c.bonus(REF, 2, on=c.me, until=When.EONT)
    c.cannot_be_flanked(on=c.me, until=When.EONT)


@power(
    "p4317",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL,
)
def p4317(c: Cast) -> None:
    """The mark is bought with a free swing at the fighter, and an ally gets
    clear while the enemy is busy taking it."""
    victim = c.target
    if victim is None:
        return
    c.mark(until=When.EONT)
    c.grant_attack(victim, on=c.me, attack_bonus=-2)
    friends = [a for a in c.within(1, of=victim, side="ally") if a != c.me]
    if friends:
        who = c.choose(sorted(friends), "who gets clear")
        c.shift(c.speed_of(who), who=who)


# -- move actions -----------------------------------------------------------


@power(
    "p10483",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=holds_somebody,
    requires_text="needs a creature grabbed",
)
def p10483(c: Cast) -> None:
    """Dragging what you are holding. The slide is aimed rather than handed
    to the mover's decider, which would be free to leave it behind."""
    held = grabbed_by(c)
    if not held:
        return
    who = c.choose(held, "who is dragged")
    if who is None:
        return
    c.no_provoke(from_=who, until=When.EOT)
    walked = c.move(c.speed_of())
    where = beside_me(c, who)
    if walked and where is not None:
        c.slide(walked, on=who, to=where)
    if c.may("let go and put it down hard", who=c.me):
        release(c, who)
        c.prone(on=who)


@power(
    "p12669",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(2),
    target=EACH_ALLY,
    keywords=MARTIAL,
)
def p12669(c: Cast) -> None:
    if c.target != c.me:
        c.shift(1, who=c.target)


@power(
    "p12672",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12672(c: Cast) -> None:
    close_by_shift(c, 3)


@power(
    "p12696",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p12696(c: Cast) -> None:
    close_by_walk(c, max(0, c.dex_mod))


@power(
    "p13775",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(3),
    target=ONE_ALLY,
    keywords=[Keyword.MARTIAL, Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p13775(c: Cast) -> None:
    """"You and one ally in the burst" is one choice: the other end of a
    swap is the caster, so the header names the ally and `c.swap` supplies
    the pair."""
    if c.target is not None and c.target != c.me:
        c.swap(c.target)


@power(
    "p2116",
    level=2,
    cls="fighter",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p2116(c: Cast) -> None:
    """"As long as you end adjacent to that enemy" cannot be judged after
    the fact -- the opportunity window has already opened and closed by
    then -- so the destination is chosen from the squares that satisfy it
    and the exemption is granted for a move that will."""
    near = sorted(c.within(1, side="enemy"))
    foe = c.choose(near, "who you keep your eye on") if near else None
    if foe is None:
        c.move(c.speed_of())
        return
    paths = c.world.reachable_paths(c.me, c.speed_of())
    beside = spread(squares_of(c.world, foe), 1)
    options = sorted(sq for sq in paths if sq in beside)
    where = c.choose(options, "where to end up") if options else None
    if where is None:
        c.move(c.speed_of())
        return
    c.no_provoke(from_=foe, until=When.EOT)
    walk(c.world, c.me, paths[where])


@power(
    "p9994",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_felled_this_turn,
    requires_text="must have dropped a real enemy this turn",
)
def p9994(c: Cast) -> None:
    """The bonus is how far the fighter got, so the squares are counted
    rather than assumed: a shift that is refused buys nothing."""
    from_ = c.here
    if not close_by_shift(c, c.speed_of()) or from_ is None or c.here is None:
        return
    gone = abs(c.here[0] - from_[0]) + abs(c.here[1] - from_[1])
    if gone:
        c.bonus("damage", gone, on=c.me, until=When.EONT, once=True)


# -- answering something ----------------------------------------------------


@power(
    "p1122",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_WITH_THE_DROP,
    on=Trigger(AttackRolled, _has_the_drop_on_me, _WITH_THE_DROP),
)
def p1122(c: Cast) -> None:
    """Declared on the roll rather than on the declaration, which is the one
    window where the advantage is known *and* still undone: `resolve.attack`
    re-reads the defence and recomputes the outcome from `result` once this
    closes, so taking the +2 back off the total and clearing the flag is the
    whole of "you don't grant combat advantage for the attack".
    """
    ev = c.trigger
    result = getattr(ev, "result", None)
    if result is None or not result.advantage:
        return
    result.total -= 2
    result.advantage = False
    ev.advantage = False
    c.note(f"{c.ref}: the opening closed")


@power(
    "p10487",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger=_KNOCKED_ABOUT,
    on=(
        Trigger(ForcedMove, _shoved_me, "an enemy next to you shoves you"),
        Trigger(ConditionApplied, _floored_me, "an enemy next to you knocks you prone"),
    ),
)
def p10487(c: Cast) -> None:
    """Two printed triggers with a different answer each, so both are
    declared and the body asks which one happened. `ConditionApplied` names
    its subject `target`, so `about_me` would be false forever here.
    """
    ev = c.trigger
    foe = getattr(ev, "source", None)
    if foe is None:
        return
    if isinstance(ev, ConditionApplied):
        c.prone(on=foe)
        return
    where = beside_me(c, foe)
    if where is not None:
        c.pull(10, on=foe, to=where)


@power(
    "p12693",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger=_MISSED_IN_MELEE,
    on=Trigger(Miss, _missed_me_in_melee, _MISSED_IN_MELEE),
)
def p12693(c: Cast) -> None:
    """"One creature other than the triggering enemy" is not whoever swung,
    which is what the dispatcher would aim this at -- so the row takes no
    target in the header and picks one here."""
    swung = getattr(c.trigger, "attacker", None)
    pool = sorted(e for e in c.within(1, side="enemy") if e != swung)
    who = c.choose(pool, "who catches the elbow") if pool else None
    if who is not None:
        c.flat(3 + c.dex_mod, on=who)


@power(
    "p12847",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_CAME_ALONGSIDE,
    on=Trigger(MoveEnd, _closed_on_me, _CAME_ALONGSIDE),
)
def p12847(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    close_by_shift(c, 3)
    c.bonus(
        "attack", 2, on=c.me, until=When.EONT, once=True,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power(
    "p4319",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_I_AM_HIT,
    on=Trigger(Hit, targets_me, _I_AM_HIT),
)
def p4319(c: Cast) -> None:
    c.shift(max(1, c.wis_mod))


@power(
    "p7387",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_MY_MARK_FELL,
    on=Trigger(Dropped, _my_mark_fell, _MY_MARK_FELL),
)
def p7387(c: Cast) -> None:
    """Which enemies are adjacent is asked where the fighter ends up, not
    where it started."""
    c.move(max(0, c.dex_mod))
    near = sorted(c.within(1, side="enemy"))
    if near:
        c.mark(on=c.choose(near, "who is called out next"), until=When.EONT)
