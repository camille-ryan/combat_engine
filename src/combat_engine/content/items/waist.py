"""Waist-, ring- and ammunition-slot magic items, heroic tier.

Nothing here declares an item. The level, the price, the slot, the ladder
and the enhancement bonus are columns in `game.db` and are laid on by
`engine/equipment.py` -- which writes a worn item's modifiers straight into
`Mods` so they survive the end of a fight. What is written here is only the
part that needs a body, and a property's *own* bonus is an ordinary
`c.bonus` with an encounter duration, because a trait is re-armed at the
start of every fight.

Four judgements run through the file.

* **Ammunition is drawn and spent by `engine/ammunition`.** A piece goes
  from `Gear.quiver` when a ranged weapon attack is declared and the
  item's ref rides all four attack events, so `_ammo_hit` is the cheap
  filter -- a shot of mine that drew *something* -- and `c.ammunition()`
  in the body is the exact one, because only the body knows which item
  its row belongs to. Each declares `no_provoke=True`: the rider needs a
  ranged reach to name the creature that was shot, and without it every
  such rider opened a second opportunity window for the one shot.
* **A property that answers a printed trigger is `action=ActionType.NONE`
  with the trigger declared**, not a trait holding a `c.watch`. The
  dispatcher costs nothing for a no-action row and `Triggers._at` aims a
  single-target enemy row answering your own `Hit` at the creature you hit,
  which is what "that enemy" means. A trait is kept for the properties that
  are standing modifiers, and for the two that are both.
* **A saving throw and a skill check are announced before they are acted
  on**, so "+2 to the saving throw" and "treat the check as a natural 20"
  are written onto the event. `SavingThrow` carries no damage type, so
  "against ongoing *poison*" cannot be told from any other save.
* **A healing surge value is a quarter of maximum hit points plus
  modifiers**, read through `query.surge_value`. A card raising one is
  `c.bonus("surge_value", n)` like any other standing number.
* **A defence is read again once an interrupt window closes**, so "use X in
  place of your Fortitude" is the difference between the two written as a
  modifier to Fortitude, gated on the one attacker. `AttackRolled.defence`
  is the Fortitude the attack was actually measured against, so the
  difference is exact rather than recomputed without the attack's context.

Paragon and epic lines (`Level 11:`, `Level 15 or 20:`) are out of scope;
the heroic number is the one written.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
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
    CloseBurst,
    Condition,
    DamageRolled,
    DamageType,
    Defense,
    ForcedMove,
    Health,
    Hit,
    Ident,
    InitiativeRolled,
    Keyword,
    Melee,
    Miss,
    Position,
    Ranged,
    SavingThrow,
    SkillCheck,
    Square,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    When,
    Window,
    World,
    both,
    by_me,
    by_melee,
    by_ranged,
    get,
    my_check,
    power,
    spread,
    targets_me,
    would_hit_me,
)

ITEM = "item"


# -- shared reading of the board --------------------------------------------


def _free_near(c: Cast, of: int) -> Square | None:
    """An unoccupied square beside somebody, for a "to" clause."""
    pos = c.world.get(of, Position)
    if pos is None:
        return None
    for sq in sorted(spread({pos.square}, 1)):
        if sq != pos.square and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _boost_save(c: Cast, amount: int) -> bool:
    """Add to the saving throw being answered, and read the outcome back.

    `c.reroll_save` is the only saving-throw verb and it replaces the die;
    a printed "+2 bonus to the saving throw" wants the die kept. The event
    is announced before it is acted on, so the total is rewritten here the
    way `SkillCheck` is rewritten by `c.boost_check`.
    """
    ev = c.trigger
    if not isinstance(ev, SavingThrow):
        return False
    ev.bonus += amount
    ev.saved = ev.natural + ev.bonus >= 10
    return True


def _weapon_damage(ctx: dict[str, Any]) -> bool:
    """Gate: this damage came from a weapon power."""
    row = get(ctx.get("power") or "")
    return row is not None and Keyword.WEAPON in row.keywords


def _typed_nonweapon(ctx: dict[str, Any]) -> bool:
    """Gate: typed damage from something that is not a weapon attack."""
    if ctx.get("dtype") in (None, DamageType.UNTYPED):
        return False
    row = get(ctx.get("power") or "")
    return row is None or Keyword.WEAPON not in row.keywords


def _poison_save(ctx: dict[str, Any]) -> bool:
    """Gate: the effect this save is against is ongoing poison damage."""
    return ctx.get("dtype") is DamageType.POISON


def _took_typed_nonweapon(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    if getattr(ev, "dtype", DamageType.UNTYPED) is DamageType.UNTYPED:
        return False
    row = get(getattr(ev, "detail", "") or "")
    return row is None or Keyword.WEAPON not in row.keywords


def _hurt_by_enemy(world: World, me: int, ev: Any) -> bool:
    from combat_engine.engine import query

    who = getattr(ev, "source", None)
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and who is not None
        and who != me
        and query.team(world, who) is not query.team(world, me)
    )


def _would_drop_me(world: World, me: int, ev: Any) -> bool:
    """This blow, as rolled, takes me to 0 hit points or fewer."""
    health = world.get(me, Health)
    return (
        getattr(ev, "target", None) == me
        and health is not None
        and health.hp - getattr(ev, "amount", 0) <= 0
    )


def _my_poison(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "dtype", None) is DamageType.POISON
    )


def _natural_20_initiative(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "actor", None) == me and getattr(ev, "rolled", 0) == 20


def _ammo_hit(world: World, me: int, ev: Any) -> bool:
    """A ranged attack of mine that drew a piece of magic ammunition.

    Loose on purpose: the dispatcher hands a predicate `(world, me, ev)`
    and never the ref of the row being offered, so *which* quiver the
    shot came out of cannot be asked here. `c.ammunition()` asks it in
    the body, where the row knows what item it is -- so this is the
    cheap filter and that is the exact one, and a wielder carrying two
    kinds of magic arrow has each property answering only its own.
    """
    return (
        by_me(world, me, ev)
        and by_ranged(world, me, ev)
        and bool(getattr(ev, "ammo", ""))
    )


def _at_target(foe: int) -> Any:
    """Gate a modifier on which creature is being attacked."""

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == foe

    return gate


#: Minion-ness by stat-block ref. `load` goes to sqlite every call and these
#: are read from a modifier gate, which is once per defence.
_MINION: dict[str, bool] = {}


def _minion(c: Cast, who: int | None) -> bool:
    """Is that creature a minion?

    `c.is_kind` reads the `keywords`, `kind` and `origin` columns and
    minion-ness is none of those -- it is its own column, and 383 stat
    blocks carry it while only some of them also print it as their role.
    So the block is read the way `c.kinds_of` reads one.
    """
    ident = c.world.get(who, Ident) if who is not None else None
    ref = ident.ref if ident is not None else ""
    if not ref.startswith("m"):
        return False
    if ref not in _MINION:
        from combat_engine.content.loader import load

        try:
            _MINION[ref] = bool(load(ref).row["minion"])
        except Exception:  # a ref with no stat block is nobody's minion
            _MINION[ref] = False
    return _MINION[ref]


def _flanker_hits_me(world: World, me: int, ev: Any) -> bool:
    from combat_engine.engine import query

    foe = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and foe is not None
        and query.flanked_by(world, me, foe)
    )


def _ongoing_poison_save(world: World, me: int, ev: Any) -> bool:
    """A save against ongoing poison damage.

    `SavingThrow.against` is `str(effect)`, and an effect carrying a burn
    prints "ongoing N <type>" inside it -- so the damage type is on the
    event after all, spelled rather than typed.
    """
    against = getattr(ev, "against", "")
    return (
        getattr(ev, "actor", None) == me
        and "ongoing" in against
        and DamageType.POISON.value in against
    )


def _would_hit_my_fort(world: World, me: int, ev: Any) -> bool:
    result = getattr(ev, "result", None)
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "vs", None) is Defense.FORT
        and bool(result and result.hit)
    )


def _stand_in_for_fort(c: Cast, value: int) -> None:
    """Put `value` in place of Fortitude for the attack being interrupted.

    The defence is re-read once this window closes, so the swap is the
    difference written as a modifier -- gated on the one attacker and gone
    at the end of the turn, because a modifier is the only thing that
    reaches the second reading. Untyped: the card prints no bonus at all.
    """
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    was = getattr(ev, "defence", None)
    if foe is None or was is None:
        return
    c.bonus(FORT, value - was, on=c.me, until=When.EOT,
            when=lambda ctx: ctx.get("attacker") == foe)


def _plus(c: Cast) -> int:
    """The item's enhancement, never below 1: "1d6 per plus" on a piece of
    ammunition whose plus has been decayed away still rolls something."""
    return max(1, c.enhancement)


# == waist ==================================================================


@power("i650x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.aid_another()",))
def i650x1(c: Cast) -> None:
    """The bonus rides on somebody *else's* Heal check and only when that
    check is aimed at me. `SkillCheck` carries `actor`, `skill` and `dc` and
    nothing about who is being helped, and aiding another is not an action
    the engine has -- which is the eight-row gap this joins."""


@power("i1897x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1897x1(c: Cast) -> None:
    """Carrying capacity: normal load, heavy load and drag load are not
    weighed anywhere on a board."""


@power("i2131x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Keyword.RAGE",))
def i2131x1(c: Cast) -> None:
    """A death save is an ordinary `SavingThrow` with `against="death"`,
    announced before it is read back, so the bonus is written onto it.
    `once=True` is the printed "first". A rage is held as an effect like any
    other and `keywords_of` reads the laying row's keywords, so "while
    raging" wants the keyword the rage rows have no word for; without it the
    bonus is paid whatever the wearer was doing."""

    def death_save(ev: SavingThrow) -> None:
        if ev.actor != c.me or ev.against != "death":
            return
        ev.bonus += 4
        ev.saved = ev.natural + ev.bonus >= 10

    c.watch(SavingThrow, death_save, until=When.ENCOUNTER, once=True)


@power("i654x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i654x1(c: Cast) -> None:
    """`query.surge_value` reads `Mods.total`. Paragon steps are out of
    scope; this is the heroic +1."""
    c.bonus("surge_value", 1, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i3523x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.class_feature()",))
def i3523x1(c: Cast) -> None:
    """The regeneration this raises belongs to a class feature the card
    names in prose, of a class the importer never brought in -- no `cf:`
    ref in the card and no row behind one. Even given both, `c.regeneration`
    lays a second, separate heal rather than adding to the feature's."""


@power("i640x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("TempHP.power",))
def i640x1(c: Cast) -> None:
    """`cf:barbarian-f1s0` is a ref the card prints and no row carries:
    `cf:barbarian-f1` writes that option inline, on its `rageblood` leg,
    and the temporary hit points come off a `Dropped` handler there.

    Even with a row it would not be enough. `TempHP` carries a source, a
    target and an amount and no power, so a pool this feature laid cannot
    be told from any other, and temporary hit points do not add -- a
    second, larger pool laid from here would replace rather than raise."""


@power("i657x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.as_weapon()",))
def i657x1(c: Cast) -> None:
    """An improvised or unarmed attack is not a `Weapon`, so nothing can be
    told to count as a club."""


@power("i2993x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2993x1(c: Cast) -> None:
    c.resist(5, DamageType.POISON, on=c.me, until=When.ENCOUNTER)


@power("i2993p1", level=4, cls=ITEM, usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you make a saving throw against ongoing poison damage",
       on=Trigger(SavingThrow, _ongoing_poison_save,
                  "you make a saving throw against ongoing poison damage"))
def i2993p1(c: Cast) -> None:
    """"No action" is `ActionType.NONE` with the trigger declared. The save
    *can* be told to be against ongoing poison: `against` is the effect
    rendered, and an effect carrying a burn spells its amount and type
    inside that string."""
    _boost_save(c, 2)


@power("i1415x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bull_rush()",))
def i1415x1(c: Cast) -> None:
    """A bull rush is not its own action here, so the extra square is paid
    on every push the wearer makes rather than on that one manoeuvre."""
    c.forces(1, on=c.me, until=When.ENCOUNTER,
             when=lambda ctx: ctx.get("how") == "push")


@power("i1657p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1657p1(c: Cast) -> None:
    """"Weapon damage" is not a damage type; it is damage from a power with
    the weapon keyword, which the damage context can be asked about."""
    c.resist(5, on=c.me, until=When.EONT, when=_weapon_damage)


@power("i600x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i600x1(c: Cast) -> None:
    """"Grabbing you" is the relation read from the grabber's side:
    `c.grabbing(of=foe)` is everything that foe holds."""

    def mine(ev: TurnStart) -> None:
        if ev.actor != c.me:
            return
        for foe in c.enemies():
            if c.me in c.grabbing(of=foe):
                c.damage("1d8", on=foe)

    c.watch(TurnStart, mine, until=When.ENCOUNTER)


@power("i2659x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2659x1(c: Cast) -> None:
    def crit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.critical:
            c.temp_hp(c.con_mod, on=c.me)

    c.watch(Hit, crit, until=When.ENCOUNTER)


@power("i467x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i467x1(c: Cast) -> None:
    """Storage. Consumables are not carried as objects, so stowing one is a
    line about the pack rather than about the fight."""


@power("i467p1", level=6, cls=ITEM, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.consume_item()",))
def i467p1(c: Cast) -> None:
    """The second wind half is reachable; the stowed alchemical item is the
    whole benefit and there is no consumable to spend."""


@power("i594x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you roll a 20 on your initiative check",
       on=Trigger(InitiativeRolled, _natural_20_initiative,
                  "you roll a 20 on initiative"))
def i594x1(c: Cast) -> None:
    """Declared rather than armed as a plain trait: traits are armed *after*
    initiative is rolled, so a `c.watch(InitiativeRolled)` laid by one would
    never hear the opening roll. The action is banked on the first turn
    rather than now, because the budget it goes into is the turn's."""

    def first_turn(ev: TurnStart) -> None:
        if ev.actor == c.me:
            c.extra_action(MOVE, on=c.me)

    c.watch(TurnStart, first_turn, until=When.ENCOUNTER, once=True)


@power("i639x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i639x1(c: Cast) -> None:
    c.bonus("skill:endurance", 2, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i639p1", level=6, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="before you make an Endurance check",
       on=Trigger(SkillCheck, my_check("endurance"),
                  "you make an Endurance check"))
def i639p1(c: Cast) -> None:
    """"As though you rolled a natural 20" is the die raised to 20, which
    `c.boost_check` says by adding the difference -- the bonus half of the
    check is kept, which is what treating the *roll* as a 20 means."""
    ev = c.trigger
    if isinstance(ev, SkillCheck):
        c.boost_check(max(0, 20 - ev.natural))


@power("i652x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i652x1(c: Cast) -> None:
    """Gated rather than applied: the resistance is only in force below 0,
    and the gate is read as each blow lands."""

    def down(ctx: dict[str, Any]) -> bool:
        health = c.world.get(c.me, Health)
        return health is not None and health.hp <= 0

    c.resist(10, on=c.me, until=When.ENCOUNTER, when=down)


@power("i652p1", level=6, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you would be reduced to 0 hit points by an attack",
       on=Trigger(DamageRolled, _would_drop_me,
                  "an attack would drop you"))
def i652p1(c: Cast) -> None:
    """Answered on `DamageRolled`, where the number is known and the hit
    points have not gone yet, so "the same amount of damage that you took"
    is the rolled amount."""
    ev = c.trigger
    foe = getattr(ev, "source", None)
    if foe is not None:
        c.flat(getattr(ev, "amount", 0), on=foe)


@power("i658p1", level=6, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=Melee(1), target=ONE_CREATURE,
       trigger="a flanking enemy makes an attack roll against you",
       on=Trigger(AttackDeclared, _flanker_hits_me,
                  "a flanking enemy attacks you"))
def i658p1(c: Cast) -> None:
    """`query.flanked_by` is the printed gate, asked of the attacker rather
    than of the attack; the slide is to a named square, which is what "to a
    square adjacent to you" is."""
    foe = c.target
    sq = _free_near(c, of=c.me)
    if foe is not None and sq is not None:
        c.slide(2, on=foe, to=sq)


@power("i875x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i875x1(c: Cast) -> None:
    """Which ability a skill check is rolled off is fixed in `skills`, and
    the whole printed benefit is that swap."""


@power("i2355x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2355x1(c: Cast) -> None:
    """Prone carries `attack=-2` in the condition rules, and nothing lifts
    part of a condition -- so the penalty is cancelled by an untyped +2 that
    is only in force while prone. The card prints no bonus type because it
    prints no bonus at all."""
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_(Condition.PRONE, on=c.me))


@power("i3255x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3255x1(c: Cast) -> None:
    """Both halves are narrative: a skill bonus against one race, which is
    not a thing a creature carries, and a language."""


@power("i3255p1", level=7, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an attack pushes, pulls, or slides you",
       on=Trigger(ForcedMove, targets_me, "you are pushed, pulled or slid"))
def i3255p1(c: Cast) -> None:
    """The square is taken off the move being interrupted rather than laid
    as a standing `c.resist_forced`: the shove reads its modifier before
    this window opens, so a modifier laid here would shorten the *next*
    one."""
    ev = c.trigger
    if isinstance(ev, ForcedMove):
        ev.squares = max(0, ev.squares - 1)


@power("i3255p2", level=7, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you take ongoing poison damage from an attack",
       on=Trigger(DamageRolled, _my_poison, "you take poison damage"))
def i3255p2(c: Cast) -> None:
    c.save(on=c.me, against="ongoing")


@power("i3491p1", level=7, cls=ITEM, action=MOVE,
       reach=PERSONAL, target=SELF, dropped=("c.collide()",))
def i3491p1(c: Cast) -> None:
    """Two dice rather than one `2d10`, because the malfunction reads each
    of them. The malfunction itself is dropped: nothing carries a creature
    in a random direction into whatever is standing there."""
    first, second = c.roll("1d10"), c.roll("1d10")
    c.rise(first + second)
    c.fall()


@power("i591x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i591x1(c: Cast) -> None:
    """The attack context carries `opportunity` and `attacker`, so both
    halves of the printed gate are real."""
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: bool(ctx.get("opportunity"))
            and _minion(c, ctx.get("attacker")))


@power("i591p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("c.phasing(through=)",))
def i591p1(c: Cast) -> None:
    """Phasing is broader than the printed line -- it walks through walls
    and through everybody, not only through minions -- but it is the only
    verb that lets a creature cross an occupied square, and ending in one is
    refused by the grid either way. What is missing is the narrowing, not
    the reading: `_minion` answers which squares were meant."""
    c.phasing(on=c.me, until=When.EONT)


@power("i642p1", level=7, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you would be hit by an attack against Fortitude",
       on=Trigger(AttackRolled, _would_hit_my_fort,
                  "an attack would hit your Fortitude"))
def i642p1(c: Cast) -> None:
    """The check's total stands in for Fortitude. `c.check` with no DC is a
    roll with nothing to beat, which is what a check made for its number
    rather than against a difficulty is."""
    _stand_in_for_fort(c, c.check("endurance").total)


@power("i647x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i647x1(c: Cast) -> None:
    """Not needing to eat is narrative, and so is the day of wear the
    property asks for; the Endurance bonus is the whole combat content."""
    c.bonus("skill:endurance", 3, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i649x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i649x1(c: Cast) -> None:
    def crit_on_me(ev: Hit) -> None:
        if ev.target == c.me and ev.critical and ev.attacker != c.me:
            c.bonus(AC, 2, on=c.me, until=When.EONT, kind="item")

    c.watch(Hit, crit_on_me, until=When.ENCOUNTER)


@power("i651x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i651x1(c: Cast) -> None:
    """The same line as `i654x1`, paid to allies instead of to the wearer.

    Laid on whoever is in range when the belt is armed and gated on still
    being there, because the printed line is a standing radius and a
    modifier is laid once. An ally who was outside it at the top of the
    fight never picks it up; nothing on a bonus watches a distance."""
    for mate in c.within(5, side="ally"):
        c.bonus("surge_value", 1, on=mate, until=When.ENCOUNTER, kind="item",
                when=lambda ctx, who=mate: c.distance(who) <= 5)


@power("i651p1", level=7, cls=ITEM, usage=DAILY, action=MINOR,
       reach=CloseBurst(5), target=ONE_ALLY)
def i651p1(c: Cast) -> None:
    """Two surges spent for nothing and one handed over: `c.spend_surge` is
    the "lose a surge" half and `c.regain_surge` the other."""
    c.spend_surge(on=c.me)
    c.spend_surge(on=c.me)
    c.regain_surge(1)


@power("i942x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.ignore_squeeze_penalty()",))
def i942x1(c: Cast) -> None:
    """Squeezing carries `attack=-5` and `halve_speed`. The attack half is
    cancelled by a matching untyped bonus; the speed half is a cap rather
    than a modifier and nothing lifts it. Granting combat advantage is
    printed as kept, so it is left alone."""
    c.bonus("attack", 5, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_(Condition.SQUEEZING, on=c.me))


@power("i2067x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.retrieve(consumable=)",))
def i2067x1(c: Cast) -> None:
    """Drawing and stowing are not actions the engine spends, so a belt that
    makes one of them free has nothing to make free."""


@power("i2393x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.grab_reach()",))
def i2393x1(c: Cast) -> None:
    """`c.grab` is applied, not rolled and not measured: there is no reach
    on it to lengthen and no free hand to do without."""


@power("i2393p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=Melee(1), target=ONE_CREATURE, todo=("c.sustain_grab()",))
def i2393p1(c: Cast) -> None:
    """Handing a grab to an object that then holds it without the grabber
    adjacent has no relation to set: `Relation.GRABBED_BY` names a
    creature."""


@power("i2689p1", level=8, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2689p1(c: Cast) -> None:
    c.immovable(on=c.me, until=When.EONT)


@power("i2746x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2746x1(c: Cast) -> None:
    """Swimming, holding your breath and treading water: skill checks with
    no combat consequence, and a check context cannot be asked what the
    check was for."""


@power("i593p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(1), target=NO_TARGET,
       todo=("c.flank_from_square()",))
def i593p1(c: Cast) -> None:
    """Flanking is computed from two creatures' positions; an empty square
    cannot stand in for one of them."""


@power("i645p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=Melee(1), target=ONE_CREATURE,
       trigger="you miss with a melee attack",
       on=Trigger(Miss, both(by_me, by_melee), "you miss with a melee attack"))
def i645p1(c: Cast) -> None:
    """`Triggers._at` aims the row at the creature the missed attack named,
    so "the same target" needs no digging out of the event."""
    foe = c.target
    if foe is not None:
        c.basic(on=foe)


@power("i655x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i655x1(c: Cast) -> None:
    """A bare "+1 bonus": no type word on the card, so untyped."""
    c.bonus(FORT, 1, on=c.me, until=When.ENCOUNTER)


@power("i846p1", level=8, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF, trigger="you are hit by an attack",
       on=Trigger(AttackRolled, would_hit_me, "an attack would hit you"))
def i846p1(c: Cast) -> None:
    """Declared on `AttackRolled` rather than `Hit`: the defence is read
    again once the interrupt window closes, so a defence raised here can
    still turn the blow aside."""
    c.bonus(FORT, 4, on=c.me, until=When.EONT, kind="power")


@power("i1152x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1152x1(c: Cast) -> None:
    c.bonus("skill:acrobatics", 2, on=c.me, until=When.ENCOUNTER, kind="item")
    c.bonus("skill:athletics", 2, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i1152p1", level=9, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you make an Acrobatics check or an Athletics check",
       on=Trigger(SkillCheck, my_check("acrobatics", "athletics"),
                  "you make an Acrobatics or Athletics check"))
def i1152p1(c: Cast) -> None:
    """"Use the new result" is `keep="new"`, which is the default and is the
    opposite of the commoner "use the better"."""
    c.reroll_check(keep="new")


@power("i1455x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.bull_rush()", "c.grab_check()"))
def i1455x1(c: Cast) -> None:
    """Neither manoeuvre is rolled: `c.grab` is applied outright and a bull
    rush is a push, so there is no attack for the bonus to sit on and no
    size comparison being made to relax."""


@power("i2163x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.no_coup_de_grace()",))
def i2163x1(c: Cast) -> None:
    """`c.coup_de_grace` consults nothing on its victim, and who may take a
    belt off a corpse is not a fight."""


@power("i643p1", level=9, cls=ITEM, action=MINOR,
       reach=PERSONAL, target=SELF)
def i643p1(c: Cast) -> None:
    """An at-will with a price: the vulnerability is what stops the policy
    taking it every turn for free."""
    c.bonus(AC, 1, on=c.me, until=When.EONT, kind="power")
    c.vulnerable(c.level // 2, on=c.me, until=When.EONT)


@power("i648x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.max_surges()",))
def i648x1(c: Cast) -> None:
    """`Health.max_surges` is a field, but writing it from a property is
    wrong twice over: a property is re-armed at the start of every fight, so
    the ceiling would climb once an encounter, and `c.regain_surge` refills
    the pool without lifting the ceiling at all. What is missing is a verb
    that raises it idempotently for the day."""


@power("i648p1", level=9, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an enemy hits you and causes damage",
       on=Trigger(DamageRolled, _hurt_by_enemy, "an enemy damages you"))
def i648p1(c: Cast) -> None:
    """"Resist 15 against that attack" is a reduction of the one blow rather
    than a standing resistance, so it is `c.reduce` on the damage being
    interrupted. The delayed 10 is paid at the first end-of-turn of the
    wearer's after this, which is "the end of your next turn" whenever the
    blow lands on somebody else's turn -- the usual case for an interrupt."""
    c.reduce(15)

    def later(ev: TurnEnd) -> None:
        if ev.actor == c.me:
            c.flat(10, on=c.me)

    c.watch(TurnEnd, later, until=When.ENCOUNTER, once=True)


@power("i895x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("chargen.race_choice()",))
def i895x1(c: Cast) -> None:
    """The saving-throw context carries the ongoing damage's type, so
    "against poison effects" is a real gate. "Nondwarf" is not: a character's
    race is not on the board, so every ally in the burst is helped."""
    for friend in c.within(3, side="ally"):
        c.bonus("save", 5, on=friend, until=When.ENCOUNTER, kind="item",
                when=_poison_save)


@power("i1083x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1083x1(c: Cast) -> None:
    """The diamond is the power's fuel; the bonus is the whole property."""
    c.bonus(FORT, 1, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i1083p1", level=10, cls=ITEM, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       dropped=("c.item_charges()", "c.decay_bonus()"))
def i1083p1(c: Cast) -> None:
    """The surge is spent and the heal is paid. What is missing is the
    fuel: nothing counts an item's charges, so the belt never runs out and
    its Fortitude bonus never shrinks."""
    c.surge(on=c.me)


@power("i1766p1", level=10, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you are hit by an attack that deals typed nonweapon damage",
       on=Trigger(DamageRolled, _took_typed_nonweapon,
                  "you take typed nonweapon damage"))
def i1766p1(c: Cast) -> None:
    """Both the trigger and the resistance ask the same two questions of the
    damage -- that it has a type, and that the power dealing it is not a
    weapon power."""
    c.resist(5, on=c.me, until=When.EONT, when=_typed_nonweapon)


@power("i2488p1", level=10, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you would be hit by an attack",
       on=Trigger(AttackRolled, would_hit_me, "an attack would hit you"))
def i2488p1(c: Cast) -> None:
    c.bonus(AC, 4, on=c.me, until=When.EONT, kind="power")


@power("i637x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i637x1(c: Cast) -> None:
    """Gated rather than laid when the blooding happens: a property is
    armed once and bloodied comes and goes with healing. Untyped -- the
    card prints no word in front of it."""
    me = c.me
    c.bonus("surge_value", c.con_mod, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.bloodied(me))


@power("i876p1", level=10, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an attack would hit your Fortitude defence",
       on=Trigger(AttackRolled, _would_hit_my_fort,
                  "an attack would hit your Fortitude"))
def i876p1(c: Cast) -> None:
    """Which defence the attack is rolled *against* stays Fortitude -- what
    changes is the number it meets, and that is read again after this
    window. So Will is put in its place as the difference."""
    from combat_engine.engine import query

    _stand_in_for_fort(c, query.defence(c.world, c.me, WILL))


# == ring ===================================================================


@power("i3475x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("spec.monster_ref()",))
def i3475x1(c: Cast) -> None:
    """The attack context carries `attacker`, so "against the attacks of
    constructs" is a gate on all four defences. The daze is dropped rather
    than over-applied: `Ident.ref` does say which row a creature was built
    from, but the spec names the creature with an `x_` token, which
    `etl/build` makes deliberately opaque so that no row can point at it."""
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, on=c.me, until=When.ENCOUNTER, kind="power",
                when=lambda ctx: c.is_kind("construct", on=ctx.get("attacker")))


@power("i3475p1", level=5, cls=ITEM, usage=ENCOUNTER, action=STANDARD,
       reach=Ranged(10),
       target=Target("enemy", 1, label="one construct",
                     kinds=frozenset({"construct"})),
       attack=Attack(vs=WILL, printed=8),
       dropped=("spec.monster_ref()",))
def i3475p1(c: Cast) -> None:
    """"One construct" is the target line now. The longer domination is
    printed for a creature the spec names with an opaque `x_` token, which is
    a name withheld rather than a ref to point at."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


@power("i2208x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2208x1(c: Cast) -> None:
    """A language and a conversation: neither is a fight."""


@power("i2208p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i2208p1(c: Cast) -> None:
    """A day's travel and twenty-four hours: nothing an encounter reaches."""


@power("i2208p2", level=7, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(40), target=NO_TARGET, keywords=[Keyword.ILLUSION],
       dropped=("c.conjure(defences=)", "c.on_sustain(conjuration)",
                "c.zone(ends_on=)"))
def i2208p2(c: Cast) -> None:
    """The illusion stands on the board as a conjuration, sustained by a
    minor. Three clauses have nowhere to go: its flat defences of 10, the
    ten squares it moves each time it is sustained -- `c.on_sustain` takes an
    `Effect` and `c.conjure` hands back an entity -- and the two ways it
    pops, an attack hitting it or a creature walking into it."""
    where = _free_near(c, of=c.me)
    if where is not None:
        c.conjure(at=where, label=c.ref, until=When.SUSTAIN, sustain=MINOR)


@power("i3469x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.teleport(no_sight=)",))
def i3469x1(c: Cast) -> None:
    """`c.teleport` picks its destination through the decider and asks no
    question about sight, so neither the permission nor the printed penalty
    for aiming at an occupied square can be written."""


@power("i3469p1", level=8, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       out_of_combat=True)
def i3469p1(c: Cast) -> None:
    """A journey to anywhere in a named dungeon, which is travel between
    encounters rather than movement on a board."""


# == ammunition =============================================================


@power("i1931x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i1931x1(c: Cast) -> None:
    """The bonus is laid on each ally who can see the target and gated on
    that target, so it is spent on that enemy and nobody else."""
    if not c.ammunition():
        return
    foe = c.target
    if foe is None:
        return
    for friend in c.allies():
        if c.can_see(friend):
            c.bonus("attack", 1, on=friend, until=When.EONT, kind="item",
                    when=_at_target(foe))


@power("i1292x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i1292x1(c: Cast) -> None:
    if not c.ammunition():
        return
    dice = f"{_plus(c)}d6"
    foe = c.target
    if foe is None:
        return
    c.damage(dice, dtype=DamageType.FIRE, on=foe)
    for other in c.within(1, of=foe):
        if other != foe:
            c.damage(dice, dtype=DamageType.FIRE, on=other)


@power("i1357x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i1357x1(c: Cast) -> None:
    if not c.ammunition():
        return
    c.damage(f"{_plus(c)}d6", dtype=DamageType.COLD)
    c.slowed(until=When.EOTNT)


@power("i1735x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i1735x1(c: Cast) -> None:
    if not c.ammunition():
        return
    c.damage(f"{_plus(c)}d6", dtype=DamageType.LIGHTNING)


@power("i2576x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i2576x1(c: Cast) -> None:
    """"Each creature adjacent to it" is everybody, not just enemies."""
    if not c.ammunition():
        return
    foe = c.target
    if foe is None:
        return
    c.slowed(on=foe, until=When.EONT)
    for other in c.within(1, of=foe):
        if other != foe:
            c.slowed(on=other, until=When.EONT)


@power("i2736x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you attack an enemy using this ammunition",
       on=Trigger(AttackDeclared, _ammo_hit, "you attack with this ammunition",
                  window=Window.BEFORE))
def i2736x1(c: Cast) -> None:
    """Answered in the before-window, because the advantage has to be
    standing when the roll is made; `once=True` spends it on that attack."""
    if not c.ammunition():
        return
    c.grants_advantage(to="me", until=When.EOT, once=True)


@power("i565x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i565x1(c: Cast) -> None:
    """The mark's punishment is the arrow striking the marked enemy again,
    which is `c.on_attack` on that creature rather than a mark rider: the
    damage is the item's, not the wearer's."""
    if not c.ammunition():
        return
    foe = c.target
    if foe is None:
        return
    c.mark(on=foe, until=When.EOTNT)
    dice = f"{_plus(c)}d6"

    def ignored(ev: Any) -> None:
        if getattr(ev, "target", None) != c.me:
            c.damage(dice, on=foe)

    c.on_attack(ignored, by=foe, until=When.EOTNT)


@power("i3163x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you make an attack using this ammunition",
       on=Trigger(AttackRolled, _ammo_hit, "you attack with this ammunition"))
def i3163x1(c: Cast) -> None:
    """Declared on `AttackRolled` rather than `Hit`, because the zone is
    laid whether the shot lands or not. Heavily obscured is
    `blocks_sight=True`, which is the grade cover and concealment are read
    from."""
    if not c.ammunition():
        return
    c.zone(spread({c.there}, 1), label=c.ref, blocks_sight=True,
           until=When.ENCOUNTER)


@power("i3164x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i3164x1(c: Cast) -> None:
    """"Each other creature" includes the wearer's own allies, and the
    enemy that was hit is the one creature left out."""
    if not c.ammunition():
        return
    foe = c.target
    if foe is None:
        return
    for other in c.within(2, of=foe):
        if other != foe:
            c.flat(4, on=other)


@power("i3471x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with a bow or crossbow attack",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i3471x1(c: Cast) -> None:
    """Ongoing poison, and a last 5 points when the burn finally stops.

    The bow-or-crossbow half of the printed trigger is read off the weapon's
    group. The aftereffect used to be dropped for want of anything that
    fires when a save ends an effect; `c.aftereffect` is that.
    """
    victim = c.target
    if not c.ammunition():
        return
    if c.wielding("bow") or c.wielding("crossbow"):
        burn = c.ongoing(5, DamageType.POISON)
        c.aftereffect(
            burn, lambda: c.flat(5, dtype=DamageType.POISON, on=victim)
        )


@power("i660x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       todo=("c.ignore_line_of_effect()",))
def i660x1(c: Cast) -> None:
    """The whole benefit is being allowed to shoot a creature you have no
    line of effect to; line of effect is checked in targeting and nothing
    relaxes it. Treating the enemy as having cover is the price, not the
    benefit."""


@power("i1097x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i1097x1(c: Cast) -> None:
    """"One conjuration or zone that enemy has" is `c.conjurations` filtered
    by who made it; `c.dispel` unwinds what it was holding."""
    if not c.ammunition():
        return
    foe = c.target
    if foe is None:
        return
    theirs = [z for z in c.conjurations() if c.made_by(z) == foe]
    if theirs:
        pick = c.choose(theirs, "which zone or conjuration to end")
        if pick is not None:
            c.dispel(pick)


@power("i2570x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i2570x1(c: Cast) -> None:
    if not c.ammunition():
        return
    foe = c.target
    if foe is not None:
        c.teleport(1, who=foe)


@power("i2718x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i2718x1(c: Cast) -> None:
    if not c.ammunition():
        return
    foe = c.target
    if foe is None:
        return
    near = [a for a in c.within(3, of=foe, side="ally") if a != c.me]
    sq = _free_near(c, of=foe)
    if near and sq is not None:
        who = c.choose(near, "which ally steps in")
        if who is not None:
            c.teleport(max(1, c.distance(foe)), who=who, to=sq)


@power("i3162x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"),
       dropped=("c.ongoing(ends_on=)",))
def i3162x1(c: Cast) -> None:
    """The ongoing damage ends on a save rather than on the move action the
    card prints, which is the only end condition `c.ongoing` has."""
    if not c.ammunition():
        return
    c.ongoing(5)


@power("i732x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i732x1(c: Cast) -> None:
    """"Cannot shift" on its own is `c.cannot_shift`, not `c.immobilized`: the
    enemy may still walk."""
    if not c.ammunition():
        return
    c.cannot_shift(until=When.EOTNT)


@power("i733x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i733x1(c: Cast) -> None:
    if not c.ammunition():
        return
    foe = c.target
    if foe is None:
        return
    sq = _free_near(c, of=foe)
    if sq is not None:
        c.teleport(max(1, c.distance(foe) + 1), to=sq)


@power("i1341x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       todo=("c.no_teleport()",))
def i1341x1(c: Cast) -> None:
    """Nothing bars a creature from teleporting, and nothing fences off the
    squares around one: `c.immovable` refuses forced movement only."""


@power("i551x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you hit an enemy with an attack using this ammunition",
       on=Trigger(Hit, _ammo_hit, "you hit with this ammunition"))
def i551x1(c: Cast) -> None:
    """Not benefiting from invisibility is written as truesight of that one
    creature, laid on the wearer and each ally -- `c.truesight` sits on
    whoever is looking, so the printed "against anybody" is paid out to the
    side that can use it."""
    if not c.ammunition():
        return
    foe = c.target
    if foe is None:
        return
    for who in [c.me, *c.allies()]:
        c.truesight(of=foe, on=who, until=When.EONT)


@power("i1136x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=Ranged(20), target=ONE_CREATURE, no_provoke=True,
       trigger="you attack an enemy using this ammunition",
       on=Trigger(AttackRolled, _ammo_hit, "you attack with this ammunition"))
def i1136x1(c: Cast) -> None:
    """"Roll twice and use either result" is a reroll keeping the better of
    the two: the choice is only ever worth making one way."""
    if not c.ammunition():
        return
    c.reroll_attack(keep="best")


@power("i3160x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3160x1(c: Cast) -> None:
    """Two printed halves with different triggers, so this one is a trait
    holding a watch rather than a declared trigger: the first clause is a
    standing modifier on the wearer and the second answers a hit. Both are
    gated on the shot having come from this quiver -- the waiver through
    the attack context's `ammo`, which is the same fact `c.ammunition`
    reads off the event."""
    mine = c.ref.split("x")[0]
    c.ignore_cover(on=c.me, until=When.ENCOUNTER,
                   when=lambda ctx: ctx.get("ammo") == mine)

    def landed(ev: Hit) -> None:
        if ev.attacker != c.me or not c.ammunition(ev):
            return
        c.no_cover(on=ev.target, until=When.SAVE_ENDS)
        c.truesight(of=ev.target, on=c.me, until=When.SAVE_ENDS)

    c.watch(Hit, landed, until=When.ENCOUNTER)
