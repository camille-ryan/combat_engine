"""Cleric, level 2: utility, the rows outside the first book.

Two of them pay for a heal out of the cleric's own hit points. "Damage that
cannot be reduced by any means" has no expression -- resistance and
insubstantiality are both read inside `deal_damage` and neither can be
waived -- so both are dealt as ordinary untyped damage and the clause is in
the report.

`p13923` and `p7083` both name a **dying** ally, and no targeting can reach
one: `query.alive` is false below the dying line and `candidates` filters
every pool by it. So both declare their printed target as a label and pick
the creature by hand -- off the burst for the first, off the triggering
event for the second -- and `p13923` carries the printed "one dying ally" as
a Requirement, which is the only place the machinery will read it.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ANY_CREATURE,
    DAILY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Effect,
    Healed,
    Health,
    Keyword,
    Melee,
    MoveEnd,
    Ranged,
    Relation,
    SavingThrow,
    Target,
    Trigger,
    When,
    World,
    power,
)
from combat_engine.engine.events import SurgeSpent
from combat_engine.engine.query import allies, distance_between, is_, team

DIVINE = [Keyword.DIVINE]
DIVINE_HEALING = [Keyword.DIVINE, Keyword.HEALING]

#: The six the printed line offers, in the order it prints them.
WARDED = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
    DamageType.THUNDER,
)


@power(
    "p11618",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=DIVINE,
)
def p11618(c: Cast) -> None:
    """The cleric's own surge value, paid as damage rather than as a surge:
    nothing leaves the pool, so `c.surge_value` and not `c.surge`."""
    paid = c.surge_value()
    c.flat(paid, on=c.me)
    c.temp_hp(paid * 2)


@power(
    "p12607",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=ONE_ALLY,
    keywords=DIVINE_HEALING,
)
def p12607(c: Cast) -> None:
    if c.may("spend a healing surge"):
        c.surge()
    c.bonus("damage", 4, until=When.EONT, kind="power")


def _dying_ally_near(world: World, eid: int) -> bool:
    """"One dying ally in the burst", as the Requirement it has to become."""
    return any(
        is_(world, a, Condition.DYING) and distance_between(world, eid, a) <= 5
        for a in allies(world, eid)
    )


@power(
    "p13923",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("self", 0, label="One dying ally in the burst"),
    keywords=DIVINE_HEALING,
    requires=_dying_ally_near,
    requires_text="a dying ally within 5 squares",
)
def p13923(c: Cast) -> None:
    """Two surges, then a bargain that ends when the ally is whole again.

    "Grants combat advantage" names nobody, so it is the relation once per
    enemy rather than `c.grants_advantage`, whose `to=` reaches the caster's
    own side. The second ending is a `Healed` watch: no duration measures
    "until restored to full hit points", and the three holds are ended
    together so the bargain cannot be half-paid.
    """
    down = sorted(
        a for a in c.allies() if c.is_(Condition.DYING, on=a) and c.distance(a) <= 5
    )
    friend = c.choose(down, "p13923: who is called back") if down else None
    if friend is None:
        return
    for _ in range(2):
        if not c.may("spend a healing surge", who=friend):
            break
        c.surge(on=friend)

    held: list[Effect | None] = [
        c.bonus("attack", 2, on=friend, until=When.ENCOUNTER, kind="power"),
        c.bonus("damage", 2, on=friend, until=When.ENCOUNTER, kind="power"),
        c.world.effects.apply(
            friend,
            c.me,
            When.ENCOUNTER,
            label=f"{c.ref} exposed",
            relations=[(Relation.GRANTS_CA_TO, friend, foe) for foe in c.enemies()],
        ),
    ]

    def mended(ev: Healed) -> None:
        # `Healed` is announced *before* the hit points go on, so the total
        # is read off the event rather than off `Health`, which still holds
        # what the creature had a moment ago.
        health = c.world.get(friend, Health)
        if ev.target != friend or health is None:
            return
        if ev.hp + ev.amount < health.max_hp:
            return
        for one in list(held):
            if one is not None and not one.ended:
                c.world.effects.end(one, "restored to full")

    held.append(
        c.watch(Healed, mended, until=When.ENCOUNTER, on=friend, label=f"{c.ref} bargain")
    )


@power(
    "p13924",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(1, within=10),
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.ZONE],
)
def p13924(c: Cast) -> None:
    """"Heavily obscured" and "blocks line of sight" are the same field here:
    the engine keeps one grade of obscurity and `blocks_sight` is it."""
    area = c.area()
    if area:
        c.zone(area, label=c.ref, until=When.SUSTAIN, blocks_sight=True, sustain=MINOR)


@power(
    "p3466",
    level=2,
    cls="cleric",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=DIVINE,
    out_of_combat=True,
)
def p3466(c: Cast) -> None:
    c.note(f"p3466: +{c.cha_mod} to the target's next skill check this encounter")


@power(
    "p3467",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=DIVINE,
)
def p3467(c: Cast) -> None:
    which = c.choose([AC, FORT, REF, WILL], "p3467: which defence is guarded")
    if which is not None:
        c.bonus(which, 4, until=When.ENCOUNTER, kind="power")


@power(
    "p7081",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p7081(c: Cast) -> None:
    """The ally's share is handed out as each one stops moving, because that
    is the printed sentence -- ending a move beside the cleric, not standing
    beside it. `SOTNT` is clocked on the ally, which is whose next turn the
    line measures, and an ally that ends two moves in one turn is not warded
    twice: two resistances of a type add, and the printed one is 5.
    """
    kind = c.choose(list(WARDED), "p7081: which damage the ward turns")
    if kind is None:
        return
    me = c.me
    c.resist(5, kind, until=When.ENCOUNTER, on=me)
    warded: dict[int, Effect] = {}

    def arrived(ev: MoveEnd) -> None:
        if ev.actor == me or ev.actor not in c.allies() or not c.adjacent(to=ev.actor):
            return
        standing = warded.get(ev.actor)
        if standing is not None and not standing.ended:
            return
        got = c.resist(5, kind, until=When.SOTNT, on=ev.actor)
        if got is not None:
            warded[ev.actor] = got

    c.watch(MoveEnd, arrived, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p7082",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ANY_CREATURE,
    keywords=DIVINE_HEALING,
)
def p7082(c: Cast) -> None:
    paid = c.surge_value()
    c.flat(paid, on=c.me)
    c.heal(paid * 2)


_DEATH_SAVE_FAILS = "an ally within 20 squares of you fails a death saving throw"


def _ally_fails_a_death_save(world: World, me: int, ev: SavingThrow) -> bool:
    who = ev.actor
    if who == me or ev.against != "death" or ev.saved:
        return False
    if team(world, who) is not team(world, me):
        return False
    return distance_between(world, me, who) <= 20


@power(
    "p7083",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=INTERRUPT,
    reach=Ranged(20),
    target=Target("self", 0, label="The triggering ally"),
    keywords=DIVINE_HEALING,
    trigger=_DEATH_SAVE_FAILS,
    on=Trigger(SavingThrow, when=_ally_fails_a_death_save, text=_DEATH_SAVE_FAILS),
)
def p7083(c: Cast) -> None:
    """`SavingThrow` is announced before it is acted on and `saved` is read
    back afterwards, so "succeeds on the death saving throw" is that field
    and not a reroll -- and an interrupt runs in the window that can set it.
    """
    ev = c.trigger
    friend = getattr(ev, "actor", None)
    if friend is None:
        return
    ev.saved = True
    if c.may("spend a healing surge", who=friend):
        c.surge(on=friend)


@power(
    "p9982",
    level=2,
    cls="cleric",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, Keyword.DIVINE],
)
def p9982(c: Cast) -> None:
    """One angel, with the sustain's three squares as its own speed.

    The watch hangs on the conjuration's hold rather than on a duration of
    its own, so it lives exactly as long as the angel does however often the
    angel is sustained.

    The clause conjuring extra angels counts earlier uses of two other rows
    by name rather than by id, and there is nothing to count; see the report.
    """
    angel = c.conjure(label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=3)
    if not angel:
        return

    def topped_up(ev: SurgeSpent) -> None:
        ours = ev.actor == c.me or ev.actor in c.allies()
        if ours and c.adjacent_to(angel, ev.actor):
            c.heal(4, on=ev.actor)

    for hold in c.world.effects.of(angel):
        hold.subs.append(c.world.bus.on(SurgeSpent, topped_up, owner=c.me))
