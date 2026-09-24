"""What each condition actually does.

One table. Every rule that reads "a dazed creature ..." reads it from here,
so a condition's consequences are in one place rather than scattered across
the attack pipeline, the movement system and the action economy.

Relational conditions appear here too, for the half of their meaning that is
about the afflicted creature. The other half -- *by whom* -- lives in
`relations`, and the marked penalty is applied in `resolve` because it is the
only one that depends on who is being attacked.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import Condition, Defense


@dataclass(frozen=True)
class Rules:
    #: The creature grants combat advantage to everyone.
    grants_ca: bool = False
    #: Penalty to the creature's own attack rolls.
    attack: int = 0
    defences: dict[Defense, int] = field(default_factory=dict)
    #: No actions at all.
    cannot_act: bool = False
    #: One action per turn instead of the full budget.
    one_action: bool = False
    #: No immediate or opportunity actions.
    no_reactions: bool = False
    #: No standard actions. A shape you assume rather than a thing
    #: done to you -- it still moves, and it still acts otherwise.
    no_standard: bool = False
    cannot_move: bool = False
    #: Speed is capped at this many squares.
    speed_cap: int | None = None
    #: Damage the creature deals is halved.
    weakened: bool = False
    #: Treated as helpless: a coup de grace target.
    helpless: bool = False
    #: Cannot flank, and cannot draw line of sight.
    blind: bool = False
    #: Damage the creature *takes* is halved. Distinct from resistance: it
    #: applies to everything, and it is a property of the creature rather
    #: than of the damage type.
    insubstantial: bool = False
    #: Prone and may not stand up yet. Prone itself is the other half.
    no_stand: bool = False
    #: May still walk, but may not shift. Several powers bar the one without
    #: barring the other, and `cannot_move` is the wrong card for them --
    #: it stops walking too.
    no_shift: bool = False


NOTHING = Rules()

RULES: dict[Condition, Rules] = {
    Condition.BLINDED: Rules(grants_ca=True, attack=-2, blind=True),
    Condition.DAZED: Rules(grants_ca=True, one_action=True, no_reactions=True),
    Condition.DEAFENED: Rules(),
    Condition.DOMINATED: Rules(grants_ca=True, one_action=True, no_reactions=True),
    Condition.DYING: Rules(cannot_act=True, cannot_move=True, grants_ca=True, helpless=True),
    Condition.GRABBED: Rules(cannot_move=True),
    Condition.HELPLESS: Rules(grants_ca=True, helpless=True),
    Condition.IMMOBILIZED: Rules(cannot_move=True),
    Condition.INSUBSTANTIAL: Rules(insubstantial=True),
    Condition.MARKED: Rules(),  # the -2 needs to know who is being attacked
    Condition.PETRIFIED: Rules(cannot_act=True, cannot_move=True, helpless=True),
    Condition.PINNED: Rules(no_stand=True),
    Condition.SHAPED: Rules(no_standard=True),
    Condition.PRONE: Rules(grants_ca=True, attack=-2),
    Condition.REMOVED: Rules(cannot_act=True, cannot_move=True),
    Condition.RESTRAINED: Rules(grants_ca=True, attack=-2, cannot_move=True),
    # "Cannot shift" on its own. Named for what it does rather than
    # after any one power, because three classes impose it.
    Condition.ROOTED: Rules(no_shift=True),
    Condition.SLOWED: Rules(speed_cap=2),
    Condition.STUNNED: Rules(grants_ca=True, cannot_act=True, no_reactions=True),
    Condition.SURPRISED: Rules(grants_ca=True, cannot_act=True, no_reactions=True),
    Condition.UNCONSCIOUS: Rules(
        grants_ca=True,
        cannot_act=True,
        cannot_move=True,
        helpless=True,
        defences={Defense.AC: -5},
    ),
    Condition.WEAKENED: Rules(weakened=True),
}


def rules(c: Condition) -> Rules:
    return RULES.get(c, NOTHING)


#: Conditions that always arrive together. Dropping to 0 hit points gives all
#: three, and nothing else in the engine should be assembling that set.
DROPPED = (Condition.UNCONSCIOUS, Condition.PRONE, Condition.DYING)
