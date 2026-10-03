"""The warden's three class-page features.

Nothing recorded any of the three before this file: no implementation, no
`Feature` row of their own, and no `docs/blocked.json` entry -- so the tree
looked complete while the warden took no turn-start save, marked nobody and
got no AC out of its own fork.

`chargen.loadout` deals a class every level 0 row it has, so the "you gain
<power>" half of the third one is already done. What is left is the half
that is not a grant: a save, a mark, and a modifier.

The swordmage's ward is **not** here. Its whole printed content is the
granted row, three of them are dealt, and the page identifies only one --
so there is no leg for `requires=on_leg(...)` to name and nothing else to
write. `cf:swordmage-f1` in `docs/blocked.json`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Keyword,
    When,
    power,
)
from combat_engine.engine.events import TurnStart


@power(
    "cf:warden-f0",
    level=0,
    cls="warden",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def warden_font(c: Cast) -> None:
    """A second saving throw, taken at the start of the turn instead of its end.

    The printed consequences -- a stun that ends before it costs the turn,
    ongoing damage avoided rather than suffered -- are all downstream of
    *when* the throw is made, so rolling it here is the whole feature.
    `c.save` follows `c.target` and a trait has none, hence `on=c.me`.

    "You can" is not asked: an extra throw against a save-ends effect is
    never worse than not taking it, and `Effects` still offers the ordinary
    end-of-turn one when this fails.

    Which effect it answers is left to `c.save`, which takes the first
    save-ends hold it finds. The card says "one effect" and gives the
    warden the choice; nothing in `c.save` takes a list, so the choice is
    not offered rather than being made wrongly on the warden's behalf.
    """
    me = c.me

    def at_start(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            c.save(on=me)

    c.watch(TurnStart, at_start, until=When.ENCOUNTER, on=me, label="cf:warden-f0")


@power(
    "cf:warden-f1",
    level=0,
    cls="warden",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def warden_might(c: Cast) -> None:
    """The fork's first sentence, which is the same on all four legs but for
    which ability it names.

    Two of the printed options substitute Constitution and two substitute
    Wisdom. `chargen.BUILDS["warden"]` is a named leg per option, so the
    pair on each side is asked for by name; it read `c.build("second-con")`
    against the derived legs the class no longer has, which was false for
    every warden and gave every warden in the tree the Wisdom branch.

    It is written as an untyped bonus of the difference because that is
    what a replacement comes to: `chargen.defences` gives light armour the
    better of Dexterity and Intelligence, and this adds whatever the named
    ability is worth over that. Nothing else in the tree lays an untyped AC
    modifier for the same reason, so there is nothing for it to collide
    with. Zero or less is not applied, which is the printed "you can".

    **"While you are not wearing heavy armor" is not gated.** `Build`
    records no armour -- the same gap `cf:fighter-talent-rest` names -- and
    the warden chassis is hide on every leg, so the clause is true for
    every warden `chargen` deals and a gate would only be a thing that
    cannot yet be false.

    **The second sentence is not here**; see `cf:warden-f1-rest` in
    `docs/blocked.json`. All four options hang a different rider on the
    warden's second wind, and each rider is written on the option's own row --
    `cf:warden-f1s0` to `f1s3` in `features/guardians.py` -- rather than here,
    because this row is the half that is true whichever was taken. (That note
    used to say the legs "cannot tell the Constitution pair apart"; there are
    four legs now, one per option, so they can.)
    """
    # **The Constitution pair is the first and third option, not the first
    # two.** The page prints Constitution, Wisdom, Constitution, Wisdom, and
    # this read the two legs that `chargen.BUILDS` happened to list first --
    # which were the two whose secondary said Constitution, because that list
    # was grouped by ability while its names were in page order. So one option
    # substituted Constitution for AC where its own text says Wisdom. #337.
    on_con = c.build("f1s0") or c.build("f1s2")
    instead = c.con_mod if on_con else c.wis_mod
    gain = instead - max(c.dex_mod, c.int_mod)
    if gain > 0:
        c.bonus(AC, gain, until=When.ENCOUNTER, on=c.me, kind="untyped")


@power(
    "cf:warden-f2",
    level=0,
    cls="warden",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def warden_wrath(c: Cast) -> None:
    """The marking half of the defender's job, which nothing was doing.

    `p5093` and `p5094` both trigger on "an enemy **marked by you**", and
    the warden had no way to mark anybody -- so both rows were standing
    threats against a condition that never arose. This is the sentence that
    arms them.

    Taken at the start of the turn rather than anywhere in it. The printed
    line is "once during each of your turns, as a free action", and the
    turn's start is the only moment a trait can pick without a model of
    when in a turn a free action is spent; it is also the moment that makes
    the mark worth the most, which is what a warden would choose.

    One mark per creature is the relation's own rule, so re-marking an
    enemy that is already carrying this warden's mark simply refreshes it.
    """
    me = c.me

    def at_start(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        adjacent = [e for e in c.enemies() if c.adjacent(e)]
        if not adjacent or not c.may("mark every adjacent enemy", who=me):
            return
        for enemy in adjacent:
            c.mark(on=enemy, until=When.EONT)

    c.watch(TurnStart, at_start, until=When.ENCOUNTER, on=me, label="cf:warden-f2")


