"""Battlemind, level 2."""

from __future__ import annotations

from combat_engine.content.powers.augment import spent_on
from combat_engine.engine import (
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    PERSONAL,
    REACTION,
    SELF,
    Cast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Ranged,
    Trigger,
    When,
    World,
    both,
    get,
    hits_me,
    power,
)

from . import PSIONIC, bloodied


def _close_or_area(world: World, me: int, ev: Hit) -> bool:
    """"A close or an area attack" -- neither `by_melee` nor `by_ranged` says
    it, since each of them straddles the line."""
    p = get(getattr(ev, "power", ""))
    if p is None:
        return False
    return p.reach_of(getattr(ev, "branch", 0)).kind in (
        "close_burst",
        "close_blast",
        "area_burst",
    )


@power(
    "p10443",
    level=2,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=PSIONIC,
)
def p10443(c: Cast) -> None:
    c.mark(until=When.EONT)


@power(
    "p11162",
    level=2,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p11162(c: Cast) -> None:
    c.temp_hp(5 + c.cha_mod, on=c.me)


@power(
    "p12421",
    level=2,
    cls="battlemind",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.FORCE],
    requires=bloodied,
    requires_text="must be bloodied",
)
def p12421(c: Cast) -> None:
    """Rolled on each hit rather than stored as a flat `c.bonus`, because the
    extra damage is force and a modifier carries no damage type.

    "Unaugmented" is a real exclusion now that the augment clauses are
    written: `augment.spent_on` is what the use resolving right now paid,
    where `PowerPoints.augmented` is the encounter's running total and would
    bar the row for the rest of the fight after one augmented swing."""

    def extra(ev: Hit) -> None:
        p = get(ev.power)
        if ev.attacker != c.me or p is None or Keyword.PSIONIC not in p.keywords:
            return
        if spent_on(c.me, ev.power):
            return
        c.flat(c.roll("1d6"), dtype=DamageType.FORCE, on=ev.target)

    c.watch(Hit, extra, until=When.EONT, on=c.me)


@power(
    "p13033",
    level=2,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(5),
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.TELEPORTATION],
)
def p13033(c: Cast) -> None:
    """"One target" and "the other" are a choice; the ally is slid and the
    battlemind takes the teleport, which is the useful half of it."""
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    if mates:
        mate = c.choose(mates, "who comes along")
        if mate is not None:
            c.slide(1, on=mate)
    c.teleport(3)


@power(
    "p13034",
    level=2,
    cls="battlemind",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
    trigger="a close or an area attack hits you",
    on=Trigger(Hit, both(hits_me, _close_or_area), "a close or an area attack hits you"),
)
def p13034(c: Cast) -> None:
    """The conditional half damage is dropped: nothing on `Cast` asks whether
    a square is still inside the attack's area, and a reaction cannot reach
    the damage roll anyway."""
    c.shift(1)


@power(
    "p13036",
    level=2,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p13036(c: Cast) -> None:
    c.resist(3, until=When.ENCOUNTER)


@power(
    "p13037",
    level=2,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.STANCE],
    requires=bloodied,
    requires_text="must be bloodied",
)
def p13037(c: Cast) -> None:
    """The stance's own attack is `p13037b`, declared on its own now that the
    second printed block has an id; what stays here is the stance's standing
    clause, which flattens whoever the opportunity attack lands on."""
    held = c.stance()

    def flatten(ev: Hit) -> None:
        if ev.attacker == c.me and getattr(ev, "opportunity", False):
            c.prone(on=ev.target)

    held.subs.append(c.world.bus.on(Hit, flatten, owner=c.me))


@power(
    "p2625",
    level=2,
    cls="battlemind",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=PSIONIC,
)
def p2625(c: Cast) -> None:
    """Walking on water is fiction the grid has no opinion about; the
    difficult-terrain half and the 3 squares are the mechanical line."""
    c.ignores_difficult(until=When.EOT)
    c.move(3)
