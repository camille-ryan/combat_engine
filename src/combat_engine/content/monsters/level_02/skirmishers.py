"""Monster abilities, level 2: the ones that move.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=7)` and `Damage("1d8", 6)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

A **trait** is a standing arrangement rather than something spent on a turn,
so it is written as a row that costs no action, has no target, and arms the
watches that hold it for the rest of the fight. Several rows the database
files as standard actions are plainly traits -- a rider on every attack the
creature makes is not something it does -- and they are written as traits
here, which is what level 1 settled on.

A printed range of "10/20" is a normal range and a long range, and `Range`
holds one number: every such row below takes the **normal** range, so the
creature shoots inside the band where it has no penalty.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    Condition,
    Cover,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Usage,
    When,
    World,
    get,
    power,
    use,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    ConditionApplied,
    ConditionEnded,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    MoveEnd,
    RelationCleared,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import cover_between, distance_between, squares
from combat_engine.engine.triggers import (
    Trigger,
    ally_within,
    both,
    by_me,
    by_melee,
    by_ranged,
    either,
    enemy_within,
    targets_me,
)


def _had_advantage(ev: Hit) -> bool:
    """Did *that* attack have combat advantage?

    Read off the roll rather than asked of the board a second time. Attacking
    gives a hidden creature away and `resolve.attack` clears the relation the
    moment the attack is over, so a body that swings and then asks the board
    gets "no" for every creature that struck from concealment -- which is
    precisely the creature these riders are written for.
    """
    result = getattr(ev, "result", None)
    return bool(result and result.advantage)


def _shed(c: Cast, *kinds: Relation) -> None:
    """Drop every mark or curse laid on the caster -- the effect and the
    relation both, since either one left behind keeps half of it alive."""
    for effect in list(c.world.effects.of(c.me)):
        if any(kind in kinds and target == c.me for kind, _, target in effect.relations):
            c.world.effects.end(effect, c.ref)
    for kind in kinds:
        for source in c.world.relations.sources(kind, c.me):
            c.world.relations.clear(kind, source, c.me, c.ref)


def _conceal(c: Cast) -> None:
    """Go unseen by every enemy whose line to the creature is blocked."""
    for foe in c.enemies():
        if not c.is_hidden(from_=foe) and cover_between(c.world, foe, c.me) is not Cover.NONE:
            c.hide(from_=foe)


def _hides_with_cover(c: Cast) -> None:
    """Hides on anything better than open ground, and keeps doing it.

    The printed line lowers what hiding *requires* -- cover or concealment
    rather than superior cover or total concealment. There is no requirement
    in the engine to lower and no skill check to roll, so what is left that
    can be said is the consequence: wherever it could try, it has. Asked
    again at the top of each of its own turns, because getting back out of
    sight is the whole of a lurker's turn.
    """
    me = c.me

    def each_turn(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            _conceal(c)

    _conceal(c)
    c.watch(TurnStart, each_turn, until=When.ENCOUNTER, on=me, label=f"{c.ref} unseen")


def _still_hidden_on_a_miss(c: Cast, reaches: tuple[str, ...]) -> None:
    """Missing from hiding does not give the creature away.

    Attacking normally breaks hidden -- `resolve.attack` clears it for
    whoever swung -- so this is written as the exemption it is printed as
    rather than as a special case inside the engine. The miss is noted while
    the creature is still unseen, and the break is undone as it happens.
    """
    me = c.me
    spared: set[int] = set()

    def missed(ev: Miss) -> None:
        p = get(ev.power)
        if ev.attacker != me or p is None or p.reach.kind not in reaches:
            return
        if c.is_hidden(from_=ev.target):
            spared.add(ev.target)

    def broke(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.HIDDEN_FROM or ev.source != me:
            return
        if ev.why == "attacked" and ev.target in spared:
            spared.discard(ev.target)
            c.world.relations.set(Relation.HIDDEN_FROM, me, ev.target)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=f"{c.ref} keeps cover")
    c.watch(RelationCleared, broke, until=When.ENCOUNTER, on=me, label=f"{c.ref} keeps cover")


def _advantage_rider(c: Cast, dice: str, reaches: tuple[str, ...] = ()) -> None:
    """Extra damage whenever it lands one with the drop on the target.

    `reaches` names the ranges the printed line applies to, where it names
    any; left empty it is every attack the creature makes.
    """
    me = c.me
    ref = c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not _had_advantage(ev):
            return
        p = get(ev.power)
        if reaches and (p is None or p.reach.kind not in reaches):
            return
        c.damage(dice, on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


def _heals_its_killer(c: Cast, amount: int) -> None:
    """Anyone who lands a critical on it is paid for it."""
    me = c.me

    def reward(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            c.heal(amount, on=ev.attacker)

    c.watch(Hit, reward, until=When.ENCOUNTER, on=me, label=f"{c.ref} crit")


def _unseen(world: World, eid: int) -> bool:
    return bool(world.relations.targets(Relation.HIDDEN_FROM, eid))


def _beside_a_ward(c: Cast, who: int | None) -> bool:
    """Is that creature standing next to something the caster is guarding?

    Asked at the moment of the roll rather than when the trait arms: what a
    guard is protecting can change mid-fight, and who is next to it changes
    every time anything moves.
    """
    return who is not None and any(
        distance_between(c.world, who, ward) <= 1 for ward in c.guarding()
    )


def _flanks_with(c: Cast, foe: int, mate: int) -> bool:
    """Is the caster flanking `foe` with that *particular* creature?

    `query.flanked_by` asks whether any ally at all is on the far side; the
    printed line names one, so the grid is asked directly instead.
    """
    space = squares(c.world, foe)
    return any(
        c.world.grid.flanks(a, b, space)
        for a in squares(c.world, c.me)
        for b in squares(c.world, mate)
    )


def _squeezes_freely(c: Cast) -> None:
    """Folding into a small space costs this creature nothing.

    Half speed, the -5 to attacks and the combat advantage it hands out are
    the *whole* of what `Condition.SQUEEZING` is, and the printed line
    waives all three -- so the hold is taken off as it lands rather than
    three separate counterweights being written against it. `Effects.apply`
    installs everything before it announces, which is what makes ending an
    effect from inside `ConditionApplied` safe.
    """
    me, ref = c.me, c.ref

    def unsqueeze(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.SQUEEZING:
            return
        for eff in list(c.world.effects.of(me)):
            if Condition.SQUEEZING in eff.conditions:
                c.world.effects.end(eff, ref)

    c.watch(ConditionApplied, unsqueeze, until=When.ENCOUNTER, on=me, label=ref)


# --------------------------------------------------------------------------
# m189
# --------------------------------------------------------------------------


@power(
    "m189a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m189a0(c: Cast) -> None:
    """A rider on every attack, so a trait rather than an action."""
    _advantage_rider(c, "1d6")


@power(
    "m189a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m189a1(c: Cast) -> None:
    """Rough ground costs it nothing.

    The printed line is about shifting in particular and `c.ignores_difficult`
    is about moving at all -- nothing distinguishes the two, and the broader
    reading is the one that can be said. Worth narrowing if a
    `when=` gate on movement mode ever exists.
    """
    c.ignores_difficult(until=When.ENCOUNTER)


@power(
    "m189a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 6),
)
def m189a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m189a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 5),
)
def m189a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m189a4",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    damage=Damage("", 4, kind=LIMITED),
)
def m189a4(c: Cast) -> None:
    """Both weapons into one creature, and a bonus for landing both.

    The two attacks are the rows that print them rather than copies, so their
    damage lines stay in one place. `use` reports whether a power went off,
    not whether it hit, so the hits are counted off the bus for the duration
    of the pair.
    """
    victim = c.target
    if victim is None:
        return
    landed: list[str] = []

    def tally(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            landed.append(ev.power)

    sub = c.world.bus.on(Hit, tally, owner=c.me)
    try:
        for ref in ("m189a2", "m189a3"):
            use(c.world, c.me, ref, targets=[victim], spend=False)
    finally:
        c.world.bus.off(sub)
    if len(landed) == 2:
        c.hit(on=victim)


_M189_ROLLED = "the m189 makes an attack roll"


@power(
    "m189a5",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M189_ROLLED,
    on=Trigger(AttackRolled, when=by_me, text=_M189_ROLLED),
)
def m189a5(c: Cast) -> None:
    """The second result stands, good or bad.

    Answered on `AttackRolled`, which is emitted before the hit or miss is
    announced, so the rerolled number is the one the attack resolves on.
    """
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m234
# --------------------------------------------------------------------------


@power(
    "m234a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m234a0(c: Cast) -> None:
    """An aura 1 whose occupants give away their guard.

    Membership is diffed by the zone rather than recomputed: `ZoneEntered`
    and `ZoneExited` are exactly the two moments the relation should be set
    and dropped. The printed line is unqualified -- it grants the advantage
    to everybody -- and the relation names one beneficiary, so it is set for
    the creature and each ally it has at the moment the enemy walks in.

    Whoever is already standing inside is granted separately at the end.
    Making the aura refreshes membership on the spot, before its id exists
    for a listener to recognise, so arming the watches first is not enough:
    the creatures the fight starts beside arrive before anything can hear
    them.
    """
    held: dict[int, Effect] = {}
    ring = c.aura(1, until=When.ENCOUNTER)

    def grant(who: int) -> None:
        if who in held or who not in c.enemies():
            return
        held[who] = c.world.effects.apply(
            who,
            c.me,
            When.ENCOUNTER,
            label=c.ref,
            relations=[(Relation.GRANTS_CA_TO, who, w) for w in (c.me, *c.allies())],
        )

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            grant(ev.actor)

    def left(ev: ZoneExited) -> None:
        effect = held.pop(ev.actor, None) if ev.zone == ring else None
        if effect is not None:
            c.world.effects.end(effect, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=c.me, label="m234a0 in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=c.me, label="m234a0 out")
    for actor in c.world.zones.occupants(ring):
        grant(actor)


@power(
    "m234a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m234a1(c: Cast) -> None:
    """Extra damage against whoever the pack has surrounded.

    The ally pool includes the creature itself, so it is filtered out: the
    printed line counts its allies and it is not one of them.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        pack = [a for a in c.within(1, of=ev.target, side="ally") if a != me]
        if len(pack) >= 2:
            c.damage("1d6", on=ev.target, detail="m234a1")

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m234a1")


@power(
    "m234a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 3),
)
def m234a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m236
# --------------------------------------------------------------------------


@power(
    "m236a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 3),
)
def m236a0(c: Cast) -> None:
    """The printed critical -- 1d8 + 11 -- is the ordinary rule: a critical
    maxes the dice, and 8 + 3 is what the card prints."""
    if c.strike():
        c.hit()


@power(
    "m236a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 3),
)
def m236a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m236a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m236a2(c: Cast) -> None:
    """Filed as a standard action and plainly a trait: it is a rider on
    every attack. The printed line names the two reaches it pays on, so a
    close or area attack does not get it."""
    _advantage_rider(c, "1d6", ("melee", "ranged"))


_M236_HURT = "the m236 takes damage"


@power(
    "m236a3",
    level=2,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M236_HURT,
    on=Trigger(DamageApplied, when=targets_me, text=_M236_HURT),
)
def m236a3(c: Cast) -> None:
    """Gone from sight until it attacks or the clock runs out.

    Attacking gives it away whether or not the attack lands, so the watch is
    on the roll rather than on the hit, and it is torn down with the veil so
    a second vanishing does not inherit the first one's listener.
    """
    veil = c.invisible(until=When.EONT)
    if veil is None:
        return
    me = c.me

    def reveal(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(veil, "it attacked")

    seen = c.watch(AttackRolled, reveal, until=When.EONT, on=me, label="m236a3")
    veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))


@power(
    "m236a4",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m236a4(c: Cast) -> None:
    """Starts the fight unseen by whoever it had something to stand behind.

    A trait is armed as the encounter starts, which is the moment the printed
    line names. There are no skill checks in the engine, so the Stealth check
    is taken as made; the cover is testable and is asked of each enemy
    separately, because one may have a clear line where another does not.
    """
    _conceal(c)


@power(
    "m236a5",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m236a5(c: Cast) -> None:
    _still_hidden_on_a_miss(c, ("melee", "ranged"))


# --------------------------------------------------------------------------
# m265
# --------------------------------------------------------------------------


@power(
    "m265a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m265a0(c: Cast) -> None:
    """Harder to catch on the way past.

    A gate rather than an effect put on and taken off around every move: the
    attack context carries `opportunity`, so the modifier is asked whether it
    applies at the moment the defence is read.
    """
    c.bonus(
        AC,
        2,
        until=When.ENCOUNTER,
        on=c.me,
        kind="racial",
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m265a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 5),
)
def m265a1(c: Cast) -> None:
    """The shift is an Effect line: it happens whether or not the blow lands.

    The extra die is read off the roll that was just made rather than asked
    of the board afterwards -- see `_had_advantage`.
    """
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.damage("1d6")
    c.shift(1)


@power(
    "m265a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d4", 5),
)
def m265a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.damage("1d6")


@power(
    "m265a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m265a3(c: Cast) -> None:
    """Strike, then cover ground without the target getting a swing in.

    The blade is m265a1 rather than a copy of it, so the damage line stays in
    one place. The attack is taken *before* the move, for the reason level 1
    gives on its own two of these: the move picks its own destination and one
    taken first can leave the target out of reach. The printed line allows
    either order.
    """
    c.no_provoke(from_=c.target)
    use(c.world, c.me, "m265a1", targets=[c.target], spend=False)
    c.move(4)


# --------------------------------------------------------------------------
# m2798
# --------------------------------------------------------------------------


@power(
    "m2798a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.ACID),
)
def m2798a0(c: Cast) -> None:
    """The extra die lands only on a creature already burning.

    Asked of the effect table rather than of anything the attack carries:
    "already has ongoing acid damage" is about the target's condition and
    says nothing about where it came from, so somebody else's acid counts.
    """
    if not c.strike():
        return
    burning = any(
        eff.ongoing is not None and eff.ongoing[1] is DamageType.ACID
        for eff in c.world.effects.of(c.target)
    )
    c.hit()
    if burning:
        c.damage("1d10", dtype=DamageType.ACID)


_M2798_ALLY_DOWN = "an ally within 10 squares drops to 0 hit points"


@power(
    "m2798a1",
    level=2,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2798_ALLY_DOWN,
    on=Trigger(Dropped, when=ally_within(10), text=_M2798_ALLY_DOWN),
)
def m2798a1(c: Cast) -> None:
    """It loses interest in whoever was holding it and moves off.

    The printed line names one kind of ally; nothing distinguishes a
    creature's own kind from any other ally at ten squares, so every ally
    counts. Narrow it if a "same stat block" predicate is ever written.
    """
    _shed(c, Relation.MARKED_BY, Relation.CURSED_BY)
    c.shift(2)


# --------------------------------------------------------------------------
# m2822
# --------------------------------------------------------------------------


@power(
    "m2822a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3),
)
def m2822a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2822a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m2822a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2822a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RELIABLE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 3, kind=LIMITED),
)
def m2822a2(c: Cast) -> None:
    """Slips whatever was holding it, crosses four squares and cuts.

    The penalty is written as a gate rather than a flat one: it is only paid
    when this creature is the one being swung at, which the modifier's
    context can answer at the moment the roll is made.
    """
    _shed(c, Relation.MARKED_BY)
    c.shift(4)
    if c.strike():
        c.hit()
        c.penalty(
            "attack",
            4,
            on=c.target,
            until=When.EONT,
            when=lambda ctx: ctx.get("target") == c.me,
        )


@power(
    "m2822a3",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m2822a3(c: Cast) -> None:
    """A standing arrangement, not an action, whatever the database says."""
    _heals_its_killer(c, 4)


# --------------------------------------------------------------------------
# m283
# --------------------------------------------------------------------------


@power(
    "m283a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d8", 1),
)
def m283a0(c: Cast) -> None:
    """The shift is printed on the hit line, so a miss stays put."""
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m283a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 3),
)
def m283a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m283a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=4),
    damage=Damage("1d8", 1, kind=LIMITED),
)
def m283a2(c: Cast) -> None:
    """The printed Requirement names the weapon in its hand, and a monster's
    gear is not modelled by name -- it is the same line m283a0 swings, so the
    row is left usable rather than gated on something nothing can answer."""
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)
        c.shift(1)


@power(
    "m283a3",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m283a3(c: Cast) -> None:
    _advantage_rider(c, "1d6", ("melee", "ranged"))


# --------------------------------------------------------------------------
# m3001
# --------------------------------------------------------------------------


@power(
    "m3001a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m3001a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3001a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3001a1(c: Cast) -> None:
    """A standing bonus rather than an action, whatever the section line says.

    Gated at the moment of the roll, because what it is guarding and who is
    pressed against that creature both change during a fight.
    """
    c.bonus(
        "attack",
        2,
        until=When.ENCOUNTER,
        on=c.me,
        when=lambda ctx: _beside_a_ward(c, ctx.get("target")),
    )


@power(
    "m3001a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3001a2(c: Cast) -> None:
    """An extra die whenever the two of them have an enemy between them.

    Dice rather than a flat number, so it is rolled as the blow lands
    instead of riding along as a damage modifier -- and the flanking is read
    against the guarded creature by name, which `query.flanked_by` cannot do.
    """
    me = c.me

    def press(ev: Hit) -> None:
        if ev.attacker != me:
            return
        if any(_flanks_with(c, ev.target, ward) for ward in c.guarding()):
            c.damage("1d6", on=ev.target, detail="m3001a2")

    c.watch(Hit, press, until=When.ENCOUNTER, on=me, label="m3001a2")


@power(
    "m3001a3",
    level=2,
    usage=AT_WILL,
    action=ActionType.MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3001a3(c: Cast) -> None:
    c.shift(3)


# --------------------------------------------------------------------------
# m3054
# --------------------------------------------------------------------------


@power(
    "m3054a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3054a0(c: Cast) -> None:
    """An ooze pours through a gap without slowing down or opening up."""
    _squeezes_freely(c)


@power(
    "m3054a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("1d6", 6, dtype=DamageType.ACID),
)
def m3054a1(c: Cast) -> None:
    """Each application is its own effect, which is what makes the printed
    penalty cumulative without anything having to add them up."""
    if c.strike():
        c.hit()
        c.penalty(FORT, 2, until=When.SAVE_ENDS)


@power(
    "m3054a2",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3054a2(c: Cast) -> None:
    c.shift(2)


# --------------------------------------------------------------------------
# m386
# --------------------------------------------------------------------------


@power(
    "m386a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3),
)
def m386a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(3)


# --------------------------------------------------------------------------
# m485
# --------------------------------------------------------------------------


@power(
    "m485a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 5),
)
def m485a0(c: Cast) -> None:
    """A bigger bite on a creature already down, and it knocks one down.

    Prone is read *before* the damage, or the extra die would land on a
    target this very attack has just put on the floor. The shift is an
    Effect line and is taken whether the bite landed or not.
    """
    if c.strike():
        was_prone = c.is_(Condition.PRONE)
        c.hit()
        if was_prone:
            c.damage("1d6")
        elif c.result is not None and c.result.advantage:
            c.prone()
    c.shift(4)


# --------------------------------------------------------------------------
# m4881
# --------------------------------------------------------------------------


@power(
    "m4881a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4881a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m4881a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 5),
)
def m4881a1(c: Cast) -> None:
    """"Or 1d12 + 5 while bloodied" is a second expression rather than a
    rider on the first, so the bloodied branch is rolled in the body. Only
    the printed line in the header rescales between editions."""
    if not c.strike():
        return
    if c.bloodied(on=c.me):
        c.damage("1d12", 5)
    else:
        c.hit()


@power(
    "m4881a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=5),
    damage=Damage("2d6", 4, kind=LIMITED),
)
def m4881a2(c: Cast) -> None:
    """In, bite, out again. Both shifts are Effect lines and are taken
    whether or not the bite landed."""
    c.shift(3)
    if c.strike():
        if c.bloodied(on=c.me):
            c.damage("2d12", 4)
        else:
            c.hit()
    c.shift(3)


@power(
    "m4881a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=5),
)
def m4881a3(c: Cast) -> None:
    """No damage at all: the slide is the whole of the hit line."""
    if c.strike():
        c.slide(1)


# --------------------------------------------------------------------------
# m4995
# --------------------------------------------------------------------------


@power(
    "m4995a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4995a0(c: Cast) -> None:
    _hides_with_cover(c)


@power(
    "m4995a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
)
def m4995a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4995a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 5),
    requires=_unseen,
    requires_text="the target cannot see it",
)
def m4995a2(c: Cast) -> None:
    """Only into a creature that cannot see it coming.

    The printed restriction is per target and the header's `target` field
    cannot say so, so `requires` carries the half about the creature -- being
    unseen at all -- and the body checks this target. The slow and the poison
    are one effect with one saving throw, as printed: "save ends both".
    """
    victim = c.target
    if victim is None or not c.world.relations.holds(Relation.HIDDEN_FROM, c.me, victim):
        return
    if not c.strike():
        return
    c.hit()

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            on=eff.owner,
            ongoing=(5, DamageType.POISON),
        )

    c.condition(
        Condition.SLOWED,
        until=When.SAVE_ENDS,
        ongoing=(5, DamageType.POISON),
        escalate=worsen,
    )


# --------------------------------------------------------------------------
# m5026
# --------------------------------------------------------------------------


@power(
    "m5026a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5026a0(c: Cast) -> None:
    _hides_with_cover(c)


@power(
    "m5026a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5026a1(c: Cast) -> None:
    _still_hidden_on_a_miss(c, ("ranged",))


@power(
    "m5026a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5026a2(c: Cast) -> None:
    """Five extra against anybody it is unseen by.

    Not the same clause as combat advantage even though being unseen grants
    it: a flanked enemy that can see the creature perfectly well pays
    nothing. The relation is still standing when the hit is announced --
    `resolve` clears it on the line after -- so it is asked directly.
    """
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and c.world.relations.holds(Relation.HIDDEN_FROM, me, ev.target):
            c.flat(5, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m5026a2")


@power(
    "m5026a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 5),
)
def m5026a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5026a4",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d10", 3),
)
def m5026a4(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5026_CAME_CLOSE = "an enemy ends its movement within 2 squares of the m5026"


@power(
    "m5026a5",
    level=2,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5026_CAME_CLOSE,
    on=Trigger(MoveEnd, when=enemy_within(2), text=_M5026_CAME_CLOSE),
)
def m5026a5(c: Cast) -> None:
    """Steps back and marks whoever came too close.

    The extra damage is written; ignoring cover and concealment is not --
    `c.strike` has no way to say so, though `resolve.attack` itself takes an
    `ignore_cover`.
    """
    foe = getattr(c.trigger, "actor", None)
    c.shift(3)
    if foe is None:
        return
    me = c.me

    def rider(ev: Hit) -> None:
        p = get(ev.power)
        if ev.attacker != me or ev.target != foe:
            return
        if p is not None and p.reach.kind == "ranged":
            c.flat(5, on=foe)

    c.watch(Hit, rider, until=When.EONT, on=me, label="m5026a5")


# --------------------------------------------------------------------------
# m668
# --------------------------------------------------------------------------


@power(
    "m668a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=3),
    damage=Damage("1d6", 3),
)
def m668a0(c: Cast) -> None:
    """The secondary attack is rolled in the body.

    A header carries one attack line and this row prints two, so the printed
    +2 vs. Fortitude goes through `scaling.trim` by hand -- exactly what
    `Attack(printed=...)` does with the first one -- rather than being
    written as a raw bonus that would not move with the treadmill.
    """
    if not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(2, c.level), FORT):
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m668a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=5),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC),
)
def m668a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m668a2",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m668a2(c: Cast) -> None:
    """A standing bonus rather than an action, whatever the section line says.

    Only the "adjacent to" half is sayable. Nothing on the board is
    *carried* -- there is no inventory and no way to ask who is holding
    what -- so a creature walking off with the guarded thing gets the same
    treatment as one standing a long way from it. See the report.
    """
    c.bonus(
        "attack",
        4,
        until=When.ENCOUNTER,
        on=c.me,
        when=lambda ctx: _beside_a_ward(c, ctx.get("target")),
    )



@power(
    "m668a3",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m668a3(c: Cast) -> None:
    """Unseen by anybody dazed, for exactly as long as the daze lasts.

    Hung on the two condition events rather than asked when an attack is
    made: `HIDDEN_FROM` is what combat advantage and line of sight already
    read, so it has to be set and dropped rather than computed. Attacking
    normally breaks it, and here it should not -- the printed line is a flat
    statement about dazed creatures -- so the break is undone as it happens.
    """
    me = c.me
    veils: dict[int, Effect] = {}

    def blind(ev: ConditionApplied) -> None:
        if ev.condition is not Condition.DAZED or ev.target == me or ev.target in veils:
            return
        veil = c.invisible(to=ev.target, until=When.ENCOUNTER)
        if veil is not None:
            veils[ev.target] = veil

    def wakes(ev: ConditionEnded) -> None:
        if ev.condition is not Condition.DAZED:
            return
        veil = veils.pop(ev.target, None)
        if veil is not None:
            c.world.effects.end(veil, "no longer dazed")

    def broke(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.HIDDEN_FROM or ev.source != me:
            return
        if ev.why == "attacked" and ev.target in veils:
            c.world.relations.set(Relation.HIDDEN_FROM, me, ev.target)

    c.watch(ConditionApplied, blind, until=When.ENCOUNTER, on=me, label="m668a3")
    c.watch(ConditionEnded, wakes, until=When.ENCOUNTER, on=me, label="m668a3 ends")
    c.watch(RelationCleared, broke, until=When.ENCOUNTER, on=me, label="m668a3 keep")


_M668_SWUNG_AT = "the m668 is targeted by a melee or a ranged attack"


@power(
    "m668a4",
    level=2,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    attack=Attack(vs=WILL, printed=4),
    trigger=_M668_SWUNG_AT,
    on=Trigger(
        AttackDeclared,
        when=both(targets_me, either(by_melee, by_ranged)),
        text=_M668_SWUNG_AT,
    ),
)
def m668a4(c: Cast) -> None:
    """Puts somebody else in the way of the blow.

    `c.redirect` only works in the interrupt window, which is where this row
    sits. The printed line gives the counter-attack no range at all, so the
    header carries none and the roll is aimed at whoever swung, at whatever
    distance. Nobody adjacent to take the blow and the row does nothing.
    """
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None or not c.strike(on=attacker):
        return
    shields = [w for w in c.within(1) if w not in (c.me, attacker)]
    if shields:
        c.redirect(to=c.choose(sorted(shields), "who takes it instead"))
