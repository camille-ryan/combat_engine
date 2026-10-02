"""Weapon-slot magic items, heroic tier: their Properties and their Powers.

Nothing here declares a weapon. The ladder, the enhancement bonus, the
critical rider and the base-item restriction are columns in `game.db` and
are laid on by `engine/equipment.py`; what is written here is only the part
that needs a body.

"Class X can use this weapon as an implement" is the commonest property in
the slot -- eleven blocks in the first sixty -- and `c.as_implement` is the
verb for it. The one thing the corpus keeps asking for that still cannot be
said is a change to the **weapon's own columns**: "this weapon can be used
as a heavy thrown weapon, range N/M" and "increase this weapon's range",
marked `c.make_thrown()` and `c.weapon_range()`. `Weapon.ranged` and
`Weapon.properties` are fields on the object in `Gear`, and writing to them
from a body is not a change a body may make: clearing `ranged` is what
takes a weapon out of `Gear.melee`, so hanging a thrown range on a hammer
would stop it being a hammer.

"The damage ignores resistance" **is** sayable -- `c.ignore_resistance`
landed and two rows here use it.

One judgement runs through the whole file. A great many lines read "using
this weapon", and the damage context carries `target`, `power`,
`opportunity`, `charge`, `dtype`, `dtypes`, `crit`, `ranged`, `advantage`
and the two granted-swing keys -- not the weapon, and not the hand. A gate
on the weapon is therefore impossible, and since the character is holding
the item for as long as the property is armed, these are written as though
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
    EffectApplied,
    Forced,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    Position,
    Powers,
    Ranged,
    SecondWind,
    Size,
    TotalDefence,
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


def _weapon_damage(ctx: dict[str, Any]) -> bool:
    """The blow being resolved came out of a weapon power."""
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.WEAPON in p.keywords


def _melee_spirit(ctx: dict[str, Any]) -> bool:
    """The row being measured takes its range from the spirit companion.

    `dsl.area_of` hands `_stretched` a context of `power` and `kind`, so a
    reach modifier can be narrowed to "Melee spirit" rows -- which is
    `Range.from_ == "companion"`, the same column `measured_from` reads.
    """
    p = get(ctx.get("power", ""))
    return p is not None and p.reach is not None and p.reach.from_ == "companion"


def _hit_already(world: World, me: int, foe: int) -> bool:
    """Has this creature already landed a blow on that one this fight?

    `world.bus.log` is the tally, which is the only record of what has
    happened: nothing on a creature counts who it has hit.
    """
    return any(
        isinstance(past, Hit) and past.attacker == me and past.target == foe
        for past in world.bus.log
    )


def _bard_power(world: World, me: int, ev: Any) -> bool:
    """Was the row that caused this a bard attack power?

    `Hit` carries `power` and `Power.cls` is the column, the same lookup
    `by_melee` and `by_keyword` make for the reach and the keywords. A
    `Hit` is already an attack landing, so the class is the whole gate.
    """
    p = get(getattr(ev, "power", ""))
    return p is not None and p.cls == "bard"


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
)
def i601x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i602x1",
    level=1,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i602x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


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
)
def i1045x1(c: Cast) -> None:
    """Necrotic resistance, walked through entirely -- no number printed,
    so no cap. Laid on the wielder, which is where an ignore lives."""
    c.ignore_resistance(
        None, DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER,
        when=_weapon_damage,
    )


@power(
    "i1057x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you take the total defence or second wind action",
    on=[Trigger(SecondWind, about_me, "you take your second wind"),
        Trigger(TotalDefence, about_me, "you take the total defence action")],
)
def i1057x1(c: Cast) -> None:
    """"All your defenses" is the four of them, and the card names the bonus
    an item bonus.

    Both printed actions, as two declared triggers -- `Power.on` takes a
    sequence. Total defence announces itself now, so the dropped half is
    written, and the two payouts are identical so the body need not ask
    which fired."""
    plus = c.enhancement
    for what in (AC, FORT, REF, WILL):
        c.bonus(what, plus, on=c.me, until=When.SONT, kind="item")


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
        "skill:intimidate", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
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
        "damage", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER,
        when=_bigger(c),
    )


@power(
    "i1490x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1490x1(c: Cast) -> None:
    """Both halves are readable and the marker was stale.

    A guardian form is a **stance** -- `powers/warden/__init__.assume`
    writes it, labelled with the form row's own ref -- and `EffectApplied`
    announces every effect that lands, its `label` included. So the form
    going on is an event, and "while you're in *that* form" is the stance
    object itself: the bonus is hung on its `on_end`, which is how the
    class's own rows bind a modifier to a form.

    `PowerUsed` is the wrong seam here even though a feat uses it: it
    fires **before** the body, so the stance is not up yet and there is
    nothing to hang the bonus on."""

    def took_form(ev: EffectApplied) -> None:
        if ev.target != c.me:
            return
        row = get(ev.label)
        if row is None or row.cls != "warden" or Keyword.POLYMORPH not in row.keywords:
            return
        # Found by **label**, not by `Effects.stance_of`: that one returns
        # the first stance it happens to find, and the form is only
        # reliably the only one because `c.stance` ends the previous
        # first. Hanging the bonus on the wrong stance is silent, and the
        # bonus then outlives the form it was printed for.
        form = next(
            (e for e in c.world.effects.of(c.me) if e.label == ev.label), None
        )
        which = c.choose([FORT, REF, WILL], "which defence the form guards")
        if form is None or which is None:
            return
        held = c.bonus(which, 2, on=c.me, until=When.ENCOUNTER)
        if held is not None:
            form.on_end.append(
                lambda: c.world.effects.end(held, "the form ended")
            )

    c.watch(EffectApplied, took_form, until=When.ENCOUNTER)


@power(
    "i1505x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1505x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


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
    todo=("Healed.power",),
)
def i1561x1(c: Cast) -> None:
    """Adds to the amount one **named** healing row restores.

    Re-aimed. The old marker said healing has no seam at all, which is no
    longer true: `resolve.heal` announces `Healed` *before* the hit points
    go on and reads `amount` back off the event, so a listener may raise
    it. What is missing is narrowing it to the row the card names --
    `Healed` carries `source`, `target`, `amount` and `hp` and nothing
    saying which power healed. Ungated this would fatten every heal the
    wielder ever gave, which is far more than the card grants."""


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
    dropped=("c.cover_from()",),
)
def i1580x1(c: Cast) -> None:
    """Damage to whichever creature was granting the target cover cannot
    be said: `query.cover_between` answers how much cover there is, never
    who is giving it."""
    c.as_implement(on=c.me)


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
)
def i1771p1(c: Cast) -> None:
    """The marker was stale: `c.expend_row` is the half that was missing.

    A use is spent and the row never runs, which is exactly the price this
    card charges. The pair it buys back is chosen before anything is paid
    -- `c.expend_row` returns False when there is no use to spend, and a
    trade with nothing on the other side is not one the card offers.

    "Of up to the same level" is read off the row that was burned. An
    *attack* power is one with a printed `Attack` line, which is the
    column; `Power.is_attack` is a different question -- it asks whether
    the row aims at anybody, and a utility that buffs an ally does."""
    known = c.world.get(c.me, Powers)
    if known is None:
        return

    def encounter_attacks(word: Keyword) -> list[str]:
        out = []
        for ref in known.all:
            p = get(ref)
            if (
                p is not None
                and p.usage is ENCOUNTER
                and p.attack is not None
                and word in p.keywords
            ):
                out.append(ref)
        return out

    spendable = [r for r in encounter_attacks(Keyword.ARCANE) if not known.times(r)]
    spent = [r for r in encounter_attacks(Keyword.MARTIAL) if known.times(r)]
    if not spendable or not spent:
        return
    paid = c.choose(spendable, "which arcane power is given up")
    if paid is None:
        return
    cap = get(paid).level
    back = [r for r in spent if (p := get(r)) is not None and p.level <= cap]
    if not back or not c.expend_row(paid):
        return
    chosen = c.choose(back, "which martial power comes back")
    if chosen is not None:
        c.restore_use(chosen)


@power(
    "i1793p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.regain_points()",),
)
def i1793p1(c: Cast) -> None:
    """A power point out of nowhere, held until the end of your next turn.

    Re-aimed on to the eleven-row group that names the same gap.
    `c.transfer_points` moves a point between creatures and
    `c.spend_points` spends one; nothing puts one into a pool, whether
    that is a point regained or -- as here -- one over the maximum. The
    "only to augment a psionic attack power" half rides on the same verb:
    a point nothing can create cannot be earmarked either."""


@power(
    "i2008x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2008x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i2008p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.cast_through()",),
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
)
def i2009x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i2010x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2010x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


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
        c.teleport(1 + c.enhancement, who=foe)


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
    c.initiative(c.enhancement, on=c.me)


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
        c.enhancement, on=c.me, until=When.ENCOUNTER,
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
    c.slide(c.enhancement, on=_struck(c))


@power(
    "i2926x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2926x1(c: Cast) -> None:
    """The reach *can* be widened, and the dropped marker was wrong.

    `dsl.area_of` stretches a melee range by `Mods.total("reach", ctx)`
    and hands the gate a context carrying the row being measured, so an
    ordinary `c.bonus("reach", ...)` narrowed to rows whose `Range.from_`
    is the companion says this and only this -- the wielder's own reach is
    untouched.

    A printed "Melee spirit" is reach 1, so "within 2 squares of your
    spirit" is +1. The card states a distance rather than an increase, so
    a hypothetical Melee spirit 2 row would come out at 3; there is no
    such row, and a bonus is the only shape the modifier has."""
    c.as_implement(on=c.me)
    c.bonus("reach", 1, on=c.me, until=When.ENCOUNTER, when=_melee_spirit)


@power(
    "i2927x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.origin_of()",),
)
def i2927x1(c: Cast) -> None:
    """Swapping which square a "melee spirit" power originates from cannot
    be said: `Range.from_` is a column on the power and no body moves
    it."""
    c.as_implement(on=c.me)


@power(
    "i3011x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3011x1(c: Cast) -> None:
    """Skill modifiers are read under `skill:<name>`, so the Stealth
    penalty is an ordinary one."""
    c.as_implement(on=c.me)
    plus = c.enhancement

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
    """The entry condition is back: the bus log is the tally.

    The clause was dropped as a fact about a creature the row does not
    name, and that is the wrong way round -- the row need not name the
    target, because `c.ignore_cover` takes a `when` and the attack
    context carries `target`. So the question is asked when the modifier
    is read, against whoever is actually being shot at, which is the
    moment the card means.

    `once=True` is "your next attack roll"; `c.ignore_cover` waives cover
    as well as concealment, which is wider than printed and the only
    shape the verb has."""
    me = c.me
    c.ignore_cover(
        on=me, until=When.EONT, once=True,
        when=lambda ctx: ctx.get("target") is not None
        and _hit_already(c.world, me, ctx["target"]),
    )


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
)
def i3069x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i3069p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you attack an enemy with a bard attack power using this weapon",
    on=Trigger(Hit, both(by_me, _bard_power), "you attack with a bard power"),
)
def i3069p1(c: Cast) -> None:
    """The class gate is back: `Hit` carries `power`.

    It was dropped as a question no predicate could ask, and the event has
    named the row that landed it all along -- `by_melee` and `by_keyword`
    read the same field. `Power.cls` is the column, so "a bard attack
    power" is one lookup.

    The bonus is aimed at one enemy, which the attack context carries as
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
    damage.

    The feature **is** modelled -- the old docstring said otherwise and
    was wrong. `powers/sorcerer/souls._chaos_burst` is the wild soul's
    half of `cf:sorcerer-f0`: it watches `AttackRolled` and, on an odd
    natural, calls `c.save(on=me)`.

    What is missing is declining it. `c.save` picks the first save-ends
    effect and rolls; `SavingThrow` is announced, but only in the `bare`
    branch and the caller ignores its `cancelled` either way, so an
    interrupt could not stop the throw and a free action certainly
    cannot. `c.unsave` fails a save that is happening, which spends the
    effect's chance rather than keeping it."""


@power(
    "i3103x1",
    level=2,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3103x1(c: Cast) -> None:
    """A critical takes the target's resistances away until it saves.

    The marker was stale twice over. `c.resistances` reads back what a
    creature shrugs off, by type -- its own docstring says it exists for
    "the target loses that resistance" -- and a **negative** amount to
    `c.resist` stays arithmetic rather than taking the highest, which is
    the subtraction. The hold puts back exactly what it took when the
    save lands.

    One call per type it actually has, because the delta differs per
    type; a blanket negative would drive every other type below zero and
    turn a resistance into a vulnerability."""

    def on_crit(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical:
            return
        for dtype, amount in c.resistances(on=ev.target).items():
            c.resist(-amount, dtype, on=ev.target, until=When.SAVE_ENDS)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i3103p1",
    level=2,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i3103p1(c: Cast) -> None:
    """Sorcerer powers ignore every resistance for the rest of the fight,
    within 10 squares. The distance is asked per blow rather than once,
    because the enemy moves."""

    def near_sorcery(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", ""))
        foe = ctx.get("target")
        return (
            p is not None and p.cls == "sorcerer"
            and foe is not None and c.distance(foe) <= 10
        )

    c.ignore_resistance(
        None, on=c.me, until=When.ENCOUNTER, when=near_sorcery
    )


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
    dropped=("c.weapon_range()",),
)
def i3156x1(c: Cast) -> None:
    """Waiving the long-range penalty is a verb, so that half is written;
    the +10 to long range is a column on the weapon."""
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
        "attack", 2, kind="item", on=c.me, until=When.ENCOUNTER,
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
    """Both halves land, and the gate `c.maximise` lacks is not needed.

    It was dropped because `c.maximise` takes no `when` and an ungated
    one maximises every swing. But `c.maximise` is already a **one-shot**
    -- it tops up the next roll and spends itself -- so arming it at the
    moment the swing is declared at an object is the same sentence with
    no gate at all. `AttackDeclared` carries `target` and is announced
    before the roll; "an object" is `c.scenery`, as it is one row up.

    `until=When.EOT` is the cleanup for a swing that misses and rolls no
    damage to top up."""

    def at_an_object(ev: AttackDeclared) -> None:
        if ev.attacker == c.me and ev.target in c.scenery():
            c.maximise(on=c.me, until=When.EOT)

    c.watch(AttackDeclared, at_an_object, until=When.ENCOUNTER, window=Window.BEFORE)
    c.bonus(
        "damage", 2, kind="item", on=c.me, until=When.ENCOUNTER,
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
    dropped=("c.flat(unpreventable=)",),
)
def i696p1(c: Cast) -> None:
    """The wielder pays the whole allowance rather than choosing a smaller
    one: the trade is always worth at least double. The self-damage is
    dealt flat and resistance still eats it, so a resistant wielder gets
    the payout cheap -- which is the clause that could not be written."""
    foe = _struck(c)
    if foe is None:
        return
    cost = c.enhancement
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
)
def i1120x1(c: Cast) -> None:
    """Rides on a class feature firing -- and the feature's own trigger is
    an event, so the row does not need the feature to announce itself.

    The marker was right that nothing says "a trait became true". It was
    wrong that this row needed one: the feature it names is the dragon
    soul's half of `cf:sorcerer-f0`, whose printed trigger is *the first
    time you are bloodied in an encounter*, and `Bloodied` names its
    subject `actor`. So the condition is "the wielder has that feature on
    that build" plus the same event, with the same once-a-fight latch the
    feature keeps -- kept here rather than `once=True` on the watch,
    because a bloodied ally is not this sentence.

    "Melee and close attacks" is read off the row's range line, the way
    `by_melee` reads it: the attack context's `ranged` is false for a
    close burst as well as for a swing, so it cannot tell the two
    from an area attack on its own."""
    me = c.me
    # `c.feat`, not `c.knows`: a feature is an ordinary row in
    # `Powers.known` and `c.feat` asks the caster's own list, where
    # `c.knows` answers with whoever on the board has it first -- an ally
    # sorcerer would have armed this dagger for a fighter.
    if not (c.build("dragon") and c.feat("cf:sorcerer-f0")):
        return
    done: list[bool] = []

    def in_reach(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power") or "")
        return p is not None and p.reach_of(ctx.get("branch", 0)).kind in (
            "melee", "close_burst", "close_blast",
        )

    def on_blood(ev: Bloodied) -> None:
        if ev.actor != me or done:
            return
        done.append(True)
        c.bonus("attack", 1, kind="item", on=me, until=When.EONT, when=in_reach)

    c.watch(Bloodied, on_blood, until=When.ENCOUNTER, on=me)


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
        "attack", 2, kind="item", on=c.me, until=When.ENCOUNTER,
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
    dropped=("c.retarget_defence()",),
)
def i1318p1(c: Cast) -> None:
    """Sending the attack at Fortitude instead of AC cannot be said -- the
    defence is read off the power's own `Attack` line before the roll. The
    extra damage lands: declared in the `BEFORE` window so the modifier is
    installed before the triggering attack rolls its damage, and
    `once=True` spends it there."""
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EOT, once=True)
