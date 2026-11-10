"""Skill powers for `cls="streetwise"`: the opening rolls, and built-up
ground.

Seven rows, levels 2/6/10. Three of the seven print the same shape -- *"you
make a Streetwise check in place of the X check"* -- and the engine has no
way to put one skill in another's place: `skills.check` is handed the skill
by its caller and `CheckDeclared` is a plain `Event`, so there is nothing to
answer. Two of those three are narrowed to a settlement or an urban
environment on top of that, and `World.terrain` carries no word for either.

What is left is real and is written: the two initiative rows move creatures
in the order with `c.initiative`, which is the only thing that can -- a
bonus laid with `c.bonus` is read before the d20 and these answer a roll
that has already happened.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    MOVE,
    PERSONAL,
    SELF,
    YOU_AND_EACH_ALLY,
    Cast,
    CloseBurst,
    Cover,
    InitiativeRolled,
    Trigger,
    When,
    about_me,
    power,
)
from combat_engine.engine.ecs import World
from combat_engine.engine.events import MoveEnd
from combat_engine.engine.grid import Square, blast, spread
from combat_engine.engine.query import cover_between, enemies, squares


def _covered_against(world: World, me: int) -> list[int]:
    """Whoever this creature has cover from, right now.

    `ranged=True` because a creature's body is only ever cover against a
    shot -- `cover_between`'s `bodies` set is empty for a melee swing, so
    without it the only answer is terrain.
    """
    return [
        foe
        for foe in enemies(world, me)
        if cover_between(world, foe, me, ranged=True) is not Cover.NONE
    ]


def _move_ended_with_cover(world: World, me: int, ev: Any) -> bool:
    """"You end a move action and have cover against at least one
    creature." `MoveEnd` is the event that fires once the stepping is
    finished, which is when the printed sentence is true."""
    if getattr(ev, "actor", None) != me:
        return False
    return bool(_covered_against(world, me))


def _aim_beside(c: Cast, mine: frozenset[Square]) -> Square | None:
    """A square to point a close blast at: whoever is chasing, or anywhere.

    `grid.blast` snaps to the nearest legal placement, so handing it an
    enemy's own square lays the ground between the caster and whoever is
    chasing, which is what the card is for. With nobody behind, any
    adjacent square will do.
    """
    foes = [
        (c.distance(f), sorted(squares(c.world, f))[0])
        for f in c.enemies()
        if squares(c.world, f)
    ]
    if foes:
        return min(foes)[1]
    ring = sorted(spread(mine, 1) - mine)
    return ring[0] if ring else None


@power(
    "p11596",
    level=2,
    cls="streetwise",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you roll initiative and dislike the result",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p11596(c: Cast) -> None:
    """"Use either result" is arithmetic on the count, not a reroll.

    `c.initiative(0)` reads the number back without moving it -- the whole
    of `adjust_initiative` is `rolled += amount` and a re-splice -- so the
    two candidates can be compared and the better one taken as a
    difference. A `c.reroll_initiative` would throw the first roll away,
    which is the one thing the card does not do."""
    standing = c.initiative(0, on=c.me)
    rolled = c.check("streetwise")
    if rolled.total > standing:
        c.initiative(rolled.total - standing, on=c.me)


@power(
    "p12827",
    level=2,
    cls="streetwise",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def p12827(c: Cast) -> None:
    """Inert on the **circumstance**, which is a claim about the card.

    Both halves of the printed trigger are things a board is not: a
    settlement, and a Streetwise check already succeeded in it. The row is
    declared inert rather than left waiting on a check substitution no
    board would ever reach -- unlike `p11597`, whose three skills really are
    rolled in fights."""


@power(
    "p16508",
    level=2,
    cls="streetwise",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(5),
    target=YOU_AND_EACH_ALLY,
    trigger="you and your allies roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p16508(c: Cast) -> None:
    """The +2 goes through `c.initiative`, which is what moves a creature in
    the order -- and the printed type word cannot ride with it, because the
    count is a component rather than a modifier anything sums. `f1031` and
    `f1664` carry the same note.

    "Combat advantage against all enemies" is `c.gains_advantage` with a
    gate that is always true, which is what the card's own blanket says."""
    c.initiative(2, on=c.target)
    c.gains_advantage(lambda ctx: True, on=c.target, until=When.EOTNT)


@power(
    "p9341",
    level=2,
    cls="streetwise",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you end a move action and have cover against at least one"
    " creature",
    on=Trigger(MoveEnd, _move_ended_with_cover, "you end a move action"),
)
def p9341(c: Cast) -> None:
    """One roll, against the hardest pair of eyes, extended to the printed
    set by hand.

    `c.hide(check=True)` takes a single watcher and makes the check against
    its passive Perception, which is the printed arrangement -- so the
    hardest of the covered creatures is rolled against and the rest are laid
    with `c.invisible` off that one success. Calling it per creature would
    be a check each, and the card prints one.

    **The skill is a parameter now.** `_stealth_hide` rolled
    `c.check("stealth", ...)` outright, so the card's whole benefit -- the
    substitution -- was unsayable and the row was marked for it.
    `c.hide(skill=)` threads it to the roll and changes nothing else: the
    passive-Perception DC, the movement penalty and its `"stealth:moved"`
    waiver key all describe the circumstance rather than the roll, so a
    creature that ran is still easier to spot whichever skill it uses."""
    covered = _covered_against(c.world, c.me)
    if not covered:
        return
    hardest = max(covered, key=lambda f: c.passive("perception", of=f))
    if c.hide(from_=hardest, check=True, skill="streetwise") is None:
        return
    for foe in covered:
        if foe != hardest:
            c.invisible(to=foe, on=c.me, until=When.ENCOUNTER)


@power(
    "p11597",
    level=6,
    cls="streetwise",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    todo=("story.terrain_words",),
)
def p11597(c: Cast) -> None:
    """One gap now, and it is the place rather than the substitution.

    The substitution half is written: `c.substitute_check` answers
    `CheckDeclared` and `skills.check` reads the skill back off it, so
    streetwise' modifier is what gets rolled. #1209.

    What is left is the printed narrowing to an urban environment, which
    `c.terrain` has no word for and no board declares -- so the gate would
    be a word nothing sets, which is indistinguishable from a correct gate
    for as long as `World.terrain` stays empty (#539). The substitution is
    written out below the marker rather than left unsaid, so what lands
    when the word exists is one line and not a re-reading of the card.
    """
    # c.substitute_check("streetwise",
    #                    instead_of="acrobatics,athletics,perception")


@power(
    "p9342",
    level=6,
    cls="streetwise",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    requires_text="you must be in an urban environment",
    dropped=("story.terrain_words",),
)
def p9342(c: Cast) -> None:
    """The move and the ground both play; the Requirement does not.

    "At one point during the movement" is taken as the end of it, which is
    where the caster is when the zone is laid and the only point a body can
    reach -- `c.move` returns once the stepping is done. The blast is aimed
    at the nearest pursuer so the rough ground lands between it and the
    caster, which is `grid.blast`'s snap-to-nearest-placement doing the
    geometry rather than a compass direction being picked here.

    Dropped: the urban Requirement. It is **not** written as a `requires=`
    gate, because `c.terrain` raises on a word it does not know and the
    vocabulary has no word for a built-up place -- so a gate here would be
    a crash
    rather than a refusal."""
    c.move(c.speed_of())
    mine = squares(c.world, c.me)
    if not mine:
        return
    aim = _aim_beside(c, mine)
    if aim is None:
        return
    c.zone(blast(mine, 3, aim), difficult=True, until=When.ENCOUNTER)


@power(
    "p9343",
    level=10,
    cls="streetwise",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p9343(c: Cast) -> None:
    """`c.may_enter` is the mover's own permission and is handed back as
    soon as the shift is over -- the card gives it "during this movement",
    and the shortest duration `When` offers is still the whole turn.

    **The step off a shared square is a correction, not a printed clause.**
    `movement._clear` consults `may_enter` on every square of the route
    *including the last*, which `movement.shift`'s own docstring says is a
    melding power's business -- so this shift ended on top of an enemy on
    every seed driven. The permission is surrendered first, so the extra
    square can only be a free one. See the batch report."""
    through = c.may_enter(side="enemy", on=c.me, until=When.EOT)
    c.shift(c.speed_of())
    c.end_effect(through, why="the move is over")
    if len(c.in_squares([c.here])) > 1:
        c.shift(1)
