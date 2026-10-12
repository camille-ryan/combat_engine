"""Barbarian, ardent and assassin: the sub-options of the class features.

A `-fNsM` ref is a build option of a feature and a `-fNcM` ref is a power
card printed inside the feature's section. Between them the options close
the three gaps `docs/blocked.json` records as `cf:barbarian-might-rest`,
`cf:ardent-f0-rest` and `cf:assassin-training-guild`: the other options'
text is on the page after all, so each one's rider can be written and hung
on the leg it belongs to.

**Most of the `-cM` refs this batch was given are not written here, and
that is deliberate.** Each was a second printing of a card the tree already
declares under its own `p` ref -- `cf:barbarian-f1c0` and `p4809` are one
card with two ids -- and `chargen.second_card` only recognises the `p5106b`
shape, so declaring both would deal a character the card twice with a use
counter each. The extraction is being fixed at the source; the pairs are in
the report. `cf:barbarian-f2c0` is the one that stayed, because `p4807` has
never been declared and the card has to live under some ref. It is written
now; `p4807` was also its marker, which is a symbol that could not have
closed.

**`cf:barbarian-f1s0` is not here either, and `docs/blocked.json` asks for
it.** It is the first of the four options and the only one whose text was on
the page from the start, so `cf:barbarian-f1` in `strikers_sb.py` wrote it
inline on the `rageblood` leg -- the grant of `p4809` and the temporary hit
points off `Dropped` -- and the ref never got a row of its own. Declaring one
beside it would be a second handler paying the same pool, which costs nothing
in play (`resolve.temp_hp` keeps the larger and returns) and still says the
same thing twice. It would also resolve `f1009`'s `todo=("cf:barbarian-f1s0",)`
and so report that feat finished, when what `f1009` actually waits on is
`TempHP.power` -- the symbol `i640x1` already names for the same clause. The
honest order is: re-aim `f1009`, move the option's body out of
`cf:barbarian-f1` and into a row here, then close the `blocked.json` entry.

Two things are worth saying once about what did get written.

* **A leg per option is what the riders want, and `chargen.BUILDS` now has
  one each.** The barbarian's five legs cover its four options exactly, and
  the ardent's three mantles and the assassin's three guild methods have a
  leg apiece -- `f0s0..f0s2` and `f1s0..f1s2`, named for the option rather
  than for a secondary ability. The note here said each class was a leg
  short and shared one between two siblings; it is not true any more, and
  `c.build("f1s1")` is an exact gate.
* **"Your attack bloodies an enemy" is `Bloodied.source`.** The event now
  names whoever struck the blow, exactly as `Dropped` does, so all three
  barbarian riders answer only the enemies this barbarian put past the
  line.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.builds import on_leg
from combat_engine.content.powers.barbarian.rage import raging
from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    STANDARD,
    STR,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBurst,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Powers,
    PowerUsed,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.query import distance_between, team

PSIONIC = [Keyword.PSIONIC]
PRIMAL = [Keyword.PRIMAL]
PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]
SHADOW = [Keyword.SHADOW]


def _against_openings(ctx: dict[str, Any]) -> bool:
    """The damage context carries `opportunity`, which is the whole gate."""
    return bool(ctx.get("opportunity"))


def _end_all(c: Cast, held: list[Effect | None]) -> None:
    for eff in held:
        if eff is not None and not eff.ended:
            c.world.effects.end(eff)


# ----------------------------------------------------------------- ardent


@power(
    "cf:ardent-f0s1",
    level=0,
    cls="ardent",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PSIONIC,
)
def ardent_mantle_elation(c: Cast) -> None:
    """The second mantle, which reads Constitution, on the Constitution leg.

    `cf:ardent-f0` lays the *first* mantle's bonuses for every ardent,
    because that was the only mantle whose text the class page carried.
    This one is a different set of numbers, so it does not overlap it --
    but an ardent on this leg is wearing the wrong mantle's bonuses as well
    as this one's until that parent learns its own gate.

    The damage context carries `opportunity`, so "a bonus to damage rolls
    for opportunity attacks" is one gated modifier per creature and not a
    watch. `stacks=False` buckets it under this row's ref, which every
    ardent wearing this mantle shares -- the printed "only the highest
    applies" the sibling mantle spells out and this one leaves implied.

    A snapshot, not an aura, for the reason the parent gives: nothing hangs
    modifiers on a zone's occupants, so the five squares are measured once
    when `Encounter._arm_traits` runs this.
    """
    if not c.build("f0s1"):
        return
    nearby = c.within(5, side="team")
    if c.con_mod > 0:
        for who in nearby:
            c.bonus(
                "damage", c.con_mod, until=When.ENCOUNTER, on=who,
                stacks=False, when=_against_openings,
            )
    for who in nearby:
        # The skill half is the allies' and not the ardent's own.
        if who == c.me:
            continue
        c.bonus("skill:diplomacy", 2, until=When.ENCOUNTER, on=who, stacks=False)
        c.bonus("skill:intimidate", 2, until=When.ENCOUNTER, on=who, stacks=False)


@power(
    "cf:ardent-f0s2",
    level=0,
    cls="ardent",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=PSIONIC,
)
def ardent_mantle_impulse(c: Cast) -> None:
    """The third mantle, on the third leg.

    It reads Constitution, like the second one, and used to share that
    leg -- so an ardent wore both, and their damage bonuses are of
    different kinds ("power" here, untyped there) and therefore added.
    A leg per mantle is what stops that.

    "Until the end of his or her turn" is `EOTNT`: an opportunity attack is
    taken on somebody else's turn, so the ally whose damage this is has no
    turn running and the sentence means their next one.
    """
    if not c.build("f0s2"):
        return
    me = c.me

    def struck_at(ev: AttackDeclared) -> None:
        if not getattr(ev, "opportunity", False):
            return
        ally = ev.target
        if ally == me or team(c.world, ally) is not team(c.world, me):
            return
        if distance_between(c.world, me, ally) > 5 or c.con_mod <= 0:
            return
        c.bonus("damage", c.con_mod, until=When.EOTNT, on=ally, kind="power")

    c.watch(AttackDeclared, struck_at, until=When.ENCOUNTER, on=me, label=c.ref)

    for who in c.within(5, side="ally"):
        if who == me:
            continue
        c.bonus("skill:endurance", 2, until=When.ENCOUNTER, on=who, stacks=False)
        c.bonus("skill:intimidate", 2, until=When.ENCOUNTER, on=who, stacks=False)

    # The mantle's own rider on the class heal. `PowerUsed` is announced
    # before the body runs, but the targets are chosen before the body too,
    # so `ev.targets` is the one thing on it that can be trusted here.
    def on_surge(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != "p10273":
            return
        for who in ev.targets:
            c.bonus("speed", 2, until=When.EONT, on=who)

    c.watch(PowerUsed, on_surge, until=When.ENCOUNTER, on=me, label=f"{c.ref} surge")


@power(
    "cf:ardent-f1",
    level=0,
    cls="ardent",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
)
def ardent_surge(c: Cast) -> None:
    """The feature's whole printed benefit is the grant of the class heal.

    `chargen.loadout` deals every level-0 row of the class and `p10273` is
    one, so the grant is a no-op for an ardent built here and only does
    work for a creature that came by the feature some other way.
    """
    c.grant_row("p10273")


@power(
    "cf:ardent-f2",
    level=0,
    cls="ardent",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PSIONIC,
    out_of_combat=True,
)
def ardent_power_points(c: Cast) -> None:
    """Power points and the augmentable keyword, and both are now real.

    The pool was always data -- `chargen.CLASSES[...].power_points` --
    and what was missing was the door a *use* goes through. It exists:
    `dsl.use(augment=)` settles the spend **before** targets are chosen,
    `dsl.Augment` is how a row declares the forms that spend buys, and
    `actions.legal` offers each affordable one as its own entry so that
    picking an augment is something the player does.

    Which leaves this row holding nothing to run. Its whole printed
    content is a resource the character is built with and a rule the
    engine now keeps, exactly as `cf:battlemind-f2`'s content is the word
    *one* and its children say it. `out_of_combat=True` is the flag for
    that -- deliberately inert rather than unwritten -- and it is the
    honest end of issue #170 for this row.
    """


# -------------------------------------------------------------- barbarian


@power(
    "cf:barbarian-f1s1",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PRIMAL,
)
def barbarian_thaneborn(c: Cast) -> None:
    """The second option: a bonus off bloodying a foe.

    The option's granted row is `p4932`, which `chargen.loadout` deals
    already, so the half worth writing is the rider. `cf:barbarian-f1`
    takes nothing away from this leg and should -- but the parent is
    another file's and the three options it could not name now have text,
    which is the `cf:barbarian-might-rest` entry.

    "The **next** attack by you or an ally" is one bonus shared across the
    party, not one each: the modifier is laid on everybody and the whole
    set is ended by hand off the first roll that could have used it.
    `once=True` would have given every ally their own.
    """
    me = c.me
    if not c.build("thaneborn") or c.cha_mod <= 0:
        return

    def on_bloodied(ev: Bloodied) -> None:
        victim = ev.actor
        if ev.source != me or team(c.world, victim) is team(c.world, me):
            return
        held: list[Effect | None] = [
            c.bonus(
                "attack", c.cha_mod, until=When.ENCOUNTER, on=who,
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )
            for who in [me, *c.allies()]
        ]

        def spend(rolled: AttackRolled) -> None:
            if rolled.target == victim:
                _end_all(c, held)

        c.watch(
            AttackRolled, spend, until=When.ENCOUNTER, on=me,
            once=True, label=f"{c.ref} spent",
        )

    c.watch(Bloodied, on_bloodied, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:barbarian-f1s2",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PRIMAL,
)
def barbarian_thunderborn(c: Cast) -> None:
    """The third option: thunder off bloodying a foe.

    `p9556` is the granted row and is dealt already. The once-a-round latch
    is the card's own and is keyed on the world's round, not on a boolean,
    so it survives the effect being re-armed.
    """
    me = c.me
    if not c.build("thunderborn") or c.con_mod <= 0:
        return
    paid: dict[int, int] = {}

    def on_bloodied(ev: Bloodied) -> None:
        victim = ev.actor
        if ev.source != me or team(c.world, victim) is team(c.world, me):
            return
        if paid.get(me) == c.world.round:
            return
        paid[me] = c.world.round
        for foe in c.within(1, side="enemy"):
            c.flat(c.con_mod, dtype=DamageType.THUNDER, on=foe)

    c.watch(Bloodied, on_bloodied, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:barbarian-f1s3",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PRIMAL,
    dropped=("Weapon.off_hand_anyway",),
)
def barbarian_whirling(c: Cast) -> None:
    """The fourth option: a shift off bloodying a foe, and combat advantage.

    `p5249` is the granted row and is dealt already. One dropped clause:
    "you can wield a one-handed weapon in your off hand and treat it as an
    off-hand weapon" is a fact about the gear rather than about the fight --
    `c.w(hand="off")` reads the weapon's own properties and nothing
    overrides them, which is the hold two feats already carry.

    The shift is printed as something you *can* do, so it is offered; the
    combat advantage is measured after it, from wherever the shift ended,
    which is what "adjacent to you at the end of the shift" means.
    """
    me = c.me
    if not c.build("whirling"):
        return
    paid: dict[int, int] = {}

    def on_bloodied(ev: Bloodied) -> None:
        victim = ev.actor
        if ev.source != me or team(c.world, victim) is team(c.world, me):
            return
        if paid.get(me) == c.world.round:
            return
        paid[me] = c.world.round
        if not c.may("shift 2 squares", who=me):
            return
        c.shift(2, who=me)
        for foe in c.within(1, side="enemy"):
            c.grants_advantage(until=When.EONT, on=foe)

    c.watch(Bloodied, on_bloodied, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:barbarian-f2",
    level=0,
    cls="barbarian",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=PRIMAL,
)
def barbarian_rage(c: Cast) -> None:
    """Two sentences, and the only one with a subject is the grant.

    **"A keyword nothing declares" is stale.** `Keyword.RAGE` exists (#503)
    and every daily the class prints carries it, from `level_1_b.py`'s
    `PRIMAL_RAGE` to `level_9.py`. So the first sentence is a fact about
    those cards and there is nothing here to lay.

    The second is the grant at 5th level, and the card is
    `cf:barbarian-f2c0`. **The marker was unclosable:** `p4807` is the
    compendium's other id for that same card and is never going to be
    declared beside it, so nothing could ever have turned the symbol green.
    `chargen.loadout` does not deal the feature's card either -- checked at
    5 and at 10 -- so this grant is what puts it in hand.

    (The marker named `c.expend()` before that, and that too was a facility
    which existed as `c.expend_row`. #418.)
    """
    if c.level >= 5:
        c.grant_row("cf:barbarian-f2c0")


def _unused_rages(world: World, eid: int) -> list[str]:
    """"An unused barbarian rage power", by ref.

    A registry filter and not a list: `Power.cls`, the daily usage and
    `Keyword.RAGE` pick the set out, so a level landing adds itself. Read
    off what the creature actually holds, and `Powers.times` is the "unused"
    half -- a spent daily is no longer one of these.
    """
    known = world.get(eid, Powers)
    if known is None:
        return []
    return sorted(
        ref
        for ref in known.all
        if known.times(ref) == 0
        and (p := get(ref)) is not None
        and p.cls == "barbarian"
        and p.usage is Usage.DAILY
        and Keyword.RAGE in (p.keywords or ())
    )


def _can_burn_a_rage(world: World, eid: int) -> bool:
    """The printed Requirement, as a `requires=` gate.

    Safe here where it would not be on a trait: this row is a standard
    action, so `usable` asks it at the moment of use rather than once at
    arming -- and both halves of it become true mid-fight, which is the
    whole shape `turns.arm_traits_of` would have refused for ever.
    """
    return raging(world, eid) and bool(_unused_rages(world, eid))


#: The printed ladder: dice by the **level of the power burned**, not by the
#: character's. Only the first three steps are reachable while the project
#: stops at 10; the rest is on the card and costs nothing to carry.
_BURN_DICE = ((29, 9), (25, 8), (19, 7), (15, 6), (9, 5), (5, 4))


def _dice_for_burning(level: int) -> int:
    for at, dice in _BURN_DICE:
        if level >= at:
            return dice
    return 3


@power(
    "cf:barbarian-f2c0",
    level=5,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    uses=2,
    requires=_can_burn_a_rage,
    requires_text="must be raging and have at least one unused rage power",
)
def barbarian_burn_a_rage(c: Cast) -> None:
    """The card `cf:barbarian-f2` grants, and the first ref it has ever had.

    `p4807` is the same card and has never been declared -- `docs/blocked.csv`
    carries it, and the two rows elsewhere that gate on the card name this
    ref instead: `f2706` and `i2947p1`. It was also this row's marker, which
    could not have closed: the symbol was a second id for the row carrying
    it.

    **Both halves the old docstring called unsayable now exist.**
    `Keyword.RAGE` names a rage power (#503) and `c.expend_row` spends a use
    *without running the row*, which is the printed "to make this attack you
    expend an unused rage power" -- and is the thing `c.forbid` is explicitly
    not. So the dice are keyed to a choice that really costs something.

    The expend comes **before** the swing, as the Attack line prints it: on a
    miss the power is still gone. Its False is the Requirement a second time,
    for the case where the gate passed and the pick was taken away in
    between.
    """
    ref = c.choose(_unused_rages(c.world, c.me), "which rage power to channel")
    if ref is None or not c.expend_row(ref):
        return
    burnt = get(ref)
    dice = _dice_for_burning(burnt.level if burnt is not None else 1)
    if c.strike():
        c.damage(c.w(dice), c.str_mod)
    else:
        c.half_damage(c.w(dice), c.str_mod)


# --------------------------------------------------------------- assassin


@power(
    "cf:assassin-f0",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=SHADOW,
)
def assassin_shrouds(c: Cast) -> None:
    """The feature's whole printed benefit is the grant of the shroud row.

    The mechanic itself is already here -- `c.shroud` caps at four,
    `c.shrouds` counts them and `c.spend_shrouds` clears them -- and
    `p9400` is the card that lays and invokes them. `chargen.loadout` deals
    that card, so this grant only does work for a creature that came by the
    feature some other way.
    """
    c.grant_row("p9400")


@power(
    "cf:assassin-f1s1",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=SHADOW,
    requires=on_leg("f1s1"),
    requires_text="needs the second of the three options printed under the feature",
)
def assassin_second_method(c: Cast) -> None:
    """The second guild method, and both sides of its trade.

    The grant is a no-op for a dealt assassin: `p13799` is a level-0 row of
    the class and `chargen.loadout` has already handed it over.

    **The loss is a registry filter, which is what the refusal said it could
    not be.** `Power.cls`, the encounter usage and an attack line pick out
    exactly "assassin encounter attack powers", so a level landing adds
    itself and nothing goes stale. The walk is over what this creature
    *holds*, because taking away a row nobody has says nothing -- the same
    shape `_no_limited_attacks` settled for a whole usage band. The
    `attack is not None` test is load-bearing and not tidiness: `p13799` is
    itself an encounter row of the class, and without it this would forbid
    the power it had just granted.

    `c.forbid` for the fight is as near as a board gets to "does not gain":
    the printed sentence is about what the character *learns*, which is a
    chargen fact, and a row unreachable for the whole encounter is that
    sentence from the inside. `until=` is not optional -- the default is
    save ends and no save is printed here.

    **The leg moved from the body into `requires=`**, which is the shape the
    three swordmage children use and is safe for the reason `AUTHORING`
    gives: a `requires=` on a trait is only safe when its Requirement cannot
    change mid-fight, and a build leg is chosen before the fight starts. It
    also makes the row visible to its own instruments -- `chargen.build_for`
    picks the leg a row is *usable* on, and with the gate inside the body
    every leg looked usable, so the audit fielded this on the first one and
    reported it silent while it was correct.
    """
    c.grant_row("p13799")
    known = c.world.get(c.me, Powers)
    for ref in known.all if known is not None else ():
        p = get(ref)
        if (
            p is None
            or p.cls != "assassin"
            or p.usage is not Usage.ENCOUNTER
            or p.attack is None
        ):
            continue
        c.forbid(ref, on=c.me, until=When.ENCOUNTER)


@power(
    "cf:assassin-f1s2",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=SHADOW,
)
def assassin_hidden_blade(c: Cast) -> None:
    """The third guild method: damage against a target with nobody beside it.

    It reads Charisma, so it rides the leg named for that secondary --
    the same correspondence `cf:assassin-f1` uses for the Constitution
    method.

    "Adjacent to none of your enemies" is asked of the *victim*, not of the
    assassin, and the damage context carries `target`, so it is one gate
    and not a watch. `c.enemies` leaves out the dead, which is right here:
    a corpse beside the target is not company. Untyped -- the card prints
    no type word.
    """
    if not c.build("f1s2") or c.cha_mod <= 0:
        return

    def alone(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        return not any(
            foe != victim and c.adjacent_to(victim, foe) for foe in c.enemies()
        )

    c.bonus("damage", c.cha_mod, until=When.ENCOUNTER, on=c.me, when=alone)


@power(
    "cf:assassin-f2",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=SHADOW,
)
def assassin_shadow_form(c: Cast) -> None:
    """The feature's whole printed benefit is the grant of `p9402`."""
    c.grant_row("p9402")


@power(
    "cf:assassin-f3",
    level=0,
    cls="assassin",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=SHADOW,
)
def assassin_shadow_step(c: Cast) -> None:
    """The feature's whole printed benefit is the grant of `p9401`."""
    c.grant_row("p9401")
