"""Ranger, level 1, beyond the first book: the second half.

`level_1_b.py` sets out the three shapes this level keeps returning to --
the absent beast companion, the thrown weapon with no flag to check, and the
melee row that moves before it swings. The rows here follow them.

Two more things are settled here. **A dual-range row** prints two attack
lines and two damage lines at once; the header carries `attack` and
`attack_alt`, and the damage reads `c.attack_mod`, which is the modifier of
whichever ability *this branch* attacked with. That is how both printed
damage lines get said with one expression. **Two swings** is `c.strike()`
twice, with `hand=` telling the second one which fist it came from.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    STANDARD,
    STR,
    Attack,
    AttackRolled,
    Cast,
    Gear,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    Target,
    UpTo,
    When,
    World,
    distance,
    power,
)
from combat_engine.engine.query import flanked_by
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

_QUARRY = Target("enemy", 1, label="One creature designated as your quarry")
_BLOODIED = Target("enemy", 1, label="One bloodied creature")


def _has_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons" -- two that are not fired."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _step_beside(c: Cast, who: int, squares_: int) -> None:
    """Aim a shift at a square next to `who`, for the swing that follows."""
    beside = squares_of(c.world, who)
    steps = [
        s
        for s in c.world.reachable_squares(c.me, squares_)
        if any(distance(s, f) <= 1 for f in beside)
    ]
    if steps:
        c.shift(squares_, to=steps[0])


def _reroll_next_attack(c: Cast) -> None:
    """"You can reroll the attack roll but must use the second result."

    `c.reroll_attack` reads the roll off `c.trigger`, so it only means
    anything inside a row the dispatcher offered, and this is a standard
    action. The live `AttackResult` rides on `AttackRolled` as a plain
    attribute for exactly this purpose, and `resolve.attack` reads the
    defence again once that window closes -- so a die changed here is the
    one judged.
    """
    mine, ref = c.me, c.ref
    spent = [False]

    def again(ev: AttackRolled) -> None:
        result = getattr(ev, "result", None)
        if spent[0] or result is None or ev.attacker != mine or ev.power != ref:
            return
        spent[0] = True
        face = c.world.rng.d20().total
        result.total += face - result.natural
        result.natural = face
        result.critical = face == 20
        result.hit = face == 20 or (
            face != 1 and result.total >= result.target_defence
        )

    c.watch(AttackRolled, again, until=When.EOT, on=mine)


@power(
    "p12501",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p12501(c: Cast) -> None:
    """The Effect -- a second row the beast companion may be commanded to
    use -- is not written: there is no companion to command."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)


@power(
    "p2595",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p2595(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1, hand="off"), c.str_mod)


@power(
    "p2602",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p2602(c: Cast) -> None:
    """One target buys a fatter damage roll, two cost accuracy. `c.first and
    c.last` is how a per-target body asks how many there are."""
    alone = c.first and c.last
    if c.strike(plus=0 if alone else -2):
        c.damage(c.w(1), c.dex_mod + (2 if alone else 0))


@power(
    "p4368",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4368(c: Cast) -> None:
    """The Effect is a step by the beast companion and is not written."""
    if c.strike():
        c.damage(c.w(1), c.str_mod)


@power(
    "p4370",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=_QUARRY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4370(c: Cast) -> None:
    """Half of the opening shift, and none of the Beast rider: the
    companion's step and its extra damage both need a companion."""
    if c.target is not None and not c.adjacent():
        _step_beside(c, c.target, 2)
    if c.strike():
        c.damage(c.w(2), c.str_mod)


@power(
    "p4371",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4371(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        if victim is not None and flanked_by(c.world, victim, c.me):
            c.flat(max(0, c.wis_mod))


@power(
    "p4372",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p4372(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        alone = victim is not None and not [
            x for x in c.within(1, of=victim) if x != victim
        ]
        if alone:
            c.flat(max(0, c.wis_mod))


@power(
    "p4374",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p4374(c: Cast) -> None:
    """"Until the target is reduced to 0 hit points" is held for the
    encounter: the watcher stops paying out once the creature is gone,
    because a dead one cannot be hit."""
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
        c.temp_hp(max(0, c.wis_mod), on=c.me)
    else:
        c.half_damage(c.w(2), c.attack_mod)
    if victim is None:
        return
    mine, drink = c.me, max(0, c.wis_mod)

    def again(ev: Hit) -> None:
        if ev.attacker == mine and ev.target == victim:
            c.temp_hp(drink, on=mine)

    c.watch(Hit, again, until=When.ENCOUNTER, on=mine)


@power(
    "p4375",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4375(c: Cast) -> None:
    """Only the half of the Effect that moves the target: sliding the beast
    companion after it needs a companion to slide."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if c.is_quarry():
        c.slide(2)


@power(
    "p4376",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=_BLOODIED,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p4376(c: Cast) -> None:
    """The wider critical range is a `crit_range` modifier laid down just
    before the roll -- `resolve.attack` reads it off the caster when it
    decides what counts as a critical."""
    if c.is_quarry():
        c.bonus("crit_range", 1, on=c.me, until=When.EOT)
    if c.strike():
        c.damage(c.w(3), c.attack_mod)
    else:
        c.half_damage(c.w(3), c.attack_mod)


@power(
    "p4377",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p4377(c: Cast) -> None:
    """"Or until you attack with your off-hand weapon" is not written: an
    attack event says which power swung and never which fist."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    c.bonus(AC, max(1, c.wis_mod), on=c.me, until=When.EONT)


@power(
    "p7390",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p7390(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.bonus(AC, 2, on=c.me, until=When.EONT)


@power(
    "p7397",
    level=1,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p7397(c: Cast) -> None:
    """`advantage=None` is "ask the board", which is what the row wants when
    the crowd is not there -- passing False would deny a flank."""
    crowd = (
        [a for a in c.within(1, of=c.target, side="ally") if a != c.me]
        if c.target is not None
        else []
    )
    if c.strike(advantage=True if len(crowd) >= 2 else None):
        c.damage(c.w(1), c.dex_mod)


@power(
    "p883",
    level=1,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p883(c: Cast) -> None:
    """The attack reroll is armed; the damage-die reroll is not. `c.damage`
    rolls its expression in one go and offers no handle on the individual
    dice, and "reroll each die, keeping the second" needs one choice per
    die."""
    _reroll_next_attack(c)
    if c.strike():
        c.damage(c.w(3), c.dex_mod)


@power(
    "p9350",
    level=1,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p9350(c: Cast) -> None:
    """Where the slide ends -- "a square adjacent to you" -- cannot be said:
    `c.slide` takes no destination and an anchor does nothing to a slide, so
    the mover's decider picks."""
    landed = 0
    for swing in range(2):
        if c.strike():
            landed += 1
            c.damage(c.w(1, hand="off" if swing else "main"), c.str_mod)
            c.slide(3 if landed == 2 else 1)
