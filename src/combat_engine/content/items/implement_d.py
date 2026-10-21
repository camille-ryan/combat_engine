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
approximated: `c.kill()` and `c.darkvision()`. `c.reshape_area()` was on
that list and landed on #614 -- `i2467p1` and `i683p1` both call it.
"Ongoing 5 fire **and** necrotic damage" is one number of two types and
not two numbers, and `c.ongoing(dtypes=)` is it.

`c.no_teleport()` was on that list and was never the gap: "cannot use
teleportation powers" is `c.forbid(keyword=Keyword.TELEPORTATION)`, and
what remains unsayable is only being another power's *target*.

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
    ANY_FACE,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    EVERY_DIE,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
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
    Gear,
    Hit,
    Initiative,
    Keyword,
    Melee,
    Moved,
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
from combat_engine.engine.events import WeaponHeld

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
)
def i3166p1(c: Cast) -> None:
    """Bright light out to 4 squares, until extinguished or let go of.

    **"Bright light in a radius is the lamp case: no combat consequence of
    its own" was the reason and it stopped being true** -- bright light
    removes the concealment a dark square confers, which is a real
    consequence on any board that has one. #686.

    "Until you extinguish it as a minor action" is `c.endable`.

    **"Or until you are no longer holding it" is written now, and the old
    note named the wrong event.** `Dropped` is indeed a creature falling
    over; the moment wanted is `WeaponHeld`, which says that what is in a
    hand changed and carries `drawn=False` for putting away. This item sits
    in the implement slot, and an implement is a `Weapon` in `Gear` with
    `group == "implement"`, so `Gear.implement` is the thing in hand.

    The ref is **snapshotted at arming**, not read inside the handler: by
    the time the stow is announced `Gear.implement` already answers
    something else, or nothing.

    Two soft edges, stated rather than papered over. Nothing records that
    *this* item is the implement being held -- only that it occupies the
    implement slot -- so a character carrying two implements would have
    either of them end the light. And the holder the audit board deals has
    no implement in `Gear` at all, so the watch is not armed there: the
    light is what that board exercises, and the letting-go was measured by
    hand through `c.stow` instead.
    """
    held = c.light(4, on=c.me, until=When.ENCOUNTER)
    if held is None:
        return
    c.endable(held, ActionType.MINOR)
    gear = c.world.get(c.me, Gear)
    arm = gear.implement if gear is not None else None
    if arm is None:
        return
    mine, ref, light = c.me, arm.ref, held

    def let_go(ev: WeaponHeld) -> None:
        if ev.actor == mine and ev.ref == ref and not ev.drawn:
            c.end_effect(light, why="no longer held")

    c.watch(WeaponHeld, let_go, until=When.ENCOUNTER, on=c.me, label=c.ref)


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
    dropped=("c.death_save_failure()",),
)
def i3180x1(c: Cast) -> None:
    """A reroll of the whole damage roll, bought with a death saving throw
    failure.

    **The reroll half is written.** `c.reroll_ones(below=ANY_FACE,
    pick=EVERY_DIE)` is it -- five symbols were filed for this mechanism
    across eight rows and one line was in the way, `_rolled_pick`'s
    `floor > faces` guard copied from the looping case. #703.
    `c.reroll_damage` was never the verb: it keeps the higher of two whole
    rolls and this card makes you keep the new result whatever it is.

    **The price is still missing and is the whole of what is left.** "If you
    make the reroll, you are considered to have failed a death saving
    throw", counted against the three since the last rest -- and nothing
    counts those. So the row is `dropped=` on that alone, where it used to
    be `todo=` on both and refused in play: the reroll is a real benefit and
    withholding it because the cost is unsayable makes the item worse than
    the card rather than merely incomplete.

    **That direction matters and it is the wrong one to err in**, so it is
    said out loud: an item whose benefit lands and whose cost does not is
    stronger than printed. It is kept this way because the alternative --
    refusing the row -- was the state it was in, and `blocked.py` counted it
    as unstarted work when seven eighths of it was writable."""
    c.reroll_ones(below=ANY_FACE, pick=EVERY_DIE, on=c.me,
                  until=When.ENCOUNTER)


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
    keywords=[Keyword.AUGMENTABLE],
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
)
def i1977p1(c: Cast) -> None:
    """**"Your attacks" is narrowed now, and both halves changed to do it.**

    The old row stripped each enemy's resistance with a negative
    `c.resist(on=foe)` and laid an ungated `c.vulnerable`, which is a
    different sentence: it took the resistance away from everybody, so an
    ally swinging in the same round got the swap too. The note blamed the
    damage context for carrying no attacker, which has not been true since
    #302.

    `c.ignore_resistance` is the printed sentence -- its own docstring names
    `c.resist(-n, on=foe)` as the other one -- and it is a property of the
    *attacker*, so it needs no gate at all. The vulnerability has to stay on
    the target, since that is who carries a save-ends-style hold, so it is
    scoped on `source`: a gated `c.vulnerable` is kept as a triple and read
    in `resolve.deal_damage` beside immunity and resistance.

    `c.resistances` is still what says *which* types to lay it on -- the
    card only pays where there was resistance to reverse. Paragon numbers
    are out of scope.
    """
    me = c.me

    def mine(ctx: dict[str, Any]) -> bool:
        return ctx.get("source") == me

    c.ignore_resistance(on=me, until=When.EONT)
    for foe in c.enemies():
        for dtype, amount in c.resistances(on=foe).items():
            if amount > 0:
                c.vulnerable(5, dtype, on=foe, until=When.EONT, when=mine)


@power(
    "i2015p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def i2015p1(c: Cast) -> None:
    """Unseen by whoever is more than 5 squares off, re-asked as they move.

    **Re-aimed off `c.invisible(when=)`, which was never the shape.** The
    old note here said the clause needed a gate re-asked at every look. It
    does not, and `m1653a3` (`monsters/level_02/lurkers_sa.py`) is the
    worked case: `c.invisible(to=)` holds a `HIDDEN_FROM` relation *per
    watcher*, so this is one relation laid when a creature is far enough
    off and taken away when it is not. The per-watcher `held` is kept for
    that reason -- ending the whole label would un-hide the caster from
    everybody still at range.

    **`Moved` and not `MoveEnd`, which is where this differs from the
    obvious reading.** `MoveEnd` is the event a row answering "an adjacent
    enemy shifts" wants, but `movement.forced` emits none -- it steps the
    victim and announces `ForcedMove` and `Moved`, and never reaches the
    `MoveEnd` that `walk`, `shift` and `teleport` each emit. So a shove
    into range would have left the caster hidden from a creature standing
    next to it. `Moved` fires once per square for every kind of going, so
    the recheck costs more and is asked of every move there is.

    The asymmetry is the other half: when the caster moves, every enemy's
    distance changed; when anybody else does, only that one's did -- and it
    is rechecked only if it is an enemy, since the relation is laid against
    enemies alone."""
    me, ref = c.me, c.ref
    held: dict[int, Any] = {}

    def recheck(who: int) -> None:
        if c.distance(who) > 5:
            if who not in held:
                eff = c.invisible(to=who, on=me, until=When.EONT)
                if eff is not None:
                    held[who] = eff
            return
        eff = held.pop(who, None)
        if eff is not None:
            c.end_effect(eff, on=me)

    def stepped(ev: Moved) -> None:
        foes = c.enemies()
        if ev.actor == me:
            for foe in foes:
                recheck(foe)
        elif ev.actor in foes:
            recheck(ev.actor)

    for foe in c.enemies():
        recheck(foe)
    c.watch(Moved, stepped, until=When.EONT, on=me, label=ref)


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
)
def i2303p1(c: Cast) -> None:
    """The gate is written, and the old note's premise was false.

    It read "nothing asks the world who has attacked whom since when", and
    **the bus log has kept it all along**: every event of the fight with a
    monotonic `seq`, and `TurnEnd` carrying the actor, so "since the end of
    your last turn" is a boundary rather than a history somebody has to
    remember. `query.attacked_since` is that read and `#757` is where the
    other row with the same premise is written.

    `c.attacked_me_since` and not the property beside this one, which keeps
    its own set of recent attackers in a closure -- correct for itself and
    unreadable from here, which is what the note was right about.

    `AttackDeclared`, so a **miss** counts: the card says "a target that
    has attacked you", and whether the swing landed is not part of it."""
    foe = _struck(c)
    if foe is not None and c.attacked_me_since(foe):
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
)
def i2895x1(c: Cast) -> None:
    """A force power sent through this tome may attack Fortitude instead of
    Reflex.

    `from_=REF` is the printed narrowing and is load-bearing: without it the
    swap would move a power that declared AC, which the card never mentions.
    The keyword gate is asked per attack, because the tome is held rather
    than worn and can be put down. #509.
    """
    c.attacks_defence(
        FORT, from_=REF, on=c.me, until=When.ENCOUNTER,
        # `keywords_of` takes the Power, not its ref -- and reads the
        # keywords *for this creature*, which is what picks up a keyword a
        # feat declared rather than only the printed ones.
        when=lambda ctx: Keyword.FORCE in c.keywords_of(
            get(str(ctx.get("power") or ""))
        ),
    )


@power(
    "i2895p1",
    level=9,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def i2895p1(c: Cast) -> None:
    """"The powers contained in the tome" is a set the card names by
    description rather than by ref, which is exactly what `c.borrow_row`
    reads off the registry and records the pick of -- wizard dailies with
    the force keyword, of a level the tome's own level allows, highest
    first.

    **The price is charged now.** The marker said "`c.expend_row` takes
    one ref rather than a set", which was true and was not the gap:
    `implement_c._spend_unused` had read the set off the bearer's own
    `Powers.all` since `i744p1` was written (it still does, for the two
    rows that grant a *named* power rather than borrowing from a set). `c.unspent` is where that
    read lives now and `implement_b._tome_trade` is the whole sentence,
    which matters most on this row of the seven: the tome is level 9 and
    the ladder is walked downwards, so charging at the tome's rung instead
    of the lent card's refused the most uses here."""
    from combat_engine.content.items.implement_b import _tome_trade

    _tome_trade(c, _item_level(c), Keyword.FORCE)


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
    on=HIT_BY_ME,
    dropped=("c.untargetable(keyword=)",),
)
def i2908p1(c: Cast) -> None:
    """Barring a whole keyword *is* said: `c.forbid(keyword=)` refuses every
    row the creature has that carries the keyword, which is the first half
    of the printed line.

    The second half is a different sentence and is still missing -- being
    the *target* of somebody else's teleportation power. `c.forbid` takes
    rows away from the creature it sits on, so it cannot refuse an ally's
    power that names this creature."""
    foe = _struck(c)
    if foe is None:
        return
    c.forbid(keyword=Keyword.TELEPORTATION, on=foe, until=When.SAVE_ENDS)


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
)
def i1093p1(c: Cast) -> None:
    """The trigger is declared against the ref the spec prints.

    **The damage bonus is narrowed now, and it was paying against
    everything.** The card gives "a power bonus to damage rolls **using beast
    form powers** through this totem equal to the totem's enhancement
    bonus", and the bonus was laid unconditionally -- so every attack the
    character made while the totem was live got it, not only the beast form
    ones. That is the direction of error this component's notes keep warning
    about: a modifier too wide is a wrong number in every fight, where a
    modifier nothing consults is merely absent.

    `Keyword.BEAST_FORM` and the 67 headers declaring it are what make the
    gate writable; `_keywords_of` was already in this file for the identical
    job on three other items, so the clause is one lambda and no new helper.

    "While you are in beast form" is carried by the trigger and the duration
    rather than by a second gate: the row only fires on using `p5032`, which
    *is* assuming the form, and ends with the encounter. A character who
    leaves the form early keeps the bonus, which is the one way this is
    looser than the card -- `p16535`'s `name=` now makes that gateable and
    it is a separate sentence on a separate item.
    """
    c.resize(Size.LARGE, on=c.me, until=When.ENCOUNTER)
    c.bonus(
        "damage", c.enhancement, kind="power", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: Keyword.BEAST_FORM in _keywords_of(ctx.get("power")),
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
)
def i2467p1(c: Cast) -> None:
    """The next area burst through this wand becomes one square, and hits harder.

    Both halves are the same "next one" and have to end together, which is
    the whole shape of this row. `c.bonus(once=True)` already spends itself
    on the first roll it modifies; the reshape has to be told, because
    `dsl.area_of` is a **query** -- the renderer calls it to highlight
    squares and `_aimings` calls it once per candidate origin -- so a
    one-shot that ended on being *measured* would be gone before the power
    was ever used. It ends on the `PowerUsed` it was waiting for instead.

    `size=0` is one square: `area_of` returns 1 for an `area_burst` of size
    0 against 9 for size 1, checked rather than assumed. `replace` keeps
    `within`, which is the card's "(within the same range)" -- the distance
    the origin may be placed at is the power's and not the wand's, and that
    is why `c.reshape_area` takes a callable on the printed range rather
    than a replacement `Range`.

    Narrowed to `area_burst` because the card says so. A close burst
    through the same wand is untouched. #614.
    """
    from dataclasses import replace

    c.bonus(
        "attack", 2, kind="power", on=c.me, until=When.ENCOUNTER, once=True
    )
    held = c.reshape_area(
        lambda r: replace(r, size=0),
        kinds=("area_burst",),
        on=c.me,
        until=When.ENCOUNTER,
    )

    def spent(ev: Any) -> None:
        """End it on the use it was bought for, not on being measured."""
        if getattr(ev, "actor", None) != c.me:
            return
        row = get(getattr(ev, "power", ""))
        if row is None or row.reach_of().kind != "area_burst":
            return
        if held is not None:
            c.world.effects.end(held, "spent")

    c.watch(PowerUsed, spent, until=When.ENCOUNTER, on=c.me, label=c.ref)


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
)
def i2595p1(c: Cast) -> None:
    """"All fire damage dealt using this staff as an implement is acid
    damage" -- a swap, which is `from_=`.

    An override has no `from` to name, so this converted every blow rather
    than only the fire ones. #613 split that out as `c.recolour(from_, to)`
    and it did not need a second verb: naming the type being replaced is
    one argument, and leaving it unnamed is the unconditional override every
    other card of this family prints.

    "A free action returns the damage to normal" needed nothing either. It
    is `c.endable` over the effect, the same sentence seen from the other
    side: the effect is the caster's, so the drop is offered to the caster
    for a free action. `i2595p2` is this card the other way round, and
    because `c.deals` ends any standing retype before laying a new one,
    using one of the pair replaces the other -- which is what a staff with
    two free actions on it means.
    """
    c.endable(
        c.deals(DamageType.ACID, until=When.ENCOUNTER, on=c.me,
                implement=True, from_=DamageType.FIRE),
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
)
def i2595p2(c: Cast) -> None:
    """The same swap the other way; see `i2595p1`."""
    c.endable(
        c.deals(DamageType.FIRE, until=When.ENCOUNTER, on=c.me,
                implement=True, from_=DamageType.ACID),
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
    dropped=("c.heal_bonus()",),
)
def i3167p1(c: Cast) -> None:
    """"Choose one of the following benefits", and two of the three can now
    be said.

    **It is a choice and was not written as one.** The row used to do the
    first benefit unconditionally, because it was the only one sayable --
    which is a reasonable thing to do with one option and the wrong thing
    to do with two. `c.choose` is the card's own word.

    The reroll arrived with `c.reroll_attack(ev=)`: the benefit is armed a
    turn earlier and spent on a later roll, so it is a `c.watch`, and a
    watch handler sees the row's `c.trigger` rather than the roll it was
    handed. Narrowed exactly as printed -- **a miss**, with **a divine
    attack power**, **mine**, **once** -- and `When.EONT` is "before the end
    of your next turn".

    Still `dropped`: nothing maximises a heal. That is `c.heal_bonus()` and
    it is a different sentence from either of these.
    """
    def missed_divine(ev: Any) -> None:
        if getattr(ev, "attacker", None) != c.me:
            return
        row = get(getattr(ev, "power", ""))
        if row is None or Keyword.DIVINE not in row.keywords:
            return
        result = getattr(ev, "result", None)
        if result is None or getattr(result, "hit", True):
            return
        if c.may("reroll the attack, and keep the second result"):
            c.reroll_attack(ev=ev, keep="new")

    def saves() -> None:
        c.save(on=c.me)
        for mate in c.within(5, side="team"):
            c.save(on=mate)

    def bank_reroll() -> None:
        c.watch(AttackRolled, missed_divine, until=When.EONT, on=c.me,
                once=True, label=c.ref)

    picked = c.choose(["a saving throw for you and each ally within 5",
                       "a reroll of your next miss with a divine power"],
                      "which benefit")
    if picked is None or picked.startswith("a saving throw"):
        # The default is the first benefit, which is what the row did
        # before there was anything to choose between.
        saves()
    else:
        bank_reroll()


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
    dropped=("c.slay()",),
)
def i3188p1(c: Cast) -> None:
    """The reckoning falls at the **second** turn ending the caster sees,
    because the row is used on his own turn and the first one is that
    turn's.

    **The old marker was false: the tally it asked for is in this body.**
    It said nothing records whether the wielder killed anything, and the
    `Dropped` watcher below has been appending to `killed` the whole
    time -- an encounter-clocked watch on the row's own use, which is
    narrower and more exact than a general "did this creature kill this
    turn" reader would be. Nothing had to be written and nothing is owed
    for that clause.

    **What is still owed is the death, and `c.kill` does not cover it.**
    The card reads "if this damage drops you below 1 hit point, you die",
    and that is outright death at a threshold of 0. `c.kill` sets hit
    points to 0 and routes through `resolve._check_down`, which consults
    `Health.dying_at` -- negative for a character -- so it lays the dying
    conditions instead, and it refuses outright for a creature already at
    or below 0, which is exactly where the surge-value blow leaves one.
    Nothing in the surface drives a creature past `dying_at`, and a body
    writing `Health.hp` by hand would walk round the engine's one path
    out of zero. So the clause keeps a marker of its own.
    """
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
)
def i3343x1(c: Cast) -> None:
    """Written, and it is the card that argued for the two changes behind
    it. The clause is not a replacement in either direction: fire dealt by
    this implement **is also** necrotic, and necrotic **is also** fire. So
    each half is a `from_` naming the type that triggers it and a `dtypes`
    carrying both -- an addition rather than a swap, which is what the
    pair `(from_=FIRE, dtypes=(FIRE, NECROTIC))` says.

    **Two holds standing at once**, one per direction, which `c.deals`
    refused: it ended every `deals:` hold before laying a new one, so the
    second call silently cancelled the first and only necrotic-becomes-fire
    would have played. It now ends only a hold whose narrowings match, and
    these two narrow on different `from_`, so no blow can match both and
    neither cancels the other. `Cast._retyped` has skipped a non-covering
    hold rather than stopping the search since it was written, precisely
    for this.

    `implement=True` because the thing is an implement, not a weapon; the
    card says "attacks using this"."""
    c.deals(
        dtypes=(DamageType.FIRE, DamageType.NECROTIC),
        from_=DamageType.FIRE, implement=True,
        on=c.me, until=When.ENCOUNTER,
    )
    c.deals(
        dtypes=(DamageType.NECROTIC, DamageType.FIRE),
        from_=DamageType.NECROTIC, implement=True,
        on=c.me, until=When.ENCOUNTER,
    )


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
)
def i3553p1(c: Cast) -> None:
    """Bright light out to 10 squares.

    **"Bright light, and nothing else" was the whole docstring and it
    stopped being true** (#686). The simplest row of the family: one call,
    no choice, no clock beyond the encounter."""
    c.light(10, on=c.me, until=When.ENCOUNTER)


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
    dropped=("c.deals(chosen=)", "c.treat_as_enemy()"),
)
def i509x1(c: Cast) -> None:
    """The necrotic half is written and over-applies: `c.deals` converts
    every blow rather than the ones the wielder chooses, and it cannot add
    the keyword to the spell it converts. Both of those are the one missing
    facility -- an opt-in recolour that also writes a keyword -- rather than
    the gate the old symbol named. #613.

    The drawback -- treating your own allies as enemies -- has no verb:
    nothing moves a creature between sides for the length of a turn."""
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
    defect="the summoned block's defences are zeroes and the entry prints "
           "no derivation for them anywhere",
)
def i509p1(c: Cast) -> None:
    """The trigger is declarable -- `Dropped` carries the killer and
    `Position` carries the victim's footprint -- but the creature is not,
    and it never will be from this source.

    **Two markers were wrong before this one, and the second was mine.**
    `etl.item.inline_block()` was right until that gap closed (#601): the
    block *is* imported now, as `m509c0`. I then re-pointed it at
    `etl.monster.derived_block()` on the reasoning that this block states
    its numbers as expressions in the conjurer's, so it belongs in the
    associate table -- the 89th member of the family `spawn_associate`
    exists for. #603.

    **That was a guess about the text and the text disagrees.** The
    associate table's shape does fit, and its readers find nothing to put
    in it: run over this entry, `_AS_HP` yields `0`, `_AS_ABS` yields
    `(0, 0, 0, 0)`, and `_AS_REL` -- the one that reads "Defenses your
    defenses + 2" -- finds **nothing**. Searched both `Txt` and
    `PlainTxt` for the phrase outright:

        'your bloodied value'  PRESENT
        'as conjurer'          PRESENT
        'your defenses'        absent
        'your defences'        absent
        'equal to yours'       absent

    So the hit points *are* recoverable and the defences are not printed at
    all. That is `defect=` in its exact sense -- the compendium is missing
    what the row would be written from -- and no table can hold a
    derivation the source does not state.

    **This drops the whole item**, which is Camille's rule of 2026-10-15
    and worth saying out loud: a level-10 rare tome leaves the game over a
    summoned creature's defences. `i509x1`, its other block, was already
    unfinished on two verbs of its own.
    """


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
)
def i683p1(c: Cast) -> None:
    """The blast becomes a burst two squares smaller, minimum 1.

    **"A row's reach is header data nothing rewrites at use time" was the
    hold and #614 answered it.** `c.reshape_area` lays the new shape on the
    creature and `dsl.reach_of` resolves it per caster per use, so the
    printed line stays the print and this staff's wielder throws a burst.
    `i2467p1` is the shape this follows and sits in this file.

    **`into` derives the burst from the blast it replaces**, which is why
    `c.reshape_area` takes a callable: the card prints "2 squares smaller
    than the blast", so the number belongs to whichever power is thrown and
    cannot be a literal. `from_` is carried across for the same reason --
    a blast measured from somewhere other than the caster stays measured
    from there.

    **No `on=Trigger`, and the printed Trigger line is why this is the
    honest shape rather than the literal one.** Targets and the area are
    chosen in `dsl.use` *before* `cast.used()` announces `PowerUsed`
    (dsl.py:3517-3566), so a reshape laid in answer to that event would
    reach the blast after it had already been aimed -- the next one, not
    this one. A free action with no declared trigger is on the action menu,
    because `dsl.usable`'s trait gate reads `p.triggers` and not the prose
    (dsl.py:2932); so the wielder spends the staff and then throws, which
    arrives at the printed shape one declaration earlier than the card
    words it.

    **Replacing, not `optional=True`.** The eleven rows that offer a second
    aiming print "you can choose X instead of Y" and must keep both; here
    the activation *is* the choice, so forcing it for that one attack is
    right. `drivers.offered_aiming` names `i2467p1` for exactly this.

    It ends on the use it was bought for rather than on being measured:
    `dsl.area_of` is a query the renderer and `_aimings` both call, so a
    one-shot would be gone before the power was thrown."""
    held = c.reshape_area(
        lambda r: CloseBurst(max(r.size - 2, 1), from_=r.from_),
        kinds=("close_blast",),
        keyword=Keyword.ARCANE,
        on=c.me,
        until=When.ENCOUNTER,
    )

    def spent(ev: Any) -> None:
        if getattr(ev, "actor", None) != c.me:
            return
        row = get(getattr(ev, "power", ""))
        # The printed line, so still a blast: `Power.reach_of` answers the
        # header and only `dsl.reach_of` sees the reshape.
        if row is None or row.reach_of().kind != "close_blast":
            return
        if Keyword.ARCANE not in row.keywords:
            return
        if held is not None:
            c.world.effects.end(held, "spent")

    c.watch(PowerUsed, spent, until=When.ENCOUNTER, on=c.me, label=c.ref)
