"""Ranger, level 2: the utilities that need a beast companion.

The engine has a companion now, so the rows `level_2.py` left out for want
of one are here. What the engine still has no notion of is a companion's
*species*. `c.call_companion` with no ref builds a body whose numbers come
off its owner, and the spec names no database ref for a beast, so there is
nothing for a species to be read off.

That splits the printed lines two ways. A Prerequisite naming a species is
an entry requirement, so it is checked as far as it can be -- the ranger
must own a beast -- and the printed sentence is kept in `requires_text`.
A `Beast:` rider that pays out only for a named species is dropped, because
asking a question that is always false is what a broken rider looks like.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    Cast,
    CloseBurst,
    Keyword,
    Movement,
    When,
    Window,
    World,
    power,
)
from combat_engine.engine.components import Companion
from combat_engine.engine.events import (
    AttackRolled,
    DamageApplied,
    DamageRolled,
    ForcedMove,
    Hit,
    SkillCheck,
)
from combat_engine.engine.triggers import Trigger, both, by_melee, targets_me

MARTIAL = [Keyword.MARTIAL]
MARTIAL_STANCE = [Keyword.MARTIAL, Keyword.STANCE]

_HIT_ON_AC_OR_REF = "you are hit by an attack that targets AC or Reflex"
_SHOVED = "you or your beast companion are pushed, pulled or slid"
_MELEE_DAMAGE = "you take damage from a melee attack"
_CLIMB_OR_SAVE = "you make a climb check, or a saving throw to stay on your feet"
_A_CLIMB_CHECK = "you make an Athletics check while climbing"


def _climbing_athletics(world: World, me: int, ev: object) -> bool:
    """"An Athletics check made **while climbing**."

    `Movement.using` is what a creature is doing rather than what it can do,
    and `movement.walk` holds it past the end of the move -- so a ranger who
    climbed a wall is still climbing when the check is rolled.
    """
    from combat_engine.engine.query import moving_as

    return (
        getattr(ev, "actor", None) == me
        and getattr(ev, "skill", "") == "athletics"
        and moving_as(world, me, "climb")
    )


def _has_beast(world: World, eid: int) -> bool:
    """"You must have a beast companion", with no species named."""
    return any(
        world.get(who, Companion).owner == eid for who in world.having(Companion)
    )


#: Each printed beast category, by the `companion` table ref that holds its
#: block. **Refs rather than the printed words**, which is the only reason this
#: can be in a tracked file at all: the category names are printed names and
#: live in `localization/`.
#:
#: The one category implemented is the bear (#235 / Camille's call), so eight of
#: the nine rows below are refused in play today -- correctly, and that is the
#: point. They were all gated on `_has_beast`, which asks only whether the
#: ranger owns *a* companion, so **fielding any beast made all nine usable** and
#: eight of them were wrong. Measured with a bear: 9 usable before, 1 after.
_CATEGORY = {
    "raptor": "comp:5",
    "cat": "comp:3",
    "simian": "comp:91",
    "lizard": "comp:4",
    "serpent": "comp:6",
    "boar": "comp:2",
    "bear": "comp:1",
    "spider": "comp:7",
    "wolf": "comp:8",
}


def _beast_is(category: str) -> Callable[[World, int], bool]:
    """"You must have a **<species>** beast companion" -- the half that used to
    be unaskable.

    The module docstring of `beast_sb.py` says the species "belongs to a
    *species*, which this engine does not model", and that was true when it was
    written: a ref-less companion is built from a copy of its owner and has no
    category at all. It is not true now. `chargen` records the category beside
    the leg as `beast:comp:N`, `c.call_beast` reads it back, and
    `Companion.ref` carries it on the board -- so the species is exactly as
    askable as the block's die, which every row here already rolls.

    Refused when the ranger has no companion at all, and when the one it has is
    a different category. Both are the printed Requirement.
    """
    want = _CATEGORY[category]

    def gate(world: World, eid: int) -> bool:
        return any(
            (mine := world.get(who, Companion)).owner == eid and mine.ref == want
            for who in world.having(Companion)
        )

    return gate


def _would_hit(ev: AttackRolled) -> bool:
    """Is the roll a hit as it stands? Read off the event's own numbers.

    The defence is read a second time after `AttackRolled` is announced, so
    a row that raises a defence in this window turns the hit into a miss.
    That is the whole point of the shape, and it needs to know the blow was
    landing before it interferes.
    """
    return ev.natural != 1 and ev.total >= ev.defence


def _hit_on_ac_or_ref(world: World, me: int, ev: AttackRolled) -> bool:
    return ev.target == me and ev.vs in (AC, REF) and _would_hit(ev)


def _shoved_us(world: World, me: int, ev: ForcedMove) -> bool:
    if ev.target == me:
        return True
    mine = world.get(ev.target, Companion)
    return mine is not None and mine.owner == me


@power(
    "p13696",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_beast_is("raptor"),
    requires_text="you must have a raptor beast companion",
)
def p13696(c: Cast) -> None:
    """Only the fly half is a combat effect, and only for a ranger who flies.

    A long jump is a skill check nothing here rolls. "A +2 power bonus on
    your fly speed (if any)" is not a modifier key -- flight is a movement
    mode with a speed -- so it is re-granted two squares faster, and a
    ranger with no fly speed gets nothing, as printed.
    """
    how = c.world.get(c.me, Movement)
    aloft = how.modes.get("fly", 0) if how is not None else 0
    if aloft:
        c.mode("fly", aloft + 2, on=c.me, until=When.ENCOUNTER)


@power(
    "p13698",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_beast_is("cat"),
    requires_text="you must have a cat beast companion",
    trigger=_HIT_ON_AC_OR_REF,
    on=Trigger(AttackRolled, when=_hit_on_ac_or_ref, text=_HIT_ON_AC_OR_REF),
)
def p13698(c: Cast) -> None:
    """Hung off `AttackRolled`, not `Hit`, for two reasons.

    `Hit` carries no `vs`, so "an attack that targets AC or Reflex" cannot
    be asked of it; and by the time a `Hit` exists the defence has already
    been read for the second time, so raising it there changes nothing.

    "If the triggering attack misses you because of this bonus" is then a
    question about the margin: the blow was landing, and four points is
    enough to take it out of reach unless it was a critical.
    """
    ev = c.trigger
    c.bonus(AC, 4, on=c.me, until=When.EONT)
    c.bonus(REF, 4, on=c.me, until=When.EONT)
    if ev is None:
        return
    result = getattr(ev, "result", None)
    critical = bool(result is not None and result.critical)
    if not critical and ev.total < ev.defence + 4:
        c.shift(max(1, c.wis_mod))


@power(
    "p13699",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_beast_is("simian"),
    requires_text="you must have a simian beast companion",
)
def p13699(c: Cast) -> None:
    """The Acrobatics bonus is a skill check and is dropped.

    "Or until your beast companion is killed" is not a duration the engine
    has; the encounter is the longer of the two and is what is held.
    """
    c.mode("climb", c.speed_of(), on=c.me, until=When.ENCOUNTER)


@power(
    "p13700",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=MARTIAL,
    requires=_beast_is("lizard"),
    requires_text="you must have a lizard beast companion",
    trigger=_SHOVED,
    on=Trigger(ForcedMove, when=_shoved_us, text=_SHOVED, window=Window.BEFORE),
)
def p13700(c: Cast) -> None:
    """A free action is answered after the fact, and this has to be before it.

    The agreed distance of a shove is settled between the two windows, and
    it reads the "forced" modifier when it settles -- so the reduction has
    to be standing by then. `once=True` spends it on the triggering move
    rather than shortening every shove for the rest of the turn.
    """
    short = max(1, c.wis_mod)
    for who in (c.me, c.companion()):
        if who is not None:
            c.bonus(
                "forced", short, on=who, until=When.EOT, kind="untyped", once=True
            )


@power(
    "p13701",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_beast_is("serpent"),
    requires_text="you must have a serpent beast companion",
)
def p13701(c: Cast) -> None:
    """"You can shift 2 squares as a move action" is dropped: nothing grants
    an action, and no modifier key sets how far a shift goes. The terrain
    half is the part that can be said, and the extra square it would buy a
    ranger who already had it has nowhere to go either."""
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "p13702",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_beast_is("boar"),
    requires_text="you must have a boar beast companion",
    trigger=_MELEE_DAMAGE,
    on=Trigger(
        DamageRolled,
        when=both(targets_me, by_melee),
        text=_MELEE_DAMAGE,
        window=Window.BEFORE,
    ),
)
def p13702(c: Cast) -> None:
    """Answered on the roll rather than on the blow, because a reduction has
    to happen before the damage lands; `DamageApplied` is past arguing with.

    "If you take no damage from the attack because of this reduction, you
    are not affected by any conditions it would have caused" is dropped --
    nothing undoes a rider an attack has not applied yet.
    """
    c.reduce(max(1, c.level // 2 + c.wis_mod))


@power(
    "p13703",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
    requires=_beast_is("bear"),
    requires_text="you must have a bear beast companion",
)
def p13703(c: Cast) -> None:
    """The stance is the hold; the watcher is what it does, and it dies with
    the stance rather than at the end of a turn."""
    c.stance(label=c.ref)

    def shove(ev: Hit) -> None:
        if ev.attacker != c.me or not by_melee(c.world, c.me, ev):
            return
        if c.may("push it", who=c.me):
            c.push(1, on=ev.target)

    c.watch(Hit, shove, until=When.STANCE, label=c.ref)


@power(
    "p13704",
    level=2,
    cls="ranger",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_beast_is("spider"),
    requires_text="you must have a spider beast companion",
    trigger=_CLIMB_OR_SAVE,
    on=Trigger(SkillCheck, _climbing_athletics, _A_CLIMB_CHECK, window=Window.BEFORE),
)
def p13704(c: Cast) -> None:
    """Half the printed Trigger; the other half names a throw nobody rolls.

    The climb check is a `SkillCheck` and is answered. The save -- against
    being forced into hindering terrain or over a precipice -- is not a
    saving throw this engine has: `Effects.save`, the death save and
    `c.save` are the only three, and none of them is that. So the dropped
    half cannot silently swallow a trigger that would otherwise fire; there
    is no moment at which it happens.

    `Window.BEFORE`, the way `p11049` is: `engine/skills.py` totals the
    modifiers inside its resolve callback, which runs once the interrupt
    window has closed, so a bonus laid here is read by the roll it is
    printed for. `When.EOT` because the modifier has no way to spend itself
    on one check.
    """
    c.bonus("skill:athletics", 4, kind="power", on=c.me, until=When.EOT)


@power(
    "p13705",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_beast_is("wolf"),
    requires_text="you must have a wolf beast companion",
    trigger=_MELEE_DAMAGE,
    on=Trigger(DamageApplied, when=both(targets_me, by_melee), text=_MELEE_DAMAGE),
)
def p13705(c: Cast) -> None:
    """The Requirement is positional, so it is asked here rather than in the
    header: the beast has to be standing next to whoever swung.

    "Cannot stand up until it begins a move action not adjacent to your
    beast companion" is a condition on a square, and `c.prone(held=)` takes
    a duration. The prone is applied; the hold on standing is dropped.
    """
    ev = c.trigger
    beast = c.companion()
    if ev is None or beast is None:
        return
    foe = ev.source
    if not c.adjacent_to(beast, foe):
        return
    c.prone(on=foe)


@power(
    "p4381",
    level=2,
    cls="ranger",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(20),
    target=NO_TARGET,
    keywords=MARTIAL,
)
def p4381(c: Cast) -> None:
    """The printed Target is the beast, which is not a target the engine
    picks -- a companion takes no turn and is nobody's enemy or ally in the
    targeting sense -- so it is reached through `c.companion()` instead.

    The bear-or-boar bonus to the save is dropped: no species is knowable.
    """
    beast = c.companion()
    if beast is not None:
        c.save(on=beast)


@power(
    "p4383",
    level=2,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p4383(c: Cast) -> None:
    """Inert by declaration: the whole Effect is a Perception check shared
    between two creatures, and nothing here rolls one or tracks awareness."""
    c.note(f"{c.ref}: you and your beast companion share the better check")
