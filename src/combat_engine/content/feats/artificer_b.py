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

`docs/blocked.json`'s `cf:artificer-items` is **out of date** and this
file no longer rides on it: `Gear.worn` records the magic items a
creature wears, `Magic.powers` lists their rows and `ItemPowerUsed`
announces one firing, so `cf:artificer-f1` is written and the rows that
read an item's daily power (f3035) are written with it. Nothing here
carries `c.class_feature()` any more. What is genuinely left is the
allowance half of the other three features, which is granted and spent
inside a short rest -- `events.ShortRested`, which nothing emits.

The next commonest shape is the cash-in all three infusions print --
"the target can end the effect as a free action to ..." -- which
`level_0.py` still leaves out of the infusions themselves. `c.end_effect`
is the trade and its `None` is the guard: without it the ally would keep
the bonus *and* take the payout, which is the one reading of the clause
that is certainly wrong. Where the card gives **no moment** for the
trade, `c.give` hands the ally a one-shot with its own cost instead of
`c.endable`, which would need an `Effect` nothing reports.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    MINOR,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionPointSpent,
    ActionType,
    AttackRolled,
    Cast,
    Companion,
    Condition,
    DamageApplied,
    DamageType,
    Gear,
    Healed,
    Hit,
    Keyword,
    Moved,
    PowerResolved,
    PowerUsed,
    SavingThrow,
    Size,
    SkillCheck,
    Summoned,
    TempHP,
    Trigger,
    When,
    Window,
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


def _familiar_active(c: Cast) -> int | None:
    """The familiar, if there is one and it is in its active mode.

    "Requirement: your familiar must be in its active state" is askable:
    passive is `Companion.passive`, which `c.familiar_mode` sets and
    nothing on `Cast` reads back. Three rows here were marked as though
    the state did not exist at all.
    """
    fam = c.familiar()
    mine = c.world.get(fam, Companion) if fam is not None else None
    return fam if mine is not None and not mine.passive else None


def _item_dailies(c: Cast, who: int) -> list[str]:
    """The **spent** daily rows of the magic items that creature wears.

    `Gear.worn` is every magic item on the creature and `Magic.powers`
    lists its own rows, so "a magic item's daily power" is a declared row
    of `DAILY` usage named by one of those slots. `docs/blocked.json`
    still records this as having no subject; it has had one since
    `Gear.worn` landed.
    """
    gear = c.world.get(who, Gear)
    if gear is None:
        return []
    spent = set(c.expended(on=who))
    out = []
    for magic in gear.worn.values():
        for ref in magic.powers:
            row = get(ref)
            if ref in spent and row is not None and row.usage is DAILY:
                out.append(ref)
    return out


def _feature(ref: str, what: str, todo: tuple[str, ...]) -> None:
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
       reach=PERSONAL, target=SELF)
def f1404(c: Cast) -> None:
    """Extra hit points on every artificer healing power.

    The old marker read `Mods` not being consulted for healing as the
    wall. It is not one: `Healed` is a `Decision` announced with a
    mutable `amount` **before** the hit points go on, which is the seam
    "the target regains half the normal hit points" already uses.

    `Healed` naming no power is true and not a wall either. The heal
    happens inside the power's body, between its `PowerUsed` and its
    `PowerResolved`, so holding both ends says which row is healing --
    and "artificer healing power" is that row's `cls` and keyword.
    """
    me = c.me
    step = 2 + sum(c.level >= n for n in (6, 11, 16, 21, 26))
    open_: list[str] = []

    def opened(ev: PowerUsed) -> None:
        row = get(ev.power)
        if (ev.actor == me and row is not None and row.cls == "artificer"
                and Keyword.HEALING in row.keywords):
            open_.append(ev.power)

    def closed(ev: PowerResolved) -> None:
        if ev.actor == me and ev.power in open_:
            open_.remove(ev.power)

    def topped(ev: Healed) -> None:
        if open_ and ev.source == me and ev.amount > 0:
            ev.amount += step

    c.watch(PowerUsed, opened, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(PowerResolved, closed, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(Healed, topped, until=When.ENCOUNTER, on=me, label=c.ref,
            window=Window.BEFORE)


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
       dropped=("c.set_hp()",))
def f1707b(c: Cast) -> None:
    """The card of f1707: the familiar swells into a Small creature that
    can flank, then teleports home and goes passive when the effect ends.

    The Requirement was the hold and it is not one -- `Companion.passive`
    holds the state `c.familiar_mode` sets, so "must be in its active
    state" is asked in full before anything is laid.

    "When this effect ends" is the resize's own `on_end`, which is what
    makes the teleport and the passive mode part of the same effect
    rather than a second clock that could outlive it.

    Dropped: hit points equal to your healing surge value. `c.surge_value`
    knows the number and nothing sets a creature's maximum to it; the
    familiar keeps the hit points it had, which is the only reading that
    cannot invent a pool the card does not print.
    """
    fam = _familiar_active(c)
    if fam is None:
        return
    grown = c.resize(Size.SMALL, on=fam, until=When.SONT)
    c.can_flank(on=fam, until=When.SONT)
    c.cannot_attack(on=fam, until=When.SONT)
    if grown is None:
        return

    def home() -> None:
        c.teleport(0, who=fam, to=c.here, share=True)
        c.familiar_mode("passive", of=c.me)

    grown.on_end.append(home)


@power("f1708", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("query.leash()",))
def f1708(c: Cast) -> None:
    """Twenty squares more leash while the familiar is active.

    Re-aimed. The mode is held after all -- `Companion.passive` -- so
    that half is not missing. What is missing is the thing the feat
    relaxes: nothing keeps a familiar within any distance of its owner,
    so there is no limit for twenty squares to be added to, and a row
    that laid the bonus anyway would be a number nothing reads."""


@power("f1709", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1709(c: Cast) -> None:
    """Same shape as f1707: the swap is chargen's, the card is the row."""
    c.grant_row("f1709b", on=c.me, until=When.ENCOUNTER)


@power("f1709b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ARCANE],
       todo=("c.use_power(origin=)",))
def f1709b(c: Cast) -> None:
    """Fires an infusion from the familiar's square instead of your own.

    Re-aimed twice. The familiar's active state is readable
    (`Companion.passive`), so that half of the old marker is gone, and
    the hold is now named precisely: `dsl.use` **takes** an `origin`
    square and `c.use_power` is the only route to it and does not pass
    one through. `c.use_power(..., who=familiar)` is the near miss to
    avoid -- it makes the familiar the caster, so the infusion would be
    rolled with the familiar's ability modifiers instead of moving one
    burst's origin, and the heal in particular would come out wrong."""


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
       reach=PERSONAL, target=SELF)
def f2111(c: Cast) -> None:
    """Two more points of the resistance p10187 grants.

    The type is chosen inside that body and the number is a literal
    there, which the old marker read as a wall. Neither has to be
    guessed: `c.resistances` reports what a creature resists, and
    `PowerResolved` is the moment **after** the infusion has laid its
    own -- so the type is whichever one went up, and the amount is what
    it went up to. `c.resist` takes the highest rather than adding, so
    two points more of the same type replaces it instead of stacking.
    """
    me = c.me
    before: dict[int, dict[DamageType, int]] = {}

    def opened(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power != RESIST_INFUSION:
            return
        before.clear()
        for who in ev.targets:
            before[who] = dict(c.resistances(on=who))

    def closed(ev: PowerResolved) -> None:
        if ev.actor != me or ev.power != RESIST_INFUSION:
            return
        for who, was in before.items():
            for dtype, now in c.resistances(on=who).items():
                if now > was.get(dtype, 0):
                    c.resist(now + 2, dtype, until=When.ENCOUNTER, on=who)
        before.clear()

    c.watch(PowerUsed, opened, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(PowerResolved, closed, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f3023", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p10187",
       on=Trigger(PowerUsed, _used(RESIST_INFUSION), "you use that infusion"))
def f3023(c: Cast) -> None:
    """A second resistance beside the one the power grants, "equal to the
    resistance ordinarily granted" -- so the same ladder, read off level.

    The saving-throw clause trades the infusion away for a 1d6 on the
    roll. `SavingThrow` is announced before it is acted on and `saved` is
    read back, so the extra die is applied there rather than by rolling
    again. Offered only on a save that is failing: adding to one that has
    already succeeded spends the infusion for nothing, and the printed
    "can" is a choice rather than a reflex.
    """
    for who in c.trigger.targets:
        c.resist(_ladder(c.level), DamageType.RADIANT,
                 until=When.ENCOUNTER, on=who)

        def steady(ev: SavingThrow, who: int = who) -> None:
            if ev.actor != who or ev.saved:
                return
            if not c.may("spend the infusion for 1d6", who=who, default=False):
                return
            if c.end_effect(on=who, against=RESIST_INFUSION) is None:
                return
            ev.saved = ev.natural + ev.bonus + c.roll("1d6") >= 10

        c.watch(SavingThrow, steady, until=When.ENCOUNTER,
                window=Window.BEFORE)


@power("f3033", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3033(c: Cast) -> None:
    """An ally trades the infusion in for 1d8 on a melee hit.

    The printed moment is the hit, so this is a watch rather than a
    granted free action, and the trade is `c.end_effect` -- its `None`
    is the ally not being under either infusion, which is what stops the
    1d8 being free on every melee hit for the rest of the fight.

    Melee is read off the row that made the hit: the damage context
    carries no reach and `Hit` carries no branch."""
    me = c.me

    def cash_in(ev: Hit) -> None:
        if ev.attacker == me or ev.attacker not in c.allies():
            return
        p = get(ev.power)
        if p is None or p.reach.kind != "melee":
            return
        if not c.may("spend the infusion for 1d8", who=ev.attacker,
                     default=False):
            return
        for infusion in (AC_INFUSION, RESIST_INFUSION):
            if c.end_effect(on=ev.attacker, against=infusion) is not None:
                c.flat(c.roll("1d8"), on=ev.target)
                return

    c.watch(Hit, cash_in, until=When.ENCOUNTER, on=me)


@power("f3034", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3034(c: Cast) -> None:
    """The card prints no moment for this trade: the ally may take it as
    a free action whenever it likes.

    Written the other way round from the old marker. `c.endable` wants
    the `Effect` object and nothing hands one over -- but it is not the
    only route to a free action somebody else spends. `c.give` puts a
    one-shot in the ally's hands with its own cost, `actions.legal`
    offers it to whoever is carrying it, and the payout closes over this
    caster. The trade itself is `c.end_effect`, whose `None` is the ally
    not being under either infusion after all, so the benefit cannot be
    taken twice or taken for free.

    The gate on p2482 is asked when the one-shot is **spent** rather
    than when it is handed over, which is where the card asks it.
    """
    me = c.me

    def trade(spender: int) -> None:
        if "p2482" in c.expended(on=me):
            return
        for infusion in (AC_INFUSION, RESIST_INFUSION):
            if c.end_effect(on=spender, against=infusion) is not None:
                c.insubstantial(on=spender, until=When.SOTNT)
                return

    def offered(ev: PowerUsed) -> None:
        if ev.actor != me or ev.power not in (AC_INFUSION, RESIST_INFUSION):
            return
        for who in ev.targets:
            if who != me:
                c.give(fn=trade, on=who, uses=1, cost=ActionType.FREE)

    c.watch(PowerUsed, offered, until=When.ENCOUNTER, on=me, label=c.ref)


def _melee_landing(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A melee attack that is about to be a hit, on somebody else.

    Read off the live `AttackResult` the event carries: the outcome is
    recomputed **after** `AttackRolled` is announced, so what the result
    says here is provisional and what a listener changes is what lands.
    """
    row = get(ev.power)
    result = getattr(ev, "result", None)
    return (
        ev.attacker != me
        and result is not None
        and result.hit
        and row is not None
        and row.reach is not None
        and row.reach.kind == "melee"
    )


@power("f3038", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an ally under one of your infusions is hit by a melee attack",
       on=Trigger(AttackRolled, _melee_landing, "a melee attack would hit"))
def f3038(c: Cast) -> None:
    """The old marker was stale in both halves. `c.reroll_attack` does
    not reroll "the caster's own" attack -- it reads the roll off
    `c.trigger` and changes whichever attack that is, so it needs no
    `on=`; and the roll is still open, because `resolve.attack` announces
    `AttackRolled` and then recomputes hit, critical and defence from the
    result afterwards. That window is the printed interrupt.

    So the moment is `AttackRolled` rather than `Hit`: by the time a hit
    is announced the damage rider has nothing left to undo. The trade is
    `c.end_effect`, and its `None` is the ally not being under either
    infusion, which is what keeps the reroll from being free.
    """
    ev = c.trigger
    who = ev.target
    if who == c.me or who not in c.allies():
        return
    for infusion in (AC_INFUSION, RESIST_INFUSION):
        if who not in c.suffering(infusion, include_self=True):
            continue
        if not c.may("end the infusion to force a reroll", who=who,
                     default=False):
            return
        if c.end_effect(on=who, against=infusion) is not None:
            c.reroll_attack()
        return


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
       reach=PERSONAL, target=SELF, todo=("chargen.race_choice()",))
def f3032(c: Cast) -> None:
    """Nine legs, one per racial manifestation, seven of them a
    resistance and two a saving-throw bonus.

    Re-aimed to name the gap rather than the thing that does exist:
    `chargen.BUILDS` is there and has a leg for every class that prints
    a choice, and `c.element` reads `element:` off the build those legs
    make. A *race* that prints a choice has nowhere to record one, so
    every branch of this would be silently false. The same hold as the
    warden's racial leg."""


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
       reach=PERSONAL, target=SELF)
def f3028(c: Cast) -> None:
    """Two printed clauses, one of them standing, so this is a trait with
    two watchers rather than a declared trigger -- a row with `on=` runs
    only when that event fires, and the substitution has to be in place
    before the racial power rolls anything.

    "Grants combat advantage to all attackers" is `to="team"`, which is
    you and your side -- everyone who will attack it in practice.
    Advantage is read off the blow rather than asked again, because a
    one-shot grant has been spent by then.

    The Arcana-for-Bluff half was dropped as unsayable and is not:
    `SkillCheck` is announced **before** its modifiers are totalled and
    the callback reads `ev.skill` back off the event, so writing the
    other skill onto it is the substitution itself rather than a bonus
    standing in for one. It is narrowed to a check made inside p7546 by
    holding that power's two ends, the way f1404 holds a heal's.
    """
    me = c.me
    inside: list[str] = []

    def hit(ev: Hit) -> None:
        if ev.attacker != me:
            return
        row = get(ev.power)
        if row is None or row.cls != "artificer" or row.reach is None:
            return
        if row.reach.kind != "melee" or not c.had_advantage(ev):
            return
        c.grants_advantage(on=ev.target, until=When.SONT, to="team")

    def opened(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == "p7546":
            inside.append(ev.power)

    def closed(ev: PowerResolved) -> None:
        if ev.actor == me and ev.power in inside:
            inside.remove(ev.power)

    def instead(ev: SkillCheck) -> None:
        if inside and ev.actor == me and ev.skill == "bluff":
            ev.skill = "arcana"

    c.watch(Hit, hit, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(PowerUsed, opened, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(PowerResolved, closed, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(SkillCheck, instead, until=When.ENCOUNTER, on=me, label=c.ref,
            window=Window.BEFORE)


@power("f3035", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("events.ShortRested",))
def f3035(c: Cast) -> None:
    """Spending an action point also hands an adjacent ally back a magic
    item's daily power.

    "Nothing asks a creature which of its rows that is" was true when
    this was marked and is not now: `Gear.worn` records the items and
    `Magic.powers` their rows, so `_item_dailies` is the list, and the
    ally picks which. One ally and one row, so the loop stops on the
    first hand-back that took.

    Dropped: the second sentence spends a use of a per-day allowance
    that is granted and spent inside a rest, and nothing announces one
    -- the same hold `cf:artificer-f0s1` itself carries.
    """
    me = c.me

    def spent(ev: ActionPointSpent) -> None:
        if ev.actor != me:
            return
        for who in c.within(1, of=me, side="ally"):
            rows = _item_dailies(c, who)
            if not rows:
                continue
            pick = c.choose(rows, "item daily power to hand back")
            if pick is not None and c.restore_use(pick, on=who):
                return

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER, on=me, label=c.ref)


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


def _hurt(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.amount > 0 and ev.target != ev.source


@power("f3041", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you or an ally under p10187 takes damage",
       on=Trigger(DamageApplied, _hurt, "somebody takes damage"))
def f3041(c: Cast) -> None:
    """Widens the trigger of a racial power to an ally taking damage, and
    makes both of you invisible when it goes off that way.

    The old marker said the shielding elixir arrives as a name with no
    ref. It does not have to: this file matches the three infusions to
    their refs by mechanic, and f2111's own card quotes the resistance
    that `p10187` grants. So "affected by your shielding elixir" is
    `c.suffering(p10187)`, which is the gate the row was missing.

    "Until you attack" is not a duration the engine holds, so it is
    written as what it is -- the clock plus a watcher that ends the
    effect on that creature's first attack roll.
    """
    ev = c.trigger
    who = ev.target
    warded = c.suffering(RESIST_INFUSION, include_self=True)
    if who != c.me and who not in warded:
        return
    if who == c.me and c.me not in warded:
        return
    if not c.use_power("p377"):
        return
    if who == c.me:
        return
    for one in (c.me, who):
        unseen = c.invisible(on=one, until=When.EONT)
        if unseen is None:
            continue

        def swung(rolled: AttackRolled, one: int = one,
                  unseen: Any = unseen) -> None:
            if rolled.attacker == one and not unseen.ended:
                c.world.effects.end(unseen, "attacked")

        c.watch(AttackRolled, swung, until=When.EONT, on=one, label=c.ref)


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


#: Both halves of the charge `cf:artificer-f0s0` banks, which is what the
#: four rows riding on it have no subject without. The feature's own row
#: names the same two, so the group holds together.
BANKED = ("events.ShortRested", "c.boost_roll()")


def _banked(ref: str, what: str) -> None:
    """`cf:artificer-f0s0` is declared now, and refused in play.

    The feature banks a +2 to one attack roll, spent as a free action
    *after* the roll. Both ends are missing and the marker now says so:
    the charge is laid during a short rest and nothing announces one, and
    a roll that has already landed cannot be added to -- `c.bonus` is
    read by the next roll, not by the one on the table. Nothing lays the
    charge, so nothing is "benefiting from" it and these four have no
    subject; the feature being named in prose was never what stopped
    them.
    """
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=BANKED)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} {_banked.__doc__}"


#: `cf:artificer-f0` is a declared row, so this is not a naming gap -- the
#: +2 it banks is the thing nothing lays, which is what its own sub-option
#: waits on too.
_feature("f2110", "Doubles the attack bonus one feature banks in a weapon.",
         todo=BANKED)
_banked("f3029", "Damage to an enemy beside an ally that charge helped.")
_banked("f3036", "An initiative bonus for whoever carries the banked charge.")
_banked("f3044", "Lends a racial power's benefit to the charge's wielder.")
