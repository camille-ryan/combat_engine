"""Swordmage, warden and monk feats.

Grouped because they are three short lists that share one shape and one
gap. The shape is a rider on the class's own powers, read off a keyword
or a reach -- cheap. The gap is "your second wind" and "your Flurry of
Blows", neither of which announces anything: the first is an action
rather than a power, the second a class feature named in prose.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.monk.level_0 import FLURRIES
from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Condition,
    Hit,
    Keyword,
    SecondWind,
    Trigger,
    When,
    about_me,
    power,
)
from combat_engine.engine.basic import MELEE
from combat_engine.engine.dsl import get
from combat_engine.engine.events import OpportunityWindow, PowerResolved
from combat_engine.engine.query import holding
from combat_engine.engine.types import Window


def _my_ranged_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.reach.kind in ("ranged", "area_burst", "wall")
    )


def _my_melee_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return ev.attacker == me and p is not None and p.reach.kind == "melee"


def _my_opportunity_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and getattr(ev, "opportunity", False)


# -- swordmage --------------------------------------------------------------


def _weapon_roll(ctx: dict[str, Any]) -> bool:
    """"Weapon damage rolls": the damage context carries the row that
    dealt them and the keyword is on the row."""
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.WEAPON in p.keywords


@power("f1118", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a ranged or area power",
       on=Trigger(Hit, _my_ranged_hit, "you hit at range"))
def f1118(c: Cast) -> None:
    """The bonus applies to *melee* powers, so the gate is the reach of
    whatever is being rolled -- which the attack context reaches through
    the power's own header."""
    me = c.me
    for what in ("attack", "damage"):
        c.bonus(
            what, 1, on=me, until=When.EONT,
            when=lambda ctx: (
                (p := get(ctx.get("power", ""))) is not None
                and p.reach.kind == "melee"
            ),
        )


def _my_melee_swordmage_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.cls == "swordmage"
        and p.reach.kind == "melee"
    )


@power("f1119", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a melee swordmage attack power",
       on=Trigger(Hit, _my_melee_swordmage_hit, "you hit in melee"))
def f1119(c: Cast) -> None:
    """Stops this swordmage's ranged and area powers provoking for a turn.

    `c.no_provoke` still takes no gate, which is what this row was marked
    for -- but the gate does not have to live there. The window is a
    cancellable `OpportunityWindow` and it carries `why`, which `dsl` sets
    to "<ref> is a ranged power" when a row at range opens one. So the ref
    that provoked is readable, and refusing only the rows the card names
    is the same three-line veto `c.no_provoke` installs with one more
    question in it.

    A bare `c.no_provoke(on=c.me)` would have been much too generous:
    walking out of a threatened square opens the same window, and this
    card says nothing about moving.
    """
    me = c.me

    def veto(ev: OpportunityWindow) -> None:
        if ev.provoker != me:
            return
        p = get(ev.why.split(" ", 1)[0])
        if p is not None and p.cls == "swordmage" and p.reach.kind in (
            "ranged", "area_burst", "wall"
        ):
            ev.cancel("the swordmage's powers do not provoke this turn")

    c.watch(OpportunityWindow, veto, until=When.EONT, on=me,
            window=Window.BEFORE, label=f"{c.ref} no provoke")


@power("f613", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f613(c: Cast) -> None:
    """Swaps which ability the melee basic rolls.

    `mba`'s attack line is header data shared by every creature and is
    not rewritable, which is what this was marked for -- but the number
    it produces is. Both contexts carry the ref of the row being rolled,
    so the difference between the two modifiers, laid against `mba` and
    nothing else, comes out as an Intelligence-based swing. An
    opportunity attack is a melee basic attack and rolls the same ref,
    so it is covered without being mentioned.

    **Damage as well as the roll**, which is the judgement call here:
    `_melee_basic` pays `c.damage(c.w(1), c.str_mod)`, so the Strength
    modifier the card replaces is in both halves of "making a basic
    attack" and swapping only one would leave the row half true.
    """
    swap = c.int_mod - c.str_mod
    if not swap:
        return
    for what in ("attack", "damage"):
        c.bonus(what, swap, on=c.me, until=When.ENCOUNTER,
                when=lambda ctx: ctx.get("power") == MELEE)


@power("f612", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recall_weapon()",))
def f612(c: Cast) -> None:
    """Calls a bonded weapon back to hand from twenty squares. Picking
    one up off the floor landed this session, but that is adjacency --
    nothing fetches at range, and `docs/blocked.json` records the same
    gap as `cf:swordmage-f0`."""


@power("f627", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f627(c: Cast) -> None:
    """A spellbook and what goes in it. `Powers.owned` is the book and
    `chargen.spellbook` fills it; this is a build-time number."""


# -- warden -----------------------------------------------------------------


@power("f585", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an opportunity attack",
       on=Trigger(Hit, _my_opportunity_hit, "you hit on an opportunity"))
def f585(c: Cast) -> None:
    """`Hit` does not declare `opportunity` -- `resolve.attack` sets it
    afterwards as a plain attribute -- so the predicate reads it with
    `getattr`, which `AUTHORING.md` says outright."""
    c.condition(Condition.SLOWED, on=c.trigger.target, until=When.EOT)


@power("f1827", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you immobilize or slow an enemy with a hammer or mace",
       on=Trigger(PowerResolved, lambda w, me, ev: (
           ev.actor == me and ev.power != "f1827"
       ), "you finish a power"))
def f1827(c: Cast) -> None:
    """Extra damage to whatever this blow held down.

    **Declared on `PowerResolved`, not on `Hit`.** I wrote it on `Hit`
    and the docstring claimed the condition was "checked after the hit
    resolved". It was not: `resolve.attack` emits `Hit` from *inside*
    the power's body, before the body applies its riders -- so the test
    read whatever slow happened to be on the target already and never
    the one the hammer had just landed. `PowerResolved` is announced
    when the body is done, which is the moment this row is printed for.

    The weapon is checked in the body rather than the predicate because
    a predicate gets no `Cast`.
    

    **The predicate excludes this row's own ref.** Declared on
    `PowerResolved` with `ev.actor == me` alone, the row answers its
    *own* resolution -- firing is a power use, which resolves, which
    offers it again -- and the stack goes with it. The traceback
    surfaces inside `query.can_act`, so it reads as an engine fault
    rather than a content one. Any row triggered on any use or
    resolution by its own caster has this shape.
    """
    if not (holding(c.world, c.me, "hammer") or holding(c.world, c.me, "mace")):
        return
    for foe in c.trigger.targets:
        if c.is_(Condition.SLOWED, on=foe) or c.is_(Condition.IMMOBILIZED, on=foe):
            c.flat(c.con_mod, on=foe)


@power("f583", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f583(c: Cast) -> None:
    """Weapon damage rolls only, which the damage context answers through
    the row that dealt them."""
    c.bonus("damage", c.con_mod, on=c.me, until=When.EONT, when=_weapon_roll)


@power("f584", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f584(c: Cast) -> None:
    """A free action answering the same moment, so the shift is simply
    taken. A warden with no Wisdom bonus shifts nowhere."""
    if c.wis_mod > 0:
        c.shift(c.wis_mod)


@power("f1024", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("SavingThrow.granted_via",))
def f1024(c: Cast) -> None:
    """Pays out on succeeding at a saving throw `cf:warden-f0` granted.

    **Re-aimed.** `c.on_save()` was the wrong symbol: `SavingThrow` is an
    ordinary event and `c.watch` reaches it, so there is nothing missing
    on that side. What is missing is on the event -- `Effects.save`
    builds it with `against=str(eff)`, the effect being *saved against*,
    and nothing records which row handed the throw over. The feature
    rolls its save from inside a `TurnStart` watch, so the only thing
    separating it from the ordinary end-of-turn throw is when in the turn
    it happened, and "the first save of my turn" is a guess rather than
    the printed gate.
    """


# -- monk -------------------------------------------------------------------


@power("f2602", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2602(c: Cast) -> None:
    """The class's unarmed strike rolls a d10 rather than a d8.

    `c.weapon_dice`, not `c.change_dice`: the die is a field on the `Weapon`
    rather than on any row, so this edits the character's own copy and the
    six places that read `weapon.damage` see it without being changed.

    **By ref, twice, and not by group.** The group holds three weapons and
    one of them is a spiked gauntlet, which this card says nothing about. The
    two refs are the same weapon under two spellings: the chassis deals a
    monk `w:unarmed`, which the database does not have -- it carries this
    class's numbers under a generic ref -- and the row that *is* in the
    database spells it out. Both are named so the row is right whichever the
    character ends up holding, and the mismatch itself is filed."""
    c.weapon_dice("1d10", ref="w:unarmed", on=c.me)
    c.weapon_dice("1d10", ref="w:monk-unarmed-strike", on=c.me)


#: **The feature has refs after all.** Both of these were marked
#: `spec.power_ref()` on the grounds that the class feature is named in
#: prose with no id. It is, but the five cards that *are* the feature are
#: written down in `powers/monk/level_0.py` as `FLURRIES`, and
#: `cf:monk-f0s0`..`s4` each hand one of them over -- so "your Flurry of
#: Blows power" is a membership test and not a naming gap. `p11215` in
#: the same file already reads the list for the same reason.


@power("f1985", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_reach(ref)",))
def f1985(c: Cast) -> None:
    """Lengthens the reach of one target of the class feature.

    **Re-aimed.** The rows are `FLURRIES` and the spear is `c.wielding`,
    so neither half of the gate is missing any more. What is missing is
    the payload: all five cards are `reach=Melee(1)`, that is header data
    read when targets are picked, and nothing in the vocabulary stretches
    one row's reach for one use. `c.threatens` is the neighbouring verb
    and speaks only for the opportunity window.
    """


@power("f2589", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2589(c: Cast) -> None:
    """A damage bonus to the class feature while holding one weapon.

    The five cards pay with `c.flat`, and `c.flat` goes through
    `deal_damage` with `from_attack` left true -- so the blow *is*
    offered the damage modifiers, and `detail` is the card's own ref,
    which is what the damage context carries as `power`. The claim
    beside `f3166` that a `c.flat` payout "is never offered a damage
    modifier" is not true of the code.

    The grip is asked inside the gate rather than once, so putting the
    club down loses the bonus, which is what "while wielding" says.
    """
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") in FLURRIES and c.wielding("club"))


@power("f3166", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3166(c: Cast) -> None:
    """Both halves are written now.

    The attack context carries `power`, so "monk implement attack powers"
    is read off the declared row rather than guessed, and the grip is
    asked inside the modifier -- a monk that puts the sword down loses
    the bonus, which is what "while wielding" says.

    **The second sentence was dropped on a false reading of the code.**
    It said the five feature cards pay with `c.flat`, which goes straight
    to `deal_damage` and is never offered a damage modifier. `c.flat`
    calls `deal_damage` with `from_attack` at its default of true, so the
    damage mods are read for it exactly as they are for `c.damage`, and
    `detail` is the card's ref. So the rider is an ordinary damage bonus
    gated on the five refs, and it cannot raise anything else the monk
    swings.
    """
    me, world = c.me, c.world

    def monk_implement(ctx: dict[str, Any]) -> bool:
        if not any(w.ref == "w:longsword" for w in holding(world, me)):
            return False
        p = get(ctx.get("power") or "")
        return (
            p is not None
            and p.cls == "monk"
            and Keyword.IMPLEMENT in p.keywords
            and p.is_attack
        )

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=monk_implement)
    def in_both_hands() -> bool:
        """A versatile blade is in two hands when nothing else is in one.

        The engine records no grip -- `cf:fighter-talent-rest` is blocked
        on the same thing -- but it records what is *in hand*, and a monk
        holding one versatile weapon and no shield has the other hand on
        it. `c.wielding("two-handed")` is the wrong question: that reads
        the weapon's own properties, and a longsword is versatile rather
        than two-handed, so the gate would be false in every fight.
        """
        held = holding(world, me)
        return (
            len(held) == 1
            and held[0].ref == "w:longsword"
            and not c.wielding("shield")
        )

    c.bonus(
        "damage", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") in FLURRIES and in_both_hands(),
    )


@power("f3116", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.phasing(when=)",))
def f3116(c: Cast) -> None:
    """Lets a shift pass through occupied squares while a named racial
    power is unspent.

    **Re-aimed.** `c.shift(through=)` was the wrong symbol: the row does
    not take the shift, a monk power does, so there is no call here to
    pass an argument to. Moving through an occupied square is
    `c.phasing`, which exists -- what it has no form of is a gate, and
    this card grants it for one kind of movement out of one kind of row.
    Laid bare it would let the monk walk through walls all fight.
    """
