"""Paladin, level 7: encounter attacks.

Two of the four need a word about their header.

`p778` prints its crit range on the attack line and conditions it on the
mark, so the modifier is put on just before the swing and gated to this row
-- `crit_range` is read at the moment of the roll, which is what lets the
condition be asked then rather than fixed now.

`p1300` has no primary attack at all: the primary target is an ally, the
Effect swaps the two of them, and the only attack is the secondary one the
header carries. Its printed range line is "Melee weapon" while its primary
target is an ally a Wisdom modifier away, and one `reach` has to serve both.
It is `Melee(5)` rather than `Ranged(5)`: a `Ranged` reach on a row carrying
`Keyword.WEAPON` demands a ranged weapon of whoever holds it, so a paladin
with a sword could never use the row at all -- and the attack it makes
really is a melee one, which is what decides cover and provoking. The five
is a ceiling for the pool `candidates` offers; the printed Wisdom limit is
enforced in the body.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Event,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Trigger,
    When,
    World,
    both,
    enemy_within,
    get,
    leaves_me_out,
    power,
)

from .marks import burning_mark

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
_DEFENCES = (AC, FORT, REF, WILL)


def _str_or_cha(c: Cast) -> tuple[int, int]:
    """"Strength or Charisma": the better of the two. See `level_1_b.py`."""
    if c.cha_ > c.str_:
        return c.cha_, c.cha_mod
    return c.str_, c.str_mod


@power(
    "p10251",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.COLD],
    attack=Attack(STR, vs=AC),
)
def p10251(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod, dtype=DamageType.COLD)
        c.immobilized()
        burning_mark(c)


@power(
    "p12305",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=REF),
)
def p12305(c: Cast) -> None:
    """The Special line lengthens the range to 10 for a heavy blade, and a
    range is header data with no room for a condition -- the printed five is
    what is declared. See the report.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
        burning_mark(c)


@power(
    "p1244",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(CHA, vs=WILL),
)
def p1244(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.cha_mod)
        c.pull(max(0, c.wis_mod))


@power(
    "p1300",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_OTHER_ALLY,
    keywords=[*DIVINE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=AC),
)
def p1300(c: Cast) -> None:
    """The swap is the Effect line and happens whatever follows it.

    "If an enemy is now within your melee reach" is asked after the two of
    them have moved, which is the whole point of the row: the paladin lands
    where the ally was standing and swings at whatever was pressing it.
    """
    friend = c.target
    if friend is None or c.distance(friend) > max(1, c.wis_mod):
        return
    c.swap(friend)
    pool = sorted(c.within(1, side="enemy"))
    foe = c.choose(pool, "who the blade finds") if pool else None
    if foe is not None and c.strike(on=foe):
        c.damage(c.w(2), c.cha_mod, on=foe)


@power(
    "p1445",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=WILL),
)
def p1445(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.RADIANT)
        c.dazed()


@power(
    "p3254",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p3254(c: Cast) -> None:
    """"If you have used <the other row> during this turn" is read off what
    that row leaves behind: it holds a damage bonus until the start of the
    paladin's next turn, so the hold standing here means it was used this
    turn and nothing else does.
    """
    used = any(e.label.startswith("p1747") for e in c.world.effects.of(c.me))
    if c.strike(plus=c.wis_mod if used else 0):
        c.damage(c.w(2), c.str_mod)


@power(
    "p3256",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p3256(c: Cast) -> None:
    """Every save-ends effect, not the first one found: the printed line is
    "each effect on you that a save can end", and it is the count of the
    ones shaken off that the attack is worth.
    """
    shaken = 0
    for effect in list(c.world.effects.of(c.me)):
        if effect.when is When.SAVE_ENDS and not effect.ended:
            c.world.effects.save(effect)
            shaken += int(effect.ended)
    if c.strike(plus=shaken):
        c.damage(c.w(2), c.str_mod + shaken)


@power(
    "p3699",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(CHA, vs=AC),
)
def p3699(c: Cast) -> None:
    """The Special line -- this row in place of a melee basic attack when
    charging -- has no header field; see the report."""
    if not c.strike():
        return
    c.damage(c.w(3), c.cha_mod, dtype=DamageType.RADIANT)

    def dreadful(ctx: dict) -> bool:
        p = get(ctx.get("power") or "")
        return p is not None and bool(
            {Keyword.FEAR, Keyword.NECROTIC} & set(p.keywords)
        )

    for d in _DEFENCES:
        c.bonus(d, 2, on=c.me, when=dreadful)


@power(
    "p7257",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p7257(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.THUNDER)
        c.penalty("attack", max(0, c.wis_mod))


_MARKED_SWINGS_ELSEWHERE = "an enemy you marked attacks without you among the targets"


def _my_mark_swings_elsewhere(world: World, me: int, ev: Event) -> bool:
    foe = getattr(ev, "attacker", None)
    return foe is not None and world.relations.holds(Relation.MARKED_BY, me, foe)


@power(
    "p7258",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=WILL),
    trigger=_MARKED_SWINGS_ELSEWHERE,
    on=Trigger(
        AttackDeclared,
        when=both(enemy_within(5), leaves_me_out, _my_mark_swings_elsewhere),
        text=_MARKED_SWINGS_ELSEWHERE,
    ),
)
def p7258(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.cha_mod, dtype=DamageType.RADIANT)
        c.blinded()


@power(
    "p7259",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p7259(c: Cast) -> None:
    """"If the attack deals at least 20 damage" is the number that actually
    came off hit points, which is what `c.damage` returns.
    """
    bonus, mod = _str_or_cha(c)
    if not c.attack(bonus, AC):
        return
    dealt = c.damage(c.w(2), mod)
    friends = [a for a in c.within(5, side="ally") if a != c.me]
    if not friends:
        return
    hurt = [a for a in friends if c.wounded(a)]
    who = c.choose(sorted(hurt or friends), "who spends a healing surge")
    if who is not None and c.may("spend a healing surge", who=who):
        c.surge(on=who, bonus=2 * c.wis_mod if dealt >= 20 else 0)


@power(
    "p778",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p778(c: Cast) -> None:
    """The wider crit range is gated to this row's own attack.

    Ungated it would have widened every swing the paladin made for the rest
    of the turn, which is a different card. `c.marked()` is asked before the
    modifier goes on because nothing can change the mark between here and
    the roll.
    """
    if c.marked():
        c.bonus(
            "crit_range", 1, until=When.EOT, on=c.me,
            when=lambda ctx: ctx.get("power") == c.ref,
        )
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.THUNDER)
        c.prone()
