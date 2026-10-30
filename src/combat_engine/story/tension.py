"""Reading the party's recent record back into the next scene's numbers.

The printed system is a closed loop and this engine ran it open:

> **Tension and release.** Maintain the tension and release of the pass/fail
> cycle by **adjusting DCs or encounter levels to reflect the party's recent
> record of loss and gain.** When a string of failures discourages players,
> adjust the numbers downward to make their subsequent success more likely.
> If the PCs are cocky in the wake of successive wins, tighten the screws.

Every input and lever already existed -- `Step.outcome` per scene,
`budget(level, scale)`, `dc(level, band)` -- and a story campaign passed
nothing to either.

## Bounded is the whole design

An unbounded loop that eases after every loss converges on a game nobody
can lose, which is the opposite of tension and release. So:

* the record is **short** (`RECENT`), and only decided scenes count;
* `footing` is **-1, 0 or +1** and cannot be anything else;
* the scale is one step either way, never compounded.

## Three things it deliberately does not touch

* **A module's stated `xp`.** `cast_list` already treats a printed figure
  as overriding the headcount, and a dynamic scale has to sit outside that
  the same way or a published encounter stops being the encounter the page
  describes. Only an *unstated*-XP fight is scaled.
* **`Scene.difficulty`**, which is what the module says, and
  `api.day.scales`, which is the arcade day's planned curve. This is the
  only one of the three that reads an outcome.
* **Nothing silently.** A rubber-banded difficulty is a thing players
  notice and resent, so every adjustment is a `note` line. #977.
"""

from __future__ import annotations

#: How many decided scenes are remembered. Short, because the rule is about
#: a *recent* record and a long window makes the loop sluggish and then
#: sudden.
RECENT = 4

#: What counts as a decision. A roleplay scene is always `done` and a
#: skipped one decided nothing, so neither is evidence about how the party
#: is faring.
DECIDED = ("won", "lost")

#: The scale a fight is given when the party is struggling, and when they
#: are cocky. One step either way, applied to `story.budget`.
EASE = 0.85
TIGHTEN = 1.15

#: How many of the remembered scenes must have gone one way before the
#: numbers move. Two losses in the last four is a *"string of failures"*;
#: one is a setback.
ENOUGH = 2


def footing(record: list[str]) -> int:
    """`-1` struggling, `+1` cocky, `0` neither. Never anything else.

    Reads only the last `RECENT` **decided** outcomes, so a stretch of
    conversation neither eases nor tightens anything.

    Cocky is stricter than struggling on purpose: the rule's two halves
    are not symmetric -- *"when a string of failures discourages players"*
    is a kindness and *"if the PCs are cocky"* is a judgement, so a loss
    counts sooner than a win does. Every remembered scene has to be a win
    to tighten, where `ENOUGH` losses will ease.
    """
    recent = [o for o in record if o in DECIDED][-RECENT:]
    if not recent:
        return 0
    lost = sum(1 for o in recent if o == "lost")
    if lost >= ENOUGH:
        return -1
    if len(recent) >= RECENT and lost == 0:
        return 1
    return 0


def scale(record: list[str]) -> float:
    """What to multiply an unstated-XP fight's budget by."""
    stance = footing(record)
    if stance < 0:
        return EASE
    return TIGHTEN if stance > 0 else 1.0


def band(base: str, record: list[str], bands: tuple[str, ...]) -> str:
    """One band easier or harder, clamped to the ends of `bands`.

    A band rather than a number, because that is the unit `dc.py` speaks
    and the unit a module states -- shifting the DC by a few points would
    put a check between two printed rows and make a module's own
    `moderate` mean something no page prints.
    """
    if base not in bands:
        return base
    at = bands.index(base)
    # **Plus, not minus.** `BANDS` runs easy -> moderate -> hard, so a
    # higher index is a harder check: tightening raises it and easing
    # lowers it. The first draft subtracted, which made a cocky party's
    # checks *easier* and a struggling party's unchanged -- the exact
    # inversion of the rule, and invisible without printing the pairs.
    moved = at + footing(record)
    return bands[max(0, min(len(bands) - 1, moved))]


#: Said after a budget note, because the budget is a ceiling rather than a
#: target: a module asking for fewer creatures than it allows is unmoved
#: either way. Measured -- a 10-creature ask fields 3/4/5 by footing, and a
#: 3-creature ask fields 3 whatever the record says. Claiming the scene is
#: harder when the roster did not move would be the overstatement this
#: whole mechanism is supposed to avoid.
ONLY_A_CEILING = (" It binds only where the module asks for more than the "
                  "budget allows.")


def says(record: list[str], *, fight: bool = False) -> str:
    """What to print when the numbers moved, or `""` when they did not.

    `fight` adds the ceiling caveat, which is true of the budget and not
    of a skill check -- a pitched band moves every primary roll.
    """
    stance = footing(record)
    if stance < 0:
        said = ("The party has been losing, so this scene is pitched "
                f"easier (x{EASE}) -- said out loud rather than applied "
                "quietly.")
    elif stance > 0:
        said = ("The party has won everything lately, so this scene is "
                f"pitched harder (x{TIGHTEN}).")
    else:
        return ""
    return said + (ONLY_A_CEILING if fight else "")
