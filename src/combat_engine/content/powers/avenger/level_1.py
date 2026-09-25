"""Avenger, level 1: the at-wills, and the first of the encounter attacks.

`level_1_b.py` carries the rest of the encounter rows and all of the
dailies; nothing but length distinguishes them, and it imports the helpers
below rather than growing its own.

Wisdom attacks everything the class owns, so every header is
`Attack(WIS, ...)` and every damage line carries `c.wis_mod`. The weapon rows
swing a longsword through `c.w()`; the implement rows roll their own dice and
carry no `[W]` at all. "Melee touch" is a reach of 1.

`oath.py` holds the questions these rows ask of the oath -- `is_oath` for
"if the target is your oath of enmity target", `swear` for the rows that
re-swear, `better_of_two` for the two rows printing their own copy of the
oath's reroll.

Three printed sentences have no header field, and are said once here rather
than in each row that carries them:

* **"You can use this power as a ranged basic attack"** and **"you can use
  this power in place of a melee basic attack when charging"** are both
  properties of the creature -- `Powers.basic` -- rather than of the row.
  Those rows are written as the standard actions they also are.
* **A build rider is gated on `c.build(...)`** and the ungated half is what
  an avenger without the build gets, which is the warlord precedent.
* **Two printed damage types are one packet** and `DamageType` holds one, so
  the first of the two is dealt and both keywords sit on the header.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    Attack,
    AttackRolled,
    Cast,
    DamageType,
    Effect,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    TurnEnd,
    When,
    distance,
    get,
    power,
)
from combat_engine.engine.events import (
    DamageApplied,
    Hit,
    Miss,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.query import adjacent, distance_between, squares, team

from .oath import better_of_two, is_oath

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


# -- the shapes these rows repeat -------------------------------------------


def _twice(c: Cast) -> None:
    """"You can roll twice on this attack and use either result".

    The row prints its own copy of the oath's line, so it is armed on the
    roll in the window before the swing rather than added as a bonus: a
    second roll is a second roll and not a +2.
    """
    me, ref = c.me, c.ref

    def roll_again(ev: AttackRolled) -> None:
        if ev.attacker == me and ev.power == ref:
            better_of_two(c, ev)

    c.watch(
        AttackRolled, roll_again, until=When.EOT, on=c.me, once=True,
        label=f"{ref} twice",
    )


def _near(c: Cast, square: tuple[int, int], who: int) -> int:
    """How far a square is from a creature, whatever size it is."""
    return min(distance(square, sq) for sq in squares(c.world, who))


def _step_toward(c: Cast, victim: int, steps: int) -> bool:
    """Shift, and finish nearer than you started. Two rows print that."""
    if steps <= 0:
        return False
    start = distance_between(c.world, c.me, victim)
    closer = [
        sq
        for sq in c.world.reachable_squares(c.me, steps)
        if _near(c, sq, victim) < start
    ]
    if not closer:
        return False
    return c.shift(steps, to=min(closer, key=lambda sq: _near(c, sq, victim)))


def _step_beside(c: Cast, victim: int, steps: int) -> bool:
    """Shift into a square next to a named creature."""
    beside = [
        sq
        for sq in c.world.reachable_squares(c.me, steps)
        if _near(c, sq, victim) <= 1
    ]
    return c.shift(steps, to=min(beside)) if beside else False


def _while_inside(
    c: Cast,
    zone: int,
    until: When,
    eligible: Callable[[int], bool],
    hold: Callable[[int], Iterable[Effect | None]],
) -> None:
    """Whoever stands in `zone` carries a hold for as long as they do.

    "Any enemy adjacent to you" is membership rather than a list taken once,
    so it is an aura and the hold follows who is standing in it.
    """
    held: dict[int, list[Effect]] = {}

    def take(who: int) -> None:
        if who in held or not eligible(who):
            return
        held[who] = [e for e in hold(who) if e is not None]

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            take(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone:
            for effect in held.pop(ev.actor, []):
                c.world.effects.end(effect, "stepped out")

    c.watch(ZoneEntered, entered, until=until, on=c.me, label=f"{c.ref} in")
    c.watch(ZoneExited, exited, until=until, on=c.me, label=f"{c.ref} out")
    for who in c.world.zones.occupants(zone):
        take(who)


def _hostile(c: Cast, who: int) -> bool:
    return who != c.me and team(c.world, who) is not team(c.world, c.me)


# -- at-will ----------------------------------------------------------------


@power(
    "p10401",
    level=1,
    cls="avenger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p10401(c: Cast) -> None:
    """The errata'd text, which adds the Level 21 line and the ranged basic
    attack; the second of those has no header field."""
    if c.strike():
        c.damage(
            "2d8" if c.level >= 21 else "1d8", c.wis_mod, dtype=DamageType.RADIANT
        )
        if is_oath(c):
            c.slowed(until=When.EONT)


@power(
    "p2894",
    level=1,
    cls="avenger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p2894(c: Cast) -> None:
    if c.strike():
        c.damage(
            "2d8" if c.level >= 21 else "1d8", c.wis_mod, dtype=DamageType.RADIANT
        )
        c.temp_hp(max(0, c.wis_mod), on=c.me)


@power(
    "p3423",
    level=1,
    cls="avenger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p3423(c: Cast) -> None:
    """The slide is into the square just left, so it is read before the step
    and named to `c.slide` afterwards."""
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.wis_mod)
    vacated = c.here
    if c.shift(1) and vacated is not None:
        c.slide(1, to=vacated)


@power(
    "p5332",
    level=1,
    cls="avenger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p5332(c: Cast) -> None:
    """"Doesn't end its next turn adjacent to you" can only be answered at
    the end of that turn, so the chase hangs off `TurnEnd` and spends itself
    on the target's first one whichever way the question went."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.wis_mod)
    me, steps, spent = c.me, 1 + max(0, c.dex_mod), []

    def chase(ev: TurnEnd) -> None:
        if spent or ev.actor != victim or ev.ghost:
            return
        spent.append(1)
        if not adjacent(c.world, me, victim) and c.may("give chase", who=me):
            _step_toward(c, victim, steps)

    c.watch(TurnEnd, chase, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} chase")


@power(
    "p5333",
    level=1,
    cls="avenger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p5333(c: Cast) -> None:
    """Hit *or* miss, so both events are armed off one latch: two watchers
    each carrying `once=True` would pay out twice."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.wis_mod)
    me, spent = c.me, []

    def lash(ev: Hit | Miss) -> None:
        if spent or ev.target != me or ev.attacker == victim:
            return
        if not _hostile(c, ev.attacker):
            return
        spent.append(1)
        c.flat(max(0, c.int_mod), dtype=DamageType.RADIANT, on=victim)

    for kind in (Hit, Miss):
        c.watch(kind, lash, until=When.EONT, on=c.me, label=f"{c.ref} answer")


@power(
    "p569",
    level=1,
    cls="avenger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p569(c: Cast) -> None:
    """"His or her next damage roll against the target" is a one-shot gated
    on who is being hit, which is the one key the damage context carries."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.wis_mod)
    friends = sorted(
        a
        for a in c.allies()
        if a != c.me and (c.adjacent(a) or c.adjacent_to(victim, a))
    )
    if not friends or c.int_mod <= 0:
        return
    c.bonus(
        "damage",
        c.int_mod,
        on=c.choose(friends, "who you point the opening out to"),
        until=When.ENCOUNTER,
        once=True,
        when=lambda ctx: ctx.get("target") == victim,
    )


@power(
    "p6980",
    level=1,
    cls="avenger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT, Keyword.CHARM],
    attack=Attack(WIS, vs=WILL),
)
def p6980(c: Cast) -> None:
    """No weapon dice and no damage at all unless the pull lands it beside
    you: the radiant half is the arrival, not the hit."""
    victim = c.target
    if victim is None:
        return
    if is_oath(c) and not c.within(1, side="enemy"):
        _twice(c)
    if not c.strike():
        return
    c.pull(max(0, c.int_mod))
    if c.adjacent(victim):
        c.damage(
            "2d10" if c.level >= 21 else "1d10", dtype=DamageType.RADIANT
        )


@power(
    "p7380",
    level=1,
    cls="avenger",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 15),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p7380(c: Cast) -> None:
    """Wisdom attacks on both branches, so there is no alternative line to
    declare -- the crossbow is the ranged half and its range is the 15 the
    weapon carries."""
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.wis_mod)
    if not is_oath(c):
        return
    others = sorted(e for e in c.within(1, side="enemy") if e != c.target)
    if others:
        c.push(2, on=c.choose(others, "who you shove clear"))


# -- encounter --------------------------------------------------------------


@power(
    "p10082",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR],
    attack=Attack(WIS, vs=AC),
)
def p10082(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    if not c.first:
        return
    ring = c.aura(1, label=c.ref, until=When.EONT, on=c.me)
    _while_inside(
        c,
        ring,
        When.EONT,
        lambda who: _hostile(c, who),
        lambda who: [c.penalty("attack", 2, on=who, until=When.EONT)],
    )


@power(
    "p10400",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p10400(c: Cast) -> None:
    if is_oath(c):
        _twice(c)
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.RADIANT)
        c.slowed(until=When.EONT)


@power(
    "p11038",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(WIS, vs=AC),
)
def p11038(c: Cast) -> None:
    """The echo is armed after this row's own lightning has landed, so the
    blow that sets it up is not also the blow that spends it. "Damage from an
    attack" is read off `DamageApplied.detail`, which names the row that
    dealt it -- a zone's bite and a burn name themselves differently.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.wis_mod)
    c.damage("1d6", dtype=DamageType.LIGHTNING)
    spent: list[int] = []

    def echo(ev: DamageApplied) -> None:
        if spent or ev.target != victim or ev.amount <= 0:
            return
        declared = get(ev.detail.removesuffix(" (half)"))
        if declared is None or declared.attack is None:
            return
        spent.append(1)
        c.flat(c.roll("1d6"), dtype=DamageType.THUNDER, on=victim)

    c.watch(DamageApplied, echo, until=When.SONT, on=c.me, label=f"{c.ref} echo")


@power(
    "p2893",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p2893(c: Cast) -> None:
    """Both halves of the Special are about charging and neither has
    anywhere to go: what a charge swings is `Powers.basic`, and the +4
    against the openings the run provokes would have to be granted before a
    body that only runs after the move is over."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod)


@power(
    "p2905",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p2905(c: Cast) -> None:
    """One arrangement read by three events: ending a turn beside the
    avenger, and hitting or missing it. The target is not excused either --
    the printed line says any enemy."""
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
    if not c.first:
        return
    me = c.me
    amount = 5 + (c.int_mod if c.build("retribution") else 0)

    def sear(who: int) -> None:
        if _hostile(c, who):
            c.flat(amount, dtype=DamageType.RADIANT, on=who)

    def on_turn(ev: TurnEnd) -> None:
        if not ev.ghost and adjacent(c.world, me, ev.actor):
            sear(ev.actor)

    def on_swing(ev: Hit | Miss) -> None:
        if ev.target == me:
            sear(ev.attacker)

    c.watch(TurnEnd, on_turn, until=When.EONT, on=c.me, label=f"{c.ref} sear")
    for kind in (Hit, Miss):
        c.watch(kind, on_swing, until=When.EONT, on=c.me, label=f"{c.ref} sear")


@power(
    "p5334",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p5334(c: Cast) -> None:
    """The step is an Effect line printed before the attack, so it is taken
    before the swing and whether the swing lands or not."""
    if c.first:
        c.shift((1 + c.dex_mod) if c.build("pursuit") else 2)
    if c.strike():
        c.damage(c.w(2), c.wis_mod)


@power(
    "p5335",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p5335(c: Cast) -> None:
    """"The same damage" is the number that came off the first one rather
    than a second roll, so it is dealt flat. "A second creature" is read as
    another enemy: nothing about the row wants a friend chosen."""
    if not c.strike():
        return
    dealt = c.damage("1d10", c.wis_mod, dtype=DamageType.PSYCHIC)
    others = sorted(e for e in c.enemies() if e != c.target and c.can_see(e))
    if others and dealt > 0:
        c.flat(
            dealt,
            dtype=DamageType.PSYCHIC,
            on=c.choose(others, "who shares the wound"),
        )
