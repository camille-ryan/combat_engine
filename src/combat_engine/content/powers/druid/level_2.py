"""Druid, level 2: the utilities.

Every printed Trigger here is declared with `on=` rather than quoted --
prose alone is never read -- except `p12326`, whose trigger is making a
skill check. There are none, so no predicate could ever be true, and the row
is declared inert instead of carrying a trigger that cannot fire.

**A benefit lasting "until the end of his or her next extended rest" has no
clock.** `When.ENCOUNTER` is the longest this engine holds, so the three
rows printing it say so and use it. Their check bonuses are checks.

Two rows are absent, both for the same reason: they extend wild shape --
"you can use wild shape to assume the form of a Tiny beast" -- and wild
shape is not a row in this batch, so there is nothing to extend. See the
report.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    Ability,
    AreaBurst,
    Cast,
    CloseBurst,
    DamageRolled,
    DamageType,
    Event,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    OpportunityWindow,
    Ranged,
    Trigger,
    TurnEnd,
    When,
    World,
    both,
    by_melee,
    get,
    hits_me,
    power,
    spread,
)
from combat_engine.engine.zones import Zone

from .forms import current_form, ends_with, in_beast_form, out_of_beast_form, take_beast_form

PRIMAL = [Keyword.PRIMAL]
BEAST_FORM = "you must be in beast form"

#: The four the elemental shield answers.
_ELEMENTS = (
    DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING, DamageType.THUNDER,
)


def _elemental_damage(world: World, me: int, ev: Event) -> bool:
    """"You take cold, fire, lightning, or thunder damage."

    Declared on `DamageRolled`, which is the window an interrupt gets: the
    number is known and the resistances are read *after* it, so resist 5
    granted here still applies to the blow that triggered the row.
    """
    return getattr(ev, "target", None) == me and getattr(ev, "dtype", None) in _ELEMENTS


def _provoked_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", None) == me


def _strength_damage(ctx: dict[str, Any]) -> bool:
    """"Damage rolls that include the target's Strength modifier."

    Read off the attack line of whichever row is rolling: a row that attacks
    with Strength is a row whose damage adds that modifier, and nothing else
    on the damage context says so.
    """
    p = get(ctx.get("power", "") or "")
    line = p.attack if p is not None else None
    return line is not None and line.ability is Ability.STR


@power(
    "p12326",
    level=2,
    cls="druid",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p12326(c: Cast) -> None:
    """No `on=`: the printed trigger is making a skill check, the engine
    rolls none, and a declared trigger that can never be true is worse than
    none at all."""
    c.note(f"{c.ref}: one Arcana, Dungeoneering or Religion check rolled as Nature")


@power(
    "p13513",
    level=2,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p13513(c: Cast) -> None:
    """The damage bonus is the only half with a board to act on; the
    Athletics and carrying-capacity halves are checks."""
    c.bonus(
        "damage", 2, until=When.ENCOUNTER, kind="power", when=_strength_damage
    )
    c.note(f"{c.ref}: +2 to Athletics and Strength checks, and four points of carrying")


@power(
    "p13514",
    level=2,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p13514(c: Cast) -> None:
    """Initiative is rolled from `Initiative.bonus` and not from the modifier
    table, so a +2 to it has nothing to write to that anything would read --
    and it is rolled once, before this row could ever be used. The Reflex
    bonus is real."""
    c.bonus(REF, 1, until=When.ENCOUNTER, kind="power")
    c.note(f"{c.ref}: +2 to initiative and to Dexterity checks")


@power(
    "p13515",
    level=2,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p13515(c: Cast) -> None:
    """A surge handed over rather than spent. Nothing in `Cast` grants one --
    `c.surge` spends one and heals for it, `c.spend_surge` spends one for
    nothing -- so the pool is written to directly."""
    who = c.target
    if who is None:
        return
    health = c.world.get(who, Health)
    if health is not None:
        health.surges += 1
    c.bonus(FORT, 1, until=When.ENCOUNTER, kind="power")
    c.note(f"{c.ref}: +2 to Endurance and Constitution checks")


@power(
    "p14503",
    level=2,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.POLYMORPH],
)
def p14503(c: Cast) -> None:
    """A polymorph and not a beast form: it carries the Polymorph keyword,
    not the other one, so it wears its own label and the beast form rows stay
    shut while it is on.

    Ending it is a free action, which is what `revert` names. Gear becoming
    part of the form has nothing to read it.
    """
    shape = c.form(until=When.ENCOUNTER, revert=FREE, label=c.ref)
    ends_with(
        c, shape,
        c.bonus("speed", 4, on=c.me, until=When.ENCOUNTER, kind="untyped"),
        c.cannot_attack(on=c.me, until=When.ENCOUNTER),
    )


@power(
    "p14504",
    level=2,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    keywords=[*PRIMAL, Keyword.HEALING],
)
def p14504(c: Cast) -> None:
    """`c.save` asks the caster unless told otherwise; `c.may` asks the
    target. Both are the printed "the target can", so both name who."""
    who = c.target
    if who is None:
        return
    if c.may("make a saving throw", who=who):
        c.save(on=who)
    if c.may("spend a healing surge", who=who):
        c.surge(on=who)


@power(
    "p16119",
    level=2,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p16119(c: Cast) -> None:
    """The aura ends with the form as well as on its clock, which is why the
    hold is tied to the shape. Partial concealment has nothing to read it.
    """
    ring = c.aura(1, label=c.ref, until=When.EONT)
    foes = set(c.enemies())

    def dusk(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in foes:
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.blinded(on=ev.actor, until=When.EONT)

    watching = c.watch(TurnEnd, dusk, until=When.EONT, on=c.me, label=f"{c.ref} glare")
    held = c.world.get(ring, Zone)
    ends_with(
        c, current_form(c),
        held.effect if held is not None else None,
        watching,
    )
    c.note(f"{c.ref}: partial concealment, and there is none here")


@power(
    "p2724",
    level=2,
    cls="druid",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=in_beast_form,
    requires_text=BEAST_FORM,
)
def p2724(c: Cast) -> None:
    """"While you are in beast form" is a gate on the modifier rather than a
    shorter duration: the printed line runs to the end of the encounter and
    comes and goes as the druid changes shape."""
    me = c.me
    c.bonus(
        "speed", c.dex_mod, on=me, until=When.ENCOUNTER, kind="power",
        when=lambda ctx: in_beast_form(c.world, me),
    )


@power(
    "p2726",
    level=2,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=SELF,
    keywords=[*PRIMAL, Keyword.ZONE],
)
def p2726(c: Cast) -> None:
    """The sustain has a payout as well as a clock -- the zone grows -- and
    without `c.on_sustain` that half of the printed line goes nowhere.

    The obscuring itself is concealment, which nothing here reads.
    """
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    held = c.world.get(zone, Zone)
    if held is None:
        return
    grown = [1]

    def spread_out() -> None:
        if grown[0] >= 5:
            return
        grown[0] += 1
        held.squares = frozenset(spread(held.squares, 1))
        c.world.zones.refresh()

    c.on_sustain(held.effect, spread_out)
    c.note(f"{c.ref}: the zone is lightly obscured, and there is no concealment here")


@power(
    "p5045",
    level=2,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p5045(c: Cast) -> None:
    c.bonus(AC, max(1, c.con_mod), until=When.EONT, kind="power")


@power(
    "p9644",
    level=2,
    cls="druid",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="an enemy hits you while you aren't in beast form",
    on=Trigger(Hit, when=hits_me, text="an enemy hits you"),
    requires=out_of_beast_form,
    requires_text="you must not be in beast form",
)
def p9644(c: Cast) -> None:
    """The second half of the printed trigger is a Requirement on the caster
    rather than a clause on the event: `requires` is asked of whoever is
    being offered the row, which is exactly who "you" is."""
    take_beast_form(c)
    c.shift(1)
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.grants_advantage(on=foe, to=c.me, until=When.EONT)


@power(
    "p9645",
    level=2,
    cls="druid",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=PRIMAL,
    trigger="you take cold, fire, lightning, or thunder damage",
    on=Trigger(
        DamageRolled,
        when=_elemental_damage,
        text="you take cold, fire, lightning, or thunder damage",
    ),
)
def p9645(c: Cast) -> None:
    """"The triggering damage type" is read off the event rather than chosen,
    and the interrupt window is early enough for the resistance to count
    against the blow that opened it."""
    dtype = getattr(c.trigger, "dtype", None)
    if dtype is None or c.target is None:
        return
    c.resist(5, dtype, until=When.EONT, on=c.target)


@power(
    "p9646",
    level=2,
    cls="druid",
    usage=ENCOUNTER,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="an enemy provokes an opportunity attack from you",
    on=Trigger(
        OpportunityWindow,
        when=_provoked_me,
        text="an enemy provokes an opportunity attack from you",
    ),
    requires=out_of_beast_form,
    requires_text="you must not be in beast form",
)
def p9646(c: Cast) -> None:
    """The shape first, then the swing -- in that order, because the swing is
    made in beast form and a beast's basic attack is not a mace."""
    take_beast_form(c)
    foe = getattr(c.trigger, "provoker", None)
    if foe is not None:
        c.basic(on=foe)


@power(
    "p9647",
    level=2,
    cls="druid",
    usage=ENCOUNTER,
    action=MINOR,
    reach=AreaBurst(2, within=10),
    target=SELF,
    keywords=[*PRIMAL, Keyword.ZONE],
)
def p9647(c: Cast) -> None:
    """Heavily obscured is a wall you cannot see through, which `blocks_sight`
    is exactly. The Stealth bonus inside it is a check."""
    area = c.area()
    if not area:
        return
    c.zone(area, label=c.ref, until=When.EONT, blocks_sight=True)
    c.note(f"{c.ref}: +5 to Stealth for you and your allies inside it")


@power(
    "p9648",
    level=2,
    cls="druid",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    trigger="you are hit by a melee attack",
    on=Trigger(
        Hit, when=both(hits_me, by_melee), text="you are hit by a melee attack"
    ),
)
def p9648(c: Cast) -> None:
    """Declared on the hit rather than on the roll, because the printed
    trigger is being hit -- but the defences it raises are what may turn the
    blow aside, so they are laid with `once=True`, which for a defence is
    spent when the blow lands or misses rather than when it was announced.

    "If the triggering attack misses you" cannot be answered here: the
    outcome is recomputed after this window closes. The slide therefore
    hangs on the `Miss` that would follow.
    """
    foe = getattr(c.trigger, "attacker", None)
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, on=c.me, until=When.EONT, kind="power")
    if foe is None:
        return
    me = c.me

    def fumbled(ev: Miss) -> None:
        if ev.attacker == foe and ev.target == me:
            c.slide(2, on=foe)

    c.watch(Miss, fumbled, until=When.EONT, on=me, once=True, label=c.ref)
