"""Weapon-slot magic items, heroic tier: the second wave of blocks.

Nothing here declares a weapon. The ladder, the enhancement bonus, the
critical rider and the base-item restriction are columns in `game.db` and
are laid on by `engine/equipment.py`; what is written here is only the part
that needs a body.

Three judgements run through the whole file.

* **The damage context carries no weapon.** "While using this weapon" is
  therefore never a gate: the character is holding the item for as long as
  the property is armed, so every swing is treated as the item's. That
  over-applies only for a character wielding two weapons of which one is
  magical.
* **"Extra <type> damage" that rides on somebody else's attack roll has no
  type.** `c.bonus` adds a number to the blow and the blow keeps its own
  type; where a card names one, the clause is marked `c.bonus(dtype=)`
  rather than quietly typed or quietly dropped. Where the card instead
  deals a separate packet -- "the target *takes* 1d8 cold damage" -- it is
  `c.damage(dtype=...)` and there is nothing missing.
* **"When you hit an enemy with this weapon"** aims at `c.target`.
  `Triggers._at` sends a single-target enemy row triggered by your own
  `Hit` at the creature you hit, so no helper digs it back out of the
  event. Rows triggered by *somebody else's* event read the event directly,
  because `_at` would aim them at the attacker.

The item's own level is read off its header with `get(c.ref).level` for the
handful of cards printing "the weapon's level + 3" as an attack bonus. That
is the declared datum, not a hand-written number, and `Attack(printed=)` is
the wrong tool -- it takes the *character's* level back out again.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    CHA,
    DAILY,
    DEX,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Cover,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Effect,
    EffectApplied,
    Forced,
    ForcedMove,
    Healed,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveStart,
    OpportunityWindow,
    Position,
    Ranged,
    Relation,
    Size,
    SurgeSpent,
    Target,
    Trigger,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    both,
    by_keyword,
    by_me,
    by_melee,
    by_opportunity,
    by_ranged,
    cursed_by_me,
    either,
    get,
    power,
    query,
    spread,
    targets_me,
)

ITEM = "item"

#: The five keywords the "acid, cold, fire, lightning, or thunder" cards
#: all print as one list.
_ELEMENTAL = (
    Keyword.ACID,
    Keyword.COLD,
    Keyword.FIRE,
    Keyword.LIGHTNING,
    Keyword.THUNDER,
)

#: Size order, for "Large or larger". `Size` is a `StrEnum`, so its members
#: do not compare by rank on their own.
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


# -- gates on the damage context --------------------------------------------


def _kinds(c: Cast, ctx: dict[str, Any]) -> frozenset[str]:
    foe = ctx.get("target")
    return c.kinds_of(on=foe) if foe is not None else frozenset()


def _against(c: Cast, *words: str):  # noqa: ANN202
    """Gate: the creature taking this damage is one of these kinds."""

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(_kinds(c, ctx) & set(words))

    return gate


def _of_type(dtype: DamageType):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("dtype") == dtype

    return gate


def _of_keyword(*words: Keyword):  # noqa: ANN202
    """Gate: the power this damage came out of prints one of these words."""

    def gate(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power") or "")
        return p is not None and bool(set(words) & set(p.keywords))

    return gate


def _charging(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("charge"))


def _melee_damage(ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power") or "")
    return p is not None and p.reach is not None and p.reach.kind == "melee"


def _aimed_at(who: int):  # noqa: ANN202
    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == who

    return gate


def _swung_by(who: int):  # noqa: ANN202
    """Gate on a *defence* read: whoever is attacking me. The attack
    context is what `query.defence` is handed, and it carries `attacker`."""

    def gate(ctx: dict[str, Any]) -> bool:
        return ctx.get("attacker") == who

    return gate


# -- predicates -------------------------------------------------------------


def _crit_by_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(ev, "critical", False)


def _crit_on_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "critical", False)


def _fumble_by_me(world: World, me: int, ev: Any) -> bool:
    """A natural 1, read off the roll rather than guessed at from a miss."""
    return getattr(ev, "attacker", None) == me and getattr(ev, "natural", 0) == 1


def _miss_coming(world: World, me: int, ev: Any) -> bool:
    """My attack is rolled and, as things stand, misses.

    Answering `Miss` is too late to reroll usefully: the comparison has been
    made and the damage branch is already chosen. `AttackRolled`'s interrupt
    window is where a reroll belongs.
    """
    result = getattr(ev, "result", None)
    return (
        getattr(ev, "attacker", None) == me
        and result is not None
        and not result.hit
    )


def _melee_miss_coming(world: World, me: int, ev: Any) -> bool:
    return _miss_coming(world, me, ev) and by_melee(world, me, ev)


def _killed_by_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "source", None) == me


def _my_marked_melee(world: World, me: int, ev: Any) -> bool:
    """Damage reached me from a creature I have marked."""
    return getattr(ev, "target", None) == me and world.relations.holds(
        Relation.MARKED_BY, me, getattr(ev, "source", None)
    )


def _covered_target(world: World, me: int, ev: Any) -> bool:
    """I am about to attack something that cover or concealment is helping."""
    foe = getattr(ev, "target", None)
    if getattr(ev, "attacker", None) != me or foe is None:
        return False
    return (
        query.cover_between(world, me, foe) is not Cover.NONE
        or query.concealment_of(world, foe) is not Cover.NONE
    )


def _adjacent_shift(world: World, me: int, ev: Any) -> bool:
    """An enemy standing next to me is starting a shift.

    Asked on `MoveStart` rather than `MoveEnd`: by the end of the shift it
    has gone, and the adjacency the card names is false precisely when the
    row should fire.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me or getattr(ev, "kind_", "") != "shift":
        return False
    return who in query.enemies(world, me) and query.adjacent(world, me, who)


def _shoved_by_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "source", None) == me and getattr(ev, "how", None) in (
        Forced.PUSH,
        Forced.SLIDE,
    )


def _pushed_by_me(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "source", None) == me
        and getattr(ev, "how", None) is Forced.PUSH
    )


def _type_words(world: World, who: int | None) -> frozenset[str]:
    """A creature's type words, asked from a predicate.

    `c.kinds_of` is the verb and a predicate is handed `(world, me, ev)`
    with no `Cast` to call it on, so one is built the way `Attack.bonus_for`
    already builds a probe.
    """
    if who is None:
        return frozenset()
    return Cast(world=world, me=who, ref="").kinds_of(on=who)


def _giant_forces(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and "giant" in _type_words(
        world, getattr(ev, "source", None)
    )


def _giant_condition(world: World, me: int, ev: Any) -> bool:
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "condition", None) in (Condition.STUNNED, Condition.PRONE)
        and "giant" in _type_words(world, getattr(ev, "source", None))
    )


def _ally_swings(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "attacker", None)
    return who is not None and who != me and who in query.allies(world, me)


def _ally_flank_hit(world: World, me: int, ev: Any) -> bool:
    """An ally I am flanking with just landed a blow."""
    who = getattr(ev, "attacker", None)
    foe = getattr(ev, "target", None)
    if who is None or foe is None or who == me or who not in query.allies(world, me):
        return False
    return query.flanked_by(world, foe, me)


def _hurt_bloodied_ally(world: World, me: int, ev: Any) -> bool:
    foe = getattr(ev, "target", None)
    if foe is None or foe == me or foe not in query.allies(world, me):
        return False
    if query.distance_between(world, me, foe) > 10:
        return False
    from combat_engine.engine import Health

    hp = world.get(foe, Health)
    # `hp` and `max_hp`, not `current`/`maximum`: `Health` has never had
    # those names, and this predicate raised every time it was asked.
    return hp is not None and hp.hp <= hp.max_hp // 2


def _odd_arcane_at_will(world: World, me: int, ev: Any) -> bool:
    """My arcane ranged at-will just came up odd, before the roll is used."""
    if getattr(ev, "attacker", None) != me:
        return False
    if getattr(ev, "natural", 0) % 2 == 0:
        return False
    p = get(getattr(ev, "power", "") or "")
    return (
        p is not None
        and p.usage is Usage.AT_WILL
        and Keyword.ARCANE in p.keywords
        and by_ranged(world, me, ev)
    )


# -- small shared bodies ----------------------------------------------------


def _square_of(c: Cast, who: int):  # noqa: ANN202
    pos = c.world.get(who, Position)
    return pos.square if pos is not None else None


def _free_beside(c: Cast, who: int) -> list[Any]:
    """Empty squares next to a creature, for a row that names one."""
    here = _square_of(c, who)
    if here is None:
        return []
    return [s for s in spread({here}, 1) if s != here and not c.in_squares([s])]


def _raise_ongoing(c: Cast, who: int, extra: int) -> bool:
    """Lift the worst burn standing on a creature by `extra`.

    Ongoing damage of one type does not stack -- the highest applies -- so
    "increase the ongoing damage" is written by reading what is there and
    laying a stronger one of the same type, which supersedes it.
    """
    standing = [e for e in c.world.effects.of(who) if e.ongoing is not None]
    if not standing:
        return False
    worst = max(standing, key=lambda e: e.ongoing[0])
    amount, dtype = worst.ongoing
    return c.ongoing(amount + extra, dtype, on=who) is not None


def _reach(c: Cast) -> int:
    held = c.held(on=c.me)
    return held[0].reach if held else 1


# -- level 3 ----------------------------------------------------------------


@power(
    "i1335p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
)
def i1335p1(c: Cast) -> None:
    """"That you can see" is a real filter, not flavour: a burst otherwise
    marks through a wall."""
    if c.can_see():
        c.mark(until=When.EONT)


@power(
    "i1337p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you would attack an enemy benefiting from concealment or cover",
    on=Trigger(
        AttackDeclared,
        _covered_target,
        "you would attack an enemy behind cover",
        window=Window.BEFORE,
    ),
)
def i1337p1(c: Cast) -> None:
    """Declared in the `BEFORE` window so both halves are installed before
    the triggering attack reads cover and advantage."""
    c.no_cover(until=When.EOT)
    c.grants_advantage(until=When.EOT, once=True)


@power(
    "i1361x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.bonus(dtype=)",),
)
def i1361x1(c: Cast) -> None:
    """The extra damage rides on somebody else's roll, so it keeps that
    blow's type; nothing types a modifier."""
    c.bonus(
        "damage",
        c.con_mod,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=c.me),
    )


@power(
    "i1363p1",
    level=3,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.COLD],
    dropped=("c.deals(revert=)",),
)
def i1363p1(c: Cast) -> None:
    """Turning the damage back to normal is the second free action and
    `c.deals` has no door out of itself."""
    c.deals(DamageType.COLD, on=c.me, until=When.ENCOUNTER)


@power(
    "i1363p2",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1363p2(c: Cast) -> None:
    c.damage("1d8", dtype=DamageType.COLD)
    c.slowed(until=When.EONT)


@power(
    "i1397x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1397x1(c: Cast) -> None:
    """Total concealment is the superior grade of the same scale, so the
    question has an answer rather than needing a new verb."""

    def on_swing(ev: AttackDeclared) -> None:
        if ev.attacker != c.me:
            return
        if query.concealment_of(c.world, c.me) is not Cover.SUPERIOR:
            return
        for d in (AC, FORT, REF, WILL):
            c.bonus(d, 2, on=c.me, until=When.SONT)

    c.watch(AttackDeclared, on_swing, until=When.ENCOUNTER)


@power(
    "i1397p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you take damage from a melee attack by an enemy marked by you",
    on=Trigger(
        DamageApplied,
        both(_my_marked_melee, by_melee),
        "an enemy you marked hurts you in melee",
    ),
)
def i1397p1(c: Cast) -> None:
    """The augment is read back off how many points were spent on this row.
    The extra `1[W]` is a second application rather than a rider, because
    the basic attack rolls its own damage out of reach of a modifier laid
    here."""
    foe = c.target
    if foe is None:
        return
    landed = c.basic(on=foe)
    if landed and c.points_spent(c.ref) >= 2:
        c.damage(c.w(), on=foe)
    c.shift(c.enhancement)


@power(
    "i1473x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1473x1(c: Cast) -> None:
    """A critical rider is its own modifier key, read only when a blow
    crits. "Cumulative until the end of the encounter" is taken at its
    word: the stack is not spent by the crit that collects it."""

    def on_crit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.critical:
            c.bonus("crit_damage", 0, dice=c.w(), on=c.me, until=When.ENCOUNTER)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i1473p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="an enemy adjacent to you scores a critical hit against you",
    on=Trigger(Hit, _crit_on_me, "an enemy crits you"),
)
def i1473p1(c: Cast) -> None:
    """"This weapon's critical damage dice, including the property" is
    exactly the `crit_damage` modifier the column and the row above both
    write into, so it is read rather than rebuilt."""
    foe = c.target
    if foe is not None and c.adjacent(foe):
        c.flat(c.total("crit_damage"), on=foe)


@power(
    "i1489p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    trigger="you hit an enemy with a named class power using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
    dropped=("by_class()",),
)
def i1489p1(c: Cast) -> None:
    """Which class row the hit came from cannot be asked, so any hit of the
    wielder's arms it."""
    c.ongoing(5 + c.str_mod, DamageType.FIRE)


@power(
    "i1497p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit a target with a weapon power using this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i1497p1(c: Cast) -> None:
    c.flat(c.str_mod + c.enhancement)


@power(
    "i1510x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1510x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i1510p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a thunder power using this blade",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.THUNDER)), "you hit with a thunder power"
    ),
    dropped=("by_class()",),
)
def i1510p1(c: Cast) -> None:
    """The keyword half of the printed trigger is a predicate; the class
    half is not."""
    foe = c.target
    if foe is None:
        return
    for e in c.within(2, of=foe, side="enemy"):
        if e != foe:
            c.dazed(on=e, until=When.EONT)


@power(
    "i1556x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1556x1(c: Cast) -> None:
    """`c.initiative` carries no bonus type, and nothing reads an
    `"initiative"` modifier -- so a typed `c.bonus` would be silently
    ignored rather than slightly too generous."""
    c.initiative(c.enhancement, on=c.me)


@power(
    "i1556p1",
    level=3,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
    out_of_combat=True,
)
def i1556p1(c: Cast) -> None:
    """Drawing and stowing are not modelled and the vanishing is a search,
    not a fight. Inert by choice."""
    c.note("i1556p1: drawn or sheathed, and only the wielder can find it")


@power(
    "i1618p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you push or slide an enemy with an attack using this weapon",
    on=Trigger(ForcedMove, _shoved_by_me, "you push or slide an enemy"),
)
def i1618p1(c: Cast) -> None:
    """Declared `SELF`, because the shove event names neither an attacker
    nor an actor and the auto-targeter would pick a stranger."""
    shoved = getattr(c.trigger, "target", None)
    for e in c.within(1, side="enemy"):
        if e != shoved:
            c.push(1, on=e)
    if shoved is not None and c.points_spent(c.ref) >= 2:
        c.damage("1d10", dtype=DamageType.FORCE, on=shoved)


@power(
    "i1619x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1619x1(c: Cast) -> None:
    """No type word on the card, so the running bonus is untyped. The stack
    is held per target and torn down the moment you swing at somebody else
    or land one, which is the whole of the printed ending clause."""
    count: dict[int, int] = {}
    holds: dict[int, Effect] = {}

    def drop(keep: int | None) -> None:
        for who in list(holds):
            if who != keep:
                c.world.effects.end(holds.pop(who), "i1619x1")
                count.pop(who, None)

    def on_miss(ev: Miss) -> None:
        if ev.attacker != c.me:
            return
        foe = ev.target
        drop(foe)
        if count.get(foe, 0) >= max(1, c.enhancement):
            return
        old = holds.pop(foe, None)
        if old is not None:
            c.world.effects.end(old, "i1619x1")
        count[foe] = count.get(foe, 0) + 1
        fresh = c.bonus(
            "attack", count[foe], on=c.me, until=When.ENCOUNTER, when=_aimed_at(foe)
        )
        if fresh is not None:
            holds[foe] = fresh

    def on_hit(ev: Hit) -> None:
        if ev.attacker == c.me:
            drop(None)

    c.watch(Miss, on_miss, until=When.ENCOUNTER)
    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i1621p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    trigger="you hit a target with an attack made with this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
    dropped=("c.aftereffect()",),
)
def i1621p1(c: Cast) -> None:
    """The Aftereffect -- what happens when the save finally succeeds -- has
    no hold to hang from. `c.condition(escalate=)` is the other side of the
    same coin and fires on a *failed* save."""
    c.ongoing(5, DamageType.FIRE)


@power(
    "i1630p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
)
def i1630p1(c: Cast) -> None:
    c.bonus("damage", c.enhancement, kind="power", until=When.EONT)


@power(
    "i1690x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("by_class()",),
)
def i1690x1(c: Cast) -> None:
    """Rides on one named class row and the spec gives its name rather than
    its ref, so there is nothing to watch for."""


@power(
    "i1757p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make an attack roll with this weapon and dislike the result",
    on=Trigger(
        AttackRolled,
        _miss_coming,
        "your attack roll is down and would miss",
        window=Window.BEFORE,
    ),
)
def i1757p1(c: Cast) -> None:
    """"Don't like the result" is a player's judgement; the closest thing
    the engine can answer is a roll that as things stand misses. `keep` is
    `new`, because the card insists on the second result even if lower."""
    c.reroll_attack(keep="new")


@power(
    "i2005x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2005x1(c: Cast) -> None:
    """The spite half answers a *declared* attack, not a hit: the card pays
    out whether or not the swing lands."""
    c.as_implement(on=c.me)
    plus = c.enhancement

    def on_swing(ev: AttackDeclared) -> None:
        if ev.target != c.me or not c.cursed(on=ev.attacker):
            return
        p = get(ev.power)
        if p is not None and p.reach is not None and p.reach.kind == "melee":
            c.flat(plus, on=ev.attacker)

    c.watch(AttackDeclared, on_swing, until=When.ENCOUNTER)


@power(
    "i2006x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2006x1(c: Cast) -> None:
    c.as_implement(on=c.me)
    plus = c.enhancement

    def on_swing(ev: AttackDeclared) -> None:
        if ev.target != c.me or not c.cursed(on=ev.attacker):
            return
        p = get(ev.power)
        if p is not None and p.reach is not None and p.reach.kind == "melee":
            c.flat(plus, on=ev.attacker)

    c.watch(AttackDeclared, on_swing, until=When.ENCOUNTER)


@power(
    "i2007x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2007x1(c: Cast) -> None:
    c.as_implement(on=c.me)
    plus = c.enhancement

    def on_swing(ev: AttackDeclared) -> None:
        if ev.target != c.me or not c.cursed(on=ev.attacker):
            return
        p = get(ev.power)
        if p is not None and p.reach is not None and p.reach.kind == "melee":
            c.flat(plus, on=ev.attacker)

    c.watch(AttackDeclared, on_swing, until=When.ENCOUNTER)


@power(
    "i2011p1",
    level=3,
    cls=ITEM,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.split_weapon()",),
)
def i2011p1(c: Cast) -> None:
    """One weapon becomes two, one per hand. `Gear` holds what is carried
    and nothing divides an item, so the off-hand copy cannot be made."""


@power(
    "i2060x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("query.provoked_by()",),
)
def i2060x1(c: Cast) -> None:
    """The attack context carries `opportunity`, so the defence gate is
    exact; what it cannot say is *what* provoked the opening, so the bonus
    also applies to an opportunity attack your walking away provoked."""
    c.bonus(
        AC,
        2,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "i2060p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def i2060p1(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.EOT)


@power(
    "i2116p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you hit a target with this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i2116p1(c: Cast) -> None:
    """"A target of your choice" is any enemy, including the one just hit."""
    foes = c.enemies()
    if foes:
        c.basic(on=c.choose(foes, "who the extra swing goes to"))


@power(
    "i2154p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def i2154p1(c: Cast) -> None:
    """Declared before the swing, so the damage bonus is laid with
    `once=True` and spent on the roll it was bought for."""
    c.bonus(
        "damage", 2 * c.enhancement, kind="power", on=c.me, until=When.EOT, once=True
    )
    c.penalty(AC, 2, on=c.me, until=When.EONT)


@power(
    "i2188x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2188x1(c: Cast) -> None:
    """"Your shield bonus increases by 1" presupposes one, so it is gated
    on actually carrying a shield -- `Gear.shield` is the printed
    Requirement line's own question. Typed `shield`, which is the word the
    card prints: a shield's own AC is not written as a modifier anywhere,
    so nothing of that type competes with this and the larger-wins rule
    costs the wielder nothing.

    The off-hand half is not enforced: the item was dealt to whoever is
    holding it."""
    if not c.wielding("shield"):
        return
    c.bonus(AC, 1, kind="shield", on=c.me, until=When.ENCOUNTER)
    c.bonus(REF, 1, kind="shield", on=c.me, until=When.ENCOUNTER)


@power(
    "i2402p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2402p1(c: Cast) -> None:
    if "reptile" in c.kinds_of():
        c.damage("1d20")
    else:
        c.damage("1d4")


@power(
    "i2504x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2504x1(c: Cast) -> None:
    """The light it sheds unaffixed is not a combat effect. "Radiant
    attacks" is the keyword on the power, read off the damage context."""
    c.bonus(
        "damage",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=_of_keyword(Keyword.RADIANT),
    )


@power(
    "i2505x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2505x1(c: Cast) -> None:
    c.bonus(
        "damage",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=_of_keyword(Keyword.IMPLEMENT),
    )


@power(
    "i2523p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit a target with this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i2523p1(c: Cast) -> None:
    c.immobilized(until=When.SAVE_ENDS)


@power(
    "i2554x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2554x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i2554p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION],
    trigger="you hit an enemy with a class power using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
    dropped=("by_class()",),
)
def i2554p1(c: Cast) -> None:
    c.invisible(to=c.target, on=c.me, until=When.EONT)


@power(
    "i2709p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2709p1(c: Cast) -> None:
    """Not `c.cure`: the weakness is still standing and still has to be
    saved against. Suppressing the condition is exactly what "you do not
    deal half damage while weakened" asks for, because halving is read off
    the live condition."""
    c.ignore_condition(Condition.WEAKENED, on=c.me, until=When.EONT)


@power(
    "i2711x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2711x1(c: Cast) -> None:
    """The damage context has no `advantage` key, so the question is asked
    of the board again when the modifier is read. A one-shot grant already
    spent on the attack roll will therefore not pay here, which is the one
    case this is thinner than the card."""
    c.bonus(
        "damage",
        c.enhancement,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None
        and query.has_combat_advantage(c.world, c.me, ctx["target"]),
    )


@power(
    "i2744x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i2744x1(c: Cast) -> None:
    """Loading is not an action the engine charges for, so waiving its cost
    is deliberately inert rather than unfinished."""
    c.note("i2744x1: loading costs a free action")


@power(
    "i2744p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def i2744p1(c: Cast) -> None:
    c.basic(on=c.target, ranged=True)


@power(
    "i2821p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
    todo=("c.reroll_attacks_against()",),
)
def i2821p1(c: Cast) -> None:
    """A standing "roll twice and use either" against one creature.
    `c.reroll_attack` rerolls the attack being answered and `c.grants_advantage`
    is a flat +2 -- neither is this, and substituting one would be a
    different number in every fight."""


@power(
    "i2882p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2882p1(c: Cast) -> None:
    c.damage("1d8", dtype=DamageType.THUNDER)
    c.push(1)


@power(
    "i2965x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2965x1(c: Cast) -> None:
    """`charge` is in the damage context, so this is one gate rather than a
    guess at which row a charge happens to be."""
    c.bonus("damage", 0, dice="1d8", on=c.me, until=When.ENCOUNTER, when=_charging)


@power(
    "i2965p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i2965p1(c: Cast) -> None:
    """A minor action spent before the run, so the payout waits on the
    charge landing. `once=True` on the watch keeps it to one charge."""

    def on_charge(ev: Hit) -> None:
        if ev.attacker != c.me or not getattr(ev, "charge", False):
            return
        for a in c.within(10, side="ally"):
            c.bonus("attack", 1, on=a, until=When.SONT)
            c.bonus("damage", c.cha_mod, on=a, until=When.SONT)

    c.watch(Hit, on_charge, until=When.EONT, once=True)


@power(
    "i2978x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2978x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i2978p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    trigger="you hit an enemy using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i2978p1(c: Cast) -> None:
    c.weakened(until=When.SAVE_ENDS)


@power(
    "i2979x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2979x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i2979p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    trigger="you hit an enemy using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i2979p1(c: Cast) -> None:
    c.ongoing(5, DamageType.POISON)


@power(
    "i3002p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    trigger="you hit with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i3002p1(c: Cast) -> None:
    """"All creatures adjacent to the target" -- allies included, which is
    why the sweep is not filtered by side."""
    foe = c.target
    if foe is None:
        return
    for e in c.within(1, of=foe):
        if e != foe:
            c.flat(c.enhancement, dtype=DamageType.ACID, on=e)


@power(
    "i3044x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3044x1(c: Cast) -> None:
    """`c.initiative` carries no bonus type; nothing reads an
    `"initiative"` modifier, so a typed `c.bonus` would be ignored."""
    c.initiative(2, on=c.me)


@power(
    "i3044p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="an enemy adjacent to you shifts",
    on=Trigger(MoveStart, _adjacent_shift, "an adjacent enemy shifts"),
)
def i3044p1(c: Cast) -> None:
    """Asked on the start of the move: by the end of a shift the enemy is
    no longer adjacent, which is the moment the row is for."""
    c.basic(on=c.target)


@power(
    "i3066p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
    trigger="you hit a target with a weapon power using this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i3066p1(c: Cast) -> None:
    """Declared as its own attack rather than routed through `c.basic`,
    because the printed swing deals no damage and `c.basic` always does."""
    if c.strike():
        c.grants_advantage(until=When.EONT)


@power(
    "i3146p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.ignore_line_of_effect()",),
)
def i3146p1(c: Cast) -> None:
    """Shooting round blocking terrain is a waiver of line of effect, which
    `query.line_of_effect` answers and nothing sets aside. The cover and
    concealment half is a verb, so it is written."""
    c.ignore_cover(on=c.me, until=When.EONT)


@power(
    "i3147x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.deals(when=)",),
)
def i3147x1(c: Cast) -> None:
    """The retyping is real; the "only on ranged attacks, only for untyped
    damage" half is not, because `c.deals` takes no gate. A melee swing
    with this weapon therefore also comes out typed."""
    c.deals(DamageType.LIGHTNING, on=c.me, until=When.ENCOUNTER)


@power(
    "i3147p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=CloseBlast(5),
    target=UpTo(3),
    keywords=[Keyword.LIGHTNING],
)
def i3147p1(c: Cast) -> None:
    """"The weapon's level + 3" is a flat number rather than an ability, so
    the roll is made in the body. `Attack(printed=)` is the wrong tool: it
    takes the *character's* level term back out, which is a monster's
    arithmetic and not an item's."""
    if c.attack(get(c.ref).level + 3, REF).hit:
        c.damage("1d8", dtype=DamageType.LIGHTNING)


@power(
    "i3154p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    trigger="you hit an adjacent enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an adjacent enemy with this weapon"),
)
def i3154p1(c: Cast) -> None:
    """The destination is named by the card, so it is worked out rather
    than left to the mover's own decider, which would happily pick a square
    nowhere near the enemy."""
    foe = c.target
    if foe is None or not c.adjacent(foe):
        return
    spots = [s for s in _free_beside(c, foe) if s != c.here]
    if spots:
        c.teleport(2, to=c.choose(spots, "where you reappear"))


@power(
    "i3155p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i3155p1(c: Cast) -> None:
    c.bonus("attack", 2, kind="power", on=c.me, until=When.ENCOUNTER, once=True)


@power(
    "i3422p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="an ally flanking with you hits the enemy you are both flanking",
    on=Trigger(Hit, _ally_flank_hit, "an ally you flank with hits"),
    dropped=("query.is_summoned()",),
)
def i3422p1(c: Cast) -> None:
    """Declared `SELF`: the event's attacker is the ally, so a single-target
    enemy row would be aimed at your own side. Which sort of ally it is --
    a beast or a summoned creature -- is not a question the board answers,
    so any flanking ally arms it."""
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.basic(on=foe)


@power(
    "i3422p2",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i3422p2(c: Cast) -> None:
    """A beast or a summoned creature is a companion or a servant, which
    the board does answer -- so this one needs no marker."""
    foe = c.target
    kin = [*c.companions(), *c.servants()]
    near = [
        k for k in kin if c.adjacent(k) or (foe is not None and c.adjacent_to(foe, k))
    ]
    if near:
        c.shift(c.enhancement, who=c.choose(near, "which of yours steps"))


@power(
    "i3459p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make an arcane ranged at-will attack and roll an odd number",
    on=Trigger(
        AttackRolled,
        _odd_arcane_at_will,
        "your arcane ranged at-will comes up odd",
    ),
)
def i3459p1(c: Cast) -> None:
    """The repeat is the *same* row fired again, which is what
    `c.grant_attack(ref=)` is for; `reentrant` is the printed "use the
    power again" and the guard against a row handing itself back and forth
    would otherwise refuse it."""
    ev = c.trigger
    first = getattr(ev, "target", None)
    others = [e for e in c.enemies() if e != first]
    if not others:
        return
    c.grant_attack(
        c.me,
        on=c.choose(others, "who the second casting goes to"),
        ref=getattr(ev, "power", ""),
        attack_bonus=c.enhancement,
        reentrant=True,
    )


@power(
    "i3558x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i3558x1(c: Cast) -> None:
    """A skill bonus to ritual checks, and rituals are not fights. Inert by
    choice rather than unfinished."""
    c.note("i3558x1: paired with its companion blade, a bonus to ritual checks")


@power(
    "i3558p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you miss with a melee or close attack made with this item",
    on=Trigger(
        AttackRolled,
        _melee_miss_coming,
        "your melee or close attack would miss",
        window=Window.BEFORE,
    ),
)
def i3558p1(c: Cast) -> None:
    """Answered while the roll is still open rather than on the miss: by
    the time `Miss` is emitted the damage branch has been chosen and a
    reroll changes nothing."""
    c.reroll_attack(keep="best")


@power(
    "i457p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    dropped=("c.aegis()",),
)
def i457p1(c: Cast) -> None:
    """Treating the mark as a particular class feature's mark cannot be
    said: a mark is a relation and carries no flavour of which row laid
    it."""
    c.mark(until=When.SAVE_ENDS)


@power(
    "i478x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i478x1(c: Cast) -> None:
    """Skill modifiers are read under `skill:<name>`, so the check bonus is
    a real modifier rather than an inert note."""
    c.bonus("skill:nature", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER)
    c.as_implement(on=c.me)


@power(
    "i478p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.PSYCHIC],
    trigger="you score a critical hit against an enemy with this spear",
    on=Trigger(Hit, _crit_by_me, "you score a critical hit"),
)
def i478p1(c: Cast) -> None:
    c.dazed(until=When.EOTNT)


@power(
    "i510p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i510p1(c: Cast) -> None:
    """"Your next attack that hits an aberrant creature" is a gated
    one-shot: the gate picks the creature and `once=True` spends it."""
    dice = c.w(2 if c.points_spent(c.ref) >= 2 else 1)
    c.bonus(
        "damage",
        0,
        dice=dice,
        on=c.me,
        until=When.ENCOUNTER,
        once=True,
        when=_against(c, "aberrant"),
    )


@power(
    "i517x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i517x1(c: Cast) -> None:
    """"Whenever you reduce an enemy to 0 hit points" is the downfall
    event, which names who struck the blow -- so it is one predicate rather
    than a guess off the damage."""
    c.bonus(
        "attack",
        1,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_against(c, "undead"),
    )
    plus = c.enhancement

    def on_kill(ev: Dropped) -> None:
        if ev.source != c.me:
            return
        who = [a for a in c.within(5, side="ally") if c.bloodied(on=a)]
        if c.bloodied(on=c.me):
            who.append(c.me)
        if who:
            c.heal(plus, on=c.choose(who, "who is mended"))

    c.watch(Dropped, on_kill, until=When.ENCOUNTER)


@power(
    "i529x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i529x1(c: Cast) -> None:
    """How many hands a weapon needs and whether it eats ammunition are
    columns the engine never charges for. Inert by choice."""
    c.note("i529x1: one-handed, and it needs no bolts")


@power(
    "i567p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy that has an aura with this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
    dropped=("c.no_aura()",),
)
def i567p1(c: Cast) -> None:
    """An aura is a thing on the board with an owner, so ending it is
    `c.dispel`. Stopping the enemy putting it back up is not: nothing
    forbids a trait, only a row."""
    foe = c.target
    if foe is None:
        return
    for z in c.conjurations():
        if c.made_by(z) == foe:
            c.dispel(z)


@power(
    "i691p1",
    level=3,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.considered_bloodied()",),
)
def i691p1(c: Cast) -> None:
    """"Bloodied for all purposes" without losing hit points. Being
    bloodied is read off `Health` everywhere, and nothing pretends."""


@power(
    "i828p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with an attack using the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
    dropped=("c.no_teleport()",),
)
def i828p1(c: Cast) -> None:
    """Barring one mode of movement cannot be said: `c.no_walk` takes away
    walking and nothing takes away a blink."""
    c.dazed(until=When.EONT)
    if "aberrant" in c.kinds_of():
        c.condition(Condition.RESTRAINED, until=When.EONT)


@power(
    "i834x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_damage_die()",),
)
def i834x1(c: Cast) -> None:
    """Turns on what the individual damage dice came up as. `DamageRolled`
    carries the total and nothing carries the faces."""


@power(
    "i845p1",
    level=3,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a primal attack power using this weapon",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.PRIMAL)), "you hit with a primal power"
    ),
)
def i845p1(c: Cast) -> None:
    c.push(1)
    c.shift(1)
    for a in c.within(5, side="ally"):
        c.shift(1, who=a)


@power(
    "i867x1",
    level=3,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.on_grant_attack()",),
)
def i867x1(c: Cast) -> None:
    """Rides on the moment you hand an ally a swing. `c.grant_attack` takes
    a bonus, but nothing announces a grant for a second row to answer."""


# -- level 4 ----------------------------------------------------------------


@power(
    "i1043p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1043p1(c: Cast) -> None:
    """The burn and the penalty to its saves are one hold, not two: applied
    separately the victim would get two saving throws."""
    c.condition(
        until=When.SAVE_ENDS, save_mod=-2, ongoing=(5, DamageType.NECROTIC)
    )


@power(
    "i1096p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i1096p1(c: Cast) -> None:
    """The destination is named, so the square is worked out here rather
    than left to the mover's decider. The augment only restates the
    combat-advantage clause the base effect already has."""
    foe = c.target
    if foe is None:
        return
    allies = c.allies()
    if allies:
        ally = c.choose(allies, "who the enemy lands beside")
        spots = _free_beside(c, ally)
        if spots:
            c.teleport(20, who=foe, to=spots[0])
    c.grants_advantage(until=When.EONT)


@power(
    "i1174x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1174x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i1231x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.deals(when=)",),
)
def i1231x1(c: Cast) -> None:
    """The damage is one type against a creature vulnerable to it and
    another against everyone else. `c.deals` retypes every swing and takes
    no gate, so an ungated one would be wrong for every other target."""


@power(
    "i1231p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    trigger="you hit an enemy with this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
    dropped=("c.flat(dtypes=)",),
)
def i1231p1(c: Cast) -> None:
    """A blow of two types at once has no spelling: damage carries one
    `DamageType`. Dealt as the first of the pair, which is a resistance
    the target may have and the other may not."""
    c.flat(2 * c.enhancement, dtype=DamageType.FIRE)
    c.dazed(until=When.EONT)


@power(
    "i1460p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with a melee attack using this weapon",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def i1460p1(c: Cast) -> None:
    c.immobilized(until=When.SONT)
    c.immobilized(on=c.me, until=When.SONT)


@power(
    "i1502x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1502x1(c: Cast) -> None:
    def on_kill(ev: Dropped) -> None:
        if ev.source != c.me:
            return
        for e in c.within(1, side="enemy"):
            c.prone(on=e)

    c.watch(Dropped, on_kill, until=When.ENCOUNTER)


@power(
    "i1507x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("Hit.hand",),
)
def i1507x1(c: Cast) -> None:
    """Turns on hitting with each hand in the same turn. The attack context
    carries `hand`, but the hit does not, so the two blows cannot be told
    apart after the fact."""


@power(
    "i1633x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1633x1(c: Cast) -> None:
    """Answered on the hold landing rather than on the hit: the burn is
    applied by the attack's *body*, which runs after `Hit` has been
    announced, so a watch on the hit finds nothing yet to raise. The
    re-entry guard matters -- lifting a burn lays another hold, which is
    the same event again."""
    plus = c.enhancement
    busy = {"in": False}

    def on_hold(ev: EffectApplied) -> None:
        if ev.source != c.me or busy["in"]:
            return
        busy["in"] = True
        try:
            _raise_ongoing(c, ev.target, plus)
        finally:
            busy["in"] = False

    c.watch(EffectApplied, on_hold, until=When.ENCOUNTER)


@power(
    "i1699x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1699x1(c: Cast) -> None:
    """`c.forces` is handed `how`, so a push can be lengthened without also
    lengthening pulls and slides, which the card does not grant."""
    c.forces(
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("how") == Forced.PUSH,
    )


@power(
    "i1699p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you push a target with a weapon power or a critical hit",
    on=Trigger(ForcedMove, _pushed_by_me, "you push a target"),
)
def i1699p1(c: Cast) -> None:
    """Declared `SELF`: the shove event names no attacker, so a
    single-target enemy row would be aimed by the auto-targeter."""
    shoved = getattr(c.trigger, "target", None)
    if shoved is not None:
        c.prone(on=shoved)


@power(
    "i1762p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.SLEEP],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1762p1(c: Cast) -> None:
    """The secondary attack has a flat bonus rather than an ability, so it
    is rolled in the body. `escalate` is the printed "first failed save",
    and it fires on every failed save rather than only the first -- a
    difference that costs the target nothing it was not already going to
    suffer on the next one."""
    plus = get(c.ref).level + c.enhancement
    foe = c.target
    if foe is None or not c.attack(plus, WILL).hit:
        return
    c.condition(
        Condition.SLOWED,
        until=When.SAVE_ENDS,
        escalate=lambda eff: c.unconscious(on=foe, until=When.SAVE_ENDS),
    )


@power(
    "i1820x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1820x1(c: Cast) -> None:
    """A basic attack is at-will, so the two halves of the printed list are
    one gate. Whether a stance is up is asked when the modifier is read,
    which is the moment the card means."""

    def gate(ctx: dict[str, Any]) -> bool:
        if c.world.effects.stance_of(c.me) is None:
            return False
        p = get(ctx.get("power") or "")
        return p is not None and p.usage is Usage.AT_WILL

    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=gate)


@power(
    "i1820p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.stance(keep=)",),
)
def i1820p1(c: Cast) -> None:
    """Two stances at once. `c.stance` ends whatever you were in by
    definition and at most one is ever live."""


@power(
    "i1840x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.in_form()",),
)
def i1840x1(c: Cast) -> None:
    """Pays out only while a particular kind of shape is held. `c.form`
    installs one and nothing asks which one is on."""


@power(
    "i1846x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("Keyword.CHANNEL_DIVINITY",),
)
def i1846x1(c: Cast) -> None:
    """Rides on a class of powers the keyword list does not have a word
    for, so there is nothing to recognise on `PowerUsed`."""


@power(
    "i1846p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    todo=("Keyword.CHANNEL_DIVINITY",),
)
def i1846p1(c: Cast) -> None:
    """Hands back a use of that same class of powers. `c.restore_use` needs
    a ref and the group cannot be named."""


@power(
    "i1924p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i1924p1(c: Cast) -> None:
    """"Per plus" is the item's own enhancement, never a written number."""
    c.bonus(
        "damage",
        0,
        dice=f"{max(1, c.enhancement)}d6",
        on=c.me,
        until=When.ENCOUNTER,
        once=True,
        when=lambda ctx: ctx.get("target") is not None
        and c.marked(on=ctx["target"]),
    )


@power(
    "i1935p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy provokes an opportunity attack",
    on=Trigger(
        OpportunityWindow,
        lambda world, me, ev: ev.actor == me,
        "an enemy provokes you",
    ),
)
def i1935p1(c: Cast) -> None:
    """The window names both ends, so the extra swing goes at the creature
    that provoked and nowhere else."""
    who = getattr(c.trigger, "provoker", None)
    if who is not None:
        c.basic(on=who)


@power(
    "i2185p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="an enemy hits you with a melee or a close attack",
    on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits you in melee"),
)
def i2185p1(c: Cast) -> None:
    """`by_melee` counts close bursts and blasts as melee, which is the
    printed pair."""
    foe = c.target
    if foe is None:
        return
    c.no_provoke(on=c.me, until=When.EOT)
    if c.basic(on=foe, ranged=True):
        c.push(2, on=foe)


@power(
    "i2409x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2409x1(c: Cast) -> None:
    """A holy symbol is an implement by another name."""
    c.as_implement(on=c.me)


@power(
    "i2409p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you score a critical hit against a target",
    on=Trigger(Hit, _crit_by_me, "you score a critical hit"),
    dropped=("c.forgo_crit()",),
)
def i2409p1(c: Cast) -> None:
    """The trade is one-sided here: the crit rider is applied by the
    critical itself and nothing declines it, so the wielder keeps the
    damage and gets the hold as well."""
    c.condition(Condition.DOMINATED, until=When.EONT)


@power(
    "i2418x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.deals(when=)",),
)
def i2418x1(c: Cast) -> None:
    """"An attack power that doesn't have a damage type" is a gate
    `c.deals` cannot take, so every swing comes out typed. The deafening
    half is exact."""
    c.deals(DamageType.THUNDER, on=c.me, until=When.ENCOUNTER)

    def on_hit(ev: Hit) -> None:
        if ev.attacker == c.me:
            c.condition(Condition.DEAFENED, on=ev.target, until=When.EONT)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i2418p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you hit an enemy with this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i2418p1(c: Cast) -> None:
    foe = c.target
    if foe is None:
        return
    c.vulnerable(5, DamageType.THUNDER, until=When.SAVE_ENDS)
    for e in c.within(1, of=foe):
        if e == foe:
            continue
        c.condition(Condition.DEAFENED, on=e, until=When.EONT)
        c.vulnerable(5, DamageType.THUNDER, on=e, until=When.EONT)


@power(
    "i2486x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2486x1(c: Cast) -> None:
    c.bonus(AC, 1, kind="shield", on=c.me, until=When.ENCOUNTER)


@power(
    "i2694p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    trigger="you hit an enemy with a lightning or thunder power",
    on=Trigger(
        Hit,
        both(by_me, either(by_keyword(Keyword.LIGHTNING), by_keyword(Keyword.THUNDER))),
        "you hit with a lightning or thunder power",
    ),
)
def i2694p1(c: Cast) -> None:
    """"Save ends both" is one hold carrying the condition and the burn
    together, so a single throw shakes off both or neither."""
    c.prone()
    c.condition(
        Condition.DEAFENED,
        until=When.SAVE_ENDS,
        ongoing=(5, DamageType.LIGHTNING),
    )


@power(
    "i2723x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i2723x1(c: Cast) -> None:
    """Light and darkness are not modelled. Inert by choice."""
    c.note("i2723x1: sheds bright or dim light out to 20 squares, at will")


@power(
    "i2723p1",
    level=4,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.RADIANT],
    dropped=("c.deals(revert=)",),
)
def i2723p1(c: Cast) -> None:
    c.deals(DamageType.RADIANT, on=c.me, until=When.ENCOUNTER)


@power(
    "i2723p2",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(STR, vs=REF),
)
def i2723p2(c: Cast) -> None:
    """The enhancement rides on the roll as a printed extra, which
    `c.strike(plus=)` takes without inventing a modifier for it."""
    if c.strike(plus=c.enhancement):
        c.damage("1d8", dtype=DamageType.RADIANT)


@power(
    "i2729p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a ranged attack using this weapon",
    on=Trigger(Hit, both(by_me, by_ranged), "you hit with a ranged attack"),
    todo=("c.cannot_attack(when=)",),
)
def i2729p1(c: Cast) -> None:
    """A bar on attacking measured by distance from a third creature.
    `c.cannot_attack` bars everything or one named victim and takes no
    gate, so either reading would be far wider or far narrower than the
    card."""


@power(
    "i2842x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.bull_rush()",),
)
def i2842x1(c: Cast) -> None:
    """Adds to a bull rush attempt, and nothing makes one."""


@power(
    "i2842p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(STR, vs=FORT),
)
def i2842p1(c: Cast) -> None:
    if c.strike(plus=c.enhancement):
        c.prone()


@power(
    "i2853p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2853p1(c: Cast) -> None:
    """A penalty takes no bonus type, by the rule."""
    for d in (AC, FORT, REF, WILL):
        c.penalty(d, 2, until=When.SAVE_ENDS)


@power(
    "i2878p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.THUNDER],
    todo=("c.next_attack_becomes()",),
)
def i2878p1(c: Cast) -> None:
    """Rewrites the next basic attack into a burst against a different
    defence. `c.widen_areas` grows an area a power already has; nothing
    turns a single-target attack into one."""


@power(
    "i2901p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a class attack power using this dagger",
    on=Trigger(Hit, by_me, "you hit an enemy with this dagger"),
    dropped=("by_class()",),
)
def i2901p1(c: Cast) -> None:
    """The parity is chosen when the daily is spent rather than per later
    hit, because a hold cannot ask a question at the moment it is read."""
    pick = c.choose(["even", "odd"], "which way the rolls should read")
    if pick is not None:
        c.treat_roll_as(pick, on=c.me, until=When.ENCOUNTER)


@power(
    "i2941x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.silvered()",),
)
def i2941x1(c: Cast) -> None:
    """What a weapon is made of is not a thing the engine holds, and the
    whole content of this property is the material."""


@power(
    "i2941p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    todo=("c.retarget_defence()", "c.refund_use()"),
)
def i2941p1(c: Cast) -> None:
    """Sends an attack at a defence of your choosing, and hands the daily
    back on a miss. The defence is read off the power's own `Attack` line
    before the roll, and nothing un-spends a use."""


@power(
    "i2946x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.penalty(against=)",),
)
def i2946x1(c: Cast) -> None:
    """Which effect the penalised saving throw is against cannot be named,
    so the penalty applies to the target's next save whatever it is for."""
    c.as_implement(on=c.me)
    plus = c.enhancement

    def on_hit(ev: Hit) -> None:
        if ev.attacker == c.me:
            c.penalty("save", plus, on=ev.target, until=When.EONT)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i2946p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    trigger="you hit an enemy using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i2946p1(c: Cast) -> None:
    """"While the target is taking this damage" is written as the same
    duration rather than as a live question about the burn, which is the
    same span in every case but a save that ends it early."""
    foe = c.target
    if foe is None:
        return
    c.ongoing(5, DamageType.THUNDER)
    c.bonus(
        "attack",
        2,
        kind="item",
        on=c.me,
        until=When.SAVE_ENDS,
        when=_aimed_at(foe),
    )


@power(
    "i2959x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("Bloodied.source",),
)
def i2959x1(c: Cast) -> None:
    """"Whenever *you* bloody an enemy" -- and the event that says a
    creature has been bloodied names only the creature, so which side did
    it cannot be read."""


@power(
    "i2959p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
    todo=("c.ignore_resistance()",),
)
def i2959p1(c: Cast) -> None:
    """Damage that bypasses resistance and immunity. `c.resist` grants
    resistance and `c.vulnerable` offsets it; neither bypasses."""


@power(
    "i2990x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2990x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i2990p1",
    level=4,
    cls=ITEM,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i2990p1(c: Cast) -> None:
    """Light is not modelled. Inert by choice."""
    c.note("i2990p1: bright light out to 4 squares until ended")


@power(
    "i2990p2",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an ally adjacent to you is attacked by an enemy adjacent to you",
    on=Trigger(
        AttackDeclared,
        lambda world, me, ev: (
            ev.target != me
            and ev.target in query.allies(world, me)
            and query.adjacent(world, me, ev.target)
            and query.adjacent(world, me, ev.attacker)
        ),
        "an adjacent enemy swings at an adjacent ally",
        window=Window.BEFORE,
    ),
)
def i2990p2(c: Cast) -> None:
    """Declared `SELF`, because the printed effect is about you and the
    ally rather than about the attacker the auto-targeter would pick."""
    ev = c.trigger
    ally = getattr(ev, "target", None)
    foe = getattr(ev, "attacker", None)
    if ally is not None:
        c.swap(ally)
    if foe is not None:
        c.grants_advantage(on=foe, until=When.EONT)


@power(
    "i3053p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an arcane attack power using this weapon",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.ARCANE)), "you hit with an arcane power"
    ),
)
def i3053p1(c: Cast) -> None:
    c.mark(until=When.SAVE_ENDS)


@power(
    "i3058p1",
    level=4,
    cls=ITEM,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.LIGHTNING],
    attack=Attack(STR, vs=AC),
)
def i3058p1(c: Cast) -> None:
    """"Reach one greater than normal" is the row's own reach line, so it
    is declared rather than granted. Routed through `c.strike` rather than
    `c.basic`, because the extra square and the damage type are both
    properties of *this* swing."""
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.LIGHTNING)


@power(
    "i3058p2",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i3058p2(c: Cast) -> None:
    foe = c.target
    if foe is None:
        return
    c.push(2)
    c.damage("1d8", dtype=DamageType.LIGHTNING)
    for e in c.within(1, of=foe):
        if e != foe:
            c.damage("1d8", dtype=DamageType.LIGHTNING, on=e)


@power(
    "i3059x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.oath()",),
)
def i3059x1(c: Cast) -> None:
    """Which enemy a class feature has sworn against is not a relation the
    board keeps, so any kill arms the rider."""
    c.as_implement(on=c.me)
    dice = f"{max(1, c.enhancement)}d6"

    def on_kill(ev: Dropped) -> None:
        if ev.source == c.me:
            c.bonus("damage", 0, dice=dice, on=c.me, until=When.EONT, once=True)

    c.watch(Dropped, on_kill, until=When.ENCOUNTER)


@power(
    "i3092x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("EffectApplied.ongoing",),
)
def i3092x1(c: Cast) -> None:
    """The hold announces that it is save-ends but not what it carries, so
    "untyped ongoing damage" cannot be told from any other save-ends
    effect, and the penalty is laid on all of them."""
    plus = c.enhancement

    def on_hold(ev: EffectApplied) -> None:
        if ev.source == c.me and ev.save_ends:
            c.penalty("save", plus, on=ev.target, until=When.SAVE_ENDS)

    c.watch(EffectApplied, on_hold, until=When.ENCOUNTER)


@power(
    "i3092p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i3092p1(c: Cast) -> None:
    c.ongoing(5)


@power(
    "i3141x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3141x1(c: Cast) -> None:
    plus = c.enhancement

    def on_kill(ev: Dropped) -> None:
        if ev.source == c.me:
            c.temp_hp(5 + plus, on=c.me)

    c.watch(Dropped, on_kill, until=When.ENCOUNTER)


@power(
    "i3141p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i3141p1(c: Cast) -> None:
    """The heal is the damage the card actually dealt, not the number it
    was asked for -- resistance and immunity come off first."""
    dealt = c.flat(2 + c.enhancement, dtype=DamageType.NECROTIC)
    c.heal(dealt, on=c.me)


@power(
    "i3150x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3150x1(c: Cast) -> None:
    c.bonus(
        "skill:perception", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
    )


@power(
    "i3150p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.truesight(sustain=)",),
)
def i3150p1(c: Cast) -> None:
    """Knowing where the hidden are is truesight with a radius; the
    printed "Sustain Minor" has nowhere to attach, because neither verb
    takes a sustain cost."""
    c.see_invisible(on=c.me, until=When.EONT)
    c.truesight(5, on=c.me, until=When.EONT)


@power(
    "i3151p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(5),
    target=Target(side="ally", count=2),
    keywords=[Keyword.TELEPORTATION],
    dropped=("c.hit_this_turn()",),
)
def i3151p1(c: Cast) -> None:
    """The Requirement -- you must already have hit somebody this turn --
    is a fact about the turn that nothing records, so the row is freely
    usable and the enemy is chosen rather than remembered."""
    foes = c.enemies()
    if not foes:
        return
    foe = c.choose(foes, "who the allies arrive beside")
    spots = _free_beside(c, foe)
    if spots and c.target is not None:
        c.teleport(20, who=c.target, to=spots[0])


@power(
    "i3152x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3152x1(c: Cast) -> None:
    c.resist(1, on=c.me, until=When.ENCOUNTER)


@power(
    "i3152p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you take damage from a melee attack that hits you",
    on=Trigger(
        DamageRolled,
        both(targets_me, by_melee),
        "a melee attack is about to hurt you",
        window=Window.BEFORE,
    ),
)
def i3152p1(c: Cast) -> None:
    """Answered on the roll rather than on the application: by the time
    the damage has landed there is nothing left to halve."""
    c.halve()


@power(
    "i3153p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    trigger="you hit an adjacent enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an adjacent enemy with this weapon"),
)
def i3153p1(c: Cast) -> None:
    c.push(5)
    c.immobilized(until=When.SAVE_ENDS)


@power(
    "i3427x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3427x1(c: Cast) -> None:
    """"One or more targets" needs no once-per-use guard: temporary hit
    points do not add, the larger simply stands."""
    plus = c.enhancement

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        p = get(ev.power)
        if p is not None and set(_ELEMENTAL) & set(p.keywords):
            c.temp_hp(1 + plus, on=c.me)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i3427p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(2),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
    trigger="you use your second wind on your turn",
    on=Trigger(SurgeSpent, lambda world, me, ev: ev.actor == me, "you spend a surge"),
    dropped=("c.on_second_wind()",),
)
def i3427p1(c: Cast) -> None:
    """A second wind announces only that a surge went, which every other
    surge announces too -- so any surge of the wielder's arms this. "For
    your enemies" is the zone plus a waiver for your own side."""
    z = c.zone(spread({c.here}, 2), difficult=True, until=When.EONT)
    c.ignores_difficult_in(z, side="ally")


@power(
    "i3428x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3428x1(c: Cast) -> None:
    plus = c.enhancement

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        p = get(ev.power)
        if p is None or Keyword.FIRE not in p.keywords:
            return
        near = c.within(1, side="enemy")
        if near:
            c.flat(1 + plus, dtype=DamageType.FIRE, on=near[0])

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i3428p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
    trigger="you use your second wind on your turn",
    on=Trigger(SurgeSpent, lambda world, me, ev: ev.actor == me, "you spend a surge"),
    dropped=("c.on_second_wind()", "c.bonus(dtype=)"),
)
def i3428p1(c: Cast) -> None:
    """The melee half of the gate is readable off the power's reach; the
    extra damage keeps the blow's own type, because nothing types a
    modifier."""
    c.bonus(
        "damage", c.enhancement, on=c.me, until=When.EONT, when=_melee_damage
    )


@power(
    "i3430x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3430x1(c: Cast) -> None:
    """"You can", so it is offered rather than forced."""
    step = max(1, c.enhancement // 2)

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        p = get(ev.power)
        if p is not None and set(_ELEMENTAL) & set(p.keywords) and c.may("shift"):
            c.shift(step)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i3430p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you use your second wind on your turn",
    on=Trigger(SurgeSpent, lambda world, me, ev: ev.actor == me, "you spend a surge"),
    dropped=("c.on_second_wind()",),
)
def i3430p1(c: Cast) -> None:
    near = [w for w in c.within(5) if w != c.me]
    if near:
        c.pull(4, on=c.choose(near, "who is dragged in"))


@power(
    "i3486x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.half_damage(when=)",),
)
def i3486x1(c: Cast) -> None:
    """A natural 1 is read off the roll, which carries it. Halving your own
    damage against one sort of creature has no verb: `c.half_damage` is a
    miss line and takes no gate."""
    c.bonus(
        "damage",
        0,
        dice=c.w(),
        on=c.me,
        until=When.ENCOUNTER,
        when=_against(c, "undead"),
    )

    def fumble(ev: AttackRolled) -> None:
        if ev.attacker != c.me or ev.natural != 1:
            return
        c.condition(on=c.me, until=When.SAVE_ENDS, ongoing=(10, DamageType.UNTYPED))
        c.penalty("attack", 2, on=c.me, until=When.SAVE_ENDS)

    c.watch(AttackRolled, fumble, until=When.ENCOUNTER)


@power(
    "i3486p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit a creature with a melee attack using this weapon",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def i3486p1(c: Cast) -> None:
    c.ongoing(5)


@power(
    "i3505x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3505x1(c: Cast) -> None:
    """The retaliation is armed per heal and torn down with the duration
    the card gives it, so two heals in a round do not compound."""
    c.as_implement(on=c.me)
    plus = c.enhancement

    def on_heal(ev: Healed) -> None:
        if ev.source != c.me or ev.target == c.me:
            return
        mended = ev.target

        def spite(hit: Hit) -> None:
            if hit.target != mended:
                return
            p = get(hit.power)
            if p is not None and p.reach is not None and p.reach.kind == "melee":
                c.flat(plus, on=hit.attacker)

        c.watch(Hit, spite, until=When.EONT)

    c.watch(Healed, on_heal, until=When.ENCOUNTER)


@power(
    "i447p1",
    level=4,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.ACID],
    attack=Attack(STR, vs=AC),
)
def i447p1(c: Cast) -> None:
    """Declared as its own melee row with the printed reach rather than
    routed through `c.basic`, because the reach and the damage type are
    both this swing's."""
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.ACID)


@power(
    "i447p2",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i447p2(c: Cast) -> None:
    c.ongoing(5, DamageType.ACID)


@power(
    "i571x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i571x1(c: Cast) -> None:
    c.bonus("damage", 0, dice=c.w(), on=c.me, until=When.ENCOUNTER, when=_charging)


@power(
    "i605p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    trigger="you hit a target with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i605p1(c: Cast) -> None:
    """"Each creature adjacent to *you*" -- friend and foe alike, and the
    wielder's own square is not adjacent to itself."""
    for e in c.within(1):
        if e != c.me:
            c.flat(5, dtype=DamageType.FIRE, on=e)
    c.push(1)


@power(
    "i625x1",
    level=4,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i625x1(c: Cast) -> None:
    c.bonus(
        "damage",
        0,
        dice="1d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=c.me),
    )


@power(
    "i625p1",
    level=4,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.considered_bloodied()", "c.flat(unpreventable=)"),
)
def i625p1(c: Cast) -> None:
    """The self-harm lands; resistance still eats it, which the card says
    it should not. Being bloodied without having lost the hit points has no
    spelling, so a wielder who does not cross the line gets the cut and
    none of the benefit."""
    c.flat(c.level // 2, on=c.me)


@power(
    "i939p1",
    level=4,
    cls=ITEM,
    action=FREE,
    reach=Ranged(5),
    target=NO_TARGET,
    todo=("c.boost_roll()",),
)
def i939p1(c: Cast) -> None:
    """Adds to any d20 an ally has already rolled. `c.boost_check` does it
    for a skill check alone, and an attack roll has only a reroll."""


# -- level 5 ----------------------------------------------------------------


@power(
    "i1167x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1167x1(c: Cast) -> None:
    """Answered on the hold landing rather than on the hit, and guarded
    against re-entry: raising a burn lays another hold, which is the same
    event again."""
    busy = {"in": False}

    def on_hold(ev: EffectApplied) -> None:
        if ev.source != c.me or busy["in"]:
            return
        busy["in"] = True
        try:
            _raise_ongoing(c, ev.target, 2)
        finally:
            busy["in"] = False

    c.watch(EffectApplied, on_hold, until=When.ENCOUNTER)


@power(
    "i1266p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def i1266p1(c: Cast) -> None:
    """Declared as a ranged row with the melee weapon's own dice rather
    than routed through `c.basic(ranged=True)`, which would look for a
    ranged weapon the wielder does not have."""
    if c.strike():
        c.damage(c.w(), c.str_mod)


@power(
    "i1266p2",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i1266p2(c: Cast) -> None:
    foe = c.target
    spots = _free_beside(c, c.me)
    if foe is not None and spots:
        c.teleport(10, who=foe, to=spots[0])


@power(
    "i1284p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="an enemy hits you with a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits you in melee"),
)
def i1284p1(c: Cast) -> None:
    c.basic(on=c.target)


@power(
    "i1306p1",
    level=5,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
    dropped=("c.deals(revert=)",),
)
def i1306p1(c: Cast) -> None:
    c.deals(DamageType.FIRE, on=c.me, until=When.ENCOUNTER)


@power(
    "i1306p2",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1306p2(c: Cast) -> None:
    c.damage("1d6", dtype=DamageType.FIRE)
    c.ongoing(5, DamageType.FIRE)


@power(
    "i1317p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
    dropped=("c.considered_bloodied()",),
)
def i1317p1(c: Cast) -> None:
    """Being bloodied is read off hit points everywhere, so pretending at
    it has no spelling; the burn is the half that lands."""
    c.ongoing(5)


@power(
    "i1711x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1711x1(c: Cast) -> None:
    """Two halves, both per target. The miss stack is torn down the moment
    you swing at somebody else or land one; the hit bonus is a one-shot
    spent on the next roll against the same creature."""
    count: dict[int, int] = {}
    holds: dict[int, Effect] = {}

    def drop(keep: int | None) -> None:
        for who in list(holds):
            if who != keep:
                c.world.effects.end(holds.pop(who), "i1711x1")
                count.pop(who, None)

    def on_miss(ev: Miss) -> None:
        if ev.attacker != c.me:
            return
        foe = ev.target
        drop(foe)
        if count.get(foe, 0) >= max(1, c.enhancement):
            return
        old = holds.pop(foe, None)
        if old is not None:
            c.world.effects.end(old, "i1711x1")
        count[foe] = count.get(foe, 0) + 1
        fresh = c.bonus(
            "attack",
            count[foe],
            kind="power",
            on=c.me,
            until=When.ENCOUNTER,
            when=_aimed_at(foe),
        )
        if fresh is not None:
            holds[foe] = fresh

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        drop(None)
        c.bonus(
            "damage",
            2,
            kind="power",
            on=c.me,
            until=When.EONT,
            once=True,
            when=_aimed_at(ev.target),
        )

    c.watch(Miss, on_miss, until=When.ENCOUNTER)
    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i1730x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1730x1(c: Cast) -> None:
    """The downfall event names who struck the blow but not with what; the
    item is melee-only, so the melee half of the line is the base item's
    restriction rather than a gate."""

    def on_kill(ev: Dropped) -> None:
        if ev.source == c.me:
            c.temp_hp(5, on=c.me)

    c.watch(Dropped, on_kill, until=When.ENCOUNTER)


@power(
    "i1739p1",
    level=5,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.LIGHTNING],
    dropped=("c.deals(revert=)",),
)
def i1739p1(c: Cast) -> None:
    c.deals(DamageType.LIGHTNING, on=c.me, until=When.ENCOUNTER)


@power(
    "i1739p2",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1739p2(c: Cast) -> None:
    foe = c.target
    if foe is None:
        return
    c.damage("1d6", dtype=DamageType.LIGHTNING)
    for e in c.within(2, of=foe, side="enemy"):
        if e != foe:
            c.damage("1d6", dtype=DamageType.LIGHTNING, on=e)


@power(
    "i1861x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1861x1(c: Cast) -> None:
    c.bonus(
        "damage",
        2,
        kind="item",
        on=c.me,
        until=When.ENCOUNTER,
        when=_of_keyword(Keyword.PSYCHIC),
    )


@power(
    "i1861p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    trigger="you hit an enemy with a psychic attack using this weapon",
    on=Trigger(
        Hit, both(by_me, by_keyword(Keyword.PSYCHIC)), "you hit with a psychic power"
    ),
)
def i1861p1(c: Cast) -> None:
    c.ongoing(5, DamageType.PSYCHIC)


@power(
    "i1905x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1905x1(c: Cast) -> None:
    """The attack context has no `vs`, so which defence is being attacked
    is read off the power's own printed line."""

    def gate(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power") or "")
        if p is None or p.attack is None or p.attack.vs is not FORT:
            return False
        foe = ctx.get("target")
        if foe is None:
            return False
        return not (c.kinds_of(on=foe) & {"undead", "construct"})

    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=gate)


@power(
    "i1905p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1905p1(c: Cast) -> None:
    c.damage("1d8", dtype=DamageType.NECROTIC)
    c.weakened(until=When.EONT)


@power(
    "i2062p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2062p1(c: Cast) -> None:
    """"Save ends both" is one hold carrying the condition and the burn."""
    c.condition(
        Condition.WEAKENED,
        until=When.SAVE_ENDS,
        ongoing=(5, DamageType.POISON),
    )


@power(
    "i2132x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.surprise_round()",),
)
def i2132x1(c: Cast) -> None:
    """Both halves hang on the round being the surprise one. `Encounter`
    keeps the round number and nothing says which round was the ambush."""


@power(
    "i2357x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2357x1(c: Cast) -> None:
    """`c.grant_action` understands standing up, which is the one thing
    this hands out; anything else it would silently swallow."""

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        for a in c.allies():
            if c.can_see(a):
                c.grant_action("stand", ActionType.FREE, on=a, until=When.EOT)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i2367x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2367x1(c: Cast) -> None:
    plus = c.enhancement

    def on_hit(ev: Hit) -> None:
        if ev.attacker != c.me:
            return
        p = get(ev.power)
        if p is not None and Keyword.ARCANE in p.keywords:
            c.temp_hp(plus, on=c.me)

    c.watch(Hit, on_hit, until=When.ENCOUNTER)


@power(
    "i2437p1",
    level=5,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.CONJURATION],
    trigger="you slay a living creature with an attack using this weapon",
    on=Trigger(Dropped, _killed_by_me, "you drop an enemy with this weapon"),
    dropped=("c.conjure(defences=)",),
)
def i2437p1(c: Cast) -> None:
    """A conjuration that can be moved is `c.conjure(speed=)`; what cannot
    be said is a body with defences of 10 and no hit points that any
    damaging hit destroys."""
    slain = getattr(c.trigger, "actor", None)
    if slain is None:
        return
    spots = _free_beside(c, slain)
    c.conjure(
        at=spots[0] if spots else None,
        label=c.ref,
        until=When.ENCOUNTER,
        sustain=None,
        speed=5,
        solid=True,
    )


@power(
    "i2437p2",
    level=5,
    cls=ITEM,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.NECROTIC],
)
def i2437p2(c: Cast) -> None:
    """Everything the wielder has standing on the board is taken to be one
    of these: nothing reads a conjuration's label back."""
    standing = c.my_zones()
    caught = {
        w
        for z in standing
        for w in (*c.enemies(), *c.allies(), c.me)
        if c.adjacent_to(z, w)
    }
    for w in caught:
        c.flat(5, dtype=DamageType.NECROTIC, on=w)
    for z in standing:
        c.dispel(z)


@power(
    "i2855x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2855x1(c: Cast) -> None:
    def on_kill(ev: Dropped) -> None:
        if ev.source != c.me:
            return
        for w in (c.me, *c.within(1, side="ally")):
            c.bonus(
                "attack", 2, kind="item", on=w, until=When.ENCOUNTER, once=True
            )

    c.watch(Dropped, on_kill, until=When.ENCOUNTER)


@power(
    "i2866p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy that is taking ongoing damage",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i2866p1(c: Cast) -> None:
    """"Increase it by 5" is written by reading what is standing and laying
    a stronger burn of the same type, which supersedes it -- the only hold
    the stacking rule leaves."""
    foe = c.target
    if foe is not None:
        _raise_ongoing(c, foe, 5)


@power(
    "i2867p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    out_of_combat=True,
)
def i2867p1(c: Cast) -> None:
    """Picking a pocket has no combat consequence, so the row is
    deliberately inert -- but the check is still rolled, because the bonus
    is the whole of what the item adds."""
    c.check("thievery", bonus=c.enhancement)


@power(
    "i2871p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i2871p1(c: Cast) -> None:
    amount = c.enhancement
    if c.points_spent(c.ref) >= 2:
        amount += c.roll("1d10")
    for e in c.enemies():
        if c.marked(on=e):
            c.flat(amount, dtype=DamageType.PSYCHIC, on=e)


@power(
    "i2976p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="an attack hits a bloodied ally within 10 squares of you",
    on=Trigger(Hit, _hurt_bloodied_ally, "a bloodied ally near you is hit"),
)
def i2976p1(c: Cast) -> None:
    """Declared `SELF`: the event's target is the ally, so a single-target
    enemy row would be aimed at the wrong end of it."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.bonus(
        "attack", 2, kind="power", on=c.me, until=When.EONT, when=_aimed_at(foe)
    )
    c.bonus(
        "damage",
        0,
        dice="1d10",
        kind="power",
        on=c.me,
        until=When.EONT,
        when=_aimed_at(foe),
    )


@power(
    "i3056p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with an opportunity attack",
    on=Trigger(
        Hit, both(by_me, by_opportunity), "you hit with an opportunity attack"
    ),
)
def i3056p1(c: Cast) -> None:
    c.damage("1d8")


@power(
    "i3085p1",
    level=5,
    cls=ITEM,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="an enemy hits you with an opportunity attack",
    on=Trigger(
        Hit, both(targets_me, by_opportunity), "an opportunity attack hits you"
    ),
    dropped=("by_class()",),
)
def i3085p1(c: Cast) -> None:
    """What provoked the opening cannot be asked, so any opportunity attack
    that lands on the wielder arms it."""
    c.flat(5)


@power(
    "i3085p2",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    todo=("c.origin_of()",),
)
def i3085p2(c: Cast) -> None:
    """Moves where a close attack comes from. `Range.from_` names the
    origin as a column on the power and no body moves it."""


@power(
    "i3157x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3157x1(c: Cast) -> None:
    """`c.initiative` carries no bonus type; nothing reads an
    `"initiative"` modifier, so a typed `c.bonus` would be ignored."""
    c.initiative(c.enhancement, on=c.me)


@power(
    "i3157p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def i3157p1(c: Cast) -> None:
    c.basic(on=c.target, ranged=True)


@power(
    "i3408x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3408x1(c: Cast) -> None:
    """A holy symbol is an implement by another name. The ritual bonus is
    not a fight and is left as a note."""
    c.as_implement(on=c.me)
    c.note("i3408x1: a bonus to skill checks made as part of a ritual")


@power(
    "i3408p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    trigger="you hit an enemy with an attack using this dagger",
    on=Trigger(Hit, by_me, "you hit an enemy with this dagger"),
    dropped=("c.ignore_resistance()",),
)
def i3408p1(c: Cast) -> None:
    """The burn lands; that it should get past a resistance or an immunity
    cannot be said."""
    c.ongoing(5, DamageType.POISON)


@power(
    "i3408p2",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i3408p2(c: Cast) -> None:
    """The whole payout is a bonus to a ritual performed later. Inert by
    choice."""
    c.note("i3408p2: a bonus to the next ritual's skill checks")


@power(
    "i3452x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3452x1(c: Cast) -> None:
    """Whether a creature was a minion is not asked: its hit points are in
    the database and the downfall event says nothing about them."""
    c.initiative(c.enhancement, on=c.me)
    plus = c.enhancement

    def on_kill(ev: Dropped) -> None:
        if ev.source == c.me:
            c.temp_hp(5 + plus, on=c.me)

    c.watch(Dropped, on_kill, until=When.ENCOUNTER)


@power(
    "i3452p1",
    level=5,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i3452p1(c: Cast) -> None:
    """"Against the enemy" is a gate on a defence read, and the attack
    context handed to `query.defence` carries who is swinging."""
    foe = c.target
    if foe is None:
        return
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, kind="power", on=c.me, until=When.EONT, when=_swung_by(foe))


@power(
    "i3487x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3487x1(c: Cast) -> None:
    """A natural 1 is read off the roll, which carries it. The victim is
    drawn from the world's own dice rather than offered as a choice: the
    card says random, and a policy asked to choose would pick the best."""

    def fumble(ev: AttackRolled) -> None:
        if ev.attacker != c.me or ev.natural != 1:
            return
        near = [w for w in c.within(5)]
        if not near:
            return
        pick = near[c.world.rng.roll(f"1d{len(near)}").total - 1]
        c.basic(on=pick, ranged=True)

    c.watch(AttackRolled, fumble, until=When.ENCOUNTER)


@power(
    "i3487p1",
    level=5,
    cls=ITEM,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
)
def i3487p1(c: Cast) -> None:
    """A flat attack bonus off the item's own level, rolled in the body --
    `Attack(printed=)` would take the character's level term back out."""
    if c.attack(get(c.ref).level + 3, REF).hit:
        c.damage("2d8", dtype=DamageType.FIRE)


@power(
    "i456p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you drop an undead enemy to 0 hit points",
    on=Trigger(Dropped, _killed_by_me, "you drop an enemy"),
)
def i456p1(c: Cast) -> None:
    """Declared `SELF`: the downfall event names the fallen creature as its
    actor, and a single-target enemy row would be aimed at a corpse."""
    slain = getattr(c.trigger, "actor", None)
    if slain is not None and "undead" in c.kinds_of(on=slain):
        c.regain_surge(1, on=c.me)


@power(
    "i694x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("by_class()",),
)
def i694x1(c: Cast) -> None:
    """Rides on one named class row, given as a name rather than a ref, so
    there is nothing to watch for."""


@power(
    "i694p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i694p1(c: Cast) -> None:
    """"Your lowest-level arcane encounter attack power" is a question the
    spent list and the registry answer between them."""
    c.flat(2 * c.enhancement, dtype=DamageType.NECROTIC)
    spent = []
    for ref in c.expended():
        p = get(ref)
        if (
            p is not None
            and p.usage is Usage.ENCOUNTER
            and p.attack is not None
            and Keyword.ARCANE in p.keywords
        ):
            spent.append(p)
    if spent:
        c.restore_use(min(spent, key=lambda p: p.level).ref)


@power(
    "i778x1",
    level=5,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.cover_from()",),
)
def i778x1(c: Cast) -> None:
    """Damage to whichever creatures were granting the target cover cannot
    be said: `query.cover_between` answers how much cover there is, never
    who is giving it."""


@power(
    "i848p1",
    level=5,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=Melee(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(STR, vs=AC),
)
def i848p1(c: Cast) -> None:
    """Declared as its own melee row with the printed reach rather than
    routed through `c.basic`, which would measure the weapon's."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.prone()


# -- level 6 ----------------------------------------------------------------


@power(
    "i1153p1",
    level=6,
    cls=ITEM,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    todo=("c.reshape_weapon()",),
)
def i1153p1(c: Cast) -> None:
    """Becomes a different weapon, with different dice and a different
    group. `Weapon` is a column set no body rewrites."""


@power(
    "i1468x1",
    level=6,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.grab(bonus=)",),
)
def i1468x1(c: Cast) -> None:
    """A grab with a weapon, and a bonus to the attempt. `c.grab` simply
    takes hold -- there is no roll for a modifier to reach."""


@power(
    "i1468p1",
    level=6,
    cls=ITEM,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1468p1(c: Cast) -> None:
    c.pull(1)
    c.grab()


@power(
    "i2373p1",
    level=6,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2373p1(c: Cast) -> None:
    """The surge is spent and pays nothing back, which is exactly
    `c.spend_surge` rather than `c.surge`."""
    c.spend_surge(on=c.me)
    c.weakened(until=When.EONT)


# -- level 7 ----------------------------------------------------------------


@power(
    "i1078x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1078x1(c: Cast) -> None:
    """"Your melee reach" is the weapon in hand, read off it rather than
    assumed to be one square -- this base item has two. A curse is a
    relation the board keeps, so the rest of the line is exact."""
    span = _reach(c)

    def on_turn(ev: TurnStart) -> None:
        if ev.actor != c.me:
            return
        for e in c.within(span, side="enemy"):
            if c.cursed(on=e):
                c.flat(c.int_mod, dtype=DamageType.FIRE, on=e)

    c.watch(TurnStart, on_turn, until=When.ENCOUNTER)


@power(
    "i1078p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(2),
    target=ONE_CREATURE,
    trigger="you hit a cursed creature with this weapon",
    on=Trigger(Hit, both(by_me, cursed_by_me), "you hit a cursed enemy"),
)
def i1078p1(c: Cast) -> None:
    """"To all creatures" is as wide as the relation goes: it names one
    beneficiary at a time and `allies` is you and your side."""
    c.grants_advantage(until=When.SAVE_ENDS, to="allies")


@power(
    "i1079x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.bonus(against=)",),
)
def i1079x1(c: Cast) -> None:
    """A saving throw does not know what it is saving against, so the bonus
    applies to all of them rather than to one kind of attacker's."""
    c.bonus("save", c.enhancement, on=c.me, until=When.ENCOUNTER)


@power(
    "i1079p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    trigger="you hit a devil with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1079p1(c: Cast) -> None:
    """The creature's type words are the gate, and the board carries
    them."""
    if "devil" not in c.kinds_of():
        return
    c.damage("1d8", dtype=DamageType.RADIANT)
    c.blinded(until=When.SAVE_ENDS)


@power(
    "i1566x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1566x1(c: Cast) -> None:
    """`partial=True` is the lesser grade of the same scale, which is what
    "partial concealment" names."""
    c.ignore_cover(on=c.me, until=When.ENCOUNTER, partial=True)


@power(
    "i1566p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def i1566p1(c: Cast) -> None:
    """"The next attack" has no one-shot on this verb, so it is held to the
    end of the turn instead -- the same span for every attack routine and
    one shot too generous for two swings in a round."""
    c.ignore_cover(on=c.me, until=When.EOT, partial=True)


@power(
    "i1623p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.bonus(compute=)",),
)
def i1623p1(c: Cast) -> None:
    """The card counts the enemies afresh at each swing; a modifier carries
    a fixed number or a die expression and nothing else, so the count is
    taken once when the minor action is spent."""
    c.bonus(
        "damage",
        len(c.within(1, side="enemy")),
        on=c.me,
        until=When.EOT,
    )


@power(
    "i2052p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(2),
    target=ONE_CREATURE,
    trigger="you hit a target with this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i2052p1(c: Cast) -> None:
    c.ongoing(c.dex_mod + c.enhancement)


@power(
    "i2114x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def i2114x1(c: Cast) -> None:
    """Underwater penalties and ammunition are neither of them modelled.
    Inert by choice."""
    c.note("i2114x1: no underwater penalty, and it needs no arrows")


@power(
    "i2114p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you hit with a ranged attack using this weapon",
    on=Trigger(Hit, both(by_me, by_ranged), "you hit with a ranged attack"),
)
def i2114p1(c: Cast) -> None:
    c.push(2)
    c.prone()


@power(
    "i2183x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2183x1(c: Cast) -> None:
    """"Per plus" is the item's own enhancement, never a written number."""
    dice = f"{max(1, c.enhancement)}d6"

    def on_crit(ev: Hit) -> None:
        if ev.target != c.me or not ev.critical:
            return
        c.bonus(
            "damage",
            0,
            dice=dice,
            on=c.me,
            until=When.EONT,
            once=True,
            when=_aimed_at(ev.attacker),
        )

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i2579p1",
    level=7,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POISON],
    dropped=("c.deals(revert=)",),
)
def i2579p1(c: Cast) -> None:
    c.deals(DamageType.POISON, on=c.me, until=When.ENCOUNTER)


@power(
    "i2579p2",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2579p2(c: Cast) -> None:
    """`escalate` is the printed "First Failed Save", and it fires on every
    failed save rather than only the first -- which costs the target
    nothing it was not already going to suffer."""
    foe = c.target
    if foe is None:
        return
    c.condition(
        Condition.SLOWED,
        until=When.SAVE_ENDS,
        escalate=lambda eff: c.immobilized(on=foe, until=When.SAVE_ENDS),
    )


@power(
    "i2590p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2590p1(c: Cast) -> None:
    foe = c.target
    if foe is None:
        return
    near = [e for e in c.within(1, of=foe, side="enemy") if e != foe]
    if near:
        c.flat(c.dex_mod + c.enhancement, on=c.choose(near, "who else is caught"))


@power(
    "i2931p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2931p1(c: Cast) -> None:
    """"Continues to run its course as normal" is what moving the hold
    intact means, so this is `c.transfer` rather than a cure and a fresh
    application, which would restart the duration."""
    foe = c.target
    if foe is None:
        return
    mine = [
        e
        for e in c.world.effects.of(c.me)
        if e.conditions or e.ongoing is not None
    ]
    if mine:
        c.transfer(c.choose(mine, "what you pass on"), to=foe)


@power(
    "i2981x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("by_class()", "c.hit_twice()"),
)
def i2981x1(c: Cast) -> None:
    """Turns on hitting the same creature twice with one named class row.
    Neither half can be asked: nothing counts a use's hits per target and
    no predicate reads the class a power belongs to."""


@power(
    "i2981p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    todo=("by_class()", "c.hit_twice()"),
)
def i2981p1(c: Cast) -> None:
    """The same trigger as the property above, and the same two gaps."""


@power(
    "i3136x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3136x1(c: Cast) -> None:
    """`Size` is a string enum, so "Large or larger" is a rank comparison
    rather than a `>`."""

    def gate(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or "humanoid" not in c.kinds_of(on=foe):
            return False
        return _rank(c.size_of(on=foe)) > _rank(Size.MEDIUM)

    c.bonus(
        "damage", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER, when=gate
    )


@power(
    "i3136p1",
    level=7,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="a giant tries to push you, stun you, or knock you prone",
    on=(
        Trigger(ForcedMove, _giant_forces, "a giant pushes you", window=Window.BEFORE),
        Trigger(
            ConditionApplied,
            _giant_condition,
            "a giant stuns you or knocks you prone",
        ),
    ),
)
def i3136p1(c: Cast) -> None:
    """The printed line names three things, so all three are declared. The
    shove is a proposal and is refused outright; the two conditions are
    only announced after the fact, so they are lifted and then barred for
    the rest of the turn."""
    ev = c.trigger
    cond = getattr(ev, "condition", None)
    if cond is None:
        c.cancel()
        return
    c.cure(cond, on=c.me)
    c.immune(cond, on=c.me, until=When.EOT)


@power(
    "i3488x1",
    level=7,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i3488x1(c: Cast) -> None:
    """The item's level is its own header datum, read back rather than
    written out. Ammunition is not modelled."""
    hurt = get(c.ref).level

    def fumble(ev: AttackRolled) -> None:
        if ev.attacker != c.me or ev.natural != 1:
            return
        c.flat(hurt, on=c.me)
        c.condition(on=c.me, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))

    c.watch(AttackRolled, fumble, until=When.ENCOUNTER)


@power(
    "i3488p1",
    level=7,
    cls=ITEM,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
)
def i3488p1(c: Cast) -> None:
    """A flat attack bonus off the item's own level, rolled in the body."""
    if c.attack(get(c.ref).level + 3, AC).hit:
        c.damage("2d8")
        c.ongoing(5)


@power(
    "i709p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    todo=("Bloodied.source",),
)
def i709p1(c: Cast) -> None:
    """"*You* bloody an enemy" -- and the event that says a creature has
    been bloodied names only the creature, so which side did it cannot be
    read."""


@power(
    "i734p1",
    level=7,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def i734p1(c: Cast) -> None:
    """Declared as its own blast rather than routed through `c.basic`,
    which makes one swing at one creature."""
    if c.strike():
        c.damage(c.w(ranged=True), c.dex_mod)


# -- level 8 ----------------------------------------------------------------


@power(
    "i1048x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1048x1(c: Cast) -> None:
    def on_crit(ev: Hit) -> None:
        if ev.attacker == c.me and ev.critical:
            c.penalty(WILL, 2, on=ev.target, until=When.EONT)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i1048p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1048p1(c: Cast) -> None:
    c.penalty(WILL, 2, until=When.EONT)


@power(
    "i1075x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.weapon_range()",),
)
def i1075x1(c: Cast) -> None:
    """A change to the weapon's own range, and `Weapon.ranged` is a column
    no body can reach."""


@power(
    "i1075p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you miss with a ranged attack using this weapon",
    on=Trigger(Miss, both(by_me, by_ranged), "you miss with a ranged attack"),
)
def i1075p1(c: Cast) -> None:
    """The weapon not returning is bookkeeping with no consequence here.
    The delayed shot waits on the victim's own turn beginning, which is a
    watch rather than a duration."""
    foe = c.target
    if foe is None:
        return

    def later(ev: TurnStart) -> None:
        if ev.actor == foe:
            c.basic(on=foe, ranged=True)

    c.watch(TurnStart, later, until=When.EOTNT, once=True)


@power(
    "i1100x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1100x1(c: Cast) -> None:
    """A holy symbol is an implement by another name. The extra critical
    damage is a `crit_damage` modifier, which is the same key the printed
    column writes into, and it takes the damage context's gate."""
    c.as_implement(on=c.me)
    c.bonus(
        "crit_damage",
        0,
        dice="2d10",
        on=c.me,
        until=When.ENCOUNTER,
        when=_against(c, "undead"),
    )


@power(
    "i1100p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    trigger="you hit an undead creature with this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
)
def i1100p1(c: Cast) -> None:
    if "undead" in c.kinds_of():
        c.damage("2d10", dtype=DamageType.RADIANT)


@power(
    "i1128x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.penalty(checks=)",),
)
def i1128x1(c: Cast) -> None:
    """The defences are four modifiers; "and checks" is a fifth key that
    does not exist -- skill modifiers are read one skill at a time and
    there is no bucket for all of them."""
    plus = c.enhancement

    def on_crit(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical:
            return
        for d in (AC, FORT, REF, WILL):
            c.penalty(d, plus, on=ev.target, until=When.EONT)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i1128p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    trigger="you hit with this weapon",
    on=Trigger(Hit, by_me, "you hit with this weapon"),
    dropped=("c.penalty(checks=)",),
)
def i1128p1(c: Cast) -> None:
    """Same shape as the property above, and the same missing key."""
    for d in (AC, FORT, REF, WILL):
        c.penalty(d, c.enhancement, until=When.EONT)


@power(
    "i1159x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1159x1(c: Cast) -> None:
    def on_crit(ev: Hit) -> None:
        if ev.attacker != c.me or not ev.critical:
            return
        if c.kinds_of(on=ev.target) & {"earth", "plant"}:
            c.dazed(on=ev.target, until=When.EONT)

    c.watch(Hit, on_crit, until=When.ENCOUNTER)


@power(
    "i1159p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1159p1(c: Cast) -> None:
    """The penalty is part of the same hold rather than a second effect, so
    it is read by the saving throw that hold provokes."""
    earthy = bool(c.kinds_of() & {"earth", "plant"})
    c.condition(
        Condition.RESTRAINED,
        until=When.SAVE_ENDS,
        save_mod=-5 if earthy else 0,
    )


@power(
    "i1308p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def i1308p1(c: Cast) -> None:
    """`c.can_flank` is the modifier the flanking question reads to make an
    exception of somebody, which is exactly "you count as flanking whenever
    an ally is also adjacent"."""
    c.can_flank(on=c.me, until=When.EONT)


@power(
    "i1346p1",
    level=8,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FORCE],
    dropped=("c.deals(revert=)",),
)
def i1346p1(c: Cast) -> None:
    c.deals(DamageType.FORCE, on=c.me, until=When.ENCOUNTER)


@power(
    "i1346p2",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1346p2(c: Cast) -> None:
    c.slide(1)
    c.condition(Condition.RESTRAINED, until=When.EONT)


@power(
    "i1466p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    trigger="an enemy within your reach makes a melee attack against you",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_melee),
        "an enemy swings at you in melee",
    ),
)
def i1466p1(c: Cast) -> None:
    c.basic(on=c.target)


@power(
    "i1467x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.brutal()", "c.darkvision()"),
)
def i1467x1(c: Cast) -> None:
    """Rerolling the lowest damage dice is a weapon property with no verb,
    and sight in the dark is not a sense the board keeps."""


@power(
    "i1467p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    trigger="you hit with a melee attack",
    on=Trigger(Hit, both(by_me, by_melee), "you hit with a melee attack"),
)
def i1467p1(c: Cast) -> None:
    for e in c.within(1):
        if e != c.me:
            c.flat(5, dtype=DamageType.NECROTIC, on=e)


@power(
    "i1557x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i1557x1(c: Cast) -> None:
    c.bonus(
        "skill:intimidate", c.enhancement, kind="item", on=c.me, until=When.ENCOUNTER
    )


@power(
    "i1557p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.WEAPON],
    attack=Attack(CHA, vs=WILL),
    trigger="you reduce an enemy to 0 hit points with this weapon",
    on=Trigger(Dropped, _killed_by_me, "you drop an enemy with this weapon"),
)
def i1557p1(c: Cast) -> None:
    """The printed "+2 and the enhancement" rides on the roll rather than
    becoming a modifier. The daze is conditional on where the target ends
    its turn, which is a watch on the turn ending and not a duration."""
    if not c.strike(plus=2 + c.enhancement):
        return
    foe = c.target
    if foe is None:
        return
    c.penalty("attack", 2, on=foe, until=When.SAVE_ENDS)

    def at_end(ev: TurnEnd) -> None:
        if ev.actor == foe and c.adjacent(foe):
            c.dazed(on=foe, until=When.EOTNT)

    c.watch(TurnEnd, at_end, until=When.SAVE_ENDS)


@power(
    "i1672p1",
    level=8,
    cls=ITEM,
    usage=ENCOUNTER,
    action=ActionType.OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="an enemy misses you with a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "an enemy misses you in melee"),
)
def i1672p1(c: Cast) -> None:
    c.weakened(until=When.EOTNT)


@power(
    "i1687p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you score a critical hit against an enemy",
    on=Trigger(Hit, _crit_by_me, "you score a critical hit"),
)
def i1687p1(c: Cast) -> None:
    c.vulnerable(5, DamageType.NECROTIC, until=When.SAVE_ENDS)


@power(
    "i1688p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    todo=("Bloodied.source",),
)
def i1688p1(c: Cast) -> None:
    """"*You* bloody an enemy" -- and the event that says a creature has
    been bloodied names only the creature."""


@power(
    "i1839p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
    dropped=("c.steer()",),
)
def i1839p1(c: Cast) -> None:
    """Choosing the first square a creature moves to on its own turn cannot
    be said: a move is proposed and refused, never redirected."""
    if "construct" in c.kinds_of():
        c.damage("1d10")


@power(
    "i1874x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.teleport_bonus()",),
)
def i1874x1(c: Cast) -> None:
    """`c.forces` lengthens a push, a pull or a slide. A blink is none of
    those and nothing lengthens one."""


@power(
    "i1874p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i1874p1(c: Cast) -> None:
    foe = c.target
    if foe is not None:
        c.teleport(2, who=foe)


@power(
    "i1890p1",
    level=8,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ACID, Keyword.POISON],
    dropped=("c.deals(dtypes=)", "c.deals(revert=)"),
)
def i1890p1(c: Cast) -> None:
    """A blow of two types at once has no spelling: damage carries one
    `DamageType`. Retyped as the first of the pair."""
    c.deals(DamageType.ACID, on=c.me, until=When.ENCOUNTER)


@power(
    "i1890p2",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.POISON],
    attack=Attack(STR, vs=FORT),
    dropped=("c.damage(dtypes=)",),
)
def i1890p2(c: Cast) -> None:
    """A blow of two types at once has no spelling, so it lands as the
    first of the pair."""
    if c.strike():
        c.damage("2d8", c.str_mod, dtype=DamageType.ACID)


@power(
    "i2030x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2030x1(c: Cast) -> None:
    """The class half of the line is not enforced: the item was dealt to
    whoever is holding it."""
    c.as_implement(on=c.me)


@power(
    "i2030p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with a class attack power using this blade",
    on=Trigger(Hit, by_me, "you hit an enemy with this blade"),
    dropped=("by_class()",),
)
def i2030p1(c: Cast) -> None:
    foe = c.target
    if foe is None:
        return
    seers = [a for a in c.allies() if c.can_see(a)]
    if seers:
        c.bonus(
            "attack",
            4,
            kind="power",
            on=c.choose(seers, "who takes the opening"),
            until=When.ENCOUNTER,
            once=True,
            when=_aimed_at(foe),
        )


@power(
    "i2139x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2139x1(c: Cast) -> None:
    """Whether a creature was a minion is not asked: its hit points are in
    the database and the downfall event says nothing about them. "Either"
    is a genuine choice, so it is offered."""

    def on_kill(ev: Dropped) -> None:
        if ev.source != c.me:
            return
        if c.may("spend a healing surge", who=c.me):
            c.surge(on=c.me)
        else:
            c.save(on=c.me)

    c.watch(Dropped, on_kill, until=When.ENCOUNTER)


@power(
    "i2358p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an ally you can see makes an attack roll",
    on=Trigger(
        AttackDeclared,
        _ally_swings,
        "an ally swings",
        window=Window.BEFORE,
    ),
    dropped=("c.item_set()",),
)
def i2358p1(c: Cast) -> None:
    """Answered on the declaration rather than on the roll, so the bonus is
    installed before the die is read. Which other items the ally is wearing
    is not a question the board answers."""
    ally = getattr(c.trigger, "attacker", None)
    if ally is None:
        return
    amount = max(c.cha_mod, c.str_mod)
    c.bonus("attack", amount, on=ally, until=When.EOT, once=True)
    c.bonus("damage", amount, on=ally, until=When.EOT, once=True)


@power(
    "i2359x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    todo=("c.teleport_bonus()",),
)
def i2359x1(c: Cast) -> None:
    """Lengthening a blink has no verb, and the bonded-weapon penalty is a
    fact about who is holding the item, which the engine never asks."""


@power(
    "i2359p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=MOVE,
    reach=CloseBurst(5),
    target=Target(side="ally", count=2),
    keywords=[Keyword.TELEPORTATION],
)
def i2359p1(c: Cast) -> None:
    """`c.first` carries the once-per-power half: the wielder goes with
    them, not once per ally."""
    if c.first:
        c.teleport(5)
    if c.target is not None:
        c.teleport(5, who=c.target)


@power(
    "i2389x1",
    level=8,
    cls=ITEM,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
)
def i2389x1(c: Cast) -> None:
    def on_kill(ev: Dropped) -> None:
        if ev.source == c.me:
            c.conceal(on=c.me, until=When.EONT)

    c.watch(Dropped, on_kill, until=When.ENCOUNTER)


@power(
    "i2389p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ZONE],
    trigger="you hit an enemy with this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i2389p1(c: Cast) -> None:
    """"Heavily obscured" is a zone that sight does not cross. Dismissing
    it early is a free action with nothing to hold it, and the zone simply
    runs to the end of the fight."""
    foe = c.target
    if foe is None:
        return
    here = _square_of(c, foe)
    if here is not None:
        c.zone(spread({here}, 2), blocks_sight=True, until=When.ENCOUNTER)


@power(
    "i2416p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Ranged(20),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i2416p1(c: Cast) -> None:
    """`c.ignore_cover` takes a gate, so the waiver is held to the one
    creature the card names rather than to everything you shoot at."""
    foe = c.target
    if foe is not None:
        c.ignore_cover(on=c.me, until=When.ENCOUNTER, when=_aimed_at(foe))


@power(
    "i2435p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger="you hit an enemy with an attack using this weapon",
    on=Trigger(Hit, by_me, "you hit an enemy with this weapon"),
)
def i2435p1(c: Cast) -> None:
    c.damage("2d6" if c.points_spent(c.ref) >= 1 else "1d6")


@power(
    "i2495p1",
    level=8,
    cls=ITEM,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.COLD],
    dropped=("c.deals(revert=)",),
)
def i2495p1(c: Cast) -> None:
    c.deals(DamageType.COLD, on=c.me, until=When.ENCOUNTER)


@power(
    "i2495p2",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    trigger="you hit with the weapon",
    on=Trigger(Hit, by_me, "you hit with the weapon"),
)
def i2495p2(c: Cast) -> None:
    c.damage("1d8", dtype=DamageType.COLD)
    c.slowed(until=When.EONT)


@power(
    "i2703p1",
    level=8,
    cls=ITEM,
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    todo=("c.retarget_defence()",),
)
def i2703p1(c: Cast) -> None:
    """Sends an attack at Fortitude instead of AC. The defence is read off
    the power's own printed line before the roll and nothing moves it."""
