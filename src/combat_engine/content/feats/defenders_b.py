"""Swordmage, monk, seeker and runepriest feats: the second batch.

Four short lists in one file because three of them are four or five rows
long. Two gaps run through the whole thing and neither is new:

* **The class feature that announces nothing.** The swordmage's aegis
  punishes an attacker from inside a `c.watch` callback, the monk's Flurry
  of Blows is named in prose with no ref, and the runepriest counts its own
  feats by a category the engine has no column for. A feat hanging off any
  of those has nothing to declare a trigger against.
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
    Gear,
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


@power("f1142", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.class_feature()", "chargen.race_choice()"))
def f1142(c: Cast) -> None:
    """Two clauses, two absences. `warding()` returns 0 while unconscious
    -- that is the printed default this feat lifts -- and it is computed
    inside the feature rather than laid as a modifier, so nothing reaches
    in to drop the clause. The resistance the second half adds to is a
    racial trait, and there is no race on a character to carry one."""


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
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f1156(c: Cast) -> None:
    """Pays out when the aegis punishment fires. All three aegis rows do
    that from inside a `c.watch` callback, which emits nothing a trigger
    can answer, and `cf:swordmage-f1` has no row of its own."""


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
       reach=PERSONAL, target=SELF, todo=("c.bonus(surge_value)",))
def f2264(c: Cast) -> None:
    """`c.surge_value` reads a quarter of maximum hit points straight off
    `Health` and consults no modifiers, so there is nowhere to add the
    ability modifier -- which makes the stance half moot as well."""


@power("f2795", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("chargen.FALCHION", "Weapon.double"))
def f2795(c: Cast) -> None:
    """The whole benefit is gated on two weapons the chassis does not
    deal. Written anyway, the grip test would be false in every fight and
    the row would look finished -- which is the failure this marker
    exists for. The double one also wants a property nothing models."""


# -- monk -------------------------------------------------------------------


@power("f3171", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.class_feature()", "c.forgo_damage()", "c.ignore_resistance()"))
def f3171(c: Cast) -> None:
    """Three absences in one sentence: the feature is named in prose, a
    row cannot decline its own damage, and stripping a creature's
    resistance is not a thing `c.resist` can be told to undo."""


@power("f3205", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3205(c: Cast) -> None:
    """Extra damage to one target of the class feature. Same gap as the
    four rows in `defenders.py`: the feature has no ref."""


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
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3319(c: Cast) -> None:
    """Swaps one target of the class feature for a distant one. The
    weapon half is readable; the feature it retargets is not."""


@power("f3320", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.shift(through=)",))
def f3320(c: Cast) -> None:
    """A long shift passes through occupied squares. `share=True` puts a
    creature *into* one square rather than letting a path cross several,
    which is the same absence f3116 names."""


@power("f3326", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3326(c: Cast) -> None:
    """Both halves have to fire off one hit. p6189 is a ref and could be
    watched; the class feature it has to coincide with is not."""


@power("f3327", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.ignore_resistance()",))
def f3327(c: Cast) -> None:
    """The trigger is writable -- `c.struck_with` hands back the weapon a
    `Hit` was made with, and the unarmed strike has its own group. What is
    missing is the payout: `c.resist` lays resistance and nothing takes a
    creature's own away."""


@power("f3401", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=FEATURE)
def f3401(c: Cast) -> None:
    """Trades the class feature's normal effect for a penalty. The
    penalty is one line; what it is traded against has no ref."""


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
#: `cf:seeker-bond`, and a seeker has used at most one of the two.
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
