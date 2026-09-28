"""General feats, third batch: the rest of the channelled ones, the
multiclass feats, and the familiar chain.

Three things about this batch are worth knowing before reading it.

**A multiclass feat grants another class's power, and the spec names
it by ref.** It did not: the brief used to print "you can use the
bard's X power" in prose, which the scrubber left alone because the
name is two ordinary words, and there was nothing for `c.grant_row` to
hand over. The refs are in the spec now and the grants are written. A
clause naming a *set* rather than a row -- "choose a 1st-level at-will
of that class" -- is `c.borrow_row`, which reads the set off the
registry and carries the printed once-per-encounter limit.

**The familiar chain is four feats deep and the first one is the gate.**
`c.familiar()` exists and the `companion` table was imported, but a
familiar has two printed *states* -- active and passive -- and nothing
holds one. Three of these rows turn on which state it is in.

**"Once per day" is written as once per encounter**, which is what a day
is to this engine, and each such row says so. See #72.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    CloseBurst,
    Keyword,
    Trigger,
    When,
    get,
    power,
)
from combat_engine.engine.events import Bloodied, Healed
from combat_engine.engine.query import enemies, team

DIVINE = [Keyword.DIVINE]


def _granted(ref: str, card: str):  # noqa: ANN202
    """The parent half of a feat whose whole benefit is the card beside it."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


def _ally_healed(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    from combat_engine.engine.query import distance_between

    return (
        team(world, ev.target) == team(world, me)
        and distance_between(world, me, ev.target) <= 5
    )


def _i_am_bloodied(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me


# -- the last of the channelled cards ---------------------------------------

_granted("f598", "f598b")


@power("f598b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(5), target=ONE_ALLY,
       keywords=[Keyword.DIVINE, Keyword.HEALING], group=CHANNEL_DIVINITY,
       trigger="an ally within 5 squares spends a healing surge",
       on=Trigger(Healed, _ally_healed, "an ally is healed nearby"))
def f598b(c: Cast) -> None:
    """Triggered on the healing rather than on the surge: `Healed` is what
    a spent surge emits, and there is no separate announcement of the
    surge itself."""
    c.heal(max(c.wis_mod, c.int_mod, c.cha_mod), on=c.trigger.target)


_granted("f617", "f617b")


@power("f617b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY,
       out_of_combat=True)
def f617b(c: Cast) -> None:
    """A bonus to knowledge checks. Nothing in a fight turns on one."""


_granted("f723", "f723b")


@power("f723b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="when you become bloodied",
       on=Trigger(Bloodied, _i_am_bloodied, "you become bloodied"))
def f723b(c: Cast) -> None:
    """A plain "+1 bonus" on the card, so untyped."""
    c.bonus("attack", 1, on=c.me, until=When.EONT)
    c.bonus("save", 1, on=c.me, until=When.EONT)


# -- multiclass -------------------------------------------------------------











@power("f668", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("spec.power_ref()",))
def f668(c: Cast) -> None:
    """One multiclass feat whose granted power the spec names by ref, so
    that half is written.

    Re-aimed: the hold is not the borrowing, which `c.grant_row` and
    `c.borrow_row` both say now. It is that the other two clauses name
    their powers in prose -- the at-will that comes with a chosen
    companion spirit, and the daily -- and `c.borrow_row` cannot read a
    set the card does not describe by class, level and usage. The
    spirit's at-will is one particular row per option, not a free pick
    from the class's list, so choosing freely would be a different
    feat."""
    c.grant_row("p6515", on=c.me, until=When.ENCOUNTER)


_granted("f669", "f669b")


@power("f669b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF)
def f669b(c: Cast) -> None:
    """A plain "+2 bonus" to the next damage roll, so untyped and `once`.
    The 11th and 21st steps are out of scope."""
    c.bonus("damage", 2, on=c.me, until=When.EONT, once=True)


@power("f670", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.end_effect()",))
def f670(c: Cast) -> None:
    """Another class's oath once per encounter, and the spec names it by
    ref. The granted row is an encounter power of its own, so it carries
    the printed limit and needs no `uses=`.

    Dropped: the feat shortens the oath to the end of your next turn,
    and nothing cuts a duration another row laid."""
    c.grant_row("p3069", on=c.me, until=When.ENCOUNTER)


@power("f671", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(1), target=NO_TARGET)
def f671(c: Cast) -> None:
    """Mark every adjacent enemy until the end of your next turn. The one
    multiclass feat in this batch whose benefit is written out rather
    than named, so it needs no ref at all."""
    for foe in enemies(c.world, c.me):
        if c.adjacent(foe):
            c.mark(on=foe, until=When.EONT)


# -- the familiar chain -----------------------------------------------------


@power("f738", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.familiar(defences=)",))
def f738(c: Cast) -> None:
    """The gate of the chain: you have a familiar. The rider -- a defence
    bonus per further familiar feat -- counts feats a character has, and
    `c.feat` answers one at a time rather than a family."""
    c.familiar()


@power("f739", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f739(c: Cast) -> None:
    """Telepathy with your familiar. Conversation, not combat."""


@power("f740", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.familiar_state()",))
def f740(c: Cast) -> None:
    """The +1 Reflex half, which the card's own Requirement gates on the
    familiar's passive state -- a state nothing holds. The bonus is
    written; the card it also grants is `f740b`."""
    c.bonus("ref", 1, on=c.me, until=When.ENCOUNTER)
    c.grant_row("f740b", on=c.me, until=When.ENCOUNTER)


@power("f740b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=NO_TARGET,
       keywords=[Keyword.ARCANE], todo=("c.familiar_state()",))
def f740b(c: Cast) -> None:
    """Half damage from the triggering attack, and the familiar is
    destroyed. Its Requirement is a familiar state nothing holds, so
    writing the halving alone would make it free."""


@power("f741", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.familiar_state()",))
def f741(c: Cast) -> None:
    """+1 to arcane attacks against targets adjacent to your familiar,
    while it is active. Both halves need the state."""


@power("f741b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.ARCANE],
       todo=("c.familiar_state()",))
def f741b(c: Cast) -> None:
    """Reroll a missed arcane encounter attack. Gated on the same state."""


# -- the rest ---------------------------------------------------------------


@power("f734", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f734(c: Cast) -> None:
    """A feat bonus to attack with one *type* of implement -- rod, staff,
    wand. The engine has one implement group and not the printed types,
    so the choice collapses to "your implement", which is what a
    character carrying one implement means anyway."""
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: (
            (p := get(ctx.get("power", ""))) is not None
            and Keyword.IMPLEMENT in p.keywords
        ),
    )


@power("f768", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_extra_damage()",))
def f768(c: Cast) -> None:
    """Extra damage whenever a named striker feature pays out against the
    target of one named power. Nothing announces that a striker feature
    fired, so there is no moment to add to."""


@power("f800", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.disadvantage(on=)",))
def f800(c: Cast) -> None:
    """Opportunity attacks made against you during a run roll twice and
    take the lower. `c.reroll_attack(keep="worst")` is the same idea for
    the roll you just made; nothing imposes it on somebody else's."""


@power("f651", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.darkvision()",))
def f651(c: Cast) -> None:
    """A campaign-setting option offering a choice of three traits.

    Re-aimed off the multiclass symbol, which was never what this row
    wanted: its three options are spelled out in full rather than named,
    so there is no feature to borrow and nothing to look up. Two of the
    three have no verb -- switchable darkvision of 1 square, and adding
    to the reach of one attack -- and `c.choose` among three where two
    do nothing would quietly make the third compulsory. The speed option
    alone is writable and is a third of the card, so the row stays
    refused rather than playing a third of itself."""
