"""Shaman class features: the spirit companion and the two features whose
whole benefit is a power the tree already carries.

The class page's `cf:shaman-f0cN` refs are not here. Every one of them is a
power card that is already declared under its own `p` ref in
`content/powers/shaman/` -- `cf:shaman-f0c0` and `p6515` are the same printed
block reached from the class page instead of the power list -- so declaring
them would deal a shaman the same card twice. They are an extraction fault
and are left out rather than stubbed.

What the class page genuinely adds is the choice between Companion Spirits,
which is the `cf:shaman-f0sN` run. `chargen.loadout` deals a shaman every
level 0 row its class has, so the choice is only real if the rows the other
spirits hand out are taken *away* -- the same trick `features/builds.py`
plays for the warlord's leader feature.
"""

from __future__ import annotations

from typing import Any, TypedDict

from combat_engine.content.powers.shaman._spirit import beside_spirit, friends
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    PERSONAL,
    REF,
    WILL,
    ActionType,
    Cast,
    Healed,
    Keyword,
    Target,
    TurnStart,
    Usage,
    When,
    Window,
    power,
)
from combat_engine.engine.dsl import Range

PRIMAL = [Keyword.PRIMAL]

#: A trait's header. Every row here is standing text rather than an action,
#: and they all take the same one.
#:
#: **A `TypedDict` rather than a plain one, and that is not decoration.** A
#: plain dict's value type is the union of everything in it, so `@power(
#: **TRAIT, ...)` handed `int | str | Range | Target | list[Keyword]` to every
#: parameter it filled -- one type error per parameter per call site, 245 of
#: them across eight uses, all of it noise from one idiom. `types.py` carried
#: 201 of those as a baseline and the number grew with every row added. #618.
class _Trait(TypedDict):
    level: int
    cls: str
    usage: Usage
    action: ActionType
    reach: Range
    target: Target
    keywords: list[Keyword]


TRAIT: _Trait = {
    "level": 0,
    "cls": "shaman",
    "usage": ENCOUNTER,
    "action": ActionType.NONE,
    "reach": PERSONAL,
    "target": NO_TARGET,
    "keywords": PRIMAL,
}


def _spirit_choice(c: Cast, leg: str, refs: tuple[str, str]) -> None:
    """The half of a Companion Spirit option that is its two rows.

    Granting is nearly a no-op -- `loadout` already dealt them -- so the
    load-bearing branch is the other one: a shaman who chose a different
    spirit loses this one's special attack and its at-will, which is the
    only way "choose one of the following" is true on the board.
    """
    for ref in refs:
        if c.build(leg):
            c.grant_row(ref)
        else:
            # `c.forbid` follows `c.target` and a trait has none.
            c.forbid(ref, until=When.ENCOUNTER, on=c.me)


def _provoked_beside(c: Cast, who: int):  # noqa: ANN202
    """"Provokes an opportunity attack by entering or leaving a square
    adjacent to your spirit companion", as an attack-context gate.

    The attack context carries `opportunity`; which square the ally was
    moving out of it does not carry, so the gate is "still beside the
    spirit as the swing is rolled" -- true for the whole of the leaving
    case, since an opportunity attack interrupts the move.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("opportunity")) and beside_spirit(c, who)

    return gate


@power(
    "cf:shaman-f0",
    **TRAIT,
)
def shaman_f0(c: Cast) -> None:
    """The feature's writable half is the power it hands over.

    **"Your spirit companion must be present when you use such a power" is
    a prerequisite on each power now, not a bar laid here.** Camille, asked
    directly, 2026-11-11:

      > *"this should be a prereq for every power which uses the spirit
      > companion. If that's already present in the powers, no changes
      > required."*

    It was not already present, and the reason this row believed it was is
    worth keeping. This docstring used to say *"the spirit-melee rows are
    gated anyway -- their reach is measured from the companion and cannot
    be measured without one"*. They can: `dsl.measured_from` **falls back
    to the caster**, and says so -- *"falls back to the caster when the
    named thing is not on the board, so a shaman whose spirit has been
    dismissed is simply out of reach rather than throwing from inside
    `legal()`"*. `return mine or [actor]`. So a spirit-melee power with no
    companion was measured from the shaman and still worked, which is
    exactly what the card forbids.

    `_spirit.spirit_present` is the predicate and it is on **65 of the 66**
    spirit powers. The one left out is `p11365`, which is
    `out_of_combat=True` -- a row never offered in a fight, so a
    prerequisite asked mid-fight adds nothing to it.

    **Which also retires the old marker's second hold.** It said the set to
    bar is read from content headers and *"none of the 66 powers the
    database now calls spirit declares the keyword"* -- true, and no longer
    load-bearing: a prerequisite per row needs no keyword to find its rows
    by. `#486`'s header debt is still real and no longer blocks this.

    `c.forbid(when=)` is not wanted either way. The marker asked for a
    refusal evaluated against a live predicate, which is what `requires=`
    already is: asked at the moment of use, every time.

    The Companion Spirit choice is the `cf:shaman-f0sN` rows.
        """
    c.grant_row("p6515")


@power("cf:shaman-f0s0", **TRAIT,)
def shaman_f0s0(c: Cast) -> None:
    """The option `chargen` has been offering with no row behind it.

    **An elemental shaman kept none of the eight spirit powers.** The four
    siblings each `c.forbid` their own pair when their leg is not the one
    taken, which is how "choose one of the following" is true on the board
    -- so with this row absent, every pair was forbidden and this one's two
    were never granted. A drawable build with nothing on it. #588.

    The boon is a save bonus on *allies*, gated on standing beside the
    companion, and the gate is re-asked at each save rather than laid once:
    adjacency is a live condition and the companion moves.

    **The second sentence is written now, and the old note was asking the
    wrong half of the menu.** It said `c.grant_action` is the lever and that
    the menu has no kind for calling a companion -- true, and beside the
    point: the call is not a menu *kind*, it is a declared row, `p6515`, at
    `action=MINOR`. So what the sentence asks for is that row offered a
    second time at a cheaper price, which is `c.recast` and is read by
    `actions._recasts`. The row keeps its own minor-action entry and gains a
    free one; `_recasts` skips a grant whose cost equals the row's own, so
    the two cannot collapse into one.

    "Only while the spirit is away" needs nothing here: `_recasts` asks
    `usable`, and `p6515` carries `requires=_no_spirit`, so the free entry
    disappears the moment the companion is standing there.

    "At the start of your turn ... once during that turn" is why this is a
    `TurnStart` watch rather than a standing grant. A grant laid at arming
    would also pay out on a turn the spirit was present for and then lost
    mid-turn, which the card does not give; laid here it is offered only on
    a turn that *began* without one, and `until=When.EOT` is "during that
    turn". `per_turn=1` is the "once".
    """
    _spirit_choice(c, "elemental", ("p12865", "p12866"))
    if not c.build("elemental"):
        return
    me = c.me
    for mate in friends(c):
        c.bonus(
            "save", 2, on=mate, until=When.ENCOUNTER,
            when=lambda ctx, m=mate: beside_spirit(c, m),
        )

    def spirit_away(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost or c.companion() is not None:
            return
        c.recast(
            "p6515", action=ActionType.FREE, per_turn=1, until=When.EOT, on=me,
        )

    c.watch(
        TurnStart, spirit_away, until=When.ENCOUNTER, on=me,
        label=f"{c.ref} free call",
    )


@power("cf:shaman-f0s1", **TRAIT)
def shaman_f0s1(c: Cast) -> None:
    """The boon is a rider on somebody else's healing, so it is laid as a
    watcher on `Healed` in the before-window, where the amount is still
    negotiable, rather than as a second heal that would count as its own.

    A second wind is a heal whose source is its own target, which is how
    "when he or she uses second wind" is told from a leader's surge.
    """
    _spirit_choice(c, "protector", ("p5389", "p6521"))
    if not c.build("protector") or c.con_mod <= 0:
        return
    me, extra = c.me, c.con_mod

    def more(ev: Healed) -> None:
        if (
            ev.target in friends(c)
            and beside_spirit(c, ev.target)
            and ev.source in (me, ev.target)
        ):
            ev.amount += extra

    c.watch(
        Healed, more, until=When.ENCOUNTER, window=Window.BEFORE, on=me, label=c.ref
    )


@power("cf:shaman-f0s2", **TRAIT)
def shaman_f0s2(c: Cast) -> None:
    """Untyped: the card prints no word in front of "bonus". The gate is
    re-asked at each damage roll, so an ally who walks away from the spirit
    loses it, which "any ally adjacent to your spirit companion" means."""
    _spirit_choice(c, "stalker", ("p5388", "p5510"))
    if not c.build("stalker") or c.int_mod <= 0:
        return
    for mate in friends(c):
        c.bonus(
            "damage",
            c.int_mod,
            on=mate,
            until=When.ENCOUNTER,
            when=lambda ctx, m=mate: beside_spirit(c, m)
            and (victim := ctx.get("target")) is not None
            and c.bloodied(on=victim),
        )


@power("cf:shaman-f0s3", **TRAIT)
def shaman_f0s3(c: Cast) -> None:
    """"Cover from other enemies" is narrower than anything the engine can
    say -- what grants the cover is not in the context the gate is handed --
    so this is `partial=True`, which cancels ordinary cover and leaves
    superior cover standing. Cover from a creature is the ordinary kind.

    **The second sentence is written now, and the old note was right about
    the engine and wrong about why it could not be fixed.** It said
    *"nothing asks or answers which enemy is an ally's nearest, so [the
    clause] has nothing to change"*. Nothing asked -- and six printed
    cards did, each answering it for itself, which is the shape
    `a-marker-may-name-the-writer-when-the-reader-is-the-bug` describes:
    the read was hand-rolled in six places and the marker named the
    writer.

    `query.nearest_enemy` is the one answer now, and
    `dsl.Target.nearest` is a reader of it -- declared by
    `cf:ranger-f1`, whose quarry prints *"the nearest enemy to you that
    you can see"* and was taking any creature. So the permission has
    something to permit, which is the half a modifier needs and the half
    this component most often lacks. #1251.

    **`on=` is each ALLY and `who` is the enemy**, which is the way round
    the card says it: *"**your allies** can treat any enemy adjacent to
    your spirit companion as **their** nearest enemy."* Laid the other way
    it would widen the shaman's own reach and give the allies it is for
    nothing.

    Standing rather than gated, unlike the cover half above: `c.no_cover`
    takes a `when=` because cover is asked per attack, and this is asked
    when a target pool is built -- so the permission is applied to the
    enemies beside the spirit at arming time and ends with the encounter.
    An enemy that walks in afterwards is not covered, which is the same
    limitation `beside_spirit` has and is recorded rather than hidden.
    """
    _spirit_choice(c, "watcher", ("p9732", "p9734"))
    if not c.build("watcher"):
        return
    for foe in c.enemies():
        c.no_cover(
            on=foe,
            until=When.ENCOUNTER,
            partial=True,
            when=lambda ctx, f=foe: beside_spirit(c, f),
        )
        if beside_spirit(c, foe):
            for friend in c.allies():
                c.counts_as_nearest(foe, on=friend, until=When.ENCOUNTER)


@power("cf:shaman-f0s4", **TRAIT)
def shaman_f0s4(c: Cast) -> None:
    """All four defences, which is what "all defenses" says, and untyped."""
    _spirit_choice(c, "world speaker", ("p9733", "p9736"))
    if not c.build("world speaker") or c.con_mod <= 0:
        return
    for mate in friends(c):
        gate = _provoked_beside(c, mate)
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, c.con_mod, on=mate, until=When.ENCOUNTER, when=gate)


@power("cf:shaman-f1", **TRAIT)
def shaman_f1(c: Cast) -> None:
    """The whole benefit is the card, which the tree already carries."""
    c.grant_row("p3773")


@power("cf:shaman-f2", **TRAIT)
def shaman_f2(c: Cast) -> None:
    c.grant_row("p3775")
