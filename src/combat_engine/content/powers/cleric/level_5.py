"""Cleric, level 5: daily attacks.

Two of the four leave something behind that has to be kept alive -- a
square the weapon stands in, a ring of light on the floor -- so both are
`When.SUSTAIN` with a minor action on them, and the payout half of the
printed Sustain line goes through `c.on_sustain`.

One prints "the target cannot attack", which is neither `c.forbid` (one
named row) nor `c.no_basic` (what a row is used *as*) but `c.cannot_attack`,
and it refuses at the declaration so nothing is rolled and no rider fires.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    DAILY,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    STANDARD,
    STR,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    Mod,
    Ranged,
    Relation,
    TurnStart,
    When,
    ZoneEntered,
    get,
    power,
)
from combat_engine.engine.events import ZoneExited
from combat_engine.engine.zones import Zone


def _weapon_row(ref: str) -> bool:
    """Was that attack a weapon attack? Read off the row that made it."""
    row = get(ref) if ref else None
    return row is not None and Keyword.WEAPON in row.keywords


@power(
    "p1406",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=[Keyword.DIVINE],
)
def p1406(c: Cast) -> None:
    """"One held weapon" -- and the engine has no weapon to hold.

    A weapon is not an entity, so the row is aimed at whoever is holding it
    and the blessing rides on that creature's weapon attacks instead. The
    difference only shows if the wielder swaps weapons mid-fight, which
    nothing in the model does.

    The penalty is applied with the *wielder* as its source, because the
    printed duration is measured off the wielder's next turn and a duration
    is clocked by the effect's source -- the cleric is usually somebody
    else.
    """
    wielder = c.target
    if wielder is None:
        return
    mine = {c.me, *c.allies()}

    def blessed(ev: Hit) -> None:
        if ev.attacker != wielder or ev.target in mine or not _weapon_row(ev.power):
            return
        # A critical maxes a weapon's extra dice, which is why this is rolled
        # by hand: `c.damage` reads the cleric's own last attack, not this one.
        c.flat(6 if ev.critical else c.roll("1d6"), dtype=DamageType.RADIANT, on=ev.target)
        c.world.effects.apply(
            ev.target,
            wielder,
            When.EONT,
            label=f"{c.ref} AC-2",
            mods=[(ev.target, Mod(what=AC.value, value=-2, kind="untyped", label=c.ref))],
        )

    c.watch(Hit, blessed, until=When.ENCOUNTER, on=wielder, label=c.ref)


@power(
    "p475",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CONJURATION, Keyword.DIVINE, Keyword.IMPLEMENT],
    attack=Attack(WIS, vs=AC),
)
def p475(c: Cast) -> None:
    """The weapon stands in a square somebody else is already standing in.

    So it is a one-square zone rather than a `c.conjure`: a conjuration
    takes its square on the grid, and placing one where the target stands
    overwrites that creature's occupancy. Nothing else the printed line says
    needs an entity -- the attack is repeated by the cleric, and "any enemy
    in the weapon's square" is what the zone is for.

    Combat advantage is held per enemy standing there, taken away when it
    walks out, and it is granted to the allies only: the printed line does
    not name the cleric.
    """
    if c.strike():
        c.damage("1d10", c.wis_mod)
    if not c.first:
        return

    where = c.there
    zone = c.zone({where}, until=When.SUSTAIN, sustain=MINOR)
    held = c.world.get(zone, Zone)
    friends = c.allies()
    open_to: dict[int, Effect] = {}

    def expose(who: int) -> None:
        if who in open_to or who not in c.enemies() or not friends:
            return
        effect = c.world.effects.apply(
            who,
            c.me,
            When.ENCOUNTER,
            label=f"{c.ref} advantage",
            relations=[(Relation.GRANTS_CA_TO, who, a) for a in friends],
        )
        open_to[who] = effect

    def cover(who: int) -> None:
        effect = open_to.pop(who, None)
        if effect is not None:
            c.world.effects.end(effect, "left the weapon's square")

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            expose(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone:
            cover(ev.actor)

    def cleanup() -> None:
        for who in list(open_to):
            cover(who)

    def again() -> None:
        """Sustain Minor: the weapon swings again at whoever is still there."""
        foes = [f for f in c.world.zones.occupants(zone) if f in c.enemies()]
        foe = c.choose(foes, "who the weapon strikes") if foes else None
        if foe is not None and c.strike(on=foe):
            c.damage("1d10", c.wis_mod, on=foe)

    subs = [
        c.world.bus.on(ZoneEntered, entered),
        c.world.bus.on(ZoneExited, exited),
    ]
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)
        held.effect.on_end.append(cleanup)
        c.on_sustain(held.effect, again)
    for who in c.world.zones.occupants(zone):
        expose(who)


@power(
    "p928",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.HEALING, Keyword.RADIANT, Keyword.ZONE],
)
def p928(c: Cast) -> None:
    """Both halves of the zone bite at the start of a turn and nowhere else,
    so this is a `TurnStart` watch rather than `c.hazard`, whose teeth also
    catch whoever walks in.

    The watch is ended with the zone: it outlives it otherwise, the zone
    having its own duration and the watch only a clock.
    """
    zone = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR)
    mine = {c.me, *c.allies()}
    mercy = 1 + c.cha_mod

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.world.zones.occupants(zone):
            return
        if ev.actor in c.enemies():
            c.damage("1d6", c.cha_mod, dtype=DamageType.RADIANT, on=ev.actor)
        elif ev.actor in mine and c.bloodied(on=ev.actor):
            c.heal(mercy, on=ev.actor)

    watching = c.watch(TurnStart, dawn, until=When.ENCOUNTER, label=c.ref)
    held = c.world.get(zone, Zone)
    if held is not None and held.effect is not None:
        held.effect.on_end.append(
            lambda: c.world.effects.end(watching, "the zone ended")
        )


@power(
    "p915",
    level=5,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.DIVINE, Keyword.WEAPON],
    attack=Attack(STR, vs=WILL),
)
def p915(c: Cast) -> None:
    """The miss line is not a lesser version of the hit: it bars the target
    from attacking the cleric alone, and on the cleric's clock rather than
    until it shakes it off."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.cannot_attack(until=When.SAVE_ENDS)
    else:
        c.cannot_attack(against=c.me, until=When.EONT)
