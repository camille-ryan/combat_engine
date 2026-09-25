"""Ranger, level 3: the encounter attack powers.

The first four print both attack lines at once, so all four are
`MeleeOrRanged` with `attack_alt` carrying the second line and
`c.attack_mod` in the damage line -- the shape the level 1 file's docstring
sets out. Two of them are the two-attack rows as well: main weapon then
off-hand on the melee branch, two shots from the same bow on the ranged one.

The rows after them are this level's from the later books. Four of those
print a beast companion clause, which this engine has no notion of; in every
case the ranger still swings, so the row is written and the companion's half
is dropped -- see `level_1_b.py`'s docstring.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    STR,
    AreaBurst,
    Attack,
    Cast,
    Cover,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Powers,
    Ranged,
    UpTo,
    When,
    World,
    power,
)
from combat_engine.engine.events import AttackDeclared, ZoneEntered
from combat_engine.engine.query import cover_between, team
from combat_engine.engine.triggers import Trigger

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]

_SOMEONE_ATTACKED = "you or an ally is attacked by a creature"
_ALLY_ATTACKED = "an enemy attacks your ally"


def _ally_attacked(world: World, me: int, ev: AttackDeclared) -> bool:
    """"An enemy attacks your ally" -- your ally, and not you.

    `_me_or_ally_attacked` below answers the wider sentence `p1416` prints;
    this one excludes the ranger, which is what `p10609` says.
    """
    victim = getattr(ev, "target", None)
    attacker = getattr(ev, "attacker", None)
    if victim is None or attacker is None or victim == me:
        return False
    return (
        team(world, victim) is team(world, me)
        and team(world, attacker) is not team(world, me)
    )


def _unexpend(c: Cast) -> None:
    """"This power is not expended." `use` counts the use before the body."""
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.unuse(c.ref)


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons" -- two that are not fired."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _has_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


def _melee_in_hand(world: World, eid: int) -> bool:
    """"You must be wielding a thrown weapon" -- a melee weapon that leaves
    the hand. Nothing on `Weapon` flags one, so the half that can be checked
    is checked; see `level_1_b.py`."""
    gear = world.get(eid, Gear)
    return gear is not None and bool(gear.melee)


def _me_or_ally_attacked(world: World, me: int, ev: AttackDeclared) -> bool:
    """"You or an ally is attacked" -- written out for want of an `either`.

    `targets_me` is half the sentence and `ally_within(n)` is the other half
    but forces a range the printed line does not name, and the combinator
    the module ships is `both`.
    """
    victim = getattr(ev, "target", None)
    if victim is None:
        return False
    return victim == me or team(world, victim) is team(world, me)


@power(
    "p1416",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    trigger=_SOMEONE_ATTACKED,
    on=Trigger(AttackDeclared, when=_me_or_ally_attacked, text=_SOMEONE_ATTACKED),
)
def p1416(c: Cast) -> None:
    """The penalty is spent on the roll this interrupted.

    `once=True` ends it after the first attack roll the target makes, and an
    interrupt resolves before that roll, so the one it lands on is the
    triggering attack.
    """
    if c.strike():
        c.damage(c.w(1), c.attack_mod)
        c.penalty("attack", 3 + c.wis_mod, once=True)


@power(
    "p1521",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=REF),
    attack_alt=Attack(DEX, vs=REF),
)
def p1521(c: Cast) -> None:
    """Printed for the quarry only, and nothing can ask whether one is.

    The quarry lives in a closure inside `cf:ranger-quarry` rather than as
    anything on the creature, so the restriction is dropped and any one
    enemy may be attacked.
    """
    if c.strike():
        c.damage(c.w(2), c.attack_mod)


@power(
    "p855",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p855(c: Cast) -> None:
    """Two attacks over one or two creatures, and a push for each one that lands.

    Both hits on the same creature do not push it twice: the printed line
    replaces the two single squares with one push of 1 + Wisdom, so the
    pushing waits until both swings are done and is done once.
    """
    shots = 2 if (c.first and c.last) else 1
    landed = 0
    for swing in range(shots):
        hand = "off" if (swing and c.branch == 0) else "main"
        if c.strike():
            landed += 1
            c.damage(c.w(1, hand=hand), c.attack_mod)
    if landed == 2:
        c.push(1 + c.wis_mod)
    elif landed:
        c.push(1)


@power(
    "p978",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
    requires=_two_melee,
    requires_alt=_has_ranged,
    requires_text="needs two melee weapons or a ranged weapon",
)
def p978(c: Cast) -> None:
    """The Special line offers the shift after either attack; it is taken after both.

    Stepping between the two swings cannot be offered -- the choice would
    have to be made before the second attack is rolled and nothing asks it
    -- so the shift happens once, when the shooting stops.
    """
    shots = 2 if (c.first and c.last) else 1
    for swing in range(shots):
        hand = "off" if (swing and c.branch == 0) else "main"
        if c.strike():
            c.damage(c.w(1, hand=hand), c.attack_mod)
    if c.last and c.may("shift", who=c.me):
        c.shift(1 + c.wis_mod)


@power(
    "p10609",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    charges=True,
    trigger=_ALLY_ATTACKED,
    on=Trigger(AttackDeclared, when=_ally_attacked, text=_ALLY_ATTACKED),
)
def p10609(c: Cast) -> None:
    """The run and the swing, rather than `c.charge_at`: the printed line
    replaces the charge's melee basic with *this* attack, and `c.charge_at`
    would use the row it is already inside -- which `_IN_FLIGHT` refuses.

    So the swing carries the charge's +1 by hand and not the `charge` flag,
    which means a rider elsewhere reading "when it charges" will not see
    this one. `charges=True` in the header is the other half: without it the
    reach test measures a sword's length before the run.
    """
    victim = c.target
    if victim is not None and not c.adjacent():
        c.run_at(victim)
    if c.strike(plus=1):
        c.damage(c.w(2), c.str_mod)


@power(
    "p10610",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10610(c: Cast) -> None:
    """The Effect is a free melee basic by the beast companion, and is not
    written."""
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.slide(1)
        c.shift(1)


@power(
    "p10611",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p10611(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.slowed()
    c.shift(c.speed_of(c.me))


@power(
    "p10612",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p10612(c: Cast) -> None:
    """`resolve.attack` breaks the attacker's hiding, so staying hidden is
    hiding again afterwards -- the idiom `c.hide` documents. The Stealth
    check is not rolled; having cover is the condition that stands in for
    it, since the engine holds no DCs."""
    victim = c.target
    lurking = victim is not None and c.is_hidden(from_=victim)
    hidden = (
        lurking and cover_between(c.world, c.me, victim, ranged=True) is not Cover.NONE
    )
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    if hidden:
        c.hide(from_=victim)


@power(
    "p10613",
    level=3,
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
def p10613(c: Cast) -> None:
    """The refund is asked of the board -- did the first swing fell it --
    rather than of the damage number, which says nothing about how much was
    left."""
    from combat_engine.engine.query import alive

    ref, victim = c.ref, c.target
    for swing in range(2):
        if not c.strike():
            continue
        c.damage(c.w(1, hand="off" if swing else "main"), c.str_mod)
        if swing or victim is None or alive(c.world, victim):
            continue
        _unexpend(c)
        c.bonus(
            "attack",
            2,
            on=c.me,
            until=When.ENCOUNTER,
            once=True,
            when=lambda ctx: ctx.get("power") == ref,
        )


@power(
    "p10614",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    thrown_by_hand=True,
    requires=_melee_in_hand,
)
def p10614(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2, ranged=False), c.str_mod)
        c.prone()


@power(
    "p10700",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_CREATURE,
    keywords=[*MARTIAL_RANGED, Keyword.AREA, Keyword.ZONE],
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p10700(c: Cast) -> None:
    """A zone and a watch rather than `c.hazard`: the printed line bites on
    entering only, and `c.hazard` bites at the start of a turn spent there
    as well. The once-per-turn latch is kept, as printed."""
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
    if not c.first:
        return
    zone = c.zone(c.area(), until=When.SONT, label=c.ref)
    struck: dict[int, int] = {}

    def sting(ev: ZoneEntered) -> None:
        if ev.zone != zone or struck.get(ev.actor) == c.world.round:
            return
        struck[ev.actor] = c.world.round
        c.flat(5, on=ev.actor)

    c.watch(ZoneEntered, sting, until=When.SONT, on=c.me, label=c.ref)


@power(
    "p2603",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
    requires=_has_ranged,
)
def p2603(c: Cast) -> None:
    """One target buys a fatter damage roll, two cost accuracy."""
    alone = c.first and c.last
    if c.strike(plus=0 if alone else -2):
        c.damage(c.w(1), c.dex_mod + (2 if alone else 0))
        c.slide(1)


@power(
    "p4384",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4384(c: Cast) -> None:
    """Both beast clauses -- the extra damage and the companion's free step
    after the target moves -- are dropped; the quarry half of the Effect is
    written."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    if c.is_quarry():
        c.slowed()


@power(
    "p4385",
    level=3,
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
def p4385(c: Cast) -> None:
    """"You grant combat advantage to all enemies" is the relation once per
    enemy: it names one beneficiary, and `to="allies"` is the caster's own
    side rather than the other one."""
    landed = 0
    for swing in range(2):
        if c.strike():
            landed += 1
            c.damage(c.w(1, hand="off" if swing else "main"), c.str_mod)
    if landed == 2:
        c.prone()
        c.flat(max(0, c.wis_mod))
    elif landed == 0:
        for foe in c.enemies():
            c.grants_advantage(on=c.me, to=foe, until=When.SONT)


@power(
    "p4386",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4386(c: Cast) -> None:
    """The Effect is a free melee basic by the beast companion, and is not
    written."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)


@power(
    "p4387",
    level=3,
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
def p4387(c: Cast) -> None:
    """`once=True` is "for your next melee attack against it" -- spent on
    the first roll rather than lasting the turn. The printed clause narrows
    that to a melee one and the spend cannot be told which."""
    if c.strike():
        c.damage(c.w(1, hand="off"), c.str_mod)
        c.grants_advantage(to=c.me, until=When.EOT, once=True)


@power(
    "p4389",
    level=3,
    cls="ranger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=FORT),
    requires=_has_ranged,
)
def p4389(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.slowed()
        c.penalty("attack", 2)


@power(
    "p9353",
    level=3,
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
def p9353(c: Cast) -> None:
    """The crowd is counted once, before the swinging: a creature dropped by
    the first blow was still adjacent when the power went off."""
    crowd = len(c.within(1, side="enemy"))
    for swing in range(2):
        if c.strike():
            c.damage(c.w(1, hand="off" if swing else "main"), c.str_mod + crowd)
