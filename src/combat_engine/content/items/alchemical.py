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
* **A coating is tied to the weapon it is on.** "Apply this to your weapon
  or one piece of ammunition, then make a secondary attack against the
  next creature you hit with it" is `c.apply_poison`, which coats one of
  the things in hand and checks the blow against it. Ammunition is not
  modelled and does not have to be: the card offers two answers and the
  row takes the weapon.
* **Poison in a meal has no combat consequence at all.** "The first
  creature to consume the food or drink within the next hour" is not a
  thing a fight contains, and the payout is measured in hours or in
  extended rests, so those rows are `out_of_combat=True` -- deliberately
  inert rather than unwritten.
* **A zone of smoke is two different sentences.** "Totally obscured" is
  `c.zone(blocks_sight=True)`; "lightly obscured" is concealment for
  whoever stands in it, which `_obscured` below hangs on the zone's
  geometry the way `c.cover_in` hangs cover on it.
* **The item being consumed is `usage=DAILY`.** Every row here is spent
  when it is used and the engine has one use of it to spend, so a printed
  "Effect: The item is consumed" asks for nothing the header has not
  already said.

Three readings that were written into this file as engine limits and are
not ones. They are recorded here because the docstrings asserting them
were believed for a while.

* **A creature-type pool is `c.is_kind`.** `Target` carries no `kind` and
  does not need to: the body asks, and skips the targets the card does not
  name. `Cast.kinds_of` is written for exactly this.
* **An aftereffect is `EffectExpired`.** The event carries `what` and a
  `why` -- `"saved"` for a hold shaken off, `"end of turn"` for a clocked
  one -- so "Aftereffect: ..." is a watcher on the hold this row laid,
  and the reason is what tells it apart from the creature dying.
* **A zone that answers whoever stands in it is `ZoneEntered`.** Both
  halves: an attack on entry, and a modifier taken back on `ZoneExited`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
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
    DamageApplied,
    DamageType,
    Dropped,
    Effect,
    EffectExpired,
    Gear,
    Hit,
    Keyword,
    Melee,
    Position,
    Ranged,
    Square,
    Stats,
    TurnEnd,
    TurnStart,
    When,
    ZoneEntered,
    ZoneExited,
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


def _after(c: Cast, held: Effect | None, fn: Callable[[], None]) -> None:
    """"Aftereffect: ..." -- what a hold pays out once it lets go.

    `Effect.on_end` is handed no reason and fires for every ending there
    is, including the creature dying. `EffectExpired` carries the reason,
    and `Effects` writes exactly three that mean the hold ran its course:
    `"saved"` for a save-ends one shaken off, and `"start of turn"` or
    `"end of turn"` for a clocked one reaching its boundary. Death,
    "removed", "encounter over" and a deliberate `c.end_effect` are all
    endings the printed word does not cover, which is why the reasons are
    listed rather than negated.

    Armed on the encounter rather than on the hold, because an effect's
    own subscriptions are torn down before it announces its end.
    """
    if held is None:
        return
    tag = str(held)
    owner = held.owner
    ran_out = ("saved", "start of turn", "end of turn")

    def ended(ev: EffectExpired) -> None:
        if ev.actor == owner and ev.what == tag and ev.why in ran_out:
            fn()

    c.watch(EffectExpired, ended, until=When.ENCOUNTER, on=owner,
            label=f"{c.ref} aftereffect")


def _while_in(
    c: Cast,
    zone: int,
    area: Iterable[Square],
    give: Callable[[int], Effect | None],
    *,
    until: When,
) -> None:
    """Hold something on whoever stands in a zone, and take it back.

    `Cast` has `grants_in`, `resist_in`, `cover_in` and
    `ignores_difficult_in` on exactly this shape and no way to reach the
    private helper under them, so the geometry is kept here. Whoever is
    already inside when the zone is laid gets it too, since the printed
    line is about being there rather than about arriving.
    """
    held: dict[int, Effect] = {}

    def take(who: int) -> None:
        got = held.pop(who, None)
        if got is not None:
            c.end_effect(got, why="left the zone")

    def offer(who: int) -> None:
        if who in held:
            return
        got = give(who)
        if got is not None:
            held[who] = got

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            offer(ev.actor)

    def exited(ev: ZoneExited) -> None:
        if ev.zone == zone:
            take(ev.actor)

    for who in c.in_squares(area):
        offer(who)
    c.watch(ZoneEntered, entered, until=until, label=f"{c.ref} in")
    c.watch(ZoneExited, exited, until=until, label=f"{c.ref} out")


def _obscured(c: Cast, zone: int, area: Iterable[Square], *, until: When) -> None:
    """"All squares within the zone are lightly obscured."

    Concealment for whoever stands in it. Not `c.zone(blocks_sight=True)`:
    that is the *totally* obscured reading, it is terrain rather than a
    thing the creature carries, and it blinds both sides.
    """
    _while_in(c, zone, area, lambda who: c.conceal(on=who, until=until),
              until=until)


def _in_zone(c: Cast, zone: int, who: int) -> bool:
    return who in c.world.zones.occupants(zone)


def _weeding(c: Cast, kind: str, bonus: int = 10) -> None:
    """A burst that clears one sort of creature and leaves a zone doing it.

    The zone is laid on `c.first`; its watchers are armed after, because
    `Zones._spawn` refreshes on creation and so the creatures caught by
    the burst have already announced their `ZoneEntered` by then -- arming
    first would attack each of them twice.
    """
    area = c.area()
    if c.first:
        zone = c.zone(area, until=When.ENCOUNTER)

        def bite(who: int) -> None:
            if c.is_kind(kind, on=who) and c.attack(bonus, FORT, on=who):
                c.slide(2, on=who, anchor=c.origin)

        def walked_in(ev: ZoneEntered) -> None:
            if ev.zone == zone:
                bite(ev.actor)

        def woke_in_it(ev: TurnStart) -> None:
            if not ev.ghost and _in_zone(c, zone, ev.actor):
                bite(ev.actor)

        c.watch(ZoneEntered, walked_in, until=When.ENCOUNTER)
        c.watch(TurnStart, woke_in_it, until=When.ENCOUNTER)
    if c.is_kind(kind) and c.strike():
        c.slide(2, anchor=c.origin)


# -- level 1 ----------------------------------------------------------------


@power("i1564p1", level=1, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Ranged(3), target=ONE_CREATURE, keywords=[Keyword.RADIANT],
       attack=Attack(vs=REF, printed=4))
def i1564p1(c: Cast) -> None:
    """"One undead creature or demon" is a pool the body draws. `Target`
    carries no creature type and does not need to: `c.kinds_of` reads the
    stat block's type line and its keywords, so "demon" is asked the same
    way "undead" is, and anything else the decider aims this at is left
    alone."""
    if not (c.is_kind("undead") or c.is_kind("demon")):
        return
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
       reach=PERSONAL, target=SELF)
def i521p1(c: Cast) -> None:
    """"Against poisons" is the keywords of the row that laid the hold,
    which the save context carries.

    "From a source of 10th level or lower" is the other half, and the gate
    is not handed the world -- but it does not need to be, because `c` is
    in scope and `ctx["effect"]` is the `Effect` itself, whose `source` is
    the creature that laid it. Its level is read off `Stats` the way every
    other row that wants a level reads it.

    The keyword is tested first and short-circuits, which is what keeps
    this safe on the death-save context in `turns.py`: that one carries an
    empty `keywords` and no `effect` at all, so the `.get` is never
    reached. An unknown source counts as *not* under the cap rather than
    over it -- the wrong default here would pay the bonus against every
    poison in the game, which is more than the card prints, not less.

    Level 11 and level 21 raise the cap to 20 and 30. Those are rungs of
    the ladder, and a rung is a column."""
    cap = 10

    def weak_poison(ctx: dict[str, Any]) -> bool:
        if Keyword.POISON not in ctx["keywords"]:
            return False
        effect = ctx.get("effect")
        source = getattr(effect, "source", None)
        stats = c.world.get(source, Stats) if source is not None else None
        return stats is not None and stats.level <= cap

    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, when=weak_poison)


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
       attack=Attack(vs=REF, printed=5))
def i2099p1(c: Cast) -> None:
    """Both halves are sayable and neither was written.

    The pool is five type words, which is `c.is_kind` five times.

    "The target doesn't benefit from resistances" is `c.resistances` --
    which reads back what the creature shrugs off, by type -- and then a
    **negative** `c.resist` for each, which is the printed "the target
    loses resist 10 to fire" and stays arithmetic where a positive one
    takes the highest. It strips for everybody rather than for the
    thrower, which is what the card says; the hold puts back exactly what
    it took when it lapses."""
    if not any(c.is_kind(w) for w in
               ("aberrant", "elemental", "fey", "immortal", "undead")):
        return
    if not c.strike():
        return
    c.damage("1d8")
    victim = c.target
    for dtype, amount in c.resistances(on=victim).items():
        c.resist(-amount, dtype, on=victim, until=When.EONT)


@power("i2820p1", level=2, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       attack=Attack(vs=REF, printed=5))
def i2820p1(c: Cast) -> None:
    """"At which point the creature is then slowed" is an aftereffect off
    a clocked hold rather than off a save, and `EffectExpired` announces
    both -- see `_after`."""
    if not c.strike():
        return
    victim = c.target
    held = c.immobilized(until=When.EONT)
    _after(c, held, lambda: c.slowed(on=victim, until=When.EOTNT))


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
       )
def i1403p1(c: Cast) -> None:
    """`c.ignore_resistance(insubstantial=True)` is the printed clause, and
    the old docstring here said it did not exist.

    It is a property of the attacker, so it is laid `on=c.me` and gated on
    the one creature, which is what "when determining damage for the
    attack" narrows to. `Hit` is announced before the body deals its
    damage, so a hold taken here is read by the blow that triggered it."""

    def coated(ev: Hit) -> None:
        victim = ev.target
        if not c.is_kind("undead", on=victim):
            return
        if not c.is_(Condition.INSUBSTANTIAL, on=victim):
            return
        if c.attack(6, FORT, on=victim):
            c.ignore_resistance(
                insubstantial=True, on=c.me, until=When.EOT,
                when=lambda ctx: ctx["target"] == victim,
            )

    c.apply_poison(coated)


@power("i1530p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       out_of_combat=True)
def i1530p1(c: Cast) -> None:
    """Poison in a meal. Deliberately inert: the attack is made on
    whoever eats it, against a Perception check, and no creature on a
    board eats anything. There is no combat clause here to write."""


@power("i1551p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.HEALING],
       out_of_combat=True)
def i1551p1(c: Cast) -> None:
    """The extra hit points are paid at the end of a short rest, which is
    not a moment an encounter has."""


@power("i2539p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF)
def i2539p1(c: Cast) -> None:
    """The secondary attack fires on the next hit made with the coated
    weapon. The card offers a weapon or a piece of ammunition; the row
    takes the weapon, which is one of the two printed answers."""

    def coated(ev: Hit) -> None:
        if c.attack(6, FORT, on=ev.target):
            c.slowed(on=ev.target, until=When.SAVE_ENDS)

    c.apply_poison(coated)


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
       )
def i3313p1(c: Cast) -> None:
    """A zone armed by a damage type nobody has dealt yet.

    A zone carries no trigger of its own, but a watcher outlives the body
    and can ask whether the creature that was hurt is standing in it, so
    the arming is `DamageApplied` and nothing else is needed.

    "Attacks against creatures in the zone gain +2 to damage rolls that
    include the triggering type" is `c.vulnerable` on the occupants: it is
    the same arithmetic aimed from the other end, and `c.grants_in` --
    which pays whoever stands inside -- is the wrong way round for a line
    that pays whoever is shooting in.

    The save penalty reads `ctx["dtypes"]`, which the saving-throw context
    carries for exactly this: "against ongoing damage **of that type**".

    Everything lasts until the end of the triggering creature's next turn,
    so the clock is one `When.EOTNT` hold on that creature and the rest
    hang off its ending."""
    area = c.area()
    zone = c.zone(area, until=When.ENCOUNTER)
    armed: list[bool] = []
    hot = (DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING,
           DamageType.RADIANT, DamageType.THUNDER)

    def burnt(ev: DamageApplied) -> None:
        if armed or not _in_zone(c, zone, ev.target):
            return
        types = ev.dtypes or (ev.dtype,)
        dtype = next((t for t in types if t in hot), None)
        if dtype is None:
            return
        armed.append(True)
        clock = c.effect(f"{c.ref} charged", until=When.EOTNT, on=ev.target)
        laid: list[Effect] = []
        for who in c.world.zones.occupants(zone):
            laid += [e for e in (
                c.vulnerable(2, dtype, on=who, until=When.ENCOUNTER),
                c.penalty(
                    "save", 2, on=who, until=When.ENCOUNTER,
                    when=lambda ctx, d=dtype: ctx["ongoing"] and d in ctx["dtypes"],
                ),
            ) if e is not None]

        def done() -> None:
            for eff in laid:
                c.end_effect(eff, why="the zone went out")
            c.world.zones.end(zone, "the zone went out")

        if clock is None:
            done()
        else:
            clock.on_end.append(done)

    c.watch(DamageApplied, burnt, until=When.ENCOUNTER)


@power("i3315p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       attack=Attack(vs=REF, printed=6))
def i3315p1(c: Cast) -> None:
    """"Effect: The item is consumed" is printed as a clause of its own
    here and buys nothing over the header: `usage=DAILY` is one use and
    using the row spends it, so there is no second spending left to say.
    `c.expend_row` is the other sentence -- spending a *different* row's
    use as a price -- and would double-charge this one."""
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
       attack=Attack(vs=FORT, printed=6), dropped=("c.blindsight()",))
def i687p1(c: Cast) -> None:
    """"The target treats all nonadjacent creatures as having concealment"
    is concealment pointed the wrong way, and what concealment *does* is a
    -2 on whoever is swinging at it. Aimed back at the target and gated on
    the reach, that is the printed sentence and not an approximation of
    it: the attack context carries `target`, so "nonadjacent" is asked of
    the board at the moment of the swing.

    Re-aimed. What is left is "creatures that do not rely on sight are
    immune", which is the blindsight gap the tree already names."""
    if not c.strike():
        return
    victim = c.target
    c.penalty(
        "attack", 2, on=victim, until=When.EONT,
        when=lambda ctx: not c.adjacent_to(victim, ctx["target"]),
    )


@power("i715p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON])
def i715p1(c: Cast) -> None:

    def coated(ev: Hit) -> None:
        if c.attack(6, FORT, on=ev.target):
            c.ongoing(5, DamageType.POISON, on=ev.target)

    c.apply_poison(coated)


@power("i803p1", level=3, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(1), target=ONE_ALLY)
def i803p1(c: Cast) -> None:
    c.save(against="fear")


@power("i959p1", level=3, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF)
def i959p1(c: Cast) -> None:
    """The armour answers the next blow that lands on it, and the weaker
    hold that follows the first being shaken off is `_after`.

    "(save ends both)" is one saving throw and `c.penalty` lays one hold
    per call, so the aftereffect hangs on the first of the two: one of
    them ending is the moment the card is talking about, and hanging it on
    both would pay twice."""

    def struck(ev: Hit) -> None:
        attacker = ev.attacker
        if not c.attack(6, REF, on=attacker):
            return
        held = c.penalty("attack", 1, on=attacker, until=When.SAVE_ENDS)
        c.penalty("damage", 2, on=attacker, until=When.SAVE_ENDS)
        _after(c, held, lambda: c.penalty(
            "damage", 2, on=attacker, until=When.SAVE_ENDS))

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
       attack=Attack(vs=FORT, printed=7), dropped=("c.blindsight()",))
def i1243p1(c: Cast) -> None:
    """Re-aimed. The aftereffect is `_after` off the blinding, which is a
    clocked hold rather than a save-ends one; what is still missing is the
    sight clause, which both exempts a creature that does not see from the
    blinding and hands it the aftereffect as the initial effect."""
    if not c.strike():
        return
    victim = c.target
    held = c.blinded(until=When.EONT)
    _after(c, held, lambda: c.penalty(
        "attack", 2, on=victim, until=When.SAVE_ENDS))


@power("i1482p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(1), target=EACH_CREATURE, keywords=[Keyword.ZONE],
       attack=Attack(vs=FORT, printed=10),
       )
def i1482p1(c: Cast) -> None:
    """Both halves were called missing and neither is.

    "Targets plants only" is `c.is_kind`, asked of each creature the burst
    covers.

    "Plants that move into an affected square or begin their turn in an
    affected square are subject to the same attack" is the zone's standing
    bite: `ZoneEntered` for the first half and `TurnStart` for the second,
    which is the pair every "enters or starts its turn in" line needs. The
    watchers outlive the body, so the zone goes on biting for the whole
    encounter."""
    _weeding(c, "plant")


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
       )
def i633p1(c: Cast) -> None:
    """As i1482p1, for beasts rather than plants."""
    _weeding(c, "beast")


@power("i682p1", level=4, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET,
       keywords=[Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING],
       )
def i682p1(c: Cast) -> None:
    """A patch that answers whoever walks onto it.

    Not `c.hazard`, which was the old reading and is a looser one: a
    hazard burns whoever *starts a turn* there as well, and it burns
    without rolling. The card prints one immediate reaction on entering
    and an attack roll for it, which is a `ZoneEntered` watcher and
    `c.attack` -- and once the attack is written out by hand the condition
    each variant adds costs nothing, which is what the marker was for.

    Each variant is its own dice as well as its own type."""
    sq = _free_near(c)
    if sq is None:
        return
    dtype = _element(c, DamageType.FIRE, DamageType.COLD, DamageType.LIGHTNING)
    zone = c.zone({sq}, until=When.ENCOUNTER)

    def stepped_on(ev: ZoneEntered) -> None:
        if ev.zone != zone or not c.attack(7, REF, on=ev.actor):
            return
        if dtype is DamageType.FIRE:
            c.damage("2d8", dtype=dtype, on=ev.actor)
            return
        c.damage("1d8", dtype=dtype, on=ev.actor)
        if dtype is DamageType.COLD:
            c.immobilized(on=ev.actor, until=When.SOTNT)
        else:
            c.grants_advantage(on=ev.actor, until=When.EOTNT, to="team")

    c.watch(ZoneEntered, stepped_on, until=When.ENCOUNTER)


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
       dropped=("c.conjure(hp=)",))
def i925p1(c: Cast) -> None:
    """A bomb on a fuse of up to six rounds.

    "Nothing schedules a power to go off later" was the old reading and it
    is not so: `c.watch(TurnStart)` outlives the body and is a clock, the
    fuse is a counter in its closure, and `c.roll` is the d6 the card asks
    for each round. A delayed power is a watcher that counts.

    The one clause with nothing to hold is "if the bomb is hit by an
    attack it also explodes": the bomb is a square rather than a thing on
    the board, and nothing can be aimed at it."""
    here = _free_near(c) or _square_of(c, c.me)
    if here is None:
        return
    at = [here]
    fuse = [c.choose(list(range(1, 7)), f"{c.ref}: rounds before it goes off") or 6]
    hold: list[Effect] = []

    def detonate() -> None:
        for who in c.in_squares(spread({at[0]}, 1)):
            if c.attack(7, REF, on=who):
                c.damage("1d10", dtype=DamageType.FIRE, on=who)
        if hold:
            c.end_effect(hold[0], why="the bomb went off")

    def tick(ev: TurnStart) -> None:
        if ev.actor != c.me or ev.ghost:
            return
        near = sorted(sq for sq in spread({at[0]}, 1) if sq != at[0])
        at[0] = c.choose(near, f"{c.ref}: where the bomb rolls") or at[0]
        fuse[0] -= 1
        if fuse[0] <= 0 or c.roll(6) == 6:
            detonate()

    hold.append(c.watch(TurnStart, tick, until=When.ENCOUNTER))


# -- level 5 ----------------------------------------------------------------


@power("i1622p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF)
def i1622p1(c: Cast) -> None:

    def coated(ev: Hit) -> None:
        if c.attack(8, REF, on=ev.target):
            c.vulnerable(5, DamageType.FIRE, on=ev.target,
                         until=When.SAVE_ENDS)

    c.apply_poison(coated)


@power("i1753p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1753p1(c: Cast) -> None:
    """The attack context carries the power, so "against attacks made by
    diseases" is a keyword gate rather than a dropped clause."""
    c.bonus(FORT, 2, on=c.me, until=When.ENCOUNTER,
            when=_keyword_gate(Keyword.DISEASE))


@power("i2370p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       attack=Attack(vs=REF, printed=8))
def i2370p1(c: Cast) -> None:
    """"A target wearing metal armor" is `Gear.armour`, which every
    character carries and which half the feat tree already reads -- chain,
    scale and plate are the three metal weights in `chargen.ARMOUR`.

    "Or that has a metallic body" is the same question asked of something
    with no wardrobe, and `c.is_kind("construct")` is where a stat block
    says it. Neither is an engine gap; the old docstring said nothing
    reports what a creature is wearing, and something does."""
    if not c.strike():
        return
    gear = c.world.get(c.target, Gear)
    metal = gear is not None and gear.armour in ("chain", "scale", "plate")
    if metal or c.is_kind("construct"):
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
       out_of_combat=True)
def i3014p1(c: Cast) -> None:
    """Poison in a meal, and the attack it makes is 1d6 hours later.
    Deliberately inert: nothing of it lands inside a fight."""


@power("i3312p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE,
       keywords=[Keyword.NECROTIC, Keyword.POISON],
       attack=Attack(vs=FORT, printed=8))
def i3312p1(c: Cast) -> None:
    """The secondary burst is armed off `Dropped`, which names the
    creature that fell and is the only announcement of it. The weaker
    burn that follows the first being shaken off is `_after`."""
    if not c.strike():
        return
    victim = c.target
    burn = c.ongoing(5, DamageType.POISON)
    _after(c, burn, lambda: c.ongoing(1, DamageType.POISON, on=victim))

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
       keywords=[Keyword.ZONE], attack=Attack(vs=FORT, printed=8))
def i3316p1(c: Cast) -> None:
    """"Each creature at least partially submerged in water" is
    `c.terrain("aquatic")`, which is a property of the encounter rather
    than of a square -- and that is enough, because nobody is submerged in
    a dry fight. A card that only works on water doing nothing on land is
    the printed behaviour, not an approximation of it.

    "If no creatures are in the zone, water in the zone turns to solid
    ice": solid ice is not difficult going, so the same call lays the zone
    both ways and the occupancy decides which."""
    if not c.terrain("aquatic"):
        return
    if c.first:
        area = c.area()
        c.zone(area, difficult=bool(c.in_squares(area)), until=When.ENCOUNTER)
    if c.strike():
        c.immobilized(until=When.EOTNT)


@power("i3320p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET, keywords=[Keyword.ZONE],
       dropped=("c.stored_row()",))
def i3320p1(c: Cast) -> None:
    """Re-aimed, and the row now plays.

    The delay is not the gap -- `c.watch(TurnEnd)` counting one turn is
    "at the end of your next turn", the same clock i925p1 uses -- so the
    crystal lays its zone and the zone goes out on the first creature to
    walk in, which is the whole of the printed trap.

    What is missing is the payload: the card has the wielder put a second
    alchemical item down with the crystal and nothing records which, so
    there is no ref for `c.use_power` to set off. That is the gap i3324p1
    names and the same one."""
    sq = _free_near(c) or _square_of(c, c.me)
    if sq is None:
        return
    mine = [False]

    def armed(ev: TurnEnd) -> None:
        if ev.actor != c.me or ev.ghost:
            return
        if not mine[0]:
            mine[0] = True
            return
        area = spread({sq}, 1)
        zone = c.zone(area, until=When.ENCOUNTER)

        def walked_in(e: ZoneEntered) -> None:
            if e.zone == zone:
                c.world.zones.end(zone, "the crystal flashed")

        c.watch(ZoneEntered, walked_in, until=When.ENCOUNTER)

    # `once` is "fire once and do something": the turn it merely counts
    # changes nothing and does not spend the hold, the turn it lays the
    # zone does.
    c.watch(TurnEnd, armed, until=When.ENCOUNTER, once=True)


@power("i3479p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       keywords=[Keyword.POISON], attack=Attack(vs=FORT, printed=8),
       dropped=("c.restrict_action()",))
def i3479p1(c: Cast) -> None:
    """Re-aimed from `todo` to `dropped`, and the row now plays.

    "Cannot take a standard action" is still not sayable -- it is not
    dazed, which leaves one action of any kind, and nothing takes one kind
    of action away -- so the hold is laid as a labelled effect that reads
    in the log and stops nothing, the shape i2854p1 uses for its tether.

    The aftereffect was the other half of the old marker and is not
    missing: `_after` hangs it on that hold's ending. Writing it is the
    difference between a row refused in play and a row that does most of
    what the card prints."""
    if not c.strike():
        return
    victim = c.target
    held = c.effect(f"{c.ref} cannot take a standard action", until=When.EONT)
    _after(c, held, lambda: c.slowed(on=victim, until=When.EOTNT))


@power("i446p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 10), target=EACH_CREATURE,
       keywords=[Keyword.ACID, Keyword.FIRE],
       attack=Attack(vs=REF, printed=8))
def i446p1(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", dtype=DamageType.FIRE)
        c.ongoing(2, DamageType.ACID)


@power("i469p1", level=5, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF, todo=("c.silvered()",))
def i469p1(c: Cast) -> None:
    """Silver is a material a base weapon does not record and nothing
    reads, so "attacks as a silvered weapon" has nothing to set.

    Re-aimed from `Weapon.silvered`, which was this row alone: eight rows
    across the weapon and feat trees want the same thing and all of them
    call it `c.silvered()`."""


# -- level 6 ----------------------------------------------------------------


@power("i1456p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=Melee(1), target=NO_TARGET, out_of_combat=True)
def i1456p1(c: Cast) -> None:
    """Poison in a meal, on a one-minute fuse and paying out an hour of
    unconsciousness. Deliberately inert: both clocks are longer than any
    fight and the eating is not an action a board has."""


@power("i2540p1", level=6, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=AreaBurst(1, 5), target=NO_TARGET, keywords=[Keyword.ZONE])
def i2540p1(c: Cast) -> None:
    """Lightly obscured is concealment for whoever stands in it, which
    `_obscured` hangs on the zone's geometry."""
    area = c.area()
    _obscured(c, c.zone(area, until=When.EONT), area, until=When.EONT)


@power("i3321p1", level=6, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3321p1(c: Cast) -> None:
    """A silk strand that becomes a rope and then nothing."""


# -- level 8 ----------------------------------------------------------------


@power("i1311p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(1), target=EACH_CREATURE, keywords=[Keyword.ZONE],
       attack=Attack(vs=FORT, printed=10),
       dropped=("c.blindsight()",))
def i1311p1(c: Cast) -> None:
    """The free Stealth check is `c.hide(from_=)`, which is what being
    hidden from one enemy is. The smoke is the zone and `_obscured` is the
    light obscuring of it.

    Re-aimed: what is left is "creatures that do not rely on sight are
    immune", which is the blindsight gap."""
    if c.first:
        area = c.area()
        _obscured(c, c.zone(area, until=When.EONT), area, until=When.EONT)
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
       reach=Melee(1), target=ONE_ALLY, dropped=("c.bonus(instead=)",))
def i2382p1(c: Cast) -> None:
    """Aimed at the escape attempt rather than at Acrobatics generally,
    which is what the card narrows it to. Still a bonus rather than the
    printed override -- "use this modifier instead of your normal check
    modifiers" -- because nothing replaces a total."""
    c.bonus("escape", 14, until=When.ENCOUNTER)


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
       keywords=[Keyword.POISON], attack=Attack(vs=REF, printed=11))
def i896p1(c: Cast) -> None:
    """"Targets plants" is `c.is_kind`.

    "You remove any difficult terrain created by flora within the area" is
    `c.floor`, which is the one verb that *takes away* rough going rather
    than adding it -- the old docstring said the blast had no hold on it.
    The map underneath is untouched and comes back when the overlay
    lapses, so it is laid for the encounter."""
    if c.first:
        c.floor(c.area(), until=When.ENCOUNTER, sustain=None)
    if not c.is_kind("plant"):
        return
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
       reach=PERSONAL, target=SELF, keywords=[Keyword.POISON])
def i2591p1(c: Cast) -> None:

    def coated(ev: Hit) -> None:
        if c.attack(13, FORT, on=ev.target):
            c.weakened(on=ev.target, until=When.EONT)

    c.apply_poison(coated)


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
       reach=AreaBurst(1, 10), target=NO_TARGET, keywords=[Keyword.ZONE])
def i3322p1(c: Cast) -> None:
    """A zone of lightly obscured squares and nothing else."""
    area = c.area()
    _obscured(c, c.zone(area, until=When.ENCOUNTER), area,
              until=When.ENCOUNTER)


@power("i3324x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.store_row(ref)",))
def i3324x1(c: Cast) -> None:
    """Linking one item to another has nothing to hold the link in: an
    item cannot remember a second item's row."""


@power("i3324p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET,
       todo=("c.stored_row()",))
def i3324p1(c: Cast) -> None:
    """Re-aimed: `c.use_power` runs somebody else's row now, so the hold
    is only the link -- nothing records which item this one was tied to,
    and without that there is no ref to set off."""


@power("i3481p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Melee(1), target=NO_TARGET, keywords=[Keyword.ACID],
       out_of_combat=True)
def i3481p1(c: Cast) -> None:
    """Forty acid damage to a stone wall, five minutes later. Walls the
    board carries are raised by a power and have no five-minute clock."""
