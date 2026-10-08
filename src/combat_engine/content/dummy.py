"""A crash test dummy: standard numbers for its level and nothing else.

**Camille's ask, and it came out of a real divergence.** `scripts/expect.py`'s
closed-form model and its simulation disagreed by a third, and the hit rate and
the per-hit damage were both exactly as predicted:

    AttackResult(hit=False, natural=5, total=12, rolls=[18, 5])

A monster had an interrupt that forced a reroll. The 18 hit, the reroll came up
5, and the 5 missed -- 154 of 404 hits quietly stopped being hits, with nothing
in any total saying so. #243.

So a correctness test for a player option should not be run against a real
monster at all. It should be run against something with no riders, no interrupts
and no opinions: standard defences, standard hit points, a standard attack, and
exactly two powers.

`expect.py` currently does this by hand -- spawn a real creature, clear
`Powers.known` to strip the interrupt, then overwrite every number on it. That
works and **the next instrument written will not know to do it**, which is what
this file replaces.

## The numbers, and where each comes from

Measured over 1,997 standard-rank monsters, conjurations and the two refused
rows excluded:

| | fit | used |
|---|---|---|
| AC | level + 13.92 | level + 14 |
| Fortitude | level + 12.12 | level + 12 |
| Reflex | level + 11.96 | level + 12 |
| Will | level + 11.29 | **level + 11** |
| initiative | level + 0.46 | level |

**Will is a point softer than the other two** right across the corpus, and that
is kept rather than flattened to one number: a row targeting Will really is
slightly better against real monsters, and a dummy that hides that would make
every such row look worse than it is.

Hit points are `24 + 8 x level`, which `docs/AI_DOCTRINE.md` names. A least
squares fit over the same 1,997 gives `8.13 x level + 20.8`; the formula is exact
from about level 5 and **four high at level 1**, which is worth knowing before
reading a level-1 result too closely.

Damage comes from `monster_math.FITTED` rather than a fresh fit, so the dummy
moves if that argument is ever settled differently. Attack is `level + 5`, flat,
which is `ATTACK_MM3` for every role and agrees with 623 measured at-will
attacks to within 0.14.

## Why the two basic attacks compute their own bonus

`level + 5` is not a static int and `Attack.printed` is. `Attack`'s own docstring
sanctions the exception: *"A power whose attack bonus depends on the situation
ignores this and calls `c.attack(...)` with whatever it worked out."*

The cost is that a policy cannot read the dummy's attack line without running it.
For a crash test dummy that is the right trade -- the alternative is a new
`Attack` field, which is an engine change widening the audit to every row in the
tree to buy a policy read nobody needs for two powers.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    FORT,
    ONE_CREATURE,
    REF,
    WILL,
    ActionType,
    Budget,
    Cast,
    Conditions,
    Defences,
    Defenses,
    Gear,
    Health,
    Ident,
    Initiative,
    Melee,
    Mods,
    Movement,
    Position,
    Powers,
    Ranged,
    Side,
    Size,
    Stats,
    Team,
    World,
    power,
)
from combat_engine.engine.durations import When
from combat_engine.engine.monster_math import FITTED
from combat_engine.engine.movement import place
from combat_engine.engine.types import Condition, Defense, Relation

#: What a standard monster of this level has, by defence. See the module note --
#: Will is deliberately a point lower than Fortitude and Reflex.
OVER_LEVEL = {AC: 14, FORT: 12, REF: 12, WILL: 11}

#: `docs/AI_DOCTRINE.md`'s formula. Four high at level 1 against the corpus;
#: exact from about level 5.
def hit_points(level: int) -> int:
    return 24 + 8 * level


#: Flat across every role in `ATTACK_MM3`, and measured flat too.
ATTACK_OVER_LEVEL = 5


def _swing(c: Cast) -> None:
    """One attack with the standard numbers for this level.

    Both basics are this. The bonus is worked out here rather than declared
    because it depends on the level -- see the module note on `Attack.printed`.
    """
    foe = c.target
    if foe is None:
        return
    if c.attack(c.level + ATTACK_OVER_LEVEL, Defense.AC, on=foe):
        c.flat(round(FITTED.damage(c.level)), on=foe)


@power("dummy:mba", level=0, cls="dummy", action=ActionType.STANDARD,
       reach=Melee(1), target=ONE_CREATURE)
def dummy_mba(c: Cast) -> None:
    """The dummy's melee basic attack. No riders, by the whole point of it."""
    _swing(c)


@power("dummy:rba", level=0, cls="dummy", action=ActionType.STANDARD,
       reach=Ranged(10), target=ONE_CREATURE)
def dummy_rba(c: Cast) -> None:
    """The dummy's ranged basic attack. No riders, by the whole point of it."""
    _swing(c)


def spawn(
    world: World, level: int = 1, square: tuple[int, int] = (12, 5),
    *, team: Team = Team.ENEMY,
    types: tuple[str, ...] = (),
    conditions: tuple[Condition, ...] = (),
    grabbed_by: int = 0,
) -> int:
    """Put a dummy on the board and return its entity id.

    ## The three knobs, and why these three

    A dummy with no state answers "does this row work against a plain
    creature". Most of what `audit.py` cannot ask is not that. `KNOWN_SILENT`
    is **231** hand-written excuses, and a read of a random 20 found **19
    blaming the harness** rather than the row. Classified by the state the
    harness would have to produce:

        63  grabbed                 <- `grabbed_by=`
        37  a condition applied     <- `conditions=`
        13  a creature type         <- `types=`
        11  terrain       10  a second creature
         7  a sibling's effect   7  prone   5  dying or dead
         3  a form        2  bloodied      73  unclassified

    So these are the top three by a wide margin and `grabbed_by` alone is
    27% of the file. **Creature type was the knob asked for first and is a
    tenth of the problem** -- worth having, and not where to start. #437, #286.

    `types=` needs no schema change, which is the pleasant surprise:
    `query.kinds_of` reads a creature's type words off its stat block *and*
    off any effect labelled `origin:<word>`, and the dummy has no stat block
    at all. So a type word is an effect, the same mechanism `c.set_origin`
    already uses -- rather than a fake row in the monster table.

    `conditions=` lays one hold carrying all of them, `When.ENCOUNTER`, so a
    row asking "a dazed creature" finds one and a row that *removes* a
    condition has something to remove.

    `grabbed_by=` is the id of the creature doing the grabbing, which is the
    direction the excuses want: they read *"attacks or acts on a creature it
    has grabbed"*, so it is the row's own caster that must be holding the
    dummy, not the other way round.

    Assembled the way `loader.spawn` assembles a monster, including
    `scale="monster"` on the defences and the initiative: those numbers are
    **totals** with the level already in them, so the level term comes out here
    and `world.scaling` decides how much to put back. Without that, bounded
    scaling would not bound the dummy and a test under `--scaling bounded` would
    be measuring something else.
    """
    printed = world.scaling.printed_monster(level)
    eid = world.spawn(
        Ident(ref="dummy", role="standard"),
        Position(square=square, size=Size.MEDIUM),
        Side(team=team),
        Stats(level=level, scores={}),
        Defenses(
            values={d: over + level - printed for d, over in OVER_LEVEL.items()},
            scale="monster",
        ),
        # `dies_at_zero`, like a monster: a dummy has no death saves to make and
        # a test that has to wait three rounds for one is measuring the clock.
        Health(max_hp=hit_points(level), surges=0, dies_at_zero=True),
        Movement(speed=6),
        Defences(),
        Initiative(bonus=level - printed, scale="monster"),
        Conditions(),
        Mods(),
        Budget(),
        # **Exactly two rows, and that is the feature.** Everything a real
        # monster carries -- an interrupt that forces a reroll, an aura, a
        # trigger on being hit -- is what made the simulation and the
        # closed form disagree.
        Powers(known=["dummy:mba", "dummy:rba"], basic="dummy:mba",
               ranged="dummy:rba"),
        Gear(),
    )
    place(world, eid, square)
    _configure(world, eid, types, conditions, grabbed_by)
    return eid


def _configure(
    world: World,
    eid: int,
    types: tuple[str, ...],
    conditions: tuple[Condition, ...],
    grabbed_by: int,
) -> None:
    """Lay the requested state, after the creature is on the board.

    **After `place`, not during the spawn.** A grab is a relation between two
    entities and the grabber has to exist; a condition is an `Effect` and
    `Effects.apply` reads the owner's components. Both are things done *to* a
    creature that is already there, which is also how a row would do them.

    One effect per concern rather than one carrying everything, so a test can
    end a grab without ending the conditions, and so the labels say which knob
    put each one there.
    """
    for word in types:
        # `origin:<word>` is what `query.kinds_of` reads, and the label must
        # lead with a ref for `audit._claimed` -- see that function.
        world.effects.apply(
            eid, eid, When.ENCOUNTER, label=f"dummy:setup origin:{word}",
        )
    if conditions:
        world.effects.apply(
            eid, eid, When.ENCOUNTER, conditions=tuple(conditions),
            label="dummy:setup conditions",
        )
    if grabbed_by:
        world.effects.apply(
            eid, grabbed_by, When.ENCOUNTER, label="dummy:setup grab",
            relations=[(Relation.GRABBED_BY, grabbed_by, eid)],
        )
