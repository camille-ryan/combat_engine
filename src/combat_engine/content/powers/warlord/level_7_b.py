"""Warlord, level 7: the encounter attacks printed outside the first book.

The swing is the same in nearly all of them and what differs is the gift
attached, as at level 3 and level 7 already. `c.grant_attack` and
`c.provoke` exist now, so the two shapes `level_1.py` wrote down as notes --
an ally's free swing and an ally's opportunity attack -- are written here.

Three riders name a build this chargen does not offer. Each is gated on
`c.build(...)` all the same: that is the printed sentence, and the ungated
half is what a warlord without the build gets.

What is still written down rather than approximated: an action point, which
the engine does not model at all (`p11612`); "cannot mark" and "cannot gain
combat advantage", neither of which has a veto to hang on (`p10162`); and
"treats every square as difficult terrain", which is `c.ignores_difficult`
inverted and has no card (`p7508`).

`p10935` and `p10941` are declared triggers the audit board cannot produce
-- an enemy hitting an *ally*, and an *ally* making a close or area attack,
neither of which the harness's provocations include. Both were driven by
hand: the first shifts two squares into reach and swings, the second
interrupts with a hit and a four-square slide.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Budget,
    Cast,
    Event,
    Gear,
    Health,
    Keyword,
    Melee,
    MeleeOrRanged,
    Relation,
    Trigger,
    Usage,
    When,
    World,
    by_melee,
    distance,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import AttackDeclared, Hit, Miss, SurgeSpent, TurnStart
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

_ENEMY_HITS_MY_ALLY = "an enemy within 3 squares of you hits your ally"
_ALLY_SWEEPS = "an ally makes a close or an area attack"


def _friends_within(c: Cast, radius: int) -> list[int]:
    """`side="ally"` counts the caster and every printed line here says
    "an ally", so the caster comes back out."""
    return sorted(a for a in c.within(radius, side="ally") if a != c.me)


def _mine(c: Cast, who: int | None) -> bool:
    """On my side and not me -- what "an ally" means inside a watcher."""
    return who is not None and who != c.me and team(c.world, who) is team(c.world, c.me)


def _shield(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.shield)


def _step_toward(c: Cast, victim: int, squares_: int) -> None:
    """Shift, aimed rather than handed to the decider.

    The decider knows nothing about the swing that follows and will as
    readily retreat -- the trap `ranger/level_5.py` records. The printed
    line puts this shift before the attack precisely so the attack can
    reach, so the square nearest the victim is the one taken.
    """
    options = c.world.reachable_squares(c.me, squares_)
    if not options:
        return
    there = squares_of(c.world, victim)
    if not there:
        return
    nearest = min(options, key=lambda sq: (min(distance(sq, s) for s in there), sq))
    c.shift(squares_, to=nearest)


# -- declared triggers ------------------------------------------------------


def _hits_my_ally(radius: int) -> Any:
    def check(world: World, me: int, ev: Event) -> bool:
        struck = getattr(ev, "target", None)
        attacker = getattr(ev, "attacker", None)
        if struck is None or attacker is None or struck == me:
            return False
        if team(world, struck) is not team(world, me):
            return False
        if team(world, attacker) is team(world, me):
            return False
        return distance_between(world, me, attacker) <= radius

    return check


def _ally_sweeps(world: World, me: int, ev: Event) -> bool:
    """An ally's close or area attack. The reach lives on the row, and the
    branch says which half of a two-branch row actually swung."""
    attacker = getattr(ev, "attacker", None)
    if attacker is None or attacker == me:
        return False
    if team(world, attacker) is not team(world, me):
        return False
    p = get(getattr(ev, "power", "") or "")
    if p is None:
        return False
    return p.reach_of(getattr(ev, "branch", 0)).kind in (
        "close_burst",
        "close_blast",
        "area_burst",
    )


# -- the rows ---------------------------------------------------------------


@power(
    "p10129",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10129(c: Cast) -> None:
    """Penalties always stack, so the printed maximum of -5 is counted here
    rather than left to the stacking rules to enforce."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    if foe is None:
        return
    laid = [0]

    def rattle(ev: Hit) -> None:
        if ev.target != foe or laid[0] >= 5 or not _mine(c, ev.attacker):
            return
        laid[0] += 1
        c.penalty("attack", 1, on=foe, until=When.EONT)

    c.watch(Hit, rattle, until=When.EONT, label=f"{c.ref} rattled")
    if c.build("bravura"):
        for friend in _friends_within(c, 1):
            c.bonus(
                "damage",
                c.cha_mod,
                on=friend,
                until=When.EONT,
                when=lambda ctx: ctx.get("target") == foe,
            )


@power(
    "p10162",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=WILL),
)
def p10162(c: Cast) -> None:
    """Clearing the target's marks is the Effect line and lands either way.

    A mark is a relation, so the hold carrying it is the thing to end: the
    condition and the relation come off together and whatever laid it is
    none of this row's business.
    """
    foe = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    if foe is None:
        return
    for friend in c.allies():
        for held in list(c.world.effects.of(friend)):
            if any(k is Relation.MARKED_BY and s == foe for k, s, _ in held.relations):
                c.world.effects.end(held, c.ref)
    c.note(
        f"{c.ref}: until the end of your next turn {foe} could not mark your allies nor "
        "gain combat advantage against them -- a mark has no veto to hang on and combat "
        "advantage is computed rather than held"
    )


@power(
    "p10935",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_ENEMY_HITS_MY_ALLY,
    on=Trigger(Hit, when=_hits_my_ally(3), text=_ENEMY_HITS_MY_ALLY),
)
def p10935(c: Cast) -> None:
    """The shift is printed before the attack and is what brings the enemy
    into reach, so the swing is aimed at the creature that triggered this
    rather than at whatever the dispatcher could find within a sword's
    length at the moment of the offer."""
    foe = getattr(c.trigger, "attacker", None) or c.target
    if foe is None:
        return
    _step_toward(c, foe, 2)
    if c.strike(on=foe):
        c.damage(c.w(2), c.str_mod, on=foe)


@power(
    "p10936",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=[*MARTIAL_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p10936(c: Cast) -> None:
    """Paying for somebody else's surge is the ally's surge handed straight
    back and one of yours spent instead -- `c.spend_surge`, not `c.surge`,
    because the printed line says you regain nothing for it.

    `SurgeSpent` is emitted after the pool has been decremented, which is
    why the refund reads as an increment rather than as a veto.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)

    def cover(ev: SurgeSpent) -> None:
        if not _mine(c, ev.actor):
            return
        health = c.world.get(ev.actor, Health)
        if health is None or not c.spend_surge(on=c.me):
            return
        health.surges += 1

    c.watch(SurgeSpent, cover, until=When.EONT, label=f"{c.ref} pays")


@power(
    "p10941",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_ALLY_SWEEPS,
    on=Trigger(AttackDeclared, when=_ally_sweeps, text=_ALLY_SWEEPS),
)
def p10941(c: Cast) -> None:
    """Interrupting means the ally's sweep has not resolved yet, so the
    Insightful rider cannot be read off a hit that has not happened. It is a
    one-shot damage bonus on the ally, gated on this target -- which pays out
    exactly when the printed sentence says it does.

    "One creature not targeted by the triggering attack" is `among`, the
    whole target list of the one power use.
    """
    spared = set(getattr(c.trigger, "among", ()) or ())
    victim = c.target
    if victim in spared:
        pool = sorted(f for f in c.enemies() if f not in spared and c.distance(f) <= 1)
        victim = c.choose(pool, "who you hit instead") if pool else None
    if victim is None:
        return
    friend = getattr(c.trigger, "attacker", None)
    if friend is not None and c.build("insightful"):
        c.bonus(
            "damage",
            max(c.wis_mod, c.cha_mod),
            on=friend,
            until=When.EOT,
            when=lambda ctx: ctx.get("target") == victim,
            once=True,
        )
    if c.strike(on=victim):
        c.damage(c.w(2), c.str_mod, on=victim)
        c.slide(c.str_mod, on=victim)


@power(
    "p10942",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10942(c: Cast) -> None:
    """The granted swing is an Effect line and happens on a miss too; only
    the bonus to it depends on the warlord's own blow landing."""
    landed = c.strike()
    if landed:
        c.damage(c.w(1), c.str_mod)
    foe = c.target
    if foe is None:
        return
    pool = sorted(a for a in c.allies() if c.can_see(a))
    friend = c.choose(pool, "who takes a free swing") if pool else None
    if friend is not None:
        c.grant_attack(
            friend, on=foe, attack_bonus=max(c.int_mod, c.wis_mod) if landed else 0
        )


@power(
    "p10943",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10943(c: Cast) -> None:
    """An extra move action is a slot in next turn's budget. It is handed
    over by a watcher rather than added now, because `Budget.refresh` wipes
    the turn clean at the start of it."""
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod)
    for friend in _friends_within(c, 5):
        _extra_move(c, friend)


def _extra_move(c: Cast, friend: int) -> None:
    """One more move action, the next time that creature's turn comes round.

    The hold is ended by hand rather than with `once=True`: a budget is a
    plain component, so handing one over announces nothing and leaves no
    effect behind, and `watch`'s latch reads exactly those two things.
    """
    held: list[Any] = []

    def at_start(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != friend:
            return
        budget = c.world.get(friend, Budget)
        if budget is not None:
            budget.move += 1
        if held:
            c.world.effects.end(held[0], "spent")

    held.append(
        c.watch(
            TurnStart,
            at_start,
            until=When.ENCOUNTER,
            on=friend,
            label=f"{c.ref} extra move",
        )
    )


@power(
    "p10944",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10944(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    amount = max(c.wis_mod, c.cha_mod)

    def hearten(ev: Hit) -> None:
        if ev.target == foe and _mine(c, ev.attacker):
            c.temp_hp(amount, on=ev.attacker)

    c.watch(Hit, hearten, until=When.EONT, label=f"{c.ref} heartened")


@power(
    "p11612",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11612(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.shift(c.speed_of() // 2)
    c.note(
        f"{c.ref}: until the start of your next turn an ally that can see you could shift "
        "half its speed when it spent an action point -- action points are not modelled"
    )


@power(
    "p11613",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11613(c: Cast) -> None:
    """One reward, taken by the first ally to land a blow, and the choice is
    the ally's rather than the warlord's -- it is that creature's turn and
    its bonus. The hold is spent by hand for the same reason `_extra_move`
    is: three of the four branches are one modifier, and `once=True` would
    burn the watch on the first `Hit` of any shape."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    held: list[Any] = []

    def reward(ev: Hit) -> None:
        if ev.target != foe or not _mine(c, ev.attacker):
            return
        taken = c.world.decide(
            ev.attacker, "choose", ["defences", "attack", "damage"], c.ref
        )
        if taken == "defences":
            for defence in (AC, FORT, REF, WILL):
                c.bonus(defence, 2, on=ev.attacker, until=When.EOTNT)
        elif taken == "attack":
            c.bonus("attack", 1, on=ev.attacker, until=When.EOTNT)
        else:
            c.bonus("damage", 3, on=ev.attacker, until=When.EOTNT)
        if held:
            c.world.effects.end(held[0], "taken")

    held.append(c.watch(Hit, reward, until=When.EONT, label=f"{c.ref} reward"))


@power(
    "p2331",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2331(c: Cast) -> None:
    """A printed "can", so each ally is asked; the save is their own."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    bonus = c.int_mod if c.build("resourceful") else 0
    for friend in _friends_within(c, 2):
        if c.may("try to shake something off", who=friend):
            c.save(on=friend, bonus=bonus)


@power(
    "p2332",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_shield,
    requires_text="needs a shield",
)
def p2332(c: Cast) -> None:
    """AC and Reflex are different `what`s, so both are written and neither
    swallows the other."""
    landed = c.strike()
    if landed:
        c.damage(c.w(2), c.str_mod)
    if not landed and not c.build("resourceful"):
        return
    for friend in _friends_within(c, 1):
        c.bonus(AC, 2, on=friend, until=When.EONT)
        c.bonus(REF, 2, on=friend, until=When.EONT)


@power(
    "p2562",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p2562(c: Cast) -> None:
    """`c.provoke` names who swings and who is swung at, which is the printed
    line exactly -- the window is the engine's and the opportunity attack is
    whatever that ally's own is."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    if foe is None:
        return
    pool = _friends_within(c, 5)
    friend = c.choose(pool, "who watches for an opening") if pool else None
    if friend is None:
        return

    def opening(ev: AttackDeclared) -> None:
        if ev.target in (c.me, friend) and by_melee(c.world, c.me, ev):
            c.provoke(friend, on=foe)

    c.on_attack(opening, by=foe, until=When.EONT, label=f"{c.ref} watch")


@power(
    "p4567",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4567(c: Cast) -> None:
    """Bravura's guard is spent on the one swing the target is given, so it
    is a gated one-shot rather than a standing bonus to AC."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    foe = c.target
    if foe is None:
        return
    bravura = c.cha_mod if c.build("bravura") else 0
    if bravura:
        c.bonus(
            AC,
            bravura,
            on=c.me,
            until=When.EOT,
            when=lambda ctx: ctx.get("attacker") == foe,
            once=True,
        )
    if _swung_and_missed(c, foe):
        pool = sorted(a for a in c.within(1, of=foe, side="ally") if a != c.me)
        friend = c.choose(pool, "who answers the miss") if pool else None
        if friend is not None and c.may("take the free swing", who=friend):
            c.grant_attack(friend, on=foe, damage_bonus=bravura)


def _swung_and_missed(c: Cast, foe: int) -> bool:
    """Hand the target its compelled swing and say whether it missed.

    `c.grant_attack` reports that a row went off, not that it connected, and
    an attack that never happened at all is not a miss.
    """
    outcome: list[bool] = []
    subs = [
        c.world.bus.on(Hit, lambda ev: outcome.append(True) if ev.attacker == foe else None),
        c.world.bus.on(Miss, lambda ev: outcome.append(False) if ev.attacker == foe else None),
    ]
    try:
        c.grant_attack(foe, on=c.me)
    finally:
        for sub in subs:
            c.world.bus.off(sub)
    return bool(outcome) and not outcome[0]


@power(
    "p4568",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4568(c: Cast) -> None:
    """The penalty is an Effect line and lands on a miss too. `on=c.me`,
    because `c.penalty` otherwise aims at the creature you just swung at."""
    if c.strike():
        c.damage(c.w(2), c.str_mod + c.cha_mod)
        pool = _friends_within(c, 5)
        friend = c.choose(pool, "who is spurred on") if pool else None
        if friend is not None:
            c.bonus("attack", c.cha_mod, on=friend, until=When.SONT, once=True)
    c.penalty(AC, 2, on=c.me, until=When.SONT)


def _simple_row(ctx: dict[str, Any]) -> bool:
    """"With basic attacks and at-will powers". Both basic attacks are
    at-wills in the registry, so one question answers the printed pair."""
    p = get(ctx.get("power", "") or "")
    return p is not None and p.usage is Usage.AT_WILL


@power(
    "p4569",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4569(c: Cast) -> None:
    """The two halves are different `what`s and stack; the Inspiring rider
    replaces the damage half outright rather than adding to it, which is
    what "the bonus to damage rolls equals" says."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    hurt = c.cha_mod if c.build("inspiring") else 1
    for friend in c.allies():
        if not c.can_see(friend):
            continue
        c.bonus("attack", 1, on=friend, until=When.SONT, when=_simple_row)
        c.bonus("damage", hurt, on=friend, until=When.SONT, when=_simple_row)


@power(
    "p7508",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7508(c: Cast) -> None:
    """"Ignores difficult terrain" is a property of the mover and has a card.
    The other half -- one creature treating every square as difficult -- is
    that property inverted and has none: nothing consults a per-creature
    terrain cost, and slowing is a different card altogether."""
    landed = c.strike()
    if landed:
        c.damage(c.w(2), c.str_mod)
        c.ignores_difficult(on=c.me, until=When.EONT)
        c.note(
            f"{c.ref}: until the end of your next turn {c.target} would treat every square "
            "as difficult terrain -- a per-creature terrain cost is not expressible"
        )
    if landed or c.build("resourceful"):
        for friend in c.allies():
            c.ignores_difficult(on=friend, until=When.EONT)
