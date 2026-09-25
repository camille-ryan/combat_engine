"""Druid, level 9: the forms of this tier, and the rows that change a type.

`DamageRolled.dtype` is on the event and mutable, and everything downstream
of the emit reads it back off the event -- so "this attack deals poison
damage instead of its normal type" is a listener that writes the field, and
that is the only way the sentence can be said at all.

The three forms follow `level_1_d.py`: the minor action the header
describes, with the shape's standing benefits hung on the form. `p10854` is
the one printed as a standard action, which is what its header says.

The three summoning rows of this level are absent; see the report.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    FORT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WIS,
    Attack,
    Cast,
    CloseBurst,
    DamageRolled,
    DamageType,
    Defences,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    UpTo,
    When,
    get,
    power,
)
from combat_engine.engine.query import adjacent

from .forms import (
    aura_hold,
    beast_row,
    burns_at_end,
    ends_with,
    in_beast_form,
    rough_aura,
    take_beast_form,
)

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]
BEAST_FORM = "you must be in beast form"

#: The five `p12327` offers.
_ELEMENTS = (
    DamageType.ACID, DamageType.COLD, DamageType.FIRE,
    DamageType.LIGHTNING, DamageType.THUNDER,
)


@power(
    "p10372",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.MELEE, Keyword.POISON],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p10372(c: Cast) -> None:
    """"You can choose" is asked once per damage roll rather than settled
    when the row was used, because the choice is per attack and the answer
    can differ between two swings in the same round.

    A beast form attack that already deals poison is not retyped; it is
    deepened, which is the other half of the printed sentence.
    """
    if c.strike():
        c.damage("1d10", c.wis_mod)
        c.ongoing(5, DamageType.POISON)
    else:
        c.half_damage("1d10", c.wis_mod)
    me = c.me

    def retype(ev: DamageRolled) -> None:
        if ev.source != me or not in_beast_form(c.world, me):
            return
        if not beast_row({"power": ev.detail}):
            return
        if ev.dtype is DamageType.POISON:
            ev.amount += max(0, c.con_mod)
        elif c.may("make it poison", who=me):
            ev.dtype = DamageType.POISON

    c.watch(DamageRolled, retype, until=When.ENCOUNTER, on=me, label=f"{c.ref} venom")


@power(
    "p10850",
    level=9,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_IMPLEMENT,
)
def p10850(c: Cast) -> None:
    """The Stealth half is a check; the speed is real."""
    shape = take_beast_form(c)
    ends_with(
        c, shape, c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER, kind="power")
    )


@power(
    "p10852",
    level=9,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL_IMPLEMENT,
)
def p10852(c: Cast) -> None:
    """"You must land at the end of each turn" has nothing to read it: the
    board is flat and nothing is ever off the ground, so flight here is a
    way of crossing things rather than a height."""
    take_beast_form(c, modes={"fly": c.speed_of()})
    c.note(f"{c.ref}: the flight must end on the ground each turn, and there is no height here")


@power(
    "p10854",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.POISON],
)
def p10854(c: Cast) -> None:
    """A standard action, which is what its own header prints -- the other
    forms of this class are minor ones."""
    shape = take_beast_form(c, modes={"swim": c.speed_of()})
    ends_with(
        c, shape,
        c.bonus(
            "damage", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("opportunity")),
        ),
    )


@power(
    "p12327",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=FORT),
)
def p12327(c: Cast) -> None:
    """Losing a resistance is written as resistance of the same size going
    the other way: `c.resist` takes a negative, and its own undo puts the
    number back when the hold ends -- which is what "save ends both" wants.

    The retyping half is the same listener `p10372` uses, over the druid's
    own rows rather than over its beast form ones.
    """
    landed = bool(c.strike())
    if landed:
        c.damage("2d8", c.wis_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("2d8", c.wis_mod, dtype=DamageType.PSYCHIC)
    victim = c.target
    if victim is None:
        return
    kind = c.choose(list(_ELEMENTS), f"{c.ref}: which element") or DamageType.FIRE
    defences = c.world.get(victim, Defences)
    standing = defences.resist.get(kind, 0) if defences is not None else 0
    hold = c.vulnerable(5, kind, until=When.SAVE_ENDS, on=victim)
    if standing and hold is not None:
        stripped = c.resist(-standing, kind, until=When.SAVE_ENDS, on=victim)
        if stripped is not None:
            hold.on_end.append(
                lambda: c.world.effects.end(stripped, "the hold ended")
            )
    me = c.me

    def retype(ev: DamageRolled) -> None:
        if ev.source != me or ev.dtype is kind:
            return
        p = get(ev.detail)
        if p is None or p.cls != "druid" or not p.is_attack:
            return
        if c.may("change the element", who=me):
            ev.dtype = kind

    c.watch(DamageRolled, retype, until=When.ENCOUNTER, on=me, label=f"{c.ref} element")


@power(
    "p13525",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[*PRIMAL_WEAPON, Keyword.HEALING],
    attack=Attack(WIS, vs=AC),
)
def p13525(c: Cast) -> None:
    """Three questions at the start of each turn -- is it an ally, is it
    bleeding, is it standing next to me -- and all three are asked then
    rather than when the row was used, because all three change."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    if not c.first:
        return
    me = c.me

    def dawn(ev: TurnStart) -> None:
        who = ev.actor
        if ev.ghost or who == me or who not in c.allies():
            return
        if c.bloodied(who) and adjacent(c.world, who, me):
            c.heal(max(1, c.con_mod), on=who)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} mends")


@power(
    "p13526",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_WEAPON, Keyword.CLOSE],
    attack=Attack(WIS, vs=AC),
)
def p13526(c: Cast) -> None:
    """Difficult terrain is a property of the square rather than of who is
    on it, so the aura's going is given a name and the druid's own side is
    excused from that name -- see `forms.rough_aura`."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    if not c.first:
        return
    foes = set(c.enemies())
    rough_aura(c, 1)
    aura_hold(
        c, 1,
        lambda who: who in foes,
        lambda who: c.grants_advantage(on=who, to="allies", until=When.ENCOUNTER),
    )


@power(
    "p13527",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_WEAPON, Keyword.CLOSE, Keyword.COLD],
    attack=Attack(WIS, vs=AC),
)
def p13527(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.COLD)
    else:
        c.half_damage(c.w(2), c.wis_mod, dtype=DamageType.COLD)
    if not c.first:
        return
    friends = {c.me, *c.allies()}

    def shelter(who: int) -> Any:
        c.ignores_difficult(on=who, until=When.ENCOUNTER)
        return c.bonus("save", 2, on=who, until=When.ENCOUNTER, kind="power")

    aura_hold(c, 1, lambda who: who in friends, shelter)


@power(
    "p16122",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CLOSE, Keyword.FIRE],
    attack=Attack(WIS, vs=REF),
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p16122(c: Cast) -> None:
    """Growing the aura is a minor action of its own, which no row in this
    engine can offer from inside another row: there is no second door on a
    power. The aura, its bite and its dismissal clock are all real."""
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("2d8", c.wis_mod, dtype=DamageType.FIRE)
    if not c.first:
        return
    ring = c.aura(1, label=c.ref, until=When.ENCOUNTER)
    foes = set(c.enemies())
    burns_at_end(c, ring, c.wis_mod, DamageType.FIRE, ok=lambda who: who in foes)
    c.note(f"{c.ref}: a minor action each round would widen the aura, and there is no door for one")
