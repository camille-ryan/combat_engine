"""A skill challenge: so many successes before three failures.

The other half of what a published adventure is made of, and the engine had no
notion of one. `engine/skills.py` rolls a check and announces it properly;
nothing counted the results against each other. #791.

## The printed shape, read rather than remembered

`module.COMPLEXITY` holds the table out of the compendium glossary. Complexity
1 to 5 fixes both how many successes are needed and **what mix of DCs the
checks are rolled at** -- four moderate at complexity 1, eight moderate and
four hard at complexity 5.

That mix is the part a first draft gets wrong. Assuming every primary check
rolls at moderate makes a complexity-5 challenge materially easier than the
printed one, and nothing about the result would look suspicious. The hard
checks come **last** here, so the challenge escalates into the part of it where
the party is already carrying failures; once the listed sequence runs out the
final band repeats, because failures mean more checks get rolled than the table
lists.

**Three failures ends it, and that number does not move with complexity.** The
whole tension of the subsystem is in that constant staying put: a longer
challenge is harder, not merely longer.

## Secondary skills, and the measurement that set the default

A **primary** skill is what the challenge is about and rolls at the band the
mix is up to. A **secondary** skill is a way in from an angle and rolls at the
easy DC, once each.

What a successful secondary is *worth* has two printed readings, and the choice
between them is not cosmetic. Counting it as a success was tried first and the
fixture challenge was then won **5 times out of 5, with three of its four
successes coming from easy-DC secondary rolls** -- the party finds its best
secondary, rolls nine levels below the real DC, and the skills the challenge
named first barely come up. Capping each secondary at one use does not fix it:
there are usually three of them and complexity 1 needs four successes.

So the default is `bonus`: a secondary success adds +2 to the next primary
check and the challenge is still decided on its own skills. A module that
plainly means otherwise sets `secondary_grants: "success"`.

## A skill on neither list is refused, not failed

That distinction matters because a model is going to be choosing skills here
(#794). Refusing tells it the move was not available; counting a failure would
let it burn a challenge down by guessing. It is also why `attempt` can return
an `Attempt` that counted nothing -- read `counted`, do not assume.

## Everything rolls through the engine

`table.py` explains why there is a board at all. The consequence here is that
training's +5, a racial bonus, the armour check penalty and a feat answering
`CheckDeclared` are all inside the number before this module sees it. This
module counts. It does no arithmetic on skills.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .dc import dc as dc_for
from .module import SECONDARY_BONUS, Scene
from .table import Table

#: Three, and it does not scale with complexity.
FAILURES = 3


@dataclass(frozen=True)
class Attempt:
    """One roll, and what it did to the tally."""

    slot: int
    cls: str
    skill: str
    band: str
    dc: int
    #: Zero on a refusal, which does not roll -- see `attempt`.
    natural: int = 0
    total: int = 0
    #: The +2 a prior secondary success handed this check, if any.
    carried: int = 0
    success: bool = False
    #: `"success"`, `"failure"`, `"assist"` (a secondary success under
    #: `bonus`), or why it counted for nothing -- `"not a listed skill"`,
    #: `"secondary already used"`, `"over"`.
    counted: str = ""

    @property
    def rolled(self) -> bool:
        return self.counted in ("success", "failure", "assist")

    def __str__(self) -> str:
        mark = {"success": "+", "failure": "-", "assist": ">"}.get(self.counted, ".")
        if not self.rolled:
            return f"{mark} {self.cls:<9} {self.skill:<13} ({self.counted})"
        carry = f" +{self.carried} carried" if self.carried else ""
        return (
            f"{mark} {self.cls:<9} {self.skill:<13} {self.band:<8} "
            f"d20={self.natural:<2} total={self.total:<3} vs {self.dc}{carry}"
        )


@dataclass
class Running:
    """A challenge in progress."""

    scene: Scene
    level: int
    needs: int
    bands: tuple[str, ...] = ()
    successes: int = 0
    failures: int = 0
    #: How many primary checks have been rolled, which is the index into
    #: `bands`. Secondary checks do not advance it -- they are not part of
    #: the printed mix.
    primaries: int = 0
    #: A secondary success waiting to be spent on the next primary check.
    pending_bonus: int = 0
    attempts: list[Attempt] = field(default_factory=list)
    #: Secondary skills already spent, so the once-each cap can be enforced.
    spent: set[str] = field(default_factory=set)

    @property
    def over(self) -> bool:
        return self.successes >= self.needs or self.failures >= FAILURES

    @property
    def won(self) -> bool:
        return self.successes >= self.needs and self.failures < FAILURES

    @property
    def band_now(self) -> str:
        """The DC band the next primary check faces."""
        if not self.bands:
            return "moderate"
        return self.bands[min(self.primaries, len(self.bands) - 1)]

    @property
    def tally(self) -> str:
        return (
            f"{self.successes}/{self.needs} successes, "
            f"{self.failures}/{FAILURES} failures"
        )


def open_challenge(scene: Scene, *, party_level: int = 1) -> Running:
    """Start counting. `scene.level` wins over the party's when it is set."""
    return Running(
        scene=scene,
        level=scene.level or party_level,
        needs=scene.needs,
        bands=scene.bands,
    )


def band_of(run: Running, skill: str) -> str:
    """Which DC a skill would roll against, or `""` if it is not listed."""
    skill = skill.lower()
    if skill in run.scene.primary:
        return run.band_now
    if skill in run.scene.secondary:
        return "easy"
    return ""


def attempt(run: Running, table: Table, slot: int, skill: str) -> Attempt:
    """One character tries one skill. Rolls only if the attempt can count.

    **An attempt that cannot count does not roll.** A refused skill returning a
    rolled d20 would spend a draw from the scene's stream and move every roll
    after it, so two runs differing only in a skill the challenge does not list
    would diverge. That is the reproducibility `replay.py` depends on, one
    level up.
    """
    skill = skill.lower()
    cls = table.party.sheets[slot].cls
    is_primary = skill in run.scene.primary
    is_secondary = skill in run.scene.secondary

    def refuse(why: str) -> Attempt:
        made = Attempt(slot=slot, cls=cls, skill=skill, band="-", dc=0, counted=why)
        run.attempts.append(made)
        return made

    if run.over:
        return refuse("over")
    if not (is_primary or is_secondary):
        return refuse("not a listed skill")
    if is_secondary and skill in run.spent:
        return refuse("secondary already used")

    band = run.band_now if is_primary else "easy"
    target = dc_for(run.level, band)
    carried = run.pending_bonus if is_primary else 0
    rolled = table.check(slot, skill, target - carried if carried else target)

    # **The bonus is applied by lowering the DC, and the total is reported as
    # the roll plus the carry.** `skills.check` takes a `bonus=` of its own,
    # but that one goes into the event before the resolve callback adds the
    # character's modifier -- which is right for a card's bonus and wrong for
    # this, because an assist is not a property of the character. Lowering the
    # target is the same arithmetic with the event left honest.
    total = rolled.total + carried
    success = total >= target

    if is_primary:
        run.primaries += 1
        run.pending_bonus = 0
        counted = "success" if success else "failure"
        if success:
            run.successes += 1
        else:
            run.failures += 1
    elif success:
        run.spent.add(skill)
        if run.scene.secondary_grants == "success":
            run.successes += 1
            counted = "success"
        else:
            run.pending_bonus = SECONDARY_BONUS
            counted = "assist"
    else:
        # A failed secondary costs a failure and does **not** burn the cap.
        # Charging both would make the easier roll the more expensive one.
        run.failures += 1
        counted = "failure"

    made = Attempt(
        slot=slot, cls=cls, skill=skill, band=band, dc=target,
        natural=rolled.natural, total=total, carried=carried,
        success=success, counted=counted,
    )
    run.attempts.append(made)
    return made


#: `(run, table) -> (slot, skill)`. `(-1, "")` gives up.
Chooser = Callable[[Running, Table], tuple[int, str]]


def taking_turns(run: Running, table: Table) -> tuple[int, str]:
    """The default: everybody contributes, each playing to their strength.

    Rotates through the party rather than letting one character roll the whole
    challenge, which is both the printed intent and the more interesting
    reading -- a challenge the rogue solves alone is a skill check with extra
    steps.

    Deterministic, so a seeded run repeats. The model overrides it when there
    is one (#794) and `--no-dm` lives on it.
    """
    order = [i for i in range(len(table.eids)) if not table.party.sheets[i].down]
    if not order:
        return -1, ""
    # Whose turn: fewest rolled attempts, earliest slot first. Counting rolled
    # ones only means a refusal does not cost somebody their turn.
    taken = dict.fromkeys(order, 0)
    for made in run.attempts:
        if made.rolled and made.slot in taken:
            taken[made.slot] += 1
    slot = min(order, key=lambda i: (taken[i], i))

    options: list[tuple[str, str]] = [(s, run.band_now) for s in run.scene.primary]
    # **No second secondary while a +2 is already banked.** The bonus is spent
    # by the next primary check and does not stack, so a chooser that takes the
    # easy roll whenever it has the best margin opens by burning every
    # secondary it has for one usable +2 -- measured, three assists rolled and
    # two thrown away, in two of the first three seeds. Under
    # `secondary_grants: "success"` there is nothing to waste and the gate does
    # not apply.
    #
    # **Unless this character has nothing to offer on a primary.** The gate
    # above, applied flatly, forced a wizard to roll athletics at -3 rather
    # than help from the side, which is neither good play nor what the printed
    # rule wants from "everybody participates".
    hopeless = all(
        table.modifier(slot, s) < dc_for(run.level, run.band_now) - 10
        for s in run.scene.primary
    ) if run.scene.primary else True
    may_assist = (
        run.scene.secondary_grants == "success" or not run.pending_bonus or hopeless
    )
    if may_assist:
        options += [(s, "easy") for s in run.scene.secondary if s not in run.spent]
    if not options:
        return -1, ""

    def margin(pair: tuple[str, str]) -> tuple[int, int, int]:
        skill, band = pair
        edge = table.modifier(slot, skill) - dc_for(run.level, band)
        # Primaries first on a tie: they are what the challenge counts, and a
        # secondary only ever assists. Without this the chooser spends its
        # secondaries early for a +2 it may never get to use.
        return (edge, 1 if skill in run.scene.primary else 0, -options.index(pair))

    return slot, max(options, key=margin)[0]


def play(
    scene: Scene, table: Table, *, party_level: int = 1,
    choose: Chooser | None = None, limit: int = 40,
) -> Running:
    """Run a whole challenge and return the finished tally.

    `limit` is a backstop against a chooser that keeps naming refused skills --
    a model can do that, and a loop that never ends is a worse failure than a
    challenge that stops early. Hitting it is the caller's to report rather
    than swallow.
    """
    run = open_challenge(scene, party_level=party_level)
    picker = choose or taking_turns
    for _ in range(limit):
        if run.over:
            break
        slot, skill = picker(run, table)
        if slot < 0 or not skill:
            break
        attempt(run, table, slot, skill)
    return run
