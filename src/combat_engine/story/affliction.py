"""Diseases the party carries between scenes, and how they move. #948.

**69 diseases are fully extracted and nothing ticked one.** The ETL half
has been done for a while -- `disease` carries `check_skills`,
`worsen_dc`, `improve_dc`, `dc_shape` and `stages` -- so a party could
catch one and then carry it forever at whatever stage it arrived at,
because no reader existed and no rest rolled anything.

This is steps 1 and 2 of `#948`: the state on `story.Sheet` and the roll
at an extended rest. Step 3 is 69 content rows and step 4 is the engine
half; neither is here.

**The roll follows `run.weather`'s shape and not a new one.** That function
already rolls a party-wide Endurance check between scenes -- lay a
`table.Table` over the party, then `board.check(slot, skill, target)` --
and a disease check is the same question asked against a different DC. A
second mechanism for the same thing is how two answers to one question
start disagreeing.

## What ticks and what does not, measured rather than assumed

    dc_shape          fixed 58   band 8   source_level 2   encounter_level 1
    rows with no level           8   -- exactly the band ones
    check_skills      endurance 60   insight/wisdom/arcana 3   EMPTY 4
    fixed + in band 1-10         31

Only `fixed` ticks, and `TRACKED` says so. The other eleven are refused
**by name in the return value** rather than skipped quietly:

* **`band`** prices its DC off a level band and all eight carry no level at
  all, so there is nothing to resolve it against -- `query.difficulty`
  answers `None` for exactly this case and `#491` records why. A band DC
  with no level is not a hard lookup, it is an absent one.
* **`source_level` and `encounter_level`** price off the creature or the
  encounter that inflicted it, and a `Sheet` carries neither. Tracking
  those needs the infliction to record its source, which is not state that
  exists.
* **four rows name no check skill**, so there is no roll to make. A disease
  that cannot be checked cannot improve or worsen by this rule.

Measured, and the partition is exact:

    tickable                     53
    refused                      16   8 band, 4 no skill, 2 source_level,
                                      1 encounter_level, 1 a choice of two
    ---------------------------------
                                 69

**53 and 16, not the 38 and 31 I first wrote here.** That pair was
arithmetic off the `dc_shape` histogram rather than off the rows, and it
double-counted: a row with no check skill is usually also one of the
shapes already refused. `printed()` and `refused()` partition the table
and `drivers.affliction` asserts they sum to 69, so the figure cannot
drift from the code again.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

#: The DC shapes this can resolve. See the module docstring for the other
#: three and why each is refused.
TRACKED = ("fixed",)

#: The stage a cured character is at. Stage counting runs **upward into the
#: disease**: 0 is cured and `Printed.stages` is as bad as it gets, which is
#: the direction the printed stage tracks are written in.
CURED = 0


@dataclass(frozen=True)
class Printed:
    """One disease's numbers, as the page prints them."""

    ref: str
    level: int
    skill: str
    improve_dc: int
    worsen_dc: int
    stages: int


@lru_cache(maxsize=1)
def printed() -> dict[str, Printed]:
    """Every tickable disease by ref. Read once; `game.db` does not move.

    A row is tickable when its DC shape is one this can resolve **and** it
    names exactly one check skill. One row names two (`arcana,insight`),
    which the page means as a choice -- and a choice is a decision about
    which skill the character uses, not arithmetic, so it is left out
    rather than guessed at by taking the first.
    """
    from combat_engine.db import game

    out: dict[str, Printed] = {}
    for ref, level, skills, worsen, improve, shape, stages in game().execute(
        "SELECT ref, level, check_skills, worsen_dc, improve_dc, "
        "dc_shape, stages FROM disease"
    ):
        if shape not in TRACKED:
            continue
        skill = (skills or "").strip()
        if not skill or "," in skill:
            continue
        try:
            out[ref] = Printed(
                ref=ref, level=int(level), skill=skill,
                improve_dc=int(improve), worsen_dc=int(worsen),
                stages=int(stages),
            )
        except (TypeError, ValueError):
            # A row whose numbers do not parse is an extraction fault and
            # is dropped rather than defaulted: a disease with an invented
            # DC would tick wrongly and silently, which is worse than one
            # that does not tick.
            continue
    return out


def refused() -> dict[str, str]:
    """Every disease this cannot tick, and the reason. #948.

    **Named rather than counted**, because the count alone cannot be acted
    on: a reader asking why a party's disease never moves needs to know it
    is a band DC with no level and not that 31 of 69 are missing.
    """
    from combat_engine.db import game

    out: dict[str, str] = {}
    for ref, level, skills, shape in game().execute(
        "SELECT ref, level, check_skills, dc_shape FROM disease"
    ):
        skill = (skills or "").strip()
        if shape not in TRACKED:
            why = f"dc_shape={shape!r}"
            if not str(level or "").strip():
                why += " and no level to resolve it against"
            out[ref] = why
        elif not skill:
            out[ref] = "names no check skill, so there is no roll to make"
        elif "," in skill:
            out[ref] = f"names a choice of skills ({skill}), which is a decision"
    return out


def tick(party: object, seed: int) -> list[str]:
    """Roll each afflicted character's check at an extended rest. #948.

    One line per character who rolled, saying which way it went. `[]` when
    nobody is afflicted, which is every party today -- **nothing inflicts a
    disease yet**, so this is the reader arriving before its writer. Said
    plainly because an empty list is otherwise indistinguishable from a
    broken tick.

    Beat the improve DC and the stage falls by one; fail the worsen DC and
    it rises by one; between the two and it holds, which is the printed
    three-way outcome rather than a pass/fail. A stage reaching `CURED` is
    dropped from the sheet -- a cured disease is not a disease at stage
    zero, and leaving it would make `afflictions` a history rather than a
    state.

    The board is laid once for the whole party, as `run.weather` lays one:
    `Table.check` reads each character's own modifier off it, so a table
    per character would be the same answer at four times the cost.
    """
    from combat_engine.story import table as table_mod

    sheets = list(getattr(party, "sheets", []) or [])
    if not any(getattr(s, "afflictions", None) for s in sheets):
        return []
    known = printed()
    board = table_mod.lay(party, seed=seed)
    said: list[str] = []
    for slot, sheet in enumerate(sheets):
        for ref, stage in sorted(dict(sheet.afflictions).items()):
            got = known.get(ref)
            if got is None:
                # Carried but not tickable -- `refused` says why. Left on
                # the sheet rather than dropped: the party still has it.
                continue
            # **One roll, compared against both DCs**, and this is the half
            # that was wrong in the first draft. Calling `check` twice --
            # once per DC -- throws two d20s for one printed check, so a
            # character could clear the improve DC on one die and fail the
            # worsen DC on the other, which is two outcomes at once and
            # twice the dice. `CheckResult.total` is what makes the
            # three-way comparison possible off a single throw.
            rolled = board.check(slot, got.skill, got.improve_dc)
            if rolled.total >= got.improve_dc:
                now = stage - 1
                went = "improves"
            elif rolled.total < got.worsen_dc:
                now = min(stage + 1, got.stages)
                went = "worsens"
            else:
                now, went = stage, "holds"
            if now <= CURED:
                del sheet.afflictions[ref]
                said.append(f"{sheet.cls} shakes off {ref}")
                continue
            sheet.afflictions[ref] = now
            said.append(
                f"{sheet.cls}'s {ref} {went} -- stage {now} of {got.stages}"
            )
    return said
