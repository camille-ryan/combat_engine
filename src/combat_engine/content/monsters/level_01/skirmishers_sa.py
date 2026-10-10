"""Monster abilities, level 1, skirmishers: the second sweep.

Twenty-four stat blocks whose rows were still undeclared. `skirmishers.py`
holds the first sweep of this level and this file holds the rest; the split is
by *when* the work was done, not by what the creatures are, so the conventions
are the ones that file settled and they are kept here unchanged:

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=AC, printed=6)`) and the damage line goes in the header as data
  so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight. Several rows the database
  files as standard actions are plainly traits and are written as such;
* a printed range of "15/30" takes the **normal** range, so the creature
  shoots inside the band where it has no penalty;
* combat advantage is read off the roll rather than asked of the board
  afterwards, because `resolve.attack` clears `HIDDEN_FROM` the moment the
  attack is over.

Two things this level made the author stop and think about.

**"Where it started its turn" is only knowable at the start of that turn.**
Four rows here pay out on a creature ending its move some distance from where
it began, so the square is recorded on `TurnStart` and read back on `TurnEnd`.
There is no per-turn record of how far a creature has walked, which is a
different question and the one `_shifted_this_turn` has to count by hand.

**Reach and range are taken from the printed line and nowhere else**, even
where the line is odd -- "Melee 10" is written as `Melee(10)`, because that is
what the card says and `cards.py` checks the card.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.engine import (
    AC,
    AT_WILL,
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
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Health,
    Ident,
    Keyword,
    Melee,
    MeleeOrRanged,
    Position,
    Ranged,
    Relation,
    Square,
    Usage,
    When,
    Window,
    World,
    distance,
    get,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackRolled,
    DamageApplied,
    DamageRolled,
    Dropped,
    Hit,
    Miss,
    Moved,
    MoveStart,
    SurgeSpent,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    allies,
    creatures,
    distance_between,
    enemies,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, both, by_melee, targets_me

#: The five damage types the demon's resistance row answers to.
_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _bloodied(world: World, eid: int) -> bool:
    hp = world.get(eid, Health)
    return hp is not None and 0 < hp.hp <= hp.max_hp // 2


def _while_bloodied(world: World, eid: int) -> bool:
    """The printed "usable only while bloodied" Requirement, as a gate."""
    return _bloodied(world, eid)


def _bloodied_within(reach: int):  # noqa: ANN202
    """"One bloodied creature" as an entry gate rather than a body check.

    `Target` has no field for it, and a body that looks and returns is an
    action the policy spends on nothing. `dsl.usable` is handed `(world, eid)`,
    so the question has to be asked from the caster's end.
    """

    def gate(world: World, eid: int) -> bool:
        return any(
            distance_between(world, eid, foe) <= reach and _bloodied(world, foe)
            for foe in enemies(world, eid)
        )

    return gate


def _not_grabbing(world: World, eid: int) -> bool:
    """The printed "must have no creature grabbed" Requirement."""
    return not world.relations.targets(Relation.GRABBED_BY, eid)


def _beside_kind(ref: str):  # noqa: ANN202
    """"Only while adjacent to a <ref>", which is an ally of one stat block."""

    def gate(world: World, eid: int) -> bool:
        for mate in allies(world, eid):
            if mate == eid or distance_between(world, eid, mate) > 1:
                continue
            ident = world.get(mate, Ident)
            if ident is not None and ident.ref == ref:
                return True
        return False

    return gate


def _adjacent_foes(c: Cast, reach: int = 1) -> list[int]:
    return [foe for foe in c.enemies() if c.distance(foe) <= reach]


def _armed(c: Cast, label: str) -> bool:
    """Is a watch with this label already standing on the caster?

    An at-will row that arms a lasting rider is used again and again, and a
    second copy of the rider pays out twice for one printed sentence.
    """
    return any(effect.label == label for effect in c.world.effects.of(c.me))


def _had_advantage(ev: Any) -> bool:
    """Did that blow have combat advantage? Read off the roll, not the board.

    `resolve.attack` clears `HIDDEN_FROM` as soon as the attack is over, and a
    one-shot grant has already been spent, so asking the board again answers
    about a world that no longer exists.
    """
    result = getattr(ev, "result", None)
    return bool(result and result.advantage)


def _advantage_rider(
    c: Cast, dice: str, *, dtype: DamageType = DamageType.UNTYPED
) -> None:
    """Extra damage whenever it lands one with the drop on the target."""
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me or not _had_advantage(ev):
            return
        c.damage(dice, dtype=dtype, on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


def _heals_its_killer(c: Cast, amount: int) -> None:
    """Anyone who lands a critical on it is paid for it."""
    me = c.me

    def reward(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            c.heal(amount, on=ev.attacker)

    c.watch(Hit, reward, until=When.ENCOUNTER, on=me, label=f"{c.ref} crit")


def _crowd_around(c: Cast, victim: int, *, least: int) -> bool:
    """Has that enemy got at least this many of the creature's allies on it?"""
    return (
        sum(
            1
            for mate in c.allies()
            if mate != victim and distance_between(c.world, mate, victim) <= 1
        )
        >= least
    )


def _mobile_attack(c: Cast, total: int, *, ranged: bool = False) -> None:
    """Move, swing once on the way, move on -- and no opening for the victim.

    The distance is spent in two halves rather than all at once, because "at
    any point during the movement" is what puts a creature in reach that one
    step to one destination would not.
    """
    half = max(1, total // 2)
    c.move(half)
    foe = next(iter(_adjacent_foes(c, 99 if ranged else 1)), None)
    if foe is not None:
        c.no_provoke(from_=foe, on=c.me, until=When.EOT)
        c.basic(on=foe, ranged=ranged)
    rest = total - half
    if rest > 0:
        c.move(rest)


def _shift_through(c: Cast, total: int) -> bool:
    """Shift, and let the step land in an occupied square where it must.

    "It can move through enemies' spaces" is `share=True` on the step rather
    than a waiver of anything: `movement.shift` refuses an occupied square
    outright, so without it the printed line changes nothing at all.
    """
    for foe in _adjacent_foes(c, total):
        for sq in sorted(squares(c.world, foe)):
            if c.shift(total, to=sq, share=True):
                return True
    return c.shift(total)


def _moved_far(c: Cast, who: int, far: int, pay: Any) -> None:
    """Pay out when that creature ends its turn `far` from where it began.

    Both watches are held for the encounter: a duration that runs out *at* the
    end of a turn cannot be relied on to outlive the end of that turn, which
    is the half of this that has to survive to be read.
    """
    began: dict[str, Square | None] = {"at": None}

    def opened(ev: TurnStart) -> None:
        if ev.actor != who or ev.ghost:
            return
        pos = c.world.get(who, Position)
        began["at"] = pos.square if pos else None

    def closed(ev: TurnEnd) -> None:
        if ev.actor != who or ev.ghost or began["at"] is None:
            return
        pos = c.world.get(who, Position)
        if pos is not None and distance(pos.square, began["at"]) >= far:
            pay()
        began["at"] = None

    c.watch(TurnStart, opened, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} start")
    c.watch(TurnEnd, closed, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} end")


def _until_its_next_turn(c: Cast, who: int, held: Effect | None) -> None:
    """End an effect at the *start of another creature's* next turn.

    `When.SOTNT` measures against whoever carries the effect, and these rows
    print a window measured against a third creature -- the mount, or the
    creature whose move earned the bonus. Ended by hand, once.
    """
    if held is None:
        return

    def expire(ev: TurnStart) -> None:
        if ev.actor == who:
            c.world.effects.end(held, "the window closed")

    c.watch(
        TurnStart, expire, until=When.ENCOUNTER, on=c.me, once=True,
        label=f"{c.ref} window",
    )


def _travelled_this_turn(c: Cast, *kinds: str) -> int:
    """How far the creature has moved this turn, counting only those kinds.

    Nothing records it. `Movement` says what a creature *can* do and never what
    it did, and `Moved` is the only event that says -- so the steps are tallied
    as they happen. **Kept as a modifier rather than in a dictionary here**: a
    `When.EOT` bonus expires at the end of the turn it was laid in, which is
    exactly the window "since the start of its turn" names, and `c.total` reads
    the sum back. No state in this module and nothing to reset.

    The counter is armed the first time the row that reads it is used, which is
    the half that cannot be fixed from here: a creature's movement before that
    first use is not recorded anywhere to go back and read.
    """
    me, key = c.me, f"{c.ref} steps"
    label = f"{c.ref} odometer"
    if not _armed(c, label):

        def stepped(ev: Moved) -> None:
            if ev.actor != me or getattr(ev, "kind_", "") not in kinds:
                return
            far = max(abs(ev.to[0] - ev.from_[0]), abs(ev.to[1] - ev.from_[1]))
            if far:
                c.bonus(key, far, on=me, until=When.EOT)

        c.watch(Moved, stepped, until=When.ENCOUNTER, on=me, label=label)
    return c.total(key, on=me)


def _foe_ended_within(radius: int):  # noqa: ANN202
    """"An enemy ends its turn within N squares of it."""

    def test(world: World, me: int, ev: Any) -> bool:
        actor = getattr(ev, "actor", None)
        if actor is None or actor == me or getattr(ev, "ghost", False):
            return False
        return (
            team(world, actor) is not team(world, me)
            and distance_between(world, me, actor) <= radius
        )

    return test


def _foe_moved_within(radius: int):  # noqa: ANN202
    """"An enemy within N squares of it moves."

    `MoveStart`, so the responder sees the board the enemy is leaving. On
    `MoveEnd` the enemy has already gone and the distance that qualified it is
    no longer the one measured.
    """

    def test(world: World, me: int, ev: Any) -> bool:
        actor = getattr(ev, "actor", None)
        if actor is None or actor == me:
            return False
        return (
            team(world, actor) is not team(world, me)
            and distance_between(world, me, actor) <= radius
        )

    return test


def _damaged_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "amount", 0) > 0


def _burned_me(world: World, me: int, ev: Any) -> bool:
    return _damaged_me(world, me, ev) and getattr(ev, "dtype", None) is DamageType.FIRE


def _elemental_hurt(world: World, me: int, ev: Any) -> bool:
    return _damaged_me(world, me, ev) and getattr(ev, "dtype", None) in _ELEMENTS


def _i_rolled_one(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "attacker", None) == me


def _by_hand(ref: str) -> bool:
    """Was the blow a melee or a ranged attack's? Not close, not area."""
    row = get(ref)
    return row is not None and row.reach.kind in ("melee", "ranged")


def _shed(c: Cast, kind: Relation) -> None:
    """Drop every mark laid on the caster -- the effect and the relation both,
    since either one left behind keeps half of it alive."""
    me = c.me
    for effect in list(c.world.effects.of(me)):
        if any(k is kind and t == me for k, _, t in effect.relations):
            c.world.effects.end(effect, c.ref)
    for source in c.world.relations.sources(kind, me):
        c.world.relations.clear(kind, source, me, c.ref)


def _vanish_until_it_swings(c: Cast, until: When) -> None:
    """Unseen until it hits or misses with an attack, or the window closes."""
    me = c.me
    hidden = c.invisible(on=me, until=until)
    if hidden is None:
        return

    def show(ev: Any) -> None:
        if getattr(ev, "attacker", None) == me:
            c.world.effects.end(hidden, "it attacked")

    for event in (Hit, Miss):
        c.watch(event, show, until=until, on=me, once=True, label=f"{c.ref} unseen")


def _squeezes_freely(c: Cast) -> None:
    """"It moves at full speed while squeezing", which is a waiver of the
    halving `conditions` applies and not a speed bonus: the two come apart the
    moment anything else slows the creature."""
    c.ignore_condition(Condition.SQUEEZING, on=c.me, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m115782
# --------------------------------------------------------------------------


@power(
    "m115782a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115782a0(c: Cast) -> None:
    """Extra damage bought by the mount's legs, not the rider's.

    The mount is read inside the watch rather than when the trait arms: a
    rider can be put on a different beast mid-fight, and a mount worked out
    now would be the wrong creature from then on. The window closes at the
    start of the *mount's* next turn, which no `When` measures, so it is ended
    by hand.
    """
    me = c.me
    seen: dict[str, Square | None] = {"at": None}

    def opened(ev: TurnStart) -> None:
        beast = c.mount()
        if beast is None or ev.actor != beast or ev.ghost:
            return
        pos = c.world.get(beast, Position)
        seen["at"] = pos.square if pos else None

    def closed(ev: TurnEnd) -> None:
        beast = c.mount()
        if beast is None or ev.actor != beast or ev.ghost or seen["at"] is None:
            return
        pos = c.world.get(beast, Position)
        started, seen["at"] = seen["at"], None
        if pos is None or distance(pos.square, started) < 4:
            return
        held = c.bonus("damage", 0, dice="1d6", on=me, until=When.ENCOUNTER)
        _until_its_next_turn(c, beast, held)

    c.watch(TurnStart, opened, until=When.ENCOUNTER, on=me, label=f"{c.ref} start")
    c.watch(TurnEnd, closed, until=When.ENCOUNTER, on=me, label=f"{c.ref} end")


@power(
    "m115782a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 6),
)
def m115782a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115782a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m115782a2(c: Cast) -> None:
    if c.strike():
        c.hit()


def _mounted(world: World, eid: int) -> bool:
    return bool(world.relations.sources(Relation.RIDDEN_BY, eid))


def _missed_me_or_my_mount(world: World, me: int, ev: Any) -> bool:
    victim = getattr(ev, "target", None)
    if victim is None:
        return False
    carried = world.relations.sources(Relation.RIDDEN_BY, me)
    return victim == me or victim in carried


_M115782_MISSED = "it or its mount is missed by a melee attack"


@power(
    "m115782a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_mounted,
    requires_text="it must be mounted",
    trigger=_M115782_MISSED,
    on=Trigger(Miss, _missed_me_or_my_mount, _M115782_MISSED),
)
def m115782a3(c: Cast) -> None:
    """The mount steps, not the rider -- `who=` names it."""
    beast = c.mount()
    if beast is not None:
        c.shift(1, who=beast)


# --------------------------------------------------------------------------
# m3332
# --------------------------------------------------------------------------


@power(
    "m3332a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 2),
)
def m3332a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3332a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 2),
)
def m3332a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3332a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3332a2(c: Cast) -> None:
    _mobile_attack(c, c.speed_of(), ranged=True)


@power(
    "m3332a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3332a3(c: Cast) -> None:
    """A trait, whatever the database files it as: nothing is spent on it and
    it has no target. The window is "until the start of its next turn", which
    is `SOTNT` measured against the creature holding the bonus -- itself, so
    the ordinary duration says it exactly."""
    me = c.me

    def paid() -> None:
        c.bonus(
            "damage", 0, dice="1d6", on=me, until=When.SOTNT,
            when=lambda ctx: bool(ctx.get("ranged")),
        )

    _moved_far(c, me, 4, paid)


_M3332_MISSED = "it is missed by a melee attack"


@power(
    "m3332a4",
    level=1,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3332_MISSED,
    on=Trigger(Miss, both(targets_me, by_melee), _M3332_MISSED),
)
def m3332a4(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m3435
# --------------------------------------------------------------------------


@power(
    "m3435a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m3435a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3435a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=4),
    damage=Damage("1d4", 4, dtype=DamageType.PSYCHIC),
    dropped=("query.moved_this_turn(world, eid)",),
)
def m3435a1(c: Cast) -> None:
    """A dive: the attack, then the rest of the flight.

    "It must move at least 2 squares before using this attack" is a
    Requirement nothing can read -- there is no record of how far a creature
    has moved this turn -- so the row is offered a step sooner than the card
    allows. The half that *is* printed as an Effect, continuing the flight
    afterwards, is written out.
    """
    if c.strike():
        c.hit()
        c.prone()
    c.move(c.speed_of())


@power(
    "m3435a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3435a2(c: Cast) -> None:
    """Harder to catch on the way past. `opportunity` is a key the attack
    context carries, and `query.defence` is handed that same context."""
    c.bonus(
        AC, 4, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


def _helpless_in_reach(world: World, eid: int) -> bool:
    from combat_engine.engine.conditions import rules
    from combat_engine.engine.query import active

    return any(
        distance_between(world, eid, foe) <= 1
        and any(rules(cond).helpless for cond in active(world, foe))
        for foe in enemies(world, eid)
    )


@power(
    "m3435a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    requires=_helpless_in_reach,
    requires_text="there must be a helpless creature within reach",
    dropped=("c.coup_de_grace(basic=True)",),
)
def m3435a3(c: Cast) -> None:
    """It settles on something that cannot fight back and feeds.

    `c.coup_de_grace` refuses a row that declares no attack line of its own --
    Camille's call on #250 was to disallow one rather than invent damage for it
    -- and this card prints none, so the swing has to be the creature's own
    basic attack. The automatic critical that a coup de grace *is* cannot be
    had that way; maximised damage is the nearest thing the vocabulary offers
    and is written instead, which is why the clause is marked.
    """
    victim = c.target
    if victim is None:
        return
    c.cure(Condition.INSUBSTANTIAL, on=c.me)
    c.mode("fly", 0, on=c.me, until=When.EONT)
    c.maximise(on=c.me, until=When.EOT)
    c.basic(on=victim)
    hp = c.world.get(victim, Health)
    if hp is not None and hp.hp <= 0:
        mine = c.world.get(c.me, Health)
        if mine is not None:
            c.heal(mine.max_hp, on=c.me)


# --------------------------------------------------------------------------
# m4231
# --------------------------------------------------------------------------


@power(
    "m4231a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 1),
)
def m4231a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m4231a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_while_bloodied,
    requires_text="usable only while bloodied",
)
def m4231a1(c: Cast) -> None:
    """Two swings of the row that prints the claw, not two basic attacks: the
    creature has one at-will and it is the one named."""
    for _ in range(2):
        c.use_power("m4231a0")


@power(
    "m4231a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4231a2(c: Cast) -> None:
    _advantage_rider(c, "1d6")


@power(
    "m4231a3",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_while_bloodied,
    requires_text="usable only while bloodied",
)
def m4231a3(c: Cast) -> None:
    c.shift(2)


@power(
    "m4231a4",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4231a4(c: Cast) -> None:
    """Two more against anybody its pack has surrounded.

    The crowd is counted at the moment the blow lands rather than when the
    trait arms, and it reads the *reach* of the row that struck, because the
    printed line is about its melee attacks only.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        row = get(ev.power)
        if row is None or row.reach.kind != "melee":
            return
        if _crowd_around(c, ev.target, least=2):
            c.damage(0, 2, on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


# --------------------------------------------------------------------------
# m4591
# --------------------------------------------------------------------------


@power(
    "m4591a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 3),
)
def m4591a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m4591a1",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4591a1(c: Cast) -> None:
    """It drags what it is holding along behind it.

    The pull is taken *after* the move and aimed at the creature being held,
    which is what "with it" means: pulling first would drag the victim to
    where the beast already was. The waiver is laid on both of them, because
    the printed line exempts both.
    """
    held = c.grabbing()
    half = max(1, c.speed_of() // 2)
    for victim in held:
        c.no_provoke(on=victim, until=When.EOT)
    c.no_provoke(on=c.me, until=When.EOT)
    c.move(half)
    for victim in held:
        c.pull(half, on=victim)


# --------------------------------------------------------------------------
# m4602
# --------------------------------------------------------------------------


@power(
    "m4602a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4602a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and the toll taken as a turn closes.

    Who is inside is asked when the turn ends rather than kept as a list: the
    aura travels with the swarm and a stored membership would be stale the
    moment either of them moved.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def toll(ev: TurnEnd) -> None:
        if ev.actor == me or ev.ghost:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) > 1:
            return
        c.flat(4, on=ev.actor)
        c.slide(1, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m4602a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:acrobatics",),
)
def m4602a1(c: Cast) -> None:
    """What a swarm is: a space anybody may walk into, and nothing to shove.

    "It can squeeze through any opening large enough for one of the creatures
    it comprises" is the narrative clause, and squeezing through a gap is an
    acrobatics circumstance. A board has no openings to squeeze through --
    there is nothing between two squares -- so the sentence narrows a
    circumstance that never comes up rather than naming a gap, and no
    acrobatics check is ever rolled in a fight for it to modify. The two
    halves that do land are the shared space and the immunity to being shoved.

    A very large `c.resist_forced` rather than a flat refusal: the printed line
    is about melee and ranged attacks only, and `_by_hand` is the gate that
    leaves a close burst's shove standing.
    """
    c.shares_space(on=c.me, until=When.ENCOUNTER, difficult=True)
    c.resist_forced(
        99, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _by_hand(str(ctx.get("power") or "")),
    )


@power(
    "m4602a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 3),
    dropped=("query.moved_this_turn(world, eid)",),
)
def m4602a2(c: Cast) -> None:
    """The larger expression replaces the printed one rather than adding to it.

    The count of squares walked this turn has to be kept by hand -- nothing
    records it -- and the tally is armed the first time this row is used, so
    the very first swing of a fight reads zero however far the swarm came. That
    is the clause marked: a creature's movement for the turn is not a question
    the engine can be asked.
    """
    moved = _travelled_this_turn(c, "walk", "shift", "run")
    if c.strike():
        if moved >= 2:
            c.damage("1d10", 8)
        else:
            c.hit()
    c.shift(1)


# --------------------------------------------------------------------------
# m4612
# --------------------------------------------------------------------------


@power(
    "m4612a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4612a0(c: Cast) -> None:
    """A dying beast gets one last swing.

    `team()` is compared directly rather than asking `c.allies()`:
    `query.allies` filters out the dead and the creature this answers for has
    just dropped, so the membership test would be false every single time.
    """
    me = c.me
    mine = team(c.world, me)

    def last_bite(ev: Dropped) -> None:
        if ev.actor == me or team(c.world, ev.actor) is not mine:
            return
        if not c.is_kind("beast", on=ev.actor):
            return
        if distance_between(c.world, me, ev.actor) > 3:
            return
        c.basic(who=ev.actor)

    c.aura(3, until=When.ENCOUNTER)
    c.watch(Dropped, last_bite, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m4612a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 2),
)
def m4612a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4612a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 2),
)
def m4612a2(c: Cast) -> None:
    if c.strike():
        c.hit()


def _beast_within(radius: int):  # noqa: ANN202
    """"One allied beast within N squares" as an entry gate, not a body check.

    `Target` has no field for "an ally of a particular kind", and a row that
    looks and returns is a standard action the policy spends on nothing --
    which is also what makes the difference between the audit reporting a row
    *silent* and reporting that the board could not meet its Requirement.
    """

    def gate(world: World, eid: int) -> bool:
        # `kinds_of` is a `Cast` method and a gate is handed `(world, eid)`,
        # so one is built for the question -- the same thing three item rows
        # and a wizard row do for the same reason.
        asking = Cast(world=world, me=eid, ref="")
        return any(
            mate != eid
            and asking.is_kind("beast", on=mate)
            and distance_between(world, eid, mate) <= radius
            for mate in allies(world, eid)
        )

    return gate


def _my_beast(c: Cast, *, within: int, of: int | None = None) -> int | None:
    anchor = c.me if of is None else of
    return next(
        (
            mate
            for mate in c.allies()
            if mate != c.me
            and c.is_kind("beast", on=mate)
            and distance_between(c.world, anchor, mate) <= within
        ),
        None,
    )


@power(
    "m4612a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_beast_within(10),
    requires_text="an allied beast must be within 10 squares",
)
def m4612a3(c: Cast) -> None:
    """"In either order" is written as step-then-bite: the step is what puts
    the beast in reach, and the other order only matters when it already is."""
    beast = _my_beast(c, within=10)
    if beast is None:
        return
    c.shift(max(1, c.speed_of(beast) // 2), who=beast)
    c.basic(who=beast)


_M4612_FOE_MOVES = "an enemy within 5 squares of it moves"


@power(
    "m4612a4",
    level=1,
    usage=Usage.RECHARGE,
    recharge=4,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4612_FOE_MOVES,
    on=Trigger(MoveStart, _foe_moved_within(5), _M4612_FOE_MOVES),
)
def m4612a4(c: Cast) -> None:
    """The beast is chosen for its distance from the *enemy*, not from the
    leader -- which is the printed sentence and a different creature most of
    the time."""
    c.shift(max(1, c.speed_of() // 2))
    foe = getattr(c.trigger, "actor", None)
    beast = _my_beast(c, within=5, of=foe) if foe is not None else None
    if beast is not None:
        c.shift(max(1, c.speed_of(beast) // 2), who=beast)


_M4612_MISSED = "it is missed by an attack"


@power(
    "m4612a5",
    level=1,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4612_MISSED,
    on=Trigger(Miss, targets_me, _M4612_MISSED),
)
def m4612a5(c: Cast) -> None:
    """Any attack, not only a melee one -- so no `by_melee` here."""
    c.shift(1)


# --------------------------------------------------------------------------
# m4688
# --------------------------------------------------------------------------


@power(
    "m4688a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d4", 3),
)
def m4688a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4688a1",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d4", 3, kind=LIMITED),
)
def m4688a1(c: Cast) -> None:
    """"Before or after attacking" is taken after: the target is chosen before
    the body runs, so a step beforehand can only walk out of its own reach."""
    if c.strike():
        c.hit()
    c.shift(4)


_M4688_ROLLED = "it makes an attack roll"


@power(
    "m4688a2",
    level=1,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4688_ROLLED,
    on=Trigger(AttackRolled, _i_rolled_one, _M4688_ROLLED),
)
def m4688a2(c: Cast) -> None:
    """"It must use the second roll, even if it is lower" is `keep="new"`."""
    c.reroll_attack(keep="new")


@power(
    "m4688a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4688a3(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


# --------------------------------------------------------------------------
# m4692
# --------------------------------------------------------------------------


@power(
    "m4692a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 4),
)
def m4692a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4692a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=4),
    damage=Damage("1d6", 5),
)
def m4692a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m4692a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=4),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC),
)
def m4692a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


@power(
    "m4692a3",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.HEALING, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=4),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4692a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


# --------------------------------------------------------------------------
# m4743
# --------------------------------------------------------------------------


@power(
    "m4743a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
)
def m4743a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4743a1",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m4743a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4743a2",
    level=1,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_beside_kind("m4741"),
    requires_text="it must be adjacent to an m4741",
)
def m4743a2(c: Cast) -> None:
    c.heal(7, on=c.me)


_M4743_MISSED = "it is missed by a melee attack"


@power(
    "m4743a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4743_MISSED,
    on=Trigger(Miss, both(targets_me, by_melee), _M4743_MISSED),
)
def m4743a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m5149
# --------------------------------------------------------------------------


@power(
    "m5149a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 5),
)
def m5149a0(c: Cast) -> None:
    """The larger expression replaces the printed one; `c.result.advantage` is
    read off the roll because the board has already forgotten."""
    result = c.strike()
    if result:
        if result.advantage:
            c.damage("2d6", 5)
        else:
            c.hit()
    c.shift(1)


@power(
    "m5149a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 5),
)
def m5149a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5149a2",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5149a2(c: Cast) -> None:
    c.shift(3)


_M5149_MISSED = "it is missed by a melee attack"


@power(
    "m5149a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5149_MISSED,
    on=Trigger(Miss, both(targets_me, by_melee), _M5149_MISSED),
)
def m5149a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m5282
# --------------------------------------------------------------------------


@power(
    "m5282a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5282a0(c: Cast) -> None:
    """Who may ride it, which is settled before a fight and never during one.

    The mount relation is laid by whoever climbs on; nothing in a fight ever
    asks whether a creature was *eligible* to. So the row is complete and
    inert rather than unwritten -- `out_of_combat` is the field that says
    which, and the note is there so a reader of the log can see the rule.
    """
    c.note(f"{c.ref}: a Small creature can ride it")


@power(
    "m5282a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5282a1(c: Cast) -> None:
    """A longer run, and no opening bought by taking it.

    Both halves are modifiers `actions.perform` already reads: `run` is added
    to the printed +2, and any negative `run_exposed` turns off the combat
    advantage a run ordinarily hands over. The rider's half of that sentence
    is the mount's in practice -- the mount is the creature running, and the
    rider is carried -- so one modifier says both.
    """
    c.bonus("run", 2, on=c.me, until=When.ENCOUNTER)
    c.penalty("run_exposed", 1, on=c.me, until=When.ENCOUNTER)


@power(
    "m5282a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3),
)
def m5282a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5320
# --------------------------------------------------------------------------

#: The label every half of the latch is hung off, so one sweep takes the set.
_LATCH = "m5320 latch"


def _is_latched(world: World, eid: int) -> bool:
    """Is the creature attached to something?

    There is no relation for this and it is not a grab -- the victim is not
    held, the *creature* is the one carried along, which is the opposite of
    what `c.grab` models -- so the attachment is a labelled effect on the
    creature itself and every half of the printed line reads it back here.
    """
    return any(effect.label == _LATCH for effect in world.effects.of(eid))


@power(
    "m5320a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5320a0(c: Cast) -> None:
    """Harder to shake off once it is on. Asked at the moment a defence is
    read, because whether it is attached changes mid-fight."""
    me = c.me
    c.bonus(
        AC, 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: _is_latched(c.world, me),
    )


@power(
    "m5320a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5320a1(c: Cast) -> None:
    """The drop on anything its pack has surrounded. `c.gains_advantage` lays
    the modifier on the attacker, which is the only end this sentence has: the
    set of qualifying creatures is whatever happens to be crowded at the
    moment of the swing."""
    me = c.me

    def crowded(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and _crowd_around(c, victim, least=2)

    c.gains_advantage(crowded, until=When.ENCOUNTER, on=me)


@power(
    "m5320a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 5),
)
def m5320a2(c: Cast) -> None:
    """It attaches, and from then on it goes wherever the victim goes.

    Not a grab: the victim moves freely and the *creature* is the one dragged
    along, which is the opposite of what `c.grab` models. So the attachment is
    a labelled effect on the creature and a watch on the victim's steps, and
    "no more than one creature at a time" is the old pair swept before the new
    one is laid.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    me = c.me
    for effect in list(c.world.effects.of(me)):
        if effect.label in (_LATCH, f"{_LATCH} ride"):
            c.world.effects.end(effect, "it let go")

    def ride(ev: Moved) -> None:
        if ev.actor != victim:
            return
        taken = squares(c.world, victim)
        for sq in sorted(spread(taken, 1) - taken):
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
                # Carried rather than walked: the printed line says the move
                # provokes nothing, and a shift is still limited by distance
                # while the victim may have gone right across the board.
                c.teleport(99, who=me, to=sq)
                return

    c.effect(_LATCH, until=When.ENCOUNTER, on=me)
    c.watch(Moved, ride, until=When.ENCOUNTER, on=me, label=f"{_LATCH} ride")


@power(
    "m5320a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d8", 3),
    requires=_is_latched,
    requires_text="it must be latched onto a creature",
)
def m5320a3(c: Cast) -> None:
    """It lets go as it bites, so the attachment and its watch both end here."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)
    for effect in list(c.world.effects.of(c.me)):
        if effect.label in (_LATCH, f"{_LATCH} ride"):
            c.world.effects.end(effect, "it detached")
    c.shift(2)


@power(
    "m5320a4",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5320a4(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.EOT)
    c.jump(4)


# --------------------------------------------------------------------------
# m5426
# --------------------------------------------------------------------------


@power(
    "m5426a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignore_cover(concealment_only=True)",),
)
def m5426a0(c: Cast) -> None:
    """It sees past concealment and *only* past concealment.

    `resolve.situational` takes the larger of cover and concealment and asks
    one waiver about the pair, so `c.ignore_cover` cannot be narrowed to the
    half this card prints. Laying the broad one would let the creature shoot
    through a wall's cover for free, which is a bigger rule than the card has
    and the sort of over-grant nothing ever catches again.
    """


@power(
    "m5426a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 2),
)
def m5426a1(c: Cast) -> None:
    result = c.strike()
    if result:
        if result.advantage:
            c.damage("3d6", 4)
        else:
            c.hit()
    c.shift(1)


_M5426_FOE_NEAR = "an enemy ends its turn within 2 squares of it"


@power(
    "m5426a2",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("3d6", 4, kind=LIMITED),
    trigger=_M5426_FOE_NEAR,
    on=Trigger(TurnEnd, _foe_ended_within(2), _M5426_FOE_NEAR),
)
def m5426a2(c: Cast) -> None:
    """The step comes first, because at 2 squares the triggering enemy is out
    of reach and "before or after the attack" has only one useful order."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.distance(foe) > 1:
        for sq in sorted(squares(c.world, foe)):
            if c.shift(1, to=sq):
                break
        else:
            c.shift(1)
    if c.strike(on=foe):
        c.hit(on=foe)


# --------------------------------------------------------------------------
# m5444
# --------------------------------------------------------------------------


@power(
    "m5444a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3),
    dropped=("query.moved_this_turn(world, eid)",),
)
def m5444a0(c: Cast) -> None:
    """Two more for every square of footwork this turn.

    The count has to be kept by hand -- nothing records a creature's movement
    for the turn -- and the tally is armed the first time this row is used, so
    the first swing of a fight reads zero however much the creature danced.
    That is the clause marked.
    """
    steps = _travelled_this_turn(c, "shift")
    if c.strike():
        c.hit()
        if steps:
            c.damage(0, 2 * steps)


@power(
    "m5444a1",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5444a1(c: Cast) -> None:
    c.shift(3)


@power(
    "m5444a2",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5444a2(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m5533
# --------------------------------------------------------------------------


@power(
    "m5533a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5533a0(c: Cast) -> None:
    _advantage_rider(c, "1d6", dtype=DamageType.LIGHTNING)


@power(
    "m5533a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:dungeoneering",),
)
def m5533a1(c: Cast) -> None:
    """Burrowing at full speed is the half that lands; stone is the other one.

    A board has no rock to tunnel through -- every square is either passable or
    it is not, and nothing distinguishes earth from granite -- so "through
    solid stone" narrows a circumstance that never arises rather than naming a
    gap. Knowing one stone from another is a dungeoneering matter and no
    dungeoneering check is rolled on a board, so the clause has nowhere to go.
    Shifting while burrowing is already true: nothing forbids it.
    """
    c.mode("burrow", c.speed_of(), on=c.me, until=When.ENCOUNTER)


@power(
    "m5533a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
)
def m5533a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m5533a3",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(10),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=4),
    requires=_bloodied_within(10),
    requires_text="there must be a bloodied creature within reach",
)
def m5533a3(c: Cast) -> None:
    """No damage line at all -- the whole Hit is the exchange of places.

    "The m5533 or one of its allies" is written as itself when it has nowhere
    better to be and as the nearest ally otherwise; `c.swap` takes whichever.
    """
    victim = c.target
    if victim is None or not c.strike():
        return
    mate = next(
        (a for a in c.allies() if a != c.me and c.distance(a) <= 10),
        None,
    )
    c.swap(victim, who=mate if mate is not None else c.me)


_M5533_HURT = "it takes damage"


@power(
    "m5533a4",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5533_HURT,
    on=Trigger(DamageApplied, _damaged_me, _M5533_HURT),
)
def m5533a4(c: Cast) -> None:
    c.shift(7)


# --------------------------------------------------------------------------
# m5584
# --------------------------------------------------------------------------


@power(
    "m5584a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5584a0(c: Cast) -> None:
    """Half from a sword or an arrow, all of it from force.

    Not `c.insubstantial`: that halves *everything*, and this card exempts
    close and area attacks as well as force. Written as a reduction taken in
    the BEFORE window of `DamageRolled`, where the blow has a number and has
    not yet reached hit points, and the reach is read off the row that rolled
    it. The force clause is a plain early return rather than a separate
    vulnerability, because the printed sentence is "full damage", not "extra".
    """
    me = c.me

    def soften(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0:
            return
        if ev.dtype is DamageType.FORCE or DamageType.FORCE in (ev.dtypes or ()):
            return
        if not _by_hand(ev.detail):
            return
        c.reduce(ev.amount - ev.amount // 2, ev)

    c.watch(
        DamageRolled, soften, until=When.ENCOUNTER, on=me,
        window=Window.BEFORE, label=f"{c.ref} diffuse",
    )


@power(
    "m5584a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5584a1(c: Cast) -> None:
    """Its own kind walk on it as if it were ground.

    The terrain the sentence is about is the creature's own substance, and a
    board has none of it: there is no square made of this and nothing to grant
    footing on. So the row is complete and inert rather than unwritten.
    """
    c.note(f"{c.ref}: its own kind can walk on it")


@power(
    "m5584a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 7),
)
def m5584a2(c: Cast) -> None:
    """The extra dice are added rather than swapped in: the card prints them as
    "plus an additional 2d6", which is a rider on the printed line."""
    if not c.strike():
        return
    c.hit()
    if c.is_(Condition.SLOWED) or c.is_(Condition.IMMOBILIZED):
        c.damage("2d6")


@power(
    "m5584a3",
    level=1,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d4", 10, kind=LIMITED, half_on_miss=True),
)
def m5584a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m5584a4",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5584a4(c: Cast) -> None:
    """It rolls through whoever is in the way, and the first one pays.

    "The first time during this shift" is the loop breaking after one payout
    rather than a per-round guard: the sentence is about this one move.
    """
    caught = _adjacent_foes(c, 3)
    for foe in caught:
        for sq in sorted(squares(c.world, foe)):
            if c.shift(3, to=sq, share=True):
                c.flat(5, on=foe)
                c.slowed(until=When.EONT, on=foe)
                return
    c.shift(3)


# --------------------------------------------------------------------------
# m5846
# --------------------------------------------------------------------------


@power(
    "m5846a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5846a0(c: Cast) -> None:
    """The drop on anything one of its friends is already busy with."""
    me = c.me

    def crowded(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and _crowd_around(c, victim, least=1)

    c.gains_advantage(crowded, until=When.ENCOUNTER, on=me)


@power(
    "m5846a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d4", 4),
)
def m5846a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5846a2",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_while_bloodied,
    requires_text="it must be bloodied",
)
def m5846a2(c: Cast) -> None:
    """A desperate swing: its own at-will, with both halves of the gamble.

    `c.use_power` leaves the borrowed row's last roll in `c.result`, which is
    what answers "if the attack hits" without the body having to roll twice.
    """
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is None:
        return
    c.use_power("m5846a1", on=foe)
    if c.landed:
        c.damage("2d6", on=foe)
    else:
        c.damage("1d6", on=c.me)


@power(
    "m5846a3",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5846a3(c: Cast) -> None:
    """`total=False` is the printed "partial concealment" and the default."""
    c.shift(3)
    c.conceal(on=c.me, until=When.EONT)


_M5846_HIT = "an enemy hits it"


@power(
    "m5846a4",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5846_HIT,
    on=Trigger(Hit, targets_me, _M5846_HIT),
)
def m5846a4(c: Cast) -> None:
    """An interrupt resolves in the BEFORE window, so the roll it rewrites is
    still the one about to be read. "Use the new result" is `keep="new"`."""
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m6030
# --------------------------------------------------------------------------


@power(
    "m6030a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m6030a0(c: Cast) -> None:
    """An aura 2 for the board to draw, and the rule hung off `SurgeSpent`.

    Who is inside is asked when the surge is spent rather than kept as a list:
    the aura travels with the creature and a stored membership would be stale
    the moment either of them moved.
    """
    me = c.me
    c.aura(2, until=When.ENCOUNTER)

    def sicken(ev: SurgeSpent) -> None:
        if ev.actor == me or team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) <= 2:
            c.weakened(until=When.EOTNT, on=ev.actor)

    c.watch(SurgeSpent, sicken, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m6030a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6030a1(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m6030a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m6030a2(c: Cast) -> None:
    _heals_its_killer(c, 3)


@power(
    "m6030a3",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6030a3(c: Cast) -> None:
    """Said twice, once per word the card names -- the waiver is per label and
    "mud or shallow water" is two sorts of ground, not one."""
    c.ignores_difficult("mud", on=c.me, until=When.ENCOUNTER)
    c.ignores_difficult("water", on=c.me, until=When.ENCOUNTER)


@power(
    "m6030a4",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 4),
)
def m6030a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6030a5",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
)
def m6030a5(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6030a6",
    level=1,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m6030a6(c: Cast) -> None:
    """"Marks on it end" is the effect *and* the relation: either one left
    behind keeps half of the mark alive, and `resolve` reads the relation."""
    _shed(c, Relation.MARKED_BY)
    c.no_provoke(on=c.me, until=When.EOT)
    c.jump(3)
    result = c.strike()
    if not result:
        return
    if result.advantage:
        c.damage("3d6", 6)
    else:
        c.hit()
    victim = c.target
    if victim is not None:
        me = c.me
        c.penalty(
            "attack", 2, on=victim, until=When.EONT,
            when=lambda ctx: ctx.get("target") == me,
        )


# --------------------------------------------------------------------------
# m6488
# --------------------------------------------------------------------------


@power(
    "m6488a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6488a0(c: Cast) -> None:
    _squeezes_freely(c)


@power(
    "m6488a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 4),
)
def m6488a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6488a2",
    level=1,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6488a2(c: Cast) -> None:
    _shift_through(c, max(1, c.speed_of() // 2))


# --------------------------------------------------------------------------
# m6553
# --------------------------------------------------------------------------


@power(
    "m6553a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d4", 4),
)
def m6553a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6553a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6553a1(c: Cast) -> None:
    """A darting pass, guarded while it lasts.

    The +5 is four bonuses rather than one: "all defences" is not a key, and a
    single modifier on one of them would be a quarter of the printed line. All
    four are ended by hand when the pass is over, because the window is the
    movement and nothing shorter than a turn expresses that.
    """
    held = [
        c.bonus(d, 5, on=c.me, until=When.EOT) for d in (AC, FORT, REF, WILL)
    ]
    try:
        half = max(1, c.speed_of() // 2)
        step = max(1, half // 2)
        c.shift(step)
        foe = next(iter(_adjacent_foes(c)), None)
        if foe is not None:
            c.use_power("m6553a0", on=foe)
        if half - step > 0:
            c.shift(half - step)
    finally:
        for guard in held:
            if guard is not None:
                c.world.effects.end(guard, "the pass is over")


@power(
    "m6553a2",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=4),
)
def m6553a2(c: Cast) -> None:
    """No damage line at all -- the whole Hit is the forced walk and the daze.

    The Sustain repeats the Hit rather than merely holding it, so the payout is
    hung on `c.on_sustain`; a `When.SUSTAIN` duration alone would keep the
    effect standing and pay nothing, which is the half of a sustain that goes
    missing.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    half = max(1, c.speed_of(victim) // 2)
    c.move(half, who=victim)
    c.dazed(until=When.EONT, on=victim)
    if not c.first:
        return
    anchor = c.effect(f"{c.ref} charm", until=When.SUSTAIN, on=c.me, sustain=STANDARD)

    def again() -> None:
        for foe in c.enemies():
            if c.distance(foe) <= 3:
                c.move(max(1, c.speed_of(foe) // 2), who=foe)
                c.dazed(until=When.EONT, on=foe)

    c.on_sustain(anchor, again)


@power(
    "m6553a3",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m6553a3(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


# --------------------------------------------------------------------------
# m6621
# --------------------------------------------------------------------------


@power(
    "m6621a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6621a0(c: Cast) -> None:
    """It picks off whatever has nobody else beside it.

    "No **other** creatures adjacent to it" counts the demon out: it is
    standing next to its victim itself whenever this is a melee hit, so
    counting every neighbour would make the line false in the one case it is
    written for.
    """
    me, ref = c.me, c.ref

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        alone = not [
            other
            for other in creatures(c.world)
            if other not in (me, ev.target)
            and distance_between(c.world, other, ev.target) <= 1
        ]
        if alone:
            c.damage("1d6", on=ev.target, detail=ref)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m6621a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.drags_grabbed()",),
)
def m6621a1(c: Cast) -> None:
    """It can haul what it is holding along with any move it makes.

    There is no standing form of that. One row's body can pull a held creature
    after it -- `m4591a1` does -- but this is a *trait*: it has to apply to
    every move the creature makes, including ones the engine chose, and
    nothing can be hung off a walk to make the grabbed creature follow.
    """


@power(
    "m6621a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 4),
    narrative=("skill:endurance",),
)
def m6621a2(c: Cast) -> None:
    """The bite is exact; the contagion is the clause with no combat meaning.

    The saving throw is made "at the end of the encounter" and the stage track
    that follows is rolled with endurance checks over days. Neither happens on
    a board, so there is nothing in a fight for the clause to change and no
    mechanism worth building for it.
    """
    if c.strike():
        c.hit()


@power(
    "m6621a3",
    level=1,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d8", 4, kind=LIMITED),
    requires=_not_grabbing,
    requires_text="it must have no creature grabbed",
)
def m6621a3(c: Cast) -> None:
    """A pounce: the swing, then the rest of the run.

    "Recharge when it hits with bite" is laid on top of the printed 6+ rather
    than instead of it -- the number stays in the header because that is what
    `actions.recharge` rolls and what the card shows, and the two only ever
    agree to make the row available sooner.
    """
    if c.strike():
        c.hit()
        c.grab()
    c.move(c.speed_of())
    if not c.first:
        return
    me, ref = c.me, c.ref

    def bit(ev: Hit) -> None:
        if ev.attacker == me and ev.power == "m6621a2":
            c.restore_use(ref, on=me)

    c.watch(Hit, bit, until=When.ENCOUNTER, on=me, label=f"{ref} recharge")


@power(
    "m6621a4",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=4),
    requires=_not_grabbing,
    requires_text="it must have no creature grabbed",
)
def m6621a4(c: Cast) -> None:
    """No damage line at all -- the whole Hit is the shove."""
    if c.strike():
        c.slide(1)


_M6621_ELEMENT = "it takes acid, cold, fire, lightning, or thunder damage"


@power(
    "m6621a5",
    level=1,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6621_ELEMENT,
    on=Trigger(DamageApplied, _elemental_hurt, _M6621_ELEMENT),
)
def m6621a5(c: Cast) -> None:
    """The resistance is for *the triggering type*, read off the event rather
    than chosen: five types can set this off and only one of them did."""
    dtype = getattr(c.trigger, "dtype", None)
    if dtype in _ELEMENTS:
        c.resist(5, dtype, on=c.me, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m6654
# --------------------------------------------------------------------------


@power(
    "m6654a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m6654a0(c: Cast) -> None:
    """An aura 1 for the board, and the burn taken as a turn closes.

    "Can take no actions until the start of its next turn" is written as
    stunned: it is the one condition whose rule is exactly that. Dazed would
    be a *weaker* line -- one action rather than none -- and there is nothing
    narrower than stunned in the vocabulary.
    """
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def scorch(ev: TurnEnd) -> None:
        if ev.actor == me or ev.ghost:
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) > 1:
            return
        c.flat(3, dtype=DamageType.FIRE, on=ev.actor)
        c.condition(Condition.STUNNED, until=When.SOTNT, on=ev.actor)

    c.watch(TurnEnd, scorch, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m6654a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6654a1(c: Cast) -> None:
    """It walks through whoever is in the way. `c.shares_space` is the standing
    permission `movement` reads; without it an occupied square is refused
    outright and the printed line changes nothing."""
    c.shares_space(on=c.me, until=When.ENCOUNTER, difficult=False)


@power(
    "m6654a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE),
)
def m6654a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6654a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE),
)
def m6654a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m6654a4",
    level=1,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_while_bloodied,
    requires_text="it must be bloodied",
)
def m6654a4(c: Cast) -> None:
    """Both of its at-wills in one action, each at its own printed reach."""
    c.use_power("m6654a2")
    c.use_power("m6654a3")


_M6654_BURNED = "it takes fire damage"


@power(
    "m6654a5",
    level=1,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger=_M6654_BURNED,
    on=Trigger(DamageApplied, _burned_me, _M6654_BURNED),
)
def m6654a5(c: Cast) -> None:
    """It flares and bolts, scalding whoever it passes through.

    One creature per space entered, and "for the first time" is the set of
    those already paid rather than a per-round guard: the sentence is about
    this one movement.
    """
    half = max(1, c.speed_of() // 2)
    burned: set[int] = set()
    for foe in _adjacent_foes(c, half):
        if foe in burned:
            continue
        for sq in sorted(squares(c.world, foe)):
            if c.shift(half, to=sq, share=True):
                burned.add(foe)
                c.flat(3, dtype=DamageType.FIRE, on=foe)
                break
    if not burned:
        c.shift(half)


# --------------------------------------------------------------------------
# m6661
# --------------------------------------------------------------------------


@power(
    "m6661a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6661a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m6661a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("2d4", 4),
)
def m6661a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6661a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6661a2(c: Cast) -> None:
    """The burn is hung on the borrowed row's own result: `c.use_power` leaves
    its last roll in `c.result`, which is what "if the attack hits" reads."""
    c.shift(max(1, c.speed_of() // 2))
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is None:
        return
    c.use_power("m6661a1", on=foe)
    if c.landed:
        c.ongoing(5, on=foe)
