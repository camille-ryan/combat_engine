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
Three of these rows turn on which of its two printed states the familiar
is in, and something does hold one: `c.familiar_mode` sets
`Companion.passive`, and a passive familiar is off the board entirely.
Nothing on `Cast` reads it back, so `_familiar` here does -- the same
question `powers/sorcerer.has_familiar` asks.

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
    Companion,
    Keyword,
    Miss,
    PowerResolved,
    Trigger,
    TurnEnd,
    When,
    get,
    power,
)
from combat_engine.engine.events import (
    Bloodied,
    DamageRolled,
    Healed,
)
from combat_engine.engine.query import enemies, team

DIVINE = [Keyword.DIVINE]
ARCANE = [Keyword.ARCANE]

#: The two striker features whose extra damage this batch reads. Both pay
#: through `features/strikers.extra_damage`, which stamps the feature's own
#: ref as the `detail` of the damage it rolls.
STRIKER_DAMAGE = ("cf:rogue-scoundrel-f4", "cf:ranger-f1")


def _familiar(c: Cast, *, passive: bool) -> int | None:
    """The caster's familiar, if it is in the state the card asks for.

    "Active" and "passive" are one flag -- `Companion.passive`, which
    `c.familiar_mode` sets and which decides whether the familiar holds a
    square at all. Nothing on `Cast` reads it back, which is what the
    `c.familiar_state()` markers on this chain were written against.
    """
    fam = c.familiar()
    mine = c.world.get(fam, Companion) if fam is not None else None
    return fam if mine is not None and mine.passive is passive else None


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











#: Each Companion Spirit option and the at-will that comes with it.
#:
#: "The at-will shaman power **associated with that option**" is one
#: particular row per option and not a free pick from the class's list, which
#: is why `c.borrow_row` could not express it: that reads a set by class,
#: level and usage, and this set is none of those. All eleven options are in
#: the index and every at-will they name is declared.
_COMPANION_SPIRIT = {
    "cf:shaman-f0c0": "p6515",
    "cf:shaman-f0c1": "p12866",
    "cf:shaman-f0c2": "p12865",
    "cf:shaman-f0c3": "p6521",
    "cf:shaman-f0c4": "p5389",
    "cf:shaman-f0c5": "p5388",
    "cf:shaman-f0c6": "p5510",
    "cf:shaman-f0c7": "p9734",
    "cf:shaman-f0c8": "p9732",
    "cf:shaman-f0c9": "p9736",
    "cf:shaman-f0c10": "p9733",
}


@power("f668", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f668(c: Cast) -> None:
    """A multiclass feat: the spirit, its at-will, and the daily.

    The hold was never the borrowing -- `c.grant_row` says that -- it was that
    two clauses named their powers in prose. Both have refs now: the daily is
    `p3775`, and the spirit's at-will is whichever of `_COMPANION_SPIRIT` the
    chosen option names.

    The option goes to the decider, like any choice the sheet does not record.
    Both granted rows get `uses=1`: the card gives the at-will "as an
    encounter power" and the daily as one use.
    """
    c.grant_row("p6515", on=c.me, until=When.ENCOUNTER)
    taken = c.choose(sorted(_COMPANION_SPIRIT), f"{c.ref}:spirit")
    if taken:
        c.grant_row(_COMPANION_SPIRIT[taken], on=c.me, until=When.ENCOUNTER,
                    uses=1)
    c.grant_row("p3775", on=c.me, until=When.ENCOUNTER, uses=1)


_granted("f669", "f669b")


@power("f669b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF)
def f669b(c: Cast) -> None:
    """A plain "+2 bonus" to the next damage roll, so untyped and `once`.
    The 11th and 21st steps are out of scope."""
    c.bonus("damage", 2, on=c.me, until=When.EONT, once=True)


@power("f670", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f670(c: Cast) -> None:
    """Another class's oath once per encounter, and the spec names it by
    ref. The granted row is an encounter power of its own, so it carries
    the printed limit and needs no `uses=`.

    The feat shortens the oath to the end of your next turn. Nothing
    re-clocks an effect another row laid, so the shortening is a clock of
    its own: a turn counter carrying the same latch `When.EONT` has --
    sworn on your own turn, the current turn's end is skipped -- which
    then ends every hold p3069 stamped with its ref."""
    c.grant_row("p3069", on=c.me, until=When.ENCOUNTER)

    def sworn(ev: PowerResolved) -> None:
        if ev.actor != c.me or ev.power != "p3069":
            return
        skip = [c.turn_of() == c.me]

        def expire(end: TurnEnd) -> None:
            if end.actor != c.me:
                return
            if skip[0]:
                skip[0] = False
                return
            while c.end_effect(on=c.me, against="p3069") is not None:
                pass

        c.watch(TurnEnd, expire, until=When.ENCOUNTER, on=c.me)

    c.watch(PowerResolved, sworn, until=When.ENCOUNTER, on=c.me)


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
       reach=PERSONAL, target=SELF)
def f740(c: Cast) -> None:
    """"While your familiar is in its passive state" is a gate on the
    bonus rather than a condition of laying it: the familiar goes active
    and passive inside a fight, and a bonus laid once at the start would
    outlive the state it is printed for. `c.bonus(when=)` is read every
    time the defence is, so the +1 comes and goes with the state.

    The card it also grants is `f740b`."""
    c.bonus("ref", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: _familiar(c, passive=True) is not None)
    c.grant_row("f740b", on=c.me, until=When.ENCOUNTER)


def _hurts_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.target == me and ev.amount > 0


@power("f740b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=NO_TARGET,
       keywords=ARCANE, trigger="you are hit by an attack",
       on=Trigger(DamageRolled, _hurts_me, "an attack damages you"),
       dropped=("c.destroy(companion=)",))
def f740b(c: Cast) -> None:
    """Half damage from the triggering attack, and the familiar pays for
    it.

    The Requirement is askable -- `Companion.passive` is the state -- and
    the halving answers `DamageRolled` rather than `Hit`, because `Hit`
    carries no amount and `c.halve` needs one; the blow is announced
    before it is applied, which is the interrupt's window.

    Dropped: the familiar is *destroyed*, and the nearest thing the
    engine has is dismissing it. The two differ out of combat -- a
    destroyed familiar wants a ritual and a dismissed one does not -- so
    the cost is taken as a dismissal and the difference is named rather
    than papered over.
    """
    if _familiar(c, passive=True) is None:
        return
    c.halve(c.trigger)
    c.dismiss_companion()


@power("f741", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f741(c: Cast) -> None:
    """+1 to arcane attacks against targets adjacent to your familiar,
    while it is active.

    Three questions, all asked per roll off the attack context: the
    familiar is active, the row swinging is arcane, and the target is
    beside the familiar. A passive familiar holds no square at all, so
    the adjacency would answer False on its own -- but only because the
    square was taken away, which is not a reading to rely on.

    The card it also grants is `f741b`.
    """
    def beside_it(ctx: dict[str, Any]) -> bool:
        fam = _familiar(c, passive=False)
        row = get(ctx.get("power", "") or "")
        victim = ctx.get("target")
        return (
            fam is not None
            and row is not None
            and Keyword.ARCANE in row.keywords
            and victim is not None
            and c.adjacent_to(fam, victim)
        )

    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=beside_it)
    c.grant_row("f741b", on=c.me, until=When.ENCOUNTER)


def _missed_arcane(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    row = get(ev.power)
    return (
        ev.attacker == me
        and row is not None
        and Keyword.ARCANE in row.keywords
        and row.usage is ENCOUNTER
        and row.attack is not None
    )


@power("f741b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=ARCANE,
       trigger="you miss with an arcane encounter attack power",
       on=Trigger(Miss, _missed_arcane, "you miss with an arcane power"))
def f741b(c: Cast) -> None:
    """Reroll a missed arcane encounter attack, active familiar only.

    A miss is not the end of the roll: `resolve.attack` re-announces the
    outcome when a listener changes it, up to twice, so a reroll taken in
    the free-action window turns the `Miss` into a `Hit` that is properly
    announced. `c.reroll_attack` reads the roll off `c.trigger`, and
    "even if it is lower" is `keep="new"`.
    """
    if _familiar(c, passive=False) is None:
        return
    c.reroll_attack(keep="new")


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
       reach=PERSONAL, target=SELF)
def f768(c: Cast) -> None:
    """Extra damage whenever a named striker feature pays out against the
    target of p1831.

    Something does announce it. Both striker features roll their extra
    damage through `features/strikers.extra_damage`, which stamps the
    feature's own ref as the `detail` of the `DamageRolled` -- so "you
    deal cf:rogue-scoundrel-f4 or Hunter's Quarry damage" is that field,
    and the moment to add to is that roll.

    "The target of your p1831 power" is `c.suffering`, since an effect's
    label is the ref of the row that laid it.
    """
    me = c.me

    def paid(ev: DamageRolled) -> None:
        if ev.source != me or ev.detail not in STRIKER_DAMAGE:
            return
        if ev.target not in c.suffering("p1831") or c.wis_mod <= 0:
            return
        c.flat(c.wis_mod, dtype=ev.dtype, on=ev.target)

    c.watch(DamageRolled, paid, until=When.ENCOUNTER, on=me, label=c.ref)


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
