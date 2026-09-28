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
the report. `cf:barbarian-f2c0` is the one that stayed, because `p4807` is
blocked and has never been declared.

Two things are worth saying once about what did get written.

* **A leg per option is what the riders want and `chargen.BUILDS` has
  fewer.** The barbarian's five legs cover its four options exactly. The
  ardent has two legs for three mantles and the assassin two for three
  guild methods, so one row in each class is gated on a leg it shares with
  a sibling. Marked where it changes what plays.
* **"Your attack bloodies an enemy" cannot be said.** `Bloodied` carries
  `actor` and no source, so all three barbarian riders answer any enemy
  crossing the line rather than only the ones this barbarian put there.
  That is `Bloodied.source`, which sixteen other rows already want.
"""

from __future__ import annotations

from typing import Any

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
    PowerUsed,
    When,
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
    dropped=("Bloodied.source",),
)
def barbarian_thaneborn(c: Cast) -> None:
    """The second option: a bonus off bloodying a foe.

    The option's granted row is `p4932`, which `chargen.loadout` deals
    already, so the half worth writing is the rider. `cf:barbarian-f1`
    takes nothing away from this leg and should -- but the parent is
    another file's and the three options it could not name now have text,
    which is the `cf:barbarian-might-rest` entry.

    `Bloodied` carries `actor` and nothing else, so "**your** attack
    bloodies an enemy" cannot be told from an enemy crossing the line to a
    hazard or an ally's blow. The row fires on either, which is wider than
    the card, and that is the dropped clause.

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
        if victim == me or team(c.world, victim) is team(c.world, me):
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
    dropped=("Bloodied.source",),
)
def barbarian_thunderborn(c: Cast) -> None:
    """The third option: thunder off bloodying a foe.

    `p9556` is the granted row and is dealt already. Same source gap as the
    thaneborn leg -- this answers any enemy being bloodied rather than only
    the ones this barbarian bloodied. The once-a-round latch is the card's
    own and is keyed on the world's round, not on a boolean, so it survives
    the effect being re-armed.
    """
    me = c.me
    if not c.build("thunderborn") or c.con_mod <= 0:
        return
    paid: dict[int, int] = {}

    def on_bloodied(ev: Bloodied) -> None:
        victim = ev.actor
        if victim == me or team(c.world, victim) is team(c.world, me):
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
    dropped=("Bloodied.source", "Weapon.off_hand_anyway"),
)
def barbarian_whirling(c: Cast) -> None:
    """The fourth option: a shift off bloodying a foe, and combat advantage.

    `p5249` is the granted row and is dealt already. Two dropped clauses.
    `Bloodied` names no source, as on the other two legs. And "you can
    wield a one-handed weapon in your off hand and treat it as an off-hand
    weapon" is a fact about the gear rather than about the fight --
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
        if victim == me or team(c.world, victim) is team(c.world, me):
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
    todo=("Keyword.RAGE", "c.expend()"),
)
def barbarian_rage(c: Cast) -> None:
    """Two sentences and neither can be said.

    Every daily attack power of the class carries a keyword nothing
    declares, so no row can be told to be a rage; and the level-5 row the
    second sentence grants is `cf:barbarian-f2c0`, which is blocked on that
    same keyword and on expending a row without using it. This is the
    `cf:barbarian-rage` entry in `docs/blocked.json`, which now has a ref.
    """


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
    requires_text="must be raging and have at least one unused rage power",
    todo=("Keyword.RAGE", "c.expend()"),
)
def barbarian_rage_strike(c: Cast) -> None:
    """The card `cf:barbarian-f2` grants, and the first ref it has ever had.

    `p4807` is the same card and has never been declared -- `docs/blocked.csv`
    carries it, and the two rows elsewhere that gate on the card now name
    this ref instead: `f2706` and `i2947p1`.

    The attack and the miss half are ordinary; the whole point of the row
    is not. The dice are the level of the rage power you burn to make it,
    and nothing can name a rage power or spend one without using it.
    `c.forbid` removes a row, which `Powers` is explicit is not the same as
    spending it, so the damage would be keyed to a choice that costs
    nothing. Refused in play rather than written at 3[W] forever.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)


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
    todo=("c.no_encounter_attacks()",),
)
def assassin_night_stalker(c: Cast) -> None:
    """The second guild method: it has a leg now, and still no way to pay.

    The grant is a no-op: `p13799` is a level-0 row of the class and
    `chargen.loadout` has already dealt it. The loss -- every encounter
    attack power in the class -- would be a hand-listed set of refs that
    goes stale the moment a level lands, and a half-written version leaves
    an assassin holding the powers its method says it never learned. So
    the row is still refused: the whole of it is the trade, and only one
    side of the trade can be written.
    """
    if not c.build("f1s1"):
        return
    c.grant_row("p13799")


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
