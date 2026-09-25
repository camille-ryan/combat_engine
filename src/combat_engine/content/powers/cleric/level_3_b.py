"""Cleric, level 3: encounter attacks, the rows outside the first book.

Almost every one of these spends its rider on somebody other than the
creature it hits, and the three shapes that takes are worth naming once.

A **bonus a friend carries** -- "each ally gains a bonus to melee damage
rolls" -- is applied once per ally and gated on the damage context, because
a modifier is only ever read off the creature the roll belongs to.

A **rider that waits for somebody else's attack** -- "when any ally hits the
target" -- is a `c.watch` on `Hit` for the printed duration, filtered by the
attacker and by the creature struck. `Hit` and not `AttackDeclared`, except
in `p14276`, whose printed line pays out for the attempt rather than for
landing it.

A **second ending** -- "until an ally misses with a melee attack" -- is a
second watch that ends the first thing, since only one duration can sit on
an effect.

`p14263`'s "cold and radiant" is one packet of two types, which `DamageType`
cannot hold; it is dealt as the first of the two printed, the reading
`paladin/level_3.py` settled. `p14300`'s weapon clause asks for a category
`Gear` does not record; see the report.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    STR,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Effect,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    Ranged,
    Trigger,
    UpTo,
    When,
    World,
    ZoneEntered,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import ConditionEnded, ZoneExited
from combat_engine.engine.query import distance_between
from combat_engine.engine.zones import Zone

DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]
DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


def _melee_row(ref: str) -> bool:
    """Was that swing made with a melee row?

    The damage context carries the power's ref and nothing about its shape,
    so "melee damage rolls" is read back off the registry -- the same move
    `level_3.py` makes for the ranged half of the question.
    """
    row = get(ref) if ref else None
    return row is not None and row.reach_of().kind == "melee"


def _reroll(c: Cast, result: Any) -> None:
    """Roll that attack again and keep the new face.

    `c.reroll_attack` reads the attack off `c.trigger`, which is empty inside
    a watch the row armed for later, so the arithmetic is written out. The
    outcome is recomputed from `natural` and `total` once the roll's window
    closes, which is why writing them is enough.
    """
    fresh = c.world.rng.d20().total
    result.total += fresh - result.natural
    result.natural = fresh
    result.critical = fresh == 20
    result.hit = fresh == 20 or (fresh != 1 and result.total >= result.target_defence)


def _already(c: Cast, who: int, label: str) -> bool:
    """Is this row's once-per-use hold already on that creature?

    A burst's Hit line runs once per target, and a clause it prints about
    *allies* is owed once for the whole power. `c.first` is the wrong latch
    for it -- the first target may be the one that was missed.
    """
    return any(e.label == label and not e.ended for e in c.world.effects.of(who))


@power(
    "p11043",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11043(c: Cast) -> None:
    """Two endings, so the duration the effect table can measure goes on the
    bonuses and the other one is a watch that ends them early."""
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    friends = [a for a in c.within(5, side="ally") if a != c.me]

    def swinging(ctx: dict[str, Any]) -> bool:
        return _melee_row(ctx.get("power") or "")

    held = [
        h
        for h in (
            c.bonus("damage", c.cha_mod, on=a, until=When.EONT, kind="power", when=swinging)
            for a in friends
        )
        if h is not None
    ]
    if not held:
        return

    def fumbled(ev: Miss) -> None:
        if ev.attacker not in friends or not _melee_row(ev.power):
            return
        for one in held:
            if not one.ended:
                c.world.effects.end(one, "an ally missed")

    c.watch(Miss, fumbled, until=When.EONT, on=c.me, label=f"{c.ref} watches")


@power(
    "p12299",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p12299(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.wis_mod + c.cha_mod, dtype=DamageType.PSYCHIC)
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "p12639",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.THUNDER],
    attack=Attack(WIS, vs=AC),
)
def p12639(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.THUNDER)
        c.push(1)
        c.prone()
    for friend in c.within(3, side="ally"):
        if friend != c.me:
            c.slide(2, on=friend)


@power(
    "p12652",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.HEALING],
    attack=Attack(WIS, vs=AC),
)
def p12652(c: Cast) -> None:
    """The pool is offered worst-hurt first, so the answer a headless fight
    takes -- the first one -- is the one worth taking."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    pool = sorted(c.within(5, side="ally"), key=lambda a: (-c.missing(a), a))
    friend = c.choose(pool, "p12652: who spends a surge") if pool else None
    if friend is not None and c.may("spend a healing surge", who=friend):
        c.surge(on=friend)


@power(
    "p13711",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=FORT),
)
def p13711(c: Cast) -> None:
    """Resistance "while in the aura" is a hold per creature, granted on the
    way in and ended on the way out, rather than a gate: `c.resist` writes
    into `Defences` and takes no condition.
    """
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
        c.push(3)
    ring = c.aura(2, label=c.ref, until=When.EONT)
    inside: dict[int, Effect] = {}

    def shelter(who: int) -> None:
        if who in inside or not (who == c.me or who in c.allies()):
            return
        got = c.resist(5, until=When.EONT, on=who)
        if got is not None:
            inside[who] = got

    def walked_in(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            shelter(ev.actor)

    def walked_out(ev: ZoneExited) -> None:
        if ev.zone != ring:
            return
        held = inside.pop(ev.actor, None)
        if held is not None and not held.ended:
            c.world.effects.end(held, "left the aura")

    standing = c.world.get(ring, Zone)
    if standing is not None and standing.effect is not None:
        standing.effect.subs.extend(
            [
                c.world.bus.on(ZoneEntered, walked_in),
                c.world.bus.on(ZoneExited, walked_out),
            ]
        )
    for who in c.world.zones.occupants(ring):
        shelter(who)


_SOMEBODY_DROPS = "a creature within 3 squares of you drops to 0 hit points"


def _drops_near(world: World, me: int, ev: Dropped) -> bool:
    return distance_between(world, me, ev.actor) <= 3


@power(
    "p13944",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=FORT),
    trigger=_SOMEBODY_DROPS,
    on=Trigger(Dropped, when=_drops_near, text=_SOMEBODY_DROPS),
)
def p13944(c: Cast) -> None:
    if c.first:
        for friend in sorted({c.me, *c.in_squares(c.area(), side="ally")}):
            c.bonus("attack", 2, on=friend, until=When.EONT, kind="power")
            c.temp_hp(5, on=friend)
    if c.strike():
        c.damage("1d8", c.wis_mod, dtype=DamageType.PSYCHIC)


@power(
    "p14237",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p14237(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
    foe = c.target
    friends = sorted(a for a in c.within(5, side="ally") if a != c.me)
    friend = c.choose(friends, "p14237: whose next swing is taken again") if friends else None
    if friend is None or foe is None:
        return
    spent = [False]

    def again(ev: AttackRolled) -> None:
        result = getattr(ev, "result", None)
        if spent[0] or ev.attacker != friend or ev.target != foe or result is None:
            return
        if not c.may("take that roll again", who=friend):
            return
        spent[0] = True
        _reroll(c, result)

    c.watch(AttackRolled, again, until=When.EONT, on=friend, label=c.ref)


@power(
    "p14250",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p14250(c: Cast) -> None:
    """A wider crit range belongs to whoever is rolling, so it sits on the
    ally and the gate keeps it to this one creature."""
    if not c.strike():
        return
    c.damage(c.w(1), c.wis_mod)
    foe = c.target
    friends = sorted(c.allies())
    friend = c.choose(friends, "p14250: whose blows tell") if friends else None
    if friend is None or foe is None:
        return
    c.bonus(
        "crit_range", 2, on=friend, until=When.EONT,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power(
    "p14263",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.COLD, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p14263(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.COLD)
    c.slowed(until=When.EONT)


@power(
    "p14276",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p14276(c: Cast) -> None:
    """"Whenever you or an ally attacks the target" pays for the attempt, so
    the watch is on the declaration rather than on the landing."""
    if not c.strike():
        return
    c.damage(c.w(2), c.wis_mod)
    foe = c.target
    ours = {c.me, *c.allies()}

    def steadied(ev: AttackDeclared) -> None:
        if ev.target == foe and ev.attacker in ours:
            c.temp_hp(c.wis_mod, on=ev.attacker)

    c.watch(AttackDeclared, steadied, until=When.EONT, on=c.me, label=c.ref)


@power(
    "p14300",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14300(c: Cast) -> None:
    """The weapon clause asks for a category `Gear` does not record -- no
    weapon carries it, so `c.wielding` answers no to every character there
    is and the extra die is inert until it does. See the report.
    """
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        if c.wielding("simple"):
            c.damage("1d6")
        c.dazed()


@power(
    "p16422",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR],
    attack=Attack(WIS, vs=AC),
)
def p16422(c: Cast) -> None:
    """Getting up is the one ending of prone that `actions.perform` gives a
    reason for, so "whenever it stands up" is a `ConditionEnded` reading
    that reason. The opening is offered to whoever is standing over it.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.wis_mod)
    c.prone()
    foe = c.target

    def stood(ev: ConditionEnded) -> None:
        if ev.target != foe or ev.condition is not Condition.PRONE:
            return
        if ev.why != "stood up":
            return
        for who in c.within(1, of=foe, side="ally"):
            c.provoke(who, on=foe)

    c.watch(ConditionEnded, stood, until=When.EONT, on=c.me, label=c.ref)


@power(
    "p7084",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p7084(c: Cast) -> None:
    if c.strike():
        c.dazed()


@power(
    "p7085",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p7085(c: Cast) -> None:
    """The extra die is rolled rather than dealt through `c.damage`: it is
    not part of the ally's attack, so a critical of theirs does not max it.
    """
    if not c.strike():
        return
    c.damage(c.w(1), c.str_mod, dtype=DamageType.RADIANT)
    foe = c.target
    friends = set(c.allies())

    def flares(ev: Hit) -> None:
        if ev.target == foe and ev.attacker in friends:
            c.flat(c.roll("1d6"), dtype=DamageType.RADIANT, on=foe)

    c.watch(Hit, flares, until=When.SONT, on=c.me, label=c.ref)


@power(
    "p7086",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p7086(c: Cast) -> None:
    """"A -2 penalty to all defences" is four modifiers, one per defence: a
    defence is read on its own and there is no key that means all of them.
    """
    if c.first:
        for friend in sorted(a for a in c.in_squares(c.area(), side="ally") if a != c.me):
            taken = c.choose(
                ["5 temporary hit points", "a saving throw"],
                "p7086: what the ally takes",
            )
            if taken == "a saving throw":
                c.save(on=friend)
            else:
                c.temp_hp(5, on=friend)
    if not c.strike():
        return
    foe = c.target
    for defence in (AC, FORT, REF, WILL):
        c.penalty(defence, 2, on=foe, until=When.EONT)
    friends = set(c.allies())

    def floored(ev: Hit) -> None:
        if ev.target == foe and ev.attacker in friends:
            c.prone(on=foe)

    c.watch(Hit, floored, until=When.EONT, on=c.me, label=f"{c.ref} {foe}")


@power(
    "p7087",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=5),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p7087(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("1d8", c.wis_mod, dtype=DamageType.RADIANT)
    for friend in sorted({c.me, *c.in_squares(c.area(), side="ally")}):
        if not _already(c, friend, f"{c.ref} ac+2"):
            c.bonus(AC, 2, on=friend, until=When.EONT, kind="power")


@power(
    "p7088",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(STR, vs=AC),
)
def p7088(c: Cast) -> None:
    """Who is beside whom is read once, at the swing. The printed line names
    two anchors and the cleric is not one of the beneficiaries.
    """
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
    foe = c.target
    beside = {a for a in c.within(1, side="ally") if a != c.me}
    if foe is not None:
        beside |= {a for a in c.within(1, of=foe, side="ally") if a != c.me}
    for friend in sorted(beside):
        c.resist(c.cha_mod, until=When.EONT, on=friend)


@power(
    "p9983",
    level=3,
    cls="cleric",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p9983(c: Cast) -> None:
    """The second sentence turns on having used a particular other row on
    that ally this turn, and names it rather than giving an id; see the
    report. The first sentence is the whole of what is written here.
    """
    if not c.strike():
        return
    c.damage("1d10", c.wis_mod, dtype=DamageType.RADIANT)
    foe = c.target
    friends = sorted(a for a in c.within(5, side="ally") if a != c.me)
    friend = c.choose(friends, "p9983: whose aim is guided") if friends else None
    if friend is None or foe is None:
        return
    c.bonus(
        "attack", 2, on=friend, until=When.EONT, kind="power",
        when=lambda ctx: ctx.get("target") == foe,
    )
