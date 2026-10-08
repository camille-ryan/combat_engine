"""Implement-slot magic items, heroic tier, fourth wave: levels 8 to 10.

Nothing here declares an implement. The ladder, the enhancement bonus, the
price, the critical rider and the base-item restriction are columns in
`game.db` and are laid on by `engine/equipment.py`; what is written here is
only the part that needs a body.

The judgements that run through the whole file are the ones the earlier
implement waves settled, and they are repeated because they decide most of
these rows:

* **"Using this implement" cannot be gated.** The damage context carries
  `target`, `power`, `opportunity`, `charge`, `dtype` and `crit`; the
  attack context adds `attacker`, `advantage`, `ranged`, `branch` and
  `hand`. Neither carries the item, so a rider phrased that way is armed
  always-on, on the ground that the carrier is holding the item for as
  long as the property is.
* **The class half of a line is not enforced.** "A primal implement
  power", "an invoker attack power" -- the item was dealt to whoever is
  holding it. Where the *keyword* is the gate rather than the class
  ("a primal **cold** power", "an **arcane** implement power") the
  keyword is read, because that one the power does print.
* **Where the spec prints a ref** -- `p1400`, `p435`, `p1530` -- the whole
  content of "as the wizard's X power" is `c.grant_attack(c.me, ref=...)`,
  which lends the row for the one swing. Every such block in this batch
  prints its ref, so none of them carries a marker.
* **A `Level 13:`/`Level 19:` line is paragon and out of scope.** Only the
  heroic number is written.

Recurring gaps, each named with the symbol it wants rather than
approximated: `c.reshape_area()`, `c.no_teleport()`, `c.kill()` and
`c.darkvision()`. "Ongoing 5 fire **and** necrotic damage" is one number
of two types and not two numbers, and `c.ongoing(dtypes=)` is it.

Three gaps this file recorded in an earlier wave have since closed, and
the rows that named them are written:
`c.ignore_resistance(insubstantial=True)` pierces the quality,
`c.resistances()` reads what a creature shrugs off so a resistance can be
swapped for a vulnerability, and `AttackResult.critical` is writable --
`Hit` is announced inside `c.strike()`, before the body rolls damage, so
a row promoting a hit still maxes the dice.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Hit,
    Initiative,
    Keyword,
    Melee,
    Position,
    PowerUsed,
    Ranged,
    Relation,
    RelationSet,
    Size,
    SkillCheck,
    Trigger,
    TurnEnd,
    TurnStart,
    Wall,
    When,
    World,
    ZoneEntered,
    about_me,
    both,
    by_keyword,
    by_me,
    by_melee,
    get,
    power,
    query,
    spread,
    targets_me,
    would_hit_me,
)

ITEM = "item"

#: "Fire, cold, acid or lightning" -- the four an elemental ward names.
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
)

#: The same four as keywords, for reading them off a power.
_ELEMENT_WORDS = frozenset(
    {Keyword.ACID, Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING}
)

#: The seven a tome's wielder picks one of.
_TOME_TYPES = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.PSYCHIC,
    DamageType.THUNDER,
)

#: "Fire, force, lightning, necrotic or radiant" -- one printed list.
_ENERGIES = frozenset(
    {
        Keyword.FIRE,
        Keyword.FORCE,
        Keyword.LIGHTNING,
        Keyword.NECROTIC,
        Keyword.RADIANT,
    }
)


def _struck(c: Cast) -> int | None:
    """The creature the triggering attack was aimed at.

    A row triggered by **your own** hit is aimed at `ev.attacker` -- you --
    by the auto-targeter, so it can pick a different enemy than the one
    just hit. Every "use this power when you hit" row reads the event.
    """
    foe = getattr(c.trigger, "target", None)
    return foe if foe is not None else c.target


def _item_level(c: Cast) -> int:
    """The item's own level, which two rows deal damage equal to."""
    p = get(c.ref)
    return p.level if p is not None else 0


def _reach_of(ref: str | None) -> str:
    p = get(ref or "")
    return p.reach.kind if p is not None and p.reach is not None else ""


def _keywords_of(ref: str | None) -> frozenset[Keyword]:
    p = get(ref or "")
    return frozenset(p.keywords) if p is not None else frozenset()


def _my_side(world: World, me: int, who: int | None) -> bool:
    return who is not None and query.team(world, who) is query.team(world, me)


def _is_melee(ctx: dict[str, Any]) -> bool:
    return _reach_of(ctx.get("power")) == "melee"


def _of_type(*types: DamageType):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("dtype") in types

    return gate


def _save_keywords(*words: Keyword):  # noqa: ANN202
    """Save gate: the row that laid the effect printed one of these.
    `durations.keywords_of` reads them back off the effect's label."""
    wanted = set(words)

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(wanted & set(ctx.get("keywords", ())))

    return gate


def _from_row(ref: str):  # noqa: ANN202
    """Attack gate: this roll belongs to that one row.

    The attack context carries `power`, so "+1 to attack rolls with <that
    spell>" is a gate the engine can read outright -- the spec prints the
    ref in the block's own Power beside it.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("power") == ref

    return gate


# -- predicates --------------------------------------------------------------


def _my_kill(world: World, me: int, ev: Dropped) -> bool:
    return ev.source == me


def _my_small_kill(world: World, me: int, ev: Dropped) -> bool:
    """"You drop a Small or Medium enemy" -- the footprint is on
    `Position`, and a victim already off the board is taken on trust."""
    if ev.source != me:
        return False
    pos = world.get(ev.actor, Position)
    return pos is None or pos.size in (Size.SMALL, Size.MEDIUM)


def _hits_me_and_an_ally(world: World, me: int, ev: AttackDeclared) -> bool:
    """`AttackDeclared` names one target per announcement, but `among`
    rides on it as a plain attribute and names everyone the one use is
    aimed at -- which is how "you and at least one ally" is asked."""
    if _my_side(world, me, ev.attacker):
        return False
    among = tuple(getattr(ev, "among", ()) or ())
    return me in among and any(
        w != me and _my_side(world, me, w) for w in among
    )


def _my_curse(world: World, me: int, ev: RelationSet) -> bool:
    return ev.kind_ is Relation.CURSED_BY and ev.source == me


def _used_by_me(ref: str):  # noqa: ANN202
    def gate(world: World, me: int, ev: PowerUsed) -> bool:
        return ev.actor == me and ev.power == ref

    return gate


def _hit_with(ref: str):  # noqa: ANN202
    def gate(world: World, me: int, ev: Hit) -> bool:
        return ev.attacker == me and ev.power == ref

    return gate


def _my_melee_lightning(world: World, me: int, ev: AttackDeclared) -> bool:
    return (
        ev.attacker == me
        and Keyword.LIGHTNING in _keywords_of(ev.power)
        and by_melee(world, me, ev)
    )


def _lightning_hit_by_me(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and Keyword.LIGHTNING in _keywords_of(ev.power)


def _advantaged_hit_by_me(world: World, me: int, ev: Hit) -> bool:
    """`AttackResult` rides on the event as a plain attribute, which is the
    only place the advantage of a spent one-shot survives."""
    result = getattr(ev, "result", None)
    return ev.attacker == me and bool(getattr(result, "advantage", False))


def _arcane_noncrit_by_me(world: World, me: int, ev: Hit) -> bool:
    return (
        ev.attacker == me
        and not ev.critical
        and Keyword.ARCANE in _keywords_of(ev.power)
    )


def _crit_near_me(world: World, me: int, ev: Hit) -> bool:
    """You, or an ally within 5 squares, scores a critical hit."""
    if not ev.critical or not _my_side(world, me, ev.attacker):
        return False
    return ev.attacker == me or query.distance_between(world, me, ev.attacker) <= 5


def _ally_hit_in_sight(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker != me and _my_side(world, me, ev.attacker)


def _ally_failed_check(world: World, me: int, ev: SkillCheck) -> bool:
    return (
        ev.actor != me
        and not ev.success
        and _my_side(world, me, ev.actor)
        and query.distance_between(world, me, ev.actor) <= 5
    )


def _elemental_at_me(world: World, me: int, ev: AttackDeclared) -> bool:
    return ev.target == me and bool(_keywords_of(ev.power) & _ELEMENT_WORDS)


def _energy_damage_at_me(world: World, me: int, ev: DamageRolled) -> bool:
    """The damage context names the power in `detail`, which is what
    `resolve._damage` puts there, so the keyword list is reachable from a
    roll that has not been applied yet -- the window `c.halve` needs."""
    return ev.target == me and bool(_keywords_of(ev.detail) & _ENERGIES)


def _fear_hit_on_me(world: World, me: int, ev: Hit) -> bool:
    return ev.target == me and Keyword.FEAR in _keywords_of(ev.power)


HIT_BY_ME = Trigger(Hit, by_me, "you hit an enemy with this implement")
HIT_IN_MELEE = Trigger(
    Hit, both(by_me, by_melee), "you hit an enemy in melee with this implement"
)


def _pick(c: Cast, radius: int) -> int:
    """"You or an ally within N squares" -- the caster is in the pool."""
    pool = [c.me, *c.within(radius, side="ally")]
    chosen = c.choose(pool, "who gains it")
    return chosen if chosen is not None else c.me


def _first_hit_crits(c: Cast) -> None:
    """"If your first attack roll with the power hits, you score a
    critical hit."

    `AttackResult.critical` is writable and the `Hit` is announced from
    inside `c.strike()`, before the row being lent rolls its damage -- so
    promoting it here pays the crit riders and maxes the dice, which is
    what the printed sentence is. Only the first, which is what the
    latch is for.
    """
    done: list[int] = []

    def promote(ev: Hit) -> None:
        result = getattr(ev, "result", None)
        if ev.attacker != c.me or done or result is None:
            return
        done.append(1)
        result.critical = True
        ev.critical = True

    c.watch(Hit, promote, until=When.EOT)


def _beside(c: Cast, who: int) -> Any:
    """An unoccupied square next to a creature, for a teleport that lands
    there. `c.teleport(to=)` names the square outright."""
    pos = c.world.get(who, Position)
    if pos is None:
        return None
    for sq in sorted(spread({pos.square}, 1)):
        if sq != pos.square and not c.in_squares([sq]):
            return sq
    return None


# -- level 8 ----------------------------------------------------------------


@power(
    "i2975p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2975p1(c: Cast) -> None:
    """Written as a standing gate rather than a snapshot, so an enemy that
    walks up to the companion later is caught and one that walks away is
    not. A wielder with no companion on the board is a board limitation,
    not a creature the row should refuse, so the gate stands open then --
    the same reading `i1583p1` took."""

    def beside_it(ctx: dict[str, Any], foe: int) -> bool:
        mine = c.companion()
        return mine is None or c.adjacent_to(mine, foe)

    for foe in c.enemies():
        c.penalty(
            "attack",
            2,
            on=foe,
            until=When.ENCOUNTER,
            when=lambda ctx, f=foe: beside_it(ctx, f),
        )


@power(
    "i3020p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
)
def i3020p1(c: Cast) -> None:
    """The spec prints the ref, so the row resolves it outright."""
    if c.target is not None:
        c.grant_attack(c.me, on=c.target, ref="p1400")


@power(
    "i3022p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.IMPLEMENT],
)
def i3022p1(c: Cast) -> None:
    if c.target is not None:
        c.grant_attack(c.me, on=c.target, ref="p1341")


@power(
    "i3024p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.IMPLEMENT],
)
def i3024p1(c: Cast) -> None:
    if c.target is not None:
        c.grant_attack(c.me, on=c.target, ref="p435")


@power(
    "i3028p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT],
    trigger="you are hit by an attack",
    on=Trigger(AttackRolled, would_hit_me, "you are hit by an attack"),
)
def i3028p1(c: Cast) -> None:
    """The lent row is itself an interrupt, so the triggering event has to
    reach it -- `c.grant_attack` passes `c.trigger` through, and the
    trigger declared here is the one `p1235` declares."""
    c.grant_attack(c.me, on=c.me, ref="p1235")


@power(
    "i3166p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i3166p1(c: Cast) -> None:
    """Lighting the candle. Bright light in a radius is the lamp case: no
    combat consequence of its own, and the block beside it carries the
    whole mechanical half."""


@power(
    "i3166p2",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(5),
    target=ONE_ALLY,
    trigger="an ally within 5 squares of you fails a skill check",
    on=Trigger(SkillCheck, _ally_failed_check, "a nearby ally fails a check"),
)
def i3166p2(c: Cast) -> None:
    """"While the candle is lit" is not asked: the light has no state the
    engine keeps, and the encounter usage is the once-a-fight the candle's
    own extinguishing enforced."""
    c.boost_check(2 + c.enhancement)


@power(
    "i3172p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a melee attack using this ki focus",
    on=HIT_IN_MELEE,
)
def i3172p1(c: Cast) -> None:
    """"Each of your enemies adjacent to it" is read after the push, which
    is what "at the end of the push" says."""
    foe = _struck(c)
    if foe is None:
        return
    c.push(c.enhancement, on=foe)
    c.prone(on=foe)
    for other in c.within(1, of=foe, side="enemy"):
        if other != foe:
            c.prone(on=other)


@power(
    "i3180x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.reroll_damage(keep=)", "c.death_save_failure()"),
)
def i3180x1(c: Cast) -> None:
    """`c.reroll_damage` keeps the higher of the two rolls; this one must
    keep the new result whatever it is. The price -- a death saving throw
    failure, counted against the three since the last rest -- has no
    counter anywhere."""


@power(
    "i3191x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3191x1(c: Cast) -> None:
    """`c.ignore_resistance(insubstantial=True)` is the piercing half and
    `amount=0` is the rest of it: the card pierces the quality and no
    resistance. The chosen keyword is read off the damage context's
    `dtype` and the arcane half off the row that rolled."""
    pick = c.choose(list(_TOME_TYPES), "which damage type")
    chosen = pick if pick is not None else DamageType.FIRE

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("dtype") is chosen and Keyword.ARCANE in _keywords_of(
            ctx.get("power")
        )

    c.ignore_resistance(
        0, on=c.me, until=When.ENCOUNTER, when=gate, insubstantial=True
    )


@power(
    "i3196p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Wall(5, 10),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def i3196p1(c: Cast) -> None:
    """`c.wall(solid=False)` is a zone in the shape of a wall, which is
    what the printed "a zone in a wall 5" is. Heavy obscurement is
    `blocks_sight`; light obscurement is concealment held on whoever
    stands inside, which is `c.grants_in` with the key `c.conceal` uses
    and `side="any"` because the card shelters everybody. The frost wall
    bites and slows together, so it is written as its own pair of
    watchers rather than as `c.burns` -- once per turn, like `c.burns`,
    and on entering or at the start of a turn, which is the approximation
    every zone in this file makes for "ends its turn there"."""
    pick = c.choose(["flame", "frost", "darkness", "venom"], "which wall")
    pick = pick or "flame"
    zone = c.wall(
        5, solid=False, blocks_sight=pick == "darkness", until=When.EONT
    )
    if not zone:
        return
    if pick == "flame":
        c.burns(zone, 5, DamageType.FIRE)
    elif pick == "venom":
        c.burns(zone, 2, DamageType.POISON)
        c.grants_in(zone, "concealment", 2, side="any", kind="concealment")
    elif pick == "frost":
        bitten: dict[int, int] = {}

        def nip(who: int) -> None:
            if bitten.get(who) == c.world.round:
                return
            bitten[who] = c.world.round
            c.flat(2, dtype=DamageType.COLD, on=who)
            c.slowed(on=who, until=When.SAVE_ENDS)

        def entered(ev: ZoneEntered) -> None:
            if ev.zone == zone:
                nip(ev.actor)

        def began(ev: TurnStart) -> None:
            if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
                nip(ev.actor)

        c.watch(ZoneEntered, entered, until=When.EONT)
        c.watch(TurnStart, began, until=When.EONT)


@power(
    "i3201x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3201x1(c: Cast) -> None:
    """The window is armed by the lightning attack and expires at the start
    of your next turn, so the inner watch carries the duration and the
    outer one only opens it."""

    def charged(ev: AttackDeclared) -> None:
        if ev.attacker != c.me or Keyword.LIGHTNING not in _keywords_of(ev.power):
            return

        def sting(hit: Hit) -> None:
            if hit.target != c.me or hit.attacker == c.me:
                return
            if c.adjacent(hit.attacker):
                c.flat(
                    2 + c.enhancement,
                    dtype=DamageType.LIGHTNING,
                    on=hit.attacker,
                )

        c.watch(Hit, sting, until=When.SONT)

    c.watch(AttackDeclared, charged, until=When.ENCOUNTER)


@power(
    "i3201p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    trigger="you hit a target with a lightning attack using this wand",
    on=Trigger(Hit, _lightning_hit_by_me, "you hit with a lightning attack"),
)
def i3201p1(c: Cast) -> None:
    """"Each creature adjacent to the target" is everybody, not only your
    enemies. Paragon numbers are out of scope."""
    foe = _struck(c)
    if foe is None:
        return
    for other in c.within(1, of=foe):
        if other != foe:
            c.flat(10, dtype=DamageType.LIGHTNING, on=other)


@power(
    "i3201p2",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
    out_of_combat=True,
)
def i3201p2(c: Cast) -> None:
    """A trap laid on an unattended object for whoever touches it within
    five minutes. Nothing in a fight touches scenery, and the duration is
    longer than any encounter."""


@power(
    "i3461x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3461x1(c: Cast) -> None:
    """`AttackRolled` carries the die itself, which is the only place a
    natural 1 can be read. "Cold and lightning damage" is one number that
    is both, so the wielder's own cold resistance alone does not stop
    it."""

    def fumble(ev: AttackRolled) -> None:
        if ev.attacker == c.me and ev.natural == 1:
            c.flat(
                _item_level(c),
                dtypes=(DamageType.COLD, DamageType.LIGHTNING),
                on=c.me,
            )

    c.watch(AttackRolled, fumble, until=When.ENCOUNTER)


@power(
    "i3461p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i3461p1(c: Cast) -> None:
    """"Extra damage" with no type word in front of it is an untyped
    *bonus*, so the modifier carries no `kind` -- which is a different
    thing from its damage type. "Cold and lightning" is one die of two
    types, written as a sequence, and a creature shrugs it off only if
    it resists both."""
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EONT, when=_is_melee,
            dtype=(DamageType.COLD, DamageType.LIGHTNING))


@power(
    "i668p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    trigger="you reduce a target to 0 hit points with this holy symbol",
    on=Trigger(Dropped, _my_kill, "you drop an enemy"),
)
def i668p1(c: Cast) -> None:
    """The creature that fell is measured from while its square is still
    on the board; if it has already been cleared away, the second creature
    is picked from around the caster instead."""
    victim = getattr(c.trigger, "actor", None)
    near = [
        e
        for e in (c.within(5, of=victim, side="enemy") if victim else [])
        if e != victim
    ]
    foe = next(iter(near), None) or next(iter(c.within(5, side="enemy")), None)
    if foe is None:
        return
    c.flat(c.cha_mod, dtype=DamageType.COLD, on=foe)
    c.immobilized(on=foe, until=When.SAVE_ENDS)


@power(
    "i738p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an implement attack using this symbol",
    on=HIT_BY_ME,
)
def i738p1(c: Cast) -> None:
    foe = _struck(c)
    pool = c.within(5, of=foe, side="ally") if foe is not None else c.allies()
    mate = next((m for m in pool if m != c.me), None)
    if mate is not None:
        c.shift(c.enhancement, who=mate)


@power(
    "i929p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=HIT_BY_ME,
)
def i929p1(c: Cast) -> None:
    """"Move his place in the initiative order to directly after your own"
    is `c.initiative`, which is the only thing that moves a creature in the
    order once the d20s are down: `Initiative.rolled` is the sort key, so
    one below mine puts him in the next slot."""
    mate = next(iter(c.within(10, side="ally")), None)
    if mate is None:
        return
    mine = c.world.get(c.me, Initiative)
    his = c.world.get(mate, Initiative)
    if mine is None or his is None:
        return
    c.initiative(mine.rolled - 1 - his.rolled, on=mate)


@power(
    "i967p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a melee attack using this ki focus",
    on=HIT_IN_MELEE,
)
def i967p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is None:
        return
    c.push(c.enhancement, on=foe)
    c.prone(on=foe)
    c.shift(c.enhancement)


# -- level 9 ----------------------------------------------------------------


@power(
    "i1280x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i1280x1(c: Cast) -> None:
    """Two skill-check bonuses and nothing else."""


@power(
    "i1280p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="you hit an enemy with a primal implement power using this totem",
    on=HIT_BY_ME,
)
def i1280p1(c: Cast) -> None:
    c.teleport(c.enhancement)


@power(
    "i1350p1",
    level=9,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.LIGHTNING],
    trigger="you make a melee attack using this ki focus",
    on=Trigger(AttackDeclared, both(by_me, by_melee), "you attack in melee"),
)
def i1350p1(c: Cast) -> None:
    c.deals(DamageType.LIGHTNING, until=When.EOT, on=c.me, implement=True)


@power(
    "i1350p2",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.LIGHTNING, Keyword.TELEPORTATION],
    trigger="you make a melee attack that deals lightning damage",
    on=Trigger(
        AttackDeclared, _my_melee_lightning, "you attack in melee with lightning"
    ),
)
def i1350p2(c: Cast) -> None:
    """"An unoccupied square adjacent to that enemy" is named outright --
    `c.teleport(to=)` takes the square, so the destination is not left to
    the decider, which would happily have put the caster out of reach of
    the creature it is about to hit.

    And when there is no such square the whole Effect fails. The swing used
    to be made outside the guard, so a ring of occupied squares meant no
    teleport and a melee basic attack landing from wherever the caster
    already stood -- up to five squares off, since that is how far the enemy
    was allowed to be from the triggering attack's target."""
    victim = getattr(c.trigger, "target", None)
    pool = (
        [e for e in c.within(5, of=victim, side="enemy") if e != victim]
        if victim is not None
        else c.enemies()
    )
    foe = next(iter(pool), None)
    if foe is None:
        return
    square = _beside(c, foe)
    if square is None:
        return
    c.teleport(0, to=square)
    c.deals(DamageType.LIGHTNING, until=When.EOT, on=c.me, implement=True)
    c.basic(on=foe)


@power(
    "i1516x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_save()",),
)
def i1516x1(c: Cast) -> None:
    """`SavingThrow` **is** announced before it is acted on, so the roll
    itself is reachable from a `c.watch`; what is not reachable is the
    gate, which is the whole of this property. "When you use an arcane
    power to grant a bonus to saving throws" needs the save to say which
    row put the bonus there, and nothing records it -- written without
    that, every low save anybody rolled would be rerolled. `c.on_save()`
    is the hook the nine rows in this group want, gate included."""


@power(
    "i1516p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i1516p1(c: Cast) -> None:
    """The spec prints the ref, so the row resolves it outright."""
    if c.target is not None:
        c.grant_attack(c.me, on=c.target, ref="p4138")


@power(
    "i1733p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you place your curse on a target",
    on=Trigger(RelationSet, _my_curse, "you curse a creature"),
)
def i1733p1(c: Cast) -> None:
    """The ongoing tick announces itself as ordinary damage whose `detail`
    is the effect's own description, which is where "ongoing" can be read;
    there is no separate event for a burn coming off. Paragon numbers are
    out of scope."""
    foe = getattr(c.trigger, "target", None)
    if foe is None:
        return
    c.ongoing(3, on=foe)
    mate = _pick(c, 5)

    def bleed(ev: DamageApplied) -> None:
        if ev.target == foe and ev.source == c.me and "ongoing" in ev.detail:
            c.heal(ev.amount, on=mate)

    c.watch(DamageApplied, bleed, until=When.ENCOUNTER)


@power(
    "i1894x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1894x1(c: Cast) -> None:
    """The damage context carries the victim, so the two conditions are a
    gate the engine can read. Paragon numbers are out of scope."""

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None:
            return False
        return c.is_(Condition.PRONE, on=foe) or c.is_(
            Condition.IMMOBILIZED, on=foe
        )

    c.bonus("damage", 2, kind="item", on=c.me, until=When.ENCOUNTER, when=gate)


@power(
    "i1894p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a melee attack using this ki focus",
    on=HIT_IN_MELEE,
)
def i1894p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.immobilized(on=foe, until=When.SAVE_ENDS)


@power(
    "i1953x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1953x1(c: Cast) -> None:
    """`c.points` asks the power-point half as a gate on the damage
    context, and `c.ignore_resistance(insubstantial=True)` is the
    piercing half -- `amount=0` because the card pierces the quality and
    no resistance."""
    c.ignore_resistance(
        0,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.points() >= 1,
        insubstantial=True,
    )


@power(
    "i1953p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an insubstantial enemy with an attack using this orb",
    on=HIT_BY_ME,
)
def i1953p1(c: Cast) -> None:
    """Two halves: the quality standing now is taken off, and `c.immune`
    keeps it off for the printed duration -- which is also what makes the
    augment mean something, since a bare removal has no duration to
    lengthen."""
    foe = _struck(c)
    if foe is None:
        return
    c.cure(Condition.INSUBSTANTIAL, on=foe)
    held = When.SAVE_ENDS if c.spend_points(1) else When.SONT
    c.immune(Condition.INSUBSTANTIAL, on=foe, until=held)


@power(
    "i1977p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.vulnerable(when=)",),
)
def i1977p1(c: Cast) -> None:
    """`c.resistances` reads what each enemy shrugs off, a negative
    `c.resist` takes that resistance away and `c.vulnerable` puts the
    printed 5 in its place; the hold is the clock, so both go back
    together. The damage context carries no attacker, so the swap cannot
    be narrowed to the wielder's own attacks and an ally swinging in the
    same round gets it too. Paragon numbers are out of scope."""
    for foe in c.enemies():
        for dtype, amount in c.resistances(on=foe).items():
            if amount <= 0:
                continue
            c.resist(-amount, dtype, on=foe, until=When.EONT)
            c.vulnerable(5, dtype, on=foe, until=When.EONT)


@power(
    "i2015p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    dropped=("c.invisible(when=)",),
)
def i2015p1(c: Cast) -> None:
    """`c.invisible` names one watcher and takes no gate, so the range is
    measured once when the power is used: an enemy that closes inside 5
    squares afterwards still cannot see you, which the printed line would
    not allow."""
    for foe in c.enemies():
        if c.distance(foe) > 5:
            c.invisible(to=foe, on=c.me, until=When.EONT)


@power(
    "i2294x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.curse_damage()",),
)
def i2294x1(c: Cast) -> None:
    """`c.curse` hangs the relation; the extra dice the curse pays out are
    rolled inside the class feature and nothing reaches into them."""


@power(
    "i2303x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2303x1(c: Cast) -> None:
    """"Since the end of your last turn" is a set emptied by your own turn
    ending, and the attack context carries the victim, so the gate reads
    the set directly. Paragon numbers are out of scope."""
    hitters: set[int] = set()

    def struck(ev: Hit) -> None:
        if ev.target == c.me and ev.attacker != c.me:
            hitters.add(ev.attacker)

    def forget(ev: TurnEnd) -> None:
        if ev.actor == c.me:
            hitters.clear()

    c.watch(Hit, struck, until=When.ENCOUNTER)
    c.watch(TurnEnd, forget, until=When.ENCOUNTER)
    c.bonus(
        "attack",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") in hitters,
    )


@power(
    "i2303p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a target that has attacked you since your last turn",
    on=HIT_BY_ME,
    dropped=("query.damaged_since()",),
)
def i2303p1(c: Cast) -> None:
    """The property beside this one keeps its own set of recent attackers
    in a closure, which a separate row cannot read; nothing asks the world
    who has attacked whom since when, so the stun lands on any hit."""
    foe = _struck(c)
    if foe is not None:
        c.stunned(on=foe, until=When.EONT)


@power(
    "i2317x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2317x1(c: Cast) -> None:
    """`DamageApplied.resisted` is what the target's resistance took off
    before any of the blow reached hit points, which is the printed
    trigger exactly. The payout is a negative `c.resist`, clamped to what
    is standing so the rod cannot drive a resistance below zero, and the
    class is read off `detail` -- the ref of the row that rolled it."""
    me, plus = c.me, c.enhancement

    def blunted(ev: DamageApplied) -> None:
        if ev.source != me or ev.resisted <= 0:
            return
        p = get(ev.detail)
        if p is None or p.cls != "invoker":
            return
        standing = c.resistances(on=ev.target).get(ev.dtype, 0)
        if standing > 0:
            c.resist(
                -min(plus, standing), ev.dtype, on=ev.target, until=When.EONT
            )

    c.watch(DamageApplied, blunted, until=When.ENCOUNTER)


@power(
    "i2317p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2317p1(c: Cast) -> None:
    """"The next power you use" is `once=True`: the bonus is spent by
    whichever attack roll comes first."""
    c.bonus(
        "attack", 2, kind="power", on=c.me, until=When.ENCOUNTER, once=True
    )


@power(
    "i2604x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2604x1(c: Cast) -> None:
    """The damage context carries `dtype`, so the four energies are a gate
    the engine can read. Paragon numbers are out of scope."""
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_of_type(*_ELEMENTS),
    )


@power(
    "i2604p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=INTERRUPT,
    reach=CloseBurst(2),
    target=SELF,
    trigger="you are attacked by a fire, cold, acid or lightning power",
    on=Trigger(AttackDeclared, _elemental_at_me, "an energy attack targets you"),
)
def i2604p1(c: Cast) -> None:
    """Paragon radii and numbers are out of scope; this is the heroic 2
    squares and resist 10."""
    kind = c.choose(list(_ELEMENTS), "which energy") or DamageType.FIRE
    c.resist(10, kind, on=c.me, until=When.EONT)
    for mate in c.within(2, side="team"):
        c.resist(10, kind, on=mate, until=When.EONT)


@power(
    "i2615x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i2615x1(c: Cast) -> None:
    """Overland speed, and the printed line says outright that it does not
    affect speed in combat."""


@power(
    "i2615p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(1),
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="you take damage from an attack",
    on=Trigger(DamageApplied, targets_me, "you take damage"),
)
def i2615p1(c: Cast) -> None:
    c.teleport(c.enhancement)
    for mate in c.within(1, side="team"):
        c.teleport(c.enhancement, who=mate)


@power(
    "i2763x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2763x1(c: Cast) -> None:
    """The save context carries the keywords of the row that laid the
    effect, so "against fear effects" is one gate. Counted once, when the
    trait arms, like the other allies-within-N properties here."""
    gate = _save_keywords(Keyword.FEAR)
    for who in [c.me, *c.within(5, side="ally")]:
        c.bonus(
            "save", c.enhancement, kind="item", on=who,
            until=When.ENCOUNTER, when=gate,
        )


@power(
    "i2763p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy hits you with a power that has the fear keyword",
    on=Trigger(Hit, _fear_hit_on_me, "a fear power hits you"),
)
def i2763p1(c: Cast) -> None:
    """"An immediate saving throw against the effect" is `c.save`, which
    rolls against one standing save-ends hold."""
    c.save(on=c.me)


@power(
    "i2774x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2774x1(c: Cast) -> None:
    """"Or 1d10 while you're bloodied" is one die or the other, not a
    second bonus, so it is chosen at the moment the blow lands. Paragon
    numbers are out of scope."""

    def burn(ev: Hit) -> None:
        if ev.attacker != c.me or Keyword.DIVINE not in _keywords_of(ev.power):
            return
        if not c.marked(on=ev.target):
            return
        dice = "1d10" if c.bloodied(on=c.me) else "1d6"
        c.damage(dice, dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, burn, until=When.ENCOUNTER)


@power(
    "i2783p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    trigger="you hit with a radiant attack delivered by this holy symbol",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.RADIANT)), "you hit with radiant"
    ),
)
def i2783p1(c: Cast) -> None:
    """"When it uses a standard action to attack" is readable: the declared
    attack names its power, and the power's own header says what action it
    costs. Paragon numbers are out of scope."""
    foe = _struck(c)
    if foe is None:
        return

    def punish(ev: AttackDeclared) -> None:
        if ev.attacker != foe:
            return
        p = get(ev.power)
        if p is not None and p.action is ActionType.STANDARD:
            c.flat(5, dtype=DamageType.RADIANT, on=foe)

    c.watch(AttackDeclared, punish, until=When.SAVE_ENDS, on=foe)


@power(
    "i2802p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy targets you and at least one ally with an attack",
    on=Trigger(
        AttackDeclared,
        _hits_me_and_an_ally,
        "an enemy targets you and at least one ally",
    ),
)
def i2802p1(c: Cast) -> None:
    """`AttackDeclared` names one target per announcement, but `among`
    rides on it and names the whole use, so the pool is readable after
    all. `query.defence` reads each score with the level term in it and
    the gap is laid as a plain modifier, which the roll callback reads
    after the interrupt window -- so it lands on the announcement being
    answered as well as on the ones still to come. It holds to the end of
    the turn rather than to the one attack, because a modifier has no way
    to name a single roll."""
    ev = c.trigger
    vs = getattr(ev, "vs", None)
    among = [
        w for w in getattr(ev, "among", ()) if _my_side(c.world, c.me, w)
    ]
    if vs is None or not among:
        return
    scores = {w: query.defence(c.world, w, vs) for w in among}
    best = max(scores.values())
    for who, score in scores.items():
        if best > score:
            c.bonus(vs, best - score, on=who, until=When.EOT)


@power(
    "i2804p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(5),
    target=ONE_CREATURE,
    trigger="you or an ally within 5 squares scores a critical hit",
    on=Trigger(Hit, _crit_near_me, "somebody nearby scores a critical hit"),
)
def i2804p1(c: Cast) -> None:
    """`c.grant_action_point` hands one out beyond the encounter's own
    limit, which is what "gains an action point" means."""
    who = getattr(c.trigger, "attacker", None)
    if who is not None:
        c.grant_action_point(1, on=who)


@power(
    "i2807p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with an attack using this holy symbol",
    on=HIT_BY_ME,
)
def i2807p1(c: Cast) -> None:
    """"Cannot make opportunity attacks" is `c.threatens(0)`: how far a
    creature reaches for an opening, taken down to nothing."""
    foe = _struck(c)
    if foe is None:
        return
    c.immobilized(on=foe, until=When.SAVE_ENDS)
    c.threatens(0, on=foe, until=When.SAVE_ENDS)
    c.penalty("attack", 2, on=foe, until=When.SAVE_ENDS)


@power(
    "i2895x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.retarget_defence()",),
)
def i2895x1(c: Cast) -> None:
    """The defence a power attacks is header data: `AttackDeclared.vs` is
    a field but `resolve.attack` reads its own local afterwards, so a
    listener rewriting it changes nothing. The block's second paragraph
    is the tome's contents, which is the Power beside this one."""


@power(
    "i2895p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.expend_row(among=)",),
)
def i2895p1(c: Cast) -> None:
    """"The powers contained in the tome" is a set the card names by
    description rather than by ref, which is exactly what `c.borrow_row`
    reads off the registry and records the pick of -- wizard dailies with
    the force keyword, of a level the tome's own level allows, highest
    first. The price is not written: expending an unused daily of equal
    or higher level means choosing among the ones the character still
    has, and `c.expend_row` takes one ref rather than a set."""
    for lv in range(_item_level(c), 0, -1):
        if c.borrow_row(
            cls="wizard",
            level=lv,
            usage=DAILY,
            keyword=Keyword.FORCE,
            until=When.ENCOUNTER,
        ):
            return


@power(
    "i2908x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2908x1(c: Cast) -> None:
    """`engine/skills.py` totals `skill:<name>` and `skill` off the
    creature's modifiers, so the two check bonuses do have a key to hang
    on. Paragon numbers are out of scope."""
    for skill in ("arcana", "perception"):
        c.bonus(
            f"skill:{skill}", 1, kind="item", on=c.me, until=When.ENCOUNTER
        )
    c.bonus(
        "damage",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None
        and c.is_kind("aberrant", on=ctx["target"]),
    )


@power(
    "i2908p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a primal implement power using this totem",
    todo=("c.no_teleport()",),
)
def i2908p1(c: Cast) -> None:
    """`c.forbid` takes one named row away; barring a whole keyword, in
    both directions, is the thing nothing says."""


@power(
    "i2913p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a primal cold power using this totem",
    on=Trigger(Hit, both(by_me, by_keyword(Keyword.COLD)), "you hit with cold"),
)
def i2913p1(c: Cast) -> None:
    """"Grants combat advantage" with nobody named is the whole side, which
    is `to="team"`."""
    foe = _struck(c)
    if foe is None:
        return
    c.immobilized(on=foe, until=When.SAVE_ENDS)
    c.grants_advantage(on=foe, until=When.SAVE_ENDS, to="team")


@power(
    "i2920p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you reduce an enemy to 0 hit points with this totem",
    on=Trigger(Dropped, _my_kill, "you drop an enemy"),
)
def i2920p1(c: Cast) -> None:
    c.extra_action(MOVE, on=c.me)


@power(
    "i2923x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.see_invisible(within=)",),
)
def i2923x1(c: Cast) -> None:
    """`c.see_invisible` is all or nothing, so "adjacent to your spirit
    companion" cannot narrow it and the caster sees every invisible
    creature."""
    c.see_invisible(on=c.me, until=When.ENCOUNTER)


@power(
    "i3171x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3171x1(c: Cast) -> None:
    """Five points of any resistance, so no type and a cap. The paragon
    and epic steps are out of scope."""
    c.ignore_resistance(5, on=c.me, until=When.ENCOUNTER)


@power(
    "i3190x1",
    level=9,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i3190x1(c: Cast) -> None:
    """A skill-check bonus and nothing else."""


@power(
    "i3190p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a skill check and dislike the result",
    on=Trigger(SkillCheck, about_me, "you make a skill check"),
)
def i3190p1(c: Cast) -> None:
    """Not flagged narrative: `SkillCheck` is a first-class event and
    `c.reroll_check` a real verb, so the row is written rather than
    declared inert -- a check rolled in a fight is rerolled here."""
    c.reroll_check()


@power(
    "i3190p2",
    level=9,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i3190p2(c: Cast) -> None:
    """"Before the end of the current turn" is `When.EOT`, and `once=True`
    spends the bonus on the first roll."""
    c.bonus("attack", 2, kind="item", on=c.me, until=When.EOT, once=True)


# -- level 10 ---------------------------------------------------------------


@power(
    "i1093p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use your p5032 power to assume beast form",
    on=Trigger(PowerUsed, _used_by_me("p5032"), "you assume beast form"),
    dropped=("c.in_beast_form()",),
)
def i1093p1(c: Cast) -> None:
    """The trigger is declared against the ref the spec prints. "Using
    beast form powers" is the clause nothing gates: a form is not a
    keyword and the damage context cannot be asked which form a power
    belongs to, so the bonus rides every roll while the form lasts."""
    c.resize(Size.LARGE, on=c.me, until=When.ENCOUNTER)
    c.bonus(
        "damage", c.enhancement, kind="power", on=c.me, until=When.ENCOUNTER
    )


@power(
    "i1104p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=REACTION,
    reach=Ranged(20),
    target=ONE_ALLY,
    trigger="an ally within your line of sight hits with an attack",
    on=Trigger(Hit, _ally_hit_in_sight, "an ally hits with an attack"),
)
def i1104p1(c: Cast) -> None:
    """The ally's die is read off the `AttackResult` riding on the event,
    which is the only place it survives, and `critical` on that same
    result is writable. A reaction answers inside the `Hit`, before the
    ally's body rolls its damage, so promoting it there maxes the dice
    and pays the crit riders. A tie does neither, as printed."""
    result = getattr(c.trigger, "result", None)
    theirs = getattr(result, "natural", 0)
    mine = c.roll("1d20")
    if mine > theirs and result is not None:
        result.critical = True
        c.trigger.critical = True
    elif mine < theirs:
        c.penalty("attack", 2, on=c.me, until=When.EONT)


@power(
    "i1303x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1303x1(c: Cast) -> None:
    """"Granting combat advantage to you" is asked of the blow that landed,
    not of the creature afterwards: a one-shot grant has already been spent
    by then."""

    def burn(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        if not getattr(getattr(ev, "result", None), "advantage", False):
            return
        c.damage("1d6", dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, burn, until=When.ENCOUNTER)


@power(
    "i1303p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
)
def i1303p1(c: Cast) -> None:
    """"The next power ... during this turn" is latched on the first ref
    seen, so the burn rides every target of that one power and nothing
    after it. Paragon numbers are out of scope."""
    latch: list[str] = []

    def kindle(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        if not latch:
            latch.append(ev.power)
        if ev.power == latch[0]:
            c.ongoing(5, DamageType.FIRE, on=ev.target)

    c.watch(Hit, kindle, until=When.EOT)


@power(
    "i1899p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit a target that is granting combat advantage to you",
    on=Trigger(Hit, _advantaged_hit_by_me, "you hit with combat advantage"),
)
def i1899p1(c: Cast) -> None:
    foe = _struck(c)
    if foe is not None:
        c.damage("2d6", on=foe)


@power(
    "i2091x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2091x1(c: Cast) -> None:
    """The named power is the one the block beside this one prints a ref
    for, and the attack context carries `power`, so the gate is exact."""
    c.bonus(
        "attack",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_from_row("p173"),
    )


@power(
    "i2091p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.RADIANT],
)
def i2091p1(c: Cast) -> None:
    """The latch is armed before the row is lent, so the first hit of the
    lent power is the one promoted."""
    if c.target is not None:
        _first_hit_crits(c)
        c.grant_attack(c.me, on=c.target, ref="p173")


@power(
    "i2093x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2093x1(c: Cast) -> None:
    c.bonus(
        "attack",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_from_row("p1530"),
    )


@power(
    "i2093p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def i2093p1(c: Cast) -> None:
    if c.target is not None:
        _first_hit_crits(c)
        c.grant_attack(c.me, on=c.target, ref="p1530")


@power(
    "i2301x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.racial_row()",),
)
def i2301x1(c: Cast) -> None:
    """The fire half is written as a watch rather than a damage modifier so
    that the extra really is fire rather than a nameless addition to
    whatever the blow deals. The racial half names a trait the spec gives
    no ref for and nothing raises another row's bonus."""

    def scorch(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        if c.cursed(on=ev.target) and c.bloodied(on=ev.target):
            c.flat(c.enhancement, dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, scorch, until=When.ENCOUNTER)


@power(
    "i2316x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2316x1(c: Cast) -> None:
    """`relations.set` announces the curse being laid, so "when you place
    your curse" is a readable event."""

    def laid(ev: RelationSet) -> None:
        if ev.kind_ is not Relation.CURSED_BY or ev.source != c.me:
            return
        c.vulnerable(
            c.enhancement, DamageType.PSYCHIC, on=ev.target, until=When.EONT
        )

    c.watch(RelationSet, laid, until=When.ENCOUNTER)


@power(
    "i2329x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2329x1(c: Cast) -> None:
    def laid(ev: RelationSet) -> None:
        if ev.kind_ is not Relation.CURSED_BY or ev.source != c.me:
            return
        c.vulnerable(
            c.enhancement, DamageType.RADIANT, on=ev.target, until=When.EONT
        )

    c.watch(RelationSet, laid, until=When.ENCOUNTER)


@power(
    "i2346p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    trigger="you place your curse on a target",
    on=Trigger(RelationSet, _my_curse, "you curse a creature"),
)
def i2346p1(c: Cast) -> None:
    """Paragon numbers are out of scope."""
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.vulnerable(2, DamageType.FIRE, on=foe, until=When.EONT)


@power(
    "i2411p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.FORCE],
    trigger="you are hit by an attack",
    on=Trigger(AttackRolled, would_hit_me, "you are hit by an attack"),
)
def i2411p1(c: Cast) -> None:
    c.grant_attack(c.me, on=c.me, ref="p1235")


@power(
    "i2411p2",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.IMPLEMENT],
)
def i2411p2(c: Cast) -> None:
    if c.target is not None:
        c.grant_attack(c.me, on=c.target, ref="p435")


@power(
    "i2467p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.reshape_area()",),
)
def i2467p1(c: Cast) -> None:
    """`c.widen_areas` grows a close burst or blast; shrinking an area
    burst to a single square is the other direction and nothing says it.
    The attack bonus is written, spent on the first roll."""
    c.bonus(
        "attack", 2, kind="power", on=c.me, until=When.ENCOUNTER, once=True
    )


@power(
    "i2467p2",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.LIGHTNING],
)
def i2467p2(c: Cast) -> None:
    if c.target is not None:
        c.grant_attack(c.me, on=c.target, ref="p1530")


@power(
    "i2595p1",
    level=10,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ACID],
    dropped=("c.deals(when=)",),
)
def i2595p1(c: Cast) -> None:
    """`c.deals` converts every blow rather than only the fire ones. "A
    free action returns the damage to normal" is `c.endable`, which is
    the same sentence seen from the other side: the effect is the
    caster's, so the drop is offered to the caster for a free action."""
    c.endable(
        c.deals(DamageType.ACID, until=When.ENCOUNTER, on=c.me, implement=True),
        FREE,
    )


@power(
    "i2595p2",
    level=10,
    cls=ITEM,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
    dropped=("c.deals(when=)",),
)
def i2595p2(c: Cast) -> None:
    c.endable(
        c.deals(DamageType.FIRE, until=When.ENCOUNTER, on=c.me, implement=True),
        FREE,
    )


@power(
    "i2608p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you take damage from a fire, force, lightning, necrotic or "
    "radiant attack",
    on=Trigger(
        DamageRolled, _energy_damage_at_me, "you take energy damage"
    ),
)
def i2608p1(c: Cast) -> None:
    """Declared on the roll rather than on the hit: `c.halve` takes a
    number off damage that has been rolled and not yet dealt, and `Hit`
    carries no amount to halve. `DamageRolled.detail` is the power, which
    is where the keyword list is read."""
    c.halve()
    c.bonus(
        "attack", 2, kind="power", on=c.me, until=When.ENCOUNTER, once=True
    )
    c.bonus(
        "damage", 10, kind="power", on=c.me, until=When.ENCOUNTER, once=True
    )


@power(
    "i2674p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    trigger="you hit with a primal attack power using this totem",
    on=HIT_BY_ME,
)
def i2674p1(c: Cast) -> None:
    """"As if you had spent a healing surge" costs no surge, so this is the
    surge's value healed rather than `c.surge`."""
    c.heal(c.surge_value(), on=c.me)


@power(
    "i2787p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a divine attack power using this symbol",
    on=HIT_BY_ME,
)
def i2787p1(c: Cast) -> None:
    """`c.cannot_attack(against=)` bars one creature rather than all of
    them, which is the printed line."""
    foe = _struck(c)
    mate = next(iter(c.within(5, side="ally")), None)
    if foe is None or mate is None:
        return
    c.cannot_attack(on=foe, against=mate, until=When.EONT)


@power(
    "i2905x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2905x1(c: Cast) -> None:
    """"On your next attack against it" is `once=True`, so the opening is
    spent by whichever swing comes first."""

    def mark(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        if not _keywords_of(ev.power) & {Keyword.FIRE, Keyword.RADIANT}:
            return
        c.grants_advantage(on=ev.target, until=When.EONT, to="me", once=True)

    c.watch(Hit, mark, until=When.ENCOUNTER)


@power(
    "i2905p1",
    level=10,
    cls=ITEM,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i2905p1(c: Cast) -> None:
    """A torch, and nothing else."""


@power(
    "i2909p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger="you hit with a primal attack power using this totem",
    on=HIT_BY_ME,
)
def i2909p1(c: Cast) -> None:
    """The companion is measured from as well as the caster, which is the
    printed "within 2 squares of you or your spirit companion"."""
    mine = c.companion()
    pool = set(c.within(2, side="ally"))
    if mine is not None:
        pool |= set(c.within(2, of=mine, side="ally"))
    for mate in sorted(pool):
        c.save(on=mate, bonus=c.enhancement)


@power(
    "i2917p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION, Keyword.ZONE],
)
def i2917p1(c: Cast) -> None:
    """The zone is centred on the ally rather than on the caster, so its
    squares are spread from where that ally stands. `c.burns` bites on
    entering as well as at the start of a turn and the printed line bites
    only at the start of one, so the damage goes in the same watcher as
    the slow rather than in a burn."""
    mate = next(iter(c.within(10, side="ally")), None)
    if mate is None:
        return
    pos = c.world.get(mate, Position)
    if pos is None:
        return
    area = spread({pos.square}, 5)
    c.zone(area, until=When.EONT)
    c.teleport(5, who=mate)

    def drag(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.in_squares(area):
            return
        c.flat(5, on=ev.actor)
        c.slowed(on=ev.actor, until=When.EOT)

    c.watch(TurnStart, drag, until=When.EONT)


@power(
    "i3018x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i3018x1(c: Cast) -> None:
    """A skill-check bonus laid on top of another power's benefit, and
    nothing else."""


@power(
    "i3018p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def i3018p1(c: Cast) -> None:
    """The spec prints the ref. The lent row is a close burst on its
    caster, so the caster is the creature it is resolved against."""
    c.grant_attack(c.me, on=c.me, ref="p4990")


@power(
    "i3167p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=SELF,
    dropped=("c.heal_bonus()", "c.reroll_attack(ev=)"),
)
def i3167p1(c: Cast) -> None:
    """Of the three printed benefits only the first can be said: nothing
    maximises a heal, and `c.reroll_attack` answers the attack that
    triggered the row it is in, which a benefit armed a turn earlier has
    no way to reach."""
    c.save(on=c.me)
    for mate in c.within(5, side="team"):
        c.save(on=mate)


@power(
    "i3179x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def i3179x1(c: Cast) -> None:
    """Three skill-check bonuses and nothing else."""


@power(
    "i3179p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.CHARM],
)
def i3179p1(c: Cast) -> None:
    """An enemy already marked by the caster is skipped outright; "if you
    attack it" is the same exception arriving later, so each hold is kept
    and `c.end_effect` takes that one back when the caster declares an
    attack on its holder. The third exception names a zone the spec gives
    a ref for and no such zone is standing, so nobody is in it."""
    holds: dict[int, Any] = {}
    for foe in c.enemies():
        if c.marked(on=foe):
            continue
        held = c.cannot_attack(on=foe, against=c.me, until=When.EONT)
        if held is not None:
            holds[foe] = held

    def released(ev: AttackDeclared) -> None:
        if ev.attacker != c.me:
            return
        held = holds.pop(ev.target, None)
        if held is not None:
            c.end_effect(held, why="attacked by its holder")

    c.watch(AttackDeclared, released, until=When.EONT)


@power(
    "i3188x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3188x1(c: Cast) -> None:
    """`c.see_invisible` and `c.truesight` are different senses. The rest of
    the block is skill bonuses, which no fight reads."""
    c.darkvision()


@power(
    "i3188p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.kill()",),
)
def i3188p1(c: Cast) -> None:
    """The reckoning falls at the **second** turn ending the caster sees,
    because the row is used on his own turn and the first one is that
    turn's. Dropping below 1 hit point kills outright on the card; the
    damage is dealt and the outright death is the clause nothing says."""
    c.bonus("attack", 2, kind="item", on=c.me, until=When.EONT, once=True)
    c.bonus(
        "damage",
        4 + c.enhancement,
        kind="item",
        on=c.me,
        until=When.EONT,
        once=True,
    )
    killed: list[int] = []
    turns: list[int] = []

    def felled(ev: Dropped) -> None:
        if ev.source == c.me:
            killed.append(1)

    def reckon(ev: TurnEnd) -> None:
        if ev.actor != c.me or len(turns) >= 2:
            return
        turns.append(1)
        if len(turns) == 2 and not killed:
            c.flat(c.surge_value(), on=c.me)

    c.watch(Dropped, felled, until=When.ENCOUNTER)
    c.watch(TurnEnd, reckon, until=When.ENCOUNTER)


@power(
    "i3343x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.deals(dtypes=)",),
)
def i3343x1(c: Cast) -> None:
    """`c.deals` replaces one type with another; a blow that is both fire
    and necrotic at once is a shape the damage pipeline does not have."""


@power(
    "i3343p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    trigger="you hit with a m880a0 power using this ki focus",
    on=Trigger(Hit, _hit_with("m880a0"), "you hit with that power"),
)
def i3343p1(c: Cast) -> None:
    """The trigger is declared against the ref the spec prints. "Ongoing 5
    fire and necrotic damage" is one number of two types, which is one
    burn and one save. Paragon numbers are out of scope."""
    foe = _struck(c)
    if foe is None:
        return
    c.ongoing(5, dtypes=(DamageType.FIRE, DamageType.NECROTIC), on=foe)
    c.no_healing(on=foe, until=When.SAVE_ENDS)


@power(
    "i3489x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3489x1(c: Cast) -> None:
    """A drawback, and `AttackRolled` carries the die, so it is writable in
    full. Who does the dominating is not a field the condition keeps."""

    def malfunction(ev: AttackRolled) -> None:
        if ev.attacker == c.me and ev.natural == 1:
            c.condition(Condition.DOMINATED, on=c.me, until=When.EONT)

    c.watch(AttackRolled, malfunction, until=When.ENCOUNTER)


@power(
    "i3489p1",
    level=10,
    cls=ITEM,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
)
def i3489p1(c: Cast) -> None:
    """"The wand's level + 3" is 13 at level 10, printed as the page prints
    it. The free-action slide is armed as a watch on the caster's own turn
    start rather than offered as a row, because it is the same effect's
    second half and lasts exactly as long as the daze. Paragon dice are out
    of scope."""
    if not c.strike():
        return
    c.damage("2d6", dtype=DamageType.PSYCHIC)
    c.dazed(until=When.SAVE_ENDS)
    foe = c.target
    if foe is None:
        return

    def herd(ev: TurnStart) -> None:
        if ev.actor != c.me or not c.is_(Condition.DAZED, on=foe):
            return
        if c.may("slide the dazed target", who=c.me):
            c.slide(5, on=foe)

    c.watch(TurnStart, herd, until=When.ENCOUNTER)


@power(
    "i3553x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3553x1(c: Cast) -> None:
    """The ritual half is out of combat; the AC is a plain item bonus."""
    c.bonus(AC, 2, kind="item", on=c.me, until=When.ENCOUNTER)


@power(
    "i3553p1",
    level=10,
    cls=ITEM,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i3553p1(c: Cast) -> None:
    """Bright light, and nothing else."""


@power(
    "i3553p2",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you fail to sustain an arcane implement power you could sustain",
    todo=("c.sustain_free()",),
)
def i3553p2(c: Cast) -> None:
    """`c.on_sustain` is what happens when an effect *this row* made is
    sustained; sustaining somebody else's standing effect from outside it,
    and noticing that it was not sustained, are both absent."""


@power(
    "i3553p3",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you hit with an arcane implement attack and do not score a "
    "critical hit",
    on=Trigger(Hit, _arcane_noncrit_by_me, "you hit with an arcane power"),
)
def i3553p3(c: Cast) -> None:
    """`c.maximise` is the next damage rolled coming out maximum, which is
    the damage of the hit being answered: the free action lands between the
    hit and its damage roll."""
    c.maximise(on=c.me, until=When.EOT)


@power(
    "i3554x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3554x1(c: Cast) -> None:
    """The ritual half is out of combat. "Can also be used as a holy symbol
    implement" is `c.as_implement`."""
    c.as_implement(on=c.me)


@power(
    "i3554p1",
    level=10,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def i3554p1(c: Cast) -> None:
    """"As if it had spent a healing surge" costs the target no surge, so
    it is that creature's surge value healed."""
    if c.target is not None:
        c.heal(c.surge_value(of=c.target), on=c.target)


@power(
    "i3554p2",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=SELF,
    keywords=[Keyword.HEALING],
)
def i3554p2(c: Cast) -> None:
    c.heal(c.surge_value(), on=c.me)
    for mate in c.within(5, side="team"):
        c.heal(c.surge_value(of=mate), on=mate)


@power(
    "i3554p3",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    out_of_combat=True,
)
def i3554p3(c: Cast) -> None:
    """The printed Requirement is that it be used at the end of a rest, so
    the raising never happens inside an encounter. `c.reanimate` exists and
    is deliberately not called: a row that can only be used between fights
    has no combat consequence to audit."""


@power(
    "i509x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.deals(when=)", "c.treat_as_enemy()"),
)
def i509x1(c: Cast) -> None:
    """The necrotic half is written and over-applies: `c.deals` converts
    every blow rather than the ones the wielder chooses, and it cannot add
    the keyword to the spell it converts. The drawback -- treating your own
    allies as enemies -- has no verb: nothing moves a creature between
    sides for the length of a turn."""
    c.deals(DamageType.NECROTIC, until=When.ENCOUNTER, on=c.me, implement=True)


@power(
    "i509p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.SUMMONING],
    trigger="you drop a Small or Medium enemy with an implement attack",
    on=Trigger(Dropped, _my_small_kill, "you drop a small or medium enemy"),
    todo=("etl.item.inline_block()",),
)
def i509p1(c: Cast) -> None:
    """The trigger is declarable -- `Dropped` carries the killer and
    `Position` carries the victim's footprint -- but the creature is not.
    `dsl.Summon` and `c.summon_inline` are complete; what is missing is
    the block itself: `etl/item.py` truncates an item's text at its
    second `<h1>`, which on this page is the summoned creature's stat
    block, so no number of it reaches the spec and writing one would be
    inventing it."""


@power(
    "i683x1",
    level=10,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i683x1(c: Cast) -> None:
    """`Hit` is announced once per target, so "at least three targets with
    one power" is counted per ref rather than read off a list -- `Hit` has
    no `targets`. "You gain combat advantage" names nobody, so it is laid
    against every enemy and spent on the first swing."""
    tally: dict[str, int] = {}

    def counted(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        if _reach_of(ev.power) not in ("close_blast", "close_burst"):
            return
        tally[ev.power] = tally.get(ev.power, 0) + 1
        if tally[ev.power] != 3:
            return
        for foe in c.enemies():
            c.grants_advantage(on=foe, until=When.EONT, to="me", once=True)

    c.watch(Hit, counted, until=When.ENCOUNTER)


@power(
    "i683p1",
    level=10,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use an arcane close blast attack power through this staff",
    todo=("c.reshape_area()",),
)
def i683p1(c: Cast) -> None:
    """Turning a close blast into a smaller close burst changes the shape a
    declared power covers, and a row's reach is header data nothing
    rewrites at use time."""
