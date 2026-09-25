"""Warlord, level 1, the rows printed after the first book.

`level_1.py` holds the ones that came first; these are the rest.

Three notes apply across the batch.

**Somebody else swings.** More than half of these are a granted attack, and
`c.grant_attack` (the swing alone), `c.charge_at(..., who=)` (the run and
the charge flag) and `c.run_at(..., who=)` (the run alone) are the three
shapes the printed lines take. `level_1.py`'s docstring predates all three.

**"Intelligence modifier or Wisdom modifier"** is the player's pick, so it
is read as the better of the two.

**The presences.** Several rows carry a rider keyed to a build -- an
insightful one, a skirmishing one -- and `chargen` knows two warlord builds,
`inspiring` and `tactical`. A rider belonging to neither has no fork to read,
so those rows are the printed base line only.

Six rows print "Ranged weapon" and the warlord's chassis carries a longsword
and nothing to fire, so `can_branch` refuses them on the audit board. They
are written for the warlord who owns a crossbow.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBurst,
    Event,
    Forced,
    Gear,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Square,
    Trigger,
    When,
    Window,
    World,
    power,
    spread,
)
from combat_engine.engine.events import ForcedMove, Healed
from combat_engine.engine.movement import forced_squares
from combat_engine.engine.query import (
    adjacent,
    distance_between,
    has_combat_advantage,
    team,
)

from .level_1 import _beside

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

_ALLY_HIT = "an ally within 5 squares of you is hit by an enemy"
_HIT_BY_ENEMY = "an enemy hits you"


def _int_or_wis(c: Cast) -> int:
    """"Intelligence modifier or Wisdom modifier" -- whichever is better."""
    return max(c.int_mod, c.wis_mod)


def _friends_within(c: Cast, squares: int) -> list[int]:
    """Allies in range -- "an ally", so never the warlord itself."""
    return sorted(a for a in c.within(squares, side="ally") if a != c.me)


def _visible_friends(c: Cast) -> list[int]:
    return sorted(a for a in c.allies() if c.can_see(a))


def _one_w(c: Cast, who: int) -> int:
    """One roll of *that* creature's weapon dice.

    `c.w` only ever reads the caster's hands, and "the attack deals 1[W]
    extra damage" is added to somebody else's swing.
    """
    gear = c.world.get(who, Gear)
    weapon = gear.main if gear else None
    return c.roll(weapon.damage if weapon else "1d4")


def _used_this_turn(c: Cast, ref: str) -> bool:
    """Has the caster used that row since its turn began?

    `use` stamps a `PowerUsed`, so the log can answer it; the search stops
    at this turn's `TurnStart` rather than finding last round's.
    """
    for e in reversed(c.world.bus.log):
        if e.kind == "TurnStart" and getattr(e, "actor", None) == c.me:
            return False
        if (
            e.kind == "PowerUsed"
            and getattr(e, "actor", None) == c.me
            and getattr(e, "power", "") == ref
        ):
            return True
    return False


def _has_shield(world: World, eid: int) -> bool:
    """"Requirement: You must be using a shield"."""
    gear = world.get(eid, Gear)
    return bool(gear and gear.shield)


def _ally_hit_within(radius: int) -> Callable[[World, int, Event], bool]:
    """An ally of mine, within range, is about to be hit by an enemy.

    Declared on the roll rather than on the `Hit`: `resolve.attack` reads
    the defence again once the interrupt window closes, which is the only
    beat at which raising it can turn the blow into a miss.
    """

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "target", None)
        attacker = getattr(ev, "attacker", None)
        result = getattr(ev, "result", None)
        if who is None or who == me or attacker is None:
            return False
        if not (result and result.hit):
            return False
        if team(world, who) is not team(world, me):
            return False
        if team(world, attacker) is team(world, me):
            return False
        return distance_between(world, me, who) <= radius

    return check


def _enemy_hits_me(world: World, me: int, ev: Event) -> bool:
    attacker = getattr(ev, "attacker", None)
    if getattr(ev, "target", None) != me or attacker is None:
        return False
    return team(world, attacker) is not team(world, me)


def _safe_square(c: Cast, who: int) -> Square | None:
    """A square this creature could be slid to that no enemy stands beside."""
    for sq in forced_squares(c.world, who, c.here, Forced.SLIDE):
        if not c.in_squares(spread({sq}, 1), side="enemy"):
            return sq
    return None


# -- at-will ---------------------------------------------------------------


@power(
    "p10888",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p10888(c: Cast) -> None:
    """The whole row is the ally's swing: no attack of the warlord's own.

    `c.grant_attack` with no `ref` rolls whatever that creature's own basic
    attack is, which is the printed "a basic attack" and not always a melee
    one.
    """
    foes = sorted(f for f in c.within(10, side="enemy") if c.can_see(f))
    victim = c.choose(foes, "who that ally attacks")
    if victim is not None:
        c.grant_attack(c.target, on=victim)


@power(
    "p10889",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=WILL),
)
def p10889(c: Cast) -> None:
    """"The next ally" is one grant in total, so the bonus is handed out
    when a qualifying swing is announced rather than held on every ally --
    an effect per ally would be a bonus each.

    `AttackDeclared` is emitted with the roll as its resolution, so a
    modifier applied in the `BEFORE` window is read by that very roll.
    """
    if not c.strike():
        return
    c.damage(c.w(1))
    foe = c.target
    squad = set(c.allies())

    def hand_it_over(ev: AttackDeclared) -> None:
        if ev.target != foe or ev.attacker not in squad:
            return
        if not has_combat_advantage(c.world, ev.attacker, foe):
            return
        c.bonus("attack", 2, on=ev.attacker, until=When.EOT, once=True)

    c.watch(
        AttackDeclared,
        hand_it_over,
        until=When.SONT,
        window=Window.BEFORE,
        once=True,
        label=c.ref,
    )


@power(
    "p10890",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
)
def p10890(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(1))
    foe = c.target
    value = _int_or_wis(c)

    def at_it(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == foe

    for friend in c.allies():
        c.bonus("damage", value, on=friend, until=When.SONT, when=at_it)


@power(
    "p10891",
    level=1,
    cls="warlord",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
)
def p10891(c: Cast) -> None:
    """The Effect is the warlord giving *everybody* an opening, and the
    relation names one beneficiary, so it is granted once per enemy.
    """
    if c.strike():
        c.damage(c.w(1), c.str_mod + _int_or_wis(c))
    for foe in c.enemies():
        c.grants_advantage(on=c.me, to=foe, until=When.SONT)


# -- encounter --------------------------------------------------------------


@power(
    "p10119",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10119(c: Cast) -> None:
    """The Special line is read off the log -- `p1590` stamps a `PowerUsed`
    when it is used, and the search stops where this turn began.

    The Effect names its destination ("a square adjacent to no enemies"),
    so the legal steps are filtered rather than left to the decider, which
    would slide the ally straight back into reach.

    Both clauses draw from the pool as it stands before either happens: the
    ally who takes the free shift is usually no longer adjacent to anybody
    afterwards, and asking again left the Effect with nobody to move.
    """
    pool = _beside(c, c.target)
    if c.strike(plus=2 if _used_this_turn(c, "p1590") else 0):
        c.damage(c.w(1), c.str_mod)
        stepper = c.choose(pool, "who shifts a square")
        if stepper is not None:
            c.shift(1, who=stepper)
    friend = c.choose(pool, "who you slide out of trouble")
    if friend is not None:
        c.slide(1, on=friend, to=_safe_square(c, friend))


@power(
    "p10120",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p10120(c: Cast) -> None:
    """The extra 1[W] is the ally's weapon, not the warlord's, and it is a
    one-shot untyped addition rather than a power bonus -- two power bonuses
    to damage would not add.
    """
    friend = c.target
    foes = sorted(c.within(c.speed_of(friend) + 1, of=friend, side="enemy"))
    victim = c.choose(foes, "who that ally charges")
    if victim is None:
        return
    extra = _one_w(c, friend)
    if extra:
        c.bonus(
            "damage", extra, on=friend, until=When.EOT, kind="untyped", once=True
        )
    c.charge_at(victim, who=friend)


@power(
    "p10892",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
)
def p10892(c: Cast) -> None:
    """"Ranged attack rolls" is a gate on the attack context, which carries
    `ranged`; the damage context does not, but this is not a damage line.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    value = _int_or_wis(c)

    def shot_at_it(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == foe and bool(ctx.get("ranged"))

    for who in (c.me, *c.allies()):
        c.bonus("attack", value, on=who, until=When.EONT, when=shot_at_it)


@power(
    "p10893",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=MARTIAL,
    trigger=_ALLY_HIT,
    on=Trigger(AttackRolled, _ally_hit_within(5), _ALLY_HIT),
)
def p10893(c: Cast) -> None:
    """The defence bonus is one-shot: it is spent on the blow it was raised
    against, which is what "against the attack" means and what the printed
    line exists for.
    """
    friend = getattr(c.trigger, "target", None) or c.target
    attacker = getattr(c.trigger, "attacker", None)
    if friend is None:
        return
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=friend, until=When.EOT, once=True)
    if attacker is not None:
        c.grant_attack(friend, on=attacker)


@power(
    "p10894",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
)
def p10894(c: Cast) -> None:
    """"Charge the target **or** make a melee basic attack against it": the
    ally already standing beside it cannot charge, and the one further off
    has to run, so the choice makes itself.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    foe = c.target
    friend = c.choose(_visible_friends(c), "who swings at it")
    if friend is None:
        return
    if c.adjacent_to(foe, friend):
        c.grant_attack(friend, on=foe)
    else:
        c.charge_at(foe, who=friend)


@power(
    "p10895",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10895(c: Cast) -> None:
    """The damage context carries no attacker and does not need one -- the
    modifier hangs on each attacker. "While **you** have combat advantage"
    is the warlord's own, so it is asked of the board when the blow lands
    rather than settled now.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe, me = c.target, c.me

    def while_i_have_it(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == foe and has_combat_advantage(c.world, me, foe)

    for who in (c.me, *c.allies()):
        c.bonus(
            "damage", c.cha_mod, on=who, until=When.EONT, when=while_i_have_it
        )


@power(
    "p10900",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_has_shield,
    requires_text="needs a shield",
)
def p10900(c: Cast) -> None:
    """The Effect lands hit or miss. "While adjacent to you" is asked of the
    board each time the ally's defence is read, not fixed now.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    me = c.me
    c.bonus(AC, 2, on=me, until=When.EONT)
    for friend in c.allies():

        def beside_me(ctx: dict[str, Any], who: int = friend) -> bool:
            return adjacent(c.world, me, who)

        c.bonus(AC, 2, on=friend, until=When.EONT, when=beside_me)


@power(
    "p10901",
    level=1,
    cls="warlord",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_HIT_BY_ENEMY,
    on=Trigger(Hit, _enemy_hits_me, _HIT_BY_ENEMY),
)
def p10901(c: Cast) -> None:
    """"Move his or her speed and make a melee basic attack" is a charge's
    move without the charge -- no bonus, no flag -- so it is `c.run_at` and
    then `c.grant_attack` rather than `c.charge_at`.
    """
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None:
        return
    c.basic(on=attacker)
    friend = c.choose(_friends_within(c, 5), "who runs in and swings")
    if friend is None:
        return
    c.run_at(attacker, who=friend)
    c.grant_attack(friend, on=attacker)


# -- daily ------------------------------------------------------------------


@power(
    "p10121",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=WILL),
)
def p10121(c: Cast) -> None:
    """No damage of its own: the pull is what the warlord does and the rest
    is up to three friends arriving. "One, two, or three" is a real choice,
    so each is offered with a decline.
    """
    if not c.strike():
        return
    foe = c.target
    c.pull(5, on=foe)
    pool = [a for a in _friends_within(c, 5) if c.can_see(a)]
    for _ in range(3):
        friend = c.choose(pool, "who charges it", optional=True)
        if friend is None:
            return
        pool.remove(friend)
        c.charge_at(foe, who=friend)


@power(
    "p10902",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10902(c: Cast) -> None:
    """The arrangement is armed after the opening shove, so the push in the
    same sentence does not set it off, and a latch keeps a granted swing
    that shoves again from becoming a chain.

    `ForcedMove` is negotiated before the creature steps, which is the same
    beat an opportunity action would interrupt it at.
    """
    foe = c.target
    if not c.strike():
        c.half_damage(c.w(2), c.str_mod)
        c.push(1, on=foe)
        return
    c.damage(c.w(2), c.str_mod)
    if c.int_mod > 0:
        c.push(c.int_mod, on=foe)
    busy: list[bool] = []

    def counter(ev: ForcedMove) -> None:
        if ev.target != foe or busy:
            return
        beside = sorted(a for a in c.within(1, of=foe, side="ally") if a != c.me)
        friend = c.choose(beside or _friends_within(c, 10), "who takes the opening")
        if friend is None:
            return
        busy.append(True)
        try:
            c.grant_attack(friend, on=foe)
        finally:
            busy.clear()

    c.watch(ForcedMove, counter, until=When.SAVE_ENDS, on=foe, label=c.ref)


@power(
    "p10903",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10903(c: Cast) -> None:
    """Hit and miss differ only in how long the legs last."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        until = When.ENCOUNTER
    else:
        c.half_damage(c.w(2), c.str_mod)
        until = When.EONT
    for who in (c.me, *_visible_friends(c)):
        c.bonus("speed", 1, on=who, until=until)


@power(
    "p10913",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_RANGED, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p10913(c: Cast) -> None:
    """"Your healing powers restore additional hit points" is the seam
    `Healed` was made negotiable for: the amount is announced before the hit
    points go on and read back afterwards.
    """
    if not c.strike():
        return
    c.damage(c.w(3), c.str_mod)
    me, extra = c.me, _int_or_wis(c)

    def more(ev: Healed) -> None:
        if ev.source == me:
            ev.amount += extra

    c.watch(Healed, more, until=When.ENCOUNTER, window=Window.BEFORE, label=c.ref)


@power(
    "p10914",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p10914(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    friend = c.choose(_visible_friends(c), "who takes a free swing")
    if friend is not None:
        c.grant_attack(friend, on=c.target, attack_bonus=2)


@power(
    "p10915",
    level=1,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_RANGED, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p10915(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(3), c.str_mod)
    foe = c.target
    value = _int_or_wis(c)

    def at_it(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == foe

    for friend in c.allies():
        c.bonus("damage", value, on=friend, until=When.ENCOUNTER, when=at_it)
