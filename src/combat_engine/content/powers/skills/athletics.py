"""Athletics, all nine of its skill powers.

`cls` is the skill rather than a class -- see the package docstring. Seven
of the nine are Personal and aim every target-defaulting `Cast` call back
with `on=c.me`; the other two reach a creature in front of them.

Four print a Trigger and all four declare it with `on=`, since `trigger=`
on its own is prose nothing reads. Three of those answer a `SkillCheck`,
which is the event `skills.check` announces around every roll -- the
window it opens before the modifiers are totalled is what lets a free
action add to a check it is answering.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    Ability,
    ActionType,
    Cast,
    Keyword,
    Melee,
    Size,
    Trigger,
    When,
    Window,
    World,
    both,
    by_me,
    by_melee,
    power,
)
from combat_engine.engine.events import Escaped, Miss, SkillCheck
from combat_engine.engine.query import defence, has_running_start, held_by

SKILL = "athletics"

#: The raw-ability key `skills.ability_check` announces a strength check
#: under. Deliberately not a skill name, so no skill key can collide with
#: it -- which is also what makes it askable here.
_STRENGTH_CHECK = f"ability:{Ability.STR.value}"

#: The DC the printed line gives for each size. Medium or smaller is the
#: floor, so only the three large ones need naming.
_LEAP_DC = {Size.LARGE: 20, Size.HUGE: 25, Size.GARGANTUAN: 30}

_FAILED_BADLY = "you fail an athletics check by 5 or more when swimming or climbing"
_WOULD_ROLL_STRENGTH = "you would make a strength check"
_ESCAPING = "you make an escape attempt using athletics"
_MELEE_MISSED = "your melee attack misses its target"


def _failed_a_swim(world: World, me: int, ev: SkillCheck) -> bool:
    """Failed an athletics check by five or more while swimming.

    The margin is readable here because a free action answers in
    `Window.AFTER` and `Bus.emit` runs the resolve callback first, so
    `total` and `success` are settled rather than half-totalled.

    `purpose` is the plain attribute `skills.check` stamps on, and
    `movement.swim` is the one caller that passes it -- so this is narrowed
    to the printed circumstance instead of firing on every failed check.
    """
    return (
        ev.actor == me
        and ev.skill == SKILL
        and getattr(ev, "purpose", "") == "swim"
        and not ev.success
        and ev.dc - ev.total >= 5
    )


def _would_roll_strength(world: World, me: int, ev: SkillCheck) -> bool:
    """A raw strength check this creature is making."""
    return ev.actor == me and ev.skill == _STRENGTH_CHECK


def _escaping_with_athletics(world: World, me: int, ev: SkillCheck) -> bool:
    """An athletics check by a creature something is still holding.

    `escape.attempt` rolls through `skills.check` and stamps no purpose on
    it, so being held is the narrowest thing that tells an escape attempt
    from any other athletics check. The relation is still set at this
    point: it is cleared after the roll and only on a success.
    """
    return ev.actor == me and ev.skill == SKILL and bool(held_by(world, me))


@power(
    "p13690",
    level=2,
    cls=SKILL,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_FAILED_BADLY,
    on=Trigger(SkillCheck, _failed_a_swim, _FAILED_BADLY),
    dropped=("Grid.climb_dc",),
)
def p13690(c: Cast) -> None:
    """Pulls the failure up to exactly four short of the DC.

    `c.boost_check` is the lever rather than a modifier: the failure is
    what is being answered, so there is nothing left to lay a `c.bonus`
    on, and `skills.check` builds its result from the event after the bus
    has finished with it.

    The climbing half is dropped rather than approximated. Nothing in the
    engine rolls an athletics check to climb, because no square carries a
    climb DC to roll against -- `p10699` waits on the same thing -- so
    there is no check of that sort for this row to rescue.
    """
    ev = c.trigger
    c.boost_check(ev.dc - 4 - ev.total)


@power(
    "p9301",
    level=2,
    cls=SKILL,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p9301(c: Cast) -> None:
    """A long jump is the check result divided by ten, or by five off a
    run-up.

    The +5 rides on this one check rather than being laid as a standing
    modifier, so it cannot be collected by a second check in the same turn.

    **Written, and the old note had the rule backwards.** It said *"a jump
    off a run and a jump from standing come to the same distance here, so
    the clause buys nothing"*, which read as though the row was already
    giving the better of the two. It was not. The page (PHB 183, under
    Athletics):

      > *"Running Start: If you move at least 2 squares before making the
      > jump, divide your check result by 5, not 10."*

    So `// 10` is the **standing** jump and was always correct, and the
    missing clause makes the jump *longer* rather than capping it -- this
    row has been short by half for every character who ran at it. The
    page's worked example is the check: a result of 24 clears 4.8 squares
    with a run-up and 2.4 without.

    `query.has_running_start` is the reader and answers the two ways of
    having one -- 2 squares of this turn's walking, or a card granting it.
    The clause that the distance may exceed the character's speed needs
    nothing written, because `c.jump` is paid for by the power and is not
    capped by speed.
    """
    got = c.check(SKILL, bonus=5)
    c.jump(got.total // (5 if has_running_start(c.world, c.me) else 10))


@power(
    "p9302",
    level=2,
    cls=SKILL,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p9302(c: Cast) -> None:
    """No DC is printed, so the check has nothing to beat and the climb
    follows. The roll is still made rather than assumed: a row watching for
    an athletics check has to see this one, and the +5 belongs on it.

    The climb is a mode plus a move at it, which is how every other climb
    in this tree is said -- the speed is granted for the turn because the
    printed distance is not this creature's own.
    """
    far = 2 + c.speed_of()
    if c.check(SKILL, bonus=5):
        c.mode("climb", far, on=c.me, until=When.EOT)
        c.move(far, at="climb")


@power(
    "p11534",
    level=6,
    cls=SKILL,
    usage=ENCOUNTER,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def p11534(c: Cast) -> None:
    """The immunity is laid before the leap, since it is the leap that
    would open the window.

    `c.jump` lands the creature somewhere legal beside what it aimed at --
    it clears bodies for the length of the leap and then settles into the
    nearest square it fits in -- which is the printed "another square
    adjacent to the target".
    """
    victim = c.target
    if victim is None:
        return
    if not c.check(SKILL, _LEAP_DC.get(c.size_of(on=victim), 15)):
        return
    c.no_provoke(from_=victim, on=c.me, until=When.EOT)
    c.jump(1, toward=victim)


@power(
    "p13691",
    level=6,
    cls=SKILL,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger=_WOULD_ROLL_STRENGTH,
    on=Trigger(SkillCheck, _would_roll_strength, _WOULD_ROLL_STRENGTH),
)
def p13691(c: Cast) -> None:
    """The athletics check is rolled for real and stands in for the other.

    A no-action row with a declared Trigger answers in `Window.AFTER`,
    which `Bus.emit` runs after the resolve callback -- so the strength
    check is settled and `c.boost_check` is what decides what it finally
    came to.

    A fresh d20 rather than the face already down, because the printed line
    is that you *make* an athletics check: `c.substitute_check()` is the
    verb two other rows wait on and this one does not need it, since the
    whole substitution is one roll and one adjustment. Rolling announces a
    second `SkillCheck` under the skill key, which this row's own predicate
    cannot match, so it does not answer itself.
    """
    ev = c.trigger
    got = c.check(SKILL)
    c.boost_check(got.total - ev.total)


@power(
    "p16518",
    level=6,
    cls=SKILL,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_ESCAPING,
    on=Trigger(SkillCheck, _escaping_with_athletics, _ESCAPING, window=Window.BEFORE),
)
def p16518(c: Cast) -> None:
    """`Window.BEFORE`, so the bonus can be a real typed modifier.

    `skills.check` totals the modifiers inside its resolve callback, which
    runs after the before-window and before the after-window -- so a bonus
    laid here is read by the check and a power bonus stays a power bonus,
    where `c.boost_check` would have written an untyped number straight
    onto the event and stacked with another power bonus the card does not
    stack with. It is ended on the way out so it cannot pay for a second
    athletics check in the same turn.

    The vulnerability waits on `Escaped` rather than being laid now:
    whether the hold broke is not known until after this window closes,
    and the grabber is named on the event. "To your attacks" is the gate on
    `source`, which the damage context carries.
    """
    held = c.bonus(
        "skill:athletics", c.str_mod, kind="power", on=c.me, until=When.EOT
    )

    def freed(ev: Escaped) -> None:
        c.end_effect(held)
        if ev.actor != c.me or not ev.success:
            return
        c.vulnerable(
            5,
            on=ev.holder,
            until=When.EONT,
            when=lambda ctx: ctx.get("source") == c.me,
        )

    c.watch(Escaped, freed, until=When.EOT)


@power(
    "p9303",
    level=6,
    cls=SKILL,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p9303(c: Cast) -> None:
    """The bonus is laid before the move and ended after it, which is the
    printed "checks you make as part of the move" -- an aquatic board rolls
    a swim check inside `c.move`, and that is the check this pays for.
    Left standing it would also pay for every athletics check later in the
    turn, which the card does not."""
    c.ignores_difficult(on=c.me, until=When.EOT)
    held = c.bonus("skill:athletics", 5, kind="power", on=c.me, until=When.EOT)
    c.move(c.speed_of() + 4)
    c.end_effect(held)


@power(
    "p11535",
    level=10,
    cls=SKILL,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p11535(c: Cast) -> None:
    """The stance is taken first, because taking one drops whatever was
    held before it, and the bonus then runs to `When.STANCE`.

    No keywords: the compendium prints none for this row, and the printed
    Effect naming the stance is what `c.stance()` is written from.
    """
    c.stance()
    c.bonus("speed", 4, kind="power", on=c.me, until=When.STANCE)


@power(
    "p13692",
    level=10,
    cls=SKILL,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_MELEE_MISSED,
    on=Trigger(Miss, both(by_me, by_melee), _MELEE_MISSED),
)
def p13692(c: Cast) -> None:
    """The creature comes off the trigger and not off `c.target`: this row
    has no target of its own, so a bare call would aim at nobody.

    "Equals or exceeds its highest defence" is all four read off the board
    rather than the one the missed attack rolled against, which is what the
    line says.
    """
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    got = c.check(SKILL)
    best = max(defence(c.world, victim, d) for d in (AC, FORT, REF, WILL))
    if got.total < best:
        return
    if c.choose(["prone", "slide"], "knock it down, or slide it a square") == "slide":
        c.slide(1, on=victim)
    else:
        c.prone(on=victim)
