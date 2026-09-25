"""Warlord, level 2: the utilities the later books added.

`level_2.py` holds the first four; these are the rest. Three notes apply
across the batch.

**The presences.** `chargen` knows two warlord builds, `inspiring` and
`tactical`, so a rider keyed to any of the others has no fork to read and
those rows are the printed base line only -- the same reading `level_1_b.py`
took.

**A second wind is a counted use**, not a heal with a name: `Powers` holds
the counter that `actions.legal` reads, so taking one costs a `note_use` and
handing one back is a `restore`. The defences that come with it are applied
here as well, because nothing else would.

**"No action" is not an action type.** `ActionType.NONE` marks a trait,
which `_arm_traits` turns on at the start of the fight and the dispatcher
never offers; a *triggered* row declared with it could therefore never fire.
The two here are `FREE`, which is the window the dispatcher answers in.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    ONE_ALLY,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    REF,
    WILL,
    Cast,
    CloseBurst,
    Condition,
    Event,
    Hit,
    Initiative,
    Keyword,
    Melee,
    Powers,
    Ranged,
    Relation,
    RoundStart,
    Target,
    Trigger,
    Usage,
    When,
    World,
    about_me,
    both,
    by_me,
    by_melee,
    get,
    power,
)
from combat_engine.engine.events import EffectApplied, InitiativeRolled
from combat_engine.engine.query import creatures, is_, level_term

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_HEALING = [Keyword.HEALING, Keyword.MARTIAL]

#: Everyone on your side in the area except you, for a line that names the
#: caster separately.
EACH_OTHER_ALLY = Target("other_ally", 99, everyone=True, label="Each ally in the burst")

#: What `actions.perform` labels the effect a second wind installs. It is
#: the one thing on the bus that tells a second wind from any other spent
#: surge -- `SurgeSpent` carries the actor and nothing about why.
SECOND_WIND = "second-wind"


def _friends_within(c: Cast, squares: int) -> list[int]:
    """Allies in range -- "an ally", so never the warlord itself."""
    return [a for a in c.within(squares, side="ally") if a != c.me]


def _take_second_wind(c: Cast, who: int, bonus: int = 0) -> int:
    """Somebody takes a second wind out of turn, at your word.

    `actions.perform` owns the only other copy: a counted use, a surge, and
    a hold on the defences. Spelling it out is what "the target can use its
    second wind" means -- `c.surge` alone spends the surge without ever
    marking the use, so the target could take another one on its own turn.
    """
    known = c.world.get(who, Powers)
    if known is not None:
        known.note_use(SECOND_WIND, c.world.round)
    healed = c.surge(on=who, bonus=bonus)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=who, until=When.SOTNT, kind="untyped")
    return healed


def _initiative_check(c: Cast, who: int) -> int:
    """One initiative check, rolled the way `Encounter` rolls them."""
    init = c.world.get(who, Initiative) or c.world.add(who, Initiative())
    return c.world.rng.d20().total + init.bonus + level_term(c.world, who, init.scale)


_MY_AT_WILL = "an enemy is hit by your at-will weapon attack"


def _my_at_will_weapon_hit(world: World, me: int, ev: Hit) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.usage is Usage.AT_WILL and Keyword.WEAPON in p.keywords


_SURPRISE = "a surprise round begins, and you are conscious"


def _surprise_round(world: World, me: int, ev: RoundStart) -> bool:
    """Nothing announces a surprise round; what one *is* is a round that
    begins with somebody still surprised, which is readable."""
    if is_(world, me, Condition.UNCONSCIOUS):
        return False
    return any(is_(world, x, Condition.SURPRISED) for x in creatures(world))


_ROLLED_INITIATIVE = "you roll initiative"

_SECOND_WIND_NEARBY = "you or an ally within 5 squares of you uses second wind"


def _second_wind_within(squares: int) -> Callable[[World, int, Event], bool]:
    """Somebody in range took a second wind.

    Read off the hold it installs rather than off `SurgeSpent`, which says
    a surge left a pool and not what spent it -- and a leader row spending
    an ally's surge is not the printed sentence.
    """
    from combat_engine.engine.query import distance_between, team

    def check(world: World, me: int, ev: Event) -> bool:
        if SECOND_WIND not in getattr(ev, "label", ""):
            return False
        who = getattr(ev, "target", None)
        if who is None or team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


@power(
    "p10916",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=MARTIAL_HEALING,
)
def p10916(c: Cast) -> None:
    """A printed "can": the surge is the target's, so the target is asked."""
    who = c.target
    if who is not None and c.may("use its second wind", who=who):
        _take_second_wind(c, who, bonus=c.cha_mod)


@power(
    "p10917",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    trigger=_MY_AT_WILL,
    on=Trigger(Hit, when=_my_at_will_weapon_hit, text=_MY_AT_WILL),
)
def p10917(c: Cast) -> None:
    """The enemy is read off the event: `Triggers._at` re-aims a single-enemy
    row at whoever the event was *about*, which on your own hit is you, so it
    hands the row back its own auto-targeting instead.

    Prone is offered first -- it is worth having at any Intelligence, and a
    shove of nought squares is worth nothing.
    """
    foe = getattr(c.trigger, "target", None) or c.target
    if foe is None:
        return
    if c.choose(["knock it prone", "push it"], "which") == "push it":
        c.push(max(c.int_mod, c.wis_mod), on=foe)
    else:
        c.prone(on=foe)


@power(
    "p10918",
    level=2,
    cls="warlord",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(10),
    target=Target("ally", 99, everyone=True, label="You and each surprised ally"),
    keywords=MARTIAL,
    trigger=_SURPRISE,
    on=Trigger(RoundStart, when=_surprise_round, text=_SURPRISE),
)
def p10918(c: Cast) -> None:
    """Being surprised is a condition and ending one early is ending the
    effect that carries it, which is the only door `Effects` has."""
    who = c.target
    if who is None or (who != c.me and not c.is_(Condition.SURPRISED, on=who)):
        return
    for eff in list(c.world.effects.of(who)):
        if Condition.SURPRISED in eff.conditions:
            c.world.effects.end(eff, c.ref)
    c.bonus(AC, c.int_mod, on=who, until=When.EONT)
    c.bonus(REF, c.int_mod, on=who, until=When.EONT)


@power(
    "p10919",
    level=2,
    cls="warlord",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(10),
    target=Target("ally", 99, everyone=True, label="You and each ally in the burst"),
    keywords=MARTIAL,
    trigger=_ROLLED_INITIATIVE,
    on=Trigger(InitiativeRolled, when=about_me, text=_ROLLED_INITIATIVE),
)
def p10919(c: Cast) -> None:
    """"Must use the second result" is what `reroll_initiative` does: it
    replaces the roll and splices the creature back into the order."""
    who = c.target
    if who is not None and c.may("take a new initiative check", who=who):
        c.reroll_initiative(on=who)


_HIT_IN_MELEE = "you hit an enemy with a melee attack"


@power(
    "p11721",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_OTHER_ALLY,
    keywords=MARTIAL,
    trigger=_HIT_IN_MELEE,
    on=Trigger(Hit, when=both(by_me, by_melee), text=_HIT_IN_MELEE),
)
def p11721(c: Cast) -> None:
    """Printed Personal with a target; the reach is what picks the ally, and
    "adjacent to you" is a melee one."""
    friend = c.target
    if friend is None:
        return
    c.shift(3, who=friend)
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.grants_advantage(on=foe, to=friend, until=When.EONT)


@power(
    "p2531",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=MARTIAL,
)
def p2531(c: Cast) -> None:
    """Two targets on two sides, and the header carries one: the enemy is
    the declared target and the friend is picked here.

    The hold is applied through `Effects` rather than through
    `c.grants_advantage` so that the **winner** is its source -- "until the
    end of the winner's next turn" is a clock on a creature that is neither
    the caster nor the one the effect sits on, and `When.EONT` reads the
    source. A tie goes to your side.
    """
    foe = c.target
    if foe is None:
        return
    pool = sorted(c.within(5, side="ally"))
    friend = c.choose(pool, "who sizes it up") if pool else None
    if friend is None:
        return
    winner, loser = (
        (friend, foe)
        if _initiative_check(c, friend) >= _initiative_check(c, foe)
        else (foe, friend)
    )
    c.world.effects.apply(
        loser,
        winner,
        When.EONT,
        label=f"{c.ref} advantage",
        relations=[(Relation.GRANTS_CA_TO, loser, winner)],
    )


@power(
    "p2555",
    level=2,
    cls="warlord",
    usage=DAILY,
    action=MOVE,
    reach=CloseBurst(5),
    target=Target("ally", 99, everyone=True, label="You and each ally in the burst"),
    keywords=MARTIAL,
)
def p2555(c: Cast) -> None:
    """The burst widens with the build, and a header is data read before
    anything runs -- so the printed five are the declared targets and the
    further five are gathered here, once."""
    if c.target is not None and c.may("shift a square", who=c.target):
        c.shift(1, who=c.target)
    if c.first and c.build("tactical"):
        for friend in c.within(10, side="ally"):
            if friend in c.targets:
                continue
            if c.may("shift a square", who=friend):
                c.shift(1, who=friend)


@power(
    "p4549",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p4549(c: Cast) -> None:
    """The ally's choice, so the ally is asked. Damage first: a saving throw
    bonus is worth nothing to somebody carrying nothing that saves."""
    if c.target is None:
        return
    pick = c.choose(["damage rolls", "saving throws"], "which bonus")
    if pick == "saving throws":
        c.bonus("save", c.cha_mod, until=When.EONT)
    else:
        c.bonus("damage", c.int_mod, until=When.EONT)


def _bloodied(world: World, eid: int) -> bool:
    from combat_engine.engine import Health

    health = world.get(eid, Health)
    return health is not None and health.bloodied


@power(
    "p4550",
    level=2,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(10),
    target=EACH_OTHER_ALLY,
    keywords=MARTIAL,
    requires=_bloodied,
    requires_text="you must be bloodied",
)
def p4550(c: Cast) -> None:
    """"Until you are no longer bloodied" is not a duration the engine holds,
    so it is a gate on the modifier instead: the hold runs the encounter and
    pays out only while the warlord is still bloodied. The one difference
    from the printed line is that being bloodied a second time turns it back
    on, which costs a heal and a wound to notice.
    """
    if c.first:
        c.temp_hp(c.level + c.cha_mod, on=c.me)
    if c.target is not None:
        c.bonus(
            "damage",
            c.cha_mod,
            until=When.ENCOUNTER,
            when=lambda ctx: c.bloodied(c.me),
        )


@power(
    "p4551",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=MARTIAL,
)
def p4551(c: Cast) -> None:
    """"All your allies" and not you, which `c.grants_advantage(to="allies")`
    would include -- so the relations are listed out, one per ally, on the
    single hold that method would have made.

    The printed target is an enemy already granting combat advantage to
    somebody; the header filters by side and not by state, so that much of
    the line is not enforced.
    """
    foe = c.target
    friends = c.allies()
    if foe is None or not friends:
        return
    c.world.effects.apply(
        foe,
        c.me,
        When.SONT,
        label=f"{c.ref} advantage",
        relations=[(Relation.GRANTS_CA_TO, foe, a) for a in friends],
    )
    if c.build("inspiring"):
        at_it = lambda ctx: ctx.get("target") == foe  # noqa: E731
        for friend in friends:
            c.bonus("damage", c.cha_mod, on=friend, until=When.SONT, when=at_it)


@power(
    "p4552",
    level=2,
    cls="warlord",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p4552(c: Cast) -> None:
    """Giving a second wind back is `restore` on the counter `actions.legal`
    reads, the same door the cleric's version goes through. The printed
    target is a bloodied ally; the header filters by side only."""
    who = c.target
    if who is None:
        return
    known = c.world.get(who, Powers)
    if known is not None:
        known.restore(SECOND_WIND)
    c.bonus("attack", c.cha_mod, on=who, until=When.ENCOUNTER, once=True)


@power(
    "p4554",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p4554(c: Cast) -> None:
    """"You if you're bloodied or one bloodied ally": the ally pool already
    has the caster in it, which is the whole of the first half."""
    c.temp_hp(5 + c.cha_mod)


@power(
    "p4675",
    level=2,
    cls="warlord",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=ONE_OTHER_ALLY,
    keywords=MARTIAL,
    trigger=_SECOND_WIND_NEARBY,
    on=Trigger(EffectApplied, when=_second_wind_within(5), text=_SECOND_WIND_NEARBY),
)
def p4675(c: Cast) -> None:
    """The mark is the **ally's**, not the warlord's, so it is applied with
    the ally as its source -- `c.mark` would hang it off the caster and every
    "if the marked creature attacks somebody else" rider would then read the
    wrong creature.
    """
    used_it = getattr(c.trigger, "target", None)
    friend = c.target
    if friend is None or friend == used_it:
        pool = [a for a in _friends_within(c, 5) if a != used_it]
        friend = c.choose(sorted(pool), "who moves up") if pool else None
    if friend is None:
        return
    c.shift(1, who=friend)
    foes = sorted(c.within(5, side="enemy"))
    foe = c.choose(foes, "who the ally marks") if foes else None
    if foe is not None:
        c.world.effects.apply(
            foe,
            friend,
            When.EOTNT,
            label=f"{c.ref} mark",
            relations=[(Relation.MARKED_BY, friend, foe)],
        )
