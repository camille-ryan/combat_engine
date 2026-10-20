"""A board with nobody to fight on it, so a scene that is not a fight can roll.

A skill challenge needs `skills.check`, and `skills.check` needs a `World` and
an entity id. There is no sheet-level check anywhere in the engine and nothing
reads a skill off a `chargen.Character` -- `chargen.sheet` prints abilities,
hit points, surges, defences, armour and powers, and not one skill.

So rather than reimplement the roll in `story/` and have the two drift, a
non-combat scene gets a **real board with only the party on it**. Everything
then applies for free and stays applying: training's +5, racial bonuses laid as
`Mods`, the armour check penalty on the four encumbered skills, a feat that
answers `CheckDeclared` to call odd or even, and a trigger that adds to the
bonus inside the resolve window. A hand-rolled `d20 + half level + mod` in this
file would have none of that and would look right.

## The encounter is started, and that is not decoration

`scripts/expect.py` already records the reason in one line: *"An encounter has
to be running or nothing a feat arms is armed."* A feat arms itself at the top
of a fight -- that is what `Powers.known` rows do -- so a challenge rolled on
an unstarted board silently loses every feat that modifies a check. The rolls
would still come out plausible, which is this component's named failure mode:
not a crash, a number that is quietly four too low.

Nothing ever takes a turn here. `start()` is called for the arming and the
clock is then left alone.

## Small board, far apart, and no terrain

Twelve by eight with the party in a column. No `terrain.dress`, because dressing
puts difficult ground and a trap on the board and a conversation is not a fight;
and because `dress` is seeded, dressing here would consume draws and move what a
later fight in the same campaign rolled.

## It is thrown away, but the wear is not

`harvest` runs when the table is struck, for the same reason it runs after a
fight: a feat that spends a healing surge to add to a check has spent it, and a
party that walked away from the conversation with the surge back would make the
day's arithmetic a lie. Measured or not, the cost of harvesting is one pass over
four entities and the cost of not harvesting is a resource economy that leaks
in exactly one direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from combat_engine import chargen
from combat_engine.engine import Bus, Grid, Rng, World
from combat_engine.engine.scaling import PRESETS
from combat_engine.engine.skills import SKILLS, CheckResult, modifier
from combat_engine.engine.skills import check as roll_check
from combat_engine.engine.turns import Encounter

from . import Party, _wear, harvest

#: Room enough to stand in and nothing else. A conversation has no geometry.
WIDTH, HEIGHT = 12, 8

#: Where the party stands. A column, so nobody is flanking anybody.
AT = (2, 1)
SPACING = 2


@dataclass
class Table:
    """The party, standing somewhere, able to roll."""

    world: World
    encounter: Encounter
    party: Party
    #: Entity id per sheet, by position in `party.sheets`. Position is what
    #: ties the two together everywhere in this component -- a `Sheet` carries
    #: no entity id on purpose, because an id belongs to a world and a sheet
    #: outlives one.
    eids: list[int] = field(default_factory=list)

    def who(self, index: int) -> int:
        """The entity for a party slot."""
        return self.eids[index]

    def named(self, name: str) -> int:
        """The party slot a name refers to, or -1.

        Matched on class, lower-cased, because that is the only word a `Sheet`
        carries that a person would type. Two of a class resolve to the first;
        `index` is the unambiguous form and what the tools use.
        """
        want = name.strip().lower()
        for i, sheet in enumerate(self.party.sheets):
            if sheet.cls.lower() == want:
                return i
        return -1

    def modifier(self, index: int, skill: str) -> int:
        """What this character adds to that skill, before the die."""
        return modifier(self.world, self.eids[index], skill.lower())

    def best(self, skill: str, *, exclude: set[int] | None = None) -> int:
        """Which party slot is best at a skill. `-1` if nobody can try.

        The default chooser for `--no-dm` and the fallback when the model names
        nobody. Ties go to the earlier slot, which keeps a seeded run
        reproducible without needing the dice.

        Somebody who is `down` is skipped: a character at negative hit points
        is not talking their way past a guard, and letting the best modifier in
        the party come from somebody bleeding out on the floor is the kind of
        quietly-wrong answer this component produces.
        """
        skill = skill.lower()
        if skill not in SKILLS:
            return -1
        pool = [
            i for i in range(len(self.eids))
            if i not in (exclude or set()) and not self.party.sheets[i].down
        ]
        if not pool:
            return -1
        return max(pool, key=lambda i: (self.modifier(i, skill), -i))

    def check(self, index: int, skill: str, dc: int) -> CheckResult:
        """Roll one check, through the engine, with everything standing."""
        return roll_check(self.world, self.eids[index], skill.lower(), dc)

    def strike(self) -> None:
        """Read the wear back onto the sheets and let the board go.

        **Arming is not spending, and conflating the two cost the party their
        whole encounter kit.** `Encounter.start()` fires every once-per-fight
        *trait* -- a class feature, a passive feat -- and firing one marks it
        used, which is correct on a real board. Harvesting that off the
        scratch board carried it into the campaign: measured, four characters
        walked out of a *conversation* having spent 6, 4, 5 and 10 rows, and
        then into the next fight without them. Nothing about the output looked
        wrong; the party was simply weaker from then on.

        So a row that arrived in `used` during this scene is kept only if it
        **costs an action**. A trait that armed itself is an artefact of
        needing a board at all -- no turn is ever taken here -- while a feat
        that really did spend something to help with a check took an action to
        do it and should stay spent.
        """
        from combat_engine.engine.dsl import get
        from combat_engine.engine.types import ActionType

        before = [dict(sheet.spent) for sheet in self.party.sheets]
        harvest(self.world, self.party)
        for sheet, had in zip(self.party.sheets, before, strict=False):
            kept = dict(had)
            for ref, when in sheet.spent.items():
                if ref in had:
                    continue
                row = get(ref)
                if row is not None and getattr(row, "action", None) is not ActionType.NONE:
                    kept[ref] = when
            sheet.spent = kept


def lay(party: Party, *, seed: int = 0) -> Table:
    """Stand the party up somewhere they can roll dice.

    `seed` is the scene's own, not the campaign's and not a fight's -- a
    challenge that drew from the same stream as the next encounter would make
    changing a conversation change the battle after it, which is the drift
    `field_encounter` already keeps its monster draw out of `world.rng` to
    avoid.
    """
    world = World(Grid(WIDTH, HEIGHT), Rng(seed), Bus())
    world.scaling = PRESETS["full"]
    eids: list[int] = []
    for i, sheet in enumerate(party.sheets):
        eid = chargen.spawn(world, sheet.character, (AT[0], AT[1] + i * SPACING))
        _wear(world, eid, sheet)
        eids.append(eid)
    encounter = Encounter(world)
    encounter.start()
    return Table(world=world, encounter=encounter, party=party, eids=eids)
