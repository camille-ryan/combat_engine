"""Consumable items, heroic tier: potions, poisons, reagents, whetstones.

Nothing here declares an item. The level, the ladder and the price are
columns in `game.db`; what is written here is the part that needs a body,
and in this slot that is nearly all of it.

Seven judgements run through the file.

* **There is no consumption model.** Every row here is spent when it is
  used and nothing tracks that; `usage=DAILY` is the closest the engine
  comes. Only the rows whose printed text makes the spending a clause of
  its own -- "using this power turns it to dust" -- carry
  `dropped=("c.expend()",)`.
* **A coating cannot be tied to a weapon.** "Apply this to your weapon or
  one piece of ammunition; the next creature you hit with it..." has no
  way to ask which weapon a swing came from, so those rows fire on the
  wielder's next hit whatever it was made with and carry
  `dropped=("c.apply_poison()",)`.
* **Poison in a meal is refused outright**: "the first creature to consume
  the food or drink within the next hour" is not a moment a fight has.
  Those rows carry `todo=("c.apply_poison()",)` and never play.
* **A reagent is a declared trigger on `PowerUsed`.** "Expend this reagent
  when you use a power with the fire keyword of up to 5th level" is
  exactly that, and `_reagent` is the predicate. It excludes every item
  row -- a reagent modifies a class power -- which is also what keeps the
  row from answering its own use and going round for ever.
  `PowerUsed` fires *before* the body, so a reagent that pays out on a
  target **hit** watches `Hit` from inside the body rather than reading
  anything off the declaration; `ev.targets` is trustworthy there and is
  used where the printed line is about targets rather than hits.
* **A soulfang is a bargain**: a standing benefit and half a healing
  surge's worth of damage at the start of each of your turns. `_soulfang`
  is the price, and "damage caused by this soulfang cannot be reduced by
  any means" is `c.ignore_resistance` gated on this row -- read off the
  wearer, who is the source of their own bite. "Until you remove this
  soulfang" is written as the end of the encounter.
* **"Drink this and spend a healing surge"** is `c.spend_surge`, which
  spends one and pays out nothing -- which is the printed line. `c.surge`
  would heal as well and make every one of these potions strictly better
  than the rules say.
* **A rung of the ladder is a column.** A card printing level 5 and level
  10 is one row and the row writes the first rung. Paragon is out of
  scope outright.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    EACH_ENEMY,
    EACH_OTHER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionPointSpent,
    ActionType,
    AreaBurst,
    Attack,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageType,
    Event,
    Forced,
    ForcedMove,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    Moved,
    PowerResolved,
    PowerUsed,
    Ranged,
    SurgeSpent,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    World,
    ZoneEntered,
    about_me,
    get,
    power,
    targets_me,
)
from combat_engine.engine.grid import distance as squares_apart
from combat_engine.engine.grid import neighbours
from combat_engine.engine.query import allies, distance_between, squares

ITEM = "item"

#: "The damage type is determined when the item is made."
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.POISON,
    DamageType.PSYCHIC,
    DamageType.THUNDER,
)


#: What `i3576p1` leaves on its drinker for `i3576p2` to read back.
_CHARGED = "i3576 charged"

#: "Tied to a creature type of the creator's choice."
_SCROLL_KINDS = ("angel", "demon", "devil", "dragon", "elemental", "undead")


def _element(c: Cast, *among: DamageType) -> DamageType:
    """The damage type an item was made with.

    Fixed when the item was made and carried by no column, so it is asked
    of the decider each time the row runs rather than guessed at authoring
    time.
    """
    pool = list(among or _ELEMENTS)
    return c.choose(pool, "the item's damage type") or pool[0]


def _on_my_next_hit(c: Cast, fn: Callable[[Hit], None],
                    *, until: When = When.ENCOUNTER) -> None:
    """"The next creature you hit."

    The flag is kept here rather than passed to `c.watch(once=True)`
    because the hold has to go on the hit that *counts*, and a guard that
    returns without announcing anything is indistinguishable from one that
    did nothing at all -- which is how `c.watch` decides whether a
    once-only trigger was spent.
    """
    spent: list[bool] = []

    def seen(ev: Hit) -> None:
        if spent or ev.attacker != c.me:
            return
        spent.append(True)
        fn(ev)

    c.watch(Hit, seen, until=until)


def _on_each_hit(c: Cast, fn: Callable[[Hit], None]) -> None:
    """"Whenever you hit a creature", for the rest of the fight."""

    def seen(ev: Hit) -> None:
        if ev.attacker == c.me:
            fn(ev)

    c.watch(Hit, seen, until=When.ENCOUNTER)


def _soulfang(c: Cast) -> None:
    """The price every soulfang prints: half a healing surge's worth of
    damage at the start of each of your turns, for as long as it is in.

    "Damage caused by this soulfang cannot be reduced by any means" is
    read off the **source** of the blow, which is the wearer, so
    `c.ignore_resistance` is the verb and the gate is what keeps it from
    stripping the wearer's resistances against everything else: it fires
    only for damage whose context names this row.
    """
    c.ignore_resistance(
        on=c.me, until=When.ENCOUNTER, when=_is_row(c.ref),
        immunity=True, insubstantial=True,
    )

    def bite(ev: TurnStart) -> None:
        if ev.actor == c.me:
            c.flat(max(1, c.surge_value() // 2), on=c.me)

    c.watch(TurnStart, bite, until=When.ENCOUNTER)


def _ends_when_you_attack(c: Cast, effect: Any, who: int) -> None:
    """"...or until you attack."

    `AttackRolled` rather than `AttackDeclared`: the printed line is bought
    so that the attack itself is made from behind the effect, and the hold
    comes off once the die is down. The flag is kept here for the reason
    `_on_my_next_hit` keeps one.
    """
    if effect is None:
        return
    spent: list[bool] = []

    def swung(ev: AttackRolled) -> None:
        if spent or ev.attacker != who:
            return
        spent.append(True)
        c.end_effect(effect)

    c.watch(AttackRolled, swung, until=When.ENCOUNTER)


def _is_row(ref: str) -> Callable[[dict[str, Any]], bool]:
    """Gate a modifier on which row is in the context."""

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("power") == ref

    return gate


def _keyword_gate(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    """Gate a modifier on the keywords of the power in the context."""

    def gate(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return row is not None and any(w in row.keywords for w in words)

    return gate


def _weapon_attack(ctx: dict[str, Any]) -> bool:
    row = get(ctx.get("power") or "")
    return row is not None and Keyword.WEAPON in row.keywords


def _reagent(cap: int, *words: Keyword) -> Callable[[World, int, Event], bool]:
    """"When you use a <keyword> power of up to Nth level."

    Declared on `PowerUsed`, which is announced before the body runs. Item
    rows are excluded: a reagent is spent on a class power, and without
    that clause the row would answer its own use and go round for ever.
    """

    def gate(world: World, me: int, ev: Event) -> bool:
        if getattr(ev, "actor", None) != me:
            return False
        row = get(getattr(ev, "power", ""))
        if row is None or row.cls == ITEM or row.level > cap:
            return False
        return not words or any(w in row.keywords for w in words)

    return gate


def _reagent_targets(c: Cast) -> list[int]:
    """The targets of the power the reagent was spent on.

    Chosen before the body runs, so this is the one thing a `PowerUsed`
    watcher may trust.
    """
    return list(getattr(c.trigger, "targets", ()) or ())


# -- level 1 ----------------------------------------------------------------


@power("i1483p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON])
def i1483p1(c: Cast) -> None:
    """The card offers a melee weapon or a piece of ammunition; the row
    coats the weapon, which is one of the two printed answers."""

    def coated(ev: Hit) -> None:
        c.flat(10, dtype=DamageType.POISON, on=ev.target)
        c.no_healing(on=ev.target, until=When.SAVE_ENDS)

    c.apply_poison(coated)


@power("i1483p2", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       out_of_combat=True)
def i1483p2(c: Cast) -> None:
    """Poison in a meal, paid out an hour later and for a rest.
    Deliberately inert: no clause of it lands inside a fight."""


@power("i1595p1", level=1, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       keywords=[Keyword.IMPLEMENT, Keyword.POISON],
       attack=Attack(DEX, vs=REF))
def i1595p1(c: Cast) -> None:
    """"Each Failed Saving Throw" is `escalate`, which `durations` runs on
    a failed save and on nothing else -- so the burn hangs on
    `c.condition`, which takes the hook, rather than on `c.ongoing`, which
    does not. The insanity clause is the DM's.

    `c.within(side="ally")` is the wrong tool for "its nearest ally": the
    pool is read off the caster whatever `of=` says, so the victim's own
    side is asked for directly."""
    if c.strike():
        c.damage("2d10", c.dex_mod, dtype=DamageType.POISON)
    else:
        c.half_damage("2d10", c.dex_mod, dtype=DamageType.POISON)

    def turns_on_a_friend(eff: Any) -> None:
        victim = eff.owner
        friends = allies(c.world, victim)
        if friends:
            c.basic(who=victim, on=min(
                friends, key=lambda a: distance_between(c.world, victim, a)
            ))

    c.condition(ongoing=(5, DamageType.PSYCHIC), until=When.SAVE_ENDS,
                escalate=turns_on_a_friend)


@power("i1595p2", level=1, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1595p2(c: Cast) -> None:
    """A trapped container, sprung within the hour. Deliberately inert:
    a board has no containers and no hour."""


@power("i1919p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON])
def i1919p1(c: Cast) -> None:
    """Five pieces of ammunition is every hit for the fight, not one, so
    the coating is `once=False`. "First Failed Saving Throw: ongoing 5
    instead" is `escalate`, which `c.condition` takes and `c.ongoing` does
    not; set rather than added, so a second failed save changes nothing,
    which is what "first" means."""

    def coated(ev: Hit) -> None:
        def worsens(eff: Any) -> None:
            eff.ongoing = (5, DamageType.POISON)

        c.condition(ongoing=(2, DamageType.POISON), until=When.SAVE_ENDS,
                    on=ev.target, escalate=worsens)

    c.apply_poison(coated, once=False)


@power("i1919p2", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       out_of_combat=True)
def i1919p2(c: Cast) -> None:
    """A poisoned doorhandle, on an hour's clock and paying out until an
    extended rest. Deliberately inert."""


@power("i2955p1", level=1, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       keywords=[Keyword.ACID, Keyword.IMPLEMENT, Keyword.POISON],
       attack=Attack(DEX, vs=REF))
def i2955p1(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.dex_mod, dtype=DamageType.POISON)
    else:
        c.half_damage("3d8", c.dex_mod, dtype=DamageType.POISON)
    c.ongoing(5, DamageType.ACID)


@power("i2955p2", level=1, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2955p2(c: Cast) -> None:
    """A trapped container, sprung within the hour. Deliberately inert:
    a board has no containers and no hour."""


@power("i3288p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i3288p1(c: Cast) -> None:
    """"If you are bloodied and have no surges you still regain the hit
    points" -- so the surge is spent when there is one and the healing
    happens whenever either half is true."""
    if c.spend_surge(on=c.me) or c.bloodied(on=c.me):
        c.heal(c.roll("1d8") + 1, on=c.me)


@power("i710p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON])
def i710p1(c: Cast) -> None:

    def coated(ev: Hit) -> None:
        c.flat(6, dtype=DamageType.POISON, on=ev.target)
        c.dazed(on=ev.target, until=When.SAVE_ENDS)

    c.apply_poison(coated)


@power("i710p2", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       out_of_combat=True)
def i710p2(c: Cast) -> None:
    """Poison in a meal, paying out until an extended rest.
    Deliberately inert."""


@power("i835p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON])
def i835p1(c: Cast) -> None:
    """Five pieces of ammunition is every hit for the fight, so the
    coating is `once=False`."""

    def coated(ev: Hit) -> None:
        c.flat(4, dtype=DamageType.POISON, on=ev.target)
        c.slowed(on=ev.target, until=When.EONT)

    c.apply_poison(coated, once=False)


@power("i835p2", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       out_of_combat=True)
def i835p2(c: Cast) -> None:
    """A poisoned handheld object, on an hour's clock and paying out
    until an extended rest. Deliberately inert."""


# -- level 2 ----------------------------------------------------------------


@power("i2069p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2069p1(c: Cast) -> None:
    """A guise and a Bluff bonus for an hour."""


@power("i2356p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       )
def i2356p1(c: Cast) -> None:
    """Both powers the card names have refs now, so the whole benefit
    attaches. It used to be half a row: `p5389` resolved and the second was
    prose, so a character holding only that one paid for the soulfang and
    got nothing."""
    rows = ("p5389", "p5388")
    for what in ("attack", "damage"):
        c.bonus(what, 2, on=c.me, until=When.ENCOUNTER, kind="power",
                when=lambda ctx: ctx.get("power") in rows)
    _soulfang(c)


@power("i2749p1", level=2, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you roll for initiative",
       on=Trigger(InitiativeRolled, about_me, "you roll for initiative"))
def i2749p1(c: Cast) -> None:
    c.initiative(2, on=c.me)


@power("i2749p2", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2749p2(c: Cast) -> None:
    """"This power is lost when you use the consumable power" is written
    from this side: `c.forbid` takes the other row away."""
    c.bonus(AC, 3, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("opportunity")))
    c.bonus("speed", 3, on=c.me, kind="item", until=When.ENCOUNTER)
    c.forbid("i2749p1", on=c.me, until=When.ENCOUNTER)


@power("i3298x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3298x1(c: Cast) -> None:
    """A fire that burns for eight hours on its own fuel."""


# -- level 3 ----------------------------------------------------------------


@power("i1420p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       dropped=("Healed.power",))
def i1420p1(c: Cast) -> None:
    """"When one of your primal healing powers heals an ally" needs the
    power off the `Healed`, which does not carry one."""
    _soulfang(c)


@power("i2561p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       dropped=("c.in_form()",))
def i2561p1(c: Cast) -> None:
    """Nothing asks which shape a creature is in -- `c.form` labels its
    hold with the ref that laid it and no two druid rows agree on a word
    -- so the +1 has no gate to hang on and is left off rather than
    applied to everything."""
    _soulfang(c)


@power("i2685x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2685x1(c: Cast) -> None:
    """A day's food that weighs a tenth of a pound."""


@power("i2685p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i2685p1(c: Cast) -> None:
    """`SurgeSpent` is announced after the surge has paid out, so the
    extra hit point is healed on top of it."""
    c.bonus("skill:endurance", 1, on=c.me, kind="power", until=When.ENCOUNTER)
    spent: list[bool] = []

    def seen(ev: SurgeSpent) -> None:
        if spent or ev.actor != c.me:
            return
        spent.append(True)
        c.heal(1, on=c.me)

    c.watch(SurgeSpent, seen, until=When.ENCOUNTER)


@power("i2815p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2815p1(c: Cast) -> None:
    """Untyped: the card prints a bare "+1 bonus". `"skill"` is the key
    for a bonus to whichever skill the character chose."""
    c.bonus("skill", 1, on=c.me, until=When.ENCOUNTER)


@power("i2868p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2868p1(c: Cast) -> None:
    """`p5094` is a ref now. `ForcedMove` is where a slide is announced
    and it is the only event carrying the ref of the row doing the
    shoving -- `Moved` knows the kind but not what caused it."""
    me = c.me

    def bites(ev: ForcedMove) -> None:
        if ev.source == me and ev.power == "p5094" and ev.how is Forced.SLIDE:
            c.flat(5, on=ev.target)

    c.watch(ForcedMove, bites, until=When.ENCOUNTER)
    _soulfang(c)


@power("i3512p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3512p1(c: Cast) -> None:
    """Five minutes of talking to fey beasts."""


@power("i3531p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=AreaBurst(1, 5), target=NO_TARGET, keywords=[Keyword.ZONE])
def i3531p1(c: Cast) -> None:
    """"Enters or starts its turn there" is two announcements, and a zone
    makes only the first -- so the turn half is watched separately."""
    zone = c.zone(c.area(), until=When.ENCOUNTER)
    squares = frozenset(c.area())

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            c.slowed(on=ev.actor, until=When.SAVE_ENDS)

    def began(ev: TurnStart) -> None:
        if ev.actor in c.in_squares(squares):
            c.slowed(on=ev.actor, until=When.SAVE_ENDS)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER)
    c.watch(TurnStart, began, until=When.ENCOUNTER)


# -- level 4 ----------------------------------------------------------------


@power("i1726x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1726x1(c: Cast) -> None:
    """A corpse that will not rot and cannot be raised."""


@power("i1901p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET, out_of_combat=True)
def i1901p1(c: Cast) -> None:
    """A door sealed as though by a ritual."""


@power("i2078p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2078p1(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.resist(5, _element(c), on=c.me, until=When.ENCOUNTER)


@power("i2083p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2083p1(c: Cast) -> None:
    """Walking on water, which the board has no water to walk on."""


@power("i2536p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2536p1(c: Cast) -> None:
    """A gem that tells you a history."""


@power("i2753p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF)
def i2753p1(c: Cast) -> None:
    c.no_advantage(on=c.me, until=When.ENCOUNTER)
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("opportunity")))


@power("i930p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you miss all targets with an augmented psionic power",
       todo=("Miss.all_targets", "c.regain_points()"))
def i930p1(c: Cast) -> None:
    """Neither half is sayable: a `Miss` names one target and does not
    know whether the others were missed too, and nothing hands a power
    point back."""


# -- level 5 ----------------------------------------------------------------


@power("i1187p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1187p1(c: Cast) -> None:
    c.bonus("skill", 1, on=c.me, kind="power", until=When.ENCOUNTER)


@power("i1469p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1469p1(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.resist(5, DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER)
    c.resist(5, DamageType.POISON, on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:endurance", 5, on=c.me, kind="power",
            until=When.ENCOUNTER, once=True)


@power("i1658p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1658p1(c: Cast) -> None:
    c.resist(3, on=c.me, until=When.ENCOUNTER)
    _soulfang(c)


@power("i2068p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.reroll_attack(ev=)",))
def i2068p1(c: Cast) -> None:
    """A reroll banked for later: `c.reroll_attack` rolls the attack being
    answered, and a one-shot spent out of turn is answering nothing."""


@power("i2070p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       dropped=("c.ignores_difficult(when=)",))
def i2070p1(c: Cast) -> None:
    """"When you shift" is the missing gate; rough ground is ignored on
    every kind of move instead, which is more than the card gives."""
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power("i2071p1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2071p1(c: Cast) -> None:
    """An attitude and an Insight penalty, for an hour."""


@power("i2072p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i2072p1(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.heal(10, on=c.me)


@power("i2079p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2079p1(c: Cast) -> None:
    """A death save *is* reachable: `turns._death_saves` reads the `save`
    modifier with `label="death"` in the context, which is the gate that
    keeps this off every other saving throw. "You do not regain hit points
    as normal" is `c.spend_surge`, which pays out nothing."""
    c.spend_surge(on=c.me)
    c.bonus("save", 1, on=c.me, kind="power", until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("label") == "death")


@power("i2563p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2563p1(c: Cast) -> None:
    c.resist(10, _element(c), on=c.me, until=When.ENCOUNTER)
    _soulfang(c)


@power("i2564p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2564p1(c: Cast) -> None:

    def struck(ev: Hit) -> None:
        if ev.target == c.me and ev.attacker != c.me:
            c.flat(4, dtype=DamageType.NECROTIC, on=ev.attacker)

    c.watch(Hit, struck, until=When.ENCOUNTER)
    _soulfang(c)


@power("i2698p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2698p1(c: Cast) -> None:
    """The extra point is lightning and carries that type, so it meets a
    lightning resistance the weapon's own damage does not."""
    c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, when=_weapon_attack,
            dtype=DamageType.LIGHTNING)
    _soulfang(c)


@power("i3274p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION],
       out_of_combat=True)
def i3274p1(c: Cast) -> None:
    """Seeing from somewhere else. Sight is not measured from a square a
    creature is not standing in."""


@power("i3282p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("c.alignment()",))
def i3282p1(c: Cast) -> None:
    """Nothing records an alignment, so "against evil creatures" has no
    gate and the bonuses apply to everything."""
    c.bonus("damage", 1, on=c.me, kind="power", until=When.EONT)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 1, on=c.me, kind="power", until=When.EONT)


@power("i3283p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3283p1(c: Cast) -> None:
    """A sense of where the treasure is."""


@power("i3305p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(2), target=NO_TARGET,
       dropped=("c.no_enter(zone)",))
def i3305p1(c: Cast) -> None:
    """The creature type is fixed when the scroll is made and carried by
    no column, so it is asked of the decider the way `_element` asks for a
    damage type.

    The -4 is not `c.grants_in`: that one is about who is standing inside,
    and this penalty rides the *attacker* wherever it is, gated on where
    its target is. The attack context carries `target`, so the gate reads
    the aura's occupants each time rather than a list frozen now. A
    creature that joins the fight later is missed, which is the honest
    limit of laying a modifier per enemy.

    Dropped: nothing bars a creature from walking into a zone, so "it
    cannot enter the aura willingly, and must use its first action to
    leave by the shortest route" has nowhere to go."""
    from combat_engine.engine.components import Stats

    kind = c.choose(list(_SCROLL_KINDS), "the scroll's creature type")
    aura = c.aura(2, on=c.me, until=When.ENCOUNTER)
    spent: list[bool] = []

    def in_the_aura(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") in c.world.zones.occupants(aura)

    for foe in c.enemies():
        stats = c.world.get(foe, Stats)
        if not c.is_kind(kind or "", on=foe) or (stats and stats.level > 5):
            continue
        c.penalty("attack", 4, on=foe, until=When.ENCOUNTER, when=in_the_aura)

    def swung(ev: AttackRolled) -> None:
        if spent or ev.attacker != c.me:
            return
        spent.append(True)
        c.dispel(aura)

    c.watch(AttackRolled, swung, until=When.ENCOUNTER)


@power("i3307x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3307x1(c: Cast) -> None:
    """Ink only its reader can see."""


@power("i3308p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(1), target=NO_TARGET, keywords=[Keyword.ZONE])
def i3308p1(c: Cast) -> None:
    """"Totally obscured" is the one obscurity the engine has a word
    for."""
    c.zone(c.area(), blocks_sight=True, until=When.EONT)


@power("i3392p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3392p1(c: Cast) -> None:
    """"Toward the nearest enemy" is the neighbouring square that shortens
    the gap most, handed to `c.shift(to=)`. A shift the board refuses --
    rough ground, an occupied square -- falls back to letting the decider
    place it, which is what the row did before it could aim."""
    c.spend_surge(on=c.me)
    c.temp_hp(10, on=c.me)
    foes = c.enemies()
    if not foes:
        c.shift(1)
        return
    nearest = min(foes, key=c.distance)
    theirs = squares(c.world, nearest)
    here = sorted(squares(c.world, c.me))[0]
    step = min(
        neighbours(here),
        key=lambda s: min(squares_apart(s, t) for t in theirs),
    )
    if not c.shift(1, to=step):
        c.shift(1)


@power("i3468x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3468x1(c: Cast) -> None:
    """A coin that always lands the same way up."""


@power("i3468p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.boost_roll()",))
def i3468p1(c: Cast) -> None:
    """"A roll you just made" covers an attack, a check and a save alike,
    and only the skill check has a way in -- `c.boost_check`. One third of
    a printed line is not the line."""


@power("i3548p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3548p1(c: Cast) -> None:
    """Insubstantial halves what you take. The printed drawback -- your own
    attacks deal half damage too -- is `Condition.WEAKENED`: its whole rule
    is `weakened=True`, which `resolve.deal_damage` reads to halve what the
    creature deals, so the condition is the clause rather than a name for
    something else.

    "Except those that deal force or psychic damage" is said of both halves
    and is carried by neither: `Rules.insubstantial` and `Rules.weakened`
    are both flat, so the exception is out at the same fidelity on the way
    in as on the way out."""
    c.insubstantial(on=c.me, until=When.EONT)
    c.phasing(on=c.me, until=When.EONT)
    c.weakened(on=c.me, until=When.EONT)


@power("i3576p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF)
def i3576p1(c: Cast) -> None:
    """Where the surge goes is a charge on the item, and nothing holds
    state on an item -- but the twelve hours are longer than any fight, so
    inside one the charge is a named hold on the drinker and `i3576p2`
    reads it back. Nothing is charged if there was no surge to lose."""
    if c.spend_surge(on=c.me):
        c.effect(_CHARGED, on=c.me, until=When.ENCOUNTER)


@power("i3576p2", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i3576p2(c: Cast) -> None:
    """Charged, the surge pays out as normal *and* the dice on top, and
    the charge goes. Uncharged, the surge is lost for the dice alone,
    which is `c.spend_surge` rather than `c.surge`."""
    if c.me in c.suffering(_CHARGED, include_self=True):
        c.end_effect(on=c.me, against=_CHARGED)
        c.surge(on=c.me)
    else:
        c.spend_surge(on=c.me)
    c.heal(c.roll("2d8"), on=c.me)


@power("i992p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i992p1(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.resist(5, DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER)
    c.resist(5, DamageType.POISON, on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:endurance", 5, on=c.me, kind="power",
            until=When.ENCOUNTER, once=True)


# -- level 6 ----------------------------------------------------------------


@power("i1191p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION])
def i1191p1(c: Cast) -> None:
    """"Or until you attack" is not a `When`, so it is the hold ended by
    hand on the first attack roll the drinker makes. Level 16 is paragon
    and out of scope."""
    _ends_when_you_attack(c, c.invisible(on=c.me, until=When.EONT), c.me)


@power("i1285p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1285p1(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.temp_hp(5, on=c.me)
    c.resist(5, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)


@power("i1910p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use an encounter or daily attack power of 5th level "
               "or lower that has a damage keyword",
       on=Trigger(PowerUsed, _reagent(5),
                  "you use a low-level attack power"))
def i1910p1(c: Cast) -> None:
    """The payout is on a target **hit**, which the declaration does not
    know yet -- `PowerUsed` is announced above the body -- so the hit is
    watched for instead."""

    def landed(ev: Hit) -> None:
        c.no_healing(on=ev.target, until=When.ENCOUNTER)

    _on_my_next_hit(c, landed, until=When.EOT)


@power("i2697p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a lightning or thunder power of 5th level or "
               "lower and damage a target",
       on=Trigger(PowerUsed, _reagent(5, Keyword.LIGHTNING, Keyword.THUNDER),
                  "you use a lightning or thunder power"))
def i2697p1(c: Cast) -> None:
    """"If the target cannot be pushed, it falls prone" is what `c.push`
    returning nothing means."""

    def landed(ev: Hit) -> None:
        if not c.push(2, on=ev.target):
            c.prone(on=ev.target)

    _on_my_next_hit(c, landed, until=When.EOT)


@power("i2994x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2994x1(c: Cast) -> None:
    """A component that helps a divination ritual."""


@power("i3275p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3275p1(c: Cast) -> None:
    c.bonus("skill:athletics", 4, on=c.me, kind="power",
            until=When.ENCOUNTER)


@power("i3285p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3285p1(c: Cast) -> None:
    """"Once before the end of the encounter, as a minor action" is
    `c.give`: a one-shot put in the drinker's hands. The blast is walked
    as everything within 3 squares, which is a burst's pool rather than a
    blast's wedge."""
    dtype = _element(c, DamageType.ACID, DamageType.COLD, DamageType.FIRE,
                     DamageType.LIGHTNING, DamageType.POISON)

    def swallow(who: int) -> None:
        for foe in c.within(3, of=who, side="enemy"):
            if c.attack(11, REF, on=foe):
                c.damage("2d6", 3, dtype=dtype, on=foe)

    c.give(fn=swallow, on=c.me, cost=MINOR)


@power("i3306p1", level=6, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3306p1(c: Cast) -> None:
    """A camp and its tracks gone, five minutes later."""


@power("i3355p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3355p1(c: Cast) -> None:
    """A vehicle is not a thing the board carries; a mount is, and it is
    the same printed sentence."""
    mount = c.mount()
    if mount is not None:
        c.extra_action(MOVE, on=mount)


@power("i3473p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3473p1(c: Cast) -> None:
    """One ranged attack, so both halves are `once=True`."""
    c.bonus("attack", 4, on=c.me, kind="enhancement",
            until=When.ENCOUNTER, once=True)
    c.bonus("damage", 4, on=c.me, kind="enhancement",
            until=When.ENCOUNTER, once=True)


@power("i566p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i566p1(c: Cast) -> None:
    """An enhancement bonus, which does not stack with the weapon's own --
    the larger wins, which is the printed rule and the intended one."""
    c.bonus("attack", 2, on=c.me, kind="enhancement", until=When.ENCOUNTER)
    c.bonus("damage", 2, on=c.me, kind="enhancement", until=When.ENCOUNTER)


# -- level 7 ----------------------------------------------------------------


@power("i1071p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use an arcane or divine power of 5th level or lower",
       todo=("c.sustain_free()",))
def i1071p1(c: Cast) -> None:
    """Sustaining costs an action the engine spends; nothing waives it for
    one round."""


@power("i1188p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ACID, Keyword.COLD, Keyword.FIRE,
                 Keyword.LIGHTNING, Keyword.POISON],
       todo=("c.grant_inline()",))
def i1188p1(c: Cast) -> None:
    """An at-will attack power granted for the encounter, printed in full
    and with no ref of its own: `c.grant_row` needs a row that exists and
    `c.give` is a one-shot, not an at-will."""


@power("i1368p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.COLD])
def i1368p1(c: Cast) -> None:
    """The extra 2 is cold and carries that type, so it meets a cold
    resistance the weapon's own damage does not."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=_weapon_attack,
            dtype=DamageType.COLD)


@power("i1422p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a force power of 7th level or lower",
       on=Trigger(PowerUsed, _reagent(7, Keyword.FORCE),
                  "you use a force power"))
def i1422p1(c: Cast) -> None:
    """"Slide each target" is about targets, not hits, and targets are
    chosen before the body runs -- so the declaration may be read."""
    for who in _reagent_targets(c):
        c.slide(1, on=who)


@power("i1720p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1720p1(c: Cast) -> None:
    """"The effect ends if you make an attack roll" names the event
    outright, which is why the helper watches `AttackRolled`."""
    _ends_when_you_attack(c, c.invisible(on=c.me, until=When.EONT), c.me)


@power("i2074p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("c.resist(once=)",))
def i2074p1(c: Cast) -> None:
    """The interrupt is banked as a one-shot. "Against a single attack"
    is the missing half: the resistance stands for the turn instead."""
    c.spend_surge(on=c.me)

    def brace(who: int) -> None:
        c.resist(15, DamageType.NECROTIC, on=who, until=When.EOT)

    c.give(fn=brace, on=c.me, cost=ActionType.IMMEDIATE_INTERRUPT)


@power("i2075p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION],
       out_of_combat=True)
def i2075p1(c: Cast) -> None:
    """A disguise and a Bluff bonus, bought with a healing surge."""


@power("i2537p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2537p1(c: Cast) -> None:
    c.bonus("save", 2, on=c.me, kind="power", until=When.ENCOUNTER,
            once=True)


@power("i3297p1", level=7, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3297p1(c: Cast) -> None:
    """An object conjured out of nothing, which cannot be stood on, hidden
    behind or thrown."""


@power("i3357p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3357p1(c: Cast) -> None:
    """The light is narrative; the candle showing up the invisible is not.
    `c.truesight` is `c.see_invisible` with the range the card prints, and
    the candle is carried, so the radius is measured from the bearer."""
    c.truesight(1, on=c.me, until=When.ENCOUNTER)


@power("i3474p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3474p1(c: Cast) -> None:
    """Nothing shrinks a live modifier, so the walk down a point a turn is
    the hold ended and a smaller one laid in its place. At zero nothing is
    laid, which is the stone spent."""
    hold = [c.bonus(AC, 6, on=c.me, kind="enhancement", until=When.ENCOUNTER)]
    left = [6]

    def wanes(ev: TurnStart) -> None:
        if ev.actor != c.me or hold[0] is None:
            return
        c.end_effect(hold[0])
        left[0] -= 1
        hold[0] = c.bonus(
            AC, left[0], on=c.me, kind="enhancement", until=When.ENCOUNTER
        ) if left[0] > 0 else None

    c.watch(TurnStart, wanes, until=When.ENCOUNTER)


@power("i894p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a summoning power of 5th level or lower",
       on=Trigger(PowerUsed, _reagent(5, Keyword.SUMMONING),
                  "you use a summoning power"),
       dropped=("c.reroll_attack(on=)",))
def i894p1(c: Cast) -> None:
    """The temporary hit points land on whatever is serving the summoner.
    Rerolling somebody else's first miss is the missing half."""
    for who in c.servants():
        c.temp_hp(5, on=who)


# -- level 8 ----------------------------------------------------------------


@power("i1008p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a necrotic power of 5th level or lower",
       on=Trigger(PowerUsed, _reagent(5, Keyword.NECROTIC),
                  "you use a necrotic power"))
def i1008p1(c: Cast) -> None:

    def landed(ev: Hit) -> None:
        c.vulnerable(5, DamageType.NECROTIC, on=ev.target, until=When.EONT)

    _on_my_next_hit(c, landed, until=When.EOT)


@power("i1186p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.boost_attack()",))
def i1186p1(c: Cast) -> None:
    """A bonus added to an attack roll already made: nothing reaches back
    into a roll that has landed."""


@power("i1190p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.set_defence()",))
def i1190p1(c: Cast) -> None:
    """"Your Fortitude equals 25 against that attack" replaces a defence
    rather than adding to it, and a modifier cannot say that."""


@power("i1192p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.set_defence()",))
def i1192p1(c: Cast) -> None:
    """As i1190p1, for Reflex."""


@power("i1194p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.set_defence()",))
def i1194p1(c: Cast) -> None:
    """As i1190p1, for Will."""


@power("i1770p1", level=8, cls=ITEM, usage=DAILY,
       action=ActionType.IMMEDIATE_REACTION, reach=PERSONAL, target=SELF,
       trigger="you are damaged by an attack",
       on=Trigger(DamageApplied, targets_me, "you are damaged"))
def i1770p1(c: Cast) -> None:
    """"You can no longer shift" is `c.cannot_shift`, which is exactly that and
    not `c.immobilized`."""
    if c.may("spend a healing surge", who=c.me):
        c.spend_surge(on=c.me)
    else:
        c.save(on=c.me)
    c.cannot_shift(on=c.me, until=When.ENCOUNTER)


@power("i2043p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2043p1(c: Cast) -> None:
    """A dream at the next extended rest."""


@power("i2080p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("c.resist(once=)",))
def i2080p1(c: Cast) -> None:
    """The choice of lightning or thunder is made when the one-shot is
    spent, not when the potion is drunk."""
    c.spend_surge(on=c.me)

    def brace(who: int) -> None:
        c.resist(15, _element(c, DamageType.LIGHTNING, DamageType.THUNDER),
                 on=who, until=When.EOT)

    c.give(fn=brace, on=c.me, cost=ActionType.IMMEDIATE_INTERRUPT)


@power("i2513p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       trigger="you use a healing power of 6th level or lower",
       on=Trigger(PowerUsed, _reagent(6, Keyword.HEALING),
                  "you use a healing power"))
def i2513p1(c: Cast) -> None:
    """"The target of the power" is a target, not a hit, so the
    declaration may be read for it."""
    for who in _reagent_targets(c):
        c.heal(5, on=who)


@power("i3010p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a conjuration power of 6th level or lower",
       on=Trigger(PowerUsed, _reagent(6, Keyword.CONJURATION),
                  "you use a conjuration power"))
def i3010p1(c: Cast) -> None:
    """Two traps in one row. `PowerUsed` is announced **above** the body
    of the power it answers, so the conjuration does not exist yet and
    looking for it here finds nothing -- the whole row was silent. It is
    `PowerResolved` for the same use that says it is on the board, and the
    reagent's own resolution arrives first, which is what the ref check
    is for.

    "Enemies adjacent to it" is then an aura 1 hung on the conjuration --
    `c.aura(on=)` follows anything with a position -- carrying the penalty
    through `c.grants_in`, so a creature that walks up afterwards takes it
    and one that walks away stops. Untyped: the card prints a bare -2."""
    spent_on = getattr(c.trigger, "power", "")
    before = set(c.conjurations())

    def arrived(ev: PowerResolved) -> None:
        if getattr(ev, "power", "") != spent_on:
            return
        for thing in c.conjurations():
            if thing in before or c.made_by(thing) != c.me:
                continue
            ring = c.aura(1, on=thing, until=When.ENCOUNTER)
            c.grants_in(ring, "attack", -2, side="enemy", kind="untyped")

    c.watch(PowerResolved, arrived, until=When.EOT)


@power("i3273p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION],
       dropped=("query.against_wall()",))
def i3273p1(c: Cast) -> None:
    """The minor action is banked, and "until you attack" ends the hold
    the one-shot lays. Dropped: the third end -- you stop being beside a
    wall or an object your own size -- has nothing to ask. `c.scenery`
    sees the loose objects a room was furnished with and not the map's
    own walls, so gating on it would end the concealment instantly on
    every board that has no furniture."""

    def blend(who: int) -> None:
        _ends_when_you_attack(
            c, c.conceal(on=who, total=True, until=When.ENCOUNTER), who
        )

    c.give(fn=blend, on=c.me, cost=MINOR)


@power("i3276p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.set_defence()",))
def i3276p1(c: Cast) -> None:
    """A defence set to a number, as i1190p1."""


@power("i3279p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3279p1(c: Cast) -> None:
    """Levitation is a fly speed of 1: the four squares are vertical and
    a move's worth of height is what `c.mode` grants."""
    c.mode("fly", 1, on=c.me, until=When.ENCOUNTER)


@power("i3284p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3284p1(c: Cast) -> None:
    """An hour of breathing underwater."""


@power("i3296p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=ONE_ALLY, keywords=[Keyword.ILLUSION])
def i3296p1(c: Cast) -> None:
    """"Until he or she moves or attacks" is two ends and neither is a
    `When`, so the encounter clock is the outer bound and both are taken
    off by hand. `Moved` rather than `MoveStart`: the printed line is
    about having moved, and the dust should survive a move that is
    refused.

    `c.invisible` is one of the methods that defaults to the **caster**,
    so "yourself or an adjacent ally" has to name who: without `on=` this
    row hid the drinker and left the ally plainly visible."""
    who = c.target
    hold = c.invisible(on=who, until=When.ENCOUNTER)
    if hold is None or who is None:
        return
    _ends_when_you_attack(c, hold, who)
    spent: list[bool] = []

    def stirred(ev: Moved) -> None:
        if spent or ev.actor != who:
            return
        spent.append(True)
        c.end_effect(hold)

    c.watch(Moved, stirred, until=When.ENCOUNTER)


@power("i3299p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.FIRE])
def i3299p1(c: Cast) -> None:

    def coated(ev: Hit) -> None:
        c.ongoing(5, DamageType.FIRE, on=ev.target)

    c.apply_poison(coated)


@power("i3300p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBlast(3), target=EACH_OTHER,
       dropped=("c.effects_on()",))
def i3300p1(c: Cast) -> None:
    """Barring concealment is `c.no_cover`. Losing what is already up is
    `c.end_effect` over the holds that grant it, found by the label
    `c.invisible` and `c.conceal` stamp -- so an invisibility or a
    concealment a row laid comes off.

    Dropped, and re-aimed off `c.end_effect`, which exists now: what is
    still missing is a way to ask what effects a creature is under.
    Matching on a label fragment reaches the two spellings those verbs
    happen to use and nothing else, so concealment from terrain or from
    a monster trait stands."""
    c.no_cover(until=When.SAVE_ENDS)
    for word in ("unseen", "concealment"):
        while c.end_effect(against=word) is not None:
            pass


@power("i3569p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(5, 10), target=NO_TARGET, keywords=[Keyword.ZONE],
       dropped=("c.burns(condition=)",))
def i3569p1(c: Cast) -> None:
    """Seven eggs on one card. The shared half -- difficult ground and 5
    damage to whoever starts a turn in it -- is the hazard; the condition
    each variety adds on top of that is what a hazard cannot carry."""
    c.hazard(c.area(), 5, _element(c), until=When.ENCOUNTER,
             difficult=True, sustain=None)


@power("i3577p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i3577p1(c: Cast) -> None:
    c.resist(5, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)
    c.bonus("damage", 2, on=c.me, kind="power", until=When.ENCOUNTER,
            when=_keyword_gate(Keyword.FIRE))

    def spent(ev: ActionPointSpent) -> None:
        if ev.actor == c.me:
            c.heal(5, on=c.me)

    c.watch(ActionPointSpent, spent, until=When.ENCOUNTER, once=True)


@power("i3578p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("c.swallowed()",))
def i3578p1(c: Cast) -> None:
    """Being inside something that ate you is not a state the board has,
    so only the second half -- swallow it yourself and be sick -- is
    written."""
    c.dazed(on=c.me, until=When.SOTNT)


@power("i813p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a radiant power of 5th level or lower",
       on=Trigger(PowerUsed, _reagent(5, Keyword.RADIANT),
                  "you use a radiant power"))
def i813p1(c: Cast) -> None:

    def landed(ev: Hit) -> None:
        c.vulnerable(5, DamageType.RADIANT, on=ev.target, until=When.EONT)

    _on_my_next_hit(c, landed, until=When.EOT)


# -- level 9 ----------------------------------------------------------------


@power("i2077p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i2077p1(c: Cast) -> None:
    """The spec prints the amount as a monster's ref; the ladder above it
    -- 15 at level 29, a step of 5 a tier -- puts the heroic rung at 5."""
    c.spend_surge(on=c.me)
    c.regeneration(5, on=c.me, until=When.ENCOUNTER, while_bloodied=True)


@power("i2081p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2081p1(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.temp_hp(15, on=c.me)


@power("i2852p1", level=9, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a fear power of 5th level or lower",
       on=Trigger(PowerUsed, _reagent(5, Keyword.FEAR),
                  "you use a fear power"))
def i2852p1(c: Cast) -> None:
    """"To end any effect of the power" is the save context's `label`,
    which is the ref of the row that laid the hold -- so the penalty
    bites only on saves against this power's own effects and not on
    every save the target makes."""
    spent_on = getattr(c.trigger, "power", "")

    def laid_by_it(ctx: dict[str, Any]) -> bool:
        return ctx["label"].split()[:1] == [spent_on]

    for who in _reagent_targets(c):
        c.penalty("save", 2, on=who, until=When.ENCOUNTER, when=laid_by_it)


@power("i3064p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON])
def i3064p1(c: Cast) -> None:

    def coated(ev: Hit) -> None:
        c.ongoing(5, DamageType.POISON, on=ev.target)

    c.apply_poison(coated)


@power("i3278p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       dropped=("query.is_basic_attack()",))
def i3278p1(c: Cast) -> None:
    """The draught ends itself on a natural 1 or 2, which is read off
    `AttackRolled.natural` -- both bonuses go together.

    Dropped: nothing asks whether an attack was a basic one, so the
    damage bonus applies to every attack rather than only to basics."""
    holds = [
        c.bonus("skill:athletics", 2, on=c.me, kind="power",
                until=When.ENCOUNTER),
        c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER),
    ]

    def fumbled(ev: AttackRolled) -> None:
        if ev.attacker != c.me or ev.natural > 2:
            return
        for hold in holds:
            c.end_effect(hold)

    c.watch(AttackRolled, fumbled, until=When.ENCOUNTER, on=c.me, once=True)


@power("i463p1", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       attack=Attack(DEX, vs=REF, plus=3))
def i463p1(c: Cast) -> None:
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)
        c.grants_advantage(until=When.SAVE_ENDS, to="team")
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power("i667p1", level=9, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use an acid power of 5th level or lower",
       on=Trigger(PowerUsed, _reagent(5, Keyword.ACID),
                  "you use an acid power"))
def i667p1(c: Cast) -> None:

    def landed(ev: Hit) -> None:
        c.vulnerable(5, DamageType.ACID, on=ev.target, until=When.EONT)

    _on_my_next_hit(c, landed, until=When.EOT)


# -- level 10 ---------------------------------------------------------------


@power("i1265p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       todo=("c.teleport_as()",))
def i1265p1(c: Cast) -> None:
    """"You can use a move action to teleport 5 squares" is a way of
    moving granted for a while; `c.grant_action` knows shift and stand
    and silently eats anything else."""


@power("i1297p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.FIRE],
       trigger="you use a fire power of 7th level or lower",
       on=Trigger(PowerUsed, _reagent(7, Keyword.FIRE),
                  "you use a fire power"))
def i1297p1(c: Cast) -> None:
    """"Each target" is about targets rather than hits."""
    for who in _reagent_targets(c):
        c.ongoing(5, DamageType.FIRE, on=who)


@power("i1370p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a cold power of 7th level or lower",
       on=Trigger(PowerUsed, _reagent(7, Keyword.COLD),
                  "you use a cold power"))
def i1370p1(c: Cast) -> None:
    """"No effect if the power already immobilizes the target" is what
    the engine does anyway: the second hold is the same hold."""

    def landed(ev: Hit) -> None:
        c.immobilized(on=ev.target, until=When.SAVE_ENDS)

    _on_my_next_hit(c, landed, until=When.EOT)


@power("i1444x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1444x1(c: Cast) -> None:
    """Dim light, two squares out."""


@power("i1444p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(2, 5), target=NO_TARGET,
       keywords=[Keyword.RADIANT, Keyword.ZONE],
       dropped=("c.is_vulnerable()", "c.expend()"))
def i1444p1(c: Cast) -> None:
    """The zone stands. What it pays out is "as if it had taken radiant
    damage", which is the creature's own vulnerability read back at it --
    and nothing reports what a creature is vulnerable to."""
    c.zone(c.area(), until=When.ENCOUNTER)


@power("i1703p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1703p1(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.temp_hp(15, on=c.me)
    c.resist(5, DamageType.ACID, on=c.me, until=When.ENCOUNTER)


@power("i1928p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=ONE_ALLY)
def i1928p1(c: Cast) -> None:
    """"Or take damage equal to your healing surge value instead" is the
    branch for a creature with no surges left."""
    who = c.target if c.target is not None else c.me
    if not c.spend_surge(on=who):
        c.flat(c.surge_value(of=who), on=who)
    c.cure(Condition.PETRIFIED, on=who)


@power("i2562p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       dropped=("c.raging()",))
def i2562p1(c: Cast) -> None:
    """"You are considered to be raging" has nothing to set: rage is a
    barbarian's own state and nothing else reads it."""
    _soulfang(c)


@power("i2565p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2565p1(c: Cast) -> None:
    c.bonus("speed", 2, on=c.me, kind="power", until=When.ENCOUNTER)
    _soulfang(c)


@power("i2752p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF)
def i2752p1(c: Cast) -> None:
    c.bonus("damage", 6, on=c.me, kind="power", until=When.ENCOUNTER)


@power("i2845p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.LIGHTNING])
def i2845p1(c: Cast) -> None:
    """"Each enemy within 2 squares of the target; the target does not
    take this damage" -- so the creature that was hit is left out."""

    def struck(ev: Hit) -> None:
        for foe in c.within(2, of=ev.target, side="enemy"):
            if foe != ev.target:
                c.flat(2, dtype=DamageType.LIGHTNING, on=foe)

    _on_each_hit(c, struck)


@power("i3063p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3063p1(c: Cast) -> None:
    """"Against the next attack that deals fire damage to it" is one
    blow's worth, and the order is what makes it sayable: `deal_damage`
    reads the vulnerability and announces `DamageApplied` afterwards, so
    the blow that spends the hold still gets it. No saving throw -- the
    card gives none -- so the encounter clock is the outer bound."""

    def struck(ev: Hit) -> None:
        victim = ev.target
        hold = c.vulnerable(5, DamageType.FIRE, on=victim,
                            until=When.ENCOUNTER)
        if hold is None:
            return
        spent: list[bool] = []

        def burnt(hurt: DamageApplied) -> None:
            if spent or hurt.target != victim or hurt.dtype is not DamageType.FIRE:
                return
            spent.append(True)
            c.end_effect(hold)

        c.watch(DamageApplied, burnt, until=When.ENCOUNTER)

    _on_each_hit(c, struck)


@power("i3280p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.reroll_attack(ev=)",))
def i3280p1(c: Cast) -> None:
    """A reroll banked for later, as i2068p1."""


@power("i3286p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3286p1(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.bonus("speed", 2, on=c.me, kind="power", until=When.ENCOUNTER)


@power("i3289p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING])
def i3289p1(c: Cast) -> None:
    """As i3288p1: the surge is spent when there is one, and a bloodied
    drinker with none regains the hit points anyway."""
    if c.spend_surge(on=c.me) or c.bloodied(on=c.me):
        c.heal(c.roll("2d8") + 10, on=c.me)


@power("i3292p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3292p1(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.resist(25, on=c.me, until=When.EONT)


@power("i3293p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3293p1(c: Cast) -> None:
    c.spend_surge(on=c.me)
    c.extra_action(MOVE, on=c.me)


@power("i3337p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(1), target=EACH_ENEMY,
       keywords=[Keyword.COLD, Keyword.NECROTIC],
       attack=Attack(vs=WILL, printed=13),
       dropped=("c.no_healing(temp_hp=)",))
def i3337p1(c: Cast) -> None:
    """Two damage types, so two burns: ongoing damage of one type does not
    stack but different types do, which is what the card wants. Barring
    *temporary* hit points is the clause with nothing to set."""
    if not c.strike():
        return
    victim = c.target
    c.ongoing(5, DamageType.COLD)
    c.ongoing(5, DamageType.NECROTIC)
    c.no_healing(until=When.SAVE_ENDS)
    c.grants_advantage(until=When.SAVE_ENDS)
    if victim is not None:
        c.on_attack(lambda ev: c.penalty("save", 2, on=victim, once=True),
                    by=victim, until=When.SAVE_ENDS)


@power("i3588p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(10), target=ONE_ALLY)
def i3588p1(c: Cast) -> None:
    """"Until the end of 1d4 of its turns" is counted, not clocked, and
    `When` has no turn count -- so the hold runs on the encounter and a
    `TurnEnd` watcher takes it off on the right one. A creature that
    cannot act still takes its turn, which is what makes the count
    reachable; a ghost turn is not one of its turns."""
    who = c.target
    hold = c.condition(Condition.REMOVED, until=When.ENCOUNTER)
    if hold is None or who is None:
        return
    left = [c.roll("1d4")]

    def ticks(ev: TurnEnd) -> None:
        if ev.actor != who or ev.ghost or not left:
            return
        left[0] -= 1
        if left[0] <= 0:
            left.clear()
            c.end_effect(hold)

    c.watch(TurnEnd, ticks, until=When.ENCOUNTER)


@power("i844p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ACID])
def i844p1(c: Cast) -> None:

    def struck(ev: Hit) -> None:
        c.ongoing(2, DamageType.ACID, on=ev.target)

    _on_each_hit(c, struck)


@power("i969p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       trigger="you use a teleport power of 10th level or lower",
       todo=("c.teleport_bonus()",))
def i969p1(c: Cast) -> None:
    """The teleport has already happened by the time anything is
    announced, and nothing lengthens one before it does."""
