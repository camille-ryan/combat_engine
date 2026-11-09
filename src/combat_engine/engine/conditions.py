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

from dataclasses import dataclass, field, replace
from typing import Any

from .types import DEFENCES, Condition, Defense


@dataclass(frozen=True)
class Rules:
    #: The creature grants combat advantage to everyone.
    grants_ca: bool = False
    #: Penalty to the creature's own attack rolls.
    attack: int = 0
    #: Flat change to the creature's defences, applied to every attack.
    #: One user -- `UNCONSCIOUS: {AC: -5}`.
    defences: dict[Defense, int] = field(default_factory=dict)
    #: Change to the creature's defences **against a ranged attack from a
    #: nonadjacent enemy**, and against nothing else.
    #:
    #: A second dict rather than a gate on `defences`, because there is
    #: exactly one printed instance of this shape and a general
    #: `defences_when=` would be a mechanism with one caller. The same call
    #: `_NEUTRAL` makes about itself: a closed list beats an extension
    #: point nobody else reaches.
    #:
    #: **Why prone cannot use `defences`.** `query.defence` sums that one
    #: for every active condition and never looks at the context, so a `+2`
    #: there would raise the prone creature's defences against melee and
    #: against adjacent ranged attacks too -- both of which the printed
    #: rule excludes. Camille, asked directly, 2026-11-09:
    #:
    #:   *"Being prone grants a +2 bonus to your defenses against ranged
    #:   attacks coming from non-adjacent enemies."*
    #:
    #: Read in `query.defence` off the attack context, which already
    #: carries `attacker`, `target` and `ranged`. #1198.
    ranged_defences: dict[Defense, int] = field(default_factory=dict)
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
    #: Half speed rather than a cap. Squeezing is the only thing that does
    #: this, and it is a fraction of whatever the speed happens to be.
    halve_speed: bool = False
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
    # `no_shift` because the printed line is "you can't move from your space,
    # although you can teleport, crawl, or be forced to move by a pull, a push
    # or a slide" -- and a shift is none of those. `actions._movement` already
    # withholds the option at the action layer, so a creature on its own turn
    # was never offered one; `c.shift()` reaches past that, and a row saying
    # "the target shifts" moved a prone creature one square, or three.
    #
    # Forced movement is untouched by this: a slide is not a shift, and
    # `movement.forced` does not go through `can_shift`.
    # **The defence bonus is the printed bullet this table was missing**,
    # and it is not small: without it every prone creature in every fight
    # was 2 easier to shoot from range than the page says. #1198.
    #
    # `grants_ca=True` is still wider than print, which restricts the grant
    # to **melee** attackers. That half is not fixable here --
    # `query.grants_ca` is a creature-level question and
    # `_has_combat_advantage` does not know whether the attack is melee or
    # ranged -- so it is filed rather than guessed at. Until it lands, an
    # adjacent archer still gets a combat-advantage +2 it should not.
    Condition.PRONE: Rules(
        grants_ca=True, attack=-2, no_shift=True,
        ranged_defences={d: 2 for d in DEFENCES},
    ),
    Condition.REMOVED: Rules(cannot_act=True, cannot_move=True),
    Condition.RESTRAINED: Rules(grants_ca=True, attack=-2, cannot_move=True),
    # "Cannot shift" on its own. Named for what it does rather than
    # after any one power, because three classes impose it.
    Condition.CANNOT_SHIFT: Rules(no_shift=True),
    Condition.SLOWED: Rules(speed_cap=2),
    # A big creature folding itself into a small space: half speed, -5 to
    # attack, and it grants combat advantage to everybody.
    Condition.SQUEEZING: Rules(grants_ca=True, attack=-5, halve_speed=True),
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


def rules_for(world: Any, eid: int, c: Condition) -> Rules:
    """This condition's rules **as they apply to this creature**.

    The table above is what the book prints. A dozen rows print a waiver on
    part of it -- "you take no penalty to attack rolls while squeezing", "you
    move at full speed" -- and a waiver is not the same as not having the
    condition: you are still squeezing, and still fit where only a squeezing
    creature fits. See `Conditions.waived`.

    Returns the shared table object untouched when nothing is waived, which
    is every creature almost always -- this is on the path of every speed
    and every attack. #508.
    """
    from .components import Conditions

    base = RULES.get(c, NOTHING)
    held = world.get(eid, Conditions)
    waived = held.waived.get(c) if held is not None else None
    if not waived:
        return base
    return replace(base, **{k: _NEUTRAL[k] for k in waived if k in _NEUTRAL})


#: What each waivable field becomes when a card switches it off. Only the
#: fields a printed waiver actually names: `cannot_act` and the rest are not
#: things a feat relaxes, and listing them would invite a row to try.
_NEUTRAL: dict[str, Any] = {
    "attack": 0,
    "halve_speed": False,
    "grants_ca": False,
    "speed_cap": None,
}


#: Conditions that always arrive together. Dropping to 0 hit points gives all
#: three, and nothing else in the engine should be assembling that set.
DROPPED = (Condition.UNCONSCIOUS, Condition.PRONE, Condition.DYING)
