"""Fighter feats, the third batch.

`fighter.py` and `fighter_b.py` hold the first two. This one finishes the
class, and it is three families again.

**The rest of the weapon-style pairs.** Ten more of the lesser/greater
rows `fighter_b.py` started, and the `Associated Powers:` lists resolve
to refs now, so `among`, `hit_with_one_of` and `used_one_of` from
`styles.py` say the clause outright. Every lesser one also prints a
skill bonus that is *not* gated on the weapon, so those rows are traits
with a `c.watch` for the triggered half rather than declared triggers --
a body under `on=Trigger(...)` never lays a standing modifier at all.
The greater ones mostly end in "in place of a melee basic attack",
which is still `c.as_basic(ref)`.

**The racial riders.** Eleven rows keyed to a race. Where the racial
power arrives as a ref -- `p2483`, `p2484` -- it is ordinary; where the
page names it in prose it is not ours to find, and `c.racial_row()`
with `c.expend_row()` is the pair of gaps.

**The mark.** Three rows change the number a marked creature pays for
leaving you out of its attack. `resolve._mark_penalty` returns a
hard-coded -2 and nothing reaches it, so the two that merely deepen the
penalty are written as a second, stacking modifier and name
`c.mark_penalty()` for the part that stacking cannot say; the one that
also wants a count taken afresh at each swing is refused outright.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    Gear,
    Hit,
    Keyword,
    Miss,
    Ranged,
    Trigger,
    When,
    power,
)
from combat_engine.engine.components import Position
from combat_engine.engine.dsl import get
from combat_engine.engine.events import Moved, PowerUsed
from combat_engine.engine.grid import distance, neighbours
from combat_engine.engine.query import enemies, has_combat_advantage

from .styles import among

#: Knowing which rows a feat names still does not let one stand in for a
#: basic attack. `f1239` named it; `fighter_b.py` carries nine more.
AS_BASIC = ("c.as_basic(ref)",)
#: A racial power the page names in prose rather than by ref, and the
#: paying half -- `c.expended` reads what has gone and nothing spends.
RACIAL = ("c.racial_row()", "c.expend_row()")
#: `resolve._mark_penalty` returns a hard-coded -2 and takes no modifier.
MARK_PENALTY = ("c.mark_penalty()",)

_STUNNING = ("dazed", "stunned")


# -- reading the grip -------------------------------------------------------
#
# The same two helpers `fighter_b.py` defines, repeated for the reason the
# files are separate at all, plus a third: half of this batch names a
# weapon rather than a group, and a weapon is its `ref`.


def _holding(c: Cast, *groups: str) -> bool:
    """Is the caster swinging one of these weapon groups?"""
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(w.group in groups for w in gear.melee)


def _grip(c: Cast, *groups: str, hands: int) -> bool:
    """One of those groups, held in that many hands."""
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(
        w.group in groups and w.two_handed == (hands == 2)
        for w in gear.melee
    )


def _named(c: Cast, *refs: str) -> bool:
    """One of these weapons by ref.

    "A longsword, a rapier, or a short sword" is not a group and not a
    property -- it is three rows of the weapon table -- so `c.wielding`,
    which asks the group, the category and the properties, cannot answer
    it. `Weapon.ref` can, and `chargen` spells them `w:<slug>`.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(w.ref in refs for w in gear.melee)


def _with_property(c: Cast, group: str, prop: str) -> bool:
    """A weapon of that group carrying that printed property."""
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(
        w.group == group and prop in w.properties for w in gear.melee
    )


def _one_hand_free(c: Cast) -> bool:
    """A weapon in one hand and nothing in the other.

    `Gear` has no hands, but it has everything a hand is made of: a
    shield or a second weapon fills the other one, and a two-handed
    weapon fills both. "Or grabbing a creature" needs no separate test --
    a grab occupies a hand that was already empty.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None or gear.shield or gear.two_weapon:
        return False
    main = gear.main
    return main is not None and not main.two_handed


def _beside_me(c: Cast, foe: int) -> Any:
    """A free square next to the caster that `foe` can reach in one step.

    "Slide that enemy 1 square to a square adjacent to you" names the
    destination, and a slide with no `to=` is the decider's free choice
    -- which duly slides things away. `c.slide` takes `to=`; this is
    what to hand it.
    """
    mine = c.world.get(c.me, Position)
    his = c.world.get(foe, Position)
    if mine is None or his is None:
        return None
    for sq in neighbours(mine.square):
        if (
            distance(sq, his.square) <= 1
            and c.world.grid.passable(sq)
            and c.world.grid.occupant(sq) is None
        ):
            return sq
    return None


# -- predicates -------------------------------------------------------------


def _i_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _i_hit_with_martial(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return ev.attacker == me and p is not None and Keyword.MARTIAL in p.keywords


def _i_hit_with_martial_encounter(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.usage is ENCOUNTER
        and Keyword.MARTIAL in p.keywords
    )


def _i_used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _i_used_a_fighter_row(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return ev.actor == me and p is not None and p.cls == "fighter"


def _missed_me_in_melee(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return ev.target == me and p is not None and p.reach.kind == "melee"


# -- the style pairs --------------------------------------------------------
#
# Each associated list is written out beside the row that uses it, as
# `styles.py` asks: two feats printed as a pair almost never share one.


@power("f2356", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2356(c: Cast) -> None:
    """The skill bonus is not gated on the weapon and the push is, so
    this is a trait with a watch rather than a declared trigger: a body
    under `on=` runs only when the trigger fires, and the skill bonus
    would never be laid at all."""
    me = c.me
    c.bonus("skill:intimidate", 2, kind="feat", on=me, until=When.ENCOUNTER)

    def on_hit(ev: Any) -> None:
        if (
            ev.attacker == me
            and ev.power in ("p992", "p1063")
            and _grip(c, "polearm", "spear", hands=2)
        ):
            c.push(1, on=ev.target)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f2358", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_BASIC,
       trigger="you hit an enemy with an attack power",
       on=Trigger(Hit, _i_hit, "you hit"))
def f2358(c: Cast) -> None:
    """Any attack power, not the associated ones -- the list belongs to
    the second benefit, which is the substitution and is dropped."""
    if _grip(c, "polearm", "spear", hands=2):
        c.bonus(AC, 1, kind="feat", on=c.me, until=When.EONT)


@power("f2359", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.retarget_defence()",))
def f2359(c: Cast) -> None:
    """The skill half plays. `p2104`, `p10733` and `p10593` may hit
    Reflex instead of AC, and the defence a row rolls against is header
    data -- the same gap `f2331` and four item blocks name."""
    c.bonus("skill:acrobatics", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f2360", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.extend_shift()",))
def f2360(c: Cast) -> None:
    """The damage half is a standing modifier with two named rows. The
    other clause lengthens a shift by 1, and nothing adds to one."""
    picked = among("p2109", "p1018")
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: picked(ctx) and _holding(c, "light blade"),
    )


@power("f2363", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2363(c: Cast) -> None:
    """A blanket -1 to the target's saving throws: the card narrows it to
    nothing, so no `when=` gate on the save's conditions."""
    me = c.me
    c.bonus("skill:intimidate", 2, kind="feat", on=me, until=When.ENCOUNTER)

    def on_hit(ev: Any) -> None:
        if (
            ev.attacker == me
            and ev.power in ("p2099", "p315")
            and _grip(c, "axe", "hammer", "pick", hands=2)
        ):
            c.penalty("save", 1, on=ev.target, until=When.EONT)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f2364", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.bonus(against=)", "c.as_basic(ref)"))
def f2364(c: Cast) -> None:
    """Both halves are gaps. The defence bonus is "against any attack
    that **would** immobilize, restrain or slow you", and the attack
    context carries the power's ref but nothing about what its body is
    going to apply -- a defence cannot be gated on an effect that has
    not happened. The other half is the associated substitution."""


@power("f2366", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.retarget_defence()",))
def f2366(c: Cast) -> None:
    """The skill half plays; `p4541`, `p2248`, `p10592` and `p10472` may
    hit Fortitude instead of AC, which is header data."""
    c.bonus("skill:endurance", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f2370", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Keyword.INVIGORATING",),
       trigger="you hit an enemy with a martial power",
       on=Trigger(Hit, _i_hit_with_martial, "you hit with a martial power"))
def f2370(c: Cast) -> None:
    """The saving throw's context carries the conditions the effect it is
    against holds, which is what makes "effects that daze or stun" a
    narrowing rather than a blanket penalty -- the same read `f364`
    makes. The keyword half is the gap four other fighter rows name."""
    if not _grip(c, "hammer", "flail", "mace", hands=1):
        return
    c.penalty(
        "save", 2, on=c.trigger.target, until=When.EONT,
        when=lambda ctx: any(
            str(x.value) in _STUNNING for x in ctx.get("conditions", ())
        ),
    )


@power("f2371", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bonus(compute=)",))
def f2371(c: Cast) -> None:
    """The skill half plays. The damage half is "+1 for each enemy
    adjacent to you", counted afresh at each swing, and a modifier
    carries a number decided when it is laid."""
    c.bonus("skill:endurance", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f2374", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_BASIC)
def f2374(c: Cast) -> None:
    """"They don't gain the +2 for having combat advantage" is the
    printed sentence `c.no_advantage` says, narrowed to the enemies
    standing next to you -- and its `when=` is handed the attacker,
    which is the creature the narrowing is about."""
    me = c.me
    if not _with_property(c, "heavy blade", "versatile"):
        return
    c.no_advantage(
        on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("attacker") is not None
            and c.adjacent_to(me, ctx["attacker"])
        ),
    )


@power("f2375", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2375(c: Cast) -> None:
    """"All defenses", so all four, and a penalty takes no `kind`."""
    me = c.me
    c.bonus("skill:intimidate", 2, kind="feat", on=me, until=When.ENCOUNTER)

    def on_hit(ev: Any) -> None:
        if (
            ev.attacker == me
            and ev.power in ("p4541", "p2620")
            and _grip(c, "hammer", "mace", hands=2)
        ):
            for defence in (AC, FORT, REF, WILL):
                c.penalty(defence, 1, on=ev.target, until=When.EONT)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f2376", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_BASIC)
def f2376(c: Cast) -> None:
    """"A critical hit on a roll of 19-20" is one off the crit floor, and
    `resolve.attack` reads `crit_range` off the attacker's modifiers with
    the attack context -- so the charge is an ordinary gate."""
    if not _grip(c, "hammer", "mace", hands=2):
        return
    c.bonus(
        "crit_range", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("charge", False),
    )


@power("f2379", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2379(c: Cast) -> None:
    """"When you **use** a power to attack an enemy granting combat
    advantage" -- so `PowerUsed`, which fires before the body and carries
    the targets it has already chosen, and the board is asked for the
    advantage while the grant is still standing."""
    me = c.me
    c.bonus("skill:acrobatics", 2, kind="feat", on=me, until=When.ENCOUNTER)
    blades = ("w:longsword", "w:rapier", "w:short-sword")

    def on_use(ev: Any) -> None:
        if ev.actor != me or ev.power not in ("p2105", "p653"):
            return
        if not _named(c, *blades):
            return
        if any(has_combat_advantage(c.world, me, t) for t in ev.targets):
            for defence in (AC, REF):
                c.bonus(defence, 1, on=me, until=When.SONT)

    c.watch(PowerUsed, on_use, on=me, until=When.ENCOUNTER)


@power("f2381", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_BASIC,
       trigger="you score a critical hit against an enemy",
       on=Trigger(Hit, _i_crit, "you crit"))
def f2381(c: Cast) -> None:
    """Every enemy beside the one you crit, and not that one: the card
    says "each enemy adjacent to that enemy"."""
    if not _named(c, "w:longsword", "w:rapier", "w:short-sword"):
        return
    foe = c.trigger.target
    for other in enemies(c.world, c.me):
        if other != foe and c.adjacent_to(foe, other):
            c.mark(on=other, until=When.EONT)


@power("f2382", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2382(c: Cast) -> None:
    """The destination is named, so the slide is given `to=`; a slide
    with a free choice of square drags enemies away from you, which is
    the opposite of what a flail is printed as doing."""
    me = c.me
    c.bonus("skill:intimidate", 2, kind="feat", on=me, until=When.ENCOUNTER)

    def on_hit(ev: Any) -> None:
        if (
            ev.attacker != me
            or ev.power not in ("p1505", "p997", "p1063")
            or not _holding(c, "flail")
        ):
            return
        square = _beside_me(c, ev.target)
        if square is not None:
            c.slide(1, on=ev.target, to=square)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f2383", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an enemy with a martial power",
       on=Trigger(Hit, _i_hit, "you hit"))
def f2383(c: Cast) -> None:
    """Two clauses off one hit, and they are gated differently -- the
    first on any martial power, the second on the two associated rows.

    The shift is watched on `Moved` rather than `MoveStart`, because the
    payment is for having shifted and `Moved` is the event that carries
    `kind_` *and* has happened. `once=True`: one payment, however often
    it moves.
    """
    if not _holding(c, "flail"):
        return
    foe = c.trigger.target
    p = get(c.trigger.power)
    hurt = c.dex_mod
    if p is not None and Keyword.MARTIAL in p.keywords:

        def on_move(ev: Any) -> None:
            if ev.actor == foe and getattr(ev, "kind_", "") == "shift":
                c.flat(hurt, on=foe)

        c.watch(Moved, on_move, on=foe, until=When.EONT, once=True)
    if c.trigger.power in ("p2176", "p1428"):
        c.slowed(on=foe, until=When.EONT)


# -- the grip, the shield and the grab --------------------------------------


@power("f2399", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2399(c: Cast) -> None:
    """A **shield** bonus without a shield, which is the printed type and
    therefore what it has to be -- it does not stack with a real one.
    Asked per attack rather than latched, because a hand that fills ends
    it the moment it matters."""
    me = c.me
    for defence in (AC, REF):
        c.bonus(
            defence, 1, kind="shield", on=me, until=When.ENCOUNTER,
            when=lambda ctx: _one_hand_free(c),
        )


@power("f2400", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_dice()",))
def f2400(c: Cast) -> None:
    """Raises the damage die of two weapons. `Weapon.damage` is the
    character's own string and nothing rewrites one for a fight."""


@power("f2427", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_grab_attack()",))
def f2427(c: Cast) -> None:
    """A critical hit with a grab attack. `c.grab` sets the relation and
    rolls nothing, so there is no roll to crit with -- the same gap a
    general feat wanting +4 to the grab's attack roll names."""


@power("f2432", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.escape()",))
def f2432(c: Cast) -> None:
    """Changes what an escape is rolled against. Escaping a grab is not
    modelled as a check at all, so there is nothing to redirect."""


@power("f2478", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_grab_attack()",))
def f2478(c: Cast) -> None:
    """Damage on a **missed** grab. Same gap as f2427 from the other
    side: nothing announces an attack as one that would have grabbed."""


# -- the mark ---------------------------------------------------------------


@power("f2411", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=MARK_PENALTY)
def f2411(c: Cast) -> None:
    """-3 for being marked instead of -2, written as the difference.

    `resolve._mark_penalty` charges the 2 already and returns a constant,
    so the extra 1 is laid beside it and the totals agree. What stacking
    cannot say is the word "instead": the engine waives its 2 when the
    attack catches you in it, and the context carries one target rather
    than the whole burst, so a burst that includes you still pays this 1
    on its other targets. Named rather than left in prose.
    """
    me = c.me
    if not (_named(c, "w:longsword") or _holding(c, "spear")):
        return
    for foe in enemies(c.world, me):
        c.penalty(
            "attack", 1, on=foe, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: (
                ctx.get("target") != me and c.marked(on=f, by=me)
            ),
        )


@power("f2440", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.bonus(compute=)", "c.mark_penalty()"))
def f2440(c: Cast) -> None:
    """"-2 or the number of enemies adjacent to you, whichever is worse",
    and both halves of that are gaps: the number is counted afresh at
    each swing where a modifier carries one decided when it is laid, and
    the penalty *replaces* the engine's constant 2 rather than adding
    to it."""


@power("f2412", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.no_provoke(when=)",))
def f2412(c: Cast) -> None:
    """Only the **first square** of the movement is free. `c.no_provoke`
    waives the whole move or none of it, and takes no gate -- waiving all
    of it would be a much larger feat than the one printed."""


@power("f2421", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2421(c: Cast) -> None:
    """High crit is an extra weapon die on a critical, and at heroic that
    is the whole of it -- `crit_damage` is the rolled modifier
    `resolve.deal_damage` reads in the crit branch, which is where a
    magic weapon's "+1d6 per plus" already lives.

    The mace is read once, when the trait arms; the mark is read per
    blow, because that is the half that changes.
    """
    me = c.me
    gear = c.world.get(me, Gear)
    mace = next((w for w in gear.melee if w.ref == "w:mace"), None) if gear else None
    if mace is None:
        return
    c.bonus(
        "crit_damage", 0, dice=mace.damage, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None and c.marked(on=ctx["target"], by=me)
        ),
    )


@power("f2470", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.telepathy()",))
def f2470(c: Cast) -> None:
    """Marks every enemy within the range of a racial telepathy. The
    crit and the mark are both ordinary; the radius is a racial trait
    the engine does not carry, and guessing a number would be a feat of
    whatever size I picked."""


@power("f2476", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit a creature with an opportunity attack",
       on=Trigger(Hit, _i_hit, "you hit"))
def f2476(c: Cast) -> None:
    """`getattr` on `opportunity`: `resolve.attack` sets it after the
    fact as a plain attribute rather than as a field of `Hit`."""
    if getattr(c.trigger, "opportunity", False):
        c.prone(on=c.trigger.target)


# -- the racial riders ------------------------------------------------------


@power("f2401", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f2401(c: Cast) -> None:
    """Spends a racial power to mark your neighbours instead. The mark is
    ordinary; the power is named in prose with no ref, and nothing
    expends a row on another row's say-so."""


@power("f2404", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.use_power()",))
def f2404(c: Cast) -> None:
    """Uses `p1831` as a free action after hitting a marked creature. The
    power is a ref and the trigger is ordinary -- what is missing is a
    row using another row, which eleven item blocks also want."""


@power("f2409", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.dragon_breath()",))
def f2409(c: Cast) -> None:
    """Extra damage on a racial breath against creatures marked by you.
    The breath is named in prose and has no ref to watch."""


@power("f2438", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2483",
       on=Trigger(PowerUsed, _i_used("p2483"), "you use p2483"))
def f2438(c: Cast) -> None:
    """"+4 instead of +2", written as the difference for the same reason
    `f2411` is: `p2483` lays its own +2 and this raises it against the
    creatures you marked. Both are untyped and untyped bonuses add, so
    the two come to the printed 4.

    "While you are under the effect of" is read as the encounter the
    power was used in -- `p2483`'s own line lasts until the end of it.
    """
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None and c.marked(on=ctx["target"], by=me)
        ),
    )


@power("f2448", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.on_miss_all()", "c.expend_row()"))
def f2448(c: Cast) -> None:
    """Spends `m4421a6` to reroll every attack roll of a power that
    missed everything. `Miss` is announced per target and says nothing
    about the others, and nothing spends a row to pay for a rider."""


@power("f2456", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=MARK_PENALTY,
       trigger="you use p2484",
       on=Trigger(PowerUsed, _i_used("p2484"), "you use p2484"))
def f2456(c: Cast) -> None:
    """The same stacking reading as `f2411`, and the same shortfall: the
    extra 1 is laid beside the engine's constant 2 rather than replacing
    it, so a burst that catches you still charges the other targets."""
    me = c.me
    for foe in enemies(c.world, me):
        c.penalty(
            "attack", 1, on=foe, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: (
                ctx.get("target") != me and c.marked(on=f, by=me)
            ),
        )


@power("f2472", level=1, cls="", usage=ENCOUNTER, action=ActionType.MINOR,
       reach=Ranged(10), target=ONE_CREATURE, todo=RACIAL)
def f2472(c: Cast) -> None:
    """A minor action rather than a trait, which is what the card prints.
    The mark and the range are ordinary; the cost is expending a cantrip
    a racial trait grants, and the trait is named in prose."""


@power("f2475", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.class_feature()",))
def f2475(c: Cast) -> None:
    """Widens which weapons a named class feature covers. Which weapons
    it covers is written into that feature's own body and nothing reads
    it back, let alone rewrites it."""


@power("f2791", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("query.power_moves()",),
       trigger="you use a fighter attack power",
       on=Trigger(PowerUsed, _i_used_a_fighter_row, "you use a fighter row"))
def f2791(c: Cast) -> None:
    """`PowerUsed` fires before the body, which is what makes this
    reachable at all -- the movement the card is about happens inside
    that body, so the waiver has to be standing before it runs.

    "A power that allows you to move" is the dropped half: nothing
    records which rows move their user, so this arms on every fighter
    attack power. It is wider than printed, and only while the turn
    lasts.
    """
    c.ignores_difficult(on=c.me, until=When.EOT)


# -- the last of the style pairs --------------------------------------------


@power("f2709", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_BASIC,
       trigger="an enemy misses you with a melee attack",
       on=Trigger(Miss, _missed_me_in_melee, "an enemy misses you in melee"))
def f2709(c: Cast) -> None:
    """The reaction half plays. "High crit" is a printed property and
    `Weapon.properties` is where the printed properties live, so the
    weapon question is the same read `versatile` gets."""
    if _with_property(c, "heavy blade", "high crit"):
        c.shift(1)


@power("f2714", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2714(c: Cast) -> None:
    """Both halves are standing, so this is a plain trait -- no watch."""
    me = c.me
    c.bonus("skill:athletics", 2, kind="feat", on=me, until=When.ENCOUNTER)
    picked = among("p992", "p1063")
    c.bonus(
        "crit_range", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: picked(ctx) and _grip(c, "heavy blade", hands=2),
    )


@power("f2715", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2715(c: Cast) -> None:
    """The greater feat of the pair prints only the one benefit, and it
    is the same one over a different list -- so it is a second
    `crit_range` modifier rather than a wider one. Untyped, and they add,
    which is the reading that makes the greater feat worth taking with
    the lesser."""
    picked = among("p1019", "p2106")
    c.bonus(
        "crit_range", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: picked(ctx) and _grip(c, "heavy blade", hands=2),
    )


@power("f2801", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2801(c: Cast) -> None:
    """"Hit **or** miss", so both events are watched; watching one of
    them would look finished and fire half as often."""
    me = c.me
    c.bonus("skill:acrobatics", 2, kind="feat", on=me, until=When.ENCOUNTER)
    blades = ("w:scimitar", "w:double-scimitar")

    def on_swing(ev: Any) -> None:
        if (
            ev.attacker == me
            and ev.power in ("p2104", "p10592")
            and _named(c, *blades)
        ):
            c.shift(1)

    c.watch(Hit, on_swing, on=me, until=When.ENCOUNTER)
    c.watch(Miss, on_swing, on=me, until=When.ENCOUNTER)


@power("f2802", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.forgo_push()",),
       trigger="you hit with a martial encounter attack power",
       on=Trigger(Hit, _i_hit_with_martial_encounter,
                  "you hit with a martial encounter power"))
def f2802(c: Cast) -> None:
    """Step away, then drag the target back to your side.

    The order is the printed one and it matters: the shift is taken
    first, so the square the slide aims at is read after it.

    Declared on `Hit` rather than on the end of the power, which nothing
    announces -- so a power that hits two creatures runs this twice
    where the card says "one target you hit". The dropped clause is the
    other benefit: turning a push the power grants into a slide.
    """
    if not _named(c, "w:scimitar", "w:double-scimitar"):
        return
    foe = c.trigger.target
    c.shift(2)
    square = _beside_me(c, foe)
    if square is not None:
        c.slide(2, on=foe, to=square)


# -- the shield ------------------------------------------------------------


@power("f2860", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("query.shield_bonus()",))
def f2860(c: Cast) -> None:
    """"Your shield bonus also applies to Will." The same gap `f1741`
    names for Fortitude: `Gear.shield` is a bool and the light-or-heavy
    number was folded into the defence totals at spawn, so the amount to
    apply again is not recoverable."""


@power("f2861", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an opportunity attack while using a shield",
       on=Trigger(Hit, _i_hit, "you hit"))
def f2861(c: Cast) -> None:
    """The shield is asked when the blow lands rather than when the trait
    arms, because a shield can be put down mid-fight and this is the
    moment it counts."""
    if getattr(c.trigger, "opportunity", False) and c.wielding("shield"):
        c.grants_advantage(on=c.trigger.target, until=When.EONT)


# -- the arena ---------------------------------------------------------------


@power("f3181", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.on_second_wind()", "c.chosen_weapon_group()"))
def f3181(c: Cast) -> None:
    """Two gaps. Second wind is an action rather than a power, so it
    announces nothing a trigger can answer; and "your arena weapons" is
    a set chosen at build time that nothing stores."""


@power("f3202", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.chosen_weapon_group()",))
def f3202(c: Cast) -> None:
    """Two weapons chosen at build time become proficient and join the
    same unstored set. Proficiency is a column on `Weapon` decided when
    the character is made, and the choice is not recorded anywhere."""
