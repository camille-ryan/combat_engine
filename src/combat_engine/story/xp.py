"""What an encounter, a challenge and a quest are worth. #967.

Nothing in the engine awarded any experience before this. `Sheet` carried
`level`, `hp`, `surges`, `action_points`, `failures` and `powers`, and a
campaign played its module at the level `Party.of` was called with and
stopped there.

**Awarding is this module. Spending is not.** Applying a level means
re-dealing powers, feats and ability increases for a character whose hand is
pinned deliberately, which re-opens exactly the thing `chargen`'s charter
says does not exist. So this computes and records, says when a character has
enough, and applies nothing.

Every figure here is **read off `game.db`** rather than written down, for the
reason `budget` gives one function away: a table here can disagree with what
the monsters are actually worth, and then two numbers describe one rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from combat_engine.story import SIDE, ceiling, commonest

#: How many encounters of their own level a character gains a level over.
#:
#: *"The experience point numbers in the game are built so that characters
#: complete eight to ten encounters for every level they gain."* Ten, not
#: eight, because **ten is what the printed advancement table actually
#: divides into** -- which is a measurement rather than a choice of the
#: friendlier end. Running totals of `10 * standard(level)` reproduce the
#: printed cumulative thresholds exactly for levels 1 through 9:
#:
#:     1,000  2,250  3,750  5,500  7,500  10,000  13,000  16,500  20,500
#:
#: and the first level it misses is 10, where the real curve bends on its way
#: into paragon. Heroic is the standing tier, so the derivation holds
#: everywhere it is used; `to_advance` says so rather than pretending past
#: the bend.
PER_LEVEL = 10

#: Beats of focused interaction that earn a drama reward, DMG2. The book's
#: unit is *"every 15 minutes they spend in significant, focused
#: roleplaying"*, and a text engine has no minutes -- so the unit is a beat
#: in which something actually happened, which is a thing the engine can
#: already tell apart.
#:
#: **Four is a judgement, not a printed figure.** It is the one number in
#: this file not read off a page: `beat.MAX_BEATS` is 6, so four earns the
#: reward for a scene that was mostly substance and withholds it from one
#: that opened, wandered and left.
DRAMA_BEATS = 4


@dataclass(frozen=True)
class Award:
    """One payment, and what it was for.

    Carried rather than returned as a bare number so the line the player
    reads can say which rule paid -- *"don't be shy about letting the
    players know"* applies to the reward as much as to the quest.
    """

    source: str
    each: int
    total: int
    why: str = ""


def standard(level: int) -> int:
    """A standard monster of this level's XP.

    **The commonest figure at the level, not whichever row sorted first.**
    `budget` asks the same column the same question and used to ask it with
    `LIMIT 1` and no `ORDER BY` -- which agrees at all 13 levels today and
    was one re-ordering away from not: level 10 carries a single creature at
    300 against 141 at 500, level 8 one at **1,750** against 350, and level
    1 one at **25** against 100. So the exposure ran from a quarter to five
    times, not the 40% #1014's title names. Both now go through
    `story.commonest`, which lives a layer down so there is one definition.

    **The claim still cannot be posed against the database**, which is why
    `commonest` is a named function at all: a plant swapping it for
    `rows[0]` stays green on the live rows, so the driver asserts it against
    a list where the two differ.

    Clamped to `ceiling()` for the same reason `budget` clamps: the
    database stops where the ETL stopped, and a figure above it would
    describe monsters that are not there.
    """
    from combat_engine.db import game

    rows = [
        row[0] for row in game().execute(
            "SELECT xp FROM monster WHERE level = ? AND minion = 0 "
            "AND xp > 0 AND (rank IS NULL OR rank = 'standard')",
            (min(max(level, 1), ceiling()),),
        )
    ]
    return commonest(rows)


def for_creatures(refs: list[str]) -> int:
    """What the opposition was worth, summed over what was fielded.

    **Each creature's own printed XP**, which is why `story.WORTH` does not
    appear here: an elite's row already carries double and a solo's five
    times, so multiplying by the rank again would pay twice. `WORTH` is for
    *spending* a budget, and reading it as a reward multiplier is the
    mistake this comment exists to stop.

    A minion is worth its quarter the same way -- it is in the row.
    """
    from combat_engine.db import game

    if not refs:
        return 0
    total = 0
    for ref in refs:
        row = game().execute(
            "SELECT xp FROM monster WHERE ref = ?", (ref,)
        ).fetchone()
        total += (row[0] or 0) if row else 0
    return total


def for_challenge(level: int, complexity: int) -> int:
    """A skill challenge, which the page prices in monsters.

    *"A skill challenge counts as a number of monsters of its level equal to
    its complexity -- so a 7th-level challenge with a complexity of 3 counts
    as three 7th-level monsters, or 900 XP."* That sentence is also the
    check: `for_challenge(7, 3)` is 900.
    """
    return max(complexity, 0) * standard(level)


def for_quest(kind: str, level: int) -> Award:
    """A completed quest, where the two kinds divide differently.

    This is the asymmetry worth knowing, and it is printed:

    * a **minor** quest *"is worth one monster of its level"*, divided among
      the party like any other award;
    * a **major** quest is worth a whole encounter of its level, and its
      per-character value **does not divide** -- *"When a group of
      characters completes a 10th-level major quest, each individual in the
      group gets 500 XP, regardless of how many characters are in the
      group."*

    `standard(10)` is 500, so a major quest pays one standard monster of its
    level **per head** and keeps paying that however many heads there are. A
    minor quest pays one standard monster of its level **between them**.
    """
    one = standard(level)
    if kind == "major":
        return Award(
            "quest", each=one, total=one * SIDE,
            why="a major quest pays each character the same, whatever the "
                "party's size",
        )
    return Award(
        "quest", each=0, total=one,
        why="a minor quest is one monster of its level, split",
    )


def share(total: int, heads: int) -> int:
    """*"Divide the XP total for the encounter by the number of players
    present."*

    Floored, which loses up to `heads - 1` points of a party's award. The
    alternative is handing the remainder to somebody, and the page gives no
    rule for who -- so it is dropped, which at least treats everybody the
    same.
    """
    return total // max(heads, 1)


def to_advance(level: int) -> int:
    """The **cumulative** XP one character needs to reach the next level.

    Cumulative, because `Sheet.xp` is a running total and never resets.
    This read `PER_LEVEL * standard(level)` first -- the *increment* for
    one level -- and a probe caught it: a 2nd-level character would have
    been called ready at 1,250 XP where the printed table says 2,250. The
    two agree only at level 1, which is exactly where a first probe looks.

    Summed, it is the printed cumulative table for every heroic level:

        level 2 at 1,000, 3 at 2,250, 4 at 3,750, 5 at 5,500, 6 at 7,500,
        7 at 10,000, 8 at 13,000, 9 at 16,500, 10 at 20,500

    Above the bend on the way into paragon it is the printed *rate* rather
    than the printed table, and nothing here applies a level anyway -- the
    campaign only says a character is ready. #1013.
    """
    return sum(PER_LEVEL * standard(each)
               for each in range(1, max(level, 1) + 1))


def drama(beats: object, level: int) -> Award | None:
    """DMG2's third XP source, and the one a text engine measures best.

    > *Award the characters experience as if they had defeated one monster
    > of their level for every 15 minutes they spend in significant,
    > focused roleplaying that advances the story of your campaign. Don't
    > count time the players use to digress, idly chatter, repeat
    > themselves, wander off topic, argue to a standstill, or engage
    > pointlessly with minor characters.*

    That exclusion list is almost exactly a list of beats this engine can
    already pick out: a beat where **no affordance fired** is a beat where
    nobody did anything the module had anything at stake in. `Ruling`
    defaults `affordance` to `"none"`, so the test needs nothing new.

    **One award per scene at most**, which is the book's own anti-farming
    clause -- *"if you think a player is clearly drawing out an interaction
    to score a drama reward, subtract an amount of time that you estimate
    is equal to the entire time that player spent"* -- expressed as a cap
    rather than as a judgement call, because the engine has no judgement to
    make.

    **Opt in.** The same chapter: *"you should grant drama rewards for
    vignettes only if you rely on them in any given session"*, so this is a
    per-campaign setting and off by default.
    """
    played = getattr(beats, "beats", None)
    if not played:
        return None
    substantial = sum(
        any(r.affordance != "none" for r in beat.rulings) for beat in played
    )
    if substantial < DRAMA_BEATS:
        return None
    one = standard(level)
    return Award(
        "drama", each=0, total=one,
        why=f"{substantial} beats of focused play, one monster of the "
            f"party's level",
    )


def pay(sheets: list, award: Award, *, heads: int = 0) -> Award:
    """Add an award to every sheet, and report what each one got.

    `Award.each` set means the figure is per character already -- a major
    quest -- and is paid as it stands. Otherwise the total is shared.

    `heads` overrides how many ways it divides, and the one caller that
    passes it is a fight with allies: *"when a nonplayer character
    participates in an encounter, that character earns an equal share of
    experience points"*, so a party of four with two allies divides by
    six. The allies hold no sheet, so their shares are simply not paid to
    anybody -- which is the point, not a rounding loss. #961.
    """
    each = award.each or share(award.total, heads or len(sheets))
    for sheet in sheets:
        sheet.xp += each
    return Award(award.source, each=each, total=each * len(sheets),
                 why=award.why)


def ready(sheet: object) -> bool:
    """Has this character earned the next level.

    Says so and does nothing about it: see this module's own docstring, and
    the `chargen` issue it names.
    """
    level = getattr(sheet, "level", 1)
    return getattr(sheet, "xp", 0) >= to_advance(level)
