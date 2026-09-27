"""Swordmage, warden and monk feats.

Grouped because they are three short lists that share one shape and one
gap. The shape is a rider on the class's own powers, read off a keyword
or a reach -- cheap. The gap is "your second wind" and "your Flurry of
Blows", neither of which announces anything: the first is an action
rather than a power, the second a class feature named in prose.
"""

from __future__ import annotations

from typing import Any

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
from combat_engine.engine.dsl import get
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.query import holding

FEATURE = ("c.class_feature()",)


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


@power("f1119", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.no_provoke(when=)",))
def f1119(c: Cast) -> None:
    """Stops ranged powers provoking, for a turn, after a melee hit.
    `Power.no_provoke` is header data set per row; `c.no_provoke` has no
    gated form, so there is no way to say "not this turn"."""


@power("f613", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.basic_ability()",))
def f613(c: Cast) -> None:
    """Swaps which ability the melee basic rolls. `mba`'s attack line is
    header data shared by every creature. Same gap as the general
    f1016."""


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
       reach=PERSONAL, target=SELF, todo=("c.on_save()",))
def f1024(c: Cast) -> None:
    """Pays out on succeeding at a saving throw one class feature
    granted. The feature is named by ref in the prerequisite; what is
    missing is knowing *which* save a `SavingThrow` came from."""


# -- monk -------------------------------------------------------------------


@power("f2602", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_dice()",))
def f2602(c: Cast) -> None:
    """Raises the die of the class's unarmed strike. The dice are a
    string on a `Weapon` the chassis deals, and nothing rewrites one --
    the same symbol the ranger's f273 and the rogue's f185 want."""


def _flurry(ref: str, what: str) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=FEATURE)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} The class feature is named in prose with no ref."


_flurry("f1985", "Lengthens the reach of one target of a class feature.")
_flurry("f2589", "A damage bonus to that feature while holding one weapon.")
_flurry("f3166", "An attack bonus, and more damage from the same feature.")


@power("f3116", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.shift(through=)",))
def f3116(c: Cast) -> None:
    """Lets a shift pass through occupied squares while a named racial
    power is unspent. The power is named by ref and `Powers.times` reads
    whether it is spent -- but `c.shift` has no way to ignore
    occupancy, and `share=True` is one square rather than a path."""
