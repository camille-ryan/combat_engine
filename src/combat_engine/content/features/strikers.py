"""The three strikers' class features.

The extra damage first: three classes, one shape -- once in a while, when
you hit the right sort of target, you do more. The rogue's condition is
combat advantage, the ranger and the warlock each nominate a victim first,
and the rogue's card says once per *turn* where the other two say once per
round. None of these has a compendium row of its own -- they are described
on the class's own page -- so they all carry `cf:` refs.

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
    Powers,
    Ranged,
    Weapon,
    When,
    World,
    distance,
    get,
    power,
)
from combat_engine.engine.events import (
    Hit,
    MoveEnd,
    MoveStart,
    OpportunityWindow,
    TurnStart,
)
from combat_engine.engine.query import (
    alive,
    allies,
    distance_between,
    has_combat_advantage,
    team,
)

from .builds import RUFFIAN_GROUPS, on_leg


def extra_damage(
    c: Cast,
    dice: str,
    *,
    applies: Callable[[int], bool],
    label: str,
    per_turn: bool = False,
) -> None:
    """Arm "once per round, when you hit X, add dice".

    Written once because all three strikers are this and differ only in what
    counts as X. The latch is per *striker*, not per target -- hitting two
    different creatures in one payment window pays once, which is what all
    three printed texts say.

    Which window is the one difference between them, and it is not
    cosmetic. `per_turn` is the rogue's card, which says "only once per
    turn": the rogue may pay again on somebody else's turn, off an
    immediate action or an opportunity attack, and a per-round latch
    silently refused that. The initiative slot being played is what names a
    turn -- the round alone cannot, and the actor cannot either, because a
    solo with a second turn owns two slots.

    The payout adds whatever `"<label> damage"` modifier the striker is
    carrying. Closing over the dice alone left no number for a build feature
    to raise, and the rogue's fork is exactly that sentence.
    """
    me = c.me
    paid: dict[int, object] = {}

    def window() -> object:
        fight = c.world.encounter
        if not per_turn or fight is None:
            return c.world.round
        return (c.world.round, fight.index)

    def on_hit(ev: Hit) -> None:
        if ev.attacker != me or not applies(ev.target):
            return
        now = window()
        if paid.get(me) == now:
            return
        paid[me] = now
        # **The die is asked for, not closed over.** Four feats raise a
        # striker's extra damage from d6s to d8s and one to d10s, and with the
        # string baked in at arming time there was nothing for them to change.
        # `dice_for` falls through to `dice` for anybody carrying no such feat.
        # The target goes in the context because one of those feats narrows by
        # it -- "against a creature marked by your ..." -- and the gate has no
        # other way to know who was hit.
        rolled = c.dice_for(label, dice, {"target": ev.target})
        c.damage(rolled, c.total(f"{label} damage"), on=ev.target, detail=label)

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

    Untyped, which is what a class feature printing no type word is. It was
    kinded for a while to keep a ranger from collecting this *and* the
    alternative that replaces it, because `chargen.loadout` hands a class
    every level-0 row it has. The printed exclusivity is a choice of
    fighting style, and now that `chargen.BUILDS["ranger"]` carries a leg
    per style each of the two rows states its own half in `requires=` --
    which is the printed sentence rather than a bucket standing in for it.
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

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, kind="untyped", when=alone)


_TOOK_THE_TACTIC = on_leg("cutthroat")

#: The four arms the extra damage names -- a light blade and three shooters.
#: The hand crossbow and the shortbow the card prints are the `crossbow` and
#: `bow` groups here; `chargen` carries no weapon that is one of those groups
#: and not one of those weapons, so the groups are the closest the engine can
#: say it. Asking merely whether the weapon was *ranged* was wider than the
#: card in a way nothing would have noticed until a rogue picked up a bow.
_SNEAK_GROUPS = ("crossbow", "bow", "sling")


def _light_blade_or_bow(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    if gear is None or gear.main is None:
        return False
    if gear.main.is_light_blade or gear.main.group in _SNEAK_GROUPS:
        return True
    # The fourth tactic lets its two groups stand in for the light blade.
    # It is asked here rather than in `cf:rogue-tactic-club` because this
    # gate is the one place the requirement is written down.
    return _TOOK_THE_TACTIC(world, eid) and gear.main.group in RUFFIAN_GROUPS


#: The ids of the arms the rogue's two talents name. Weapons are ids here
#: like everything else, and `chargen` gives the class both of these.
_DAGGER = "w3594"
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


#: The leg whose printed feature says outright that it replaces the other
#: weapon talent. The two are exclusive on the page and were both dealt to
#: every rogue, so the leg is asked in each one's Requirement.
_TOOK_THE_SHOOTER = on_leg("shadowy")


def _carries_dagger(world: World, eid: int) -> bool:
    return not _TOOK_THE_SHOOTER(world, eid) and _carries(world, eid, ref=_DAGGER)


def _carries_shooter(world: World, eid: int) -> bool:
    return _TOOK_THE_SHOOTER(world, eid) and _carries(world, eid, groups=_SHOOTERS)


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
    "cf:rogue-scoundrel-f4",
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
    """Once a turn, a hit against a creature you have the drop on hurts more.

    Combat advantage is asked of the board at the moment of the hit rather
    than stored, which is the same reason `query` computes it: flanking ends
    the instant an ally steps away, and a stored flag would not notice.

    Per **turn**, which is what this card says and the other two strikers'
    cards do not -- so the rogue pays again on an opportunity attack in a
    round it has already paid in. See `extra_damage`.
    """
    extra_damage(
        c,
        "2d6",
        applies=lambda target: has_combat_advantage(c.world, c.me, target),
        label="cf:rogue-scoundrel-f4",
        per_turn=True,
    )


@power(
    "cf:rogue-scoundrel-f0",
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
    "cf:rogue-scoundrel-f1",
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

    Four tactics are printed across five legs -- two of the five take the
    same one -- and two of the four land here: the Strength leg raises the
    extra damage above, and the Charisma one is cover against being caught
    leaving. The remaining two are rows of their own on the legs that name
    them, `cf:rogue-tactic-stealth` and `cf:rogue-tactic-club`, because
    neither is a modifier this shape.

    The damage leg is a modifier rather than a second once-a-turn watcher.
    Two latches with the same condition would pay at the same moment right
    up until one of them stopped, and the one that arms is decided by a
    weapon Requirement the other does not carry.
    """
    if c.build("brawny"):
        c.bonus(
            "cf:rogue-scoundrel-f4 damage",
            c.str_mod,
            until=When.ENCOUNTER,
            on=c.me,
            kind="untyped",
        )
    elif c.build("trickster") or c.build("aerialist"):
        c.bonus(
            AC,
            c.cha_mod,
            until=When.ENCOUNTER,
            on=c.me,
            kind="untyped",
            when=lambda ctx: bool(ctx.get("opportunity")),
        )


@power(
    "cf:rogue-scoundrel-f2",
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
    "cf:rogue-scoundrel-f3",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=_carries_shooter,
    requires_text="needs the leg that trades the blade talent for this, and a shooter",
)
def rogue_ranged_talent(c: Cast) -> None:
    """A standing +1 to attacks made with either of the two groups printed.

    The printed line asks you to choose one of the two groups. No chassis
    carries both, so the choice never changes an outcome and offering it
    would be a question with one answer; both are allowed and the weapon in
    hand decides. Its first printed sentence says this feature *replaces*
    the blade talent above, which is stronger than the two never paying on
    one swing: the leg that took this does not have the other at all, and
    that is in both Requirements rather than left to the hand.

    The bonus feat the second half grants is not written: nothing in the
    engine is a feat, and what that one does is double a range.
    """
    me = c.me

    def with_the_shooter(ctx: dict[str, Any]) -> bool:
        weapon = _weapon_attack(c.world, me, ctx)
        return weapon is not None and weapon.group in _SHOOTERS

    c.bonus("attack", 1, until=When.ENCOUNTER, on=me, kind="untyped", when=with_the_shooter)


#: The legs of the ranger's fighting-style fork, as `chargen.BUILDS`
#: records them. Five styles are printed; these are the two whose benefit
#: is something other than a bonus feat, and the third that gives prime
#: shot up for a companion.
HUNTER_STYLE = "hunter"
MARAUDER_STYLE = "marauder"
BEAST_STYLE = "companion"

_ON_HUNTER = on_leg(HUNTER_STYLE)
_ON_BEAST = on_leg(BEAST_STYLE)


def _keeps_prime_shot(world: World, eid: int) -> bool:
    """Neither of the two printed ways of not having the shared ranged bonus.

    One style replaces it outright and one gives it up as the price of the
    companion, and both legs now exist, so both halves are live.
    """
    return not _ON_HUNTER(world, eid) and not _ON_BEAST(world, eid)


@power(
    "cf:ranger-f0",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def ranger_style(c: Cast) -> None:
    """Which fighting style was taken, and what it is worth in a fight.

    Five are printed and three of the five are a bonus feat and nothing
    else, or a bonus feat beside a permission `chargen` already grants --
    the two blades a ranger is dealt are both off-hand weapons already.
    Nothing here is a feat: the engine has none, and inventing one would be
    inventing a rule.

    What is left is two clauses, one per leg. One is cover while shooting
    out of somebody's reach; the other is a standing step of speed, which
    the printed line takes away from a ranger carrying a shield or swinging
    with both hands.

    The remaining style is the companion, and its whole benefit is a second
    creature: `c.call_beast` puts it on the board with the numbers off the
    category the leg chose. The other half of that style -- giving up prime
    shot -- is `_keeps_prime_shot` above, on the row that grants it.
    """
    me, world = c.me, c.world
    if c.build(BEAST_STYLE):
        c.call_beast()
        return
    if c.build(MARAUDER_STYLE):
        def unencumbered(ctx: dict[str, Any]) -> bool:
            gear = world.get(me, Gear)
            if gear is None:
                return True
            return not gear.shield and not any(w.two_handed for w in gear.held)

        c.bonus("speed", 1, until=When.ENCOUNTER, on=me, kind="untyped",
                when=unencumbered)
        return
    if not c.build(HUNTER_STYLE):
        return

    # "Against opportunity attacks you provoke by making a ranged attack."
    # The cause is on the window and not in the attack context, so the
    # bonus is laid when the window opens for that reason and spent by the
    # swing that answers it -- `once=True` on a defence ends it when the
    # blow lands or misses, which is the one attack the sentence means.
    def opened(ev: OpportunityWindow) -> None:
        if ev.provoker == me and "ranged power" in ev.why:
            c.bonus(
                AC, 4, until=When.EONT, on=me, kind="untyped", once=True,
                when=lambda ctx: bool(ctx.get("opportunity")),
            )

    c.watch(OpportunityWindow, opened, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "cf:ranger-f1",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL],
    once_per_round=True,
)
def ranger_quarry(c: Cast) -> None:
    """Name the nearest enemy as your quarry; hitting it pays once a round.

    The printed text says the nearest enemy you can see, which is a choice
    the ranger makes and the interface offers, so the target comes in as
    `c.target` like any other.

    **Once per turn** is what the class page allows, and the header says
    once per *round*, which is the nearest thing `usable` counts. The two
    differ only for a creature with two turns in a round, and no ranger
    the engine deals has one; without the field the row was a plain minor
    action and a ranger could re-nominate as often as it had minors.
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
        c, "1d6", applies=lambda target: target == quarry, label="cf:ranger-f1"
    )


@power(
    "cf:ranger-f2",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=_keeps_prime_shot,
    requires_text="lost to the fighting style that replaces it",
)
def ranger_nearest(c: Cast) -> None:
    """The shared ranged bonus. See `prime_shot`.

    The printed line ends with the two ways a ranger does not have this:
    the style that grants a companion gives it up, and the one that runs
    replaces it. `_keeps_prime_shot` is that sentence.
    """
    prime_shot(c)


@power(
    "cf:ranger-f3",
    level=0,
    cls="ranger",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=_ON_HUNTER,
    requires_text="needs the fighting style this replaces cf:ranger-f2 for",
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

    The printed line opens by saying which class feature this replaces, so
    the two are exclusive by name and not by arithmetic. It used to be
    said with a shared bonus `kind` that let the larger win, because
    `chargen.loadout` hands a class every level-0 row it has and there was
    no leg to ask about. There is one now, so both rows carry the printed
    half of the sentence in `requires=` and the bonus is untyped like any
    other class feature's.
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

    c.watch(MoveStart, on_start, until=When.ENCOUNTER, on=me, label="cf:ranger-f3")
    c.watch(MoveEnd, on_end, until=When.ENCOUNTER, on=me, label="cf:ranger-f3")
    c.bonus(
        "attack",
        1,
        until=When.ENCOUNTER,
        on=me,
        kind="untyped",
        when=lambda ctx: bool(ctx.get("charge")) and run["far"] >= 2,
    )


@power(
    "cf:warlock-f4",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE],
    once_per_round=True,
)
def warlock_curse(c: Cast) -> None:
    """Curse an enemy; hitting it pays once a round, for the rest of the fight.

    Several warlock powers read "if the target is cursed", and this is what
    makes that true. `c.cursed(target)` is how they ask.

    The class page's whole sentence about this row is that it may be used
    **once a turn**, and that was not written: an at-will minor action with
    nothing remembering it could be laid on every enemy in reach in one
    turn. `once_per_round` is the nearest the engine says it -- the guard is
    keyed to `world.round`, so the one creature that takes two turns in a
    round gets one curse across both rather than one each.
    """
    victim = c.target
    if victim is None:
        return
    c.curse(on=victim)
    extra_damage(
        c, "1d6", applies=lambda target: target == victim, label="cf:warlock-f4"
    )


@power(
    "cf:warlock-f2",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def warlock_nearest(c: Cast) -> None:
    """The shared ranged bonus. See `prime_shot`.

    **The warlock really does have this**, despite it reading as a ranger
    feature: the class page's own list names it among the five. Its text
    is the ranger's copied verbatim, ranger-specific trailing clause and
    all -- "you do not gain this feature if you choose the Beast Mastery
    fighting style", a style no warlock can take. That sentence is in the
    source, not an import artefact, and nothing here acts on it. Left
    alone deliberately: the row is right and the oddity is the
    compendium's.
    """
    prime_shot(c)


@power(
    "cf:warlock-f0",
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

    The other printed half is that `p1333` **counts as a ranged basic
    attack**, so anything granting one may use it. That was left out on the
    grounds that `Powers` had only a melee basic and an opportunity row, and
    that pointing `Powers.basic` at a Ranged 10 row would hand it to the
    opportunity window too. `Powers.ranged` is the third slot and exists for
    exactly this reason, so the line is written: the warlock's ranged basic
    becomes the blast instead of the engine's weapon row, which it could
    never use anyway -- its chassis carries an implement and no ranged
    weapon, and `basic.RANGED` refuses anyone not holding one.
    """
    c.grant_row("p1333")
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.ranged = "p1333"


@power(
    "cf:warlock-f1",
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

    A third leg pays here too. Its boon is a tally raised by exactly this
    trigger and spent by `p4311`, and the raising has to live where the
    other payouts do -- the row that spends it is an immediate interrupt
    and cannot also be armed on a creature dropping. The fourth leg's boon
    *is* a row (`p16254`), triggered on the same drop, so it is not here.

    The later books print four more pacts and there is no leg to ask about
    for any of them, and nothing is invented for them here.

    `Dropped` is announced before `_die` clears anything, so the curse is
    still on the creature when this reads it. Sides are compared directly
    rather than through `query.enemies`, which filters out the dead -- and
    the creature this is about has just died.
    """
    from combat_engine.content.powers.warlock.pacts import raise_tally

    me = c.me
    infernal = c.build("infernal")
    dark = c.build("dark")
    if not infernal and not dark and not c.build("fey"):
        return

    def on_drop(ev: Dropped) -> None:
        if ev.actor == me or team(c.world, ev.actor) == team(c.world, me):
            return
        if not c.cursed(on=ev.actor):
            return
        if infernal:
            c.temp_hp(c.level, on=me)
        elif dark:
            raise_tally(c)
        else:
            c.teleport(3, who=me)

    c.watch(Dropped, on_drop, until=When.ENCOUNTER, on=me, label="cf:warlock-f1")


@power(
    "cf:warlock-f3",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
)
def warlock_shadow(c: Cast) -> None:
    """Cover the ground and the shadows close over you: three squares away
    from where the turn began buys concealment.

    The printed sentence measures **displacement**, not mileage: "at least 3
    squares away from where you started your turn". An earlier draft summed
    each move action's length instead, so two squares out and two back --
    which ends where it began -- bought concealment. The turn's opening
    square is taken off `TurnStart` rather than off the first `MoveStart`,
    because that is the square the sentence names.

    "On your turn" is the other half, and it is why the caster's own turn is
    latched: forced movement on somebody else's turn is not the warlock
    moving. Granted once a turn -- `c.conceal` is a modifier, and a second
    one of the same kind would not add anyway.
    """
    me, world = c.me, c.world
    run: dict[str, Any] = {"from": None, "mine": False, "given": False}

    def on_turn(ev: TurnStart) -> None:
        mine = ev.actor == me and not getattr(ev, "ghost", False)
        run["mine"] = mine
        if mine:
            pos = world.get(me, Position)
            run["from"] = pos.square if pos else None
            run["given"] = False

    def on_end(ev: MoveEnd) -> None:
        began = run["from"]
        if ev.actor != me or not run["mine"] or began is None or run["given"]:
            return
        if distance(began, ev.at) >= 3:
            run["given"] = True
            c.conceal(on=me, until=When.EONT)

    for kind, fn in ((TurnStart, on_turn), (MoveEnd, on_end)):
        c.watch(kind, fn, until=When.ENCOUNTER, on=me, label="cf:warlock-f3")
