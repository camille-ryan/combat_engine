"""Monster abilities, level 1: the ones that move.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=6)` and `Damage("1d10", 5)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

A **trait** is a standing arrangement rather than something spent on a turn,
so it is written as a row that costs no action, has no target, and arms the
watches that hold it for the rest of the fight. `usage=ENCOUNTER` is what
keeps it from being armed a second time and paying twice.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    Damage,
    DamageType,
    Ident,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Square,
    Stats,
    When,
    Window,
    World,
    distance,
    get,
    power,
    spread,
    use,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    DamageApplied,
    Hit,
    Miss,
    MoveEnd,
    MoveStart,
    TurnStart,
)
from combat_engine.engine.query import has_combat_advantage, squares
from combat_engine.engine.triggers import Trigger, both, enemy_within, targets_me


def _ref_of(c: Cast, who: int) -> str:
    """Which stat block a creature is, so "an ally of the same kind" can ask."""
    ident = c.world.get(who, Ident)
    return ident.ref if ident else ""


def _level_of(c: Cast, who: int) -> int:
    stats = c.world.get(who, Stats)
    return stats.level if stats else 0


# --------------------------------------------------------------------------
# m237
# --------------------------------------------------------------------------


@power(
    "m237a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d6", 2),
)
def m237a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m237a1",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m237a1(c: Cast) -> None:
    """Extra damage whenever it has the drop on what it hit.

    The database files this as a standard action, which it plainly is not --
    it is a rider on every attack the creature makes -- so it is written as a
    trait. Combat advantage is asked of the board at the moment of the hit
    rather than stored, because flanking ends the instant an ally steps away.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and has_combat_advantage(c.world, me, ev.target):
            c.damage("1d6", on=ev.target, detail="m237a1")

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m237a1")


@power(
    "m237a2",
    level=1,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="missed by a melee attack",
)
def m237a2(c: Cast) -> None:
    c.shift(1)


@power(
    "m237a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m237a3(c: Cast) -> None:
    """A shift that may end in an ally's square, the ally taking the one left.

    Written as the shift rather than as a rule about shifting: nothing can
    reach into a shift's choice of destination, and the generic shift action
    will not end on an occupied square, so this row is the only way the
    permission can ever be used. With no ally to trade places with it is an
    ordinary shift, which is what the trait modifies.
    """
    mates = sorted(
        a
        for a in c.allies()
        if c.adjacent(a) and _level_of(c, a) <= c.level
    )
    mate = c.choose(mates, "swap places with which ally")
    if mate is None:
        c.shift(1)
    else:
        c.swap(mate)


# --------------------------------------------------------------------------
# m2998
# --------------------------------------------------------------------------


@power(
    "m2998a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m2998a0(c: Cast) -> None:
    """The ongoing damage more than doubles once the creature is hurt."""
    if c.strike():
        c.hit()
        c.ongoing(5 if c.bloodied(on=c.me) else 2)


@power(
    "m2998a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m2998a1(c: Cast) -> None:
    """Bite, then fly off without giving the target an opening.

    The attack is m2998a0 rather than a copy of it, so the damage line stays
    in one place and rescales with it. The flight is taken *after* the bite:
    `c.move` picks its own destination and a flight taken first can leave the
    target out of reach.
    """
    c.no_provoke(from_=c.target)
    use(c.world, c.me, "m2998a0", targets=[c.target], spend=False)
    c.move(6)


# --------------------------------------------------------------------------
# m301
# --------------------------------------------------------------------------


@power(
    "m301a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8"),
)
def m301a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m301a1",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m301a1(c: Cast) -> None:
    """Extra damage with the drop on the target, on melee and ranged alike.

    Filed as a standard action in the database and written as a trait for the
    same reason as m237a1. The printed line names the two reaches it applies
    to, so a close or area attack does not pay it.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        p = get(ev.power)
        if ev.attacker != me or p is None or p.reach.kind not in ("melee", "ranged"):
            return
        if has_combat_advantage(c.world, me, ev.target):
            c.damage("1d6", on=ev.target, detail="m301a1")

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m301a1")


@power(
    "m301a2",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m301a2(c: Cast) -> None:
    """One attack bonus per ally of its own kind crowding the target.

    `c.bonus` carries a fixed value and the pack is counted fresh for every
    attack, so the bonus is worked out and applied in the interrupt window of
    `AttackDeclared` -- before the die is rolled -- and spent on the roll.
    """
    me = c.me
    kin = _ref_of(c, me)

    def pack(ev: AttackDeclared) -> None:
        if ev.attacker != me:
            return
        mates = [
            a
            for a in c.within(1, of=ev.target, side="ally")
            if a != me and _ref_of(c, a) == kin
        ]
        if mates:
            c.bonus(
                "attack", len(mates), until=When.EOT, on=me, kind="untyped", once=True
            )

    c.watch(
        AttackDeclared,
        pack,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        on=me,
        label="m301a2",
    )


@power(
    "m301a3",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m301a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m430
# --------------------------------------------------------------------------


@power(
    "m430a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
)
def m430a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m430a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
    damage=Damage("", 1),
)
def m430a1(c: Cast) -> None:
    """The single point of damage is the whole mechanical content.

    What the row is for -- lifting a small object off the target -- has no
    representation here: creatures carry `Gear`, which is what is in hand,
    and nothing models a pouch or its contents.
    """
    if c.strike():
        c.hit()


@power(
    "m430a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m430a2(c: Cast) -> None:
    """Strike, then fly clear of the creature it struck.

    `c.basic` rather than a named row, because the printed line says basic
    attack and a monster may have had its basic replaced. Attack first, then
    fly, for the reason given on m2998a1.
    """
    c.no_provoke(from_=c.target)
    c.basic()
    c.move(8)


# --------------------------------------------------------------------------
# m433
# --------------------------------------------------------------------------


@power(
    "m433a0",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m433a0(c: Cast) -> None:
    """Much harder to hit while it has hold of somebody.

    A gate rather than an effect applied and taken back when the grab starts
    and ends: the modifier is asked whether it applies every time a defence
    is read, so there is no second place that has to remember to undo it.
    """
    me = c.me

    def holding(_: dict) -> bool:
        return bool(c.world.relations.targets(Relation.GRABBED_BY, me))

    for d in (AC, REF):
        c.bonus(d, 5, until=When.ENCOUNTER, on=me, kind="untyped", when=holding)


def _not_grabbing(world: World, eid: int) -> bool:
    return not world.relations.targets(Relation.GRABBED_BY, eid)


@power(
    "m433a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 5),
    requires=_not_grabbing,
    requires_text="must not already have hold of a creature",
)
def m433a1(c: Cast) -> None:
    """The bleed runs until the grab does, so it hangs off the grab's own end.

    Applied on the encounter clock and cut short by the grab rather than
    given its own saving throw: the printed line offers no save, it offers
    escape, and escaping is what ends the grab.
    """
    if not c.strike():
        return
    c.hit()
    grab = c.grab()
    bleed = c.ongoing(5, until=When.ENCOUNTER)
    if grab is not None and bleed is not None:
        grab.on_end.append(lambda: c.world.effects.end(bleed, "the grab ended"))


# --------------------------------------------------------------------------
# m4859
# --------------------------------------------------------------------------


@power(
    "m4859a0",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4859a0(c: Cast) -> None:
    """Unseen from the start of any turn it begins with nobody next to it.

    `When.EONT` is applied on the creature's own turn, so it latches past the
    end of that turn and runs out at the end of the next one -- exactly what
    the printed duration says. Attacking gives it away whether or not the
    attack lands, so the watch is on the roll rather than on the hit.
    """
    me = c.me

    def vanish(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost or c.within(1, side="enemy"):
            return
        veil = c.invisible(until=When.EONT)
        if veil is None:
            return

        def reveal(rolled: AttackRolled) -> None:
            if rolled.attacker == me:
                c.world.effects.end(veil, "it attacked")

        seen = c.watch(AttackRolled, reveal, until=When.EONT, on=me, label="m4859a0")
        veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))

    c.watch(TurnStart, vanish, until=When.ENCOUNTER, on=me, label="m4859a0")


@power(
    "m4859a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3),
)
def m4859a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _unseen(world: World, eid: int) -> bool:
    return bool(world.relations.targets(Relation.HIDDEN_FROM, eid))


@power(
    "m4859a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
    damage=Damage("2d6", 4),
    requires=_unseen,
    requires_text="the target cannot see it",
)
def m4859a2(c: Cast) -> None:
    """Only against a creature that cannot see it, and then it holds on.

    The printed restriction is per target and the header's `target` field
    cannot say so, so `requires` carries the half of it that is about the
    creature -- being unseen at all -- and the body checks the target itself.

    While the grab holds, half of whatever is aimed at the elemental lands on
    whoever it is holding instead. Read off `DamageApplied`, because that is
    the only event carrying an amount; damage the elemental deals itself is
    excluded so the two cannot feed each other.
    """
    victim = c.target
    if victim is None or not c.world.relations.holds(Relation.HIDDEN_FROM, c.me, victim):
        return
    if not c.strike():
        return
    c.hit()
    if c.world.relations.targets(Relation.GRABBED_BY, c.me):
        return
    grab = c.grab()
    bleed = c.ongoing(5, until=When.ENCOUNTER)

    def shared(ev: DamageApplied) -> None:
        if ev.target != c.me or ev.source == c.me:
            return
        half = ev.amount // 2
        if half:
            c.flat(half, on=victim)

    guard = c.watch(DamageApplied, shared, until=When.ENCOUNTER, on=c.me, label="m4859a2")
    if grab is not None:
        grab.on_end.append(lambda: c.world.effects.end(guard, "the grab ended"))
        if bleed is not None:
            grab.on_end.append(lambda: c.world.effects.end(bleed, "the grab ended"))


# --------------------------------------------------------------------------
# m4865
# --------------------------------------------------------------------------


@power(
    "m4865a0",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4865a0(c: Cast) -> None:
    """Cold locks it up: it may still walk, but it cannot shift.

    A trait, armed once. `c.rooted` is the hold that bars a shift and leaves
    walking alone -- `immobilized` is the wrong card and stops both.
    """

    def chilled(ev: DamageApplied) -> None:
        if ev.target == c.me and ev.dtype is DamageType.COLD and ev.amount:
            c.rooted(until=When.EONT, on=c.me)

    c.watch(DamageApplied, chilled, until=When.ENCOUNTER, on=c.me, label="m4865a0")


@power(
    "m4865a1",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    damage=Damage("", 3, dtype=DamageType.FIRE),
)
def m4865a1(c: Cast) -> None:
    """Swinging at it and missing costs the attacker.

    The three points sit in the header like any other damage line, so this
    rescales with the rest of the stat block rather than being a literal
    buried in a closure.
    """
    me = c.me

    def scorch(ev: Miss) -> None:
        p = get(ev.power)
        if ev.target != me or p is None or p.reach.kind != "melee":
            return
        if ev.attacker in c.enemies() and c.adjacent(ev.attacker):
            c.hit(on=ev.attacker)

    c.watch(Miss, scorch, until=When.ENCOUNTER, on=me, label="m4865a1")


@power(
    "m4865a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=4),
)
def m4865a2(c: Cast) -> None:
    """All of the damage is ongoing, so there is no header damage line."""
    if c.strike():
        c.ongoing(5, DamageType.FIRE)


@power(
    "m4865a3",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4865a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m5028
# --------------------------------------------------------------------------


@power(
    "m5028a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m5028a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5028a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 3),
)
def m5028a1(c: Cast) -> None:
    """Range 5/10: the header carries the short range, which is what it can
    be aimed at without the long-range penalty."""
    if c.strike():
        c.hit()


@power(
    "m5028a2",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy adjacent to it is hit by an attack",
)
def m5028a2(c: Cast) -> None:
    c.shift(1)


_HIT_BY_ADJACENT = "an enemy adjacent to the m5028 hits it"


@power(
    "m5028a3",
    level=1,
    usage=AT_WILL,
    action=REACTION,
    trigger=_HIT_BY_ADJACENT,
    on=Trigger(Hit, when=both(targets_me, enemy_within(1)), text=_HIT_BY_ADJACENT),
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5028a3(c: Cast) -> None:
    """Round to the other side of whoever just landed one.

    The destination is named outright rather than left to a teleport 2,
    which would also allow squares nowhere near the attacker. "Another"
    square is had for free: the one it is standing in has an occupant and is
    filtered out with every other occupied square.
    """
    enemy = getattr(c.trigger, "attacker", None)
    if enemy is None:
        return
    grid = c.world.grid
    spots = sorted(
        sq
        for sq in spread(squares(c.world, enemy), 1)
        if grid.passable(sq) and grid.occupant(sq) is None
    )
    dest = c.choose(spots, "teleport beside the attacker")
    if dest is not None:
        c.teleport(2, to=dest)


# --------------------------------------------------------------------------
# m665
# --------------------------------------------------------------------------


@power(
    "m665a0",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m665a0(c: Cast) -> None:
    """Covering ground on its turn makes its shooting hurt more.

    The starting point is taken when the move begins rather than at the top
    of the turn: the printed line measures a move, and a creature that moves
    twice has each of them measured on its own.
    """
    me = c.me
    began: list[Square] = []

    def off(ev: MoveStart) -> None:
        if ev.actor == me:
            began.append(c.here)

    def landed(ev: MoveEnd) -> None:
        if ev.actor != me or not began:
            return
        start = began.pop()
        if c.turn_of() != me or distance(start, ev.at) < 4:
            return

        def rider(hit: Hit) -> None:
            p = get(hit.power)
            if hit.attacker == me and p is not None and p.reach.kind == "ranged":
                c.damage("1d6", on=hit.target, detail="m665a0")

        c.watch(Hit, rider, until=When.SONT, on=me, label="m665a0 mobile")

    c.watch(MoveStart, off, until=When.ENCOUNTER, on=me, label="m665a0")
    c.watch(MoveEnd, landed, until=When.ENCOUNTER, on=me, label="m665a0")


@power(
    "m665a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 2),
)
def m665a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m665a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 2),
)
def m665a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m665a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 2),
    no_provoke=True,
)
def m665a3(c: Cast) -> None:
    """Shoot, then move -- the printed line allows either order.

    The shot is written out rather than delegated to m665a2, because using
    that row would open an opportunity window this one says it does not, and
    the header is where "does not provoke" is said.
    """
    if c.strike():
        c.hit()
    c.move(max(1, c.speed_of() // 2))


@power(
    "m665a4",
    level=1,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="missed by an attack",
)
def m665a4(c: Cast) -> None:
    c.shift(1)


#: "+2 to all defences against traps" is the same printed line on two stat
#: blocks, so it is one function used twice rather than copied. What makes
#: it sayable is that a trap is now a thing on the board -- `Cast.is_trap`
#: asks the modifier's context whether the attacker is one.
def wary_of_traps(c: Cast) -> None:
    for d in (AC, FORT, REF, WILL):
        c.bonus(d, 2, on=c.me, until=When.ENCOUNTER,
                when=lambda ctx: c.is_trap(ctx.get("attacker")))


@power(
    "m301a4",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m301a4(c: Cast) -> None:
    """Hard to catch out with a trap. A trait, armed once."""
    wary_of_traps(c)
