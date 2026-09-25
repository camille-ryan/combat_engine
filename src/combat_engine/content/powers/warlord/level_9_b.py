"""Warlord, level 9: the daily attacks printed outside the first book.

Nine of these fifteen end by handing somebody else a swing, so `c.grant_attack`
and `c.charge_at` carry the file. Where the printed line is *charge*,
`c.charge_at(victim, who=friend)` is the one to reach for: it walks the ally
in and flags the swing, which `c.grant_attack` alone does not.

`p11614`'s second half is a row with no id of its own, so it is written out
inside the first: a granted swing is that creature's own basic attack, 1[W]
where the printed line is 2[W], and the missing die is read off the ally's
own weapon and handed over as a damage bonus -- the reading `p2328` settled.

Two durations have no spelling. `p6008`'s hold runs "until it starts its
turn outside your melee reach", which is kept for the encounter with a
start-of-turn watcher that ends it the moment the printed condition is met.
`p10949`'s "cannot make opportunity attacks" is a veto on the window rather
than a bar on attacking -- `c.cannot_attack` would take its turn away too.

Written down rather than approximated: "cannot recharge its powers" and
"cannot spend action points" on `p2593`.

Five rows the audit board cannot reach, each driven by hand instead.
`p10946`, `p4571` and `p6008` print a Requirement -- a ranged weapon, a
heavy thrown one, a reach one -- that a longsword does not meet. `p10130`
triggers on being bloodied, and the board starts its caster bloodied, so the
threshold is never crossed again. `p4572` needs somebody to have spent an
encounter attack power, and neither the caster nor the board's one ally
carries any.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    RANGED,
    REACTION,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Effect,
    Event,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    Relation,
    Trigger,
    UpTo,
    Usage,
    When,
    Window,
    World,
    about_me,
    by_melee,
    distance,
    power,
    spread,
)
from combat_engine.engine.components import Powers
from combat_engine.engine.dsl import get, use
from combat_engine.engine.events import Bloodied, Hit, Miss, MoveEnd, OpportunityWindow, TurnStart
from combat_engine.engine.movement import walk
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.query import squares as squares_of

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

#: The warlord's own class feature, whose uses `p10947` counts.
INSPIRING_WORD = "p1590"

_ENEMY_CLOSES = "an enemy enters a square within 3 squares of you"
_YOU_ARE_BLOODIED = "you are bloodied by an attack"


def _friends_within(c: Cast, radius: int) -> list[int]:
    """`side="ally"` counts the caster and every printed line here says
    "an ally", so the caster comes back out."""
    return sorted(a for a in c.within(radius, side="ally") if a != c.me)


def _mine(c: Cast, who: int | None) -> bool:
    """On my side and not me -- what "an ally" means inside a watcher."""
    return who is not None and who != c.me and team(c.world, who) is team(c.world, c.me)


def _their_w(c: Cast, who: int, count: int = 1) -> str:
    """`count`[W] of somebody else's weapon. `c.w` only ever reads yours."""
    gear = c.world.get(who, Gear)
    weapon = gear.main if gear else None
    if weapon is None:
        return f"{count}d4"
    return f"{count}d{weapon.damage.split('d')[-1]}"


def _granted_hits(c: Cast, friend: int, victim: int, damage_bonus: int = 0) -> list[int]:
    """Hand somebody a swing and say who it actually connected with.

    `c.grant_attack` reports that a row went off, not that it landed, and
    three printed riders here pay out only on the hit.
    """
    landed: list[int] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == friend:
            landed.append(ev.target)

    sub = c.world.bus.on(Hit, tally)
    try:
        c.grant_attack(friend, on=victim, damage_bonus=damage_bonus)
    finally:
        c.world.bus.off(sub)
    return landed


def _enemy_closes(radius: int) -> Any:
    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "actor", None)
        if who is None or who == me or team(world, who) is team(world, me):
            return False
        return distance_between(world, me, who) <= radius

    return check


def _heavy_thrown(world: World, eid: int) -> bool:
    """"A heavy thrown weapon."

    No weapon in the model carries a thrown flag -- what a thrown one has is
    a `ranged` band on something you also swing -- and "heavy" is the
    not-a-light-blade half. The same reading `warlord/level_1_c.py` settled.
    """
    gear = world.get(eid, Gear)
    weapon = gear.main if gear else None
    return bool(weapon and weapon.ranged and not weapon.is_light_blade)


def _reach_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    weapon = gear.main if gear else None
    return weapon is not None and "reach" in weapon.properties


# -- the rows ---------------------------------------------------------------


@power(
    "p10130",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(5),
    target=ONE_OTHER_ALLY,
    keywords=MARTIAL,
    trigger=_YOU_ARE_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_YOU_ARE_BLOODIED),
)
def p10130(c: Cast) -> None:
    """One square per enemy actually hit, and the retreat has to finish
    nearer the warlord -- which the decider knows nothing about, so the
    square is chosen here rather than offered."""
    friend = c.target
    if friend is None:
        return
    struck = 0
    for foe in sorted(c.within(1, of=friend, side="enemy")):
        struck += len(_granted_hits(c, friend, foe))
    if struck:
        _draw_in(c, friend, struck)


def _draw_in(c: Cast, friend: int, squares_: int) -> None:
    """"Must end this movement closer to you"."""
    here = c.here
    if here is None:
        return
    was = c.distance(friend)
    options = [sq for sq in c.world.reachable_squares(friend, squares_) if distance(sq, here) < was]
    if options:
        c.shift(squares_, who=friend, to=min(options, key=lambda sq: (distance(sq, here), sq)))


@power(
    "p10131",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10131(c: Cast) -> None:
    """The standing arrangement is printed after the attack, so this swing is
    not one of the ones it pays out on."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)

    def pays(what: str, amount: int) -> Any:
        def fire(ev: Event) -> None:
            if getattr(ev, "attacker", None) != c.me or not by_melee(c.world, c.me, ev):
                return
            pool = sorted(a for a in c.allies() if c.can_see(a))
            friend = c.choose(pool, f"who is given the {what}") if pool else None
            if friend is not None:
                c.bonus(what, amount, on=friend, until=When.ENCOUNTER, once=True)

        return fire

    c.watch(Hit, pays("damage", 3), until=When.ENCOUNTER, label=f"{c.ref} on a hit")
    c.watch(Miss, pays("attack", 2), until=When.ENCOUNTER, label=f"{c.ref} on a miss")


@power(
    "p10945",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p10945(c: Cast) -> None:
    """The Effect is printed before the attack and is armed first, so this
    very use pays out when the Special line is taken up and it is a charge.

    Not `charges=True`: the printed Effect is not itself a charge, and the
    Special line is a note about how the row may be used.
    """

    def rally(ev: Hit) -> None:
        if ev.attacker != c.me or not getattr(ev, "charge", False):
            return
        for friend in _friends_within(c, 5):
            c.heal(5, on=friend)

    c.watch(Hit, rally, until=When.ENCOUNTER, label=f"{c.ref} rally")
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)


@power(
    "p10946",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.RELIABLE],
    attack=Attack(STR, vs=AC),
)
def p10946(c: Cast) -> None:
    """Reliable is read by `use` itself, so nothing here gives the use back.

    The Aftereffect hangs on the first hold's `on_end`: it begins when that
    hold goes, whichever way it went.
    """
    if not c.strike():
        return
    c.damage(c.w(3), c.str_mod)
    victim = c.target
    hold = c.grants_advantage(until=When.SAVE_ENDS, to="allies")
    if hold is not None:
        hold.on_end.append(
            lambda: c.grants_advantage(on=victim, until=When.EONT, to="allies")
        )


@power(
    "p10947",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10947(c: Cast) -> None:
    """`Powers.used` counts uses rather than storing a set, so the extra dice
    are a lookup and the extra use is one taken off the count.

    Not `Powers.unuse`, which floors at nought: a warlord who has spent none
    of its feature yet would get nothing, where the printed line says the
    encounter's allowance goes up by one whatever has happened so far.
    """
    powers = c.world.get(c.me, Powers)
    spent = min(powers.times(INSPIRING_WORD), 3) if powers else 0
    if c.strike():
        c.damage(c.w(2 + spent), c.str_mod)
    if powers is not None:
        powers.used[INSPIRING_WORD] = powers.times(INSPIRING_WORD) - 1


@power(
    "p10948",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10948(c: Cast) -> None:
    """Who was adjacent is read before the shove, because the shove is what
    makes the charge worth having and the printed line says "was"."""
    foe = c.target
    if foe is None:
        return
    beside = sorted(a for a in c.within(1, of=foe, side="ally") if a != c.me)
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.push(4)
    else:
        c.push(2)
    for friend in beside:
        if c.may("charge it", who=friend):
            c.charge_at(foe, who=friend)


@power(
    "p10949",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10949(c: Cast) -> None:
    foe = c.target
    if foe is None:
        return
    beside = sorted(a for a in c.within(1, of=foe, side="ally") if a != c.me)
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        _no_openings(c, foe, When.SAVE_ENDS)
    else:
        c.half_damage(c.w(3), c.str_mod)
        _no_openings(c, foe, When.EONT)
    for friend in beside:
        if c.may("back away", who=friend):
            _back_off(c, friend, foe)


def _no_openings(c: Cast, foe: int, until: When) -> Effect | None:
    """"Cannot make opportunity attacks": the window is refused rather than
    the attack, so the creature's own turn is left alone. The hold sits on
    the creature, which is what makes the save-ends half save."""

    def veto(ev: OpportunityWindow) -> None:
        if ev.actor == foe:
            ev.cancel(c.ref)

    return c.watch(
        OpportunityWindow, veto, until=until, window=Window.BEFORE, on=foe,
        label=f"{c.ref} no openings",
    )


def _back_off(c: Cast, friend: int, foe: int) -> None:
    """"Must end in a space that is not adjacent to the target." The walk is
    aimed: the decider knows nothing about where the ally has to finish."""
    paths = c.world.reachable_paths(friend, c.speed_of(friend))
    there = squares_of(c.world, foe)
    away = [
        sq for sq, path in paths.items()
        if path and min(distance(sq, s) for s in there) > 1
    ]
    if away:
        walk(c.world, friend, paths[min(away, key=lambda sq: (len(paths[sq]), sq))])


@power(
    "p11614",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=UpTo(2, "other_ally"),
    keywords=MARTIAL_WEAPON,
)
def p11614(c: Cast) -> None:
    """Both allies are handled on the first call, because "each target must
    attack a different creature" is a fact about the pair and the body is
    called once per target."""
    if not c.first:
        return
    taken: set[int] = set()
    for friend in c.targets:
        victim = _step_in(c, friend, 3, taken)
        if victim is None:
            continue
        taken.add(victim)
        for floored in _granted_hits(c, friend, victim, c.roll(_their_w(c, friend))):
            c.prone(on=floored)


def _step_in(c: Cast, friend: int, squares_: int, taken: set[int]) -> int | None:
    """Shift an ally into reach of somebody it may hit, and say who.

    Aimed rather than handed to the decider, which knows nothing about the
    swing that follows and will as readily retreat -- the trap
    `ranger/level_5.py` records. An ally already standing next to a fair
    victim stays where it is: three squares is a printed "up to", and the
    shift happens either way because the printed line grants it outright.
    """
    fair = [f for f in c.enemies() if f not in taken]
    near = sorted(f for f in c.within(1, of=friend, side="enemy") if f in fair)
    if near:
        return c.choose(near, "who that ally puts down")
    for where in sorted(c.world.reachable_squares(friend, squares_)):
        reachable = sorted(
            foe
            for foe in fair
            if min(distance(where, sq) for sq in squares_of(c.world, foe)) <= 1
        )
        if reachable:
            c.shift(squares_, who=friend, to=where)
            return c.choose(reachable, "who that ally puts down")
    c.shift(squares_, who=friend)
    return None


@power(
    "p11726",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11726(c: Cast) -> None:
    """"Different creatures that are not the targets of this attack" bars the
    creature you just swung at and bars the two allies from doubling up."""
    foe = c.target
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    pool = [a for a in _friends_within(c, 5) if c.can_see(a)]
    taken = {foe} if foe is not None else set()
    for _ in range(2):
        friend = c.choose(pool, "who takes a free swing", optional=True) if pool else None
        if friend is None:
            return
        pool.remove(friend)
        victims = sorted(f for f in c.within(1, of=friend, side="enemy") if f not in taken)
        victim = c.choose(victims, "who that ally swings at") if victims else None
        if victim is not None:
            taken.add(victim)
            c.grant_attack(friend, on=victim)


@power(
    "p2444",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2444(c: Cast) -> None:
    """The burn and the openings are one hold on one saving throw, which is
    what "as long as the ongoing damage persists" comes to. Two holds would
    be two saves and the openings could outlive the burn."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    if foe is None:
        return
    c.world.effects.apply(
        foe, c.me, When.SAVE_ENDS,
        label=f"{c.ref} ongoing 5 and openings",
        ongoing=(5, DamageType.UNTYPED),
        relations=[(Relation.GRANTS_CA_TO, foe, a) for a in c.allies()],
    )


@power(
    "p2593",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2593(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.mark(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(3), c.str_mod)
        c.mark(until=When.EOTNT)
    c.note(
        f"{c.ref}: while marked by this, {c.target} could not recharge its powers nor spend "
        "action points -- the recharge roll has nothing to consult and action points are "
        "not modelled"
    )


@power(
    "p2594",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2594(c: Cast) -> None:
    """The penalty is an Effect line and lands on every target either way."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    c.penalty("save", 2, until=When.ENCOUNTER)


@power(
    "p4571",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=REACTION,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_heavy_thrown,
    requires_text="needs a heavy thrown weapon",
    trigger=_ENEMY_CLOSES,
    on=Trigger(MoveEnd, when=_enemy_closes(3), text=_ENEMY_CLOSES),
)
def p4571(c: Cast) -> None:
    """`MoveEnd`, not `MoveStart`: a reaction declared on the start resolves
    where nothing has happened yet, so the enemy would not be inside three
    squares when the row asked.

    The allies' shots are an Effect line and happen whether the throw landed.
    """
    foe = c.target
    if c.strike():
        c.damage(c.w(1), c.str_mod + c.int_mod)
    else:
        c.half_damage(c.w(1), c.str_mod + c.int_mod)
    if foe is None:
        return
    for friend in _friends_within(c, 2):
        if c.may("take the shot", who=friend):
            c.grant_attack(friend, on=foe, ref=_shot(c, friend), damage_bonus=c.int_mod)


def _shot(c: Cast, friend: int) -> str:
    """The ranged basic, for a creature that has one.

    `Powers.all` is known plus the one row `basic` points at, so naming the
    engine's ranged basic outright is refused as "not known" for anybody who
    does not carry it -- which is every character this chargen builds. The
    fallback is that creature's own basic rather than nothing: a swing
    beyond its reach is refused by `usable` and costs the row nothing, where
    naming a row it does not have refuses the swing every time.
    """
    known = c.world.get(friend, Powers)
    return RANGED if known is not None and RANGED in known.all else ""


def _spent_encounter_attacks(world: World, who: int, cls: str = "") -> list[str]:
    """That creature's encounter attack rows it has already used.

    "Attack power" is read as a row that rolls one: nothing on the header
    separates an attack from a utility otherwise.
    """
    powers = world.get(who, Powers)
    if powers is None:
        return []
    out = []
    for ref in powers.known:
        p = get(ref)
        if p is None or p.usage is not Usage.ENCOUNTER or p.attack is None:
            continue
        if cls and p.cls != cls:
            continue
        if powers.times(ref):
            out.append(ref)
    return sorted(out)


@power(
    "p4572",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_OTHER_ALLY,
    keywords=MARTIAL,
)
def p4572(c: Cast) -> None:
    """The ally's use is given back and immediately spent again, so it ends
    the turn no better off than before -- which is what "can make an attack
    using a power he or she has already used" means. The row picks its own
    targets, so it is `use` rather than `c.grant_attack`: a burst would
    otherwise be narrowed to the one creature a granted swing names.
    """
    friend = c.target
    powers = c.world.get(friend, Powers) if friend is not None else None
    again = _spent_encounter_attacks(c.world, friend) if friend is not None else []
    ref = c.choose(again, "which spent power that ally uses again") if again else None
    if ref is not None and powers is not None:
        powers.unuse(ref)
        use(c.world, friend, ref, spend=True)
    mine = c.world.get(c.me, Powers)
    if mine is None:
        return
    fresh = [
        r for r in mine.known
        if (p := get(r)) is not None
        and p.usage is Usage.ENCOUNTER
        and p.attack is not None
        and not mine.times(r)
    ]
    spent = _spent_encounter_attacks(c.world, c.me, "warlord")
    if not fresh and spent:
        mine.unuse(c.choose(spent, "which of yours comes back"))


@power(
    "p6008",
    level=9,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_reach_weapon,
    requires_text="needs a reach weapon",
)
def p6008(c: Cast) -> None:
    """The slide names its destination because the printed line does: it has
    to finish adjacent to you, and a free slide of three would wander."""
    foe = c.target
    if foe is None:
        return
    _drag_in(c, foe)
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        _held_close(c, foe, When.ENCOUNTER)
    else:
        c.half_damage(c.w(3), c.str_mod)
        _held_close(c, foe, When.EONT)


def _drag_in(c: Cast, foe: int) -> None:
    here, there = c.here, c.there
    if here is None or there is None:
        return
    room = sorted(
        sq
        for sq in spread({here}, 1)
        if sq != here
        and sq != there
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and distance(sq, there) <= 3
    )
    where = c.choose(room, "where it ends up") if room else None
    if where is not None:
        c.slide(3, on=foe, to=where)


def _reach_of(c: Cast) -> int:
    gear = c.world.get(c.me, Gear)
    weapon = gear.main if gear else None
    return weapon.reach if weapon else 1


def _held_close(c: Cast, foe: int, until: When) -> None:
    """The hit line runs "until it starts its turn in a square outside your
    melee reach", which no `When` spells. Kept for the encounter and ended
    by a start-of-turn watcher the moment the printed condition is met; the
    miss line is an ordinary duration and needs none of that."""
    holds = [
        c.slowed(on=foe, until=until),
        c.grants_advantage(on=foe, until=until, to="allies"),
    ]
    if until is not When.ENCOUNTER:
        return

    def loosen(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != foe or c.distance(foe) <= _reach_of(c):
            return
        for held in holds:
            if held is not None and not held.ended:
                c.world.effects.end(held, c.ref)

    c.watch(
        TurnStart, loosen, until=When.ENCOUNTER, on=foe,
        label=f"{c.ref} until it breaks away",
    )
