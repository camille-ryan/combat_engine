"""Monster abilities, level 4: the brutes and the soldiers beside them.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=9)` and `Damage("2d8", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

Several rows here are printed under an action heading and are plainly
traits; those are declared `ActionType.NONE` and armed once when the fight
starts. A printed range of "5/10" takes the short range, which is what the
creature can actually shoot without a penalty the engine does not model.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.engine import (
    AC,
    AT_WILL,
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
    OPPORTUNITY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Defense,
    Effect,
    Health,
    Ident,
    Keyword,
    Melee,
    Mod,
    Powers,
    Ranged,
    Relation,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    DamageRolled,
    Dropped,
    ForcedMove,
    Hit,
    MoveStart,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    distance_between,
    enemies,
    flanked_by,
    has_combat_advantage,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    hits_me,
    targets_me,
)

#: The reaches that count as a melee attack, for the rows whose rider is on
#: "its melee attacks" rather than on one named row.
MELEE_KINDS = ("melee",)


def _same_row(c: Cast, who: int, ref: str) -> bool:
    """Is that creature another of this stat block?

    By id. A body is never told what anything is called, and `c.is_kind`
    answers about type words -- reptile, undead -- which several different
    stat blocks share.
    """
    ident = c.world.get(who, Ident)
    return ident is not None and ident.ref == ref


def _kin(c: Cast, radius: int, ref: str) -> list[int]:
    """Allies of the same stat block within `radius`, leaving the caster out."""
    return [
        a
        for a in c.within(radius, side="ally")
        if a != c.me and _same_row(c, a, ref)
    ]


def _crowd(c: Cast, victim: int, ref: str) -> int:
    """How many *more* of this stat block are pressed against that creature.

    The caster is left out: the printed line reads "each additional", and
    the caster is the one the count is additional to.
    """
    return sum(
        1
        for other in c.within(1, of=victim, side="ally")
        if other != c.me and _same_row(c, other, ref)
    )


def _holding(c: Cast) -> list[int]:
    """Whoever this creature has hold of."""
    return list(c.world.relations.targets(Relation.GRABBED_BY, c.me))


def _empty_handed(world: World, eid: int) -> bool:
    return not world.relations.targets(Relation.GRABBED_BY, eid)


def _has_hold(world: World, eid: int) -> bool:
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


def _is_bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _crit_line(c: Cast, dice: str, bonus: int) -> None:
    """A printed "crit NdX + n" line.

    It *replaces* the damage rather than adding to it, and it is a roll --
    so it is applied flat, past the engine's own rule that a critical maxes
    the declared dice, which would read the wrong number off this header.
    """
    if c.crit:
        c.flat(c.roll(dice) + bonus)
    else:
        c.hit()


def _in_shape(prefix: str, word: str):  # noqa: ANN202
    """A printed Requirement naming one of a shapechanger's two forms.

    A creature that has not changed shape yet is in whatever shape it was
    found in, which the stat block does not say -- so an undeclared form
    rules out neither attack. Once it has changed, the hold is the answer.
    """

    def gate(world: World, eid: int) -> bool:
        for effect in world.effects.of(eid):
            if effect.label.startswith(prefix):
                return effect.label.endswith(word)
        return True

    return gate


def _change_shape(c: Cast, prefix: str, shapes: tuple[str, ...]) -> None:
    """Take one of two shapes, ending whichever was worn before.

    A polymorph is not a stance, so `c.form` does not clear the old one for
    itself. The form carries no conditions and no movement modes: the
    printed line changes what the creature looks like and which rows it can
    reach, and nothing else.
    """
    for effect in list(c.world.effects.of(c.me)):
        if effect.label.startswith(prefix):
            c.world.effects.end(effect, "changed shape")
    shape = c.choose(list(shapes), "which shape")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=f"{prefix}{shape}")


# ==========================================================================
# Brutes
# ==========================================================================

# -- m2812 ------------------------------------------------------------------

#: The prefix on m2812a4's hold, so the three gated rows can read which of
#: the two shapes is in force.
_M2812_SHAPE = "m2812a4 "
_M2812_SHAPES = ("wolf", "bugbear")


@power(
    "m2812a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d8", 4),
    requires=_in_shape(_M2812_SHAPE, "wolf"),
    requires_text="the m2812 must be in its wolf shape",
)
def m2812a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2812a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 6),
    requires=_in_shape(_M2812_SHAPE, "bugbear"),
    requires_text="the m2812 must be in its bugbear shape",
)
def m2812a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2812a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m2812a2(c: Cast) -> None:
    """Both steps are printed, so both are taken in the printed order. The
    first picks its own destination and may well leave the target out of
    reach; the swing is rolled from wherever it lands, because nothing in the
    row makes the attack conditional on the step."""
    c.shift(3)
    if c.strike():
        c.hit()
    c.shift(3)


@power(
    "m2812a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RELIABLE],
    attack=Attack(vs=WILL, printed=5),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
    requires=_in_shape(_M2812_SHAPE, "wolf"),
    requires_text="the m2812 must be in its wolf shape",
)
def m2812a3(c: Cast) -> None:
    """The attack only. The second half of the printed line -- it gains one
    use of an at-will or encounter attack it has seen the target use, to be
    spent in its other shape at +7 vs AC and +5 vs anything else -- has no
    expression: `c.forbid` takes a row away and nothing hands one over, and
    a borrowed row would roll its owner's attack line rather than the two
    numbers printed here. See the report.

    No range is printed, and melee 1 is what a stat block giving none means.
    """
    if c.strike():
        c.hit()


@power(
    "m2812a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m2812a4(c: Cast) -> None:
    _change_shape(c, _M2812_SHAPE, _M2812_SHAPES)


# -- m284 -------------------------------------------------------------------


@power(
    "m284a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d12", 4),
)
def m284a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 16)


_M284_BLOODIED = "the m284 is first bloodied"


@power(
    "m284a1",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_M284_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M284_BLOODIED),
)
def m284a1(c: Cast) -> None:
    """A basic attack with two riders, so neither can live in a header: the
    swing is whatever this creature's basic actually is, the +4 is a
    one-attack modifier, and the extra die is rolled as the blow lands rather
    than carried as a flat damage bonus.

    "First bloodied" needs no guard -- `Bloodied` is emitted on the crossing
    and nowhere else.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    c.bonus("attack", 4, until=When.EOT, on=me, once=True)

    def press(ev: Hit) -> None:
        if ev.attacker == me and ev.target == victim:
            c.damage("1d6", on=victim)

    extra = c.watch(Hit, press, until=When.EOT, on=me, once=True, label="m284a1")
    c.basic(on=victim)
    c.world.effects.end(extra, "the swing is over")


@power(
    "m284a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d6", 3),
)
def m284a2(c: Cast) -> None:
    """Range 5/10: the header carries the short range, which is the only one
    the engine measures."""
    if c.strike():
        c.hit()


# -- m2930 ------------------------------------------------------------------


@power(
    "m2930a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2930a0(c: Cast) -> None:
    """Whether the victim is held changes between one swing and the next, so
    the gate is read at the moment of the attack rather than stored."""

    def held(ctx: dict) -> bool:
        who = ctx.get("target")
        return who is not None and (
            c.is_(Condition.SLOWED, on=who) or c.is_(Condition.IMMOBILIZED, on=who)
        )

    c.bonus("attack", 2, until=When.ENCOUNTER, on=c.me, when=held)


@power(
    "m2930a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 4),
)
def m2930a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2930a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d8", 4, kind=LIMITED, half_on_miss=True),
)
def m2930a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)
    else:
        c.hit(half=True)


@power(
    "m2930a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
)
def m2930a3(c: Cast) -> None:
    """No damage at all -- the whole row is the hold, and it deepens rather
    than stacking on a creature already slowed."""
    if not c.strike():
        return
    if c.is_(Condition.SLOWED):
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)


_M2930_STRUCK = "the m2930 is hit by a melee attack"


@power(
    "m2930a4",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M2930_STRUCK,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_M2930_STRUCK),
)
def m2930a4(c: Cast) -> None:
    c.shift(3)


# -- m305 -------------------------------------------------------------------


@power(
    "m305a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m305a0(c: Cast) -> None:
    """An aura 1 for the board to draw, biting at the end of a turn rather
    than the start of one -- `c.hazard` does both ends and entry besides,
    which this line does not."""
    c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def scour(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) <= 1:
            c.flat(2, on=ev.actor)

    c.watch(TurnEnd, scour, until=When.ENCOUNTER, on=me, label="m305a0")


@power(
    "m305a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 3),
)
def m305a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m305a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m305a2(c: Cast) -> None:
    """"Save ends both" is one effect carrying the slow and the poison
    together: applied separately they would be two saving throws, and the
    victim could shake off half of a thing the card says is one."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.POISON),
        )


# -- m328 -------------------------------------------------------------------


@power(
    "m328a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m328a0(c: Cast) -> None:
    """"Plus 1d6 fire" is a second expression of its own, so the header keeps
    the untyped line that rescales and the fire is rolled in the body."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.FIRE)


@power(
    "m328a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=5),
)
def m328a1(c: Cast) -> None:
    """No damage on the hit: the burning and the hold are the whole of it,
    and they are one effect because the card says "save ends both"."""
    if c.strike():
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.FIRE),
        )


# -- m357 -------------------------------------------------------------------


@power(
    "m357a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 5),
)
def m357a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 17)


@power(
    "m357a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m357a1(c: Cast) -> None:
    """The surge and the sixteen hit points are two lines, not one: a
    monster's surge is a quarter of its maximum and the card names a flat
    number, so the surge is spent for nothing and the printed amount is
    healed."""
    c.basic()
    c.spend_surge()
    c.heal(16, on=c.me)


# -- m4800 ------------------------------------------------------------------


@power(
    "m4800a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4800a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m4800a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4800a1(c: Cast) -> None:
    """A kill buys a bonus to the *next damage roll*, which is not a duration
    -- so it is armed as a watch on the roll that spends itself, rather than
    as `c.bonus(once=True)`, which is spent by an attack roll instead.
    """
    me = c.me

    def feed(ev: DamageApplied) -> None:
        if ev.source != me or ev.hp > 0:
            return
        armed: list[Effect] = []

        def swell(roll: DamageRolled) -> None:
            if roll.source != me or roll.amount <= 0:
                return
            roll.amount += 5
            if armed:
                c.world.effects.end(armed[0], "spent")

        armed.append(
            c.watch(
                DamageRolled, swell, until=When.ENCOUNTER, on=me, label="m4800a1 relish"
            )
        )

    c.watch(DamageApplied, feed, until=When.ENCOUNTER, on=me, label="m4800a1")


@power(
    "m4800a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d12", 2),
)
def m4800a2(c: Cast) -> None:
    """One at a time, so whoever was being held is let go first -- the
    printed line makes that a rule rather than a courtesy.

    Not written: the Sustain Minor line, which keeps the grab and crushes
    what it holds. An effect can be sustained -- the clock refreshes -- but
    nothing runs when it is, so "Sustain Minor: *do this*" has nowhere to
    go. See the report.
    """
    for held in _holding(c):
        for eff in list(c.world.effects.of(held)):
            if (Relation.GRABBED_BY, c.me, held) in eff.relations:
                c.world.effects.end(eff, "it took hold of something else")
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m4800a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d12", 10, kind=LIMITED),
)
def m4800a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


# -- m4980 ------------------------------------------------------------------


@power(
    "m4980a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4980a0(c: Cast) -> None:
    """An aura 1 for the board to draw, with the bite hung off turn starts.

    How many more of its kind are crowding the victim is asked when the turn
    starts rather than stored with the aura: the count changes every time
    anything moves, and a membership worked out once would be stale
    immediately.
    """
    c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def seethe(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if c.distance(ev.actor) > 1:
            return
        c.flat(5 + 2 * _crowd(c, ev.actor, "m4980"), on=ev.actor)

    c.watch(TurnStart, seethe, until=When.ENCOUNTER, on=me, label="m4980a0")


@power(
    "m4980a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4980a1(c: Cast) -> None:
    """Only the shove half of the swarm trait.

    `c.immovable` refuses every kind of forced movement and the printed line
    refuses two of them, so the refusal is written against `ForcedMove`
    itself, which carries the row doing the shoving and can therefore tell a
    sword from a burst.

    Not written: sharing a square with another creature, an enemy entering
    that square and finding it difficult, and squeezing through gaps. All
    three are facts about occupancy that the grid decides, and no `Cast`
    method reaches them. See the report.
    """
    me = c.me

    def refuse(ev: ForcedMove) -> None:
        if ev.target != me:
            return
        p = get(getattr(ev, "power", "") or "")
        if p is not None and p.reach.kind in ("melee", "ranged"):
            ev.cancel("a swarm is not shoved by a sword or an arrow")

    c.watch(
        ForcedMove,
        refuse,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m4980a1",
    )


@power(
    "m4980a2",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4980a2(c: Cast) -> None:
    """The *designation* goes, not the row.

    A monster's basic attack is one of its own abilities, so `c.forbid` aimed
    at `Powers.basic` takes away m4980a3 itself -- the swarm's only attack,
    in every context -- and the printed line bars none of that. What it bars
    is the thing other rows reach for: an ally granting it a swing, or an
    opening it would otherwise answer. Clearing the pointer says exactly
    that and leaves the row usable on its own turn. `c.basic` then finds the
    engine's generic melee, which a swarm does not know, and refuses.

    Restored when the hold ends, the way `settle` puts a flight mode back.
    """
    known = c.world.get(c.me, Powers)
    if known is None or not known.basic:
        return
    was = known.basic
    hold = c.effect("m4980a2 no basic attack", until=When.ENCOUNTER, on=c.me)
    if hold is None:
        return
    known.basic = ""
    hold.on_end.append(lambda: setattr(known, "basic", was))


@power(
    "m4980a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
)
def m4980a3(c: Cast) -> None:
    """No damage on the hit -- the whole row is a wound that worsens.

    "First Failed Saving Throw" is `escalate`: the old effect ends and a
    heavier one replaces it, so the victim never carries two of these and
    never gets two saves against one bite.
    """

    def worsen(step: int):  # noqa: ANN202
        def harder(eff: Effect) -> None:
            c.world.effects.end(eff, "worsened")
            c.condition(
                until=When.SAVE_ENDS,
                on=eff.owner,
                ongoing=(step, DamageType.UNTYPED),
                escalate=worsen(step + 5) if step < 15 else None,
            )

        return harder

    if c.strike():
        c.condition(
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.UNTYPED),
            escalate=worsen(10),
        )


# ==========================================================================
# Soldiers
# ==========================================================================

# -- m190 -------------------------------------------------------------------


def _has_an_opening(world: World, eid: int) -> bool:
    """A printed "Requirement: combat advantage", asked of the board.

    `requires` is handed the caster and no target, so the nearest thing it
    can say is that there is *somebody* this creature is currently getting
    the better of. Which one is then the chooser's business.
    """
    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


@power(
    "m190a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d12", 5),
)
def m190a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 17)


@power(
    "m190a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
    requires=_has_an_opening,
    requires_text="the m190 must have combat advantage",
)
def m190a1(c: Cast) -> None:
    """The secondary attack is a second roll against a different defence, so
    it cannot live in the header; its printed +7 is trimmed by hand the way
    `Attack.bonus_for` trims the header's, or the row would ignore whatever
    scaling the fight is being played on.

    The stun and the poison are separate printed durations -- one ends with
    a turn, the other with a save -- so they are two effects here.
    """
    if not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(7, c.level), FORT):
        c.stunned(until=When.EONT)
        c.ongoing(5, DamageType.POISON)


@power(
    "m190a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
)
def m190a2(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means. No damage either: the hold is the whole row."""
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m190a3",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m190a3(c: Cast) -> None:
    """A standing bonus rather than an action, whatever the section line
    says. Two modifiers, both gated at the moment they are read, because
    what the victim is suffering changes from swing to swing."""

    def pinned(ctx: dict) -> bool:
        who = ctx.get("target")
        return who is not None and (
            c.is_(Condition.RESTRAINED, on=who) or c.is_(Condition.IMMOBILIZED, on=who)
        )

    c.bonus("attack", 2, until=When.ENCOUNTER, on=c.me, when=pinned)
    c.bonus("damage", 2, until=When.ENCOUNTER, on=c.me, when=pinned)


@power(
    "m190a4",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m190a4(c: Cast) -> None:
    """Said twice, once per word, which is how `c.ignores_difficult` takes a
    printed line naming two sorts of ground."""
    c.ignores_difficult("web", until=When.ENCOUNTER)
    c.ignores_difficult("swarm", until=When.ENCOUNTER)


# -- m199 -------------------------------------------------------------------


@power(
    "m199a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4),
    requires=_empty_handed,
    requires_text="the m199 must not have a creature grabbed",
)
def m199a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m199a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4, half_on_miss=True),
    requires=_has_hold,
    requires_text="the m199 must have a creature grabbed",
)
def m199a1(c: Cast) -> None:
    """The printed target is the creature in its jaws, which no `Target` can
    say, so the header takes one enemy and the body aims at whoever is
    actually being held.

    "Begins its turn" is the Requirement read as an entry condition rather
    than as a trigger: the row is a standard action on the card, and a
    creature that is still holding something at the top of its turn is
    exactly the creature this gate lets through.
    """
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
    else:
        c.hit(on=victim, half=True)


# -- m2912 ------------------------------------------------------------------


@power(
    "m2912a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 5),
)
def m2912a0(c: Cast) -> None:
    """"Or 1d10 + 10 against a bloodied target" is a second expression rather
    than a bonus, so the header keeps the printed line that rescales and the
    larger one is rolled in the body."""
    if not c.strike():
        return
    if c.bloodied():
        c.damage("1d10", 10)
    else:
        c.hit()


_M2912_SLIPPED = "a bloodied enemy adjacent to the m2912 shifts"


def _bloodied_neighbour_shifts(world: World, me: int, ev: MoveStart) -> bool:
    """Three halves of one printed sentence, and no ready-made predicate
    reads any of them: it must be a shift, by a bloodied enemy, standing
    next to this creature when it starts."""
    who = ev.actor
    if ev.kind_ != "shift" or who == me:
        return False
    if who not in enemies(world, me):
        return False
    health = world.get(who, Health)
    if health is None or not health.bloodied:
        return False
    return distance_between(world, me, who) <= 1


@power(
    "m2912a1",
    level=4,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_M2912_SLIPPED,
    on=Trigger(MoveStart, when=_bloodied_neighbour_shifts, text=_M2912_SLIPPED),
)
def m2912a1(c: Cast) -> None:
    """m2912a0 through the row that prints it, so its damage line stays in
    one place. An opportunity action resolves before the step, which is why
    the trigger watches the start of the shift."""
    if c.target is not None:
        use(c.world, c.me, "m2912a0", targets=[c.target], spend=False)


# -- m3021 ------------------------------------------------------------------


def _has_marked_somebody(world: World, eid: int) -> bool:
    """A printed target of "an enemy marked by the m3021", asked of the
    board: `requires` is handed no target, so what it can say is that there
    is one to aim at."""
    return bool(world.relations.targets(Relation.MARKED_BY, eid))


@power(
    "m3021a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 5),
)
def m3021a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m3021a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m3021a1(c: Cast) -> None:
    """Range 10/20: the header carries the short range, which is the only one
    the engine measures."""
    if c.strike():
        c.hit()


@power(
    "m3021a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 5),
    requires=_has_marked_somebody,
    requires_text="the m3021 must have an enemy marked",
)
def m3021a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3021a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ALLY,
)
def m3021a3(c: Cast) -> None:
    """The printed target names a family of stat blocks rather than a type
    word, and nothing can ask that -- `_same_row` matches this stat block
    alone, which is narrower but sayable. The caster is one of them, which
    is why it is not excluded.
    """
    if c.target is not None and _same_row(c, c.target, "m3021"):
        c.shift(1, who=c.target)


@power(
    "m3021a4",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3021a4(c: Cast) -> None:
    """Flanking is combat advantage and combat advantage is +2 here, so the
    printed +3 is that plus one -- written as the extra point rather than as
    a replacement, which nothing can express. The other half of the line,
    aiding another, is a skill action the engine does not have.
    """
    c.bonus(
        "attack",
        1,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: flanked_by(c.world, ctx["target"], c.me),
    )


@power(
    "m3021a5",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m3021a5(c: Cast) -> None:
    c.note("m3021a5: mimics sounds and voices; Insight against its Bluff sees through it")


# -- m3041 ------------------------------------------------------------------


@power(
    "m3041a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m3041a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3041a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("2d6", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m3041a1(c: Cast) -> None:
    """Everything in the burst that is not a plant -- not "enemies": an ally
    that is no plant is caught, which is the printed line.

    "Cannot take standard actions" is `Condition.SHAPED`, which is the one
    card in the table that means exactly that. It is named for the shapes
    that usually impose it and its rule is the printed sentence here.
    """
    if c.is_kind("plant"):
        return
    if c.strike():
        c.hit()
        c.condition(Condition.SHAPED, until=When.EONT)


_M3041_STRUCK = "the m3041 is hit while a m3041 ally is within 5 squares"


def _hit_with_kin_near(world: World, me: int, ev: Hit) -> bool:
    probe = Cast(world=world, me=me, ref="m3041a2")
    return hits_me(world, me, ev) and bool(_kin(probe, 5, "m3041"))


@power(
    "m3041a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3041_STRUCK,
    on=Trigger(Hit, when=_hit_with_kin_near, text=_M3041_STRUCK),
)
def m3041a2(c: Cast) -> None:
    """Sharing the blow out between two of them.

    `Hit` is announced before the damage is rolled, and `DamageRolled`
    carries a mutable `amount` -- so the half that is taken off here is the
    same half that is handed to the other one, which is the only way a row
    reading "each take half damage" can be written. The watcher is armed for
    this turn only and fires once, so a second blow is not split for free.
    """
    me = c.me
    kin = _kin(c, 5, "m3041")
    if not kin:
        return
    friend = min(kin, key=c.distance)

    def split(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        share = ev.amount // 2
        ev.amount -= share
        if share:
            c.flat(share, dtype=ev.dtype, on=friend)

    c.watch(
        DamageRolled, split, until=When.EOT, on=me, once=True, label="m3041a2"
    )


# -- m475 -------------------------------------------------------------------


@power(
    "m475a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m475a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m475a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m475a1(c: Cast) -> None:
    """Who is standing beside the victim changes every time anything moves,
    so the gate is read at the moment of the attack. `ctx["ranged"]` is what
    keeps the bonus off a thrown one."""
    me = c.me

    def pressed(ctx: dict) -> bool:
        who = ctx.get("target")
        if who is None or ctx.get("ranged"):
            return False
        return any(a != me for a in c.within(1, of=who, side="ally"))

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, when=pressed)


@power(
    "m475a2",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m475a2(c: Cast) -> None:
    c.temp_hp(14, on=c.me)


# -- m4802 ------------------------------------------------------------------


@power(
    "m4802a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m4802a0(c: Cast) -> None:
    """One row, two swings: the Effect line says the attack below is made
    twice, so the declared line is rolled twice rather than the row being
    used twice."""
    for _ in range(2):
        if c.strike():
            c.hit()
            c.slowed()


@power(
    "m4802a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4),
)
def m4802a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4802a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m4802a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.UNTYPED),
        )


@power(
    "m4802a3",
    level=4,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4802a3(c: Cast) -> None:
    """The guard is raised for the walk and dropped again on arrival, which
    is what "provoked by this movement" means -- a duration could only have
    measured it in turns. `ctx["opportunity"]` is the flag the attack
    carries, so the bonus does not also apply to anything else swung at it.
    """
    guard = c.bonus(
        Defense.AC,
        4,
        until=When.EOT,
        on=c.me,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )
    c.move(4)
    if guard is not None:
        c.world.effects.end(guard, "the move is over")
    for foe in c.within(1, side="enemy"):
        c.grants_advantage(on=foe, until=When.EONT)


@power(
    "m4802a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    no_provoke=True,
)
def m4802a4(c: Cast) -> None:
    """One creature at a time, so the previous mark and the watch that reads
    it are both torn down first.

    The mark's rider is not the defender's usual -2: it is an opening for
    everybody, so it is a grant of combat advantage armed off the attack
    itself. `leaves_me_out` judges the whole power use rather than this one
    announcement, which is what stops a burst that caught the m4802 from
    counting.
    """
    me, victim = c.me, c.target
    if victim is None:
        return
    for eff in list(c.world.effects.live.values()):
        if eff.source == me and eff.label.startswith("m4802a4"):
            c.world.effects.end(eff, "the mark moved")

    held = c.mark(until=When.ENCOUNTER, on=victim)

    def looked_away(ev: AttackDeclared) -> None:
        if ev.attacker == victim and me not in getattr(ev, "among", (ev.target,)):
            c.grants_advantage(on=victim, until=When.EOTNT, to="allies")

    watching = c.watch(
        AttackDeclared,
        looked_away,
        until=When.ENCOUNTER,
        on=me,
        label="m4802a4 watch",
    )
    if held is not None:
        held.on_end.append(
            lambda: c.world.effects.end(watching, "the mark is gone")
        )


_M4802_DOWN = "the m4802 drops to 0 hit points"


@power(
    "m4802a5",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger=_M4802_DOWN,
    on=Trigger(Dropped, when=about_me, text=_M4802_DOWN),
)
def m4802a5(c: Cast) -> None:
    """A death spasm with no attack roll at all: everyone next to it is
    simply blinded."""
    c.blinded(until=When.EOTNT)


# -- m4845 ------------------------------------------------------------------


@power(
    "m4845a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4845a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and the punishment hung off the
    declaration -- before the roll, so falling prone costs the attacker the
    -2 it has just earned, which is the printed order."""
    c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def scold(ev: AttackDeclared) -> None:
        who = ev.attacker
        if who == me or who not in c.enemies() or c.distance(who) > 1:
            return
        if me in getattr(ev, "among", (ev.target,)):
            return
        c.prone(on=who)
        c.flat(5, on=who)

    c.watch(
        AttackDeclared,
        scold,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m4845a0",
    )


@power(
    "m4845a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m4845a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4845a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 2),
)
def m4845a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4845a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_is_bloodied,
    requires_text="the m4845 must be bloodied",
)
def m4845a3(c: Cast) -> None:
    """Both rows through the ones that print them, so their damage lines stay
    in one place. Each may pick its own victim; pointed at one creature, that
    creature takes both, which is the same two attacks either way."""
    if c.target is None:
        return
    use(c.world, c.me, "m4845a1", targets=[c.target], spend=False)
    use(c.world, c.me, "m4845a2", targets=[c.target], spend=False)


_M4845_SHOVED = "the m4845 is pushed, pulled or slid"


@power(
    "m4845a4",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4845_SHOVED,
    on=Trigger(ForcedMove, when=targets_me, text=_M4845_SHOVED),
)
def m4845a4(c: Cast) -> None:
    """Three of the four printed triggers. A `Trigger` names one event class,
    and being knocked prone is a `ConditionApplied` rather than a
    `ForcedMove` -- so that quarter of the sentence is not declared. See the
    report.
    """
    for foe in c.within(1, side="enemy"):
        c.prone(on=foe)


# -- m672 -------------------------------------------------------------------


@power(
    "m672a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m672a0(c: Cast) -> None:
    """Insubstantial with an exception, which the condition cannot carry:
    `Condition.INSUBSTANTIAL` halves everything, and this line spares force.
    `DamageRolled` carries a mutable amount and is the one place a rule about
    *this* blow can read its damage type.
    """
    me = c.me

    def thin(ev: DamageRolled) -> None:
        if ev.target != me or ev.dtype is DamageType.FORCE or ev.amount <= 0:
            return
        ev.amount //= 2

    c.watch(DamageRolled, thin, until=When.ENCOUNTER, on=me, label="m672a0")


@power(
    "m672a1",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m672a1(c: Cast) -> None:
    """Combat advantage that depends on where somebody *else* is standing, so
    it cannot be a relation laid down once: it is asked as the attack is
    declared, granted for that roll, and taken away again after it.

    `AttackDeclared` is answered in the interrupt window, which is before the
    roll works out whether it had the advantage -- the only window in which
    granting it changes anything.
    """
    me = c.me

    def gang_up(ev: AttackDeclared) -> None:
        victim = ev.target
        if ev.attacker != me or victim is None or victim == me:
            return
        if not any(
            distance_between(c.world, other, victim) <= 1
            for other in _kin(c, 20, "m672")
        ):
            return
        opening = c.grants_advantage(on=victim, until=When.EOT)
        if opening is None:
            return

        def done(rolled: AttackRolled) -> None:
            c.world.effects.end(opening, "the blow is struck")

        sub = c.world.bus.on(AttackRolled, done, once=True, owner=me)
        opening.on_end.append(lambda: c.world.bus.off(sub))

    c.watch(
        AttackDeclared,
        gang_up,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m672a1",
    )


@power(
    "m672a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 7, dtype=DamageType.NECROTIC),
)
def m672a2(c: Cast) -> None:
    """The mark is an Effect line, so it is laid on whether or not the touch
    landed."""
    if c.strike():
        c.hit()
    c.mark()


# -- m879 -------------------------------------------------------------------


@power(
    "m879a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 6),
)
def m879a0(c: Cast) -> None:
    """An Effect line, so the mark is laid on a miss too -- and it runs on
    the target's clock, not the m879's, which is what the card prints."""
    if c.strike():
        c.hit()
    c.mark(until=When.EOTNT)


@power(
    "m879a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FIRE],
)
def m879a1(c: Cast) -> None:
    """The extra damage is typed, and a damage modifier is not -- so it is
    rolled onto the blow as it lands rather than carried as a bonus, which
    would have arrived untyped and ignored resistance to fire.

    The sidestep is written as a watch rather than as a declared trigger: a
    header's `on=` is data on this row, and this row is the minor action that
    arms it, not the reaction itself. It therefore costs no immediate action,
    which is the one way it differs from the printed line. See the report.
    """
    me = c.me

    def scald(ev: Hit) -> None:
        if ev.attacker != me:
            return
        p = get(ev.power)
        if p is not None and p.reach_of(getattr(ev, "branch", 0)).kind in MELEE_KINDS:
            c.flat(4, dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, scald, until=When.SONT, on=me, label="m879a1 heat")

    def sidestep(ev: MoveStart) -> None:
        if ev.actor != me and ev.actor in c.enemies() and c.distance(ev.actor) <= 1:
            c.shift(1)

    c.watch(MoveStart, sidestep, until=When.SONT, on=me, label="m879a1 step")


@power(
    "m879a2",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3, kind=LIMITED),
)
def m879a2(c: Cast) -> None:
    """"Save ends both" wants the penalty and the poison on one effect, and
    `c.condition` carries conditions and ongoing damage but no modifier --
    so this one is applied directly, which is the only way the victim gets
    one saving throw rather than two.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=c.ref,
        mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
        ongoing=(5, DamageType.POISON),
    )
