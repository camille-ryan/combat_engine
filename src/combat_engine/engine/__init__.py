"""The rules kernel.

One import for anyone writing content:

    from combat_engine.engine import *
"""

from .actions import Action, legal, perform
from .basic import MELEE, RANGED  # registers the basic attacks
from .cast import Cast
from .components import (
    Budget,
    Build,
    Conditions,
    Defences,
    Defenses,
    Gear,
    Health,
    Ident,
    Initiative,
    Mod,
    Mods,
    Movement,
    Position,
    Powers,
    Side,
    Stats,
    Weapon,
)
from .dsl import (
    ANY_CREATURE,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    PERSONAL,
    REGISTRY,
    SELF,
    AreaBurst,
    Attack,
    CloseBlast,
    CloseBurst,
    Damage,
    Melee,
    MeleeOrRanged,
    Power,
    Ranged,
    Target,
    UpTo,
    candidates,
    declared,
    get,
    power,
    usable,
    use,
)
from .durations import Effect, Effects, When
from .ecs import World
from .events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Bus,
    ConditionApplied,
    DamageApplied,
    Died,
    Dropped,
    Event,
    Healed,
    Hit,
    Miss,
    Moved,
    MoveEnd,
    OpportunityWindow,
    PowerUsed,
    RoundStart,
    SavingThrow,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from .grid import Grid, Square, distance, footprint, spread
from .monster_math import AS_PRINTED, TO_MM3
from .policy import LinearPolicy, Memory, Policy, install, take_turn
from .rng import Rng
from .triggers import (
    Trigger,
    about_me,
    ally_within,
    both,
    by_charge,
    by_keyword,
    by_me,
    by_melee,
    by_opportunity,
    by_ranged,
    cursed_by_me,
    either,
    enemy_target_within,
    enemy_within,
    hits_me,
    leaves_me_out,
    not_me,
    targets_me,
    targets_my_side,
    would_hit_me,
)
from .turns import Encounter
from .types import (
    Ability,
    ActionType,
    Condition,
    Cover,
    DamageType,
    Defense,
    Forced,
    Keyword,
    Relation,
    Size,
    Team,
    Usage,
    Window,
)

# Ability scores, spelled the way a power's attack line spells them.
STR, CON, DEX, INT, WIS, CHA = (
    Ability.STR,
    Ability.CON,
    Ability.DEX,
    Ability.INT,
    Ability.WIS,
    Ability.CHA,
)
AC, FORT, REF, WILL = Defense.AC, Defense.FORT, Defense.REF, Defense.WILL
AT_WILL, ENCOUNTER, DAILY = Usage.AT_WILL, Usage.ENCOUNTER, Usage.DAILY
STANDARD, MOVE, MINOR, FREE = (
    ActionType.STANDARD,
    ActionType.MOVE,
    ActionType.MINOR,
    ActionType.FREE,
)
INTERRUPT, REACTION, OPPORTUNITY = (
    ActionType.IMMEDIATE_INTERRUPT,
    ActionType.IMMEDIATE_REACTION,
    ActionType.OPPORTUNITY,
)

__all__ = [n for n in dir() if not n.startswith("_")]
