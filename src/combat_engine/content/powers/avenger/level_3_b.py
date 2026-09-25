"""Avenger, level 3: the rest of the encounter attacks.

Ten rows, mostly a sword and a rider. Three notes that recur.

* **The build riders** -- three different ones appear here -- are gated on
  `c.build(...)` and the ungated half is what a character without the build
  gets, which is the warlord precedent in `warlord/level_7_b.py`.
* **A rider that moves the avenger to a named square** names it: `c.shift`
  and `c.teleport` otherwise hand the choice to the decider, and "to a
  square adjacent to the target" is an instruction.
* **Two damage types in one packet** -- "5 fire and lightning damage" --
  is not something `DamageType` can hold. It is dealt as the first of the
  two printed rather than twice; see the report.

`p10403` is declared with no Target line at all. Its printed Target is the
triggering enemy, which is by definition *not* adjacent -- the row teleports
into reach before it swings -- and a melee row with a target line is refused
outright whenever nothing is in reach of the sword. `Power.is_attack` reads
the target line, so dropping it is what lets the row be offered in the one
situation it exists for; the creature is read off `c.trigger` instead.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    REACTION,
    STANDARD,
    WIS,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageRolled,
    DamageType,
    Event,
    Keyword,
    Melee,
    Square,
    Trigger,
    TurnEnd,
    When,
    Window,
    World,
    by_melee,
    by_ranged,
    distance,
    power,
)
from combat_engine.engine.query import adjacent, distance_between, squares

from .level_3 import beside
from .oath import sworn

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]

_OATH_NEAR_BUT_APART = (
    "your oath of enmity target ends its turn within 5 squares of you "
    "but not adjacent to you"
)


def _oath_near_but_apart(world: World, me: int, ev: Event) -> bool:
    return (
        sworn(world, me, ev.actor)
        and not adjacent(world, me, ev.actor)
        and distance_between(world, me, ev.actor) <= 5
    )


def _shift_beside(c: Cast, victim: int, steps: int) -> Square | None:
    """Where a shift of `steps` can end that is adjacent to the target.

    None when there is nowhere: the printed line makes ending beside the
    target a condition of the shift, not a preference.
    """
    theirs = squares(c.world, victim)
    if not theirs:
        return None
    options = [
        sq
        for sq in c.world.reachable_squares(c.me, steps)
        if any(distance(sq, s) <= 1 for s in theirs)
    ]
    if not options:
        return None
    return min(options, key=lambda sq: (min(distance(sq, s) for s in theirs), sq))


@power(
    "p10403",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[*DIVINE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(WIS, vs=AC),
    trigger=_OATH_NEAR_BUT_APART,
    on=Trigger(TurnEnd, when=_oath_near_but_apart, text=_OATH_NEAR_BUT_APART),
)
def p10403(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    landing = beside(c, foe, c.me)
    if landing is not None:
        c.teleport(c.distance(foe) + 1, to=landing)
    if c.strike(on=foe):
        c.damage(c.w(1), c.wis_mod, on=foe)


@power(
    "p2904",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.THUNDER],
    attack=Attack(WIS, vs=FORT),
)
def p2904(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.THUNDER)
        c.pull(2)
        c.slowed(until=When.EONT)


@power(
    "p2911",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(WIS, vs=AC),
)
def p2911(c: Cast) -> None:
    victim = c.target
    steps = 1 + max(0, c.dex_mod) if c.build("pursuit") else 2
    if victim is None or not c.strike():
        return
    c.damage(c.w(2), c.wis_mod)
    c.teleport(steps, who=victim)
    landing = beside(c, victim, c.me)
    if landing is not None:
        c.teleport(c.distance(victim) + 1, to=landing)


@power(
    "p3518",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FIRE],
    attack=Attack(WIS, vs=AC),
)
def p3518(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2), c.wis_mod, dtype=DamageType.FIRE)
    amount = 5 + c.int_mod if c.build("retribution") else 5

    def scorch(ev: TurnEnd) -> None:
        if ev.actor != victim and ev.actor in c.enemies() and c.adjacent_to(victim, ev.actor):
            c.flat(amount, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnEnd, scorch, until=When.EONT, on=c.me, label=f"{c.ref} pyre")


@power(
    "p5339",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.THUNDER],
    attack=Attack(WIS, vs=AC),
)
def p5339(c: Cast) -> None:
    """The blow is moved on the declaration, which is the only window in
    which an attack has a target and no result yet -- `c.redirect` reads
    the same field, and is no use here because this is a watcher rather
    than a row the dispatcher offered.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.wis_mod, dtype=DamageType.THUNDER)
    me, spent = c.me, []

    def divert(ev: AttackDeclared) -> None:
        if spent or ev.target != me or ev.attacker == me:
            return
        if not (by_melee(c.world, me, ev) or by_ranged(c.world, me, ev)):
            return
        shields = sorted(f for f in c.enemies() if f != ev.attacker and c.adjacent(f))
        if not shields:
            return
        spent.append(True)
        ev.target = c.choose(shields, "who the blow finds instead")

    c.watch(
        AttackDeclared, divert, until=When.EONT, window=Window.BEFORE, on=me,
        label=f"{c.ref} misdirection",
    )


@power(
    "p6996",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p6996(c: Cast) -> None:
    """The step comes before the roll and the phasing lasts only for it, so
    the mode is raised and taken down here rather than clocked."""
    if c.first:
        ghost = c.phasing(on=c.me, until=When.EOT)
        c.shift(max(1, c.speed_of() // 2))
        if ghost is not None:
            c.world.effects.end(ghost, "the movement ended")
    if c.strike():
        c.damage(c.w(2), c.wis_mod)


@power(
    "p6997",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p6997(c: Cast) -> None:
    """The allies are counted *after* the push, which is what makes the
    push worth aiming: the printed line says so outright."""
    victim = c.target
    steps = max(1, c.int_mod) if c.build("unity") else 1
    if victim is None or not c.strike():
        return
    c.damage(c.w(1))
    c.push(steps)
    beside_it = [a for a in c.within(1, of=victim, side="ally") if a != c.me]
    if beside_it:
        c.flat(3 * len(beside_it))
    landing = _shift_beside(c, victim, steps)
    if landing is not None:
        c.shift(steps, to=landing)


@power(
    "p6998",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p6998(c: Cast) -> None:
    """The build rider makes this row an opportunity attack as well as a
    standard action, and a row holds one action type; see the report."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p7000",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FIRE, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=AC),
)
def p7000(c: Cast) -> None:
    """The rider is read before the swing: "when the attack hits" is the
    moment the die lands, and the blast that follows can move people.

    "5 fire and lightning damage" is one packet of two types, which
    `DamageType` cannot hold; it is dealt as the first of the two printed.
    """
    victim = c.target
    if victim is None:
        return
    alone = not [w for w in c.within(1, of=victim) if w != victim]
    extra = c.int_mod if alone and c.build("retribution") else 0
    if not c.strike():
        return
    c.damage(c.w(1), c.wis_mod + extra)

    def blast(ev: TurnEnd) -> None:
        if ev.actor != victim:
            return
        near = [f for f in c.enemies() if f != victim and c.adjacent_to(victim, f)]
        for foe in near:
            c.flat(5, dtype=DamageType.FIRE, on=foe)
        if not near:
            c.flat(5, dtype=DamageType.FIRE, on=victim)

    c.watch(
        TurnEnd, blast, until=When.ENCOUNTER, on=c.me, once=True,
        label=f"{c.ref} backlash",
    )


@power(
    "p7697",
    level=3,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p7697(c: Cast) -> None:
    """The share is taken in the one window where the number exists and has
    not yet come off anybody, which is why this watches the damage rather
    than the hit: "hits **and damages** you" is a number, and an attack
    that hits for nothing splits nothing.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(2), c.wis_mod)
    c.immobilized(until=When.EONT)
    me, spent = c.me, []

    def split(ev: DamageRolled) -> None:
        if spent or ev.target != me or ev.amount <= 0:
            return
        if ev.source in (me, victim) or ev.source not in c.enemies():
            return
        if not adjacent(c.world, me, victim):
            return
        spent.append(True)
        share = ev.amount // 2
        ev.amount -= share
        c.flat(share, dtype=ev.dtype, on=victim)

    c.watch(
        DamageRolled, split, until=When.EONT, window=Window.BEFORE, on=me,
        label=f"{c.ref} shared pain",
    )
