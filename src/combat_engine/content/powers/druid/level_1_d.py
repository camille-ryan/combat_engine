"""Druid, level 1: the daily attacks, and the three forms.

**The form rows are their first stanza and nothing else.** `p10838`,
`p10840` and `p10842` each print two: a minor action that assumes a shape,
and a standard action attack with "Requirement: the form must be active".
The second is a separate row in the compendium with an id of its own, and
this spec gives one id per block -- so what is written here is the minor
action the header describes, with the shape's standing benefits hung on the
form itself.

**Two rows enchant a weapon.** Their printed Target is an object, which
nothing in the engine is, so they are written as the weapon in the druid's
own hand: a `requires=` on the weapon group, and the rider armed on its own
hits. `p13510` wants an axe, a flail, a blade, a pick or a spear and the
class carries a mace, a crossbow and a staff, so it is correctly unusable.

The three summoning rows of this level are absent; see the report.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    FORT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Gear,
    Hit,
    Keyword,
    Melee,
    MoveEnd,
    Ranged,
    TurnStart,
    UpTo,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.query import squares

from .forms import (
    aura_hold,
    beast_row,
    ends_with,
    in_beast_form,
    rough_aura,
    take_beast_form,
)

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
BEAST_FORM = "you must be in beast form"


def _wielding(*groups: str) -> Callable[[World, int], bool]:
    """A printed Target of "one <weapon>", read as the one in your own hand.

    `c.wielding` asks about the caster and nothing asks about anybody else,
    which is the other half of what this row would need to enchant an ally's
    blade -- see the report.
    """

    def check(world: World, eid: int) -> bool:
        gear = world.get(eid, Gear)
        main = gear.main if gear is not None else None
        return main is not None and main.group in groups

    return check


def _weapon_rider(c: Cast, amount: int, dtype: DamageType, *, prone: bool) -> None:
    """"Once per round when a weapon attack hits with the target, ..."

    Latched per round by hand: `once_per_round` on the header counts uses of
    the row, and this counts hits by the weapon the row enchanted.
    """
    me = c.me
    last: list[int] = []

    def struck(ev: Hit) -> None:
        if ev.attacker != me or last[-1:] == [c.world.round]:
            return
        p = get(ev.power)
        if p is None or Keyword.WEAPON not in p.keywords:
            return
        last.append(c.world.round)
        c.flat(amount, dtype=dtype, on=ev.target)
        if prone:
            c.prone(on=ev.target)

    c.watch(Hit, struck, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p10838",
    level=1,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_IMPLEMENT,
)
def p10838(c: Cast) -> None:
    """The whole of what this shape does on a board is be a shape: its
    Athletics bonus and its running start are checks and jumps, neither of
    which the engine has. The attack it unlocks is a separate row; see the
    module note.
    """
    take_beast_form(c)


@power(
    "p10840",
    level=1,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_IMPLEMENT,
)
def p10840(c: Cast) -> None:
    """"With beast form powers" is read off the gate of whichever row is
    rolling, because `Keyword` has no member for Beast Form."""
    shape = take_beast_form(c)
    ends_with(
        c, shape,
        c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, when=beast_row),
    )


@power(
    "p10842",
    level=1,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_IMPLEMENT,
)
def p10842(c: Cast) -> None:
    """The damage context carries `charge`, which is what makes the rider
    sayable at all -- a gate on a key the context does not hold is silently
    false."""
    c.temp_hp(c.surge_value(), on=c.me)
    shape = take_beast_form(c)
    ends_with(
        c, shape,
        c.bonus(
            "damage", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("charge")),
        ),
    )


@power(
    "p13510",
    level=1,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.FIRE],
    requires=_wielding("axe", "flail", "heavy blade", "light blade", "pick", "spear"),
    requires_text="an axe, a flail, a heavy or light blade, a pick or a spear",
)
def p13510(c: Cast) -> None:
    _weapon_rider(c, 5, DamageType.FIRE, prone=False)


@power(
    "p13511",
    level=1,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.FORCE],
    requires=_wielding("hammer", "mace", "staff"),
    requires_text="a hammer, a mace or a staff",
)
def p13511(c: Cast) -> None:
    _weapon_rider(c, 2, DamageType.FORCE, prone=True)


@power(
    "p13512",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.CLOSE],
    attack=Attack(WIS, vs=AC),
)
def p13512(c: Cast) -> None:
    """"Enemies grant combat advantage while adjacent to you" is an aura 1
    whose occupants carry the hold, which is the arrangement the README asks
    for -- a standing "adjacent to you" clause is an aura and gets no
    mechanism of its own."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    if not c.first:
        return
    foes = set(c.enemies())
    aura_hold(
        c, 1,
        lambda who: who in foes,
        lambda who: c.grants_advantage(on=who, to="allies", until=When.ENCOUNTER),
    )


@power(
    "p16118",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.THUNDER],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p16118(c: Cast) -> None:
    """Printed Beast Form, and *not* gated on being in one: the second half
    of its Effect is what the shape is for, and the row is in the book as a
    daily a druid opens a fight with. It is gated all the same, because the
    keyword is the rule -- see `forms.py`.
    """
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.THUNDER)
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.wis_mod, dtype=DamageType.THUNDER)
    if c.first:
        rough_aura(c, 1)


@power(
    "p2794",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p2794(c: Cast) -> None:
    """The Aftereffect hangs on the hold's `on_end`, so it follows the hold
    going whichever way it goes -- `escalate` is the other door and runs on a
    *failed* save, which is the opposite sentence.

    Slowed and granting combat advantage are one hold, because the printed
    line says "save ends **both**": two holds would be two saving throws.
    """
    landed = bool(c.strike())
    victim = c.target
    if victim is None:
        return
    if not landed:
        c.damage("1d6", c.wis_mod, dtype=DamageType.RADIANT)
        c.grants_advantage(until=When.EONT, to="allies")
        return
    hold = c.condition(Condition.SLOWED, until=When.SAVE_ENDS)
    ca = c.grants_advantage(until=When.SAVE_ENDS, to="allies")
    if hold is None:
        return
    if ca is not None:
        hold.on_end.append(lambda: c.world.effects.end(ca, "the hold ended"))

    def after() -> None:
        c.damage("3d6", c.wis_mod, dtype=DamageType.RADIANT, on=victim)
        c.grants_advantage(on=victim, until=When.EONT, to="allies")

    hold.on_end.append(after)


@power(
    "p4897",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE],
    attack=Attack(WIS, vs=FORT),
)
def p4897(c: Cast) -> None:
    """`on=c.me`: a defence bonus with no `on=` lands on `c.target`, which
    here is whoever the burst caught."""
    if c.strike():
        c.damage("2d10", c.wis_mod)
    else:
        c.half_damage("2d10", c.wis_mod)
    if not c.first:
        return
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, on=c.me, until=When.ENCOUNTER, kind="power")


@power(
    "p5043",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p5043(c: Cast) -> None:
    """"Each enemy in the burst **you can see**" is a target line the engine
    does not filter, so it is asked here."""
    if c.target is None or not c.can_see():
        return
    if c.strike():
        c.damage("1d6", c.wis_mod)
        c.condition(Condition.DAZED, Condition.SLOWED, until=When.SAVE_ENDS)
    else:
        c.half_damage("1d6", c.wis_mod)
        c.slowed()


@power(
    "p5044",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED],
    attack=Attack(WIS, vs=REF),
)
def p5044(c: Cast) -> None:
    """The Effect is owed whether or not the bolt landed, and its two halves
    are one moment: the first move both ends the advantage and fells whoever
    is standing near."""
    if c.strike():
        c.damage("2d10", c.wis_mod)
    victim = c.target
    if victim is None:
        return
    ca = c.grants_advantage(until=When.ENCOUNTER, to="allies")

    def stirred(ev: MoveEnd) -> None:
        if ev.actor != victim:
            return
        if ca is not None and not ca.ended:
            c.world.effects.end(ca, "the target moved")
        for foe in sorted(c.within(5, of=victim, side="enemy")):
            c.prone(on=foe)

    c.watch(MoveEnd, stirred, until=When.ENCOUNTER, on=c.me, once=True, label=c.ref)


@power(
    "p5506",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.FIRE, Keyword.HEALING],
    attack=Attack(WIS, vs=REF),
)
def p5506(c: Cast) -> None:
    """Two payouts on one burn, and only one of them is owed.

    Dropping ends the hold, so the Aftereffect on `on_end` would otherwise
    pay out as well as the larger heal the dropping earns. The flag is what
    keeps the printed line from being worth both.
    """
    if not c.strike():
        c.half_damage("1d6", c.wis_mod, dtype=DamageType.FIRE)
        return
    c.damage("1d6", c.wis_mod, dtype=DamageType.FIRE)
    victim = c.target
    burn = c.ongoing(5, DamageType.FIRE)
    if victim is None or burn is None:
        return
    paid: list[bool] = []

    def mend(amount: int) -> None:
        pool = sorted(c.within(5, of=victim))
        who = c.choose(pool, f"{c.ref}: who the fire mends") if pool else None
        if who is not None:
            c.heal(amount, on=who)

    def felled(ev: Dropped) -> None:
        if ev.actor == victim and not paid:
            paid.append(True)
            mend(5 + c.con_mod)

    burn.subs.append(c.world.bus.on(Dropped, felled, owner=c.me))
    burn.on_end.append(lambda: None if paid else mend(max(1, c.con_mod)))


@power(
    "p9641",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.AREA, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p9641(c: Cast) -> None:
    """The zone's rider is "starts its turn there", which is neither half of
    what `c.burns` latches, so it is written out."""
    if c.strike():
        c.damage("2d8", c.wis_mod)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.EONT)
    foes = set(c.enemies())

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in foes:
            return
        if ev.actor in c.world.zones.occupants(zone):
            c.slowed(on=ev.actor, until=When.EOTNT)

    c.watch(TurnStart, dawn, until=When.EONT, on=c.me, label=f"{c.ref} roots")


@power(
    "p9643",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=FORT),
)
def p9643(c: Cast) -> None:
    """The primary rolls Reflex and the secondary Fortitude, so the header
    carries the secondary -- `c.strike` rolls what the header declares and
    only one line fits there. The primary goes through `c.attack` with the
    same bonus, which is the pair the other way round from most rows.

    The secondary burst is centred on each primary target and catches
    whoever is standing in it, the caster included: the printed target is
    "each creature in the bursts".
    """
    victim = c.target
    if victim is None:
        return
    if c.attack(c.wis_, REF, on=victim):
        c.damage("1d10", c.wis_mod, dtype=DamageType.LIGHTNING)
        c.dazed()
    else:
        c.half_damage("1d10", c.wis_mod, dtype=DamageType.LIGHTNING)
    for who in sorted(c.in_squares(spread(squares(c.world, victim), 1))):
        if c.strike(on=who):
            c.prone(on=who)
