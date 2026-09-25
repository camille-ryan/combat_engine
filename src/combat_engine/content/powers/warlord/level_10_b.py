"""Warlord, level 10: the later books' utilities. Nothing here attacks.

`p10132` and `p2566` both hand a mark to somebody other than the caster, and
`c.mark` cannot say that -- it always names `c.me` as the marker. Both go
through `Effects.apply` with the relation written out, the way
`paladin/marks.py` does, so the hold still runs on the warlord's clock while
the mark itself belongs to the creature the printed line names.

`p10133`'s standing clause names the warlord's own class heal, which is
`p1590`, and `PowerUsed` is what announces it.

`p2565` is printed as an immediate *reaction*, and the engine puts reactions
in `Window.AFTER` -- past `resolve.attack`'s confirm callback. The reroll
still changes the `AttackResult` the attacking body reads, so a new hit does
land its damage, but the `Miss` has already been announced and no `Hit`
replaces it. Declaring it an interrupt would fix the announcement and would
be a different card; the printed action is kept.

`p4573` and `p4576` both offer an action on somebody's turn and really spend
it, which is the `_each_round` shape `paladin/level_10.py` records. Second
wind is `actions.perform`'s, not a row, so the only thing that announces one
is the `+2` it puts on AC afterwards -- an `EffectApplied` labelled for it.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    MOVE,
    ONE_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    AttackDeclared,
    Cast,
    CloseBurst,
    Event,
    Gear,
    Health,
    Hit,
    Keyword,
    Miss,
    Powers,
    PowerUsed,
    Relation,
    Target,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    both,
    by_ranged,
    get,
    hits_me,
    power,
)
from combat_engine.engine.events import DamageRolled, EffectApplied
from combat_engine.engine.query import distance_between, team

MARTIAL = [Keyword.MARTIAL]
HEALING_MARTIAL = [Keyword.HEALING, Keyword.MARTIAL]

#: The warlord's own level 0 heal, which two printed lines here name.
CLASS_HEAL = "p1590"

#: What "an area or a close attack" covers, read off the power's range.
_AREA_SHAPES = ("close_burst", "close_blast", "area_burst")

_ALLY_CAUGHT = "an ally makes an area or a close attack that targets an ally"
_ALLY_MISSED = "an ally within 5 squares of you misses with an attack"
_RANGED_HIT = "an enemy hits you with a ranged attack"


def _has_shield(world: World, eid: int) -> bool:
    """"Requirement: You must be using a shield"."""
    gear = world.get(eid, Gear)
    return gear is not None and gear.shield


def _mark_by(c: Cast, marker: int, victim: int, until: When = When.EONT) -> None:
    """Mark somebody on *another* creature's behalf.

    The hold is sourced on the warlord so the printed "until the end of your
    next turn" is measured off the warlord's turn, while the relation names
    the creature that actually holds the mark -- which is what
    `_mark_penalty` and every "marked by you" rider read.
    """
    c.world.effects.apply(
        victim,
        c.me,
        until,
        label=f"{c.ref} mark",
        relations=[(Relation.MARKED_BY, marker, victim)],
    )


def _ally_caught_in_an_area(radius: int) -> Callable[[World, int, Event], bool]:
    def check(world: World, me: int, ev: Event) -> bool:
        attacker = getattr(ev, "attacker", None)
        victim = getattr(ev, "target", None)
        # Both halves of the printed line say "an ally", so neither of them
        # is the warlord: a burst that catches only you is not this trigger.
        if attacker is None or victim is None or me in (attacker, victim):
            return False
        if attacker == victim:
            return False
        if team(world, attacker) is not team(world, me):
            return False
        if team(world, victim) is not team(world, me):
            return False
        if distance_between(world, me, victim) > radius:
            return False
        p = get(getattr(ev, "power", ""))
        return p is not None and p.reach_of(getattr(ev, "branch", 0)).kind in _AREA_SHAPES

    return check


def _ally_missed_within(radius: int) -> Callable[[World, int, Event], bool]:
    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "attacker", None)
        if who is None or who == me:
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= radius

    return check


@power(
    "p10132",
    level=10,
    cls="warlord",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p10132(c: Cast) -> None:
    """You walk in and dare one of them to answer, which costs you the same
    combat advantage it buys you the damage for. The enemy is picked after
    the walk because the printed line picks it at the end of the movement.
    """
    c.move(c.speed_of())
    foe = c.choose(sorted(c.within(1, side="enemy")), "who fixes on you")
    if foe is None:
        return
    c.grants_advantage(on=c.me, to=foe, until=When.EONT)
    _mark_by(c, foe, c.me)
    c.bonus(
        "damage",
        c.str_mod,
        on=c.me,
        until=When.EONT,
        kind="power",
        when=lambda ctx: ctx.get("target") == foe,
    )


@power(
    "p10133",
    level=10,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(2),
    target=Target("ally", 99, everyone=True, label="You and any ally in the burst"),
    keywords=MARTIAL,
)
def p10133(c: Cast) -> None:
    """The standing half is a rider on the class heal rather than on this
    row, so it watches for that row being used instead of arming anything on
    the people it will help -- the heal may well land on somebody who was
    never in this burst.
    """
    c.save(on=c.target)
    if not c.first:
        return

    def shake_it_off(ev: PowerUsed) -> None:
        if ev.actor != c.me or ev.power != CLASS_HEAL:
            return
        for friend in ev.targets:
            c.save(on=friend)

    c.watch(PowerUsed, shake_it_off, until=When.EONT, on=c.me, label=f"{c.ref} rider")


@power(
    "p10950",
    level=10,
    cls="warlord",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=MARTIAL,
    trigger=_ALLY_CAUGHT,
    on=Trigger(AttackDeclared, when=_ally_caught_in_an_area(10), text=_ALLY_CAUGHT),
)
def p10950(c: Cast) -> None:
    """Interrupted at the declaration, which is the only window where the
    ally can still walk out of the blast. The dispatcher only re-aims a row
    whose printed target is a single enemy, so the ally caught by the attack
    is read off the event.
    """
    friend = getattr(c.trigger, "target", None) or c.target
    if friend is not None:
        c.shift(3 + max(c.wis_mod, c.cha_mod), who=friend)


@power(
    "p10951",
    level=10,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("other_ally", 99, everyone=True, label="Each ally in the burst"),
    keywords=HEALING_MARTIAL,
)
def p10951(c: Cast) -> None:
    """A printed "can", so the surge is the target's to refuse."""
    if c.may("spend a healing surge", who=c.target):
        c.surge()
    if c.first:
        c.note(
            f"{c.ref}: until the end of the encounter your healing powers would restore "
            "the maximum hit points possible -- nothing maximises a heal"
        )


@power(
    "p10952",
    level=10,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=Target("ally", 2, label="You and one ally in the burst"),
    keywords=MARTIAL,
)
def p10952(c: Cast) -> None:
    """Done once for the whole power: the printed line names you outright,
    and the `"ally"` pool only happens to include you.
    """
    if not c.first:
        return
    c.shift(c.speed_of(c.me), who=c.me)
    friend = next((t for t in c.targets if t != c.me), None)
    if friend is not None:
        c.shift(c.speed_of(friend), who=friend)


@power(
    "p2565",
    level=10,
    cls="warlord",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=MARTIAL,
    trigger=_ALLY_MISSED,
    on=Trigger(Miss, when=_ally_missed_within(5), text=_ALLY_MISSED),
)
def p2565(c: Cast) -> None:
    """`c.reroll_attack` takes no bonus, so the combat advantage is the two
    points it is worth on the roll, added afterwards and the outcome
    recomputed from it -- the two lines `resolve.attack` runs itself once the
    interrupt window closes. Nothing is added to an attack that already had
    the advantage; that is one grant, not two.
    """
    result = getattr(c.trigger, "result", None)
    if result is None or not c.reroll_attack():
        return
    if not result.advantage:
        result.advantage = True
        result.total += 2
    result.hit = result.critical or (
        result.natural != 1 and result.total >= result.target_defence
    )
    c.note(f"{c.ref}: the swing is taken again with combat advantage")


@power(
    "p2566",
    level=10,
    cls="warlord",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=MARTIAL,
)
def p2566(c: Cast) -> None:
    """Resolved once for the whole burst rather than once per target: the
    ally who holds the marks is one choice, and asking it again for every
    enemy in the burst would be a different power.

    The build rider widens the burst, which is header data and cannot be
    changed from a body -- so the extra ring is gathered here instead. An
    already-marked enemy is not a target at all, whoever laid the mark.
    """
    if not c.first:
        return
    friend = c.choose(sorted(c.allies()), "whose enemies these are")
    if friend is None:
        return
    caught = set(c.targets)
    if c.build("tactical"):
        caught |= set(c.within(5, side="enemy"))
    for foe in sorted(caught):
        if not c.world.relations.sources(Relation.MARKED_BY, foe):
            _mark_by(c, friend, foe)


@power(
    "p4573",
    level=10,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target("other_ally", 99, everyone=True, label="Each ally in the burst"),
    keywords=HEALING_MARTIAL,
)
def p4573(c: Cast) -> None:
    """Second wind is `actions.perform`'s own, not a row, and the only thing
    it announces is the `+2` to AC it finishes with -- so the extra hit
    points are hung on that effect landing rather than on the heal, which
    carries nothing to tell it from any other.

    The minor-action version is offered at the start of the ally's turn and
    the minor is really spent. It is written out rather than routed through
    `actions.perform`, because the printed line takes the defence bonus away
    and that bonus is the last thing `perform` does.
    """
    if not c.first:
        return
    crew = set(c.targets)

    def topped_up(ev: EffectApplied) -> None:
        if ev.target in crew and ev.label.startswith("second-wind"):
            c.heal(c.cha_mod, on=ev.target)

    def as_a_minor(ev: TurnStart) -> None:
        who = ev.actor
        if ev.ghost or who not in crew or c.world.encounter is None:
            return
        health = c.world.get(who, Health)
        known = c.world.get(who, Powers)
        if health is None or known is None or health.surges <= 0:
            return
        if known.times("second-wind") or not c.may("catch a breath", who=who):
            return
        if not c.world.encounter.spend(who, MINOR):
            return
        known.note_use("second-wind", c.world.round)
        c.surge(on=who, bonus=c.cha_mod)

    c.watch(EffectApplied, topped_up, until=When.EONT, on=c.me, label=f"{c.ref} rider")
    c.watch(TurnStart, as_a_minor, until=When.EONT, on=c.me, label=f"{c.ref} offer")


#: The three things the warlord can call for, in the order they are printed.
_PRESENCE = ("attack rolls", "speed", "defences")


def _presence(c: Cast, who: int, pick: str) -> None:
    if pick == "attack rolls":
        c.bonus("attack", c.cha_mod, on=who, until=When.EONT, kind="power")
    elif pick == "speed":
        c.bonus("speed", c.cha_mod, on=who, until=When.EONT, kind="power")
    else:
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, c.int_mod, on=who, until=When.EONT, kind="power")


@power(
    "p4574",
    level=10,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=MARTIAL,
)
def p4574(c: Cast) -> None:
    """One choice for the whole burst unless the build rider says otherwise,
    so the asking is done once here rather than once per target.
    """
    if not c.first:
        return
    each = c.build("resourceful")
    shared = None if each else c.choose(list(_PRESENCE), "what you call for")
    for who in c.targets:
        pick = c.choose(list(_PRESENCE), f"what you call for from {who}") if each else shared
        if pick is not None:
            _presence(c, who, pick)


@power(
    "p4575",
    level=10,
    cls="warlord",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_has_shield,
    requires_text="needs a shield",
    trigger=_RANGED_HIT,
    on=Trigger(Hit, when=both(hits_me, by_ranged), text=_RANGED_HIT),
)
def p4575(c: Cast) -> None:
    """The interrupt lands before the damage is rolled, so the reduction is
    armed as a one-shot on `DamageRolled` rather than applied to a number
    that does not exist yet. Nothing on `Cast` shaves damage in flight --
    `c.absorb` takes all of it and moves it -- which is what `p1441` records.

    The charge goes through `c.charge_at`, which is the move and the charge
    flag together; `c.grant_attack` would hand over the swing without either.
    """
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None:
        return
    me = c.me
    shield = c.level // 2
    spent: list[int] = []

    def turned_aside(ev: DamageRolled) -> None:
        if spent or ev.target != me or ev.source != attacker:
            return
        spared = min(ev.amount, shield)
        ev.amount -= spared
        spent.append(spared)
        c.note(f"{c.ref}: {spared} damage turned aside")

    c.watch(
        DamageRolled,
        turned_aside,
        until=When.EOT,
        window=Window.BEFORE,
        on=me,
        label=f"{c.ref} shield",
    )
    helpers = [a for a in c.within(5, of=attacker, side="ally") if a != me]
    friend = c.choose(sorted(helpers), "who answers the shot", optional=True)
    if friend is not None and c.may("charge the archer", who=friend):
        c.charge_at(attacker, who=friend)


@power(
    "p4576",
    level=10,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p4576(c: Cast) -> None:
    """The standing offer is made at the start of the warlord's own turn and
    the move action is really spent, so it cannot be taken twice and it costs
    what it prints. Both halves of the "or" are the same square and the same
    bonus, so who gets them is one choice rather than two branches.

    The damage bonus runs to the start of the warlord's next turn whoever
    takes it -- `When.SONT` is clocked off the source, which is the warlord.
    """
    me = c.me
    stance = c.stance(label=c.ref)

    def offer(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or c.world.encounter is None or stance.ended:
            return
        if not c.may(f"spend a move action on {c.ref}", who=me):
            return
        pool = [me, *(a for a in c.within(5, side="ally") if a != me)]
        who = c.choose(pool, "who steps and swings harder")
        if who is None or not c.world.encounter.spend(me, MOVE):
            return
        c.shift(1, who=who)
        c.bonus("damage", 2, on=who, until=When.SONT, kind="power")

    hold = c.watch(
        TurnStart, offer, until=When.ENCOUNTER, on=me, label=f"{c.ref} standing offer"
    )
    stance.on_end.append(lambda: c.world.effects.end(hold, "stance ended"))
