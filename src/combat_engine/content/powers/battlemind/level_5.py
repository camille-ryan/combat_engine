"""Battlemind, level 5."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CON,
    DAILY,
    EACH_ENEMY,
    ONE_CREATURE,
    REACTION,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    Window,
    power,
    targets_me,
)
from combat_engine.engine.events import MoveStart

from . import shift_beside


@power(
    "p11165",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.POLYMORPH],
    attack=Attack(CON, vs=AC),
)
def p11165(c: Cast) -> None:
    """The aspect holds nothing of its own -- resist 5 and the Wisdom rider
    are the Augment 1 clause, dropped for want of power points."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.prone()
    else:
        c.half_damage(c.w(), c.con_mod)
    if c.first:
        c.effect("aspect", until=When.ENCOUNTER, on=c.me)


@power(
    "p11166",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(CON, vs=WILL),
)
def p11166(c: Cast) -> None:
    """"The target's reach is reduced by 1" is dropped: `c.threatens` sets how
    far a creature threatens, not how far it can swing. The slide is the other
    half of the same save-ends hold, so one save clears both."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.con_mod)
    else:
        c.half_damage(c.w(2), c.con_mod)

    def nudge(ev: Hit) -> None:
        if ev.target == victim and c.may("slide it", who=c.me):
            c.slide(1, on=victim)

    c.watch(Hit, nudge, until=When.SAVE_ENDS, on=victim)


@power(
    "p12423",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FORCE, Keyword.STANCE],
    attack=Attack(CON, vs=AC),
)
def p12423(c: Cast) -> None:
    """The stance's move-action power shares this id and cannot be a second
    `@power`; a speed + 1d4 move that sometimes ignores opportunity attacks is
    also not a thing `Cast` can grant, so it is dropped."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.con_mod, dtype=DamageType.FORCE)
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.con_mod, dtype=DamageType.FORCE)
        c.slowed(until=When.EONT)
    if c.last:
        if victim is not None:
            shift_beside(c, max(1, c.speed_of() // 2), victim)
        c.stance()


@power(
    "p13043",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC, Keyword.POLYMORPH],
    attack=Attack(CON, vs=WILL),
)
def p13043(c: Cast) -> None:
    """The aspect's Intimidate bonus is not a combat effect and its
    augmentation is the Augment 1 clause, so the hold carries nothing."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.damage("1d12", dtype=DamageType.PSYCHIC)
    else:
        c.half_damage(c.w(), c.con_mod)
        c.half_damage("1d12", dtype=DamageType.PSYCHIC)
    if c.first:
        c.effect("aspect", until=When.ENCOUNTER, on=c.me)


@power(
    "p13044",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.PSYCHIC],
    attack=Attack(CON, vs=WILL),
    trigger="you take damage from an attack",
    on=Trigger(DamageApplied, targets_me, "you take damage from an attack"),
)
def p13044(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.con_mod, dtype=DamageType.PSYCHIC)
        c.push(3)
    else:
        c.half_damage(c.w(), c.con_mod, dtype=DamageType.PSYCHIC)
        c.push(1)
    if c.first:
        c.temp_hp(c.level // 2 + c.con_mod, on=c.me)


@power(
    "p13045",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=AC),
)
def p13045(c: Cast) -> None:
    """The header's attack line is the *secondary* one; the primary target is
    only swapped with. `c.swap` is the named method for changing places, so
    the teleport keyword rides on a walk rather than a blink."""
    primary = c.target
    if primary is None:
        return
    c.swap(primary)
    reachable = c.within(1, side="enemy")
    victim = c.choose(reachable, "who you swing at") if reachable else None
    if victim is None:
        return
    if c.strike(on=victim):
        c.damage(c.w(3), c.con_mod, on=victim)
    else:
        c.half_damage(c.w(3), c.con_mod, on=victim)
    c.mark(on=victim, until=When.EONT)


@power(
    "p13046",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION, Keyword.STANCE],
    attack=Attack(CON, vs=AC),
)
def p13046(c: Cast) -> None:
    """The stance's free-action teleport is a power in its own right sharing
    this id, so it is dropped: `c.grant_row` needs a ref to grant."""
    if c.strike():
        c.damage(c.w(2), c.con_mod)
    else:
        c.half_damage(c.w(2), c.con_mod)
    if c.first:
        c.stance()


@power(
    "p2629",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.STANCE],
    attack=Attack(CON, vs=AC),
)
def p2629(c: Cast) -> None:
    """The stance's opportunity attack shares this id and is folded in as a
    subscription hung on the stance. `MoveStart.kind_` separates a walk from a
    shift, and it is the right end of the move: by `MoveEnd` the enemy has
    already left and the adjacency check would be false."""
    if c.strike():
        c.damage(c.w(2), c.con_mod)
    else:
        c.half_damage(c.w(2), c.con_mod)
    if not c.last:
        return
    held = c.stance()

    def riposte(ev: MoveStart) -> None:
        who = ev.actor
        if ev.kind_ != "walk" or c.turn_of() != who:
            return
        if not c.adjacent(who) or not c.marked(on=who):
            return
        if not c.strike(on=who):
            return
        c.damage(c.w(), c.con_mod, on=who)

        def reel(end: TurnEnd) -> None:
            if end.actor == who and c.may("pull it back", who=c.me):
                c.pull(c.speed_of(who), on=who)

        c.watch(TurnEnd, reel, until=When.EOTNT, on=c.me)

    held.subs.append(
        c.world.bus.on(MoveStart, riposte, owner=c.me, window=Window.BEFORE)
    )


@power(
    "p2631",
    level=5,
    cls="battlemind",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(CON, vs=AC),
)
def p2631(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.slide(1)
    else:
        c.half_damage(c.w(), c.con_mod)
    if not c.first:
        return

    def tug(ev: TurnStart) -> None:
        near = ev.actor in c.enemies() and c.distance(ev.actor) <= 3
        if near and c.may("slide it", who=c.me):
            c.slide(1, on=ev.actor)

    c.watch(TurnStart, tug, until=When.ENCOUNTER, on=c.me)
