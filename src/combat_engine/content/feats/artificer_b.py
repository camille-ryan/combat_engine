"""Artificer feats.

`content/powers/artificer/level_0.py` holds the three rows the class's
infusion feature hands out, and most of this list rides on one of them.
The spec names them in prose only, so each is matched to its ref by
**mechanic** and nothing else: `p7635` is the one whose whole payload is
a +1 power bonus to AC, `p10187` the one that grants resistance to a
damage type the target picks, `p4128` the heal. Three rows in this batch
quote those numbers straight back -- f3037 the +1 power bonus to AC,
f2111 the resistance, f3024 and f3026 the heal -- which is what fixes
the match.

The other three class-page features are `cf:artificer-items` in
`docs/blocked.json`: no row of any of them exists and none can, so every
feat riding on one carries `c.class_feature()` and plays as nothing.
That is eight of the thirty-seven.

The next commonest gap is the cash-in all three infusions print -- "the
target can end the effect as a free action to ..." -- which
`level_0.py` already leaves out of the infusions themselves. Nothing
ends a live effect early, so those feats carry `c.end_effect()`; without
it the ally would keep the bonus *and* take the payout, which is the
one reading of the clause that is certainly wrong.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    MINOR,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    Condition,
    DamageType,
    Hit,
    Keyword,
    Moved,
    PowerUsed,
    Summoned,
    TempHP,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.grid import distance

#: The heal.
HEAL_INFUSION = "p4128"
#: The +1 power bonus to AC.
AC_INFUSION = "p7635"
#: Resistance to a damage type the target chooses.
RESIST_INFUSION = "p10187"
INFUSIONS = (HEAL_INFUSION, AC_INFUSION, RESIST_INFUSION)

#: A class-page feature with no row: `cf:artificer-items` in blocked.json.
FEATURE = ("c.class_feature()",)
#: "The target can end the effect as a free action to ...".
CASH_IN = ("c.end_effect()",)


def _ladder(level: int) -> int:
    """The 5/10/15 resistance `p10187` pays, mirrored from its own body.

    Duplicated rather than imported because it is a private helper over
    there and one number either way is cheaper than a cross-file hook.
    """
    return 5 + 5 * (0 if level < 11 else (1 if level < 21 else 2))


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _used_infusion(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power in INFUSIONS


def _feature(ref: str, what: str, todo: tuple[str, ...] = FEATURE) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=todo)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} The feature has no row and cannot have one."


# -- riders on a power the engine has ---------------------------------------


def _enchants_gear(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.actor == me
        and p is not None
        and p.cls == "artificer"
        and bool(p.target.holding)
    )


@power("f1370", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use an artificer power that targets a weapon or implement",
       on=Trigger(PowerUsed, _enchants_gear, "you enchant a weapon"))
def f1370(c: Cast) -> None:
    """"Targets a weapon or an implement" is `Target.holding`, which the
    engine writes as the *wielder* being the target -- so the bonus lands
    on whoever `PowerUsed.targets` names. "The next attack roll before
    the end of the encounter" is `once=True` on an encounter-long bonus,
    and the narrowing to that particular weapon collapses the way f734's
    implement types do: a character carries one."""
    for who in c.trigger.targets:
        c.bonus("attack", 1, on=who, until=When.ENCOUNTER, once=True)


def _my_summoning(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.ref)
    return (
        ev.actor == me
        and p is not None
        and p.cls == "artificer"
        and Keyword.SUMMONING in p.keywords
    )


@power("f1380", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you summon a creature with an artificer summoning power",
       on=Trigger(Summoned, _my_summoning, "you summon a creature"))
def f1380(c: Cast) -> None:
    """`Summoned.ref` is the *power's* ref, not the creature's -- `c.summon`
    passes `self.ref` -- so "an artificer summoning power" is readable
    here, which is what f677 could not ask of a standing modifier."""
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.trigger.summon, until=When.ENCOUNTER,
                kind="feat")


def _force_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return ev.attacker == me and p is not None and Keyword.FORCE in p.keywords


@power("f1382", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an enemy with a force power",
       on=Trigger(Hit, _force_hit, "you hit with a force power"))
def f1382(c: Cast) -> None:
    """One ally, so the first adjacent one takes it and the row stops.
    A plain "+1 bonus to AC" with no type word, so untyped."""
    foe = c.trigger.target
    for friend in c.allies():
        if friend != c.me and c.adjacent_to(friend, foe):
            c.bonus(AC, 1, on=friend, until=When.EONT)
            return


@power("f1399", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1399(c: Cast) -> None:
    """Raises the level of item a ritual may make. Ritual only."""


@power("f1400", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1400(c: Cast) -> None:
    """Raises the level of alchemical item you can make between fights.
    The Special line swaps it for a bonus feat, which is chargen's."""


@power("f1404", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.bonus(healing)",))
def f1404(c: Cast) -> None:
    """Extra hit points on every artificer healing power. The same hold
    f822 named: the amount is worked out inside `c.heal` and `Mods` is
    not consulted for healing at all, so there is nothing to add to --
    and `Healed` carries no power, so the narrowing has no field either."""


# -- the familiar chain, which hangs off f738 -------------------------------


@power("f1707", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1707(c: Cast) -> None:
    """The printed benefit is that `f1707b` replaces a utility power --
    a swap made when the character is built. On the board the whole of
    it is having the card, which `c.grant_row` says."""
    c.grant_row("f1707b", on=c.me, until=When.ENCOUNTER)


@power("f1707b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
       todo=("c.familiar_state()",))
def f1707b(c: Cast) -> None:
    """The card of f1707: the familiar swells into a Small creature that
    can flank, then teleports home and goes passive when the effect ends.

    `c.resize`, `c.can_flank`, `c.cannot_attack` and `c.familiar_mode`
    all exist, so the body is nearly writable -- but the Requirement is
    the active state f740b was blocked on, and writing the rest would
    make a card free that is printed as conditional.
    """


@power("f1708", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.familiar_state()",))
def f1708(c: Cast) -> None:
    """Twenty squares more leash while the familiar is active. Both
    halves are missing: nothing holds the mode, and nothing enforces a
    distance between a companion and its owner for this to relax."""


@power("f1709", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1709(c: Cast) -> None:
    """Same shape as f1707: the swap is chargen's, the card is the row."""
    c.grant_row("f1709b", on=c.me, until=When.ENCOUNTER)


@power("f1709b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
       todo=("c.area_origin()", "c.familiar_state()"))
def f1709b(c: Cast) -> None:
    """Fires an infusion from the familiar's square instead of your own.
    Re-aimed: `c.use_power` fires the named row now, so that is no
    longer one of the holds. Two are left, and the row is nothing
    without either -- moving a declared area's origin off its caster
    (`c.set_origin` is the creature's origin, not this one), and the
    familiar's active state, which the Requirement turns on."""


@power("f1710", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1710(c: Cast) -> None:
    """Both halves are plain numbers on the familiar, and `c.familiar`
    finds it whichever mode it is in -- no state question to answer."""
    fam = c.familiar()
    if fam is None:
        return
    c.bonus("speed", 2, on=fam, until=When.ENCOUNTER, kind="feat")
    c.bonus(AC, 1, on=fam, until=When.ENCOUNTER, kind="feat")


# -- what counts as an implement --------------------------------------------


@power("f2109", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2109(c: Cast) -> None:
    """`c.as_implement` rewrites the group of what is in hand, so the
    printed weapon group is asked first: without the guard this would
    turn a mace into an implement for an artificer who took the feat and
    carries something else."""
    if c.wielding("crossbow"):
        c.as_implement(on=c.me)


@power("f3025", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3025(c: Cast) -> None:
    """The same row for the other ranged group."""
    if c.wielding("bow"):
        c.as_implement(on=c.me)


# -- riders on the infusion that grants resistance --------------------------


@power("f2111", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.bonus(resist)",))
def f2111(c: Cast) -> None:
    """Two more points of the resistance p10187 grants. The power is a
    ref and `PowerUsed` names its targets, but the number is a literal
    inside that body and the type is chosen there too -- `Mods` is no
    more consulted for resistance than it is for healing, which is the
    hold f822 named on the other side."""


@power("f3023", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=CASH_IN,
       trigger="you use p10187",
       on=Trigger(PowerUsed, _used(RESIST_INFUSION), "you use that infusion"))
def f3023(c: Cast) -> None:
    """A second resistance beside the one the power grants, "equal to the
    resistance ordinarily granted" -- so the same ladder, read off level.

    The saving-throw clause is dropped: it trades the effect away for a
    1d6, and nothing ends a live effect early.
    """
    for who in c.trigger.targets:
        c.resist(_ladder(c.level), DamageType.RADIANT,
                 until=When.ENCOUNTER, on=who)


@power("f3033", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=CASH_IN)
def f3033(c: Cast) -> None:
    """An ally trades the infusion in for 1d8 on a melee hit. The hit is
    declarable and `c.may` asks the ally -- but the trade is the whole
    point, and without ending the effect the 1d8 would be free on every
    melee hit for the rest of the fight."""


@power("f3034", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=CASH_IN)
def f3034(c: Cast) -> None:
    """The same trade paying insubstantial instead, gated on a racial
    power still being unspent -- which `c.expended` could answer."""


@power("f3038", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.end_effect()", "c.reroll_attack(on=)"))
def f3038(c: Cast) -> None:
    """The same trade, paying a forced reroll of the attack that hit the
    ally. Two holds rather than one: `c.reroll_attack` rerolls the
    caster's own roll and takes no other creature."""


# -- riders on the infusion that heals --------------------------------------


@power("f3024", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p4128",
       on=Trigger(PowerUsed, _used(HEAL_INFUSION), "you use that infusion"))
def f3024(c: Cast) -> None:
    """A free saving throw on top of the heal. `PowerUsed` fires before
    the body, which does not matter here: the save is against something
    already standing."""
    for who in c.trigger.targets:
        c.save(on=who)


@power("f3026", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p4128",
       on=Trigger(PowerUsed, _used(HEAL_INFUSION), "you use that infusion"))
def f3026(c: Cast) -> None:
    """The damage context carries `charge`, so the gate is readable on the
    thin side. A plain "+2 bonus to damage rolls", so untyped."""
    step = 2 + (c.level >= 11) + (c.level >= 21)
    for who in c.trigger.targets:
        c.bonus("damage", step, on=who, until=When.EONT,
                when=lambda ctx: bool(ctx.get("charge")))


# -- riders on any infusion -------------------------------------------------


@power("f3027", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.save(conditions=)",),
       trigger="you use an infusion",
       on=Trigger(PowerUsed, _used_infusion, "you use an infusion"))
def f3027(c: Cast) -> None:
    """A saving throw only for a target actually carrying one of the two
    named conditions, so the row does nothing to anybody else.

    Which effect the save is rolled against is dropped. `c.save` does
    take an `against=`, so that is not the gap -- it matches a fragment
    of the effect's *label*, and a label is the ref of the row that
    laid it rather than the name of a condition. So on a target
    carrying both a daze and a burn this may shake off the burn.
    `c.save(conditions=)` is the thing that would say it.
    """
    for who in c.trigger.targets:
        if c.is_(Condition.DAZED, on=who) or c.is_(Condition.DOMINATED, on=who):
            c.save(on=who)


@power("f3032", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.BUILDS",))
def f3032(c: Cast) -> None:
    """Nine legs, one per racial manifestation, seven of them a
    resistance and two a saving-throw bonus. `c.element` is the only
    thing that answers "which element is this character sworn to" and it
    reads a *class build's* fork -- a race has no leg to record one, so
    every branch of this would be silently false."""


def _wields_infusion(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == "p8278"


@power("f3042", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3042(c: Cast) -> None:
    """"An ally benefiting from" one of two named infusions, which needs
    a list nothing keeps -- so the row keeps its own, filled from
    `PowerUsed.targets` as the infusions go out.

    A trait rather than a declared trigger because it has to be watching
    before the racial power fires. The die is necrotic and carries its
    own type.
    """
    me = c.me
    warded: list[int] = []

    def noted(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power in (AC_INFUSION, RESIST_INFUSION):
            warded.extend(w for w in ev.targets if w != me and w not in warded)

    def paid(ev: PowerUsed) -> None:
        if not _wields_infusion(c.world, me, ev):
            return
        for who in warded:
            c.bonus("damage", 0, dice="1d6", on=who, until=When.EONT,
                    once=True, dtype=DamageType.NECROTIC)
            return

    c.watch(PowerUsed, noted, until=When.ENCOUNTER, on=me, label="f3042")
    c.watch(PowerUsed, paid, until=When.ENCOUNTER, on=me, label="f3042")


# -- the rest of the racial batch -------------------------------------------


@power("f3028", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.on_skill_check()",),
       trigger="you hit an enemy granting combat advantage to you",
       on=Trigger(Hit, lambda w, me, ev: ev.attacker == me, "you hit"))
def f3028(c: Cast) -> None:
    """"Grants combat advantage to all attackers" is `to="team"`, which
    is you and your side -- everyone who will attack it in practice.

    Advantage is read off the blow rather than asked again, because a
    one-shot grant has been spent by then. The melee-and-artificer gate
    is asked in the body, since the predicate would have to reach the
    same header twice.

    The Arcana-for-Bluff substitution is dropped: the check is made
    inside a racial power and nothing announces one to swap.
    """
    p = get(c.trigger.power)
    if p is None or p.cls != "artificer" or p.reach is None:
        return
    if p.reach.kind != "melee" or not c.had_advantage(c.trigger):
        return
    c.grants_advantage(on=c.trigger.target, until=When.SONT, to="team")


@power("f3035", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recharge_power()",))
def f3035(c: Cast) -> None:
    """Spending an action point also hands an adjacent ally back a magic
    item's daily power. `ActionPointSpent` is announced and
    `c.restore_use` takes a ref -- but the ref is "a magic item's daily
    power", and nothing asks a creature which of its rows that is."""


@power("f3037", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p7635 with p2475 unspent",
       on=Trigger(PowerUsed, _used(AC_INFUSION), "you use that infusion"))
def f3037(c: Cast) -> None:
    """"In place of the +1 power bonus to AC" needs no subtraction: the
    infusion lays that bonus itself a moment later, and the other three
    defences laid here bring it to +1 across the board. Same `kind`, so
    a second copy of the AC one could not double it either way."""
    if "p2475" in c.expended(on=c.me):
        return
    for who in c.trigger.targets:
        for defence in (FORT, REF, WILL):
            c.bonus(defence, 1, on=who, until=When.ENCOUNTER, kind="power")


@power("f3041", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("spec.power_ref()",))
def f3041(c: Cast) -> None:
    """Widens the trigger of a named racial power to an ally taking
    damage, and makes both of you invisible when it goes off that way.
    Re-aimed: `c.use_power` fires `p377` now, and `DamageApplied` is
    the event -- but the trigger is "you or an ally **affected by your
    shielding elixir power**", and that power arrives as a name with no
    ref, so there is nothing to ask who is under it. Without the gate
    the row answers every point of damage anybody on the team takes."""


@power("f3043", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3043(c: Cast) -> None:
    """"An equal number of squares" is the distance the racial teleport
    actually covered, which only `Moved` knows -- it carries `from_` and
    `to` and the `kind_` that says it was a teleport.

    `PowerUsed` arms it so that only *that* power's teleport pays out;
    on its own, `Moved` would fire for every teleport the artificer
    makes. The summons are kept in a list of the row's own, because
    `Summoned.ref` is readable when it happens and nothing keeps it
    afterwards.
    """
    me = c.me
    mine: list[int] = []
    armed: list[bool] = []

    def made(ev: Summoned) -> None:
        if _my_summoning(c.world, me, ev):
            mine.append(ev.summon)

    def declared(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == "p1449":
            armed.append(True)

    def stepped(ev: Moved) -> None:
        if not armed or ev.actor != me:
            return
        if getattr(ev, "kind_", "") != "teleport":
            return
        armed.clear()
        gap = distance(ev.from_, ev.to)
        for who in mine:
            c.teleport(gap, who=who)

    c.watch(Summoned, made, until=When.ENCOUNTER, on=me, label="f3043")
    c.watch(PowerUsed, declared, until=When.ENCOUNTER, on=me, label="f3043")
    c.watch(Moved, stepped, until=When.ENCOUNTER, on=me, label="f3043")


# -- riders on the feature that pays an ally temporary hit points -----------


def _paid_an_ally(c: Cast, ev: TempHP) -> int | None:
    """The ally `cf:artificer-f1` has just handed temporary hit points to.

    That feature is the artificer's one route from itself to an ally's
    temporary hit points -- it watches `ItemPowerUsed` and pays the ally
    that used the item -- so source, side and "not me" is the printed
    sentence rather than an approximation of it. `TempHP` names no row,
    which is the one thing this cannot ask.
    """
    if ev.source != c.me or ev.target == c.me:
        return None
    return ev.target if ev.target in c.allies() else None


@power("f3030", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3030(c: Cast) -> None:
    """A trait armed once, watching the feature pay out.

    Untyped: the card prints no word in front of "bonus". "Until the
    start of his or her next turn" is `When.SOTNT` held on the ally, so
    the window is the ally's turn and not the artificer's.
    """
    def paid(ev: TempHP) -> None:
        who = _paid_an_ally(c, ev)
        if who is None:
            return
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, 2, on=who, until=When.SOTNT)

    c.watch(TempHP, paid, until=When.ENCOUNTER, on=c.me, label="f3030")


@power("f3031", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3031(c: Cast) -> None:
    """The payout is the artificer's, not the ally's: `c.resist` follows
    the caster already, and `on=c.me` says so anyway."""
    def paid(ev: TempHP) -> None:
        if _paid_an_ally(c, ev) is not None:
            c.resist(2, on=c.me, until=When.EONT)

    c.watch(TempHP, paid, until=When.ENCOUNTER, on=c.me, label="f3031")


@power("f3039", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3039(c: Cast) -> None:
    """"As a free action" is the ally's to spend and nothing bills it, so
    the step is simply taken -- `c.shift` takes `who`, not `on`."""
    def paid(ev: TempHP) -> None:
        who = _paid_an_ally(c, ev)
        if who is not None:
            c.shift(1, who=who)

    c.watch(TempHP, paid, until=When.ENCOUNTER, on=c.me, label="f3039")


@power("f3040", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3040(c: Cast) -> None:
    """The bonus rides on the **ally**, not on the artificer, and it is
    fire: a creature that resists fire shrugs those points off and takes
    the rest of the ally's blow.
    """
    def paid(ev: TempHP) -> None:
        who = _paid_an_ally(c, ev)
        if who is None or c.cha_mod <= 0:
            return
        c.bonus("damage", c.cha_mod, on=who, until=When.EOTNT,
                dtype=DamageType.FIRE)

    c.watch(TempHP, paid, until=When.ENCOUNTER, on=c.me, label="f3040")


# -- the four that ride on the charge banked in a weapon --------------------


def _banked(ref: str, what: str) -> None:
    """`cf:artificer-f0s0` is declared now, and refused in play.

    The feature banks a +2 to one attack roll, spent as a free action
    *after* the roll -- and that is the half its own row carries
    `c.boost_roll()` for. Nothing lays the charge, so nothing is
    "benefiting from" it and these four have no subject; the feature
    being named in prose was never what stopped them.
    """
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=("c.boost_roll()",))
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} {_banked.__doc__}"


#: `cf:artificer-f0` is a declared row, so this is not a naming gap -- the
#: +2 it banks is the thing nothing lays, which is what its own sub-option
#: waits on too.
_feature("f2110", "Doubles the attack bonus one feature banks in a weapon.",
         todo=("c.boost_roll()",))
_banked("f3029", "Damage to an enemy beside an ally that charge helped.")
_banked("f3036", "An initiative bonus for whoever carries the banked charge.")
_banked("f3044", "Lends a racial power's benefit to the charge's wielder.")
