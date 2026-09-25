"""Warlord, level 6: the later books' utilities. Nothing here attacks.

Four stances, and every one of them holds its effects the way
`fighter/level_5.py` settled: the mods and the watchers run on
`When.ENCOUNTER` and the stance's own `on_end` takes them off. A second
`When.STANCE` effect on the same creature confuses `Effects.stance_of`,
which is what decides that taking a stance ends the one before it.

Three rows name the warlord's own class heal. That row is `p1590` and
`PowerUsed` is what announces it -- emitted before the body runs, so a
rider hung on it is in place by the time the healing lands.

`p10126` is declared on `DamageRolled` rather than on the printed hit.
"The attack hits you instead" has to happen while the number is still in
flight: by the time a `Hit` is announced there is nothing left to move but
the damage, which is what `c.absorb` moves. `paladin/level_2.py` records
the same reading.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MELEE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    PERSONAL,
    RANGED,
    REF,
    SELF,
    STANDARD,
    AttackDeclared,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Cover,
    Dropped,
    Effect,
    Event,
    Gear,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    MoveEnd,
    Powers,
    PowerUsed,
    Ranged,
    Relation,
    Square,
    Target,
    Trigger,
    When,
    World,
    by_melee,
    power,
)
from combat_engine.engine.events import DamageRolled
from combat_engine.engine.grid import neighbours
from combat_engine.engine.query import (
    adjacent,
    cover_between,
    distance_between,
    squares,
    team,
)

MARTIAL = [Keyword.MARTIAL]

#: The warlord's own class heal, which three rows below hang riders on.
_THE_WORD = "p1590"

_ADJACENT_ALLY_STRUCK = "an attack hits an adjacent ally"
_I_HIT_IN_MELEE_OR_AT_RANGE = "you hit an enemy with a martial melee or ranged attack"
_ALLY_SWINGS = "an ally within 10 squares makes a basic attack or a charge"
_I_USE_THE_WORD = f"you use {_THE_WORD} on an ally"


def _friends(c: Cast, radius: int) -> list[int]:
    """"An ally within N squares" -- never the warlord itself."""
    return sorted(a for a in c.within(radius, side="ally") if a != c.me)


def _stand(c: Cast, who: int) -> bool:
    """Standing up is ending whatever holds the creature down; prone runs on
    the encounter clock and nothing else takes it off."""
    floored = [e for e in c.world.effects.of(who) if Condition.PRONE in e.conditions]
    for effect in floored:
        c.world.effects.end(effect, f"{c.ref}: stands up")
    return bool(floored)


def _shield(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.shield)


def _polearm(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    weapon = gear.main if gear else None
    return weapon is not None and weapon.group in ("polearm", "spear")


def _adjacent_ally_struck(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "target", None)
    if who is None or who == me or getattr(ev, "amount", 0) <= 0:
        return False
    return team(world, who) is team(world, me) and adjacent(world, me, who)


def _i_hit_with_a_weapon(world: World, me: int, ev: Event) -> bool:
    """"You hit an enemy with a martial melee or ranged attack."

    The keyword is read off the row the `Hit` names rather than guessed from
    the class: a warlord swinging something it borrowed is not martial.
    """
    from combat_engine.engine.dsl import get

    if getattr(ev, "attacker", None) != me:
        return False
    victim = getattr(ev, "target", None)
    if victim is None or team(world, victim) is team(world, me):
        return False
    p = get(getattr(ev, "power", ""))
    if p is None or Keyword.MARTIAL not in p.keywords:
        return False
    return p.reach_of(getattr(ev, "branch", 0)).kind in ("melee", "ranged")


def _ally_swings_within(radius: int) -> Callable[[World, int, Event], bool]:
    """An ally's basic attack or charge, within range.

    A bull rush is the third thing the printed line names and the engine has
    no such action, so the sentence is two thirds of itself here.
    """

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "attacker", None)
        if who is None or who == me or team(world, who) is not team(world, me):
            return False
        if distance_between(world, me, who) > radius:
            return False
        if getattr(ev, "charge", False):
            return True
        known = world.get(who, Powers)
        basic = known.basic if known else MELEE
        return getattr(ev, "power", "") in {basic, MELEE, RANGED}

    return check


def _used_the_word(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", None) == me and getattr(ev, "power", "") == _THE_WORD


@power(
    "p10",
    level=6,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10(c: Cast) -> None:
    """"While you are adjacent to an ally" is asked when somebody rolls, so
    it is a gate rather than a snapshot: both ends of the pair move."""
    me = c.me
    stance = c.stance(label=c.ref)
    held: list[Effect] = []

    def beside_anyone(ctx: dict) -> bool:
        return any(c.adjacent(a) for a in c.allies())

    held.append(c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=beside_anyone))
    for friend in c.allies():

        def beside_me(ctx: dict, who: int = friend) -> bool:
            return c.adjacent(who)

        held.append(
            c.bonus("attack", 1, on=friend, until=When.ENCOUNTER, when=beside_me)
        )
    stance.on_end.append(
        lambda: [c.world.effects.end(e, "stance ended") for e in held if e]
    )


@power(
    "p10126",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING, Keyword.MARTIAL],
    trigger=_ADJACENT_ALLY_STRUCK,
    on=Trigger(DamageRolled, when=_adjacent_ally_struck, text=_ADJACENT_ALLY_STRUCK),
)
def p10126(c: Cast) -> None:
    """The places are swapped first, so the warlord is standing where the
    blow was aimed before it takes it -- and the surge is a printed "or", so
    whoever is worse off is offered it first.
    """
    friend = getattr(c.trigger, "target", None) or c.target
    if friend is None:
        return
    c.swap(friend)
    c.absorb()
    pool = sorted({c.me, friend}, key=lambda a: -c.missing(a))
    who = c.choose(pool, "who catches a breath")
    if who is not None and c.may("spend a healing surge", who=who):
        c.surge(on=who)


@power(
    "p10128",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    keywords=MARTIAL,
)
def p10128(c: Cast) -> None:
    """"Cannot be knocked prone" is the condition undone the instant it
    arrives: `Effects.apply` installs everything before it announces, which
    is what makes ending a hold from inside `ConditionApplied` safe --
    `monsters/level_05/brutes.py` records the same arrangement. Cancelling
    the event itself would do nothing, because it is announced after the
    fact.
    """
    who = c.target
    if who is None:
        return
    c.immovable(until=When.EONT, on=who)

    def footing(ev: ConditionApplied) -> None:
        if ev.condition is Condition.PRONE and ev.target == who:
            _stand(c, who)

    c.watch(
        ConditionApplied, footing, until=When.EONT, on=who, label=f"{c.ref} footing"
    )
    if not c.first:
        return

    def upright(ev: PowerUsed) -> None:
        if not _used_the_word(c.world, c.me, ev):
            return
        for friend in ev.targets:
            if c.is_(Condition.PRONE, on=friend) and c.may("get up", who=friend):
                _stand(c, friend)

    c.watch(PowerUsed, upright, until=When.EONT, on=c.me, label=f"{c.ref} rally")


@power(
    "p10930",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p10930(c: Cast) -> None:
    """A printed "or", and only one of the two is ever worth taking: a
    creature on its feet cannot stand up."""
    friend = c.target
    if friend is None:
        return
    if c.is_(Condition.PRONE, on=friend) and c.may("get up", who=friend):
        _stand(c, friend)
    else:
        c.slide(1, on=friend)


def _wall_from(c: Cast, size: int) -> frozenset[Square]:
    """`size` contiguous squares including one the caster occupies.

    There is no wall range in the header vocabulary, so the shape is grown
    here: breadth-first from the caster's own square, which is contiguous by
    construction and satisfies "it must include a square you occupy".
    """
    picked: list[Square] = [c.here]
    frontier: deque[Square] = deque(picked)
    while frontier and len(picked) < size:
        for sq in sorted(neighbours(frontier.popleft())):
            if len(picked) >= size:
                break
            if sq in picked or not c.world.grid.passable(sq):
                continue
            picked.append(sq)
            frontier.append(sq)
    return frozenset(picked)


@power(
    "p10931",
    level=6,
    cls="warlord",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(8),
    target=NO_TARGET,
    keywords=MARTIAL,
)
def p10931(c: Cast) -> None:
    """+1, or +2 while beside somebody: written as a +1 and a gated **+2**,
    because two power bonuses of the same kind do not add -- the larger
    wins, and a +1 plus a gated +1 comes to +1 forever.

    The bonuses outlive the printed duration and are gated on the zone
    instead: `c.bonus` cannot carry a sustain cost, so a `When.SUSTAIN` mod
    lapses after one round however faithfully the wall is kept up.
    """
    wall = c.zone(_wall_from(c, 8), label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    inside = c.world.zones.inside

    for friend in [c.me, *c.allies()]:

        def within(ctx: dict, who: int = friend) -> bool:
            return who in inside.get(wall, ())

        def sheltered(ctx: dict, who: int = friend) -> bool:
            here = inside.get(wall, ())
            return who in here and any(
                other != who and adjacent(c.world, who, other) for other in here
            )

        c.bonus(AC, 1, on=friend, until=When.ENCOUNTER, when=within)
        c.bonus(AC, 2, on=friend, until=When.ENCOUNTER, when=sheltered)


@power(
    "p10932",
    level=6,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING, Keyword.MARTIAL],
)
def p10932(c: Cast) -> None:
    """A surge put back on the sheet, not spent: `c.surge` is the other
    direction and there is no `Cast` door to this one, so the pool is
    written to. The hit points come free of it, which is why the heal is a
    flat surge value rather than `c.surge`.
    """
    friend = c.target
    health = c.world.get(friend, Health) if friend is not None else None
    if health is None:
        return
    health.surges += 1
    c.heal(c.surge_value(of=friend), on=friend)


@power(
    "p10933",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_I_USE_THE_WORD,
    on=Trigger(PowerUsed, when=_used_the_word, text=_I_USE_THE_WORD),
)
def p10933(c: Cast) -> None:
    """"Your Wisdom or Charisma modifier" is the better of the two, as a
    printed "or" between two numbers always is. The targets come off the
    event: a self-targeted row is not re-aimed by the dispatcher.
    """
    for friend in getattr(c.trigger, "targets", ()):
        c.temp_hp(5 + max(c.wis_mod, c.cha_mod), on=friend)


@power(
    "p10934",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(5),
    target=Target("other_ally", 99, everyone=True, label="Each ally in the burst"),
    keywords=MARTIAL,
)
def p10934(c: Cast) -> None:
    friend = c.target
    if friend is not None and c.may("shift", who=friend):
        c.shift(c.int_mod, who=friend)


@power(
    "p11611",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING, Keyword.MARTIAL],
    trigger=_I_HIT_IN_MELEE_OR_AT_RANGE,
    on=Trigger(Hit, when=_i_hit_with_a_weapon, text=_I_HIT_IN_MELEE_OR_AT_RANGE),
)
def p11611(c: Cast) -> None:
    """The warlord's own surge is the whole of what this can say.

    The rider is narrowed to an attack an ally gained **from an action
    point**, and there are no action points in the engine: nothing spends
    one, no event announces one, and a watcher on every ally's hit would
    hand the surge out for ordinary swings, which is a far more generous
    card than the printed one.
    """
    if c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)
    victim = getattr(c.trigger, "target", None)
    c.note(
        f"{c.ref}: until the start of your next turn, an ally hitting {victim} with an "
        "attack gained from an action point could also spend a healing surge -- there "
        "are no action points to read"
    )


@power(
    "p11724",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p11724(c: Cast) -> None:
    """The square is named rather than left to the decider, because the
    printed line names it: somewhere with cover. `Grid.cover` answers that
    for a square the ally is not standing in yet, which `query.cover_between`
    -- which takes two creatures -- cannot.

    The Stealth check is not rolled. Becoming hidden is the outcome the
    board can hold, and `c.hide` only ever hides the caster, so it is
    `c.invisible` with the ally named.
    """
    friend = c.target
    if friend is None:
        return
    watching = [sq for foe in c.enemies() for sq in squares(c.world, foe)]
    room = [
        sq
        for sq in c.world.reachable_squares(friend, max(1, c.speed_of(friend) // 2))
        if any(c.world.grid.cover(eye, sq) is not Cover.NONE for eye in watching)
    ]
    spot = c.choose(sorted(room), "where that ally slips out of sight") if room else None
    if spot is not None:
        c.shift(to=spot, who=friend)
    c.invisible(on=friend, until=When.ENCOUNTER)


@power(
    "p2533",
    level=6,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING, Keyword.MARTIAL, Keyword.STANCE],
)
def p2533(c: Cast) -> None:
    """Both halves are relations, and the second half moves: which enemies
    are beside the warlord changes every time anybody walks, so the set is
    recomputed on `MoveEnd` rather than fixed when the stance was taken.

    `c.grants_advantage` names one beneficiary, your allies or you; neither
    of these is that, so the triples are written out.
    """
    me = c.me
    stance = c.stance(label=c.ref)
    granted: set[tuple[int, int]] = set()

    def offer(source: int, to: int) -> None:
        c.world.relations.set(Relation.GRANTS_CA_TO, source, to)
        granted.add((source, to))

    def withdraw(source: int, to: int) -> None:
        c.world.relations.clear(Relation.GRANTS_CA_TO, source, to, "stance")
        granted.discard((source, to))

    def refresh(ev: Event | None = None) -> None:
        for foe in c.enemies():
            for friend in c.allies():
                beside = adjacent(c.world, me, foe)
                if beside and (foe, friend) not in granted:
                    offer(foe, friend)
                elif not beside and (foe, friend) in granted:
                    withdraw(foe, friend)

    for foe in c.enemies():
        offer(me, foe)
    refresh()
    watching = c.watch(
        MoveEnd, refresh, until=When.ENCOUNTER, on=me, label=f"{c.ref} exposure"
    )

    def rewarded(ev: Event) -> None:
        # Bravura Presence. `chargen` names no such build, so this is inert
        # until one exists.
        who = getattr(ev, "actor", None)
        if not c.build("bravura") or who is None:
            return
        if team(c.world, who) is team(c.world, me) or not adjacent(c.world, me, who):
            return
        c.heal(c.cha_mod, on=me)

    for event in (Bloodied, Dropped):
        watching.subs.append(c.world.bus.on(event, rewarded, owner=me))

    def clean_up() -> None:
        for source, to in list(granted):
            withdraw(source, to)
        c.world.effects.end(watching, "stance ended")

    stance.on_end.append(clean_up)


@power(
    "p4560",
    level=6,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p4560(c: Cast) -> None:
    me = c.me
    stance = c.stance(label=c.ref)

    def steady(swung: Event) -> int | None:
        if getattr(swung, "attacker", None) != me or not by_melee(c.world, me, swung):
            return None
        pool = [a for a in _friends(c, 5) if c.bloodied(a)]
        friend = c.choose(pool, "who is steadied") if pool else None
        if friend is None:
            return None
        c.temp_hp(5 + c.cha_mod, on=friend)
        return friend

    def on_hit(ev: Hit) -> None:
        steady(ev)

    def on_miss(ev: Miss) -> None:
        # Bravura Presence. `chargen` names no such build, so this is inert
        # until one exists.
        if not c.build("bravura") or not c.may("steady them anyway", who=me):
            return
        if steady(ev) is not None:
            c.grants_advantage(on=me, to=ev.target, until=When.EONT)

    watching = c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=f"{c.ref} rally")
    watching.subs.append(c.world.bus.on(Miss, on_miss, owner=me))
    stance.on_end.append(lambda: c.world.effects.end(watching, "stance ended"))


@power(
    "p4561",
    level=6,
    cls="warlord",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p4561(c: Cast) -> None:
    """Not taking the penalty is written as exactly cancelling it, gated on
    the cover being the ordinary sort: `Cover.PARTIAL` is the -2 the line
    excuses and `Cover.SUPERIOR` is the one it leaves in place. Untyped, so
    it stacks with whatever else the ally is carrying -- it is the removal
    of a penalty rather than a bonus of its own.

    "Who can see or hear you" is every ally: hearing is not on the board,
    and a line that says "or hear" is not narrowed by sight.
    """
    seen = sorted(f for f in c.enemies() if c.can_see(f))
    foe = c.choose(seen, "who you call out") if seen else None
    if foe is None:
        return

    def unhindered(ctx: dict) -> bool:
        attacker = ctx.get("attacker")
        if ctx.get("target") != foe or attacker is None:
            return False
        return (
            cover_between(c.world, attacker, foe, ranged=bool(ctx.get("ranged")))
            is Cover.PARTIAL
        )

    for friend in c.allies():
        c.bonus(
            "attack", 2, on=friend, until=When.EONT, kind="untyped", when=unhindered
        )


@power(
    "p4563",
    level=6,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
    requires=_shield,
    requires_text="needs a shield",
)
def p4563(c: Cast) -> None:
    """Who is carrying a shield is fixed; who is standing next to whom is
    not, so only the second half is a gate."""
    me = c.me
    stance = c.stance(label=c.ref)
    shielded = [a for a in c.allies() if _shield(c.world, a)]
    held: list[Effect] = []

    def beside_a_shield(ctx: dict) -> bool:
        return any(c.adjacent(a) for a in shielded)

    for defence in (AC, REF):
        held.append(
            c.bonus(defence, 1, on=me, until=When.ENCOUNTER, when=beside_a_shield)
        )
    for friend in shielded:

        def beside_me(ctx: dict, who: int = friend) -> bool:
            return c.adjacent(who)

        for defence in (AC, REF):
            held.append(
                c.bonus(defence, 1, on=friend, until=When.ENCOUNTER, when=beside_me)
            )
    stance.on_end.append(
        lambda: [c.world.effects.end(e, "stance ended") for e in held if e]
    )


@power(
    "p4564",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING, Keyword.MARTIAL],
)
def p4564(c: Cast) -> None:
    """"You or one ally" is what `ONE_ALLY`'s pool already reads. Both surges
    are one printed permission, so the question is asked once."""
    who = c.target
    if who is None or not c.may("spend two healing surges", who=who):
        return
    c.surge(on=who, bonus=5 + c.cha_mod if c.build("inspiring") else 0)
    c.surge(on=who)


@power(
    "p4565",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=MARTIAL,
    trigger=_ALLY_SWINGS,
    on=Trigger(AttackDeclared, when=_ally_swings_within(10), text=_ALLY_SWINGS),
)
def p4565(c: Cast) -> None:
    """Interrupted before the die, so the bonus is in place for it, and
    `once=True` is spent on `AttackRolled` -- which is after an attack
    modifier has been read and before a damage one would be, so it is right
    here and would be wrong for a damage bonus.
    """
    ally = getattr(c.trigger, "attacker", None) or c.target
    if ally is not None:
        c.bonus("attack", c.int_mod, on=ally, until=When.EOT, once=True)


@power(
    "p6007",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    requires=_polearm,
    requires_text="needs a polearm",
)
def p6007(c: Cast) -> None:
    """The exemption goes on before the walk and comes off at the end of the
    turn, so the four squares are the cheap ones the printed line promises
    and nothing after them is.

    "You can move through an enemy's space" is `c.overrun`, which is a
    different card -- it trips whoever is in the way. The walk is left to
    pick its own route.
    """
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.move(4)


@power(
    "p7386",
    level=6,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("ally", 99, everyone=True, label="You and each bloodied ally"),
    keywords=MARTIAL,
)
def p7386(c: Cast) -> None:
    """Targeting cannot filter on hit points, so "each bloodied ally" is
    asked in the body; the warlord itself is a target either way."""
    who = c.target
    if who is None or (who != c.me and not c.bloodied(who)):
        return
    c.bonus("attack", 3 if c.is_kind("dragonborn", c.me) else 2, on=who, until=When.EONT)
