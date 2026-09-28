"""Psion feats.

The class's whole vocabulary is "augmented" and "unaugmented", and those
are two different questions. `augment.spent_on` is what the use resolving
*right now* was bought with, which is what a rider on a `Hit` or on a
damage roll means; `PowerPoints.augmented` is the encounter's running
total, so a row asked that way reads as augmented for the rest of the
fight once it has been augmented at all. Every gate here uses the first.

Four of the class's six level-0 rows are `out_of_combat=True` -- they move
objects or send a sentence -- and two feats ride those. `p8225` announces
a `PowerUsed` whatever else it does, so the riders work; `p11267` has no
sustain to make cheaper, which is header data and blocks one row.

`cf:psion-focus` is the discipline focus, and it has a leg per option in
`chargen.BUILDS["psion"]` now -- so which two cards a psion's focus
granted is answerable, and `f1632` is written against it. `f3398` still
is not: it is a **second** focus alongside the first, and a character
takes one leg and stays on it.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.augment import spent_on
from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    PowerUsed,
    SavingThrow,
    Trigger,
    Usage,
    When,
    Window,
    get,
    power,
)
from combat_engine.engine.components import Position, PowerPoints
from combat_engine.engine.grid import distance
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.zones import Zone

SEND_THOUGHTS = "p8225"
DISTRACT = "p8224"
#: A racial zone named by ref. `Cast.zone` defaults a zone's label to the
#: ref that laid it, so the zone that row makes carries this string.
CLOUD = "p2473"
#: The racial attack power `f3172` retypes and hands back.
RACIAL = "p8278"

#: `chargen.BUILDS` has a leg per printed focus now, so the list is not
#: the gap -- what is missing is a way to be on a *second* leg at once.
SECOND_BUILD = ("c.set_build()",)

#: The two cards each discipline focus hands over, by the leg that takes
#: it. Read off `features/psionic.py`, which is what grants them.
FOCUS_ROWS = {
    "f0s0": ("p13300", "p13301"),
    "f0s1": ("p11267", "p11268"),
    "f0s2": ("p8224", "p8225"),
}


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _psionic(ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.PSIONIC in p.keywords


def _unaugmented_at_will(me: int, ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power", ""))
    return (
        p is not None
        and p.cls == "psion"
        and p.usage is Usage.AT_WILL
        and Keyword.PSIONIC in p.keywords
        and not spent_on(me, p.ref)
    )


def _augmented_at_will(me: int, ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power", ""))
    return (
        p is not None
        and p.cls == "psion"
        and p.usage is Usage.AT_WILL
        and Keyword.PSIONIC in p.keywords
        and bool(spent_on(me, p.ref))
    )


def _psionic_hit(world, me: int, ev: Hit) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return ev.attacker == me and p is not None and Keyword.PSIONIC in p.keywords


def _heavily_augmented_hit(world, me: int, ev: Hit) -> bool:  # noqa: ANN001
    return _psionic_hit(world, me, ev) and spent_on(me, ev.power) >= 2


def _daily_psionic_hit(world, me: int, ev: Hit) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.usage is Usage.DAILY
        and Keyword.PSIONIC in p.keywords
    )


def _ally_failed_a_save(world, me: int, ev: SavingThrow) -> bool:  # noqa: ANN001
    return (
        ev.actor != me
        and not ev.saved
        and team(world, ev.actor) is team(world, me)
        and distance_between(world, me, ev.actor) <= 20
    )


# -- augmented and unaugmented ---------------------------------------------


@power("f1634", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a psionic power bought with 2 or more points",
       on=Trigger(Hit, _heavily_augmented_hit, "a heavily augmented hit"))
def f1634(c: Cast) -> None:
    """Both halves ask `augment.spent_on`: the trigger about the blow that
    just landed, the gate about whatever is being rolled next."""
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.EONT,
        when=lambda ctx: _unaugmented_at_will(me, ctx),
    )


@power("f3277", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3277(c: Cast) -> None:
    """A standing modifier rather than a trigger: bloodied comes and goes,
    so it is asked per attack roll along with the augment."""
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=me) and _augmented_at_will(me, ctx),
    )


@power("f3307", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an enemy with a daily psion power",
       on=Trigger(Hit, _daily_psionic_hit, "a daily psion hit"))
def f3307(c: Cast) -> None:
    """"Your next attack against that enemy" is `once=True` on a gate that
    names the creature. The card prints force *or* psychic, so the type
    is asked rather than picked -- `c.choose` takes damage types, and
    writing it as both at once would be a different and harder-to-resist
    thing than the card says."""
    me, foe = c.me, c.trigger.target
    pick = c.choose(
        [DamageType.FORCE, DamageType.PSYCHIC], f"{c.ref}: which damage type"
    )
    c.bonus(
        "damage", 0, dice="1d6", on=me, until=When.EONT, once=True,
        dtype=pick or DamageType.PSYCHIC,
        when=lambda ctx: (
            ctx.get("target") == foe and _unaugmented_at_will(me, ctx)
        ),
    )


@power("f3300", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3300(c: Cast) -> None:
    """"Force powers" is the keyword on the row being rolled, not the type
    of the damage -- a force power with an untyped rider is still one. The
    card prints the word "feat" in front of "bonus"."""
    c.bonus(
        "damage", 2 + sum(lv <= c.level for lv in (11, 21)),
        kind="feat", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            (p := get(ctx.get("power", ""))) is not None
            and Keyword.FORCE in p.keywords
        ),
    )


@power("f3291", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3291(c: Cast) -> None:
    """Standing inside a zone of one's own is asked per damage roll, since
    the psion walks in and out of it. The extra 3 is psychic and carries
    that type of its own.
    """
    me = c.me

    def inside(ctx: dict[str, Any]) -> bool:
        if not _unaugmented_at_will(me, ctx):
            return False
        return any(
            zone.owner == me
            and CLOUD in zone.label
            and me in c.world.zones.occupants(eid)
            for eid, zone in c.world.each(Zone)
        )

    c.bonus("damage", 3, on=me, until=When.ENCOUNTER, when=inside,
            dtype=DamageType.PSYCHIC)


# -- riders on send thoughts and distract ----------------------------------


@power("f1633", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p8225",
       on=Trigger(PowerUsed, _used(SEND_THOUGHTS), "you use p8225"))
def f1633(c: Cast) -> None:
    """"An ally who has power points" is a creature the chassis dealt a
    pool to, which is `PowerPoints.maximum` rather than what is left in it
    -- a psion who has spent everything is still an ally who has power
    points. `c.transfer_points` is the printed exchange exactly: one
    leaves the psion and one arrives."""
    me = c.me
    for who in c.trigger.targets:
        pool = c.world.get(who, PowerPoints)
        if who == me or pool is None or pool.maximum <= 0:
            continue
        if c.may("lose a power point"):
            c.transfer_points(1, on=who)
        return


@power("f3303", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p8225",
       on=Trigger(PowerUsed, _used(SEND_THOUGHTS), "you use p8225"))
def f3303(c: Cast) -> None:
    """The ending condition is written rather than dropped: the hold is
    kept and a `Dropped` watch ends it early, which is what "until you or
    the target drops to 0 hit points" says and the only reading that does
    not leave the effect standing over a corpse."""
    me = c.me
    for foe in c.trigger.targets:
        held = c.ignore_cover(
            on=me, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: ctx.get("target") == f and _psionic(ctx),
        )
        if held is None:
            continue

        def fell(ev: Dropped, effect: Any = held, f: int = foe) -> None:
            if ev.actor in (me, f):
                c.world.effects.end(effect, "the psion or the target dropped")

        c.watch(Dropped, fell, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f3325", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p8224",
       on=Trigger(PowerUsed, _used(DISTRACT), "you use p8224"))
def f3325(c: Cast) -> None:
    """"Your next attack against the target" is `once=True` on a gate
    naming that creature. The card prints "power bonus"."""
    me = c.me
    for foe in c.trigger.targets:
        c.bonus(
            "damage", 3, kind="power", on=me, until=When.EONT, once=True,
            when=lambda ctx, f=foe: ctx.get("target") == f and _psionic(ctx),
        )


@power("f2789", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p8224",
       on=Trigger(PowerUsed, _used(DISTRACT), "you use p8224"))
def f2789(c: Cast) -> None:
    """The destination is named rather than left to the decider, because
    the printed line constrains it: "to a square adjacent to an ally" is
    not something the slide can be trusted to land on by itself. The
    candidates are tried nearest first -- a slide walks the ground a step
    at a time, so a square in range is not always a square it can get
    to."""
    me = c.me
    beside = [
        p.square for a in c.allies()
        if a != me and (p := c.world.get(a, Position)) is not None
    ]
    if not beside:
        return
    for foe in c.trigger.targets:
        here = c.world.get(foe, Position)
        if here is None:
            continue
        spots = sorted(
            (sq for sq in c.world.reachable_squares(foe, 2)
             if any(distance(sq, mate) == 1 for mate in beside)),
            key=lambda sq, at=here.square: (distance(sq, at), sq),
        )
        for square in spots:
            if c.slide(2, on=foe, to=square):
                break


@power("f3294", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally you can see within 20 squares fails a saving throw",
       on=Trigger(SavingThrow, _ally_failed_a_save, "an ally fails a save"))
def f3294(c: Cast) -> None:
    """`SavingThrow` is announced before it is acted on and `c.reroll_save`
    writes the new result back into it.

    The cost was marked as having no verb and has one: `c.expend_row`
    spends a use of a row its owner holds *without running it*, which is
    what "expend your p8225" means. Its False is the printed
    requirement -- a psion that has already spent the word cannot pay,
    and then there is no reroll. That is also why the row is `AT_WILL`:
    the card prints no limit of its own, and an `ENCOUNTER` triggered
    trait is spent on its first firing (#210)."""
    if c.can_see(c.trigger.actor) and c.expend_row(SEND_THOUGHTS, on=c.me):
        c.reroll_save()


@power("f3324", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy you are hidden from with a psion power",
       on=Trigger(Hit, _psionic_hit, "a psion hit"))
def f3324(c: Cast) -> None:
    """Hiding is broken by attacking, and `resolve.attack` clears it
    *after* the `Hit` goes out -- so asked here the relation still holds,
    and asked a moment later it would be false every time."""
    foe = c.trigger.target
    if c.is_hidden(from_=foe):
        c.slide(2, on=foe)


# -- the ones with nothing to hang on --------------------------------------


@power("f1632", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1632(c: Cast) -> None:
    """A second use of each of the two cards the discipline focus grants.

    Which two they are is the leg, and `chargen.BUILDS["psion"]` has one
    per printed focus now, so the pair is looked up rather than guessed.

    Written as a refund rather than as a second charge: nothing raises a
    row's per-encounter allowance, and `c.restore_use` is what hands a
    spent use back. One refund per card, latched, which is exactly "twice
    per encounter" -- a third use finds the latch spent.

    `PowerUsed` is announced before the body runs, and that is what this
    wants: the use has been counted by then, which is the moment there is
    something to give back.
    """
    me = c.me
    mine = next((refs for leg, refs in FOCUS_ROWS.items() if c.build(leg)), ())
    if not mine:
        return
    spent: set[str] = set()

    def refund(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power not in mine or ev.power in spent:
            return
        spent.add(ev.power)
        c.restore_use(ev.power, on=me)

    c.watch(PowerUsed, refund, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f3398", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=SECOND_BUILD)
def f3398(c: Cast) -> None:
    """A second discipline focus, its powers usable as dailies.

    Re-aimed: `chargen.BUILDS` exists and has a leg per printed focus,
    which is what `f1632` reads, so naming it was naming a gap that has
    closed. What is missing is standing on two legs -- `c.build` asks
    which one was taken and nothing adds another."""


@power("f2588", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.forces(target=)",))
def f2588(c: Cast) -> None:
    """A square further on every shove against a creature granting combat
    advantage. `c.forces` is the right key and its gate is handed `how`
    and `power` and nothing else -- the creature being shoved is not in
    the context, so the condition cannot be asked."""


@power("f2608", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2608(c: Cast) -> None:
    """Makes sustaining `p11267` a free action. `dsl.Power` is not the gap
    -- it is the header dataclass, it exists, and it carries
    `sustain_cost`. The gap was never in the engine: `p11267` lifts an
    object of twenty pounds or less, the engine has no objects, and the row
    it edits is itself declared `out_of_combat=True`. A feat that cheapens
    the upkeep of a power with no combat consequence has none either, so it
    is deliberately inert rather than unfinished."""


@power("f3172", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET)
def f3172(c: Cast) -> None:
    """A racial power that deals two types at once, and comes back and
    fires again when it kills. Both halves are writable now.

    The retype is `DamageRolled.dtypes`, which is the blow being both at
    once rather than one instead of the other. The kill is read off
    `DamageApplied` -- `Dropped` does not say who did it -- and the
    window is the watch's own `EONT`, laid when the racial power is used
    so that the creatures it aimed at are the ones being counted.
    """
    me = c.me
    pair = (DamageType.NECROTIC, DamageType.PSYCHIC)

    def retype(ev: DamageRolled) -> None:
        if ev.source == me and ev.detail == RACIAL:
            ev.dtypes = pair

    c.watch(DamageRolled, retype, until=When.ENCOUNTER, on=me,
            window=Window.BEFORE, label=c.ref)

    def aimed(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != RACIAL:
            return
        # Chosen before the body runs, so `ev.targets` is trustworthy here
        # where nothing the body did would be.
        marks = set(ev.targets)

        def felled(blow: DamageApplied) -> None:
            if blow.source != me or blow.target not in marks or blow.hp > 0:
                return
            marks.discard(blow.target)
            if c.restore_use(RACIAL, on=me):
                c.use_power(RACIAL)

        c.watch(DamageApplied, felled, until=When.EONT, on=me, label=c.ref)

    c.watch(PowerUsed, aimed, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f3275", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       todo=("c.recast(reach=)",))
def f3275(c: Cast) -> None:
    """Spends one racial power to use another at a range it does not
    print. Re-aimed, and onto the symbol ten other rows already use:
    `c.expend_row("p8225")` is the price and `c.use_power("p7546")` is
    the use, so both of those halves have verbs -- what is left is
    using a row at a reach it does not print, which is header data read
    before the body runs."""


@power("f3284", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3284(c: Cast) -> None:
    """Insight and Perception while the conjuration from `p13300` is
    nearby. The whole benefit is two skill numbers, so the row is
    deliberately inert rather than unwritten."""
