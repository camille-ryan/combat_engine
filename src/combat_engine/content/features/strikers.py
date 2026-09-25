"""The three strikers' class features.

The extra damage first: three classes, one shape -- once a round, when you
hit the right sort of target, you do more. The rogue's condition is combat
advantage, the ranger and the warlock each nominate a victim first. None of
these has a compendium row of its own -- they are described on the class's
own page -- so they all carry `cf:` refs and no spec file mentions them.

A striker without this is not a striker. The rogue's dagger does 1d4, and
the whole class is built around what happens the round it connects.

The rest of each class's page is here too: the openings, the weapon
talents, the shared ranged bonus, and the one feature per class that forks
on which build was taken. A **trait** -- `action=ActionType.NONE` -- is
simply true of the creature and is armed once by `Encounter._arm_traits`;
only the two that print a Minor Action are actions anybody takes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    ActionType,
    Cast,
    Dropped,
    Gear,
    Keyword,
    Position,
    Ranged,
    Weapon,
    When,
    World,
    distance,
    get,
    power,
)
from combat_engine.engine.events import Hit, MoveEnd, MoveStart
from combat_engine.engine.query import (
    alive,
    allies,
    distance_between,
    has_combat_advantage,
    team,
)


def extra_damage(
    c: Cast, dice: str, *, applies: Callable[[int], bool], label: str
) -> None:
    """Arm "once per round, when you hit X, add dice".

    Written once because all three strikers are this and differ only in what
    counts as X. The latch is per round and per *striker*, not per target --
    hitting two different creatures in one round pays once, which is what
    every one of the three printed texts says.

    The payout adds whatever `"<label> damage"` modifier the striker is
    carrying. Closing over the dice alone left no number for a build feature
    to raise, and the rogue's fork is exactly that sentence.
    """
    me = c.me
    paid: dict[int, int] = {}

    def on_hit(ev: Hit) -> None:
        if ev.attacker != me or not applies(ev.target):
            return
        if paid.get(me) == c.world.round:
            return
        paid[me] = c.world.round
        c.damage(dice, c.total(f"{label} damage"), on=ev.target, detail=label)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=label)


def prime_shot(c: Cast) -> None:
    """Arm "+1 to a ranged attack on a target no ally of yours stands nearer to".

    Written once because the ranger and the warlock print the identical
    sentence, the same reason `extra_damage` above is written once. The
    comparison is made at the moment of the roll rather than stored, for the
    reason combat advantage is computed rather than stored: the ally that
    was behind you a moment ago has walked past.

    Dead allies are left out -- a corpse is lifted off the grid, so its
    distance is meaningless rather than large.

    The bonus is kinded rather than untyped, which a class feature's would
    normally be. The ranger prints this and one alternative that replaces
    it, and `chargen.loadout` hands a class *every* level-0 row it has, so
    a ranger here holds both. A shared kind makes the larger win, which is
    what having one of the two comes to; untyped would add them.
    """
    me, world = c.me, c.world

    def alone(ctx: dict[str, Any]) -> bool:
        target = ctx.get("target")
        if target is None or not ctx.get("ranged"):
            return False
        mine = distance_between(world, me, target)
        return all(
            distance_between(world, mate, target) >= mine
            for mate in allies(world, me)
            if alive(world, mate)
        )

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, kind="class feature", when=alone)


def _light_blade_or_bow(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    if gear is None or gear.main is None:
        return False
    return gear.main.is_light_blade or bool(gear.main.ranged)


#: The ids of the arms the rogue's two talents name. Weapons are ids here
#: like everything else, and `chargen` gives the class both of these.
_DAGGER = "w:dagger"
_SHOOTERS = ("crossbow", "sling")


def _carries(world: World, eid: int, *, ref: str = "", groups: tuple[str, ...] = ()) -> bool:
    """Is this weapon on the creature at all -- in hand or on the belt?

    A `requires=` gate rather than the modifier's own: a two-handed weapon
    is stowed while a blade is out, and a talent that stopped existing
    whenever the other hand was full would be off for most of a fight.
    """
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return any(w.ref == ref or w.group in groups for w in gear.weapons)


def _carries_dagger(world: World, eid: int) -> bool:
    return _carries(world, eid, ref=_DAGGER)


def _carries_shooter(world: World, eid: int) -> bool:
    return _carries(world, eid, groups=_SHOOTERS)


def _weapon_attack(world: World, eid: int, ctx: dict[str, Any]) -> Weapon | None:
    """Which weapon a **weapon** attack is being swung with, if it is one.

    The grip is the same choice `c.w` makes -- the ranged weapon for a
    ranged branch, whatever is in the main hand otherwise -- because a
    talent that pays on one weapon has to agree with the dice being rolled.
    `ctx["power"]` is a ref, so the keyword half is a registry lookup.
    """
    declared = get(ctx.get("power") or "")
    if declared is None or Keyword.WEAPON not in declared.keywords:
        return None
    gear = world.get(eid, Gear)
    if gear is None:
        return None
    if ctx.get("ranged") and gear.ranged is not None:
        return gear.ranged
    return gear.main


@power(
    "cf:rogue-bonus",
    level=0,
    cls="rogue",
    # A trait, not an action. Nobody *does* this -- it is simply true of a
    # rogue, and `Encounter._arm_traits` turns it on when the fight starts.
    # As an at-will free action the policy re-took it every spare moment and
    # stacked a fresh watcher each time.
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=_light_blade_or_bow,
    requires_text="needs a light blade, a crossbow or a sling",
)
def rogue_bonus(c: Cast) -> None:
    """Once a round, a hit against a creature you have the drop on hurts more.

    Combat advantage is asked of the board at the moment of the hit rather
    than stored, which is the same reason `query` computes it: flanking ends
    the instant an ally steps away, and a stored flag would not notice.
    """
    extra_damage(
        c,
        "2d6",
        applies=lambda target: has_combat_advantage(c.world, c.me, target),
        label="cf:rogue-bonus",
    )


@power(
    "cf:rogue-advantage",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def rogue_advantage(c: Cast) -> None:
    """Nobody who has not moved yet is watching you.

    One grant per creature rather than one flag on the rogue, because the
    printed condition is per creature: it lapses the moment *that* creature
    acts, not when the round turns over. `When.SOTNT` is clocked on the
    creature the effect sits on, so each grant ends at the start of that
    creature's first turn -- the printed sentence exactly, and with no
    watcher of its own to keep in step.

    The round is checked because `Encounter.join` arms a latecomer's traits
    too, and a rogue walking into round five has caught nobody cold.
    """
    fight = c.world.encounter
    if fight is None or c.world.round > 1:
        return
    for other in fight.order:
        if other != c.me:
            c.grants_advantage(on=other, until=When.SOTNT)


@power(
    "cf:rogue-tactic",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def rogue_tactic(c: Cast) -> None:
    """Which leg of the fork was taken, and what it is worth in a fight.

    Four are printed and `chargen.BUILDS["rogue"]` carries two legs, so two
    of them land here: the Strength leg raises the extra damage above, and
    the Charisma leg is cover against being caught leaving. The other two
    have no leg to ask for and are recorded in `docs/blocked.json` rather
    than folded into one that does not exist -- one of them is a rule about
    Stealth checks, which is not a fight at all, and the other grants two
    weapon proficiencies plus a rider on a keyword the enum does not have.

    The damage leg is a modifier rather than a second once-a-round watcher.
    Two latches with the same condition would pay at the same moment right
    up until one of them stopped, and the one that arms is decided by a
    weapon Requirement the other does not carry.
    """
    if c.build("brawny"):
        c.bonus(
            "cf:rogue-bonus damage",
            c.str_mod,
            until=When.ENCOUNTER,
            on=c.me,
            kind="untyped",
        )
    elif c.build("trickster"):
        c.bonus(
            AC,
            c.cha_mod,
            until=When.ENCOUNTER,
            on=c.me,
            kind="untyped",
            when=lambda ctx: bool(ctx.get("opportunity")),
        )


@power(
    "cf:rogue-melee-talent",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=_carries_dagger,
    requires_text="needs the light blade this class is trained in",
)
def rogue_melee_talent(c: Cast) -> None:
    """A standing +1 to attacks made with the one blade the talent names.

    Untyped, because a class feature stacks with everything; gated on the
    weapon the swing is actually using rather than installed once on the
    strength of what was in hand when the fight began.

    The other printed half raises a thrown weapon's damage die by one size.
    `chargen` has no such weapon and no modifier steps a die, so that half
    is reported rather than approximated.
    """
    me = c.me

    def with_the_blade(ctx: dict[str, Any]) -> bool:
        weapon = _weapon_attack(c.world, me, ctx)
        return weapon is not None and weapon.ref == _DAGGER

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, kind="untyped", when=with_the_blade)


@power(
    "cf:rogue-ranged-talent",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=_carries_shooter,
    requires_text="needs a crossbow or a sling",
)
def rogue_ranged_talent(c: Cast) -> None:
    """A standing +1 to attacks made with either of the two groups printed.

    The printed line asks you to choose one of the two groups. No chassis
    carries both, so the choice never changes an outcome and offering it
    would be a question with one answer; both are allowed and the weapon in
    hand decides. Its sibling above and this one cannot both pay on one
    swing -- a hand holds one weapon -- which is what the printed line means
    by one replacing the other.

    The bonus feat the second half grants is not written: nothing in the
    engine is a feat, and what that one does is double a range.
    """
    me = c.me

    def with_the_shooter(ctx: dict[str, Any]) -> bool:
        weapon = _weapon_attack(c.world, me, ctx)
        return weapon is not None and weapon.group in _SHOOTERS

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, kind="untyped", when=with_the_shooter)


@power(
    "cf:ranger-quarry",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL],
)
def ranger_quarry(c: Cast) -> None:
    """Name the nearest enemy as your quarry; hitting it pays once a round.

    The printed text says the nearest enemy you can see, which is a choice
    the ranger makes and the interface offers, so the target comes in as
    `c.target` like any other.
    """
    quarry = c.target
    if quarry is None:
        return
    # Named in the relation as well as in the closure. Without this
    # `c.is_quarry()` was false for a creature the ranger had just made its
    # quarry -- the sibling curse below does it and this did not -- so every
    # printed "against your quarry" rider was silently dead.
    c.quarry(on=quarry)
    extra_damage(
        c, "1d6", applies=lambda target: target == quarry, label="cf:ranger-quarry"
    )


@power(
    "cf:ranger-nearest",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def ranger_nearest(c: Cast) -> None:
    """The shared ranged bonus. See `prime_shot`."""
    prime_shot(c)


@power(
    "cf:ranger-running",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def ranger_running(c: Cast) -> None:
    """+1 on the swing at the end of a run, when the run covered ground.

    The printed condition is a standard action that lets you move. The only
    one the engine builds is the charge, which carries `charge` in the
    attack context, so that is what this asks about; a row whose own Effect
    is a move-and-attack is not marked and does not pay, and that is said
    here rather than left to be discovered.

    The distance is measured rather than assumed. A charge here needs only
    one square and the printed rider needs two, so where the move began is
    remembered on `MoveStart` -- which fires before anybody has moved -- and
    compared with where it ended.

    It shares a `kind` with `prime_shot` deliberately: the two are
    alternatives on the page, one replacing the other, and `chargen` hands
    a class every level-0 row it has. A shared kind makes the larger win
    rather than letting one ranger collect both.
    """
    me, world = c.me, c.world
    run: dict[str, Any] = {"from": None, "far": 0}

    def on_start(ev: MoveStart) -> None:
        if ev.actor != me:
            return
        pos = world.get(me, Position)
        run["from"] = pos.square if pos else None

    def on_end(ev: MoveEnd) -> None:
        if ev.actor != me:
            return
        began = run["from"]
        run["far"] = distance(began, ev.at) if began is not None else 0

    c.watch(MoveStart, on_start, until=When.ENCOUNTER, on=me, label="cf:ranger-running")
    c.watch(MoveEnd, on_end, until=When.ENCOUNTER, on=me, label="cf:ranger-running")
    c.bonus(
        "attack",
        1,
        until=When.ENCOUNTER,
        on=me,
        kind="class feature",
        when=lambda ctx: bool(ctx.get("charge")) and run["far"] >= 2,
    )


@power(
    "cf:warlock-curse",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE],
)
def warlock_curse(c: Cast) -> None:
    """Curse an enemy; hitting it pays once a round, for the rest of the fight.

    Several warlock powers read "if the target is cursed", and this is what
    makes that true. `c.cursed(target)` is how they ask.
    """
    victim = c.target
    if victim is None:
        return
    c.curse(on=victim)
    extra_damage(
        c, "1d6", applies=lambda target: target == victim, label="cf:warlock-curse"
    )


@power(
    "cf:warlock-nearest",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def warlock_nearest(c: Cast) -> None:
    """The shared ranged bonus. See `prime_shot`."""
    prime_shot(c)


@power(
    "cf:warlock-blast",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def warlock_blast(c: Cast) -> None:
    """Every warlock knows `p1333`, whatever else it drew.

    `chargen.loadout` samples two at-wills out of a pool of dozens, so a
    warlock built here usually does not have the one its own page says it
    always has. `c.grant_row` is that sentence, and it is a no-op for a
    warlock that drew it anyway.

    The other printed half -- that `p1333` counts as a ranged basic attack,
    so anything granting one may use it -- is not written. `Powers` records
    a melee basic and an opportunity row and has no third slot, and pointing
    `Powers.basic` at a Ranged 10 row would hand it to the opportunity
    window as well, which the printed line does not say.
    """
    c.grant_row("p1333")


@power(
    "cf:warlock-pact",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def warlock_pact(c: Cast) -> None:
    """What the bargain pays out when a cursed enemy goes down.

    `chargen.BUILDS["warlock"]` carries the two legs the first book prints
    and this pays each of them: one takes vitality off the fallen, the other
    slips away. The at-will each pact also grants is a power row of its own
    and belongs to `chargen`, not here.

    The later books print six more pacts and there is no leg to ask about
    for any of them. Two rows already record that in `docs/blocked.json`,
    and nothing is invented for them here.

    `Dropped` is announced before `_die` clears anything, so the curse is
    still on the creature when this reads it. Sides are compared directly
    rather than through `query.enemies`, which filters out the dead -- and
    the creature this is about has just died.
    """
    me = c.me
    infernal = c.build("infernal")
    if not infernal and not c.build("fey"):
        return

    def on_drop(ev: Dropped) -> None:
        if ev.actor == me or team(c.world, ev.actor) == team(c.world, me):
            return
        if not c.cursed(on=ev.actor):
            return
        if infernal:
            c.temp_hp(c.level, on=me)
        else:
            c.teleport(3, who=me)

    c.watch(Dropped, on_drop, until=When.ENCOUNTER, on=me, label="cf:warlock-pact")
