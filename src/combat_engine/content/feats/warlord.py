"""Warlord feats.

Almost the whole list is a rider on something the warlord already has,
and which of those things it is decides whether the row is writable.

**"When an ally spends an action point" is writable and there are five
of them.** `ActionPointSpent` is a real event and action points are
really spent now, so these are ordinary triggers.

**"Your Inspiring Word" is `p1590`**, which is a ref and a declared
row, so the two feats riding on it are ordinary watches on `PowerUsed`.
That was never a class-feature gap: the warlord's heal is a card.

**The leader presences split three ways**, now that the prerequisites
are read. `cf:warlord-marshal-f4s0` and `-f4s3` are declared rows, and
`-f4s2` and `-f4s5` are refs nothing declares. A feat on one of the
first two is blocked on something narrower than "no ref": `-f4s0`
decides whether it fires inside its own handler and announces nothing
(`c.on_feature_power()`), and `-f4s3` keeps both its numbers as locals
in a closure (`c.amplify_bonus()`). The other two are
`c.borrow_feature()`, the same gap as any other undeclared `cf:` row.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    NO_TARGET,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionPointSpent,
    ActionType,
    Cast,
    Healed,
    Hit,
    Keyword,
    PowerUsed,
    Trigger,
    When,
    Window,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import distance_between, team

FEATURE = ("c.class_feature()",)
#: A `cf:` ref the prerequisite prints and no row in the tree declares.
BORROW = ("c.borrow_feature()",)
#: Raising a number a row somebody else wrote already handed out.
AMPLIFY = ("c.amplify_bonus()",)
#: The feature has a ref and a row, and its firing is not announced.
ON_FEATURE = ("c.on_feature_power()",)

#: The warlord's class heal, and the row six of these feats ride on.
_THE_WORD = "p1590"


def _ally_point(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor != me and team(world, ev.actor) == team(world, me)


def _bow_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    from combat_engine.engine.components import Gear

    gear = world.get(me, Gear)
    p = get(ev.power)
    return (
        ev.attacker == me
        and gear is not None
        and gear.ranged is not None
        and gear.ranged.group == "bow"
        and p is not None
        and Keyword.WEAPON in p.keywords
    )


@power("f294", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally who can see you spends an action point",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f294(c: Cast) -> None:
    """A saving throw for the ally, at your Charisma rather than theirs --
    `c.save` follows `c.target`, and the row is declared with none, so
    the ally is named outright."""
    c.save(on=c.trigger.actor, bonus=c.cha_mod)


@power("f308", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally who can see you spends an action point to attack",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f308(c: Cast) -> None:
    """The bonus is to the damage of the attack the point bought, so it
    is spent on the first roll rather than left standing."""
    c.bonus("damage", c.int_mod, on=c.trigger.actor, until=When.EONT, once=True)


@power("f794", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally who can see you spends an action point to attack",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f794(c: Cast) -> None:
    """A plain "+1 bonus", so untyped."""
    c.bonus("attack", 1, on=c.trigger.actor, until=When.EONT, once=True)


@power("f779", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally you can see spends an action point to attack",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f779(c: Cast) -> None:
    """"Before or after the attack" is a choice with no way to express
    the ordering, and the point has already been spent by the time this
    is offered -- so the teleport happens now, which is "before"."""
    c.teleport(1, who=c.trigger.actor)


@power("f796", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with a bow attack",
       on=Trigger(Hit, _bow_hit, "you hit with a bow"))
def f796(c: Cast) -> None:
    """Allies within 10 who can see and hear you, against that one
    target, until the start of your next turn."""
    me, foe = c.me, c.trigger.target
    for friend in [a for a in team(c.world, me) if a != me]:
        if distance_between(c.world, me, friend) > 10:
            continue
        c.bonus(
            "attack", 1, on=friend, until=When.SONT,
            when=lambda ctx: (
                ctx.get("target") == foe and ctx.get("ranged", False)
            ),
        )


@power("f756", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Miss.advantage",))
def f756(c: Cast) -> None:
    """Turns on an enemy **missing** you while it has combat advantage.
    `Miss` carries no `advantage`, and the live `AttackResult` that does
    rides on `Hit` -- so the one event this row needs is the one that
    cannot answer the question."""


@power("f797", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_basic()",))
def f797(c: Cast) -> None:
    """A bonus on an attack granted by one of this character's own
    powers. A granted swing is announced as the row it is, not as a
    grant, so there is nothing to tell it from any other attack."""


def _feature(ref: str, what: str, marker: tuple[str, ...] = FEATURE) -> None:
    """One of the rows riding on a class feature that has no ref."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=marker)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = what


_feature("f789", "Raises what one leader presence restores. The prerequisite "
                 "names `cf:warlord-marshal-f4s2` and no row in the tree "
                 "declares it, so there is no payout to raise.", BORROW)
_feature("f791", "Raises what a third leader presence grants. The "
                 "prerequisite names `cf:warlord-marshal-f4s5` and no row "
                 "declares it.", BORROW)
_feature("f790", "Raises what `cf:warlord-marshal-f4s3` pays. That row is "
                 "declared now, and both numbers it hands out -- the damage "
                 "bonus and the temporary hit points -- are locals in its "
                 "closure. Adding 2 to each means editing a modifier "
                 "somebody else laid; a second `c.temp_hp` would be a "
                 "competing pool rather than a larger one.", AMPLIFY)
_feature("f788", "A choice of two bonuses when `cf:warlord-marshal-f4s0` is "
                 "used. That row is declared, but the ally's opt-in -- the "
                 "moment the presence is actually taken up -- happens inside "
                 "its `ActionPointSpent` handler and nothing announces it. "
                 "Watching the bare point spend would pay out for every "
                 "ally who declined the gamble.", ON_FEATURE)
_feature("f759", "The same presence, larger and gated on bloodied, and "
                 "blocked the same way `f788` is.", ON_FEATURE)


@power("f757", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f757(c: Cast) -> None:
    """A rider on `p1590`, which is a ref and a declared row.

    `PowerUsed` announces before the body runs, so the choice is made
    while the heal is still ahead: the extra hit points are claimed by
    the **next** `Healed` that row produces on that ally, which is the
    seam `cf:cleric-templar-f1` uses from the same side -- `Healed` is a
    `Decision` and its `amount` is still negotiable in the BEFORE window.

    "Adjacent" is measured when the word is spoken, not when it lands.
    A trait, so `AT_WILL` rather than `ENCOUNTER`: the card prints no
    limit and an `action=NONE` row spends a use every firing (#210).
    """
    me = c.me

    def spoken(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != _THE_WORD:
            return
        for friend in ev.targets:
            if distance_between(c.world, me, friend) > 1:
                continue
            if c.choose(["hit points", "a saving throw"],
                        f"f757: what {friend} takes") == "a saving throw":
                c.save(on=friend)
                continue
            extra = c.wis_mod
            if extra <= 0:
                continue
            done: dict[str, bool] = {"yet": False}

            def more(healed: Healed, who: int = friend, n: int = extra,
                     paid: dict[str, bool] = done) -> None:
                if paid["yet"] or healed.target != who or healed.source != me:
                    return
                paid["yet"] = True
                healed.amount += n

            c.watch(Healed, more, until=When.EOT, window=Window.BEFORE, on=me)

    c.watch(PowerUsed, spoken, until=When.ENCOUNTER, on=me, label="f757")


@power("f218", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f218(c: Cast) -> None:
    """Charisma on top of what `p1590` restores.

    The feature is named in prose, but `p1590` is the row six feats in this
    file already ride on, so there is a ref to watch for after all --
    `PowerUsed` names the targets and `Healed` is negotiable in the BEFORE
    window, which is the seam f757 uses for the same sentence.

    One bump per target per use: the latch is what stops a second heal
    later in the same turn taking it again.

    A trait, so `AT_WILL` -- the card prints no limit and an
    `action=NONE` row spends a use every firing (#210).
    """
    me = c.me

    def spoken(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != _THE_WORD or c.cha_mod <= 0:
            return
        for friend in ev.targets:
            done: dict[str, bool] = {"yet": False}

            def more(healed: Healed, who: int = friend, n: int = c.cha_mod,
                     paid: dict[str, bool] = done) -> None:
                if paid["yet"] or healed.target != who or healed.source != me:
                    return
                paid["yet"] = True
                healed.amount += n

            c.watch(Healed, more, until=When.EOT, window=Window.BEFORE, on=me)

    c.watch(PowerUsed, spoken, until=When.ENCOUNTER, on=me, label="f218")


@power("f793", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f793(c: Cast) -> None:
    """The same rider on `p1590`, and the card prints the word "power"
    before "bonus". `PowerUsed` names the targets; `Healed` would name
    only whoever the hit points reached."""
    me = c.me

    def spoken(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != _THE_WORD:
            return
        for friend in ev.targets:
            for defence in (AC, FORT, REF, WILL):
                c.bonus(defence, 1, on=friend, until=When.SONT, kind="power")

    c.watch(PowerUsed, spoken, until=When.ENCOUNTER, on=me, label="f793")


@power("f765", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.obscure(level=)",))
def f765(c: Cast) -> None:
    """Softens a racial power's total concealment to partial. `c.conceal`
    grants concealment; nothing reaches into a standing zone and changes
    how thick it is."""
