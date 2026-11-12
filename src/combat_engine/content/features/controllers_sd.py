"""The later controllers' class-page features: the druid's aspect, the
invoker's covenant, cf:seeker-f1, and three more bonus-feat rituals.

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

Where a class printed **more** options than it had secondaries -- two more
for the druid, three more for the shaman, one more for the runepriest --
`chargen.BUILDS` now carries a leg per printed option, named for that
option's own ref. So the druid asks `c.build("f1s0")` where it used to ask
`c.build("second-con")`, and all four aspects are told apart.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.chargen import LIGHT
from combat_engine.content.features.builds import on_leg
from combat_engine.content.powers.druid.forms import in_beast_form
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
from combat_engine.engine.events import PowerResolved, SurgeSpent
from combat_engine.engine.query import Position, alive, spread, team
from combat_engine.engine.zones import Zone


def out_of_heavy_armour(c: Cast, who: int | None = None) -> bool:
    """"While you are not wearing heavy armor" -- chain, scale or plate.

    `chargen.LIGHT` names the other three and `Gear.armour` is the only
    place a creature says which it wears. Asked of the live `Gear` rather
    than of the class chassis, because a row elsewhere may have changed it.
    """
    gear = c.world.get(c.me if who is None else who, Gear)
    return gear is not None and gear.armour in LIGHT


#: "Melee attacks and ranged attacks", which is three of the reach kinds
#: short of everything: a close burst is neither, and the card names only
#: the two. The damage context carries `power` and no `attacker`, so the
#: reach is read off the declared row, which is where `reach.kind` lives.
_STRUCK = ("melee", "ranged")


def _struck_in_form(c: Cast) -> Callable[[dict[str, Any]], bool]:
    """The gate the beast-form aspect reduces damage behind."""
    me, world = c.me, c.world

    def gate(ctx: dict[str, Any]) -> bool:
        if not in_beast_form(world, me):
            return False
        dealt = get(ctx.get("power") or "")
        return dealt is not None and dealt.reach.kind in _STRUCK

    return gate


#: The four keywords the fourth aspect names.
_ELEMENTS = (Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING, Keyword.THUNDER)


def _elemental_druid_row(ctx: dict[str, Any]) -> bool:
    """"Druid attack powers ... with the cold, fire, lightning or thunder
    keywords." The class is asked off the row rather than assumed: a druid
    holding a racial or a feat card gets no bonus from this aspect."""
    rolling = get(ctx.get("power") or "")
    if rolling is None or rolling.cls != "druid" or rolling.attack is None:
        return False
    return any(k in rolling.keywords for k in _ELEMENTS)


@power(
    "cf:druid-f1",
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

    Four are printed and `chargen.BUILDS["druid"]` now carries four legs,
    one per printed option and named for its ref, so all four are written
    here and each refuses itself on the three it is not.

    Every one of them is gated on staying out of heavy armour, which is the
    printed Requirement on all four. A druid wears hide, so the gate is true
    today; it is asked anyway rather than assumed, because it is the card's
    own sentence and a row elsewhere can change what is worn.

    The armour is read **once**, when the trait is armed, for the same
    reason `cf:warlord-marshal-f2` measures its ten squares once: nothing
    re-arms a trait when equipment changes.

    **The fourth aspect asks beast form inside the gate, not outside it.**
    A druid is in its humanoid shape when traits are armed, so measuring it
    here would switch the reduction off for the whole fight; the damage
    context is consulted at the moment damage lands, which is when the
    printed "while you are in beast form" is asked.
    """
    if not out_of_heavy_armour(c):
        return

    if c.build("f1s1"):
        # "+1 bonus to your speed." No bonus type is printed, so untyped.
        c.bonus("speed", 1, until=When.ENCOUNTER, on=c.me, kind="untyped")
        return

    if c.build("f1s2"):
        if c.con_mod > 0:
            c.resist(c.con_mod, until=When.ENCOUNTER, on=c.me, when=_struck_in_form(c))
        return

    if c.build("f1s3"):
        # "Druid attack powers ... that have the cold, fire, lightning, or
        # thunder keywords." Untyped: the card prints no type word.
        c.bonus("attack", 1, until=When.ENCOUNTER, on=c.me, when=_elemental_druid_row)
        return

    if not c.build("f1s0"):
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
    "cf:druid-f2",
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

    Deliberately inert, like `cf:cleric-templar-f3`. Empty rather than a note:
    a trait is run at the start of every fight and a line in the log would
    be announcing something that is not happening.
    """


# ------------------------------------------------- druid: the protector
#
# The class's second chassis, and the first in this tree whose fork is the
# **same choice** the base class already makes: a protector's circle *is*
# one of the four aspects above, so `cf:druid-protector-f0s0` restates what
# `cf:druid-f1`'s first branch pays and adds a second clause to it. The
# circles are therefore legs -- `c.build("f1s0")` -- and not
# `chargen.BUILD_OPTIONS`, which is the opposite call from the witch's
# coven and the berserker's heartland, and for the opposite reason: there
# the leg was already spent, and here the leg *is* the printed choice.
#
# Two of the four aspects are circles and two are not, which
# `chargen.LEG_CHASSIS["druid"]` records by naming only the two the
# protector does **not** have. A leg left out of that table falls open to
# every chassis, and "open to both" is exactly what the other two are.

#: The zone `p15852` lays, found by the exemption word it carries rather
#: than by a label: the row passes `difficult=c.ref`, so the ref is already
#: on the zone and nothing in `powers/druid/level_0.py` has to change to
#: make it findable.
_GROWTH = "p15852"


def _growth_ground(c: Cast) -> frozenset:
    """"In your p15852 zone or adjacent to it" -- the zone's squares, plus
    the ring around them.

    `spread(squares, 1)` is inclusive, which is what makes one call answer
    both halves of the printed "or". Empty when the zone is not up, so the
    clause costs nothing on a board where the druid never laid it.
    """
    ground: set = set()
    for zid in c.my_zones():
        zone = c.world.get(zid, Zone)
        if zone is not None and zone.difficult == _GROWTH:
            ground |= set(zone.squares)
    return spread(ground, 1) if ground else frozenset()


@power(
    "cf:druid-protector-f0",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def protector_circle(c: Cast) -> None:
    """*"Choose a druid circle. You gain the benefits of that circle."*

    A **parent**, but one whose choice was already made: the circle is the
    leg, so this reads `c.build` rather than `c.chosen_option` and there is
    no `chargen.BUILD_OPTIONS` entry for it. Both circles are declared
    below, so this grants rather than repeating what they say.

    The fall-back is the first circle and not "nothing". A protector
    without a circle is a character missing the one feature its fork exists
    to choose, which is the harm `chargen.legs_for` is written to avoid;
    `cf:wizard-witch-f1` defaults the same way for the same reason.
    """
    circle = "cf:druid-protector-f0s1" if c.build("f1s1") else "cf:druid-protector-f0s0"
    c.grant_row(circle, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:druid-protector-f0s0",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def protector_circle_con(c: Cast) -> None:
    """One circle: Constitution for AC, and a surge in the zone heals more.

    The first clause is `cf:druid-f1`'s first branch word for word, written
    out again rather than reached for. That is not duplication to be tidied
    away: a protector is not dealt `cf:druid-f1` -- a named chassis
    supersedes the blank rows, which is what `superseded_for` is -- so if
    this row did not pay the clause, nobody would. The reading is the same
    one `cf:warden-f1` gives and `_ability_for_ac` in `guardians.py`
    records: light armour already takes the better of Dexterity and
    Intelligence, so the substitution is worth the difference and only when
    the difference is a gain, which is what the printed "can" makes it.

    The second clause is this circle's own. *"When any ally in your p15852
    zone or adjacent to it spends a healing surge ... he or she regains
    additional hit points equal to your Constitution modifier."*

    **"Any ally" is read as not the druid**, which is the edition's own
    sense of the word, so the watch declines `ev.actor == me`. And the
    ground is measured **when the surge is spent**, not when the trait
    arms: `p15852` is a minor-action zone the druid has usually not laid
    yet at the top of the fight, and measuring at arming would make the
    clause pay nothing for the whole encounter.

    **The circle is refused in the body and not in an `on_leg` header**,
    and that cost a measurement to get right. A header here reads as *"this
    row belongs to leg `f1s0`"*, which `chargen.legs_for` believes: it
    attributed the leg to the **protector** and took it off the base druid,
    so `legs_for("druid", "original")` came back `('f1s2', 'f1s3')` and
    `cf:druid-f1`'s first two branches became unreachable for the class
    that prints them. A leg shared by two chassis cannot be attributed to
    either -- `LEG_CHASSIS` maps a leg to one chassis -- so the only way to
    say "both" is to attribute it to nobody and let it fall open, which is
    `legs_for`'s own fail-open rule. `cf:druid-f1` gates the same four legs
    in its body for the same reason, and this row is the sibling of that
    branch.
    """
    me, world = c.me, c.world
    if not c.build("f1s0"):
        return
    if out_of_heavy_armour(c):
        gain = c.con_mod - max(c.dex_mod, c.int_mod)
        if gain > 0:
            c.bonus(AC, gain, until=When.ENCOUNTER, on=me, kind="untyped")

    amount = c.con_mod
    if amount <= 0:
        return

    def on_surge(ev: SurgeSpent) -> None:
        if ev.actor == me or not alive(world, ev.actor):
            return
        if team(world, ev.actor) is not team(world, me):
            return
        where = world.get(ev.actor, Position)
        if where is None or where.square not in _growth_ground(c):
            return
        c.heal(amount, on=ev.actor)

    c.watch(SurgeSpent, on_surge, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:druid-protector-f0s1",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def protector_circle_speed(c: Cast) -> None:
    """The other circle: +1 speed, and allies walk through the zone.

    The first clause is `cf:druid-f1`'s second branch, written out again
    for the reason the sibling above records.

    The second needed nothing built. `p15852` lays its zone with
    `difficult=c.ref` and exempts the druid with
    `c.ignores_difficult(c.ref)` -- the exemption is per-creature and takes
    an `on=`, so this circle is the same call once per ally. The zone does
    not have to be up yet: the exemption is a standing fact about the
    creature and `query.difficult_at` asks it when somebody walks.

    Allies are taken at arming, which is the one thing here that is a
    reading rather than the card. The printed "your allies" is the party,
    and a party does not change inside a fight -- a creature that joins
    one mid-fight is a summon, and a summon's own entry says how it moves.

    Refused in the body, not in a header -- the sibling above records why,
    and it is the one thing in this chassis that a wrong call would have
    broken silently for the **base** druid rather than for the protector.
    """
    me = c.me
    if not c.build("f1s1"):
        return
    if out_of_heavy_armour(c):
        c.bonus("speed", 1, until=When.ENCOUNTER, on=me, kind="untyped")
    for friend in c.allies():
        c.ignores_difficult(_GROWTH, on=friend, until=When.ENCOUNTER)


@power(
    "cf:druid-protector-f1",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
)
def protector_grasping_claws(c: Cast) -> None:
    """"You gain the p15852 power."

    A no-op grant: `p15852` is declared `cls="druid"` at level 0, so
    `chargen.loadout` has already dealt it. Written out because both
    circles above are about that zone and a reader following them needs to
    land somewhere. `#1259`.
    """
    c.grant_row(_GROWTH, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:druid-protector-f2",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    todo=("chargen.power_choice()",),
)
def protector_attunement(c: Cast) -> None:
    """"You gain three Primal Attunement powers of your choice."

    A draw and not a combat clause: three rows out of a named printed
    category, chosen at creation. `chargen.power_choice()` is the symbol
    four feats already wait on (`f3582`, `f3588`, `f3616`, `f3646`) and it
    is the same gap -- nothing lets a row say "deal me N of this family".

    `todo=` and not `dropped=`, because the row has no other clause: there
    is nothing here that plays.
    """


@power(
    "cf:druid-protector-f3",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    dropped=("chargen.ladder_swap(daily)",),
)
def protector_summon(c: Cast) -> None:
    """"You gain the p15858 power", and the ladder it is paid for out of.

    The grant is the no-op `-f1` is. What is **not** written is the price:
    *"Because of this feature, you do not gain a druid attack power at
    level 5, 9, 15, 19, 25, or 29. Instead ... at level 5 you can use
    p15858 twice per day, and at level 9 three times per day."*

    Two halves and neither has a writer. `chargen.EXTRA_GAINS` is the
    table that says what a feature *adds* at a level and there is no table
    that says what one **takes away** -- the ladder is derived from the
    class, not declared per row. And `Powers.per_day` counts uses per ref,
    so the rising allowance is expressible, but granting it without
    charging for the six lost powers makes a protector strictly stronger
    than print, which is the wrong direction to land half of. One symbol,
    because the two halves are one printed bargain and a row that paid the
    second alone would be wrong.

    The grant itself plays, so this is `dropped=` and not `todo=`.
    """
    c.grant_row("p15858", on=c.me, until=When.ENCOUNTER)


@power(
    "cf:druid-protector-f3s0",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    todo=("chargen.power_choice()",),
)
def protector_summon_list_con(c: Cast) -> None:
    """Which creatures this circle's p15858 can summon: a printed list of
    two at level 1, two more at 15 and two more at 29.

    The same gap as `-f2` and the same symbol. `p15858`'s own block prints
    no numbers at all -- `summon_of_your_aspect` takes `Summon`'s defaults
    and says so -- so the six named creatures are six stat blocks the
    summon would have to choose between, and nothing lets a row offer a
    choice among printed options at summon time.

    Declared rather than left out, because the list is what makes the two
    circles differ at level 15 and a reader looking for it should find a
    row saying so.
    """


@power(
    "cf:druid-protector-f3s1",
    level=0,
    cls="druid",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    todo=("chargen.power_choice()",),
)
def protector_summon_list_speed(c: Cast) -> None:
    """The other circle's p15858 list, and the sibling above holds the
    reasoning."""


#: "A divine encounter or daily **attack** power", as the header fields that
#: say so. The manifestation reads them off the resolved row rather than
#: being armed by each one.
_MANIFESTING = (Usage.ENCOUNTER, Usage.DAILY)


@power(
    "cf:invoker-f1",
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

    Three covenants are printed and this writes two of them, one per named
    leg of `chargen.BUILDS["invoker"]`. Which manifestation belongs to which
    leg is not a guess: each covenant's spec names the channelled card it
    hands over, and `cf:invoker-f1c0` says outright which covenant it is a
    power of. So the slide is the preserving leg and the push is the
    maledicting one. The third leg's manifestation -- a damage bonus per
    enemy the invocation caught -- is `cf:invoker-f1s2`, and this row laid
    the push on that leg as well, which gave a wrath invoker two arms of a
    fork that prints "choose one".

    **`PowerResolved`, not `PowerUsed`.** The printed line is "after the
    power's effect is resolved", and `PowerUsed` is announced before the
    body runs -- a push hung there would land before the damage that the
    push is supposed to follow. `PowerResolved.rolls` is also the only place
    that says which targets were *hit*, which the push half needs and no
    other event carries for a whole use at once.

    "On your turn" is asked of `c.turn_of`: an invocation used in somebody
    else's turn off an immediate action does not manifest.

    **The preserving leg's channelled invocation is handed over here.**
    `cf:invoker-f1c0` is declared as that covenant's power and nothing was
    granting it, so it sat on the board belonging to nobody;
    `cf:invoker-f1s2` grants the wrath leg's card itself. The maledicting
    leg's channelled invocation is still unplaceable -- the two candidates
    in the tree (`p5186`, `p7150`) say neither what they are called nor
    which covenant they answer to -- and forbidding the wrong one is worse
    than forbidding neither, so that half stays
    `cf:invoker-covenant-channel` in `docs/blocked.json`.
    """
    me = c.me
    # **The legs are named, not derived.** This read `c.build("second-int")`
    # and `c.build("second-con")`, which are the legs `chargen` mints
    # automatically for a class whose secondary ability is a choice. The
    # invoker is a hand-written entry in `chargen.BUILDS` and its legs are
    # `wrath`, `preservation` and `malediction` -- so both calls answered
    # False for every invoker ever built, this returned on its second line,
    # and the covenant manifestation did nothing in any fight since it was
    # written. Twenty call sites in `content/powers/invoker/` already ask
    # the right way; only this one did not.
    preserving = c.build("preservation")
    if not preserving and not c.build("malediction"):
        return
    # **The channelled card is dealt by `chargen.loadout`, not by this.**
    # Both covenant cards are level-0 rows of the class, so every invoker
    # already knows both and `c.grant_row` returns `None`. The sentence
    # worth writing is therefore the one on the legs that *lose* the card,
    # which is the judgement `cf:barbarian-f1` records for the same shape.
    c.grant_row("cf:invoker-f1c0")
    if not preserving:
        c.forbid("cf:invoker-f1c0", until=When.ENCOUNTER, on=me)
    c.forbid("cf:invoker-f1c1", until=When.ENCOUNTER, on=me)

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
        PowerResolved, after, until=When.ENCOUNTER, on=me, label="cf:invoker-f1"
    )


@power(
    "cf:invoker-f2",
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

    Inert for the reason `cf:cleric-templar-f3` is.
    """


@power(
    "cf:psion-f2",
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

    Inert for the reason `cf:cleric-templar-f3` is. The psion's *other* two
    class-page features are elsewhere: the point pool is
    `chargen.CLASSES["psion"].power_points`, and the discipline focus -- six
    declared rows in three mutually exclusive pairs -- has no leg, and is
    `cf:psion-focus` in `docs/blocked.json`.
    """


@power(
    "cf:seeker-f1",
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
