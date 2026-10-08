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
    #: **Not a defence a creature has.** An instruction about which one to
    #: roll against: a printed line reading "vs. Any" hits if it would hit
    #: any defence, which is one roll against whichever is lowest. Resolved
    #: in `query.defence`, so it gains level, modifiers and conditions the
    #: same way the other four do -- the row that needed this first worked
    #: it out from `Defenses.base`, which has none of those in it.
    #:
    #: Never iterate `Defense` to mean "all of a creature's defences". Use
    #: `DEFENCES` below; that is what this member is excluded from.
    ANY = "any"


#: The four a creature actually has, in printed order.
#:
#: **`Defense` is not this set and must not be iterated as though it were.**
#: `ANY` is a fifth member and an instruction rather than a defence, so a
#: `for d in Defense` loop laying "+2 to all defences" would lay a fifth
#: modifier nothing reads -- the exact "spelled right, does almost the right
#: thing" shape `engine/CLAUDE.md` lists first. Fifteen content files had
#: already written this tuple out by hand before it lived here, which is its
#: own argument for the engine owning it. #360.
DEFENCES: tuple[Defense, ...] = (
    Defense.AC, Defense.FORT, Defense.REF, Defense.WILL,
)


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
    # The power sources the heroic tier did not need. Every monk, psion,
    # battlemind and ardent row prints PSIONIC -- 786 rows between them --
    # and the first class to want one had no way to say it.
    PSIONIC = "psionic"
    SHADOW = "shadow"
    ELEMENTAL = "elemental"
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
    # Read in `Cast.damage`: a rattling power that deals damage leaves the
    # target at -2 to attack rolls until the end of the attacker's next
    # turn. `c.rattling` hands the word to a creature's attacks and
    # `c.rattled` asks it back, which is the whole of what the keyword is.
    RATTLING = "rattling"
    STANCE = "stance"
    #: A wizard subclass's rider on its own melee basic attack. Printed as a
    #: keyword and dropped by the ETL until now, which left `chargen.loadout` with
    #: nothing to gate on -- so six of them were dealt to **every** wizard, whose
    #: build can never satisfy their trigger. #319.
    BLADESPELL = "bladespell"
    CONJURATION = "conjuration"
    SUMMONING = "summoning"
    POLYMORPH = "polymorph"
    SLEEP = "sleep"
    GAZE = "gaze"
    DISEASE = "disease"
    ILLUSION = "illusion"
    TELEPORTATION = "teleportation"
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
    #: **Carries no `Rules` entry, deliberately.** Death is decided by `Health`
    #: and nothing about that changes: `query.alive` and `query.can_act` answer
    #: exactly what they answered before. This exists so a *target line* can
    #: say "one dead ally", which `Health` cannot be asked from a `Target`, and
    #: so a row acting on a corpse has something to read. Camille's call, #399.
    DEAD = "dead"
    DEAFENED = "deafened"
    DOMINATED = "dominated"
    DYING = "dying"
    GRABBED = "grabbed"
    HELPLESS = "helpless"
    IMMOBILIZED = "immobilized"
    INSUBSTANTIAL = "insubstantial"
    MARKED = "marked"
    PETRIFIED = "petrified"
    PINNED = "pinned"
    PRONE = "prone"
    REMOVED = "removed"
    RESTRAINED = "restrained"
    SHAPED = "shaped"
    #: **Not a printed condition and it used to claim to be.** 4e has no "rooted"
    #: condition; the printed clause is "cannot shift", and *Rooted* is a monster
    #: feature name whose meaning varies from block to block -- so a chip reading
    #: "rooted" told a player something the rules do not say, and an author reading
    #: `c.rooted` would reasonably assume it implemented that feature. Camille's
    #: correction.
    #:
    #: It stays in this enum rather than becoming a modifier because six rows pass
    #: it *alongside* a real condition -- "slowed and cannot shift (save ends
    #: both)" is one effect with one saving throw, and `Rules` is keyed by
    #: `Condition`. Naming it for the clause is the honest fix; restructuring
    #: `Rules` to hang a flag off a conditionless effect would split those into two
    #: effects and two saves, which is worse.
    CANNOT_SHIFT = "cannot shift"
    SLOWED = "slowed"
    SQUEEZING = "squeezing"
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
    #: The warlock's mark. Relational for the usual reason -- several
    #: warlock powers read "if the target is cursed", and they mean cursed
    #: *by you*, not cursed by anybody.
    CURSED_BY = "cursed_by"
    #: The ranger's quarry. Relational for the same reason a curse is:
    #: two rangers in a party each have their own.
    QUARRY_OF = "quarry_of"
    #: Granted explicitly by a power. Flanking is *computed*, not stored here.
    GRANTS_CA_TO = "grants_ca_to"
    #: The three that simply name a *second* creature, with no condition
    #: attached. Source is the one in charge -- the master, the mount, the
    #: guard -- and the target is the one it is responsible for. Several
    #: stat blocks print "its master", "its rider", "a creature guarded by
    #: it", and before these there was no way to ask who that was.
    MASTER_OF = "master_of"
    RIDDEN_BY = "ridden_by"
    GUARDED_BY = "guarded_by"
    #: Whose square the source measures its ranged and area attacks from.
    #: Read in `dsl.measured_from`, so it decides what can be aimed at as
    #: well as where line of effect is traced from.
    CASTS_FROM = "casts_from"


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
    def order(self) -> int:
        """Where this sits in the sequence, for "Medium or smaller".

        Not `squares`, which is the same number for Tiny, Small and Medium
        -- so a comparison written against it cannot tell a torch from a
        campfire, and two printed lines turn on exactly that.
        """
        return _ORDER[self]


_FOOTPRINT = {
    Size.TINY: 1,
    Size.SMALL: 1,
    Size.MEDIUM: 1,
    Size.LARGE: 2,
    Size.HUGE: 3,
    Size.GARGANTUAN: 4,
}

_ORDER = {size: n for n, size in enumerate(Size)}


class Cover(IntEnum):
    NONE = 0
    PARTIAL = 2
    SUPERIOR = 5


class Light(StrEnum):
    """How well lit a square is. Absent from `Grid.light` means `BRIGHT`.

    Three values because the books print three, and the two below bright are
    an **attack penalty on whoever is standing there**, not a property of the
    looker: dim light conceals, darkness conceals totally.
    `query.light_concealment` turns a level into a `Cover`, which is the
    existing grade, so the light model buys no second scale.

    A closed enum rather than the free labels `Grid.difficult` carries,
    because difficult going is open-ended -- mud, rubble, ice, and a row may
    invent one -- while there is no fourth light level to invent, and the
    three have an order that `light_concealment` depends on.
    """

    BRIGHT = "bright"
    DIM = "dim"
    DARK = "dark"


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
