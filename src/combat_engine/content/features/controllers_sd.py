"""The later controllers' class-page features: the druid's aspect, the
invoker's covenant, the seeker's bond, and three more bonus-feat rituals.

None of these four classes had a single `cf:` row before this file. Their
compendium `Feature` rows -- the wild shape, the two channelled invocations,
the six psionic disciplines, the two bond powers -- were written long ago and
read as the whole of each class page, because nothing anywhere said the page
had a second half. It does: every one of these classes forks on a named
option, and the fork is where the mechanics are.

**The fork is read off the printed riders, not guessed.** Every one of these
classes has attack powers whose extra sentence names an option and an
ability -- Dexterity for one druid aspect and Constitution for another,
Intelligence for one covenant and Constitution for the other, Strength for
one seeker bond and Dexterity for the other -- and `chargen.BUILDS` derives
exactly two legs per class, one per secondary. So the leg a rider asks about
is the leg whose secondary that rider spends, and the rows here ask the same
question the level 1 rows already ask.

Where a class prints **more** options than it has secondaries -- two more for
the druid, three more for the shaman, one more for the runepriest -- the
extra ones have no leg and are in `docs/blocked.json` rather than folded into
a leg that does not mean them.
"""

from __future__ import annotations

from combat_engine.content.chargen import LIGHT
from combat_engine.content.features.builds import on_leg
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Gear,
    Keyword,
    Usage,
    When,
    get,
    power,
)
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.query import alive


def out_of_heavy_armour(c: Cast, who: int | None = None) -> bool:
    """"While you are not wearing heavy armor" -- chain, scale or plate.

    `chargen.LIGHT` names the other three and `Gear.armour` is the only
    place a creature says which it wears. Asked of the live `Gear` rather
    than of the class chassis, because a row elsewhere may have changed it.
    """
    gear = c.world.get(c.me if who is None else who, Gear)
    return gear is not None and gear.armour in LIGHT


@power(
    "cf:druid-aspect",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def druid_aspect(c: Cast) -> None:
    """Which aspect of the beast this druid manifests.

    Four are printed and `chargen.BUILDS["druid"]` carries the two derived
    legs, one per secondary. The two written here are the two the legs mean:
    the class's own riders spend Dexterity for one aspect and Constitution
    for another, and `chargen`'s comment on the derived legs names the same
    pair. The other two are `cf:druid-aspect-rest` in `docs/blocked.json` --
    one reduces melee and ranged damage by a Constitution modifier, which is
    the *same* secondary as the aspect already written, and the other is an
    attack bonus keyed to no ability at all, so neither leg can be asked
    which of the two it is.

    Both halves are gated on staying out of heavy armour, which is the
    printed Requirement on all four. A druid wears hide, so the gate is true
    today; it is asked anyway rather than assumed, because it is the card's
    own sentence and a row elsewhere can change what is worn.

    The armour is read **once**, when the trait is armed, for the same
    reason `cf:warlord-senses` measures its ten squares once: nothing
    re-arms a trait when equipment changes.
    """
    if not out_of_heavy_armour(c):
        return

    if c.build("second-dex"):
        # "+1 bonus to your speed." No bonus type is printed, so untyped.
        c.bonus("speed", 1, until=When.ENCOUNTER, on=c.me, kind="untyped")
        return

    if not c.build("second-con"):
        return

    # "You can use your Constitution modifier in place of your Dexterity or
    # Intelligence modifier to determine your AC." Light armour adds the
    # better of Dexterity and Intelligence (`chargen.defences`), so what the
    # aspect is worth is the difference -- and only when it is a gain, which
    # is what the printed "can" makes it.
    gain = c.con_mod - max(c.dex_mod, c.int_mod)
    if gain > 0:
        c.bonus(AC, gain, until=When.ENCOUNTER, on=c.me, kind="untyped")


@power(
    "cf:druid-rituals",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    out_of_combat=True,
)
def druid_rituals(c: Cast) -> None:
    """A bonus feat that lets the druid perform rituals, and nothing else.

    Deliberately inert, like `cf:cleric-rituals`. Empty rather than a note:
    a trait is run at the start of every fight and a line in the log would
    be announcing something that is not happening.
    """


#: "A divine encounter or daily **attack** power", as the header fields that
#: say so. The manifestation reads them off the resolved row rather than
#: being armed by each one.
_MANIFESTING = (Usage.ENCOUNTER, Usage.DAILY)


@power(
    "cf:invoker-covenant",
    level=0,
    cls="invoker",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def invoker_covenant(c: Cast) -> None:
    """The covenant manifestation: a small thing that happens every time one
    of this invoker's bigger invocations finishes.

    Two covenants are printed and `chargen.BUILDS["invoker"]` carries two
    derived legs. Which is which is read off the class's own riders: rows
    from level 1 to 7 print a covenant and the ability its rider spends, and
    one covenant spends Intelligence in every one of them while the other
    spends Constitution. Those are the two secondaries, so the legs answer.

    **`PowerResolved`, not `PowerUsed`.** The printed line is "after the
    power's effect is resolved", and `PowerUsed` is announced before the
    body runs -- a push hung there would land before the damage that the
    push is supposed to follow. `PowerResolved.rolls` is also the only place
    that says which targets were *hit*, which the push half needs and no
    other event carries for a whole use at once.

    "On your turn" is asked of `c.turn_of`: an invocation used in somebody
    else's turn off an immediate action does not manifest.

    **The Channel Divinity half of the printed feature is not here.** Each
    covenant also hands over one channelled invocation, and the tree has two
    of them (`p5186`, `p7150`) with no way to tell which covenant grants
    which: the specs are sanitised, so neither row says what it is called
    and neither covenant's clause says what its power does. Forbidding the
    wrong one is worse than forbidding neither, so the exclusivity is
    `cf:invoker-covenant-channel` in `docs/blocked.json`.
    """
    me = c.me
    preserving = c.build("second-int")
    if not preserving and not c.build("second-con"):
        return

    def manifests(ref: str) -> bool:
        p = get(ref)
        return (
            p is not None
            and Keyword.DIVINE in p.keywords
            and p.usage in _MANIFESTING
            and p.is_attack
        )

    def after(ev: PowerResolved) -> None:
        if ev.actor != me or c.turn_of() != me or not manifests(ev.power):
            return
        if preserving:
            # "You can slide an ally within 10 squares of you 1 square."
            friends = [a for a in c.within(10, side="ally") if a != me]
            who = c.choose(friends, f"{c.ref}: which ally is moved", optional=True)
            if who is not None:
                c.slide(1, on=who)
            return
        # "You can push one target hit by the power 1 square."
        struck = [
            r.target
            for r in ev.rolls
            if getattr(r, "hit", False) and alive(c.world, r.target)
        ]
        who = c.choose(
            sorted(dict.fromkeys(struck)), f"{c.ref}: which target is pushed",
            optional=True,
        )
        if who is not None:
            c.push(1, on=who)

    c.watch(
        PowerResolved, after, until=When.ENCOUNTER, on=me, label="cf:invoker-covenant"
    )


@power(
    "cf:invoker-rituals",
    level=0,
    cls="invoker",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def invoker_rituals(c: Cast) -> None:
    """A bonus feat that lets the invoker perform rituals, and nothing else.

    Inert for the reason `cf:cleric-rituals` is.
    """


@power(
    "cf:psion-rituals",
    level=0,
    cls="psion",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSIONIC],
    out_of_combat=True,
)
def psion_rituals(c: Cast) -> None:
    """A bonus feat that lets the psion perform rituals, and nothing else.

    Inert for the reason `cf:cleric-rituals` is. The psion's *other* two
    class-page features are elsewhere: the point pool is
    `chargen.CLASSES["psion"].power_points`, and the discipline focus -- six
    declared rows in three mutually exclusive pairs -- has no leg, and is
    `cf:psion-focus` in `docs/blocked.json`.
    """


@power(
    "cf:seeker-bond",
    level=0,
    cls="seeker",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg("second-dex"),
    requires_text="needs the bond this belongs to",
)
def seeker_bond(c: Cast) -> None:
    """The rest of the one seeker bond the class page prints.

    Two bonds, two derived legs, and the pairing is printed outright: eight
    seeker rows from level 1 to 7 carry a bond rider, and every rider on one
    bond spends Dexterity while every rider on the other spends Strength.
    `seeker/level_1.py` and its siblings already ask `c.build("second-dex")`
    and `c.build("second-str")` for exactly those riders.

    **The granted row is not handed over here.** Each bond gives one row and
    `chargen.loadout` deals a seeker both, so the exclusivity is the half
    that has to happen -- and it is `requires=on_leg(...)` in each row's own
    header (`p9500`, `p11462`), not a `c.forbid` from here. The gate needs
    to name only the leg that *should* have the row, where a forbid would
    have to name every leg that should not.

    What is left is the clause that is not a row: a standing minor-action
    shift, which is a line in the action menu rather than a bonus, so
    `c.shift_as` and not `c.bonus`. It is gated on staying out of heavy
    armour, which is the card's own words; a seeker wears leather, so the
    gate is true today and is asked anyway.
    """
    if out_of_heavy_armour(c):
        c.shift_as(ActionType.MINOR, 1, on=c.me, until=When.ENCOUNTER)
