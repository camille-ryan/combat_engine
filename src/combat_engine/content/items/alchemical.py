"""Alchemical items, heroic tier: the blocks that need a body.

Nothing here declares an item. The level, the ladder and the price are
columns in `game.db`, and an alchemical item has no enhancement bonus to
hide behind, so what is written here is the whole of the mechanical part.

Six judgements run through the file.

* **A rung of the ladder is a column, not a body.** A card printing
  "level 1 (20 gp) / level 6 (75 gp)" is one row, and the row writes the
  first rung's numbers. The second heroic rung is the same sort of datum
  as the price, and paragon is out of scope outright.
* **"The item's level + 3" is `Attack(printed=)`.** Every attack in the
  slot is that number -- +4 at level 1, +8 at level 5, +13 at level 10 --
  and the printed form says exactly what the page says.
* **A coating cannot be tied to a weapon.** "Apply this to your weapon or
  one piece of ammunition, then make a secondary attack against the next
  creature you hit with it" has no way to ask *which* weapon the swing
  came from: there is nothing that marks an item as coated. Those rows
  play, firing on the wielder's next hit whatever it was made with, and
  carry `dropped=("c.apply_poison()",)`.
* **Poison in a meal is refused outright.** "The first creature to consume
  the food or drink within the next hour" is not a thing a fight contains
  and not a thing a board can answer, so those rows carry
  `todo=("c.apply_poison()",)` and never play.
* **A zone of smoke is two different sentences.** "Totally obscured" is
  `c.zone(blocks_sight=True)`, which the engine has; "lightly obscured" is
  concealment for whoever stands in it, which it does not -- there is no
  way to hang concealment on a zone -- so those rows lay the zone and
  carry `dropped=("c.conceal(in_zone=)",)`.
* **There is no consumption model**, and every row here is spent when it
  is used. `usage=DAILY` is the closest the engine comes. Only the rows
  whose printed text makes the spending a mechanical clause of its own --
  "Effect: The item is consumed" -- carry `dropped=("c.expend()",)`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_CREATURE,
    FORT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Hit,
    Keyword,
    Melee,
    Position,
    Ranged,
    Square,
    When,
    ZoneEntered,
    get,
    power,
    spread,
)

ITEM = "item"

#: "The alchemist chooses acid, cold, fire, lightning, or poison."
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
)


def _element(c: Cast, *among: DamageType) -> DamageType:
    """The damage type an item was made with.

    Chosen when the item was crafted, and no column carries the answer, so
    it is asked of the decider each time the row runs rather than guessed
    at authoring time.
    """
    pool = list(among or _ELEMENTS)
    return c.choose(pool, "the item's damage type") or pool[0]


def _on_my_next_hit(c: Cast, fn: Callable[[Hit], None]) -> None:
    """"The next creature you hit with the coated weapon."

    `c.watch(once=True)` is the wrong tool: it spends itself on whichever
    `Hit` arrives first, including somebody else's, so the flag is kept
    here instead.
    """
    spent: list[bool] = []

    def seen(ev: Hit) -> None:
        if spent or ev.attacker != c.me:
            return
        spent.append(True)
        fn(ev)

    c.watch(Hit, seen, until=When.ENCOUNTER)


def _on_next_hit_on_me(c: Cast, fn: Callable[[Hit], None]) -> None:
    """"The next time a creature hits you."""
    spent: list[bool] = []

    def seen(ev: Hit) -> None:
        if spent or ev.target != c.me or ev.attacker == c.me:
            return
        spent.append(True)
        fn(ev)

    c.watch(Hit, seen, until=When.ENCOUNTER)


def _keyword_gate(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    """Gate a modifier on the keywords of the attack coming in."""

    def gate(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return row is not None and any(w in row.keywords for w in words)

    return gate


def _free_near(c: Cast, of: int | None = None) -> Square | None:
    """An unoccupied square beside somebody, for "an adjacent square"."""
    pos = c.world.get(c.me if of is None else of, Position)
    if pos is None:
        return None
    for sq in sorted(spread({pos.square}, 1)):
        if sq != pos.square and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _square_of(c: Cast, who: int) -> Square | None:
    pos = c.world.get(who, Position)
    return None if pos is None else pos.square


# -- level 1 ----------------------------------------------------------------


@power("i1564p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(3), target=ONE_CREATURE, keywords=[Keyword.RADIANT],
       attack=Attack(vs=REF, printed=4), dropped=("Target.kind",))
def i1564p1(c: Cast) -> None:
    """"One undead creature or demon" is a target pool nothing expresses:
    `Target` has a side and a count and no creature type."""
    if c.strike():
        c.damage("1d10", dtype=DamageType.RADIANT)


@power("i3309p1", level=1, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       attack=Attack(vs=REF, printed=4))
def i3309p1(c: Cast) -> None:
    dtype = _element(c)
    if c.strike():
        c.damage("1d6", dtype=dtype)
    else:
        c.half_damage("1d6", dtype=dtype)


@power("i3314p1", level=1, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3314p1(c: Cast) -> None:
    """An impression of a key in wet plaster."""


@power("i3323p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3323p1(c: Cast) -> None:
    """Poison taken out of a meal, on a one-minute clock."""


@power("i3482p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3482p1(c: Cast) -> None:
    """Light only."""


@power("i470p1", level=1, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE, keywords=[Keyword.ACID],
       attack=Attack(vs=REF, printed=4))
def i470p1(c: Cast) -> None:
    """"5/10" is a normal range and a long one; `Ranged` carries the
    normal range and the long-range penalty is the engine's business."""
    if c.strike():
        c.damage("1d10", dtype=DamageType.ACID)
        c.ongoing(5, DamageType.ACID)
    else:
        c.half_damage("1d10", dtype=DamageType.ACID)


@power("i471p1", level=1, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       keywords=[Keyword.FIRE], attack=Attack(vs=REF, printed=4))
def i471p1(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", dtype=DamageType.FIRE)
    else:
        c.half_damage("1d6", dtype=DamageType.FIRE)


@power("i472p1", level=1, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE, keywords=[Keyword.COLD],
       attack=Attack(vs=REF, printed=4))
def i472p1(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", dtype=DamageType.COLD)
        c.slowed(until=When.EONT)
    else:
        c.half_damage("1d10", dtype=DamageType.COLD)


@power("i521p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("query.level()",))
def i521p1(c: Cast) -> None:
    """"Against poisons" is now sayable -- the save context carries the
    keywords of the row that laid the hold. "From a source of 10th level
    or lower" is the half still missing: a gate is handed the context and
    no world, so the source's level cannot be looked up, and the database
    has monsters above 10 so it is not a clause that is always true."""
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: Keyword.POISON in ctx["keywords"])


@power("i898p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(1), target=ONE_ALLY)
def i898p1(c: Cast) -> None:
    """`ONE_ALLY`'s pool includes the caster, which is "you or an adjacent
    ally" exactly. The source's level is not a gate the save can ask."""
    if c.save(against="blinded"):
        return
    c.save(against="deafened")


@power("i899p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i899p1(c: Cast) -> None:
    """A cubic square of water made safe to drink."""


# -- level 2 ----------------------------------------------------------------


@power("i2014p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.low_light()",))
def i2014p1(c: Cast) -> None:
    """Low-light vision is not a sense the board keeps."""


@power("i2099p1", level=2, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(3), target=ONE_CREATURE,
       attack=Attack(vs=REF, printed=5),
       dropped=("Target.kind", "c.strip_resistance(dtype, on=)"))
def i2099p1(c: Cast) -> None:
    """The damage lands; the creature-type pool and "does not benefit from
    resistances" are both missing."""
    if c.strike():
        c.damage("1d8")


@power("i2820p1", level=2, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       attack=Attack(vs=REF, printed=5), dropped=("c.aftereffect()",))
def i2820p1(c: Cast) -> None:
    """The immobilisation lands; the slow that follows it when the hold
    runs out has no hook -- nothing fires on an effect expiring in a way a
    row can answer with a second effect."""
    if c.strike():
        c.immobilized(until=When.EONT)


@power("i3480p1", level=2, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3480p1(c: Cast) -> None:
    """Ink that glows by firelight, for a day."""


# -- level 3 ----------------------------------------------------------------


@power("i1113p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE, keywords=[Keyword.FIRE],
       attack=Attack(vs=REF, printed=6))
def i1113p1(c: Cast) -> None:
    if c.strike():
        c.ongoing(5, DamageType.FIRE)


@power("i1299p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=NO_TARGET,
       dropped=("c.suppress_aura()",))
def i1299p1(c: Cast) -> None:
    """Four printed clauses. The save against a burn and the destruction
    of a fire zone are both sayable -- `c.save(against=)` picks the burn
    out of whatever else is on a creature, and `c.dispel` unwinds a zone.
    Deactivating a *fire aura* is the one that is not: an aura cannot be
    switched off and put back."""
    area = c.area()
    for who in c.in_squares(area):
        c.save(on=who, bonus=2, against="fire")
    for thing in c.conjurations():
        owner = c.made_by(thing)
        if owner is None or owner == c.me:
            continue
        if c.attack(6, REF, on=owner):
            c.dispel(thing)


@power("i1403p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF,
       todo=("c.apply_poison()", "c.ignore_insubstantial()"))
def i1403p1(c: Cast) -> None:
    """Both halves are missing: nothing marks a weapon as coated, and
    nothing sets a creature's resistance to insubstantial aside for one
    attack."""


@power("i1530p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       todo=("c.apply_poison()",))
def i1530p1(c: Cast) -> None:
    """Poison in a meal: the attack is made on whoever eats it, which is
    not a moment a fight has."""


@power("i1551p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.HEALING],
       out_of_combat=True)
def i1551p1(c: Cast) -> None:
    """The extra hit points are paid at the end of a short rest, which is
    not a moment an encounter has."""


@power("i2539p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, dropped=("c.apply_poison()",))
def i2539p1(c: Cast) -> None:
    """The secondary attack fires on the wielder's next hit, whatever it
    was made with: nothing marks the coated weapon."""

    def coated(ev: Hit) -> None:
        if c.attack(6, FORT, on=ev.target):
            c.slowed(on=ev.target, until=When.SAVE_ENDS)

    _on_my_next_hit(c, coated)


@power("i2854p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       attack=Attack(vs=REF, printed=6), dropped=("c.leash()",))
def i2854p1(c: Cast) -> None:
    """"Cannot move more than 3 squares from the space it occupies" is a
    tether, not a stop: `c.immobilized` and `c.no_walk` are both too much
    and nothing measures distance from a remembered square."""
    if c.strike():
        c.effect("leash", until=When.SAVE_ENDS)


@power("i3093p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=ONE_ALLY, keywords=[Keyword.HEALING])
def i3093p1(c: Cast) -> None:
    """`SurgeSpent` is announced after the surge has paid out, so the
    extra hit points are simply healed on top of it."""
    from combat_engine.engine import SurgeSpent

    who = c.target if c.target is not None else c.me
    spent: list[bool] = []

    def seen(ev: SurgeSpent) -> None:
        if spent or ev.actor != who:
            return
        spent.append(True)
        c.heal(5, on=who)

    c.watch(SurgeSpent, seen, until=When.ENCOUNTER)


@power("i3311p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3311p1(c: Cast) -> None:
    """`c.deals` rewrites what the wielder's weapon attacks come out as,
    which is the whole printed line."""
    c.deals(_element(c), on=c.me, until=When.EONT)


@power("i3313p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=NO_TARGET, keywords=[Keyword.ZONE],
       dropped=("c.zone_condition()",))
def i3313p1(c: Cast) -> None:
    """The zone lands. What it pays out is armed by a damage type nobody
    has dealt yet -- a zone cannot carry a trigger of its own, and
    `c.grants_in` takes a flat modifier and no condition."""
    c.zone(c.area(), until=When.ENCOUNTER)


@power("i3315p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       attack=Attack(vs=REF, printed=6), dropped=("c.expend()",))
def i3315p1(c: Cast) -> None:
    """"Effect: The item is consumed" is printed as a clause of its own
    here, and nothing spends an item."""
    if c.strike():
        c.slowed(until=When.SAVE_ENDS)


@power("i3315p2", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET, out_of_combat=True)
def i3315p2(c: Cast) -> None:
    """Two objects glued together, and a Strength check to part them."""


@power("i473p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       keywords=[Keyword.LIGHTNING], attack=Attack(vs=REF, printed=6))
def i473p1(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", dtype=DamageType.LIGHTNING)
        c.penalty("attack", 1, until=When.SONT)


@power("i687p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       attack=Attack(vs=FORT, printed=6), dropped=("c.conceal(from_=)",))
def i687p1(c: Cast) -> None:
    """"The target treats all nonadjacent creatures as having concealment"
    is concealment pointed the wrong way -- `c.conceal` hides the creature
    it is called on, not everybody else from it. The -2 the blindness is
    worth is laid instead, which over-applies to adjacent swings."""
    if c.strike():
        c.penalty("attack", 2, until=When.EONT)


@power("i715p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON],
       dropped=("c.apply_poison()",))
def i715p1(c: Cast) -> None:

    def coated(ev: Hit) -> None:
        if c.attack(6, FORT, on=ev.target):
            c.ongoing(5, DamageType.POISON, on=ev.target)

    _on_my_next_hit(c, coated)


@power("i803p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(1), target=ONE_ALLY)
def i803p1(c: Cast) -> None:
    c.save(against="fear")


@power("i959p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, dropped=("c.aftereffect()",))
def i959p1(c: Cast) -> None:
    """The armour answers the next blow that lands on it. The aftereffect
    -- a second, weaker hold once the first is saved off -- has no hook."""

    def struck(ev: Hit) -> None:
        if c.attack(6, REF, on=ev.attacker):
            c.penalty("attack", 1, on=ev.attacker, until=When.SAVE_ENDS)
            c.penalty("damage", 2, on=ev.attacker, until=When.SAVE_ENDS)

    _on_next_hit_on_me(c, struck)


# -- level 4 ----------------------------------------------------------------


@power("i1134p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(2), target=ONE_CREATURE, keywords=[Keyword.POISON],
       attack=Attack(vs=FORT, printed=7))
def i1134p1(c: Cast) -> None:
    """"A -2 penalty to defenses" is four penalties: the engine has no
    word that means all of them at once."""
    if c.strike():
        for defence in (AC, FORT, REF, WILL):
            c.penalty(defence, 2, until=When.SAVE_ENDS)
        c.penalty("skill:perception", 5, until=When.SAVE_ENDS)


@power("i1243p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(2), target=ONE_CREATURE, keywords=[Keyword.POISON],
       attack=Attack(vs=FORT, printed=7), dropped=("c.aftereffect()",))
def i1243p1(c: Cast) -> None:
    if c.strike():
        c.blinded(until=When.EONT)


@power("i1482p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(1), target=EACH_CREATURE, keywords=[Keyword.ZONE],
       attack=Attack(vs=FORT, printed=10),
       dropped=("Target.kind", "c.zone_condition()"))
def i1482p1(c: Cast) -> None:
    """The burst and the zone land; the plants-only pool and the standing
    attack on anything that walks back in do not."""
    if c.first:
        c.zone(c.area(), until=When.ENCOUNTER)
    if c.strike():
        c.slide(2, anchor=c.origin)


@power("i1752p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET, out_of_combat=True)
def i1752p1(c: Cast) -> None:
    """A lock destroyed on a Thievery check that replaces your own."""


@power("i2174p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(10), target=ONE_CREATURE,
       attack=Attack(vs=FORT, printed=7))
def i2174p1(c: Cast) -> None:
    if c.strike():
        c.vulnerable(5, DamageType.THUNDER, until=When.EONT)


@power("i2728p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2728p1(c: Cast) -> None:
    """The printed immediate interrupt "occurs automatically", so it is
    armed here rather than declared: a row cannot be both the minor action
    that readies it and the interrupt that spends it."""
    spent: list[bool] = []

    def struck(ev: Hit) -> None:
        row = get(ev.power)
        hot = row is not None and (
            Keyword.THUNDER in row.keywords or Keyword.LIGHTNING in row.keywords
        )
        if spent or ev.target != c.me or not hot:
            return
        spent.append(True)
        c.resist(5, DamageType.THUNDER, on=c.me, until=When.EONT)
        c.resist(5, DamageType.LIGHTNING, on=c.me, until=When.EONT)

    c.watch(Hit, struck, until=When.ENCOUNTER)


@power("i2851p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2851p1(c: Cast) -> None:
    """The printed Requirement names a crossbow; the item was dealt to
    whoever is holding it, so the group is not checked, as everywhere else
    in the item tree."""
    c.bonus("range", 2, on=c.me, until=When.ENCOUNTER, once=True)
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, once=True)


@power("i2930p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.ZONE],
       out_of_combat=True)
def i2930p1(c: Cast) -> None:
    """A tracking bonus laid over five squares, on an hour's clock."""


@power("i3310p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(2), target=ONE_CREATURE, keywords=[Keyword.POISON],
       attack=Attack(vs=WILL, printed=7))
def i3310p1(c: Cast) -> None:
    """The Insight penalty and "is not aware of the attack" are both
    narrative; the daze is the whole of the combat clause."""
    if c.strike():
        c.dazed(until=When.EONT)


@power("i3478p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3478p1(c: Cast) -> None:
    """Endurance against suffocation, and nothing else."""


@power("i633p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(1), target=EACH_CREATURE, keywords=[Keyword.ZONE],
       attack=Attack(vs=FORT, printed=10),
       dropped=("Target.kind", "c.zone_condition()"))
def i633p1(c: Cast) -> None:
    """As i1482p1, for beasts rather than plants."""
    if c.first:
        c.zone(c.area(), until=When.ENCOUNTER)
    if c.strike():
        c.slide(2, anchor=c.origin)


@power("i682p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET,
       keywords=[Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING],
       dropped=("c.burns(condition=)",))
def i682p1(c: Cast) -> None:
    """A patch that answers whoever walks onto it is `c.hazard`. The
    variants differ by a condition as well as a damage type, and a hazard
    deals damage only -- so the immobilisation and the combat advantage
    are dropped and the damage is the fire patch's."""
    sq = _free_near(c)
    if sq is None:
        return
    c.hazard({sq}, "2d8", _element(c, DamageType.FIRE, DamageType.COLD,
                                   DamageType.LIGHTNING),
             until=When.ENCOUNTER, sustain=None)


@power("i891p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=ONE_ALLY)
def i891p1(c: Cast) -> None:
    """"Even if it does not normally allow a saving throw" is not askable:
    `c.save` rolls against a save-ends hold and there is nothing else for
    it to roll against."""
    if c.save(against="dazed"):
        return
    c.save(against="stunned")


@power("i925p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=NO_TARGET, keywords=[Keyword.FIRE],
       todo=("c.delay()",))
def i925p1(c: Cast) -> None:
    """A bomb set for up to six rounds, moved a square a turn and rolled
    for each round: nothing schedules a power to go off later."""


# -- level 5 ----------------------------------------------------------------


@power("i1622p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, dropped=("c.apply_poison()",))
def i1622p1(c: Cast) -> None:

    def coated(ev: Hit) -> None:
        if c.attack(8, REF, on=ev.target):
            c.vulnerable(5, DamageType.FIRE, on=ev.target,
                         until=When.SAVE_ENDS)

    _on_my_next_hit(c, coated)


@power("i1753p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1753p1(c: Cast) -> None:
    """The attack context carries the power, so "against attacks made by
    diseases" is a keyword gate rather than a dropped clause."""
    c.bonus(FORT, 2, on=c.me, until=When.ENCOUNTER,
            when=_keyword_gate(Keyword.DISEASE))


@power("i2370p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       attack=Attack(vs=REF, printed=8), dropped=("c.wearing()",))
def i2370p1(c: Cast) -> None:
    """"A target wearing metal armor or that has a metallic body" cannot
    be asked -- nothing reports what a creature is wearing -- so the
    penalty lands on anything the flask hits."""
    if c.strike():
        c.penalty(AC, 1, until=When.ENCOUNTER)


@power("i2883p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       keywords=[Keyword.THUNDER], attack=Attack(vs=FORT, printed=8))
def i2883p1(c: Cast) -> None:
    if c.strike():
        c.damage("1d4", dtype=DamageType.THUNDER)
        c.push(1, anchor=c.origin)
        c.condition(Condition.DEAFENED, until=When.SAVE_ENDS)


@power("i3014p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       todo=("c.apply_poison()",))
def i3014p1(c: Cast) -> None:
    """Poison in a meal, and the attack it makes is 1d6 hours later."""


@power("i3312p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       keywords=[Keyword.NECROTIC, Keyword.POISON],
       attack=Attack(vs=FORT, printed=8), dropped=("c.aftereffect()",))
def i3312p1(c: Cast) -> None:
    """The secondary burst is armed off `Dropped`, which names the
    creature that fell and is the only announcement of it. The aftereffect
    -- a weaker burn once the first is saved off -- has no hook."""
    if not c.strike():
        return
    victim = c.target
    c.ongoing(5, DamageType.POISON)

    def fell(ev: Dropped) -> None:
        if ev.actor != victim:
            return
        here = _square_of(c, victim)
        if here is None:
            return
        for who in c.in_squares(spread({here}, 1)):
            if who != victim and c.attack(8, REF, on=who):
                c.damage("1d8", dtype=DamageType.NECROTIC, on=who)

    c.watch(Dropped, fell, until=When.ENCOUNTER)


@power("i3316p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       keywords=[Keyword.ZONE], attack=Attack(vs=FORT, printed=8),
       dropped=("c.water()",))
def i3316p1(c: Cast) -> None:
    """"Each creature at least partially submerged" is a target pool the
    board cannot draw: water is terrain, not a square's state."""
    if c.first:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER)
    if c.strike():
        c.immobilized(until=When.EOTNT)


@power("i3320p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET, keywords=[Keyword.ZONE],
       todo=("c.delay()",))
def i3320p1(c: Cast) -> None:
    """A crystal that sets off another item at the end of your next turn:
    nothing schedules a power to go off later, and nothing carries a
    second item's row to set off."""


@power("i3479p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       keywords=[Keyword.POISON],
       todo=("c.restrict_action()", "c.aftereffect()"))
def i3479p1(c: Cast) -> None:
    """"Cannot take a standard action" is not dazed -- a dazed creature
    still gets one action of any kind -- and nothing takes one kind of
    action away. With the hit gone the row has nothing left."""


@power("i446p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       keywords=[Keyword.ACID, Keyword.FIRE],
       attack=Attack(vs=REF, printed=8))
def i446p1(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", dtype=DamageType.FIRE)
        c.ongoing(2, DamageType.ACID)


@power("i469p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, todo=("Weapon.silvered",))
def i469p1(c: Cast) -> None:
    """Silver is a property of a weapon that nothing records, so
    "attacks as a silvered weapon" has nothing to set."""


# -- level 6 ----------------------------------------------------------------


@power("i1456p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=NO_TARGET, todo=("c.apply_poison()",))
def i1456p1(c: Cast) -> None:
    """Poison in a meal, on a one-minute fuse."""


@power("i2540p1", level=6, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 5), target=NO_TARGET, keywords=[Keyword.ZONE],
       dropped=("c.conceal(in_zone=)",))
def i2540p1(c: Cast) -> None:
    """Lightly obscured is concealment for whoever stands in it, and
    nothing hangs concealment on a zone. `blocks_sight` is the heavier
    reading and would be wrong here."""
    c.zone(c.area(), until=When.EONT)


@power("i3321p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3321p1(c: Cast) -> None:
    """A silk strand that becomes a rope and then nothing."""


# -- level 8 ----------------------------------------------------------------


@power("i1311p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(1), target=EACH_CREATURE, keywords=[Keyword.ZONE],
       attack=Attack(vs=FORT, printed=10),
       dropped=("c.conceal(in_zone=)",))
def i1311p1(c: Cast) -> None:
    """The free Stealth check is `c.hide(from_=)`, which is what being
    hidden from one enemy is. The smoke is the zone; lightly obscuring it
    is the missing half."""
    if c.first:
        c.zone(c.area(), until=When.EONT)
    if c.strike() and c.target is not None:
        c.hide(from_=c.target, until=When.EOT)


@power("i1691p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1691p1(c: Cast) -> None:
    """Two watchers, because the printed line is two: the first hit charges
    the weapon, and every hit after that until the end of the next turn
    gets the free attack."""

    def charged(ev: Hit) -> None:

        def while_charged(later: Hit) -> None:
            if later.attacker != c.me:
                return
            was = _square_of(c, later.target)
            if c.attack(11, FORT, on=later.target):
                c.push(1, on=later.target)
                if was is not None:
                    c.shift(1, to=was)

        while_charged(ev)
        c.watch(Hit, while_charged, until=When.EONT)

    _on_my_next_hit(c, charged)


@power("i2382p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_ALLY, dropped=("c.escape()",))
def i2382p1(c: Cast) -> None:
    """The bonus is laid as a bonus rather than as the printed override --
    "use this modifier instead of your normal check modifiers" -- and it
    applies to every Acrobatics check, not only to an escape."""
    c.bonus("skill:acrobatics", 14, until=When.ENCOUNTER)


@power("i2568p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET, out_of_combat=True)
def i2568p1(c: Cast) -> None:
    """Two objects glued together and a DC 29 Strength check to part
    them."""


@power("i3318p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=NO_TARGET, keywords=[Keyword.ZONE],
       dropped=("c.forces(target=)",))
def i3318p1(c: Cast) -> None:
    """The zone answers whoever walks in. Lengthening forced movement
    *into* the zone is the clause with no hold: `c.forces` lengthens what
    a creature does, not what is done to it."""
    zone = c.zone(c.area(), until=When.ENCOUNTER)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone != zone:
            return
        c.penalty("save", 2, on=ev.actor, until=When.ENCOUNTER)
        if not c.save(on=ev.actor, bare=True):
            c.prone(on=ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER)


@power("i896p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBlast(3), target=EACH_CREATURE,
       keywords=[Keyword.POISON], attack=Attack(vs=REF, printed=11),
       dropped=("Target.kind",))
def i896p1(c: Cast) -> None:
    """Undergrowth cleared is difficult terrain taken off the map, which
    the blast has no hold on; the plants-only pool is the named gap."""
    if c.strike():
        c.damage("1d4", dtype=DamageType.POISON)
        c.ongoing(5, DamageType.POISON)


# -- level 9 ----------------------------------------------------------------


@power("i1412p1", level=9, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       keywords=[Keyword.ZONE], attack=Attack(vs=FORT, printed=12))
def i1412p1(c: Cast) -> None:
    """The block carries the zone keyword and prints no zone."""
    if c.strike():
        c.dazed(until=When.SOTNT)
        c.slowed(until=When.SOTNT)


# -- level 10 ---------------------------------------------------------------


@power("i1470p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.blindsight()",))
def i1470p1(c: Cast) -> None:
    """Blindsight is not a sense the board keeps, so there is nothing to
    be invisible to."""


@power("i1671p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       attack=Attack(vs=FORT, printed=13))
def i1671p1(c: Cast) -> None:
    if c.strike():
        c.dazed(until=When.EONT)


@power("i1681p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1681p1(c: Cast) -> None:
    """"19-20" is one square of crit range. The weapon groups the card
    names are not checked: the oil was dealt to whoever is holding it."""
    c.bonus("crit_range", 1, on=c.me, until=When.EONT)


@power("i2591p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON],
       dropped=("c.apply_poison()",))
def i2591p1(c: Cast) -> None:

    def coated(ev: Hit) -> None:
        if c.attack(13, FORT, on=ev.target):
            c.weakened(on=ev.target, until=When.EONT)

    _on_my_next_hit(c, coated)


@power("i2958p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_ALLY)
def i2958p1(c: Cast) -> None:
    """The mundane-agent clause is the only combat one: a creature glued
    down gets its save at once. Which agent held it is not recorded, so
    any immobilisation is shaken off."""
    c.save(against="immobilized")


@power("i3319p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET, out_of_combat=True)
def i3319p1(c: Cast) -> None:
    """Five hundred pounds taken off an object's weight."""


@power("i3322p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=NO_TARGET, keywords=[Keyword.ZONE],
       dropped=("c.conceal(in_zone=)",))
def i3322p1(c: Cast) -> None:
    c.zone(c.area(), until=When.ENCOUNTER)


@power("i3324x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.store_row(ref)",))
def i3324x1(c: Cast) -> None:
    """Linking one item to another has nothing to hold the link in: an
    item cannot remember a second item's row."""


@power("i3324p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET,
       todo=("c.stored_row()", "c.use_power()"))
def i3324p1(c: Cast) -> None:
    """Setting off the linked item's power needs both the link and a way
    to run somebody else's row."""


@power("i3481p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET, keywords=[Keyword.ACID],
       out_of_combat=True)
def i3481p1(c: Cast) -> None:
    """Forty acid damage to a stone wall, five minutes later. Walls the
    board carries are raised by a power and have no five-minute clock."""
