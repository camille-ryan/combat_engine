"""A skill challenge: so many successes before three failures.

The other half of what a published adventure is made of, and the engine had no
notion of one. `engine/skills.py` rolls a check and announces it properly;
nothing counted the results against each other. #791.

## The printed shape, read rather than remembered

`module.complexity_table()` reads the table out of `rules_complexity`,
which the compendium glossary was imported into (#1001, #1049). Complexity
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
check and the challenge is still decided on its own skills.

**The `success` reading is gone**, retired in `b2d63e85` -- this paragraph
used to end "a module that plainly means otherwise sets
`secondary_grants: \"success\"`", and such a module is now refused. What a
module writes instead is `grants` on the skill itself, from DMG2's five
printed effects: `bonus`, `cancel`, `reroll`, `open`, `raise_cap`. #984.

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

from combat_engine.dc import BANDS
from combat_engine.dc import dc as dc_for
from combat_engine.engine.events import SkillChallengeEnded

from . import tension
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
    #: How many characters rolled, how many beat the DC, and how many had
    #: to -- for a group check, where `natural` and `total` are one
    #: character's and say nothing about the party's. Zero on an ordinary
    #: check.
    #:
    #: Recorded for the reason `rerolled` is: a group check that reports a
    #: single d20 is unobservable **as** a group check, so a driver would
    #: have to count `table.check` calls to see it happened and a player
    #: would be shown one roll out of five. #984.
    rolled_by: int = 0
    beat_it: int = 0
    needed: int = 0
    #: True when a banked `reroll` was spent on this check. Recorded rather
    #: than left implicit: a reroll that leaves no trace is an effect
    #: nothing can observe, so a driver would have to diff `run.rerolls`
    #: to see it and a player would never be told it happened.
    rerolled: bool = False
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
        if self.rolled_by:
            mark = {"success": "+", "failure": "-"}.get(self.counted, ".")
            return (
                f"{mark} {'the party':<9} {self.skill:<13} {self.band:<8} "
                f"{self.beat_it} of {self.rolled_by} beat {self.dc} "
                f"(needed {self.needed})"
            )
        carry = f" +{self.carried} carried" if self.carried else ""
        again = " (rerolled)" if self.rerolled else ""
        return (
            f"{mark} {self.cls:<9} {self.skill:<13} {self.band:<8} "
            f"d20={self.natural:<2} total={self.total:<3} vs {self.dc}"
            f"{carry}{again}"
        )


@dataclass
class Running:
    """A challenge in progress."""

    scene: Scene
    level: int
    needs: int
    bands: tuple[str, ...] = ()
    #: The campaign's recent decided outcomes, for `tension.band`. Empty
    #: for a challenge run outside a campaign, which pitches nothing.
    record: list[str] = field(default_factory=list)
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
    #: Successes each primary skill has contributed, for `Scene.cap_for`.
    #: DMG2's ground rule 2 is entirely about the bottleneck this stops:
    #: *"if only one skill does the heavy lifting for the challenge, you
    #: need to rethink the challenge."* #984.
    won_with: dict[str, int] = field(default_factory=dict)
    #: Skills a secondary's `open` effect has made usable as primaries.
    #: DMG2: *"open up the use of another skill in the challenge."* Kept
    #: here rather than mutating `scene.primary`, because a `Scene` is
    #: frozen and is the module's statement -- what the party unlocked is a
    #: fact about this run. #984.
    opened: set[str] = field(default_factory=set)
    #: Extra successes a skill may contribute, over `Scene.cap_for`, from a
    #: secondary's `raise_cap`. DMG2's fifth printed effect.
    cap_bonus: dict[str, int] = field(default_factory=dict)
    #: Rerolls banked by a secondary's `reroll` effect, each spent on the
    #: next primary check that would otherwise fail.
    rerolls: int = 0

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


def open_challenge(scene: Scene, *, party_level: int = 1,
                   record: list[str] | None = None) -> Running:
    """Start counting. `scene.level` wins over the party's when it is set.

    `record` is the campaign's recent decided outcomes, which pitch the
    primary band one rung either way. Omitted outside a campaign, where
    there is no record and nothing to react to.
    """
    return Running(
        scene=scene,
        level=scene.level or party_level,
        needs=scene.needs,
        bands=scene.bands,
        record=list(record or []),
    )


def band_of(run: Running, skill: str) -> str:
    """Which DC a skill would roll against, or `""` if it is not listed.

    **`run.opened` counts as primary**, which is what DMG2's *"open up the
    use of another skill in the challenge"* buys: the skill was not listed
    and now scores, at the band the challenge has reached. Read off the run
    rather than the scene because a `Scene` is frozen and states what the
    module wrote; what the party unlocked belongs to this playthrough. #984.
    """
    skill = skill.lower()
    if skill in run.scene.primary or skill in run.opened:
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
    # An `open`ed skill is a primary for the rest of the challenge -- see
    # `band_of`, which has to agree with this or a skill would roll at a band
    # it cannot score at.
    is_primary = skill in run.scene.primary or skill in run.opened
    is_secondary = skill in run.scene.secondary and not is_primary

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
    # **A group check may not come through here.** Rolled per character it
    # would score the challenge on *one* character's die, which is strictly
    # easier than the printed rule and indistinguishable in the output from
    # a legitimate success. `group_attempt` is the door. #984.
    if is_primary and run.scene.group_of(skill):
        return refuse("a group check, not one character's")
    # **A primary that has given all it can.** Refused before the roll,
    # like every other refusal here, so a capped skill does not spend a
    # draw from the scene's stream and move every roll after it.
    # `cap_bonus` is DMG2's fifth printed effect -- a secondary that raises
    # how much a primary may contribute. Added to the module's figure rather
    # than replacing it, and only when there is a cap to raise: lifting an
    # uncapped skill is meaningless and would read as a cap of 1.
    cap = run.scene.cap_for(skill) if is_primary else 0
    if cap:
        cap += run.cap_bonus.get(skill, 0)
    if cap and run.won_with.get(skill, 0) >= cap:
        return refuse("skill capped")

    band = run.band_now if is_primary else "easy"
    # **The reactive band, and only on a primary check.** A secondary is
    # already pitched easy by design, so moving it would turn the helping
    # roll into the challenge. The module's own complexity still decides
    # the sequence of bands -- this moves which rung it lands on, never how
    # many rungs there are. #977.
    band = tension.band(band, run.record, BANDS) if is_primary else band
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

    # **A banked reroll is spent on a primary that would otherwise fail**, and
    # the second roll stands whatever it is -- DMG2: *"allow a character to
    # reroll another skill check"*, which is a reroll and not a best-of-two
    # with a floor. Spent before the tally so the failure never lands.
    #
    # Rolled through `table.check` again rather than re-reading the first
    # roll, because a reroll is a new die: the carry is already inside
    # `target` and the band has not moved, so the second attempt faces
    # exactly the same number as the first.
    rerolled = False
    if is_primary and not success and run.rerolls:
        run.rerolls -= 1
        rerolled = True
        rolled = table.check(slot, skill, target - carried if carried else target)
        total = rolled.total + carried
        success = total >= target

    if is_primary:
        run.primaries += 1
        run.pending_bonus = 0
        counted = "success" if success else "failure"
        if success:
            run.successes += 1
            run.won_with[skill] = run.won_with.get(skill, 0) + 1
        else:
            run.failures += 1
    elif success:
        # **A secondary assists and never scores.** The `success` reading
        # was retired on Camille's call -- see `module.SECONDARY_GRANTS`
        # for the three reasons -- so there is one branch here where there
        # were two.
        #
        # **Which assistance, from DMG2's five.** `grants_of` answers
        # `("bonus", "")` for every converted challenge, so this reads as
        # it always did until a module writes a `grants`. #984.
        run.spent.add(skill)
        effect, aimed = run.scene.grants_of(skill)
        if effect == "cancel":
            # *"Cancel out a failure with another skill."* Floored at zero:
            # a challenge with no failures yet has none to take back, and a
            # negative tally would make the next real failure free.
            run.failures = max(0, run.failures - 1)
        elif effect == "reroll":
            run.rerolls += 1
        elif effect == "open":
            run.opened.add(aimed)
        elif effect == "raise_cap":
            run.cap_bonus[aimed] = run.cap_bonus.get(aimed, 0) + 1
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
        success=success, rerolled=rerolled, counted=counted,
    )
    run.attempts.append(made)
    # **Announced here rather than in `play`, because `play` is not the only
    # driver.** `dm.py` runs its own loop over `attempt` when a model is
    # choosing, so an emit in `play`'s tail would fire for a scripted
    # challenge and stay silent for a played one -- two answers to one
    # question, which is the shape `#948` already paid for once.
    #
    # The transition needs no `was_over`: this function refuses outright
    # when `run.over` is already true, so reaching the tally above means it
    # was live, and `run.over` now means it ended on *this* attempt.
    if run.over:
        table.world.bus.emit(
            SkillChallengeEnded(scene=run.scene.id, won=run.won)
        )
    return made


def needed_of(threshold: str, standing: int) -> int:
    """How many characters have to beat the DC, for `half` or `one`.

    `half` rounds **up** -- "at least half" of five is three, not two -- and
    is floored at one so a party of none cannot score by rolling nothing.
    """
    if threshold == "one":
        return 1
    return max(1, -(-standing // 2))


def group_attempt(run: Running, table: Table, skill: str) -> Attempt:
    """Everybody rolls one skill; the party scores if enough of them beat it.

    DMG2's group check. A **separate door from `attempt`** rather than a
    parameter on it, because every other move here is per character --
    `attempt` takes a slot, `Table.check` rolls for one index -- and a group
    check has no slot. A slot argument that is ignored is the one-symbol-two-
    needs shape the root `CLAUDE.md` forbids.

    **It refuses a skill the module did not mark**, which is the other half
    of `attempt`'s refusal: without it a chooser could make any primary
    party-wide, which is strictly harder at `half` and strictly easier at
    `one`. Neither is what the module wrote.

    The party scores **one** success or one failure however many dice are
    thrown -- that is what the threshold is for -- so the tally, the cap and
    a carried `pending_bonus` all move exactly as they do for a single
    check.
    """
    skill = skill.lower()
    threshold = run.scene.group_of(skill)

    def refuse(why: str) -> Attempt:
        made = Attempt(slot=-1, cls="the party", skill=skill, band="-",
                       dc=0, counted=why)
        run.attempts.append(made)
        return made

    if run.over:
        return refuse("over")
    if not threshold:
        return refuse("not a group check")
    cap = run.scene.cap_for(skill)
    if cap:
        cap += run.cap_bonus.get(skill, 0)
    if cap and run.won_with.get(skill, 0) >= cap:
        return refuse("skill capped")

    band = tension.band(run.band_now, run.record, BANDS)
    carried = run.pending_bonus
    target = dc_for(run.level, band)
    # Only the standing characters roll, for #808's reason: a character at or
    # below 0 hit points is not participating in the scene.
    rolling = [i for i, sheet in enumerate(table.party.sheets) if not sheet.down]
    need = needed_of(threshold, len(rolling))
    beat = sum(
        1 for i in rolling
        if table.check(i, skill, target - carried if carried else target).total
        + carried >= target
    )
    success = beat >= need

    run.primaries += 1
    run.pending_bonus = 0
    if success:
        run.successes += 1
        run.won_with[skill] = run.won_with.get(skill, 0) + 1
    else:
        run.failures += 1

    made = Attempt(
        slot=-1, cls="the party", skill=skill, band=band, dc=target,
        carried=carried, success=success,
        rolled_by=len(rolling), beat_it=beat, needed=need,
        counted="success" if success else "failure",
    )
    run.attempts.append(made)
    if run.over:
        table.world.bus.emit(
            SkillChallengeEnded(scene=run.scene.id, won=run.won)
        )
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

    # **A capped skill is not an option.** The chooser would otherwise
    # keep naming one that can no longer count, burning `play`'s attempt
    # limit without progressing -- measured at 33 refusals in one
    # challenge, which turned a win into a loss. A cap that makes the
    # default chooser spin is a cap that broke the challenge. #984.
    options: list[tuple[str, str]] = [
        (s, run.band_now) for s in run.scene.primary
        if not (cap := run.scene.cap_for(s))
        or run.won_with.get(s, 0) < cap
    ]
    if not options:
        # Every primary has given all it can. Nothing left to roll, so say
        # so rather than spinning: `play`'s loop ends on a refusal it
        # cannot act on.
        return slot, next(iter(run.scene.primary), "")
    # **No second secondary while a +2 is already banked.** The bonus is spent
    # by the next primary check and does not stack, so a chooser that takes the
    # easy roll whenever it has the best margin opens by burning every
    # secondary it has for one usable +2 -- measured, three assists rolled and
    # two thrown away, in two of the first three seeds. The gate applies
    # always now: the `success` reading, under which there was nothing to
    # waste, is retired.
    #
    # **Unless this character has nothing to offer on a primary.** The gate
    # above, applied flatly, forced a wizard to roll athletics at -3 rather
    # than help from the side, which is neither good play nor what the printed
    # rule wants from "everybody participates".
    hopeless = all(
        table.modifier(slot, s) < dc_for(run.level, run.band_now) - 10
        for s in run.scene.primary
    ) if run.scene.primary else True
    may_assist = not run.pending_bonus or hopeless
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
    record: list[str] | None = None,
) -> Running:
    """Run a whole challenge and return the finished tally.

    `limit` is a backstop against a chooser that keeps naming refused skills --
    a model can do that, and a loop that never ends is a worse failure than a
    challenge that stops early. Hitting it is the caller's to report rather
    than swallow.
    """
    run = open_challenge(scene, party_level=party_level,
                         record=record)
    picker = choose or taking_turns
    for _ in range(limit):
        if run.over:
            break
        slot, skill = picker(run, table)
        if slot < 0 or not skill:
            break
        resolve(run, table, slot, skill)
    return run


def resolve(run: Running, table: Table, slot: int, skill: str) -> Attempt:
    """Score one named skill, routing a group check to the group door.

    **The router, so there is one of it.** `play` did this inline and
    `#932`'s beat loop needs the identical routing -- two copies would be
    two rulebooks, and the thing they would disagree about is exactly what
    `attempt`'s own refusals exist to catch: a group skill through the
    per-character door is a roll that looks like a success and was scored
    by the wrong rule.

    **The caller routes, not the chooser.** A group check has no slot, so
    making the chooser express one would need a sentinel beside its
    `(-1, "")` give-up and would make `dm.py`'s model loop learn a new
    shape. Asking the scene after the skill is named keeps every chooser --
    including the model's -- exactly as it is.
    """
    if run.scene.group_of(skill):
        return group_attempt(run, table, skill)
    return attempt(run, table, slot, skill)
