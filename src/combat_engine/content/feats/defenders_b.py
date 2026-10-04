"""Swordmage, monk, seeker and runepriest feats: the second batch.

Four short lists in one file because three of them are four or five rows
long. Two gaps run through the whole thing and neither is new:

* **The class feature that announces nothing.** The swordmage's aegis
  punishes an attacker from inside a `c.watch` callback, and the runepriest
  counts its own feats by a category the engine has no column for. A feat
  hanging off either has nothing to declare a trigger against. **The monk's
  is no longer one of them**: its feature is five declared rows, one per
  tradition, and `FLURRY` below names them -- so the monk feats here are
  held by what they do to that use, not by finding it.
* **The distance written into somebody else's body.** A teleport's range
  and the five squares `p9501` measures are constants inside those rows;
  nothing reaches in to add one.

What is new is that the swordmage's field is readable. `warding()` is
public for `p3369`'s sake and f1143 is the second row to want it, which is
why that feat is written rather than marked.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.defenders_sa import warding
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Bloodied,
    Cast,
    Condition,
    DamageType,
    Gear,
    Hit,
    Keyword,
    MoveEnd,
    PowerUsed,
    SecondWind,
    Trigger,
    When,
    about_me,
    power,
)
from combat_engine.engine.basic import RANGED
from combat_engine.engine.dsl import get
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.types import Usage

FEATURE = ("c.class_feature()",)
RUNE_FEATS = ("c.feats(category=)",)

#: The five the swordmage's own damage feat names. `Keyword.FORCE` is not
#: among them, which is the one worth saying out loud: the class's signature
#: damage type is not on the printed list.
_ELEMENTAL = (
    Keyword.ACID,
    Keyword.COLD,
    Keyword.FIRE,
    Keyword.LIGHTNING,
    Keyword.THUNDER,
)


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


# -- swordmage --------------------------------------------------------------


@power("f1129", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1449 and land beside an enemy",
       on=Trigger(PowerResolved, _used("p1449"), "you use that racial power"))
def f1129(c: Cast) -> None:
    """`PowerResolved` and not `PowerUsed`: the printed condition is about
    where the teleport *ended*, and `PowerUsed` is announced above the body
    that does the moving. Whoever is adjacent once the power has resolved
    is standing beside the destination the card asks about."""
    beside = [foe for foe in c.enemies() if c.adjacent(to=foe)]
    if beside:
        c.basic(on=beside[0])


@power("f1130", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1130(c: Cast) -> None:
    """The damage context carries the power's ref and nothing else about
    it, so both halves of "a swordmage power with one of these keywords"
    are read back off the header. The 11th- and 21st-level steps are
    paragon and epic and out of scope."""

    def elemental(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", ""))
        return (
            p is not None
            and p.cls == "swordmage"
            and any(k in p.keywords for k in _ELEMENTAL)
        )

    c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
            when=elemental)


def _ensnared(c: Cast, who: int) -> bool:
    """Is that creature under *this* swordmage's p5736 aegis?

    Marks are a relation, so `c.marked` cannot tell the three aegis rows
    apart -- and the feat is about one of them. The effect the mark rides
    on is labelled with the ref that laid it, which is the only thing on
    the board that distinguishes them; `_release` in that file reads the
    same label for the same reason.
    """
    return any(
        e.source == c.me and e.label.startswith("p5736")
        for e in c.world.effects.of(who)
    )


@power("f1141", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1141(c: Cast) -> None:
    """`MoveEnd` rather than `Moved`: `kind_` is a declared field there and
    a plain attribute on the other, and the slow wants the creature where
    it landed. Which power did the hauling is not on the event, so the
    aegis label stands in for it -- nothing else teleports a creature this
    swordmage has ensnared."""
    me = c.me

    def landed(ev: MoveEnd) -> None:
        if ev.kind_ != "teleport" or ev.actor == me or not _ensnared(c, ev.actor):
            return
        c.slowed(on=ev.actor, until=When.EONT)

    c.watch(MoveEnd, landed, on=me, until=When.ENCOUNTER)


#: The field's worth with the consciousness clause taken out -- 0, 1 or 3.
#: `warding` folds that clause in and returns 0 while unconscious, which is
#: exactly the sentence `f1142` deletes, so the two-line grip rule is
#: restated here rather than asked for. `f650b` and `i3036p1` restate it
#: too, for the same reason: it is a rule, not a stored number.
def _grip(world: Any, eid: int) -> int:
    gear = world.get(eid, Gear)
    if gear is None:
        return 0
    held = gear.held
    if not any(w.is_light_blade or w.group == "heavy blade" for w in held):
        return 0
    spare = len(held) == 1 and not held[0].two_handed and not gear.shield
    return 3 if spare else 1


@power("f1142", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1142(c: Cast) -> None:
    """Neither half needed what the marker named.

    The field is the grip rule and `_grip` is it; the feature's own two
    modifiers are gated on `warding`, which is 0 while unconscious, so
    the readings laid here cover exactly the span the feature drops and
    the two never both apply. `stacks=False` buckets them under this
    row's ref so +1 and +3 pick the larger rather than adding.

    "Add the bonus to the resistance" is the second half, and a gated
    `c.resist` is exactly an addition: given a `when=` it lays a modifier
    that `resolve.damage` reads on top of the flat number
    `rt:r35-astral-resistance` wrote, rather than competing with it. So
    the amount handed over is the field's own worth and the trait's
    number never has to be known -- and the two readings bucket under one
    kind, so +1 and +3 pick the larger here too.
    """
    me, world = c.me, c.world

    def wielded(size: int) -> Any:
        return lambda _ctx: _grip(world, me) >= size

    def out_cold(size: int) -> Any:
        return lambda _ctx: (
            c.is_(Condition.UNCONSCIOUS, on=me) and _grip(world, me) >= size
        )

    for size in (1, 3):
        c.bonus(AC, size, on=me, until=When.ENCOUNTER, stacks=False,
                when=out_cold(size))
        for dtype in (DamageType.NECROTIC, DamageType.RADIANT):
            c.resist(size, dtype, on=me, until=When.ENCOUNTER,
                     when=wielded(size))


@power("f1143", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1143(c: Cast) -> None:
    """An extra point on top of the field rather than a rewrite of it: the
    feature buckets its own two readings under its ref with `stacks=False`
    so the larger wins, and a third reading in the same bucket would be
    swallowed. Untyped, and gated on the field being up at all -- "the
    bonus increases" says nothing when there is no bonus."""
    me, world = c.me, c.world

    def lightly_armoured(_ctx: dict[str, Any]) -> bool:
        gear = world.get(me, Gear)
        return (
            gear is not None
            and gear.armour in ("cloth", "leather", "")
            and warding(world, me) > 0
        )

    c.bonus(AC, 1, on=me, until=When.ENCOUNTER, when=lightly_armoured)


@power("f1156", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_aegis()",))
def f1156(c: Cast) -> None:
    """A rider on "the immediate action effect" of the aegis.

    Re-aimed: the naming gap has closed -- the spec prints
    `cf:swordmage-f1` -- and it was never what stopped this. The three
    aegis rows `p3322`, `p5736` and `p3323` each roll their punishment
    inside a closure the minor-action body arms, so using the immediate
    action emits no `PowerUsed` and no `Hit` that can be told from the
    aegis row's own. There is nothing to hang this on until that answer
    announces itself."""


@power("f1234", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_reduce()",))
def f1234(c: Cast) -> None:
    """Hangs on p3323 softening a blow. `c.reduce` takes a number off a
    rolled `DamageRolled` and announces nothing, so "when you reduce
    damage" has no event -- and the creature it would pay out to is the
    one that was struck, which only that callback knows."""


def _left_me_out(c: Cast, ev: Any) -> bool:
    """A creature this swordmage has marked attacked, and left me out.

    `PowerUsed` rather than `AttackDeclared`, which is announced once per
    target: a burst that caught three allies would otherwise pay this feat
    three times for one attack. `p.attack` is what tells an attack from a
    minor-action buff; every monster row declares one.
    """
    p = get(ev.power)
    return (
        ev.actor != c.me
        and c.marked(on=ev.actor)
        and p is not None
        and p.attack is not None
        and c.me not in ev.targets
    )


@power("f2261", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2261(c: Cast) -> None:
    """Against **that** creature only. A plain "+1 bonus" with no type word
    printed in front of it, so no `kind=`."""

    def swung(ev: PowerUsed) -> None:
        if not _left_me_out(c, ev):
            return
        foe = ev.actor
        c.bonus("attack", 1, on=c.me, until=When.EONT,
                when=lambda ctx: ctx.get("target") == foe)

    c.watch(PowerUsed, swung, on=c.me, until=When.ENCOUNTER)


@power("f2262", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2262(c: Cast) -> None:
    """The same trigger as f2261 paying temporary hit points instead. The
    11th- and 21st-level steps are out of scope."""

    def swung(ev: PowerUsed) -> None:
        if _left_me_out(c, ev):
            c.temp_hp(3, on=c.me)

    c.watch(PowerUsed, swung, on=c.me, until=When.ENCOUNTER)


@power("f2263", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_move()",))
def f2263(c: Cast) -> None:
    """One more square on every swordmage teleport. The distance is an
    argument each row passes to `c.teleport` and nothing adds to it --
    the symbol the ranger's f786 and the avenger's f1527 both name."""


@power("f2264", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2264(c: Cast) -> None:
    """The marker this replaces said a surge consults no modifiers.
    `query.surge_value` totals `Mods` and exists precisely so that one
    `c.bonus("surge_value", n)` reaches every place a surge is cashed,
    the second wind and a natural twenty on a death save included.

    "While in a stance" is `Effects.stance_of`, whose label is the ref of
    the row that took it, so the class is read off that row's header. The
    question is asked per surge and not once: a stance is dropped by
    taking another, and the context a surge is totalled with is empty, so
    the gate goes to the board rather than to a key."""
    me, world = c.me, c.world

    def in_a_swordmage_stance(_ctx: dict[str, Any]) -> bool:
        held = world.effects.stance_of(me)
        if held is None:
            return False
        row = get(held.label)
        return row is not None and row.cls == "swordmage"

    c.bonus("surge_value", c.str_mod, on=me, until=When.ENCOUNTER,
            when=in_a_swordmage_stance)


#: The two arms the card names. The secondary end is the same weapon's
#: other blade and is held as a row of its own.
_RAISES_THE_FIELD = (
    "w3633",
    "w3668",
    "w3677",
)


@power("f2795", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w3633",))
def f2795(c: Cast) -> None:
    """Both arms are rows in the weapon table, so the grip test is real,
    and the benefit is written the way `f1143` writes its own: an extra
    untyped point on top of the field rather than an edit of the
    feature's `stacks=False` bucket, where a third reading would be
    swallowed. Gated on the field being up at all -- "increase the AC
    bonus" says nothing where there is no bonus -- and both of these are
    two-handed, so the reading being raised is the +1."""
    me, world = c.me, c.world

    def raised(_ctx: dict[str, Any]) -> bool:
        gear = world.get(me, Gear)
        return (
            gear is not None
            and any(w.ref in _RAISES_THE_FIELD for w in gear.held)
            and warding(world, me) > 0
        )

    c.bonus(AC, 1, on=me, until=When.ENCOUNTER, when=raised)


# -- monk -------------------------------------------------------------------
#
# **The feature these hang on is five rows and all five are written.** The
# class prints one card per tradition and a monk carries whichever its
# tradition dealt, so a row about "the feature" is declared against the
# set -- which is what `powers/monk/level_6_b.py` already does, and where
# this tuple comes from.

FLURRY = ("p7448", "p11207", "p13123", "p16131", "p16132")

_USED_FLURRY = "you use your class's level 0 feature row"


#: The racial free action `f3326` pairs the flurry with.
_FURIOUS = "p6189"


def _used_paired(world, me: int, ev: PowerUsed) -> bool:  # noqa: ANN001
    return ev.actor == me and (ev.power == _FURIOUS or ev.power in FLURRY)


def _used_my_flurry(world, me: int, ev: PowerUsed) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power in FLURRY


@power("f3171", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.forgo_damage()",))
def f3171(c: Cast) -> None:
    """The feature is `FLURRY` and no longer the hold, and stripping the
    target's necrotic resistance is writable now -- `c.resistances` reads
    what is standing and a negative `c.resist` takes it away. What is
    left is the trade the whole row is: "you can choose to forgo dealing
    damage", and a row cannot decline its own damage. Written without it
    the row is the payout with no price, which is a strictly better
    card than the one printed."""


@power("f3205", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger=_USED_FLURRY,
       on=Trigger(PowerUsed, _used_my_flurry, _USED_FLURRY))
def f3205(c: Cast) -> None:
    """`c.flat` and not a damage bonus: two points that arrive whatever
    the feature rolls, and a modifier on "damage" would also be picked up
    by every other attack in the turn.

    `PowerUsed` is announced before the body runs, and that is safe here
    -- targets are chosen first, so `ev.targets` is trustworthy, and
    nothing about the feature's own damage is read. At heroic the card
    has one target; "one of the power's targets" takes the first of
    however many there are.
    """
    aimed = [t for t in (getattr(c.trigger, "targets", ()) or ()) if t is not None]
    if aimed:
        c.flat(2, on=aimed[0])


def _my_daily_power(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.actor == me
        and p is not None
        and p.usage is Usage.DAILY
        and p.attack is not None
    )


@power("f3282", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an enemy with a daily attack power",
       on=Trigger(PowerResolved, _my_daily_power, "you use a daily attack"))
def f3282(c: Cast) -> None:
    """`PowerResolved` and not `Hit`, and the branch is the whole reason:
    "if the attack already slows the enemy" is only true once the power's
    own rider has landed, and a `Hit` reaction runs before the body that
    lays it. The resolved event also carries every roll the use made, so
    the creatures that were *hit* can be told from the ones aimed at."""
    for roll in getattr(c.trigger, "rolls", ()):
        foe = roll.target
        if not roll.hit or not foe:
            continue
        if c.is_(Condition.SLOWED, on=foe):
            c.slide(2, on=foe)
        else:
            c.condition(Condition.SLOWED, on=foe, until=When.SAVE_ENDS)


@power("f3287", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3287(c: Cast) -> None:
    """`query.speed` totals modifiers to "speed", so this is one line. The
    11th-level step is paragon."""
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f3293", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f3293(c: Cast) -> None:
    """Every damage roll: no weapon, keyword or reach narrowing is
    printed, so none is written."""
    c.bonus("damage", c.wis_mod, on=c.me, until=When.EONT)


@power("f3298", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3298(c: Cast) -> None:
    """"A weapon other than your monk unarmed strike" is readable: the
    chassis deals that one as `w:unarmed` with a group of its own, so the
    test is a held weapon that is neither it nor an implement. Asked per
    roll rather than once, because the grip changes mid-fight."""
    me, world = c.me, c.world

    def armed_and_unarmoured(_ctx: dict[str, Any]) -> bool:
        gear = world.get(me, Gear)
        if gear is None or gear.shield or gear.armour not in ("cloth", ""):
            return False
        return any(w.group not in ("unarmed", "implement") for w in gear.held)

    c.bonus(AC, 1, on=me, until=When.ENCOUNTER, when=armed_and_unarmoured)


@power("f3318", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_save()",))
def f3318(c: Cast) -> None:
    """Pays out on one particular saving throw succeeding. `SavingThrow`
    carries `against` as a free-text label and nothing sets it to the
    condition the throw is avoiding, so which save this is cannot be
    asked -- the gap the warden's f1024 names."""


@power("f3319", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.retarget()",))
def f3319(c: Cast) -> None:
    """Swaps one target of the feature for a distant one. The feature is
    `FLURRY` and the weapon half is readable; what is missing is taking a
    target off a use that has already chosen them -- `c.add_target` puts
    one on and there is no other half."""


@power("f3320", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.shift(through=)",))
def f3320(c: Cast) -> None:
    """A long shift passes through occupied squares. `share=True` puts a
    creature *into* one square rather than letting a path cross several,
    which is the same absence f3116 names."""


@power("f3326", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p6189 or your class's level 0 feature row",
       on=Trigger(PowerUsed, _used_paired, "you use one of the pair"))
def f3326(c: Cast) -> None:
    """Both halves have to fire off **one** hit, and the event says which
    hit each answered, so "the same hit" is an identity test.

    Declared on either of the pair rather than on one of them, because
    the order they answer a blow in is not fixed and only the second can
    see the first in the log. That is also what keeps it to one payout:
    exactly one of the two firings finds the other already there.
    """
    ev = c.trigger
    hit = getattr(ev, "trigger", None)
    if hit is None:
        return
    want = FLURRY if ev.power == _FURIOUS else (_FURIOUS,)
    other = next(
        (e for e in c.world.bus.log
         if isinstance(e, PowerUsed) and e.actor == c.me and e.power in want
         and getattr(e, "trigger", None) is hit),
        None,
    )
    if other is None:
        return
    flurry = ev if ev.power in FLURRY else other
    if flurry.targets:
        c.flat(c.str_mod, on=flurry.targets[0])


def _crit_unarmed(world: Any, me: int, ev: Any) -> bool:
    """A critical of mine with the chassis's own `w:unarmed`.

    `Hit.critical` is a field; the weapon comes off `Gear.main`, which is
    what the unarmed strike is held as when nothing else is.
    """
    from combat_engine.engine.components import Gear

    if ev.attacker != me or not ev.critical:
        return False
    gear = world.get(me, Gear)
    return gear is not None and gear.main is not None and gear.main.group == "unarmed"


@power("f3327", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with your monk unarmed strike",
       on=Trigger(Hit, _crit_unarmed, "a critical hit with an unarmed strike"))
def f3327(c: Cast) -> None:
    """The payout is the target's own resistance taken away rather than
    one attacker walking through it, which is what the card says: it
    loses it, for everybody, until the end of your next turn.
    `c.resistances` reads what is standing and a negative `c.resist` is
    the one arithmetic case left in it, so the hold puts back exactly
    what this took when it ends.

    AT_WILL because a triggered `action=NONE` row spends a use every
    firing and the card prints no limit."""
    foe = c.trigger.target
    for dtype, amount in c.resistances(on=foe).items():
        c.resist(-amount, dtype, on=foe, until=When.EONT)


@power("f3401", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.instead_of()",))
def f3401(c: Cast) -> None:
    """Trades the feature's normal effect for a penalty. The feature is
    `FLURRY` and the penalty is one line; what has no verb is the trade
    -- nothing suppresses the effect of a row that is being used, so
    writing the penalty alone would hand out both halves."""


# -- seeker -----------------------------------------------------------------


@power("f1816", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you are bloodied by an attack",
       on=Trigger(Bloodied, about_me, "you are bloodied"))
def f1816(c: Cast) -> None:
    """`Bloodied` names its subject `actor`, so `about_me` is right here
    where it is wrong on a condition. "By any attack" is not narrowed:
    the event is emitted from damage and carries no source, and a seeker
    bloodied by its own ongoing burn is the only false positive."""
    c.shift(1)


@power("f1817", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.reach_of(power=)",))
def f1817(c: Cast) -> None:
    """Widens the ring p9501 picks its second target out of. The five
    squares are a literal inside that row's body -- not header data a
    modifier could reach -- so nothing rewrites the distance one named
    row measures."""


#: The two rows the class-page bond hands over, one per leg. Named here
#: rather than guessed at because `controllers_sd` already pairs them with
#: `cf:seeker-f1`, and a seeker has used at most one of the two.
_BOND_ROWS = ("p9500", "p11462")


@power("f1818", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="the first time you are bloodied in an encounter",
       on=Trigger(Bloodied, about_me, "you are bloodied"))
def f1818(c: Cast) -> None:
    """"The first time" is the row's own `usage`: an encounter power with
    one use cannot answer the trigger twice, so no latch is needed.
    `c.restore_use` returns False when the row was not spent, which is the
    printed "if it is expended" -- so the pair is walked until one takes."""
    for ref in _BOND_ROWS:
        if c.restore_use(ref, on=c.me):
            return


@power("f2601", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p9501",
       on=Trigger(PowerUsed, _used("p9501"), "you use that power"))
def f2601(c: Cast) -> None:
    """`PowerUsed` is announced before the body runs, which is exactly
    what this needs: the modifier has to be standing before p9501 grants
    its swing. Gated on the granted row so it does not also cover the
    seeker's next attack this turn, and `partial=True` is the narrower
    line -- superior cover and total concealment still count."""
    c.ignore_cover(on=c.me, until=When.EOT, partial=True,
                   when=lambda ctx: ctx.get("power") == RANGED)


@power("f2619", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f2619(c: Cast) -> None:
    """"All defenses" is the four of them, and the card prints no type
    word in front of the bonus, so it is untyped."""
    mate = c.choose([a for a in c.allies() if c.adjacent(a)])
    if mate is None:
        return
    for what in (AC, FORT, REF, WILL):
        c.bonus(what, 2, on=mate, until=When.SONT)


# -- runepriest -------------------------------------------------------------


@power("f2613", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2613(c: Cast) -> None:
    """Two skill bonuses and nothing else. Deliberately inert rather than
    blocked on counting rune feats: the count would only ever size a
    number no fight reads."""


@power("f2614", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RUNE_FEATS)
def f2614(c: Cast) -> None:
    """p11353 is a ref and `PowerUsed` would carry its target, but the
    whole payout is the count: feats are ordinary rows in `Powers.known`
    and carry no category, so "how many rune feats" cannot be asked."""


@power("f2615", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RUNE_FEATS)
def f2615(c: Cast) -> None:
    """`Bloodied` is the trigger and it is writable; the size of the bonus
    is the same missing count as f2614."""


@power("f2616", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2616(c: Cast) -> None:
    """The other pair of skills, on the same terms as f2613."""
