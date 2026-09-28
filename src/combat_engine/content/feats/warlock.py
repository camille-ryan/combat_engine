"""Warlock feats.

The curse is `cf:warlock-f4` and it is named by ref in three of these
prerequisites, so "an enemy cursed by you" is a real question --
`Relation.CURSED_BY` holds it and `cursed_by_me` is already a predicate.

The pact half of the list was written as though the boons were prose.
They are not: each prerequisite names a pact leg (`cf:warlock-f1s2`,
`f1s3`, `f1s5`) and each *benefit* names the card it raises by ref --
`p2263`, `p2094`, `p2095` -- all three of which are declared rows. So
the boon feats are ordinary riders on a use, and the number they raise
does not have to be reached: a second bonus stacks, a second blink adds
squares, and a larger pool of temporary hit points supersedes the one
just laid.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageApplied,
    Hit,
    Keyword,
    PowerResolved,
    Relation,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.types import Usage

CURSE = "cf:warlock-f4"


def _cursed_by(c: Cast, who: int | None) -> bool:
    return who is not None and c.world.relations.holds(
        Relation.CURSED_BY, c.me, who
    )


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _hits_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.target == me and ev.attacker != me


@power("f435", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f435(c: Cast) -> None:
    """Combat advantage against bloodied enemies you have cursed. Asked
    per attack rather than at arming: both halves change during a fight,
    and a curse moves from creature to creature."""
    me = c.me
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            _cursed_by(c, ctx.get("target"))
            and c.bloodied(on=ctx.get("target"))
        ),
    )


@power("f1112", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1112(c: Cast) -> None:
    """Combat advantage against anything carrying more than one curse.

    Re-read: "how many casters have cursed this creature" is not a
    question `c.cursed` can answer, but it is not a question the engine
    lacks either -- `Relations.sources` returns every source holding a
    relation over a target, so the count is one call. The old drop named
    `c.curse(stack=)` for it.

    The first printed half, cursing what another character has already
    cursed, is a restriction `c.curse` does not impose, so there is
    nothing to lift and the row already behaves as printed.
    """
    me = c.me

    def crowded(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None:
            return False
        return len(c.world.relations.sources(Relation.CURSED_BY, who)) > 1

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, when=crowded)


@power("f746", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f746(c: Cast) -> None:
    """Radiant resistance while concealed. `c.resist` takes a gate and
    the damage context carries the type, so both halves are sayable."""
    from combat_engine.engine.query import concealment_of
    from combat_engine.engine.types import DamageType

    me = c.me
    c.resist(
        5 + c.stats.level // 2, DamageType.RADIANT, on=me,
        until=When.ENCOUNTER,
        when=lambda ctx: concealment_of(c.world, me, ctx) > 0,
    )


@power("f745", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f745(c: Cast) -> None:
    """A saving throw whenever you deal damage with a power of either of
    two keywords.

    Re-read: the pair *is* announced together. `DamageApplied.detail` is
    the ref of the row that dealt the blow -- `c.damage` passes
    `detail or self.ref` -- so the keywords are one `get` away from the
    event that names the damage, and `c.on_damage_dealt` was naming a
    gap that had closed.

    "A condition of your choice from which you are suffering" is what
    `c.save` does with no `against=`: it takes a save-ends effect the
    caster is carrying, and with nothing to shake off it does nothing,
    which is what the sentence comes to.
    """
    me = c.me
    wanted = (Keyword.RADIANT, Keyword.FEAR)

    def dealt(ev: DamageApplied) -> None:
        if ev.source != me:
            return
        p = get(ev.detail)
        if p is not None and any(k in p.keywords for k in wanted):
            c.save(on=me)

    c.watch(DamageApplied, dealt, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f744", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f744(c: Cast) -> None:
    """Hurt yourself to get an encounter power back when it missed
    everything.

    Re-read: `PowerResolved` says a use is *over* and carries `rolls`,
    every `AttackResult` the use produced, in order. That is exactly
    "you miss all targets" -- `Miss` being per target was the old
    objection and `c.on_miss_all` the symbol for it, and both are stale.

    A use with no attack roll in it is not a miss, so an empty `rolls`
    is skipped rather than counted as missing everything.
    """
    me = c.me

    def resolved(ev: PowerResolved) -> None:
        if ev.actor != me or not ev.targets or not ev.rolls:
            return
        p = get(ev.power)
        if p is None or p.cls != "warlock" or p.usage is not Usage.ENCOUNTER:
            return
        if any(getattr(r, "hit", False) for r in ev.rolls):
            return
        if not c.may("hurt yourself to get that power back", who=me):
            return
        c.flat(p.level, on=me)
        c.restore_use(ev.power, on=me)

    c.watch(PowerResolved, resolved, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f695", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an enemy hits you",
       on=Trigger(Hit, _hits_me, "an enemy hits you"))
def f695(c: Cast) -> None:
    """Curse whoever just hit you, as an immediate reaction.

    Re-read: the nearest-enemy clause really is a restriction `c.curse`
    does not impose, but that does not leave the row empty -- what it
    prints is a *second way to use the curse*, off a trigger, and
    `c.use_power` is that verb. The old row concluded there was nothing
    to say and said nothing.
    """
    c.use_power(CURSE, on=c.trigger.attacker)


# -- the pact boons, each a rider on the card its benefit names ------------


@power("f292", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2263",
       on=Trigger(PowerResolved, _used("p2263"), "your pact boon pays"))
def f292(c: Cast) -> None:
    """A second +1 on the roll that boon buys.

    Re-read: nothing has to reach inside `p2263`. It lays an untyped
    one-shot attack bonus and untyped bonuses stack, so an identical one
    laid beside it comes to the +2 the card describes and is spent on
    the same roll. Printed as a bonus to any d20 roll; only attack rolls
    can carry a modifier here, which is the choice `p2263` itself made.
    """
    c.bonus("attack", 1, on=c.me, until=When.EONT, once=True)


@power("f293", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2094",
       on=Trigger(PowerResolved, _used("p2094"), "your pact boon pays"))
def f293(c: Cast) -> None:
    """Two more squares on that boon's teleport.

    A blink is point to point and ignores what lies between, so a second
    hop of 2 from where the first ended reaches what a single hop of 5
    would. `PowerResolved` rather than `PowerUsed`, so the first hop has
    happened and the second starts from the right square.
    """
    c.teleport(2)


@power("f291", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2095",
       on=Trigger(PowerResolved, _used("p2095"), "your pact boon pays"))
def f291(c: Cast) -> None:
    """Three more temporary hit points from that boon.

    Re-read: adding to what another row granted is exactly what
    temporary hit points already do -- they do not stack, the larger
    pool wins, so laying the boon's own number plus three after it has
    paid leaves the character with the total the card prints. The
    benefit names `cf:warlock-f1c6`, which is not a declared row; the
    card that pays it is `p2095`, which is.
    """
    c.temp_hp(c.level + 3, on=c.me)
