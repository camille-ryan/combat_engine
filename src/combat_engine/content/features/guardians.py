"""The sub-options of five classes' page features, and the paladin's budget.

Everything here came out of the extractor as a **sub-option**: a build
choice printed inside a feature's section, or a power card printed under
it. They are ordinary rows and are written as ordinary rows.

Thirteen of the refs in this batch are not declared anywhere, on purpose.
A card printed inside a feature's section is usually a card the compendium
also prints on its own page and the tree already has -- the paladin's mark
is `p805`, the warden's two answers to being ignored are `p5093` and
`p5094` -- and a sub-option is often a branch its parent already carries.
`chargen.loadout` deals a character every level 0 row of its class, so a
second copy is two uses of one encounter power, or an untyped bonus laid
twice and therefore doubled. Those refs are an extraction fault and are
being fixed there rather than papered over with rows whose whole job would
be to do nothing.

What is left is real, and it is most of what was blocked: the warden's four
second-wind riders, two of the three runepriest traditions, the seeker's
second bond, and the marauder ranger's bonus feat.

**Where a printed choose-one has more options than `chargen.BUILDS` has
legs**, `_takes_the_option` decides it once per fight and every sibling
reads the same answer. The runepriest is the one class here that needs it:
three traditions over two derived legs. The warden has four named legs for
its four options, so those are ordinary `requires=` gates.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Cast,
    Gear,
    Keyword,
    When,
    power,
)
from combat_engine.engine.events import DamageApplied, Miss, SecondWind
from combat_engine.engine.query import team

from .builds import on_leg
from .controllers_sd import out_of_heavy_armour
from .strikers import BEAST_STYLE, MARAUDER_STYLE

#: The two thrown properties, which is how a weapon says it is one of the
#: pair the seeker's second bond pays for.
THROWN = frozenset({"light thrown", "heavy thrown"})


def _takes_the_option(c: Cast, label: str, siblings: tuple[str, ...]) -> bool:
    """Which of a printed choose-one set this character took, decided once.

    `requires=on_leg(...)` narrows a fork to the options that share an
    ability and no further, so without this both of a pair arm and the
    character gets two riders where the card prints one.

    The choice is made by `c.choose` the first time any sibling arms and
    written down as a hold, so every later sibling reads the same answer
    rather than asking again. **The asking row is offered first**, which is
    what lets each of them be driven on its own: `World.decide` takes the
    head of the list, so a row audited alone picks itself, and a whole
    character's rows still agree on exactly one.
    """
    for held in c.world.effects.of(c.me):
        if held.label.startswith(label):
            return held.label == f"{label} {c.ref}"
    rest = [ref for ref in siblings if ref != c.ref]
    picked = c.choose([c.ref, *rest], f"{label}: which option")
    if picked is None:
        return False
    c.effect(f"{label} {picked}", until=When.ENCOUNTER, on=c.me)
    return picked == c.ref


def _ability_for_ac(c: Cast, instead: int) -> int:
    """"You can use <ability> in place of your Dexterity or Intelligence
    modifier to determine your AC", as an untyped modifier.

    The same reading `cf:warden-f1` gives: `chargen.defences` already takes
    the better of Dexterity and Intelligence for light armour, so the
    substitution is worth the difference and nothing when the difference is
    not in its favour, which is the printed "you can".
    """
    return instead - max(c.dex_mod, c.int_mod)


# -- paladin ----------------------------------------------------------------


@power(
    "cf:paladin-f0",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def paladin_channel(c: Cast) -> None:
    """The once-a-fight allowance, which is a header field on the rows that
    spend it rather than anything this row can lay.

    "Regardless of how many different uses you know, you can use only one
    such ability per encounter" is `group=`: `CHANNEL_DIVINITY` in this
    package's `__init__`, enforced by `dsl._group_spent`, which refuses a
    row the moment any sibling carrying the same string has been used. Two
    classes and the divinity feats already carry it, so the budget is in
    force whether this row plays or not.

    The feature grants no power of its own -- the abilities are the class's
    own rows and the feats', each declared separately -- so there is
    nothing left for this row to do, and the flag says so rather than
    leaving it looking unwritten.
    """


@power(
    "cf:paladin-f1",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    out_of_combat=True,
)
def paladin_mark_feature(c: Cast) -> None:
    """"You can use `p805` to mark an enemy of your choice", and that is the
    whole printed benefit.

    `p805` is a level 0 paladin row, so `chargen.loadout` has already dealt
    it to every paladin and `c.grant_row` returns `None` for one of those
    by its own rule -- its docstring says outright that it is not the tool
    for a build's own rows. There is no exclusivity to enforce either:
    unlike the warlord's leader features, every paladin has this one.
    """


@power(
    "cf:paladin-f2",
    level=0,
    cls="paladin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
    out_of_combat=True,
)
def paladin_hands_feature(c: Cast) -> None:
    """"Using `p1566`, paladins can grant their comrades resilience." Inert
    for the reason `cf:paladin-f1` is: the row is the paladin's own and
    every paladin already knows it.
    """


# -- ranger -----------------------------------------------------------------


@power(
    "cf:ranger-f0s0",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    todo=("c.bonus_feat()",),
)
def ranger_style_ranged(c: Cast) -> None:
    """One of the five fighting styles, and its whole benefit is a bonus
    feat the spec names in prose and not by ref.

    The tree has feats and `c.grant_row` can hand one over, so the gap is
    not a verb: it is that the extractor resolved one style's feat to an id
    -- `cf:ranger-f0s3` is handed `f172` outright -- and left this one's as
    a printed name, which is the one thing this project may not go and look
    up. `c.bonus_feat()` is the symbol for "grant the feat this line
    names", and both ranger styles here that are a bonus feat and nothing
    else want it.
    """


@power(
    "cf:ranger-f0s1",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=on_leg(BEAST_STYLE),
    requires_text="needs the fighting style that keeps a beast",
    todo=("c.beast_attacks()", "c.quarry(nearest=False)"),
)
def ranger_style_beast(c: Cast) -> None:
    """The companion style. The beast itself is already on the board --
    `cf:ranger-f0` calls `c.call_beast()` on this leg -- so what is left
    here is the pair of clauses that change `cf:ranger-f1`, and both of
    them need the beast to act.

    "Your quarry can be the enemy nearest to your beast companion" is a
    second origin for the nomination; `c.quarry` measures from the ranger
    and takes no other anchor, and `ranger_c` already named
    `c.quarry(nearest=False)` for the same hold.

    "You or your beast companion can deal the extra damage, but only one of
    you per round" is the half that cannot be faked. The companion is
    correct on every number and never takes a turn (issue #212), so a rider
    paying out on the beast's hit would be a clause with no case, and a
    once-a-round budget shared between two creatures when only one of them
    ever swings is the ranger's own rider with extra machinery. Marked
    rather than written.

    The exclusivity -- this style gives up the shared ranged bonus -- is
    already `_keeps_prime_shot` on `cf:ranger-f2`, and the ritual is not a
    combat clause.
    """


@power(
    "cf:ranger-f0s3",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=on_leg(MARAUDER_STYLE),
    requires_text="needs the fighting style that runs",
)
def ranger_style_marauder(c: Cast) -> None:
    """The one style whose bonus feat the extractor resolved to a ref.

    `f172` is a general feat, `cls=""`, so `chargen.loadout` never deals it
    to a ranger and `c.grant_row` has something to do -- unlike every other
    "you gain <power>" line in this file, all of which name a row of the
    character's own class.

    **Granting a trait is not arming it.** `Encounter.arm_traits_of` walks
    a snapshot of `Powers.all` taken before this row ran, so a row handed
    over here would be in the list for next fight and inert in this one.
    `use` arms it on the spot, which is what "you gain it as a bonus feat"
    means once the fight has started; `spend=False` because an at-will
    trait has no use to spend and the row is not being taken as an action.

    The speed clause on the rest of the printed line is `cf:ranger-f0`'s
    marauder branch, which gates it on carrying neither a shield nor a
    two-handed weapon. Not repeated here: an untyped step of speed laid
    twice is two.
    """
    from combat_engine.engine.dsl import use

    if c.feat("f172"):
        return
    c.grant_row("f172", on=c.me, until=When.ENCOUNTER)
    use(c.world, c.me, "f172", spend=False)


@power(
    "cf:ranger-f0s4",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    todo=("c.bonus_feat()",),
)
def ranger_style_two_blade(c: Cast) -> None:
    """The two-weapon style, and the same gap as `cf:ranger-f0s0`.

    Its first clause -- wielding a one-handed weapon in the off hand as
    though it were an off-hand weapon -- is a permission `chargen` already
    grants: the two blades a ranger is dealt are both off-hand weapons, as
    `cf:ranger-f0` says, so there is nothing to lift. The bonus feat is
    named in prose and is the whole of what is left.
    """


# -- runepriest -------------------------------------------------------------

#: The two traditions that both spend a Wisdom modifier, so `second-wis`
#: cannot tell them apart and `_takes_the_option` has to. The third is
#: `cf:runepriest-f2`, which sits on the Constitution leg and is settled by
#: its own `requires=`.
_RUNE_TRADITION = "cf:runepriest-f2 option"
_WIS_TRADITIONS = ("cf:runepriest-f2s0", "cf:runepriest-f2s1")


@power(
    "cf:runepriest-f1",
    level=0,
    cls="runepriest",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE, Keyword.HEALING],
    out_of_combat=True,
)
def runepriest_heal_feature(c: Cast) -> None:
    """"You gain the `p11353` power", and nothing else is printed.

    `p11353` is a level 0 runepriest row, so every runepriest has it
    already; the rider-per-rune-state the second sentence promises is
    written on that row, read off the state `cf:runepriest-f0` holds.
    """


@power(
    "cf:runepriest-f2s0",
    level=0,
    cls="runepriest",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    requires=on_leg("second-wis"),
    requires_text="needs a tradition that spends Wisdom",
)
def runepriest_tradition_miss(c: Cast) -> None:
    """The tradition that is paid for being missed.

    Sibling of `cf:runepriest-f2`, which is the Constitution one and is
    paid for being *hit*; the shape is that row's, down to `stacks=False`
    for "regardless of the number of times the enemy misses you in a
    round" -- a second miss renews the bonus rather than doubling it.

    Two of the three printed traditions spend a Wisdom modifier and
    `chargen.BUILDS["runepriest"]` has one Wisdom leg between them, so
    `_takes_the_option` decides which of the pair this runepriest follows.
    That was `cf:runepriest-tradition-rest` in `docs/blocked.json`, and it
    is the half the sub-option refs unblock.

    `Miss` carries `attacker`, `target` and `power` and nothing else, so
    the enemy is `ev.attacker`; the side check is `team`, not
    `query.enemies`, which filters out the dead.
    """
    me, world = c.me, c.world
    if c.wis_mod <= 0 or not _takes_the_option(c, _RUNE_TRADITION, _WIS_TRADITIONS):
        return
    extra = c.wis_mod

    def missed(ev: Miss) -> None:
        foe = ev.attacker
        if ev.target != me or foe == me:
            return
        if team(world, foe) is team(world, me):
            return
        c.bonus(
            "damage", extra, until=When.EONT, on=me, stacks=False,
            when=lambda ctx, f=foe: ctx.get("target") == f,
        )

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:runepriest-f2s1",
    level=0,
    cls="runepriest",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    requires=on_leg("second-wis"),
    requires_text="needs a tradition that spends Wisdom",
)
def runepriest_tradition_ward(c: Cast) -> None:
    """The other Wisdom tradition: an armour clause and temporary hit points
    for being hurt.

    **The AC clause is asked and is false on the class chassis.** It
    applies only out of heavy armour and a runepriest wears scale, so
    `out_of_heavy_armour` is the printed sentence and today it never
    passes. Written rather than dropped because the gate is real: `Gear` is
    asked live and a row elsewhere may change the armour.

    "Once per round immediately after an enemy deals damage to you" is a
    latch on the round, not on the enemy -- unlike its sibling, the printed
    limit counts uses and not attackers. `DamageApplied` carries `source`,
    `target` and `amount`.

    The weapon proficiencies are a build-time permission the engine does
    not model either way.
    """
    me, world = c.me, c.world
    if not _takes_the_option(c, _RUNE_TRADITION, _WIS_TRADITIONS):
        return

    if out_of_heavy_armour(c):
        gain = _ability_for_ac(c, c.wis_mod)
        if gain > 0:
            c.bonus(AC, gain, until=When.ENCOUNTER, on=me, kind="untyped")

    amount = c.wis_mod + 5 * sum(lv <= c.level for lv in (11, 21))
    if amount <= 0:
        return
    last: dict[int, int] = {}

    def hurt(ev: DamageApplied) -> None:
        foe = ev.source
        if ev.target != me or ev.amount <= 0 or foe is None or foe == me:
            return
        if team(world, foe) is team(world, me):
            return
        if last.get(0) == world.round:
            return
        last[0] = world.round
        c.temp_hp(amount, on=me)

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=me, label=c.ref)


# -- seeker -----------------------------------------------------------------


@power(
    "cf:seeker-f0",
    level=0,
    cls="seeker",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    out_of_combat=True,
)
def seeker_spirits_feature(c: Cast) -> None:
    """"You gain the `p9501` power." That row is a level 0 seeker row and
    `chargen.loadout` deals it to every seeker, so there is nothing to
    grant and no exclusivity to enforce -- both bonds have this one.
    """


@power(
    "cf:seeker-f1s1",
    level=0,
    cls="seeker",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg("second-str"),
    requires_text="needs the bond that throws",
    dropped=("c.returns_to_hand()",),
)
def seeker_bond_second(c: Cast) -> None:
    """The second bond, which was not in the imported text at all until the
    sub-options were extracted -- `cf:seeker-bond-rest` in
    `docs/blocked.json` is this row.

    Its granted row is `p11462`, and that row already gates itself on this
    leg, so nothing is handed over here -- exactly as `cf:seeker-f1` argues
    for the other bond.

    **The attack bonus is gated on the weapon in hand, not on the row.**
    "With both light thrown and heavy thrown weapons" is a property of the
    thing being thrown, and the damage-side context carries no attacker and
    no weapon; the main hand is asked live, the way the rogue's heavier
    tactic asks it. Untyped: no type word is printed.

    Dropped: a thrown weapon returning to the hand. Nothing in `Cast` moves
    a weapon between the ground and a hand -- `c.disarm` and `c.destroy`
    only take one away -- so the clause has no case rather than a wrong
    one.
    """
    me, world = c.me, c.world

    def thrown_in_hand(ctx: dict[str, Any]) -> bool:
        gear = world.get(me, Gear)
        held = gear.main if gear is not None else None
        return held is not None and bool(THROWN & set(held.properties))

    c.bonus(
        "attack", 1, until=When.ENCOUNTER, on=me, kind="untyped",
        when=thrown_in_hand,
    )

    if out_of_heavy_armour(c):
        gain = _ability_for_ac(c, c.str_mod)
        if gain > 0:
            c.bonus(AC, gain, until=When.ENCOUNTER, on=me, kind="untyped")


# -- warden -----------------------------------------------------------------

#: One leg per printed option, which `chargen.BUILDS["warden"]` now has
#: -- four named legs where `docs/blocked.json` was written against the
#: derived `second-<ability>` pair. The pairing is read off the ability
#: each leg's secondary names and the order the two lists print in: the
#: options are Constitution, Wisdom, Constitution, Wisdom, and the legs are
#: the two Constitution ones followed by the two Wisdom ones, each pair in
#: the page's own order.
_GUARD_LEG = {
    "cf:warden-f1s0": "earthstrength",
    "cf:warden-f1s2": "lifespirit",
    "cf:warden-f1s1": "stormheart",
    "cf:warden-f1s3": "wildblood",
}


@power(
    "cf:warden-f1s0",
    level=0,
    cls="warden",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg(_GUARD_LEG["cf:warden-f1s0"]),
    requires_text="needs the guardian might this belongs to",
)
def warden_might_ac(c: Cast) -> None:
    """The first of the four guardian mights: a second wind worth more
    armour for a round.

    **Only the second sentence is here.** The first -- Constitution in
    place of Dexterity or Intelligence for AC -- is `cf:warden-f1`, which
    writes it once for all four options because it is the half that is true
    whichever was taken, and lays it as an untyped difference. Repeating it
    would double it.

    `SecondWind` is the event the second sentence needed and did not have
    when `cf:warden-f1-rest` went into `docs/blocked.json`: it is announced
    from `Cast.second_wind`, the one implementation, before the surge is
    spent. "An additional bonus to AC" is additional to the +2 every second
    wind carries, and no type word is printed, so untyped -- which is also
    what lets it sit beside that +2 instead of losing to it.
    """
    me = c.me
    if c.con_mod <= 0:
        return
    extra = c.con_mod

    def caught_breath(ev: SecondWind) -> None:
        if ev.actor == me:
            c.bonus(AC, extra, until=When.EONT, on=me, kind="untyped")

    c.watch(SecondWind, caught_breath, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:warden-f1s1",
    level=0,
    cls="warden",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
    requires=on_leg(_GUARD_LEG["cf:warden-f1s1"]),
    requires_text="needs the guardian might this belongs to",
)
def warden_might_ally(c: Cast) -> None:
    """The guardian might that spends the warden's second wind on somebody
    else: an ally within 5 squares may take a surge and a saving throw.

    The ally is chosen, and offered most-hurt-first because that is what a
    party would pick and `World.decide` takes the head of the list. "Can"
    is the printed word, so `c.may` is asked -- it is the ally's surge, and
    an ally two hit points off full would rather keep it.

    The saving throw is not conditional on the surge: the card prints "and"
    over two independent permissions, so an ally with no surges left still
    gets its throw.

    The AC half of the printed line is `cf:warden-f1`; see
    `cf:warden-f1s0`. That row currently reads the wrong ability -- it asks
    `c.build("second-con")` and the warden's legs are named -- which is its
    bug and not this one's.
    """
    me = c.me

    def caught_breath(ev: SecondWind) -> None:
        if ev.actor != me:
            return
        # The card says "an ally", which `side="ally"` now is. It counted
        # the caster once, and the warden was then the most hurt creature in
        # its own list on the turn it took a second wind -- it healed itself
        # twice and no ally ever got the surge.
        near = sorted(
            (a for a in c.within(5, side="ally") if a != me),
            key=lambda a: -c.missing(on=a),
        )
        friend = c.choose(near, f"{c.ref}: who takes the surge and the save")
        if friend is None:
            return
        if c.may("spend a healing surge", who=friend):
            c.surge(on=friend)
        c.save(on=friend)

    c.watch(SecondWind, caught_breath, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:warden-f1s2",
    level=0,
    cls="warden",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg(_GUARD_LEG["cf:warden-f1s2"]),
    requires_text="needs the guardian might this belongs to",
)
def warden_might_slide(c: Cast) -> None:
    """The guardian might that turns a second wind into a shove.

    Two different sets, and the card is careful about it: the slide is for
    enemies marked by the warden **and within 2 squares**, the slow is for
    every enemy marked by the warden however far off. Reading one set for
    both is the obvious mistake and is the one the printed sentence goes
    out of its way to prevent.

    `c.marked(on=..., by=me)` rather than the bare condition: a warden
    marks, but so does everybody else at the table, and slowing an enemy
    the fighter marked is not this line.

    The AC half of the printed line is `cf:warden-f1`; see
    `cf:warden-f1s0`.
    """
    me = c.me

    def caught_breath(ev: SecondWind) -> None:
        if ev.actor != me:
            return
        near = set(c.within(2, side="enemy"))
        for foe in c.enemies():
            if not c.marked(on=foe, by=me):
                continue
            if foe in near:
                c.slide(1, on=foe)
            c.slowed(until=When.EONT, on=foe)

    c.watch(SecondWind, caught_breath, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:warden-f1s3",
    level=0,
    cls="warden",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL],
    requires=on_leg(_GUARD_LEG["cf:warden-f1s3"]),
    requires_text="needs the guardian might this belongs to",
)
def warden_might_penalty(c: Cast) -> None:
    """The guardian might that makes ignoring the warden cost more.

    "An **additional** penalty to attack rolls for attacks that don't
    include you as a target" is on top of the -2 a mark already carries, so
    it is laid as its own modifier rather than folded into the mark.
    `c.penalty` refuses a `kind=` outright -- a penalty has no type in 4e
    and what stops two stacking is coming from the same row.

    The gate reads the defender out of the attack context and **refuses
    when the key is absent**. A bare `ctx.get("target") != me` is true for
    a context carrying no target at all, which would have applied the
    penalty to every attack including the ones aimed at the warden -- the
    exact reversal of the printed line, and silent.

    The AC half of the printed line is `cf:warden-f1`; see
    `cf:warden-f1s0`.
    """
    me = c.me
    if c.wis_mod <= 0:
        return
    extra = c.wis_mod

    def elsewhere(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and victim != me

    def caught_breath(ev: SecondWind) -> None:
        if ev.actor != me:
            return
        for foe in c.enemies():
            if c.marked(on=foe, by=me):
                c.penalty("attack", extra, until=When.EONT, on=foe, when=elsewhere)

    c.watch(SecondWind, caught_breath, until=When.ENCOUNTER, on=me, label=c.ref)
