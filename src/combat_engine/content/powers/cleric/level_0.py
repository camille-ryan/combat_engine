"""Cleric, level 0: the class features and the Channel Divinity rows.

Two printed sentences recur here and neither has a header field.

**"You can use only one channel divinity power per encounter"** is a budget
shared across a *set* of rows. `uses` and `once_per_round` are per row, and
`group` is a string nothing spends against, so the limit is dropped rather
than half-declared. Named in the report.

**"One undead creature"** is a filter on creature type, and the targeting
layer picks by side. Those rows ask `c.is_kind` in the body and leave a
living creature alone, which is the printed rule and looks like silence on
a board with nothing undead in it.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    DAILY,
    EACH_ALLY,
    EACH_CREATURE,
    ENCOUNTER,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    STANDARD,
    STR,
    WILL,
    WIS,
    Attack,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Hit,
    Keyword,
    Melee,
    When,
    get,
    power,
)

DIVINE_WEAPON_RADIANT = [Keyword.DIVINE, Keyword.WEAPON, Keyword.RADIANT]
DIVINE_IMPLEMENT_RADIANT = [Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT]
DIVINE = [Keyword.DIVINE]

#: The seven types "resist 10 to one of the following" offers.
WARDS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.POISON,
    DamageType.THUNDER,
)


def _weapon_dice(c: Cast) -> int:
    """"2[W] ... Level 11: 3[W] ... Level 21: 4[W]"."""
    return 4 if c.level >= 21 else 3 if c.level >= 11 else 2


def _melee_weapon(ref: str) -> bool:
    """Was that a melee attack made with a weapon? Read off the row.

    Most melee rows carry no melee *keyword*, so the reach is the authority
    and only the Weapon keyword is asked for directly.
    """
    p = get(ref or "")
    if p is None or p.reach is None:
        return False
    return p.reach.kind == "melee" and Keyword.WEAPON in p.keywords


def _fresh_roll(c: Cast, ev: Any) -> None:
    """Roll the die again and keep the new number, better or worse."""
    result = getattr(ev, "result", None)
    if result is None:
        return
    fresh = c.world.rng.d20().total
    result.total += fresh - result.natural
    result.natural = fresh


@power(
    "p12601",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON_RADIANT,
    attack=Attack(WIS, vs=WILL),
)
def p12601(c: Cast) -> None:
    if not c.is_kind("undead"):
        return
    dice = c.w(_weapon_dice(c))
    if c.strike():
        c.damage(dice, c.wis_mod, dtype=DamageType.RADIANT)
        c.push(3 + c.con_mod)
        c.immobilized(until=When.EONT)
    else:
        c.half_damage(dice, c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p12608",
    level=0,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=DIVINE,
)
def p12608(c: Cast) -> None:
    """A saving throw per save-ends effect, then the petrification clause.

    The disease half is dropped: disease has no stage track in the engine,
    so "improve the disease by 2 stages" has nothing to move. Petrification
    does exist as a condition, and "loses any remaining healing surges" is
    `c.spend_surge` until there are none -- capped, because the method
    reports failure rather than counting.
    """
    who = c.target
    if who is None:
        return
    holds = [e for e in c.world.effects.of(who) if e.when is When.SAVE_ENDS]
    for _ in holds:
        c.save(bonus=5)

    stone = [e for e in c.world.effects.of(who) if Condition.PETRIFIED in e.conditions]
    if not stone:
        return
    for effect in stone:
        c.world.effects.end(effect, c.ref)
    for _ in range(20):
        if not c.spend_surge():
            break


@power(
    "p12614",
    level=0,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
    requires_text="must be used at the end of an extended rest",
    out_of_combat=True,
)
def p12614(c: Cast) -> None:
    """Raising the dead happens between fights, on a creature the encounter
    no longer holds, and the lingering -1 is measured in milestones. None of
    it is a combat effect."""
    c.note(f"{c.ref}: the dead are restored, at -1 until three milestones")


@power(
    "p12638",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_ALLY,
    keywords=DIVINE,
)
def p12638(c: Cast) -> None:
    """Extra damage of a named type, so it is dealt rather than added as a
    modifier: `c.bonus("damage", ...)` carries no `DamageType` and the
    printed line is lightning.
    """
    who = c.target
    if who is None:
        return
    extra = 8 if c.level >= 21 else 6 if c.level >= 11 else 4

    def jolt(ev: Hit) -> None:
        if ev.attacker != who or not _melee_weapon(ev.power):
            return
        c.flat(extra, dtype=DamageType.LIGHTNING, on=ev.target)

    c.watch(Hit, jolt, until=When.EONT, on=who, once=True, label=c.ref)


@power(
    "p14292",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=ANY_CREATURE,
    keywords=DIVINE,
)
def p14292(c: Cast) -> None:
    """`AttackRolled` rather than `Miss`: by the time a miss is announced the
    result has been read and a new die changes nothing. Here the engine
    re-reads `result.natural` afterwards, so the reroll can turn the attack
    into a hit -- which is the whole of the printed line.
    """
    who = c.target
    if who is None:
        return

    def again(ev: AttackRolled) -> None:
        if ev.attacker != who or ev.natural == 20 or ev.total >= ev.defence:
            return
        _fresh_roll(c, ev)

    c.watch(AttackRolled, again, until=When.EONT, on=who, once=True, label=c.ref)


@power(
    "p14293",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON_RADIANT,
    attack=Attack(STR, vs=AC),
)
def p14293(c: Cast) -> None:
    """The secondary attack is a No Action burst off the back of the primary,
    so it is rolled here rather than declared: one printed id, one row.
    """
    if not c.is_kind("undead"):
        return
    victim = c.target
    dice = c.w(_weapon_dice(c))
    if c.strike():
        c.damage(dice, c.str_mod, dtype=DamageType.RADIANT)
        c.immobilized(until=When.EONT)
    else:
        c.half_damage(dice, c.str_mod, dtype=DamageType.RADIANT)

    for foe in c.within(3, side="enemy"):
        if foe == victim or not c.is_kind("undead", on=foe):
            continue
        if c.attack(c.str_, WILL, on=foe):
            c.damage(0, c.cha_mod, dtype=DamageType.RADIANT, on=foe)
            c.push(3 + c.cha_mod, on=foe)


@power(
    "p16415",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=ONE_ALLY,
    keywords=[Keyword.DIVINE, Keyword.SHADOW, Keyword.PSYCHIC],
)
def p16415(c: Cast) -> None:
    c.flat(5, dtype=DamageType.PSYCHIC)
    c.save(bonus=5)


@power(
    "p5981",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_CREATURE,
    keywords=DIVINE_IMPLEMENT_RADIANT,
    attack=Attack(WIS, vs=WILL),
)
def p5981(c: Cast) -> None:
    """Targets every creature in the burst so that the Effect line reaches
    the allies, and the attack half is gated on the dragon keyword -- the
    printed Target. An allied dragon is attacked, which is what it says.
    """
    if c.first:
        amount = 15 if c.level >= 21 else 10
        for friend in c.within(5, side="ally"):
            ward = c.choose(list(WARDS), "which element to ward against")
            c.resist(amount, ward, on=friend, until=When.EONT)

    if not c.is_kind("dragon"):
        return
    dice = "3d10" if c.level >= 21 else "2d10"
    if c.strike():
        c.damage(dice, c.wis_mod, dtype=DamageType.RADIANT)
        c.immobilized(until=When.EONT)
    else:
        c.half_damage(dice, c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p7885",
    level=0,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
)
def p7885(c: Cast) -> None:
    if c.first:
        c.weakened(on=c.me, until=When.EONT)
    if c.bloodied() and c.may("spend a healing surge"):
        c.surge()
