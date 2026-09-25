"""Wizard, level 10: utility. Nothing in the first three rows rolls an attack.

`p1231`'s bonus is one `Mod` that is written down rather than a stack of
three: the printed line reduces it by 2 at a time and ends the power when it
reaches 0, and three separate +2s of the same kind would come to +2 rather
than +6 -- same-named bonuses do not add, the larger wins.

`p513` maintains its relations rather than setting them once. Being unseen
is `HIDDEN_FROM` per enemy, and which enemies qualify changes every time
anybody walks, so the set is recomputed on `MoveEnd` and torn down with the
effect. Only the pairs this row laid are cleared, so a rogue hiding in the
same fight keeps its own.

The level's fourth row is left out; see the report.

The rows printed in the later books follow. Four things recur in them.

**Walls.** An area wall is not a shape a `Range` can be, so its printed
distance is declared as `Ranged(n)`, the anchor is chosen, and `_wall` lays
the run of squares across the caster's line to it -- the arrangement
`level_6.py:p1548` and `level_9.py:p722` already use. Height has nowhere to
go: the board is flat.

**Cover that is not quite the printed cover.** `blocks_sight` is the only
door to a cover penalty from ground, and it is not selective: a zone carrying
it shelters everyone from everyone. Three of these rows print something
narrower -- "for all enemies but not your allies", "against ranged weapon
attacks passing through" -- and each says so rather than pretending.

**A triggering event read back.** `DamageRolled` is a `Decision` whose
`amount` `deal_damage` reads again after both windows close, so an interrupt
can halve the blow and a free action can reduce it to nothing. It is not
re-exported from `combat_engine.engine`; it comes from `engine.events`.

**Movement costs above one.** A zone's difficult terrain is a fixed one extra
square. "Two extra squares" is a number there is nowhere to put, and the rows
printing it say so.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ALLY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INT,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Miss,
    Mod,
    MoveEnd,
    Position,
    Powers,
    Ranged,
    Relation,
    SavingThrow,
    Square,
    Target,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    both,
    by_me,
    by_melee,
    distance,
    get,
    power,
    spread,
    targets_me,
    would_hit_me,
)
from combat_engine.engine.events import (
    DamageRolled,
    MoveStart,
    RelationSet,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.zones import Zone

ARCANE = [Keyword.ARCANE]
ARCANE_ILLUSION = [Keyword.ARCANE, Keyword.ILLUSION]


def _wall(c: Cast, reach: int, length: int) -> list[Square]:
    """A run of squares laid across the caster's line to a chosen anchor.

    Copied in shape from `level_6.py:p1548`, which is the only placement that
    does not ask the caller to describe a wall square by square.
    """
    anchors = sorted(
        sq for sq in spread({c.here}, reach) if c.world.grid.inside(sq) and sq != c.here
    )
    anchor = c.choose(anchors, f"{c.ref}: where the wall stands")
    if anchor is None:
        return []
    across, along = anchor[0] - c.here[0], anchor[1] - c.here[1]
    step = (1, 0) if abs(along) >= abs(across) else (0, 1)
    half = length // 2
    run = [
        (anchor[0] + step[0] * i, anchor[1] + step[1] * i)
        for i in range(-half, length - half)
    ]
    return [sq for sq in run if c.world.grid.inside(sq)]


def _arcane_miss(world: World, me: int, ev: object) -> bool:
    """A miss by me with a row carrying the arcane keyword."""
    p = get(getattr(ev, "power", ""))
    return p is not None and Keyword.ARCANE in p.keywords


def _fire_on_me(world: World, me: int, ev: object) -> bool:
    return getattr(ev, "dtype", None) is DamageType.FIRE


def _area_or_close(world: World, me: int, ev: object) -> bool:
    """Was the blow an area or a close attack? Read off the row that dealt it.

    `DamageRolled` spells the row `detail`, which is where `Cast.damage` puts
    it, and carries no reach of its own.
    """
    p = get(getattr(ev, "detail", ""))
    return p is not None and p.reach.kind in ("area_burst", "close_burst", "close_blast")


@power(
    "p1231",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE_ILLUSION,
)
def p1231(c: Cast) -> None:
    """"Otherwise the effect lasts for 1 hour" is the encounter: there is no
    longer clock on this board, and the images are gone before it in any
    fight where three attacks miss."""
    images = Mod(what=AC.value, value=6, kind="power", label=c.ref)
    veil = c.world.effects.apply(
        c.me, c.me, When.ENCOUNTER, label=c.ref, mods=[(c.me, images)]
    )

    def popped(ev: Miss) -> None:
        if ev.target != c.me or veil.ended:
            return
        images.value -= 2
        if images.value <= 0:
            c.world.effects.end(veil, "the last image is gone")

    veil.subs.append(c.world.bus.on(Miss, popped, owner=c.me))


@power(
    "p2274",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=Target("any", 1, label="You or one creature"),
    keywords=ARCANE,
)
def p2274(c: Cast) -> None:
    """The printed list is every damage type there is bar untyped, which is
    not one a creature can be resistant to."""
    kinds = [d for d in DamageType if d is not DamageType.UNTYPED]
    kind = c.choose(kinds, "p2274: which damage type")
    if kind is not None:
        c.resist(c.level + c.int_mod, kind, until=When.ENCOUNTER, on=c.target)


@power(
    "p513",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE_ILLUSION,
)
def p513(c: Cast) -> None:
    me = c.me
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=me, until=When.ENCOUNTER, kind="power")

    unseeing: set[int] = set()
    veil = c.world.effects.apply(me, me, When.ENCOUNTER, label=f"{c.ref} unseen")

    def lift() -> None:
        for watcher in sorted(unseeing):
            c.world.relations.clear(Relation.HIDDEN_FROM, me, watcher, "the veil lifted")
        unseeing.clear()

    def redraw(_ev: object = None) -> None:
        if veil.ended:
            return
        for foe in c.enemies():
            far = c.distance(to=foe) >= 5
            if far and foe not in unseeing:
                c.world.relations.set(Relation.HIDDEN_FROM, me, foe)
                unseeing.add(foe)
            elif not far and foe in unseeing:
                c.world.relations.clear(
                    Relation.HIDDEN_FROM, me, foe, "close enough to see"
                )
                unseeing.discard(foe)

    veil.subs.append(c.world.bus.on(MoveEnd, redraw, owner=me))
    veil.on_end.append(lift)
    redraw()


@power(
    "p10147",
    level=10,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p10147(c: Cast) -> None:
    """The Bluff bonus is a check this engine does not roll; the rest of the
    line is real and is the row. "Retain the use of" is `Powers.unuse`, the
    door the Reliable keyword already goes through, narrowed to the rows the
    line names: single-target encounter charms.
    """
    me = c.me

    def kept(ev: Miss) -> None:
        if ev.attacker != me:
            return
        p = get(ev.power)
        if p is None or Keyword.CHARM not in p.keywords:
            return
        if p.usage is not ENCOUNTER or p.target.everyone or p.target.count != 1:
            return
        known = c.world.get(me, Powers)
        if known is not None:
            known.unuse(p.ref)

    c.watch(Miss, kept, until=When.EONT, on=me, label=c.ref)


@power(
    "p10422",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=20),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.AREA, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p10422(c: Cast) -> None:
    """The resistance is a property of standing in the zone, so it is given on
    the way in and taken back on the way out rather than handed a duration.

    Two clauses have no number to put them in: enemies paying two extra
    squares to enter (a zone's difficult terrain is a fixed one extra), and
    the refusal to push a creature into harm, which would need the shove to
    know what it was about to cross.
    """
    heart = c.origin or c.here
    if c.first:
        area = c.area()
        if area:
            zone = c.zone(area, label=c.ref, until=When.EONT, difficult=True)
            sheltered: dict[int, Effect] = {}

            def enter(who: int) -> None:
                if who in sheltered or who in c.enemies():
                    return
                held = c.resist(c.int_mod, until=When.ENCOUNTER, on=who)
                if held is not None:
                    sheltered[who] = held

            def walked_in(ev: ZoneEntered) -> None:
                if ev.zone == zone:
                    enter(ev.actor)

            def walked_out(ev: ZoneExited) -> None:
                held = sheltered.pop(ev.actor, None)
                if ev.zone == zone and held is not None:
                    c.world.effects.end(held, "left the shelter")

            standing = c.world.get(zone, Zone)
            if standing is not None and standing.effect is not None:
                standing.effect.subs.extend(
                    [
                        c.world.bus.on(ZoneEntered, walked_in),
                        c.world.bus.on(ZoneExited, walked_out),
                    ]
                )
            for who in c.world.zones.occupants(zone):
                enter(who)
            c.note(f"{c.ref}: enemies should pay 2 extra squares, and difficult ground is 1")

    victim = c.target
    if victim is None or not c.strike():
        return
    c.push(max(1, 2 - distance(c.there, heart)), anchor=heart)


@power(
    "p12549",
    level=10,
    cls="wizard",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger="you take fire damage",
    on=Trigger(
        DamageRolled, when=both(targets_me, _fire_on_me), text="you take fire damage"
    ),
)
def p12549(c: Cast) -> None:
    """`deal_damage` reads `amount` back off the event after both windows
    close, so a free action answering the roll can still reduce it to nothing.

    Being removed from play is `Condition.REMOVED` -- no actions, no movement
    -- and the body stays in its square: nothing lifts a creature off the grid
    and leaves it in the initiative order. Coming back is the hold ending, and
    the reappearance is the teleport hung on it.
    """
    ev = c.trigger
    if ev is not None and hasattr(ev, "amount"):
        ev.amount = 0
    held = c.condition(Condition.REMOVED, until=When.SONT, on=c.me)
    if held is not None:
        held.on_end.append(lambda: c.teleport(10))


@power(
    "p12749",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger="you are damaged by an area attack or a close attack",
    on=Trigger(
        DamageRolled,
        when=both(targets_me, _area_or_close),
        text="you are damaged by an area attack or a close attack",
    ),
)
def p12749(c: Cast) -> None:
    """The bonus is gated on the row being rolled sharing a damage type with
    the blow that triggered this, which is read off its keywords -- a damage
    type is a keyword precisely so resistances can key off it. The damage
    context carries `target`, `power`, `opportunity` and `charge` and nothing
    else, so the row has to be looked up from `power`.
    """
    ev = c.trigger
    if ev is not None and hasattr(ev, "amount"):
        ev.amount //= 2
    dtype = getattr(ev, "dtype", DamageType.UNTYPED)
    if dtype is DamageType.UNTYPED:
        return
    word = Keyword(dtype.value)

    def shares(ctx: dict[str, object]) -> bool:
        p = get(str(ctx.get("power", "")))
        return p is not None and p.cls == "wizard" and word in p.keywords

    c.bonus("damage", 5, on=c.me, until=When.EONT, kind="power", when=shares)


@power(
    "p13992",
    level=10,
    cls="wizard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p13992(c: Cast) -> None:
    """The printed Requirement and destination are both a square of dim light
    or darkness, and the engine has no light at all -- squares are lit or they
    are nothing. Declaring a `requires` that can never be true would refuse the
    row for a reason that says nothing about it, so the light is dropped and
    said here instead, and what is left is the teleport.
    """
    c.teleport(10)


@power(
    "p13993",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.AREA, Keyword.ZONE],
)
def p13993(c: Cast) -> None:
    """Blindness is a property of standing in the dark rather than a duration,
    so it goes on at the edge and comes off again; a zone ending announces
    everyone leaving it, which unwinds the rest.

    "Squares adjacent to it are lightly obscured" is concealment, which this
    engine keeps no state for.
    """
    squares_ = _wall(c, 10, 8)
    if not squares_:
        return
    zone = c.zone(
        squares_,
        label=c.ref,
        until=When.SUSTAIN,
        sustain=MINOR,
        difficult=True,
        blocks_sight=True,
    )
    me = c.me
    unseeing: dict[int, Effect] = {}

    def enter(who: int) -> None:
        if who == me or who in unseeing:
            return
        held = c.blinded(until=When.ENCOUNTER, on=who)
        if held is not None:
            unseeing[who] = held

    def walked_in(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            enter(ev.actor)

    def walked_out(ev: ZoneExited) -> None:
        held = unseeing.pop(ev.actor, None)
        if ev.zone == zone and held is not None:
            c.world.effects.end(held, "out of the dark")

    standing = c.world.get(zone, Zone)
    if standing is not None and standing.effect is not None:
        standing.effect.subs.extend(
            [
                c.world.bus.on(ZoneEntered, walked_in),
                c.world.bus.on(ZoneExited, walked_out),
            ]
        )
    for who in c.world.zones.occupants(zone):
        enter(who)


@power(
    "p14561",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.AREA, Keyword.ZONE],
)
def p14561(c: Cast) -> None:
    """"Attempts to leave a square in the zone" is answered at `MoveStart`, the
    one cancellable door -- it fires before a destination exists, so an enemy
    standing in the thicket is stopped from moving at all rather than only from
    leaving. The saving throw is a bare one, with nothing to shake off, so it
    is rolled and announced here.

    Two clauses have nowhere to go: expanding or contracting the zone as a
    minor action, and the vegetation variant, whose squares have hit points.
    """
    squares_ = _wall(c, 10, 3)
    if not squares_:
        return
    zone = c.zone(
        squares_,
        label=c.ref,
        until=When.ENCOUNTER,
        difficult=True,
        blocks_sight=True,
    )

    def caught(ev: MoveStart) -> None:
        if ev.kind_ not in ("walk", "shift") or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(zone):
            return
        roll = c.world.rng.d20().total
        rolled = c.world.bus.emit(
            SavingThrow(
                actor=ev.actor, against=c.ref, natural=roll, bonus=0, saved=roll >= 10
            )
        )
        if rolled.cancelled or rolled.saved:
            return
        c.condition(Condition.IMMOBILIZED, until=When.SOTNT, on=ev.actor)
        ev.cancel("held by the thicket")

    standing = c.world.get(zone, Zone)
    if standing is not None and standing.effect is not None:
        standing.effect.subs.append(
            c.world.bus.on(MoveStart, caught, window=Window.BEFORE)
        )


@power(
    "p16290",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=ARCANE,
    out_of_combat=True,
)
def p16290(c: Cast) -> None:
    c.note(f"{c.ref}: a hole up to 2 squares across and {2 * c.int_mod} deep, climbable")


@power(
    "p16291",
    level=10,
    cls="wizard",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.CLOSE],
)
def p16291(c: Cast) -> None:
    """Shifting *through* an enemy's space is not something movement can be
    told to do -- `share` arrives in an occupied square, which is a different
    sentence -- so the distance is the whole of what is said here."""
    who = c.target
    if who is None:
        return
    if c.may("shift", who=who):
        c.shift(max(1, c.int_mod), who=who)


@power(
    "p16292",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.AREA, Keyword.CONJURATION],
)
def p16292(c: Cast) -> None:
    """`blocks_sight` is the only door to cover from ground and it is not
    selective: this wall shelters everyone from every kind of attack, where the
    printed line gives superior cover against ranged weapon attacks passing
    through it. Difficult terrain is a fixed one extra square, where the
    printed cost is two.
    """
    squares_ = _wall(c, 10, 8)
    if not squares_:
        return
    zone = c.zone(
        squares_,
        label=c.ref,
        until=When.SUSTAIN,
        sustain=MINOR,
        difficult=True,
        blocks_sight=True,
    )
    wall = frozenset(squares_)
    beside = spread(wall, 1)

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.in_squares(beside):
            return
        pos = c.world.get(ev.actor, Position)
        if pos is None:
            return
        near = min(wall, key=lambda sq: distance(sq, pos.square))
        c.push(c.roll("1d4"), on=ev.actor, anchor=near)

    standing = c.world.get(zone, Zone)
    if standing is not None and standing.effect is not None:
        standing.effect.subs.append(c.world.bus.on(TurnStart, dawn))
    c.note(f"{c.ref}: the wall costs 2 extra squares to cross, and difficult ground is 1")


@power(
    "p2838",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE, Keyword.CLOSE],
)
def p2838(c: Cast) -> None:
    """One choice for the whole burst, so it is made once and applied to every
    target rather than asked again per creature."""
    if not c.first:
        return
    kinds = [d for d in DamageType if d is not DamageType.UNTYPED]
    kind = c.choose(kinds, f"{c.ref}: which damage type")
    if kind is None:
        return
    for mate in c.targets:
        c.resist(5 + c.int_mod, kind, until=When.ENCOUNTER, on=mate)


@power(
    "p2840",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p2840(c: Cast) -> None:
    """Seeing the invisible is `HIDDEN_FROM` read from the watcher's end: every
    pair hiding somebody from this caster within ten squares is cleared, and a
    fresh one is undone as it is set. Darkvision and the two skill bonuses have
    no model -- the engine has neither light nor checks.
    """
    me = c.me
    held = c.world.effects.apply(me, me, When.ENCOUNTER, label=f"{c.ref} true sight")

    def reveal(who: int) -> None:
        if c.distance(to=who) <= 10:
            c.world.relations.clear(Relation.HIDDEN_FROM, who, me, c.ref)

    def spotted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.HIDDEN_FROM and ev.target == me and not held.ended:
            reveal(ev.source)

    for other in (*c.enemies(), *c.allies()):
        reveal(other)
    held.subs.append(c.world.bus.on(RelationSet, spotted, owner=me))


@power(
    "p3222",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.AREA, Keyword.ILLUSION],
)
def p3222(c: Cast) -> None:
    """The wall is an illusion and stops nothing; what it does is block sight,
    which `blocks_sight` says -- for everybody, where the printed line exempts
    the caster's allies, and there is no per-creature sight to set.

    The printed attack on an enemy moving adjacent has no consequence left to
    apply once that is so: a hit stops the target moving *through* a wall that
    was never blocking terrain, and a miss lifts a sight block that is not held
    per creature. It is said here rather than rolled for nothing.
    """
    squares_ = _wall(c, 20, 8)
    if not squares_:
        return
    c.zone(squares_, label=c.ref, until=When.SUSTAIN, sustain=MINOR, blocks_sight=True)
    c.note(f"{c.ref}: the wall should block sight for enemies only, and cover is not per creature")


@power(
    "p4237",
    level=10,
    cls="wizard",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger="you miss with an arcane attack",
    on=Trigger(
        Miss, when=both(by_me, _arcane_miss), text="you miss with an arcane attack"
    ),
)
def p4237(c: Cast) -> None:
    """The outcome is recomputed from the die *before* `Hit`/`Miss` is
    announced, so a reroll here changes what the body sees when `c.strike()`
    returns, which is what matters -- no second `Hit` is emitted for it.

    The eladrin's +2 is a race, and a character here has none.
    """
    c.reroll_attack(keep="new")


@power(
    "p7401",
    level=10,
    cls="wizard",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger="you are hit by a melee attack",
    on=Trigger(
        AttackRolled,
        when=both(would_hit_me, by_melee),
        text="you are hit by a melee attack",
    ),
)
def p7401(c: Cast) -> None:
    """Offered on the roll rather than on the hit, the way `level_2.py:p1235`
    is: the defence is read again once this window closes, so the +4 applies to
    the very attack that triggered it and may turn it aside.

    The shove comes after the attack resolves, which is `Hit` and `Miss` both
    -- the printed line says "makes a melee attack", not "hits with one".
    """
    me = c.me
    c.bonus(AC, 4, on=me, until=When.EONT)
    c.bonus(REF, 4, on=me, until=When.EONT)

    def shove(ev: Hit | Miss) -> None:
        if ev.target != me:
            return
        p = get(ev.power)
        if p is not None and p.reach.kind in ("melee", "close_burst", "close_blast"):
            c.push(1, on=ev.attacker)

    for kind in (Hit, Miss):
        c.watch(kind, shove, until=When.EONT, on=me, label=f"{c.ref} shove")
