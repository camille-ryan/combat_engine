"""The vocabulary the rest of the engine is written in.

Nothing here imports anything else in the package, so every other module can
import it freely.
"""

from __future__ import annotations

from enum import Enum, IntEnum, StrEnum, auto


class Ability(StrEnum):
    STR = "str"
    CON = "con"
    DEX = "dex"
    INT = "int"
    WIS = "wis"
    CHA = "cha"


class Defense(StrEnum):
    AC = "ac"
    FORT = "fort"
    REF = "ref"
    WILL = "will"


class ActionType(StrEnum):
    STANDARD = "standard"
    MOVE = "move"
    MINOR = "minor"
    FREE = "free"
    IMMEDIATE_INTERRUPT = "immediate_interrupt"
    IMMEDIATE_REACTION = "immediate_reaction"
    OPPORTUNITY = "opportunity"
    NONE = "none"


#: A standard may be spent as a move, and a move as a minor. Not the reverse.
DOWNGRADES: dict[ActionType, tuple[ActionType, ...]] = {
    ActionType.STANDARD: (ActionType.STANDARD,),
    ActionType.MOVE: (ActionType.MOVE, ActionType.STANDARD),
    ActionType.MINOR: (ActionType.MINOR, ActionType.MOVE, ActionType.STANDARD),
}


class Usage(StrEnum):
    AT_WILL = "at-will"
    ENCOUNTER = "encounter"
    DAILY = "daily"
    RECHARGE = "recharge"


class Keyword(StrEnum):
    MARTIAL = "martial"
    ARCANE = "arcane"
    DIVINE = "divine"
    PRIMAL = "primal"
    WEAPON = "weapon"
    IMPLEMENT = "implement"
    MELEE = "melee"
    RANGED = "ranged"
    CLOSE = "close"
    AREA = "area"
    HEALING = "healing"
    CHARM = "charm"
    FEAR = "fear"
    RELIABLE = "reliable"
    STANCE = "stance"
    CONJURATION = "conjuration"
    ZONE = "zone"
    # A power's damage type is also a keyword, because resistances and
    # immunities key off the keyword rather than off the damage roll.
    ACID = "acid"
    COLD = "cold"
    FIRE = "fire"
    FORCE = "force"
    LIGHTNING = "lightning"
    NECROTIC = "necrotic"
    POISON = "poison"
    PSYCHIC = "psychic"
    RADIANT = "radiant"
    THUNDER = "thunder"


class DamageType(StrEnum):
    UNTYPED = "untyped"
    ACID = "acid"
    COLD = "cold"
    FIRE = "fire"
    FORCE = "force"
    LIGHTNING = "lightning"
    NECROTIC = "necrotic"
    POISON = "poison"
    PSYCHIC = "psychic"
    RADIANT = "radiant"
    THUNDER = "thunder"


class Condition(StrEnum):
    """Conditions that live on a single creature.

    The relational ones -- grabbed, marked, dominated, hidden -- are named
    here too because a power says "the target is grabbed" without naming the
    grabber, but their *source* is held in `relations`, never here.
    """

    BLINDED = "blinded"
    DAZED = "dazed"
    DEAFENED = "deafened"
    DOMINATED = "dominated"
    DYING = "dying"
    GRABBED = "grabbed"
    HELPLESS = "helpless"
    IMMOBILIZED = "immobilized"
    MARKED = "marked"
    PETRIFIED = "petrified"
    PRONE = "prone"
    REMOVED = "removed"
    RESTRAINED = "restrained"
    SLOWED = "slowed"
    STUNNED = "stunned"
    SURPRISED = "surprised"
    UNCONSCIOUS = "unconscious"
    WEAKENED = "weakened"


class Relation(StrEnum):
    """Effects that need two creatures to mean anything."""

    GRABBED_BY = "grabbed_by"
    MARKED_BY = "marked_by"
    DOMINATED_BY = "dominated_by"
    HIDDEN_FROM = "hidden_from"
    #: Granted explicitly by a power. Flanking is *computed*, not stored here.
    GRANTS_CA_TO = "grants_ca_to"


class Size(StrEnum):
    """A creature's size category.

    The footprint is a **property**, not the value. Making the value the
    number of squares looked tidy and was wrong: Tiny, Small and Medium all
    occupy one square, so they collapsed into aliases of each other and every
    character on the board reported itself as Tiny.
    """

    TINY = "tiny"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    HUGE = "huge"
    GARGANTUAN = "gargantuan"

    @property
    def squares(self) -> int:
        """How many squares on a side this creature occupies."""
        return _FOOTPRINT[self]

    @property
    def reach_bonus(self) -> int:
        """Extra reach that comes from bulk alone."""
        return max(0, self.squares - 1)


_FOOTPRINT = {
    Size.TINY: 1,
    Size.SMALL: 1,
    Size.MEDIUM: 1,
    Size.LARGE: 2,
    Size.HUGE: 3,
    Size.GARGANTUAN: 4,
}


class Cover(IntEnum):
    NONE = 0
    PARTIAL = 2
    SUPERIOR = 5


class Speed(StrEnum):
    WALK = "walk"
    FLY = "fly"
    CLIMB = "climb"
    SWIM = "swim"
    BURROW = "burrow"
    TELEPORT = "teleport"
    SHIFT = "shift"


class Team(StrEnum):
    PC = "pc"
    ENEMY = "enemy"
    NEUTRAL = "neutral"


class Window(Enum):
    """When a listener runs relative to the event it watches.

    BEFORE is the immediate-interrupt window: the event has not happened yet
    and a listener may still change or cancel it. AFTER is the reaction
    window: it has happened and the listener is responding.
    """

    BEFORE = auto()
    AFTER = auto()


class Forced(StrEnum):
    PUSH = "push"
    PULL = "pull"
    SLIDE = "slide"


def modifier(score: int) -> int:
    """An ability score's modifier: 10-11 is +0, every two points is one step."""
    return (score - 10) // 2
