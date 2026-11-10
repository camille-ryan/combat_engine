"""Skill powers for insight: ten utilities at levels 2, 6 and 10.

What the group has in common is **answering a roll that is already on the
table**: four of the ten are immediate interrupts and two move a social
check off the skill it was printed for, so most of this file reaches for
the event rather than for the board. Two levers do all of it -- the skill
a check is about to be rolled as, answered on `CheckDeclared` through
`c.substitute_check`, and
`AttackResult.target_defence`, re-read by `resolve.attack` after the
`AttackRolled` window. Only the second is window-sensitive, which is why
one trigger here still names a window explicitly; `CheckDeclared` precedes
the d20, so there is no too-late window for the first.

`p9299`'s card heads itself with a **different skill** from the one the
database files it under. `cls` follows the database, since that is what
`chargen.loadout` selects on; named in the report.

`cls` is the skill and not a class, which is the module's own convention;
see `__init__.py`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    YOU_AND_EACH_ALLY,
    Cast,
    CheckDeclared,
    CloseBurst,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    When,
    Window,
    get,
    my_check,
    power,
)
from combat_engine.engine.events import AttackRolled, Hit, MoveStart, SkillCheck
from combat_engine.engine.query import allies, distance_between, team, unseen_by

#: The three checks the level-6 reroll names, and the three the level-10
#: burst hands a bonus to. Separate from the blanket `skill` key on purpose:
#: `p9325` prints three numbers on three named skills, not one on any check.
_SOCIAL = frozenset({"bluff", "diplomacy", "intimidate"})

#: The `Range.kind` words for an attack the printed trigger calls "an area
#: or a close attack". Read off the row rather than off the event, since no
#: attack event carries a shape -- `by_melee` looks the reach up the same
#: way, and a `wall` is an area template like the rest.
_AREA = frozenset({"area_burst", "close_burst", "close_blast", "wall"})

#: What `MoveStart.kind_` holds for movement a creature chose to make.
#: `movement.forced` announces `ForcedMove` and never this event, so a push
#: cannot reach here at all -- the list is the positive half anyway, because
#: `"place"` is a flyer being set down and is nobody's decision.
_WILLING = frozenset({"walk", "charge", "run", "shift", "teleport"})

_INTIMIDATING = "you would make an intimidate check against a creature"


def _ally_failed_a_social_check(world: Any, me: int, ev: Any) -> bool:
    """An ally within 5 that has just failed one of the three named checks.

    `my_check` is the wrong half here -- it asks whether the check is
    *mine* -- and `SkillCheck.actor` is the roller, so the side and the
    distance are asked of that field and not of `target`, which on a social
    check is whoever was being talked at.

    `success` is settled inside `skills.check`'s resolve callback, which
    runs once the interrupt window has closed, so this can only be true in
    the after window. That is why the row declares one.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if who not in allies(world, me):
        return False
    if getattr(ev, "skill", "") not in _SOCIAL:
        return False
    if getattr(ev, "success", False):
        return False
    return distance_between(world, me, who) <= 5


def _caught_in_an_area(world: Any, me: int, ev: Any) -> bool:
    """A visible enemy rolling an area or close attack that includes me.

    `AttackRolled.among` is every creature the one use is aimed at, set at
    the emission rather than declared on the event, so "includes you as a
    target" is a membership test and not an `attacker`/`target` comparison.
    """
    attacker = getattr(ev, "attacker", None)
    if attacker is None or attacker == me:
        return False
    if team(world, attacker) is team(world, me):
        return False
    if me not in getattr(ev, "among", ()):
        return False
    if unseen_by(world, me, attacker):
        return False
    row = get(getattr(ev, "power", ""))
    return row is not None and row.reach.kind in _AREA


def _enemy_moving_willingly(world: Any, me: int, ev: Any) -> bool:
    """An enemy within 5 squares starting a move of its own accord."""
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if team(world, who) is team(world, me):
        return False
    if getattr(ev, "kind_", "") not in _WILLING:
        return False
    return distance_between(world, me, who) <= 5


@power(
    "p12828",
    level=2,
    cls="insight",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    trigger=_INTIMIDATING,
    on=Trigger(CheckDeclared, my_check("intimidate"), _INTIMIDATING),
    narrative=("skill:intimidate",),
)
def p12828(c: Cast) -> None:
    """*"You make an Insight check in place of an Intimidate check."*

    **`CheckDeclared`, and no `window=` any more** -- two separate reasons,
    and the second one was a latent bug. The event precedes the d20
    altogether, so there is no window in which the swap is too late; and
    `ActionType.STANDARD` now has a `WINDOW_OF` entry, where before it had
    none and this row's own `window=Window.BEFORE` was the only thing
    making it answerable at all.

    That was not belt-and-braces: `_watched` dropped the subscription for a
    row whose action had no entry, so this one was being offered through
    **another row's** subscription of the same pair. Re-pointing those rows
    to `CheckDeclared` took the pair away and this went from silent to
    never-offered. The dependency was on nothing it declared and no
    instrument could see it. #1215.

    The swap is also **said** now: a hand-rolled `ev.skill = x` announces
    nothing, which is why this was carried silent -- not for being wrong
    but for being unobservable. #1209, #1212.

    No `instead_of`: the trigger already narrows to the one check the card
    names.

    `narrative=`: the rest of the card is the standard intimidate rules
    restated -- a +5 or +10 to Will depending on whether the creature is
    unfriendly or hostile -- and no board carries a creature's attitude at
    all, so there is no circumstance for the number to attach to. The
    target line's "shares a language with you" is the same circumstance:
    nothing asks what two creatures have in common to speak.
    """
    c.substitute_check("insight")


@power(
    "p16507",
    level=2,
    cls="insight",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p16507(c: Cast) -> None:
    """"Choose one creature within 10 squares" is a real choice, so it goes
    through `c.choose` rather than taking the nearest. Enemies are offered
    first: a headless run takes the first option, and the grant is worth
    nothing aimed at an ally.

    "You learn the vulnerabilities of that creature" is not a dropped
    clause. `c.vulnerabilities(on=)` already answers it for anybody who
    asks, and every decider on this board reads the same world, so there is
    no knowledge to hand over and nothing changes.
    """
    pool = [*c.within(10, side="enemy"), *c.within(10, side="ally")]
    who = c.choose(pool, "whose weaknesses to read")
    if who is None:
        return
    c.grants_advantage(on=who, to="me", until=When.EONT)


@power(
    "p9323",
    level=2,
    cls="insight",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def p9323(c: Cast) -> None:
    """A real opposed pair rather than a check against a passive score: the
    card says the target rolls, as a free action, so `c.check(who=)` rolls
    it and the two totals are compared. The printed order is kept -- mine
    first -- which is why neither call carries a dc and the comparison is
    made by hand.

    A tie goes to the insight check, which is this file's one judgement
    call here; the card says "opposed by" and names no tiebreak.
    """
    foe = c.target
    if foe is None:
        return
    mine = c.check("insight", against=foe)
    theirs = c.check("bluff", who=foe, against=c.me)
    if mine.total >= theirs.total:
        c.grants_advantage(on=foe, to="me", until=When.EONT)


@power(
    "p11554",
    level=6,
    cls="insight",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    trigger="an ally fails a bluff, a diplomacy or an intimidate check",
    on=Trigger(
        SkillCheck,
        _ally_failed_a_social_check,
        "an ally fails a bluff, a diplomacy or an intimidate check",
        window=Window.AFTER,
    ),
)
def p11554(c: Cast) -> None:
    """"Uses either result" is `keep="best"`, and `c.reroll_check` reads the
    roller off the triggering event rather than off `c.me`, so the ally's
    own check is the one rerolled and announced.

    `window=Window.AFTER` against an interrupt's own `Window.BEFORE`: the
    printed trigger is a **failure**, and `success` is not filled until
    `skills.check`'s resolve callback has run. Declared in the before
    window the predicate would be true of every ally's social check,
    failing or not.
    """
    c.reroll_check(keep="best")


@power(
    "p11555",
    level=6,
    cls="insight",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p11555(c: Cast) -> None:
    """The wide sentence, which is `c.no_advantage` and not
    `c.cannot_be_flanked`: the card names no branch, so being flanked,
    dazed, unseen or granting it outright are all shut.
    """
    c.no_advantage(on=c.me, until=When.EONT)


@power(
    "p16497",
    level=6,
    cls="insight",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    dropped=("Power.body_alt",),
)
def p16497(c: Cast) -> None:
    """Two +4s, and the qualifier belongs to the second only: the card
    repeats "a +4 power bonus to" in front of each half, so "against charm
    and psychic effects" narrows the saving throws and not the Will. Taken
    as shared it would be a weaker row than the page.

    The saving-throw half is gated on the save context's `keywords`, which
    `Cast.save` fills from the effect being shaken off -- the same gate
    `c.save_early`'s three rows read.

    `dropped=`: the Special line is a **second printed mode** of one card --
    no action, at the start of your turn, available only while dominated,
    expending the row to roll one saving throw instead of laying these
    bonuses. `Power.action` and the body hold one mode each, and `on=`
    would replace the minor-action use rather than sit beside it, so the
    alternative has nowhere to go. `c.expend_row` and `c.save` are both
    already here; what is missing is the second mode.
    """
    c.bonus(WILL, 4, on=c.me, kind="power", until=When.EONT)
    c.bonus(
        "save", 4, on=c.me, kind="power", until=When.EONT,
        when=lambda ctx: bool(
            {Keyword.CHARM, Keyword.PSYCHIC} & set(ctx.get("keywords") or ())
        ),
    )


@power(
    "p9299",
    level=6,
    cls="insight",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="a creature you can see rolls an area or close attack that includes you",
    on=Trigger(
        AttackRolled,
        _caught_in_an_area,
        "a creature you can see rolls an area or close attack that includes you",
    ),
)
def p9299(c: Cast) -> None:
    """Laid as real modifiers rather than written onto the result, which is
    the opposite of `p11580` below and for a reason: `resolve.attack`
    re-reads the defence *after* the `AttackRolled` window closes, so a
    modifier laid here is picked up for this blow -- and overwrites
    anything a row wrote onto `target_defence` by hand.

    "Against it" is the gate on the attack's own power ref, which is what
    the defence context carries. `When.EOT` rather than `EONT` because the
    whole of one area attack resolves inside the turn that threw it.

    Each target of a burst is a separate roll, so the allies' +2s are in
    place before their own rolls are judged -- which is what makes one
    interrupt cover the whole blast.
    """
    ev = c.trigger
    if ev is None:
        return
    ref = getattr(ev, "power", "")
    mine = {c.me, *c.allies()}
    for who in getattr(ev, "among", ()):
        if who not in mine:
            continue
        for defence in (AC, FORT, REF, WILL):
            c.bonus(
                defence, 2, on=who, kind="power", until=When.EOT,
                when=lambda ctx, r=ref: ctx.get("power") == r,
            )


@power(
    "p9324",
    level=6,
    cls="insight",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy within 5 squares of you moves willingly",
    on=Trigger(
        MoveStart,
        _enemy_moving_willingly,
        "an enemy within 5 squares of you moves willingly",
    ),
)
def p9324(c: Cast) -> None:
    """`MoveStart` and not `MoveEnd`: the interrupt is printed as going
    *before* the enemy's step, and the distance in the trigger is measured
    from where it is standing now.

    Half the speed, rounded down, with a floor of one square -- a creature
    whose speed is 1 still gets the step the card gives it.
    """
    c.shift(max(1, c.speed_of() // 2))


@power(
    "p11580",
    level=10,
    cls="insight",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="you are hit by a creature",
    on=Trigger(Hit, lambda world, me, ev: getattr(ev, "target", None) == me,
               "you are hit by a creature"),
)
def p11580(c: Cast) -> None:
    """The +2 goes onto the comparison and not into `Mods`, which is
    `p12245`'s shape and the only one that works on a `Hit`: by the time
    this event is announced `resolve.attack` has re-read the defence and
    settled the outcome, so a laid modifier is read by nothing. Raising the
    number the blow was measured against and re-settling turns a hit that
    cleared by one into a `Miss`, announced as one, with every rider on the
    hit skipped.

    "All defenses" is one number here because one attack is rolled against
    one defence, so the other three have nothing to do.

    `c.settle_attack` rather than writing `hit` by hand: it is the one
    place the automatic hit on a natural 20 and the crit range are both
    applied, and the three rows that wrote this out each lost a different
    one of them.
    """
    ev = c.trigger
    result = getattr(ev, "result", None) if ev is not None else None
    if result is None:
        return
    result.target_defence += 2
    c.settle_attack()


@power(
    "p9325",
    level=10,
    cls="insight",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=YOU_AND_EACH_ALLY,
)
def p9325(c: Cast) -> None:
    """Three `skill:<name>` keys rather than one gated effect on the
    blanket `skill` key: the card prints three skills and `skills.modifier`
    reads both forms, so three effects is the shape that says "these three"
    without also paying on a check nothing names.

    "A bonus" with no type word in front of it is untyped, so `kind=` is
    left off.
    """
    for skill in sorted(_SOCIAL):
        c.bonus(f"skill:{skill}", c.wis_mod, until=When.EONT)
