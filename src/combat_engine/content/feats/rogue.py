"""Rogue feats.

The class's extra damage is `cf:rogue-scoundrel-f4`, named by ref in
five of these prerequisites -- so where a row *rides* on it the gap is
never the name.

Nor is it the announcement, which was the standing diagnosis here and
is wrong: `features.strikers.extra_damage` pays out through
`c.damage(detail=label)`, so the payment arrives as a `DamageRolled`
carrying the feature's ref, rolled and not yet landed. `f751` trades it
away from there.

**And the two things this paragraph called missing are both built.** It
said the once-a-round latch "lives in a closure and nothing can read or
reset it" and that there was no "way to reach into the dice another row
rolls". The latch moved onto `Powers.latched` in #569 -- `c.latched`,
`c.latch` and `c.unlatch` are the three doors, and `c.payment_window`
carries the per-turn reasoning this card needs. The dice are
`c.change_dice` and `c.dice_for`, which `f185` writes and `f763` reads.
Nothing in this file waits on either.

The rest divides into the ordinary -- a critical with combat advantage,
a damage bonus beside an ally -- and three that turn on traps, which
the engine models and nothing on a board has ever placed (#74).
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
    Condition,
    DamageApplied,
    DamageRolled,
    EffectApplied,
    Hit,
    PowerUsed,
    Size,
    Trigger,
    When,
    power,
)
from combat_engine.engine.query import allies, has_combat_advantage


def _used_wrath(world, me: int, ev) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == "p1628"


def _crit_with_advantage(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A critical hit made **while you had combat advantage**.

    Read off the `Hit`'s own `AttackResult`, not by asking the board
    again: a one-shot grant of combat advantage has already been spent
    by the time the hit is announced, so asking afresh answers no for
    exactly the attacks these two rows are printed for.
    """
    result = getattr(ev, "result", None)
    return (
        ev.attacker == me
        and ev.critical
        and result is not None
        and result.advantage
    )


@power("f302", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you crit while you have combat advantage",
       on=Trigger(Hit, _crit_with_advantage, "you crit with advantage"))
def f302(c: Cast) -> None:
    c.grants_advantage(on=c.trigger.target, until=When.EONT)


@power("f307", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you crit while you have combat advantage",
       on=Trigger(Hit, _crit_with_advantage, "you crit with advantage"))
def f307(c: Cast) -> None:
    c.prone(on=c.trigger.target)


@power("f762", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f762(c: Cast) -> None:
    """Adjacency is asked when the blow lands rather than when the trait
    arms: a rogue moves, and where it was standing at the top of the
    fight is not where it is when it swings."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: any(
            c.adjacent(to=friend) for friend in allies(c.world, me)
        ),
    )


@power("f356", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f356(c: Cast) -> None:
    """The surprise round and the first round. `world.round` is 1 for
    both -- a surprise round is not counted separately -- so the gate is
    simply the first round, which is what the sentence comes to."""
    me = c.me
    c.bonus("speed", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.world.round <= 1)
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.world.round <= 1 and not ctx.get("ranged", False),
    )


@power("f751", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f751(c: Cast) -> None:
    """Trades the class's extra damage for a condition, and the moment
    does exist after all: `features.strikers.extra_damage` pays out with
    `c.damage(..., detail=label)`, so the blow arrives as a
    `DamageRolled` carrying `cf:rogue-scoundrel-f4` in `detail` -- rolled
    and not yet landed, which is exactly the seam "forgo rolling" needs.

    "Counts as using Sneak Attack for the round" comes free: the
    feature's own latch was spent before it rolled, so nothing has to say
    it. `default=False` so a fight with nobody playing takes the damage,
    which is the printed default.
    """
    me = c.me

    def offered(ev: Any) -> None:
        if ev.source != me or ev.detail != "cf:rogue-scoundrel-f4":
            return
        if ev.amount <= 0 or c.size_of(ev.target).order < Size.LARGE.order:
            return
        if not c.may("forgo the extra damage", who=me, default=False):
            return
        c.reduce(ev.amount, ev)
        c.slowed(on=ev.target, until=When.EONT)

    c.watch(DamageRolled, offered, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} trade")


@power("f763", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f763(c: Cast) -> None:
    """Raises ongoing damage by one per die of the class's extra damage.

    **The marker said "what is left is raising an ongoing amount already
    set", and that was never missing.** `Effect.ongoing` is an ordinary
    mutable field and twelve content sites already write it in place --
    `monsters/level_10/brutes_sa.py` does `existing.ongoing = (amt +
    amount, dtype)` for this very sentence, and three files carry a named
    `_ongoing_amount` helper written for "increases by N". So there was
    nothing to wait for and `c.raise_ongoing(by)` would have been a
    thirteenth spelling.

    **The ordering is the part that needed care.** `features/strikers.py`
    pays the extra damage from a `Hit` watcher, and a power lays its
    ongoing *after* `c.strike()` returns -- so a raise hung on `Hit` runs
    before there is anything to raise. It is hung on `EffectApplied`
    instead, which `durations.apply` emits **after** `self.live[eff.id] =
    eff`, so the hold is already findable and its `ongoing` already set.

    The two halves are tied together by the payout's own window rather
    than by one event carrying both: the striker's blow arrives as a
    `DamageApplied` whose `detail` is the feature's label, and that latches
    a per-target key for the current turn. The card's "once per turn" is
    the striker's latch, not a second one, so the window `c.latched(...,
    per_turn=True)` measures is the same one `pay_extra` spent.

    **One known narrowing, and it is an over-count of one.** `c.dice_for`
    answers the dice the feature is *declared* to roll, after `f185`'s
    d8 swap; it cannot see `f952`'s "forgo rolling 1 die", which
    `features/strikers._forgo` decides inside the payout and announces
    nowhere. A rogue holding both feats and taking that trade raises the
    burn by one more than it dealt. #619.
    """
    me = c.me
    sneak = "cf:rogue-scoundrel-f4"

    def paid(ev: Any) -> None:
        if ev.source != me or ev.amount <= 0:
            return
        if getattr(ev, "detail", "") != sneak:
            return
        c.latch(f"{c.ref} {ev.target}", per_turn=True)

    def landed(ev: Any) -> None:
        if ev.source != me:
            return
        if not c.latched(f"{c.ref} {ev.target}", per_turn=True):
            return
        burn = next(
            (
                e for e in c.world.effects.of(ev.target)
                if not e.ended and e.ongoing and e.source == me
                and e.label == ev.label
            ),
            None,
        )
        if burn is None:
            return
        dice = c.dice_for(sneak, "2d6")
        count = int(dice.split("d")[0]) if "d" in dice else 0
        if count <= 0:
            return
        amount, dtype = burn.ongoing
        burn.ongoing = (amount + count, dtype)

    c.watch(DamageApplied, paid, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} paid")
    c.watch(EffectApplied, landed, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} raise")


@power("f185", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f185(c: Cast) -> None:
    """The class feature's extra damage rolls d8s instead of d6s.

    `extra_damage` asks `c.dice_for` for its die now rather than closing over
    the string, which is what made this writable; the feat is the other half.

    **The count is written out rather than derived.** The feature rolls two
    dice throughout the levels this build imports, so "2d8" is the whole of
    the sentence here. It stops being so at 11th, where the feature's own
    count goes up -- so this is one of the rows #281 has to revisit, and
    saying that here is cheaper than finding it then."""
    c.change_dice("cf:rogue-scoundrel-f4", "2d8")


@power("f799", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, )
def f799(c: Cast) -> None:
    """A longsword where the rogue rows ask for a light blade, at the cost
    of a die of the extra damage.

    By **slug**, not by group: `f2078` is the card that waives every heavy
    blade, and this one names the longsword only. "You still cannot throw
    the longsword" needs nothing -- a longsword has no thrown property to
    take away.

    The price is `c.change_dice` on the class feature, gated on what is
    actually in hand at the moment of the hit rather than at arming, the
    same way `rogue_b._price` does it for the mace.
    """
    c.counts_as("light blade", holding="longsword")
    c.change_dice(
        "cf:rogue-scoundrel-f4", "1d6", on=c.me,
        when=lambda ctx: c.wielding("longsword"),
    )
#: *"That distance + 2 squares."*
_F370_FURTHER = 2


@power("f370", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f370(c: Cast) -> None:
    """Turns any shift a power grants into a longer walk.

    **"Nothing intercepts one" was the premise and it was wrong about
    the layer.** A shift is indeed taken inside the granting row's body
    -- and every one of them goes through `c.shift`, which is a single
    door. So the interception is a read there rather than a facility
    reaching into other rows' bodies.

    `c.shift_becomes_move` is that read, and the clause is a **trade**
    rather than a bonus: a shift ignores difficult terrain and draws no
    opportunity attack, a walk does both, so the card buys ground with
    safety. That is why it cannot be a silent substitution -- `c.shift`
    offers it through `World.decide`, the same door the destination
    already goes through.

    **The headless default is to keep shifting**, because `decide` takes
    `options[0]` with no decider installed and `False` is first. So
    `replay`, `audit` and every fixture behave exactly as before -- 8 of
    8 after the change -- and the trade is something a player reaches
    for. #1568."""
    c.shift_becomes_move(_F370_FURTHER, on=c.me, until=When.ENCOUNTER)


@power("f750", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit a target that has not yet acted",
       on=Trigger(Hit, lambda w, me, ev: ev.attacker == me, "you hit"))
def f750(c: Cast) -> None:
    """"Has not yet acted" is the surprised condition, which the surprise
    round lays and the creature's first turn clears."""
    foe = c.trigger.target
    if c.is_(Condition.SURPRISED, on=foe):
        c.slide(1, on=foe)


@power("f767", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1628",
       on=Trigger(PowerUsed, _used_wrath, "you use that racial power"))
def f767(c: Cast) -> None:
    """`p1628` is `NO_TARGET` and aims itself at the enemy on its own
    trigger, so "the target" is read there.

    `PowerUsed` fires before the body, which is what makes a damage
    bonus gated on that row the right shape: it is standing by the time
    the row rolls. Asking for combat advantage now rather than off a
    result is correct here -- the triggering blow was *theirs*, so no
    grant of ours has been spent on it.
    """
    foe = getattr(getattr(c.trigger, "trigger", None), "attacker", None)
    if foe is None or not has_combat_advantage(c.world, c.me, foe):
        return
    c.bonus("damage", c.dex_mod, on=c.me, until=When.EOT, once=True,
            when=lambda ctx: ctx.get("power") == "p1628")


@power("f784", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f784(c: Cast) -> None:
    """Allies hit harder against enemies this rogue has rattled.

    The narrowing to a penalty *this* character caused was marked as a
    gap and is not one: `c.suffering` already filters by `eff.source`,
    and `c._rattle` lays the `rattled` hold from the attacker's own cast
    -- so the default `by=` is the rogue and the list is the creatures it
    rattled itself."""
    me = c.me
    for friend in [a for a in allies(c.world, me) if a != me]:
        c.bonus(
            "attack", 1, on=friend, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") in c.suffering("rattled"),
        )


@power("f377", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f377(c: Cast) -> None:
    """A defence bonus against traps. `Trap` marks an entity as a hazard
    rather than a creature and `c.is_trap` asks, so this is writable --
    but nothing on a board has ever placed one (#74), so it will not
    come up until that changes."""
    from combat_engine.engine import AC, FORT, REF, WILL

    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 2, on=c.me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: (
                ctx.get("attacker") is not None
                and c.is_trap(ctx["attacker"])
            ),
        )


@power("f775", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f775(c: Cast) -> None:
    """Finding traps and opening locks. Both are checks, not a fight."""
