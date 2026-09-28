"""Psion: the stat block each of these rows is printed beside.

Every one is the second block of a row that puts something on the board or
holds something down, and each carries the same Requirement: the first block
has to still be up. They had no ids until the importer began minting one per
printed block, so each was dropped or folded into its parent.

Three of them print their origin as the **conjuration** -- the burst is
centred on the mote, the reach is measured from the anomaly -- and
`Range.from_` knows no such word. Those take **no target line**: the reach
stays as printed, the victims are gathered round the conjuration in the
body, and `c.strike(from_=)` rolls from the right square. A targetless row
is not `Power.is_attack`, so `usable` never applies the reach gate that
would refuse every creature standing round the mote.

Each of the three prints its augment clauses on its own block, but the
points are spent when the **parent** is used -- targets and forms are
settled before either body runs -- so the spend is read back with
`augment.spent_on`.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.content.powers.augment import spent_on
from combat_engine.content.powers.cards import active
from combat_engine.engine import (
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    FORT,
    INT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    REACTION,
    REF,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Position,
    Ranged,
    Trigger,
    TurnStart,
    When,
    World,
    enemy_target_within,
    power,
    spread,
)
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.query import team

from .level_1 import PSIONIC_FORCE, PSIONIC_IMPLEMENT

PSIONIC_ACID = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.ACID, Keyword.CONJURATION]
PSIONIC_LIGHTNING = [
    Keyword.PSIONIC,
    Keyword.IMPLEMENT,
    Keyword.LIGHTNING,
    Keyword.CONJURATION,
]
PSIONIC_PSYCHIC = [
    Keyword.PSIONIC,
    Keyword.IMPLEMENT,
    Keyword.PSYCHIC,
    Keyword.CONJURATION,
]


def _conjuration(c: Cast, ref: str) -> int | None:
    """The caster's own live conjuration from that row, if it is still there."""
    from combat_engine.engine.components import Conjuration

    for eid, conj in c.world.each(Conjuration):
        if conj.ref == ref and conj.by == c.me:
            return eid
    return None


def _standing(ref: str) -> Callable[[World, int], bool]:
    """"Requirement: the <ref> power must be active", where what the row left
    behind is a conjuration rather than a hold on its caster."""

    def check(world: World, eid: int) -> bool:
        from combat_engine.engine.components import Conjuration

        return any(
            conj.ref == ref and conj.by == eid for _, conj in world.each(Conjuration)
        )

    return check


def _still_held(ref: str) -> Callable[[World, int], bool]:
    """"While the target is immobilized or slowed by this power."

    The hold is on the enemy and the gate is asked of the caster, so this
    looks for anybody carrying one this creature laid.
    """

    def check(world: World, eid: int) -> bool:
        return any(
            eff.label == ref and eff.source == eid
            for eff in world.effects.live.values()
        )

    return check


def _victim_of(c: Cast, ref: str) -> int | None:
    for eff in c.world.effects.live.values():
        if eff.label == ref and eff.source == c.me:
            return eff.owner
    return None


def _square(c: Cast, who: int) -> tuple[int, int] | None:
    pos = c.world.get(who, Position)
    return None if pos is None else pos.square


@power(
    "p13303b",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PSIONIC_FORCE, Keyword.CONJURATION],
    attack=Attack(INT, vs=REF),
    requires=_standing("p13303"),
    requires_text="the p13303 power must be active",
)
def p13303b(c: Cast) -> None:
    """The swing is rolled from the conjuration, so cover and flanking are
    measured from where it stands. **Which creatures the row is offered
    against is still measured from the psion**, because that question is
    asked before the body runs and no header field moves it; the conjuration
    is laid in a square beside its caster, so the two rings differ by one.
    """
    shard = _conjuration(c, "p13303")
    if c.strike(from_=shard):
        c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
    if shard is not None:
        c.dispel(shard)


@power(
    "p13308b",
    level=1,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=PSIONIC_IMPLEMENT,
    attack=Attack(INT, vs=REF),
    uses=99,
    once_per_round=True,
    requires=_still_held("p13308"),
    requires_text="an enemy must still be held by the p13308 power",
)
def p13308b(c: Cast) -> None:
    """"One creature adjacent to the primary target at any point during the
    slide" is read off the ground the slide covered: where it started, where
    it finished, and the straight run between the two. The header's attack
    line is the secondary one -- the primary is not attacked at all, it is
    thrown -- so the row declares no target of its own and finds both
    creatures here.

    `uses` is opened up because the printed limit is once per round for as
    long as the hold stands, not once a day.
    """
    primary = _victim_of(c, "p13308")
    if primary is None:
        return
    before = _square(c, primary)
    c.slide(10, on=primary)
    after = _square(c, primary)
    if before is None or after is None:
        return
    swept = spread({*c.line(before, after), before, after}, 1)
    pool = [w for w in c.in_squares(swept, side="any") if w not in (c.me, primary)]
    second = c.choose(pool, "who it is flung past") if pool else None
    if second is None:
        return
    if c.strike(on=second):
        c.damage("2d6", c.int_mod, on=second)
        c.prone(on=second)
        c.half_damage("2d6", c.int_mod, on=primary)
    else:
        c.half_damage("2d6", c.int_mod, on=second)
    c.prone(on=primary)


@power(
    "p13322b",
    level=5,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=REF),
    uses=4,
    once_per_round=True,
    requires=active("p13322"),
    requires_text="the p13322 power must be active",
)
def p13322b(c: Cast) -> None:
    """Four spheres, four uses: the parent lays one hold per sphere and this
    ends one whether the shot lands or not, which is what expending means.
    The parent's bonus to defences is gated on at least one hold standing, so
    it goes out with the last sphere."""
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.FORCE)
        c.prone()
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == "p13322":
            c.world.effects.end(eff, c.ref)
            return


@power(
    "p13331b",
    level=7,
    cls="psion",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=PSIONIC_ACID,
    attack=Attack(INT, vs=FORT),
    requires=_standing("p13331"),
    requires_text="the p13331 power must be active",
)
def p13331b(c: Cast) -> None:
    """A close burst is centred on the creature using it, which is what the
    printed range line says and all it says. The conjuration is spent on the
    last target so that the whole burst resolves first."""
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.ACID)
        c.slowed(until=When.EONT)
    if not c.last:
        return
    servant = _conjuration(c, "p13331")
    if servant is not None:
        c.dispel(servant)


@power(
    "p13336b",
    level=9,
    cls="psion",
    usage=DAILY,
    action=REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.THUNDER],
    uses=99,
    requires=active("p13336"),
    requires_text="the p13336 power must be active",
    trigger="an enemy within 10 squares of you is hit by an attack",
    on=Trigger(
        Hit, enemy_target_within(10), "an enemy within 10 squares of you is hit"
    ),
)
def p13336b(c: Cast) -> None:
    """No attack roll of its own: the printed Effect is flat damage and a
    nudge. `uses` is opened up because the limit is the sustained hold on the
    parent, not a count."""
    c.flat(5, dtype=DamageType.THUNDER)
    c.slide(1)


def _mote(world: World, eid: int, ref: str) -> int | None:
    """That row's conjuration, still standing somewhere on the board."""
    from combat_engine.engine.components import Conjuration

    for who, conj in world.each(Conjuration):
        if conj.ref == ref and conj.by == eid and world.get(who, Position) is not None:
            return who
    return None


def _my_turn_with(ref: str) -> Callable[[World, int, TurnStart], bool]:
    """"At the start of your next turn", while that conjuration still stands."""

    def check(world: World, me: int, ev: TurnStart) -> bool:
        if getattr(ev, "ghost", False) or ev.actor != me:
            return False
        return _mote(world, me, ref) is not None

    return check


def _starts_turn_beside(ref: str) -> Callable[[World, int, TurnStart], bool]:
    """"An enemy starts its turn in a square adjacent to the anomaly."""

    def check(world: World, me: int, ev: TurnStart) -> bool:
        if getattr(ev, "ghost", False) or ev.actor == me:
            return False
        if team(world, ev.actor) is team(world, me):
            return False
        thing = _mote(world, me, ref)
        pos = world.get(thing, Position) if thing else None
        if pos is None:
            return False
        return bool(squares_of(world, ev.actor) & spread(pos.squares, 1))

    return check


@power(
    "p13462b",
    level=1,
    cls="psion",
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=PSIONIC_LIGHTNING,
    attack=Attack(INT, vs=REF),
    requires=_standing("p13462"),
    requires_text="this power follows the use of the p13462 power",
    trigger="the start of your turn, with the mote still standing",
    on=Trigger(
        TurnStart,
        _my_turn_with("p13462"),
        "the start of your turn, with the mote still standing",
    ),
)
def p13462b(c: Cast) -> None:
    """A No Action that declares a trigger rather than none: armed at the
    start of a fight it would go off once, out of nowhere, and never again.

    Augment 1 drags one of the creatures the burst caught toward the mote --
    one, so the drag stops after the first that moves.
    """
    mote = _mote(c.world, c.me, "p13462")
    pos = c.world.get(mote, Position) if mote else None
    if pos is None:
        return
    spent = spent_on(c.me, "p13462")
    dragged = False
    for who in sorted(c.in_squares(spread({pos.square}, 3), side="any")):
        if not c.strike(on=who, from_=mote):
            continue
        dice = "2d6" if spent == 2 else "1d6"
        c.damage(dice, c.int_mod, dtype=DamageType.LIGHTNING, on=who)
        if spent == 1 and not dragged:
            dragged = c.pull(1, on=who, anchor=pos.square) > 0


@power(
    "p13320b",
    level=3,
    cls="psion",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
    requires=_standing("p13320"),
    requires_text="the p13320 power must be active",
    trigger="an enemy starts its turn in a square adjacent to the anomaly",
    on=Trigger(
        TurnStart,
        _starts_turn_beside("p13320"),
        "an enemy starts its turn in a square adjacent to the anomaly",
    ),
)
def p13320b(c: Cast) -> None:
    """Melee 1 measured from the anomaly, so the victim is the triggering
    enemy rather than anything the reach gate picked.

    Augment 1's clause is the parent's -- the anomaly becomes something the
    psion's allies can flank with -- and is written there. Augment 2 is this
    block's, and is the only augment read here.
    """
    anomaly = _mote(c.world, c.me, "p13320")
    pos = c.world.get(anomaly, Position) if anomaly else None
    who = getattr(c.trigger, "actor", None)
    if pos is None or who is None:
        return
    spent = spent_on(c.me, "p13320")
    if not c.strike(on=who, from_=anomaly):
        return
    if spent == 2:
        c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC, on=who)
        c.dazed(on=who, until=When.EONT)
    else:
        c.damage("1d6", c.int_mod, dtype=DamageType.PSYCHIC, on=who)
    c.slide(3, on=who, anchor=pos.square)


@power(
    "p13339b",
    level=9,
    cls="psion",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=PSIONIC_LIGHTNING,
    attack=Attack(INT, vs=REF),
    uses=99,
    requires=_standing("p13339"),
    requires_text="the p13339 power must be active",
)
def p13339b(c: Cast) -> None:
    """The burst goes off round one of the parent's motes, not round the
    psion, so the row takes no target line and gathers its victims there.

    `uses` is opened up because the printed limit is the motes: each use
    expends the one it fired from, and the requirement fails when the last
    is gone.
    """
    mote = _mote(c.world, c.me, "p13339")
    pos = c.world.get(mote, Position) if mote else None
    if pos is None:
        return
    for who in sorted(c.in_squares(spread({pos.square}, 1), side="any")):
        if c.strike(on=who, from_=mote):
            c.damage("1d6", c.int_mod, dtype=DamageType.LIGHTNING, on=who)
            c.push(1, on=who, anchor=pos.square)
    c.dispel(mote)
