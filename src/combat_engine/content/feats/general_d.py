"""General feats, fourth batch: the martial ones and the borrowed class
features.

Two recurring shapes, and the second is the one to know about.

**"You gain class X's named class feature."** Five rows in this batch are
nothing but that sentence, and the feature is named in prose with no ref
-- `cf:` refs exist and the `class_feature` table was imported, but the
prerequisite parser could not resolve these names either, which is why
each of them also carries two opaque `q` terms. They are marked, not
guessed at.

**"Once per encounter, when ...".** An encounter-limited *trigger*, which
is a declared `on=` plus `usage=ENCOUNTER` -- the budget does the
limiting, so the body never counts anything itself.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    WILL,
    Ability,
    ActionPointSpent,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Dropped,
    Hit,
    Keyword,
    MoveStart,
    Trigger,
    When,
    power,
)
from combat_engine.engine.query import team

DIVINE = [Keyword.DIVINE]


def _ally_spent_a_point(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor != me and team(world, ev.actor) == team(world, me)


def _attacks_past_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return (
        ev.attacker != me
        and team(world, ev.attacker) != team(world, me)
        and ev.target != me
    )


def _shifts_beside_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    from combat_engine.engine.query import distance_between

    return (
        ev.actor != me
        and getattr(ev, "kind_", "") == "shift"
        and team(world, ev.actor) != team(world, me)
        and distance_between(world, me, ev.actor) <= 1
    )


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _i_dropped_them(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return getattr(ev, "by", None) == me or getattr(ev, "source", None) == me


@power("f801", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.shift_as(first_turn=)",))
def f801(c: Cast) -> None:
    """The initiative half. "During your first turn you can shift as a
    minor" needs a duration that ends when that turn does, and
    `c.shift_as` holds until a stance replaces it -- which would hand the
    character a free shift every round for the rest of the fight."""
    c.initiative(2, on=c.me)


@power("f802", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f802(c: Cast) -> None:
    """A plain "+5 bonus", so untyped. Against two named conditions, which
    the save context reaches by the effect's label."""
    c.bonus(
        "save", 5, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: any(
            w in str(ctx.get("against", "")).lower()
            for w in ("slowed", "immobilized")
        ),
    )


@power("f911", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f911(c: Cast) -> None:
    c.grant_row("f911b", on=c.me, until=When.ENCOUNTER)


@power("f911b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=NO_TARGET,
       keywords=[Keyword.WEAPON],
       trigger="an adjacent enemy shifts or attacks without including you",
       on=(
           Trigger(Hit, _attacks_past_me, "an adjacent enemy attacks somebody else"),
           Trigger(MoveStart, _shifts_beside_me, "an adjacent enemy shifts"),
       ))
def f911b(c: Cast) -> None:
    """Both halves of the printed trigger, because `on=` takes a sequence
    and declaring one of two looks finished.

    The shift half is on `MoveStart` and not `MoveEnd` deliberately: by
    the end of a shift the enemy has left, so "an **adjacent** enemy
    shifts" is false at exactly the moment the row should fire.
    """
    who = getattr(c.trigger, "attacker", None) or c.trigger.actor
    if c.adjacent(who):
        c.basic(on=who)


@power("f915", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally who can see you spends an action point",
       on=Trigger(ActionPointSpent, _ally_spent_a_point, "an ally spends a point"))
def f915(c: Cast) -> None:
    """Temporary hit points equal to 1 + half your level."""
    c.temp_hp(1 + c.stats.level // 2, on=c.trigger.actor)


@power("f918", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally you can see spends an action point to attack",
       on=Trigger(ActionPointSpent, _ally_spent_a_point, "an ally spends a point"))
def f918(c: Cast) -> None:
    """A plain "+1 bonus" to that ally's next attack roll, so untyped."""
    c.bonus("attack", 1, on=c.trigger.actor, until=When.EONT, once=True)


@power("f917", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f917(c: Cast) -> None:
    """Charisma to AC against one opportunity attack a fight. The attack
    context carries `opportunity`, so the gate is a one-liner; `once`
    spends it on the first such attack, which is the printed limit."""
    c.bonus(
        AC, c.cha_mod, on=c.me, until=When.ENCOUNTER, once=True,
        when=lambda ctx: ctx.get("opportunity", False),
    )


@power("f919", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Weapon.off_hand_anyway",))
def f919(c: Cast) -> None:
    """Lets any one-handed weapon count as an off-hand one. `Gear.off` and
    `two_weapon` read the weapon's own properties and there is nothing
    that rewrites them for a character."""


@power("f941", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f941(c: Cast) -> None:
    """A skill bonus after a critical hit. The trigger is in a fight; the
    benefit is not."""


@power("f942", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.opportunity_instead()",))
def f942(c: Cast) -> None:
    """Shift instead of making the opportunity attack. The window offers
    an attack and nothing else can be put in it."""


@power("f943", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f943(c: Cast) -> None:
    c.grant_row("f943b", on=c.me, until=When.ENCOUNTER)


@power("f943b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=CloseBurst(1), target=EACH_ENEMY,
       keywords=[Keyword.DIVINE, Keyword.IMPLEMENT], group=CHANNEL_DIVINITY,
       attack=Attack(Ability.WIS, vs=WILL))
def f943b(c: Cast) -> None:
    """A push on a hit *and* on a miss -- the only difference is the
    penalty, so the push is written once outside the branch."""
    hit = c.strike().hit
    c.push(1)
    if hit:
        c.penalty("attack", 2, until=When.EONT)


@power("f945", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f945(c: Cast) -> None:
    """Two feat bonuses against the same two printed effect families, read
    off the label the effect carries."""
    charm_or_fear = lambda ctx: any(  # noqa: E731
        w in str(ctx.get("against", "")).lower() for w in ("charm", "fear")
    )
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="feat",
            when=charm_or_fear)
    c.bonus(WILL, 1, on=c.me, until=When.ENCOUNTER, kind="feat",
            when=charm_or_fear)


@power("f946", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_skill_check()",))
def f946(c: Cast) -> None:
    """Turns on a Bluff check made in combat to gain combat advantage.
    `SkillCheck` is announced, but nothing says a check was made *for*
    combat advantage, and nothing grants it from one."""


@power("f947", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you score a critical hit",
       on=Trigger(Hit, _i_crit, "you score a critical hit"))
def f947(c: Cast) -> None:
    c.penalty("attack", 2, on=c.trigger.target, until=When.EONT)


@power("f949", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.forgo_shield()",))
def f949(c: Cast) -> None:
    """Trades the shield's bonus to AC and Reflex for damage. `Gear.shield`
    is a flag read at spawn into the defence, and nothing turns it off for
    a round."""


@power("f950", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you reduce an enemy to 0 hit points",
       on=Trigger(Dropped, _i_dropped_them, "you drop an enemy"))
def f950(c: Cast) -> None:
    for defence in (AC, WILL):
        c.bonus(defence, 1, on=c.me, until=When.EONT, kind="feat")
    c.bonus("fort", 1, on=c.me, until=When.EONT, kind="feat")
    c.bonus("ref", 1, on=c.me, until=When.EONT, kind="feat")


@power("f951", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Weapon.double",))
def f951(c: Cast) -> None:
    """Makes one printed weapon a double weapon -- two ends, each with its
    own die and properties. `Weapon` is one set of numbers."""


@power("f910", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f910(c: Cast) -> None:
    """Grants a named class feature of another class. Named in prose with
    no `cf:` ref -- the two opaque terms in its own prerequisite are the
    same gap seen from the other side."""


@power("f913", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f913(c: Cast) -> None:
    """Same shape as f910, a different class feature."""


@power("f914", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f914(c: Cast) -> None:
    """Same shape as f910, a different class feature."""


@power("f916", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.borrow_feature()",))
def f916(c: Cast) -> None:
    """Same shape as f910: a skill training, which is out of combat, and a
    named class feature with no ref."""
