"""Weapon-slot magic items, heroic tier: their Properties and their Powers.

Nothing here declares a weapon. The ladder, the enhancement bonus, the
critical rider and the base-item restriction are columns in `game.db` and
are laid on by `engine/equipment.py`; what is written here is only the part
that needs a body.

Three things this corpus keeps asking for that the engine cannot say, each
marked with the symbol it wants rather than approximated:

* **"class X can use this weapon as an implement."** The commonest property
  in the whole slot. `Gear.implement` is computed from `Weapon.group`, so
  there is no door for it -- `c.as_implement()`.
* **"this weapon can be used as a heavy thrown weapon, range N/M"**, and
  "increase this weapon's range" -- `c.make_thrown()`, `c.weapon_range()`.
* **"the damage ignores resistance"** -- `c.ignore_resistance()`.

One judgement runs through the whole file. A great many lines read "using
this weapon", and the damage context carries `target`, `power`,
`opportunity`, `charge`, `dtype` and `crit` -- not the weapon. A gate on
the weapon is therefore impossible, and since the character is holding the
item for as long as the property is armed, these are written as though
every swing is the item's. That over-applies only for a character wielding
two weapons of which one is magical.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBlast,
    DamageType,
    Forced,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    Position,
    Ranged,
    Size,
    Trigger,
    When,
    Window,
    World,
    about_me,
    both,
    by_me,
    by_melee,
    cursed_by_me,
    get,
    power,
    query,
)

ITEM = "item"

#: Size order, for "a creature larger than you". `Size` is a `StrEnum`, so
#: its members do not compare by rank on their own.
_SIZES = (
    Size.TINY,
    Size.SMALL,
    Size.MEDIUM,
    Size.LARGE,
    Size.HUGE,
    Size.GARGANTUAN,
)


def _rank(size: Size) -> int:
    return _SIZES.index(size)


def _plus(c: Cast) -> int:
    """This block's own enhancement bonus, off the weapon it was laid on.

    The number is a column and is never written here -- but a body saying
    "equal to the enhancement bonus" has to read one. Falls back to the
    heroic minimum when the board has handed out no magic weapon, so an
    audited row still does something rather than silently doing nothing.
    """
    item = c.ref.split("x")[0].split("p")[0]
    magic = c.held(on=c.me, what="magic")
    for w in magic:
        if w.item == item:
            return w.enhancement
    return magic[0].enhancement if magic else 1


def _struck(c: Cast) -> int | None:
    """The creature the triggering attack was aimed at.

    `Triggers._at` aims a single-target enemy row at `ev.attacker`, which
    for a row triggered by **your own** hit is you -- so it falls through
    to the auto-targeter and can pick a different enemy than the one you
    just hit. Every "use this power when you hit" row reads the event.
    """
    foe = getattr(c.trigger, "target", None)
    return foe if foe is not None else c.target


def _bigger(c: Cast):  # noqa: ANN202
    """Gate: the creature taking this damage is larger than the wielder."""

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and _rank(c.size_of(on=foe)) > _rank(
            c.size_of(on=c.me)
        )

    return gate


def _of_type(dtype: DamageType):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("dtype") == dtype

    return gate


def _crit_by_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(ev, "critical", False)


def _vs_ac_by_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(ev, "vs", None) == AC


def _hit_big(world: World, me: int, ev: Any) -> bool:
    """You hit a Large or larger creature."""
    if getattr(ev, "attacker", None) != me:
        return False
    foe = getattr(ev, "target", None)
    pos = world.get(foe, Position) if foe is not None else None
    return pos is not None and _rank(pos.size) > _rank(Size.MEDIUM)


# -- level 1 ----------------------------------------------------------------


@power(
    "i1101x1",
    level=1,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.weapon_range()",),
)
def i1101x1(c: Cast) -> None:
    """Normal range +5 and long range +10: a change to the weapon itself,
    and `Weapon.ranged` is a column no body can reach."""


@power(
    "i1166x1",
    level=1,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1166x1(c: Cast) -> None:
    """The damage context carries `target`, so the victim's type words are
    the gate. Paragon numbers are out of scope; this is the heroic +1."""
    c.bonus(
        "damage",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(
            c.kinds_of(on=ctx.get("target")) & {"elemental", "immortal"}
        )
        if ctx.get("target") is not None
        else False,
    )


@power(
    "i1169x1",
    level=1,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1169x1(c: Cast) -> None:
    """"An object" is whatever is on the map and is not a creature, which
    is exactly what `c.scenery` answers."""
    c.bonus(
        "damage",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") in c.scenery(),
    )


@power(
    "i3391x1",
    level=1,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3391x1(c: Cast) -> None:
    """"Until the enemy drops to 0 hit points" is free: `c.enemies` filters
    out the dead, so the gate stops being true the moment it falls. The
    printed clause is "powers that do not include the enemy as a target",
    and the attack context is per-target, which is the same thing for
    every power that has one target and close enough for the rest."""

    def first_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        foe = ev.target
        c.penalty(
            "attack",
            2,
            on=c.me,
            until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") != foe and foe in c.enemies(),
        )

    c.watch(Hit, first_hit, until=When.ENCOUNTER, once=True)


@power(
    "i601x1",
    level=1,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()",),
)
def i601x1(c: Cast) -> None:
    """A blade that counts as an implement for one class. `Gear.implement`
    is derived from the weapon's group, so nothing can say it."""


@power(
    "i602x1",
    level=1,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()",),
)
def i602x1(c: Cast) -> None:
    """A bow that counts as an implement for one class."""


@power(
    "i849x1",
    level=1,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i849x1(c: Cast) -> None:
    """"At maximum hit points" is `c.wounded` inverted. The extra die is a
    rolled modifier rather than a body line, because the damage is not this
    row's to deal -- it rides on whatever attack lands."""
    c.bonus(
        "damage",
        0,
        dice="1d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None
        and not c.wounded(on=ctx["target"]),
    )


# -- level 2 ----------------------------------------------------------------


@power(
    "i1028p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a melee weapon attack using this weapon",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with this weapon"),
    todo=("c.store_damage()", "c.on_defiling()"),
)
def i1028p1(c: Cast) -> None:
    """The weapon banks the damage dealt and pays it back as temporary hit
    points the first time one particular kind of self-inflicted damage
    happens. Neither the store nor that damage source exists."""


@power(
    "i1045x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.ignore_resistance()",),
)
def i1045x1(c: Cast) -> None:
    """Damage that ignores one resistance. `c.resist` grants resistance and
    `c.vulnerable` adds to the damage; neither bypasses."""


@power(
    "i1057x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_second_wind()", "c.total_defence()"),
)
def i1057x1(c: Cast) -> None:
    """Both halves hang on noticing an action. Total defence is not an
    action the engine has, and a second wind announces only `SurgeSpent`,
    which every other surge announces too."""


@power(
    "i1138x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1138x1(c: Cast) -> None:
    """The penalty lands on the enemy and gates on *its* attack. The attack
    context carries `ranged`; an area attack is read off the power's
    reach, since `ranged` is false for a close burst."""

    def gate(ctx: dict[str, Any]) -> bool:
        if ctx.get("ranged"):
            return True
        p = get(ctx.get("power") or "")
        return p is not None and p.reach is not None and p.reach.kind == "area_burst"

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        c.penalty("attack", 2, on=ev.target, until=When.EONT, when=gate)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i1150x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.make_thrown()",),
)
def i1150x1(c: Cast) -> None:
    """Gives a melee weapon the heavy thrown property and a range.
    `c.as_ranged` is the one-shot version and says "the next melee attack";
    a standing property of the weapon has no door."""


@power(
    "i1150p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit a Large or larger creature with an attack using this weapon",
    on=Trigger(Hit, _hit_big, "you hit a Large or larger creature"),
)
def i1150p1(c: Cast) -> None:
    """A free action after the blow has landed, so the extra damage is a
    second, flat application rather than a rider on the roll. Heroic
    number only."""
    foe = _struck(c)
    if foe is not None:
        c.flat(2, on=foe)


@power(
    "i1168x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1168x1(c: Cast) -> None:
    """`dtype` is resolved before the damage modifiers are summed, so the
    gate sees the type the blow actually comes out as."""
    c.bonus(
        "damage", 1, on=c.me, until=When.ENCOUNTER,
        when=_of_type(DamageType.LIGHTNING),
    )


@power(
    "i1252x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.make_thrown()",),
)
def i1252x1(c: Cast) -> None:
    """Heavy thrown with a range, plus a class-feature clause that recalls
    the blade from a mile away -- out of combat either way."""


@power(
    "i1319p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i1319p1(c: Cast) -> None:
    """`once=True` is "your next attack": a one-shot attack bonus is spent
    on the roll, which is the moment it is read."""
    foe = _struck(c)
    if foe is None:
        return
    c.bonus(
        "attack", 1, kind="power", on=c.me, until=When.ENCOUNTER, once=True,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power(
    "i1348p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=NO_TARGET,
)
def i1348p1(c: Cast) -> None:
    """Turning difficult ground into normal ground is `c.floor` -- the one
    verb that lays passable footing over what is there. Sustain is dropped:
    the vegetation is destroyed, not held down."""
    c.floor(c.area(), until=When.ENCOUNTER, sustain=None)


@power(
    "i1359x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1359x1(c: Cast) -> None:
    """A skill bonus, but a real modifier rather than an inert row: skill
    mods are read under `skill:<name>`."""
    c.bonus(
        "skill:intimidate", _plus(c), kind=ITEM, on=c.me, until=When.ENCOUNTER
    )


@power(
    "i1376x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1376x1(c: Cast) -> None:
    """"You can" -- so it is offered, not forced."""

    def on_crit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.critical and c.may("shift 1", who=c.me):
            c.shift(1)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i1376p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def i1376p1(c: Cast) -> None:
    """1d6-3 is as often a penalty as a bonus, and the two are different
    calls: a penalty takes no kind, by the rule. `once=True` spends it on
    the roll it was declared before."""
    n = c.roll("1d6") - 3
    if n >= 0:
        c.bonus("attack", n, kind="power", on=c.me, until=When.EOT, once=True)
    else:
        c.penalty("attack", -n, on=c.me, until=When.EOT, once=True)


@power(
    "i1446x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1446x1(c: Cast) -> None:
    """An item bonus, so `kind="item"` -- and it therefore does not stack
    with another item bonus to damage, which is the printed rule."""
    c.bonus(
        "damage", _plus(c), kind=ITEM, on=c.me, until=When.ENCOUNTER,
        when=_bigger(c),
    )


@power(
    "i1490x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_form()", "c.in_form()"),
)
def i1490x1(c: Cast) -> None:
    """A defence bonus that begins when a particular kind of form is
    assumed and lasts only while it is held. `c.form` installs one and
    nothing announces it or asks which one is on."""


@power(
    "i1505x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()",),
)
def i1505x1(c: Cast) -> None:
    """A blade that counts as an implement for one class."""


@power(
    "i1505p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
)
def i1505p1(c: Cast) -> None:
    c.bonus("attack", 2, kind="power", until=When.SONT)
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, kind="power", until=When.SONT)


@power(
    "i1561x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.heal_bonus()",),
)
def i1561x1(c: Cast) -> None:
    """Adds to the amount one named healing row restores. Healing is not
    read through `Mods`, so there is no key to write a bonus under."""


@power(
    "i1561p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def i1561p1(c: Cast) -> None:
    """The surge is spent but the amount is printed, so this is not
    `c.surge`: the ally spends and then regains a flat number. Heroic
    number only."""
    if c.may("spend a healing surge"):
        c.spend_surge(on=c.target)
        c.heal(5 + c.wis_mod)


@power(
    "i1568x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1568x1(c: Cast) -> None:
    """"An additional +1" and no type named, so untyped -- which is the
    difference between this and the item bonus two rows up."""
    c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, when=_bigger(c))


@power(
    "i1580x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()", "c.cover_from()"),
)
def i1580x1(c: Cast) -> None:
    """Two clauses, two gaps: an implement for one class, and damage to
    whichever creature was granting the target cover. `query.cover_between`
    answers how much cover there is, never who is giving it."""


@power(
    "i1582x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.make_thrown()",),
)
def i1582x1(c: Cast) -> None:
    """Heavy thrown with a range, as a standing property of the weapon."""


@power(
    "i1582p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def i1582p1(c: Cast) -> None:
    """Declared as a ranged attack with the weapon's own dice rather than
    routed through `c.basic(ranged=True)`, which would look for a ranged
    weapon the wielder does not have -- the whole point of the item. The
    spear staying in the target until the hold ends is bookkeeping with no
    mechanical consequence here."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "i1689x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1689x1(c: Cast) -> None:
    c.bonus(
        "damage", 1, on=c.me, until=When.ENCOUNTER,
        when=_of_type(DamageType.FIRE),
    )


@power(
    "i1771x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i1771x1(c: Cast) -> None:
    """Who is proficient with the weapon is a character-build fact, like a
    feat's prerequisite: `Weapon.proficiency` is already a column and the
    engine never asks whether the wielder was allowed to pick it up. So
    this is deliberately inert rather than unfinished."""
    c.note("i1771x1: proficiency with a simple weapon carries to this one")


@power(
    "i1771p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.expend()",),
)
def i1771p1(c: Cast) -> None:
    """Trades one spent encounter power for another. `c.restore_use` hands
    a use back; nothing burns one, so only half the trade can be said and
    half of it is a straight gift."""


@power(
    "i1793p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.grant_points()",),
)
def i1793p1(c: Cast) -> None:
    """A power point out of nowhere, restricted to augmenting.
    `c.transfer_points` moves points between creatures and `c.spend_points`
    spends them; neither creates one."""


@power(
    "i2008x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()",),
)
def i2008x1(c: Cast) -> None:
    """An implement for one class and one race, without the proficiency
    bonus -- and the implement half alone has no door."""


@power(
    "i2008p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()", "c.cast_through()"),
)
def i2008p1(c: Cast) -> None:
    """Fires another power out of this weapon, taking the weapon's range
    and proficiency instead of the power's. Nothing redirects a power
    through a held object."""


@power(
    "i2009x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()",),
)
def i2009x1(c: Cast) -> None:
    """An implement for one class and one race."""


@power(
    "i2010x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()",),
)
def i2010x1(c: Cast) -> None:
    """An implement for one class and one race."""


@power(
    "i2010p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    trigger="you hit a target affected by your curse with this weapon",
    on=Trigger(Hit, both(by_me, cursed_by_me), "you hit a cursed enemy"),
)
def i2010p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.teleport(1 + _plus(c), who=foe)


@power(
    "i2019p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="an enemy makes a melee attack against you",
    todo=("c.oppose_attack()", "c.basic(harmless=)"),
)
def i2019p1(c: Cast) -> None:
    """A parry: swing back, and if your roll beats the roll against you the
    attack misses. Two gaps -- nothing compares one attack roll with
    another, and `c.basic` always deals its damage where this one must
    not. `c.cancel` is an interrupt's verb and the printed action is a
    reaction, so even the miss cannot be spelled here."""


@power(
    "i2054p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i2054p1(c: Cast) -> None:
    """"Until you are no longer adjacent to it" is not a `When`, so the
    hold is laid for the encounter and a watch on movement ends it. Either
    creature moving can break the adjacency, which is why the watch is on
    `Moved` rather than on the target."""
    foe = _struck(c)
    if foe is None:
        return
    held = c.immobilized(on=foe, until=When.ENCOUNTER)
    if held is None:
        return

    def apart(ev: Moved) -> None:
        if not c.adjacent(foe):
            c.world.effects.end(held, "no longer adjacent")

    c.watch(Moved, apart, until=When.ENCOUNTER)


@power(
    "i2100x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2100x1(c: Cast) -> None:
    """"No ally is closer" is measured between two creatures, which
    `c.distance` cannot do -- it always starts at the caster."""

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None:
            return False
        mine = query.distance_between(c.world, c.me, foe)
        return all(
            query.distance_between(c.world, a, foe) >= mine for a in c.allies()
        )

    c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, when=gate)


@power(
    "i2108p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def i2108p1(c: Cast) -> None:
    """Declared as a ranged attack rather than routed through
    `c.basic(ranged=True)`: the item exists precisely because the weapon
    has no thrown property, so looking for a ranged weapon finds nothing.
    The augment is read back off how many points were spent on this row."""
    extra = 1 if c.points_spent(c.ref) >= 2 else 0
    if c.strike():
        c.damage(c.w(1 + extra), c.str_mod)


@power(
    "i2125x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2125x1(c: Cast) -> None:
    """The card says *item* bonus and `c.initiative` carries no kind, so
    this one cannot be typed -- it would stack with another item bonus to
    initiative where the printed rule says the larger wins. Nothing reads
    an `"initiative"` modifier, so a typed `c.bonus` would be worse: it
    would be silently ignored rather than slightly too generous."""
    c.initiative(_plus(c), on=c.me)


@power(
    "i2125p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you score a critical hit with this weapon",
    on=Trigger(Hit, _crit_by_me, "you score a critical hit"),
)
def i2125p1(c: Cast) -> None:
    """"Before the end of your turn" is what an extra action already
    means, so there is nothing further to hold."""
    c.extra_action(ActionType.MOVE, on=c.me)


@power(
    "i2150p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you attack an enemy with this weapon and miss",
    on=Trigger(Miss, by_me, "you attack an enemy with this weapon and miss"),
)
def i2150p1(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    others = [e for e in c.within(5, of=foe, side="enemy") if e != foe]
    if others:
        c.basic(on=c.choose(others, "who the second shot goes to"), ranged=True)


@power(
    "i2169p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2169p1(c: Cast) -> None:
    c.penalty("attack", 2, on=_struck(c), until=When.SAVE_ENDS)


@power(
    "i2175p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2175p1(c: Cast) -> None:
    c.dazed(on=_struck(c), until=When.EONT)


@power(
    "i2503x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2503x1(c: Cast) -> None:
    c.bonus(
        "damage", 1, on=c.me, until=When.ENCOUNTER,
        when=_of_type(DamageType.COLD),
    )


@power(
    "i2528x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2528x1(c: Cast) -> None:
    c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, when=_bigger(c))


@power(
    "i2657x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2657x1(c: Cast) -> None:
    """`c.forces` lengthens every shove this creature makes, and its gate
    is handed `how` -- so "a power that slides" is sayable without also
    lengthening pushes and pulls, which the card does not grant."""
    c.forces(
        _plus(c), on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("how") == Forced.SLIDE,
    )

    def on_crit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.critical:
            c.prone(on=ev.target)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i2657p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2657p1(c: Cast) -> None:
    c.slide(_plus(c), on=_struck(c))


@power(
    "i2926x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()", "c.spirit_reach()"),
)
def i2926x1(c: Cast) -> None:
    """An implement for one class, and a widening of the reach a power
    printed "melee spirit" has. `Range.from_` names the origin and nothing
    changes how far from it a target may stand."""


@power(
    "i2927x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()", "c.origin_of()"),
)
def i2927x1(c: Cast) -> None:
    """An implement for one class, and a swap of which square a power
    printed "melee spirit" originates from. `Range.from_` is a column on
    the power and no body can move it."""


@power(
    "i3011x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3011x1(c: Cast) -> None:
    """**Dropped:** the clause making this an implement for one class --
    `Gear.implement` is derived from the weapon's group and no body can
    reach it. The Stealth penalty is the rest of the card and it stands
    on its own; skill modifiers are read under `skill:<name>`."""
    plus = _plus(c)

    def on_hit(ev: Hit) -> None:
        if ev.attacker == c.me:
            c.penalty("skill:stealth", plus, on=ev.target, until=When.EONT)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i3011p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i3011p1(c: Cast) -> None:
    """The printed entry condition -- you must already have hit this target
    once -- is a fact about a creature the row does not name, so it is
    dropped rather than approximated. `c.ignore_cover` covers concealment
    as well, which is what the card waives."""
    c.ignore_cover(on=c.me, until=When.EONT)


@power(
    "i3060p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy bloodies you",
    on=Trigger(Bloodied, about_me, "an enemy bloodies you"),
)
def i3060p1(c: Cast) -> None:
    """`Bloodied` names its subject `actor`, so the predicate reads that
    and nothing else."""
    allies = c.within(5, side="ally")
    if allies:
        c.grant_attack(c.choose(allies, "who takes the free attack"))


@power(
    "i3069x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.as_implement()",),
)
def i3069x1(c: Cast) -> None:
    """A bow that counts as an implement for one class."""


@power(
    "i3069p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you attack an enemy with a power using this weapon",
    on=Trigger(Hit, by_me, "you attack an enemy with this weapon"),
)
def i3069p1(c: Cast) -> None:
    """"With a bard attack power" is a class gate the engine has no way to
    ask of a power mid-fight, so any attack of the wielder's arms it. The
    bonus is aimed at one enemy, which the attack context carries as
    `target`."""
    foe = _struck(c)
    if foe is None:
        return
    for ally in c.within(5, of=foe, side="ally"):
        c.bonus(
            "attack", 2, kind="power", on=ally, until=When.EONT,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power(
    "i3074p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.forgo_save()",),
)
def i3074p1(c: Cast) -> None:
    """Trades a saving throw one class feature would hand you for extra
    damage. `c.unsave` fails a save being rolled; declining one that has
    been offered is a different thing, and the feature is not modelled."""


@power(
    "i3103x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.strip_resistance()",),
)
def i3103x1(c: Cast) -> None:
    """A critical takes the target's resistances away for a while.
    `c.resist` grants one and `c.vulnerable` offsets one; neither removes
    what a creature already has."""


@power(
    "i3103p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.ignore_resistance()",),
)
def i3103p1(c: Cast) -> None:
    """Your powers ignore resistance for the rest of the fight -- the same
    gap as the property above, from the attacker's side."""


@power(
    "i3140x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i3140x1(c: Cast) -> None:
    """Stowing, a command word and a weapon that cannot be found on a
    search. Nothing here touches a fight, so it is inert by choice."""
    c.note("i3140x1: stowed, the weapon cannot be found or taken, and comes back to hand on a word")


@power(
    "i3156x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3156x1(c: Cast) -> None:
    """**Dropped:** the +10 to long range, which is a column on the weapon
    and not something a body can change. Waiving the long-range penalty is
    the other half and is a verb, so it is written."""
    c.ignores_long_range(on=c.me, until=When.ENCOUNTER)


@power(
    "i528x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i528x1(c: Cast) -> None:
    """The attack context carries `opportunity`, so this is one gate and
    not a guess at which row an opportunity attack happens to be."""
    c.bonus(
        "attack", 2, kind=ITEM, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "i581x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i581x1(c: Cast) -> None:
    """**Dropped:** maximum damage against objects -- `c.maximise` takes no
    `when=`, so it cannot be made to apply to one kind of target and not
    another, and an ungated one would maximise every swing. The item bonus
    against animates is the rest of the card."""
    c.bonus(
        "damage", 2, kind=ITEM, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: "animate" in c.kinds_of(on=ctx.get("target"))
        if ctx.get("target") is not None
        else False,
    )


@power(
    "i696p1",
    level=2,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i696p1(c: Cast) -> None:
    """The wielder pays the whole allowance rather than choosing a smaller
    one: the trade is always worth at least double. "Cannot be reduced or
    prevented" is not sayable and the self-damage is dealt flat, which
    resistance would still eat -- a resistant wielder gets the payout
    cheap, and nothing worse."""
    foe = _struck(c)
    if foe is None:
        return
    cost = _plus(c)
    held = c.held(on=c.me)
    two_handed = bool(held) and held[0].two_handed
    c.flat(cost, on=c.me)
    c.flat(cost * (3 if two_handed else 2), on=foe)


# -- level 3 ----------------------------------------------------------------


@power(
    "i1120x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_feature()",),
)
def i1120x1(c: Cast) -> None:
    """Rides on a class feature firing. A feature is an ordinary row, but
    nothing announces one going off in a way a second row can answer --
    `PowerUsed` is emitted before the body and only for a row that was
    used, not for a trait that simply became true."""


@power(
    "i1139p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def i1139p1(c: Cast) -> None:
    """The card names no target -- "the next creature you attack" -- and
    the engine has no way to hold an advantage for a creature not yet
    chosen. Choosing it when the minor action is spent is the nearest
    honest reading, and `once=True` keeps it to one attack."""
    c.grants_advantage(until=When.EOT, once=True)


@power(
    "i1155x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1155x1(c: Cast) -> None:
    """Two conditions in one gate: the attack has to be an opportunity one
    and the wielder has to still have a point. The second is asked when
    the modifier is read, which is the moment the card means."""
    c.bonus(
        "attack", 2, kind=ITEM, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")) and c.points() >= 1,
    )


@power(
    "i1295x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1295x1(c: Cast) -> None:
    """"Any forced movement effect", so no gate: pushes, pulls and slides
    alike."""
    c.forces(1, on=c.me, until=When.ENCOUNTER)


@power(
    "i1300p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
    todo=("c.next_attack_becomes()",),
)
def i1300p1(c: Cast) -> None:
    """Rewrites the next basic attack into a burst against a different
    defence with different damage. `c.widen_areas` grows an area a power
    already has; nothing turns a single-target attack into one."""


@power(
    "i1318p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make an attack with this weapon that targets AC",
    on=Trigger(
        AttackDeclared, _vs_ac_by_me, "you attack with this weapon against AC",
        window=Window.BEFORE,
    ),
)
def i1318p1(c: Cast) -> None:
    """**Dropped:** sending the attack at Fortitude instead of AC. The
    defence is read off the power's own `Attack` line before the roll and
    nothing redirects it. The extra damage is the other half and lands:
    declared in the `BEFORE` window so the modifier is installed before the
    triggering attack rolls its damage, and `once=True` spends it there."""
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EOT, once=True)
