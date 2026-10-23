"""General feats: the ones whose prerequisite names no class and no race.

Almost every row here is a trait -- `action=ActionType.NONE`, no trigger --
that installs one modifier for the fight. The prerequisite is a column and
is not written here; only the Benefit is.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    WIS,
    YOU_OR_ONE_ALLY,
    ActionPointSpent,
    ActionType,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Dropped,
    Gear,
    Health,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Relation,
    RelationSet,
    SavingThrow,
    Size,
    Trigger,
    TurnStart,
    When,
    Window,
    World,
    by_melee,
    get,
    power,
)
from combat_engine.engine.components import Defences
from combat_engine.engine.query import distance_between, holding, team

DIVINE = [Keyword.DIVINE]

#: The sizes "Large or larger" means.
_BIG = frozenset({Size.LARGE, Size.HUGE, Size.GARGANTUAN})

#: Weapon groups a projectile feat means, as opposed to a thrown one.
_PROJECTILE = frozenset({"bow", "crossbow", "sling"})


def _tier(level: int, heroic: int, paragon: int, epic: int) -> int:
    """The "this increases at 11th and 21st level" ladder most feats print."""
    return heroic if level < 11 else (paragon if level < 21 else epic)


# -- modifier gates (they are handed a context and nothing else) -------------


def _opportunity(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("opportunity"))


def _charging(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("charge"))


def _with_advantage(ctx: dict[str, Any]) -> bool:
    return bool(ctx.get("advantage"))


def _melee_weapon(ctx: dict[str, Any]) -> bool:
    """A weapon attack made at melee reach, read off the row being resolved.

    The damage context carries no weapon and no attacker, so this is the
    only way to ask -- see the note in AUTHORING.md.
    """
    p = get(ctx.get("power", ""))
    if p is None or Keyword.WEAPON not in p.keywords:
        return False
    reach = getattr(p, "reach", None)
    return reach is not None and reach.kind == "melee"


def _keyworded(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    """"A power that has the fire or the radiant keyword"."""
    want = frozenset(words)
    def gate(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", ""))
        return p is not None and bool(want & frozenset(p.keywords))

    return gate


def _shoots(c: Cast) -> bool:
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(
        w.ranged and w.group in _PROJECTILE for w in gear.held
    )


def _throws(c: Cast) -> bool:
    """Is the caster holding a weapon it can **throw**? `Weapon.thrown`.

    **It read `w.ranged` and that is the other field.** `chargen` splits the
    two columns deliberately and says why: *"a thrown melee weapon is not a
    ranged one: a dagger has a printed range and is still swung, and
    `Gear.ranged` picking it up would hand a rogue a ranged basic attack it
    does not have."* So `ranged` is set only for a weapon that is **fired**
    and `thrown` only for a melee weapon with a printed range.

    Reading `ranged` therefore asked for a *fireable* weapon outside the
    projectile groups, which is backwards twice over:

    * **False for a dagger and a javelin** -- the two examples `f140`'s own
      card prints -- because both are melee, so their range lands in
      `thrown`;
    * **True for a blowgun**, and for five other fired oddities filed under
      `light blade` and `flail`, none of which is a thrown weapon.

    Twelve weapons print a thrown range -- axe, flail, hammer, heavy blade,
    light blade and spear groups -- and this saw none of them.

    The old note on `f140` said "a thrown weapon is a held one that can be
    fired and is not of a projectile group", which was the model before #214
    added `thrown`. The field arrived and the helper did not follow.
    """
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.thrown for w in gear.held)


# -- trigger predicates ------------------------------------------------------


def _anyone_within(squares: int) -> Callable[[World, int, Any], bool]:
    def check(world: World, me: int, ev: Any) -> bool:
        return distance_between(world, me, ev.actor) <= squares

    return check


def _crit_on_me_or_ally(world: World, me: int, ev: Any) -> bool:
    """An enemy crits me, or an ally of mine within 5 squares."""
    if not ev.critical or team(world, ev.attacker) is team(world, me):
        return False
    if ev.target == me:
        return True
    return (
        team(world, ev.target) is team(world, me)
        and distance_between(world, me, ev.target) <= 5
    )


def _friendly_melee_crit(world: World, me: int, ev: Any) -> bool:
    """I or an ally within 5 squares scores a critical hit in melee."""
    if not ev.critical or team(world, ev.attacker) is not team(world, me):
        return False
    if distance_between(world, me, ev.attacker) > 5:
        return False
    return by_melee(world, me, ev)


def _my_kill_within(squares: int) -> Callable[[World, int, Any], bool]:
    def check(world: World, me: int, ev: Any) -> bool:
        return ev.source == me and distance_between(world, me, ev.actor) <= squares

    return check


def _my_natural_20_save(world: World, me: int, ev: Any) -> bool:
    return ev.actor == me and ev.natural == 20


# -- the rows ----------------------------------------------------------------


@power("f3", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3(c: Cast) -> None:
    """The attack context carries `opportunity`, so this is one gated mod."""
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=_opportunity)


@power("f6", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f6(c: Cast) -> None:
    """Two mods, not one: `query.speed` is handed `{"charge": True}` only on
    a charge, and a run's extra squares are their own `"run"` modifier."""
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, when=_charging)
    c.bonus("run", 2, on=c.me, until=When.ENCOUNTER)


@power("f9", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f9(c: Cast) -> None:
    """The damage context carries `charge`. The bull rush half is dropped --
    the engine has no bull rush action to put a bonus on."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=_charging)


@power("f19", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f19(c: Cast) -> None:
    """Only the skill half lands: there is no escape action to make cheaper,
    and `c.grant_action` carries any word but `shift` and `stand` silently."""
    c.bonus("skill:acrobatics", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f27", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f27(c: Cast) -> None:
    """`c.jump` is squares crossed; a running start is not a distinction the
    engine draws, so only the skill bonus is written."""
    c.bonus("skill:athletics", 1, kind="feat", on=c.me, until=When.ENCOUNTER)


#: The four skills the mount rolls off its rider's modifier.
_LENT = ("athletics", "acrobatics", "endurance", "stealth")


def _lend_skills(c: Cast, beast: int, done: set[int]) -> None:
    """Hand the mount the difference between the two modifiers.

    "Using your modifier in place of its own" is a swap, and the engine has
    no swap -- but `skills.modifier` is the same sum for both creatures and
    `c.passive` reads it for either, so the delta laid on the mount comes to
    the rider's number. Only when it is the better one: the card says the
    creature *can*, so a rider who climbs worse than the beast it is sitting
    on lends it nothing.
    """
    if beast in done:
        return
    done.add(beast)
    for skill in _LENT:
        delta = c.passive(skill) - c.passive(skill, of=beast)
        if delta > 0:
            c.bonus(f"skill:{skill}", delta, on=beast, until=When.ENCOUNTER)


@power("f30", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f30(c: Cast) -> None:
    """Riding: waive the mount's attack penalty, and let it use your skill
    modifier for four skills.

    The first half is not a gap. The engine imposes no attack penalty on a
    mount at all -- `c.ride`, `c.mount` and `c.rider` carry the relation and
    nothing anywhere subtracts 2 -- so there is nothing to waive and writing
    it would change no roll.

    The second half is the difference of two `c.passive` readings, laid on
    the mount. Asked again when a mount is taken mid-fight, because "while
    you are riding" is not true at the moment a trait arms; `done` is what
    keeps a remount from lending twice.

    Judgement: `skills.modifier` is the rider's whole modifier, so a feat
    bonus armed before this one is inside the number the card excludes with
    "not including any temporary bonuses". Arming order is the only way it
    can differ and it is worth less than a square of error.
    """
    me = c.me
    done: set[int] = set()

    def mounted(ev: RelationSet) -> None:
        if ev.kind_ is Relation.RIDDEN_BY and ev.target == me:
            _lend_skills(c, ev.source, done)

    beast = c.mount()
    if beast is not None:
        _lend_skills(c, beast, done)
    c.watch(RelationSet, mounted, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} lent skills")


@power("f36", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f36(c: Cast) -> None:
    """Climbing at full speed is a movement mode at the creature's own speed;
    the Athletics check that allows it is the ordinary one."""
    c.mode("climb", c.speed_of(c.me), on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:athletics", 1, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f109", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f109(c: Cast) -> None:
    """`Encounter.start` arms traits before it applies surprise, so refusing
    the condition here is in time to matter."""
    c.immune(Condition.SURPRISED, on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:perception", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


@power("f111", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f111(c: Cast) -> None:
    """Armour proficiency is a build-time permission, not a combat effect."""


@power("f112", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f112(c: Cast) -> None:
    """Armour proficiency is a build-time permission."""


@power("f113", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f113(c: Cast) -> None:
    """Armour proficiency is a build-time permission."""


@power("f114", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f114(c: Cast) -> None:
    """Armour proficiency is a build-time permission."""


@power("f115", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f115(c: Cast) -> None:
    """Armour proficiency is a build-time permission."""


@power("f127", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f127(c: Cast) -> None:
    """`query.defence` is handed the attack context, so a defence may be
    gated on `opportunity` where a damage rider could not be."""
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=_opportunity)


#: Characters whose surge ceiling this file has already lifted, by world and
#: creature. A trait arms at the start of every fight; the sentence is about
#: the character sheet, so it must not climb once an encounter.
_RAISED: dict[tuple[int, int], bool] = {}


@power("f131", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f131(c: Cast) -> None:
    """Two more healing surges, written the way f1085 writes its one:
    `Health.max_surges` is the ceiling a rest refills to, so the pool is
    raised and the two surges handed over in the same breath -- `story`
    clamps `surges` to the sheet's number before the fight, so lifting the
    ceiling alone would give the character nothing to spend."""
    key = (id(c.world), c.me)
    health = c.world.get(c.me, Health)
    if health is None or _RAISED.get(key):
        return
    _RAISED[key] = True
    health.max_surges += 2
    c.regain_surge(2, on=c.me)


@power("f139", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f139(c: Cast) -> None:
    """`"range"` stretches what a ranged line may be aimed at. The long-range
    penalty threshold is read off the weapon's own printed range and is not
    stretched with it, so only the reach half of the line lands."""
    if _shoots(c):
        c.bonus("range", 5, on=c.me, until=When.ENCOUNTER)


@power("f140", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f140(c: Cast) -> None:
    """"A thrown weapon such as a dagger or a javelin", +2 to both ranges.

    As `f139`, and the same half lands: `"range"` stretches what the line
    may be aimed at and the long-range penalty threshold is read off the
    weapon's printed range, which is not stretched with it.

    `_throws` is what changed. It asked `w.ranged`, which is set only for a
    weapon that is **fired**, so this row was False for both of the card's
    own examples and True for a blowgun. See that helper.
    """
    if _throws(c):
        c.bonus("range", 2, on=c.me, until=When.ENCOUNTER)


@power("f145", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f145(c: Cast) -> None:
    c.bonus(FORT, _tier(c.level, 2, 3, 4), kind="feat", on=c.me,
            until=When.ENCOUNTER)


@power("f148", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f148(c: Cast) -> None:
    c.bonus(WILL, _tier(c.level, 2, 3, 4), kind="feat", on=c.me,
            until=When.ENCOUNTER)


@power("f149", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f149(c: Cast) -> None:
    c.bonus(REF, _tier(c.level, 2, 3, 4), kind="feat", on=c.me,
            until=When.ENCOUNTER)


@power("f150", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f150(c: Cast) -> None:
    """Languages. Nothing a fight reads."""


@power("f157", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f157(c: Cast) -> None:
    """Drawing costs no action here already, so the first clause is the
    engine's behaviour. `c.initiative` moves the creature in the order --
    traits are armed after the opening rolls, which is in time."""
    c.initiative(2, on=c.me)


@power("f159", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f159(c: Cast) -> None:
    """Rituals. Not a combat effect."""


@power("f161", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f161(c: Cast) -> None:
    """Shield proficiency is a build-time permission."""


@power("f162", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f162(c: Cast) -> None:
    """Shield proficiency is a build-time permission."""


@power("f165", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f165(c: Cast) -> None:
    """A bonus to one chosen skill and nothing else."""


@power("f166", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f166(c: Cast) -> None:
    """Training in one skill and nothing else."""


@power("f171", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.max_hp()",))
def f171(c: Cast) -> None:
    """5 more hit points, 10 at 11th and 15 at 21st. `c.temp_hp` is a
    different thing and `c.heal` cannot raise a maximum."""


@power("f172", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f172(c: Cast) -> None:
    """A shield bonus, so it does not stack with an actual shield -- which is
    the point of the printed type."""
    if c.wielding("two-weapon"):
        c.bonus(AC, 1, kind="shield", on=c.me, until=When.ENCOUNTER)
        c.bonus(REF, 1, kind="shield", on=c.me, until=When.ENCOUNTER)


@power("f173", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f173(c: Cast) -> None:
    if c.wielding("two-weapon"):
        c.bonus("damage", 1, on=c.me, until=When.ENCOUNTER, when=_melee_weapon)


@power("f178", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f178(c: Cast) -> None:
    """Weapon proficiency is a build-time permission."""


@power("f233", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f233(c: Cast) -> None:
    """+1 feat bonus to damage with one chosen weapon group.

    **Both of the holds this row carried were already answered by `f1032`**,
    which is the same card one line over -- "choose a weapon group", +1 to
    *attack* instead of damage -- and has been written and unmarked
    throughout. The marker here said nothing stores the chosen group and the
    damage context carries no weapon to gate on. Neither is what the row
    needs:

    * the group is **read off the weapon in hand**, which is what the choice
      comes to for a character carrying one, and every chassis carries one.
      `f1032`'s docstring makes that argument and this follows it rather
      than inventing a second answer;
    * the gate asks `holding(...)`, which reads the gear **now**, so the
      damage context never has to carry a weapon at all. It carries `power`,
      which is what the keyword half asks about.

    `kind="feat"` because the card prints "feat bonus", so two feats of this
    shape do not stack -- which is the whole reason the type word matters.
    """
    gear = c.world.get(c.me, Gear)
    arm = gear.main if gear else None
    if arm is None:
        return
    group = arm.group
    c.bonus(
        "damage", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: bool(holding(c.world, c.me, group))
        and (p := get(ctx.get("power", ""))) is not None
        and Keyword.WEAPON in p.keywords,
    )


@power("f238", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f238(c: Cast) -> None:
    """The weapon is read once, when the trait is armed: the attack context
    carries the hand but not the group in it."""
    if c.wielding("light blade"):
        c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=_with_advantage)


@power("f240", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f240(c: Cast) -> None:
    if c.wielding("heavy blade") or c.wielding("light blade"):
        c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=_opportunity)


@power("f245", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f245(c: Cast) -> None:
    """A bonus to untrained skill checks and nothing else."""


@power("f261", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f261(c: Cast) -> None:
    """The trade is offered before each melee swing rather than baked in: it
    is optional, so a standing penalty would be the wrong row. `Window.BEFORE`
    on `AttackDeclared` is the only moment a modifier can still reach the
    roll, and both halves are one-shots so they are spent on that one attack.
    """
    light = _tier(c.level, 2, 4, 6)
    heavy = _tier(c.level, 3, 6, 9)

    def swing(ev: Any) -> None:
        if ev.attacker != c.me or not by_melee(c.world, c.me, ev):
            return
        if not c.may("take the attack penalty for extra damage"):
            return
        c.penalty("attack", 2, on=c.me, until=When.EOT, once=True)
        c.bonus("damage", heavy if c.wielding("two-handed") else light,
                on=c.me, until=When.EOT, once=True)

    c.watch(AttackDeclared, swing, on=c.me, until=When.ENCOUNTER,
            window=Window.BEFORE)


@power("f272", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f272(c: Cast) -> None:
    c.initiative(4, on=c.me)


@power("f274", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f274(c: Cast) -> None:
    """One extra helping of the rogue's rider, once for the fight. The light
    blade requirement of the real feature is not enforced here -- the feat
    prints none -- and the training half is a chargen line."""
    dice = c.sneak_damage()
    if not dice:
        return

    def landed(ev: Any) -> None:
        if ev.attacker == c.me and c.had_advantage(ev):
            c.flat(c.roll(dice), on=ev.target)

    c.watch(Hit, landed, on=c.me, until=When.ENCOUNTER, once=True)


@power("f277", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f277(c: Cast) -> None:
    """An at-will from another class, once per encounter.

    The spec names no ref because it names a *set* -- every 1st-level
    at-will attack power that class has -- and `c.borrow_row` reads the
    set off the registry the way `chargen.loadout` does. The printed
    limit is `uses=1`: handed over bare, an at-will is an unlimited
    extra attack every turn.

    The training half is a chargen line and the implements are the
    header's."""
    c.borrow_row("wizard", level=1, uses=1)


@power("f278", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f278(c: Cast) -> None:
    c.grant_row("f278b", on=c.me, until=When.ENCOUNTER)


@power("f278b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=SELF,
       keywords=DIVINE,
       trigger="a creature within 10 squares of you spends an action point",
       on=Trigger(ActionPointSpent, _anyone_within(10),
                  "a creature within 10 squares spends an action point"))
def f278b(c: Cast) -> None:
    c.extra_action(MOVE, on=c.me)


@power("f281", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f281(c: Cast) -> None:
    c.grant_row("f281b", on=c.me, until=When.ENCOUNTER)


@power("f281b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=Ranged(5),
       target=ONE_CREATURE, keywords=DIVINE,
       trigger="an enemy scores a critical hit against you or an ally within 5 squares",
       on=Trigger(Hit, _crit_on_me_or_ally,
                  "an enemy crits you or an ally within 5 squares"))
def f281b(c: Cast) -> None:
    """Turn the critical into an ordinary hit.

    An immediate interrupt is dispatched in `Window.BEFORE` of its event
    and `resolve.attack` announces `Hit` before any damage is rolled, so
    the crit is still undecided when this runs. `AttackResult.critical`
    is plain and writable -- `c.maximise(critical=True)` promotes a hit
    the same way, from the same window -- and `Cast.crit` reads that
    field, so clearing it is the demotion: ordinary dice, and none of the
    riders a critical pays. The event's own copy is cleared too, for the
    listeners after this one that read it rather than the result.

    It was marked `c.uncrit()`; nothing was missing.
    """
    ev = c.trigger
    ev.critical = False
    if ev.result is not None:
        ev.result.critical = False


@power("f282", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f282(c: Cast) -> None:
    """Gated on the row's keywords rather than the damage type: the printed
    line is about the power, and a fire power may deal none."""
    c.bonus("damage", _tier(c.level, 1, 2, 3), kind="feat", on=c.me,
            until=When.ENCOUNTER,
            when=_keyworded(Keyword.FIRE, Keyword.RADIANT))


@power("f283", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f283(c: Cast) -> None:
    c.grant_row("f283b", on=c.me, until=When.ENCOUNTER)


@power("f283b", level=1, cls="", usage=ENCOUNTER, action=MOVE,
       reach=Melee(1), target=ONE_ALLY, keywords=DIVINE)
def f283b(c: Cast) -> None:
    """Swapping is one operation: either both move or neither does, which is
    what the printed "each shift 1 square, swapping positions" means."""
    if c.target is not None:
        c.swap(c.target, who=c.me)


@power("f284", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f284(c: Cast) -> None:
    c.bonus("damage", _tier(c.level, 1, 2, 3), kind="feat", on=c.me,
            until=When.ENCOUNTER,
            when=_keyworded(Keyword.ACID, Keyword.COLD))


@power("f285", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f285(c: Cast) -> None:
    c.bonus("damage", _tier(c.level, 1, 2, 3), kind="feat", on=c.me,
            until=When.ENCOUNTER,
            when=_keyworded(Keyword.NECROTIC, Keyword.PSYCHIC))


@power("f289", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f289(c: Cast) -> None:
    c.grant_row("f289b", on=c.me, until=When.ENCOUNTER)


@power("f289b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_ALLY, keywords=DIVINE)
def f289b(c: Cast) -> None:
    """"The first attack roll" is a one-shot, so it is spent on the roll."""
    c.bonus("attack", 2, kind="power", until=When.SONT, once=True)


@power("f295", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f295(c: Cast) -> None:
    c.grant_row("f295b", on=c.me, until=When.ENCOUNTER)


@power("f295b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(5), target=YOU_OR_ONE_ALLY, keywords=DIVINE)
def f295b(c: Cast) -> None:
    c.bonus(WILL, 5, kind="power", until=When.SONT)


@power("f296", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f296(c: Cast) -> None:
    c.grant_row("f296b", on=c.me, until=When.ENCOUNTER)


@power("f296b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=Ranged(5), target=SELF, keywords=[Keyword.DIVINE, Keyword.HEALING],
       trigger="you or an ally within 5 squares scores a critical hit with a melee attack",
       on=Trigger(Hit, _friendly_melee_crit,
                  "you or an ally within 5 squares crits in melee"))
def f296b(c: Cast) -> None:
    """The target is the creature that crit, not the caster."""
    if c.trigger is not None:
        c.surge(on=c.trigger.attacker)


@power("f297", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f297(c: Cast) -> None:
    c.grant_row("f297b", on=c.me, until=When.ENCOUNTER)


@power("f297b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(5), target=YOU_OR_ONE_ALLY,
       keywords=[Keyword.DIVINE, Keyword.HEALING])
def f297b(c: Cast) -> None:
    """Regeneration 2 while bloodied. The 11th and 21st level steps are
    out of scope; the project stops at 10."""
    c.regeneration(2, on=c.target, while_bloodied=True)


@power("f298", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f298(c: Cast) -> None:
    c.grant_row("f298b", on=c.me, until=When.ENCOUNTER)


@power("f298b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE)
def f298b(c: Cast) -> None:
    """`Size` is a word, not a number, so "Large or larger" is a set."""

    def big(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.size_of(who) in _BIG

    c.bonus("attack", 2, on=c.me, until=When.EONT, when=big)


@power("f299", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f299(c: Cast) -> None:
    c.grant_row("f299b", on=c.me, until=When.ENCOUNTER)


@power("f299b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=CloseBurst(1), target=EACH_ENEMY,
       keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
       attack=Attack(WIS, vs=WILL))
def f299b(c: Cast) -> None:
    """The burst widens at 11th and 21st level, which the header cannot say;
    the printed 1 is used and the dice carry the rest of the ladder."""
    if not c.is_kind("undead"):
        return
    if c.strike():
        c.damage(f"{_tier(c.level, 1, 2, 3)}d10", c.wis_mod,
                 dtype=DamageType.RADIANT)
        c.dazed(until=When.EONT)


@power("f303", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f303(c: Cast) -> None:
    c.bonus("damage", _tier(c.level, 1, 2, 3), kind="feat", on=c.me,
            until=When.ENCOUNTER,
            when=_keyworded(Keyword.LIGHTNING, Keyword.THUNDER))


@power("f304", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f304(c: Cast) -> None:
    c.grant_row("f304b", on=c.me, until=When.ENCOUNTER)


@power("f304b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=Ranged(10), target=SELF,
       keywords=[Keyword.DIVINE, Keyword.HEALING],
       trigger="your attack reduces an enemy within 10 squares of you to 0 hit points",
       on=Trigger(Dropped, _my_kill_within(10),
                  "your attack drops an enemy within 10 squares"))
def f304b(c: Cast) -> None:
    """The surge is spent by whoever is picked, which may be an ally standing
    near the corpse rather than the caster."""
    if c.trigger is None:
        return
    who = c.choose([c.me, *c.within(5, of=c.trigger.actor, side="ally")],
                   "who spends a healing surge")
    if who is not None:
        c.surge(on=who)


@power("f305", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f305(c: Cast) -> None:
    c.grant_row("f305b", on=c.me, until=When.ENCOUNTER)


@power("f305b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=Ranged(5), target=ONE_CREATURE, keywords=DIVINE,
       trigger="you roll a natural 20 on a saving throw",
       on=Trigger(SavingThrow, _my_natural_20_save,
                  "you roll a natural 20 on a saving throw"),
       dropped=("Effect.subs",))
def f305b(c: Cast) -> None:
    """Hand the effect just saved against to an enemy.

    `SavingThrow` carries no `Effect`, but it carries `against=str(eff)`
    and that rendering opens with `e<id>`, so it names one hold
    uniquely: matching it against the live list on the roller gets the
    object back. `Effects.save` announces the throw **before** it acts on
    the outcome, so the hold is still standing while this runs even
    though the save succeeded, and `Effects.end` is idempotent -- the
    "saved" ending that follows finds the transferred copy already gone
    and does nothing.

    `c.transfer` refuses a hold carrying a relation or a subscription and
    returns None rather than moving half of it; a mark or a watch-backed
    effect therefore stays where it is. That is the one dropped clause.
    """
    foe = c.target
    if foe is None:
        return
    for eff in c.world.effects.of(c.me):
        if str(eff) == c.trigger.against:
            c.transfer(eff, to=foe)
            return


@power("f309", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f309(c: Cast) -> None:
    """Combat advantage with cold powers against whatever is vulnerable to
    cold.

    Two narrowings and the second was the whole hold-up. Reading the
    vulnerability back was never the gap -- `Defences.vulnerable` is a plain
    dict per type, the mirror of the `Defences.resist` that `c.resistances`
    reads, so it is one lookup. The keyword was: combat advantage was computed
    from the pair of creatures alone, with no power anywhere in it, so "only
    when the power has the cold keyword" had nothing to ask. `ca_ctx` carries
    the ref now and `c.gains_advantage` is read with it.

    Laid ungated this row would hand out advantage on every attack the
    character makes, which is why the verb requires a gate.
    """
    def cold_against_the_vulnerable(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power", ""))
        if row is None or Keyword.COLD not in row.keywords:
            return False
        taking = c.world.get(ctx["target"], Defences)
        return taking is not None and taking.vulnerable.get(DamageType.COLD, 0) > 0

    c.gains_advantage(cold_against_the_vulnerable, on=c.me)


@power("f333", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f333(c: Cast) -> None:
    """Another class's heal, once a day -- and the spec does name it by
    ref. The granted row is that class's encounter heal, and inside one
    fight once a day and once a fight are the same limit, so the row's
    own usage carries the cadence. The training and the implement are
    chargen's."""
    c.grant_row("p1455", on=c.me, until=When.ENCOUNTER)


@power("f334", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f334(c: Cast) -> None:
    """A one-shot put in the character's hands rather than a standing bonus:
    the printed line is a free action taken when its owner wants it. The
    weapon-category choice is not stored anywhere, so the bonus is not gated
    on it; the mark lands on hit or miss, which is why it watches the roll."""

    def spend(who: int) -> None:
        c.bonus("attack", 1, on=c.me, until=When.EOT, once=True)

        def swung(ev: Any) -> None:
            if ev.attacker == c.me:
                c.mark(on=ev.target, until=When.EONT)

        c.watch(AttackRolled, swung, on=c.me, until=When.EOT, once=True)

    c.give(fn=spend, on=c.me, uses=1, cost=FREE)


@power("f335", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f335(c: Cast) -> None:
    """Another class's marking power, once per encounter, and the spec
    names it by ref.

    `uses=1` matters here and does not on f333: the granted row is an
    **at-will** on its own card, so handing it over bare would give a
    minor-action mark every turn for one feat rather than once a
    fight."""
    c.grant_row("p805", on=c.me, until=When.ENCOUNTER, uses=1)


@power("f336", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f336(c: Cast) -> None:
    """`c.quarry` is the feature, so this one is writable without a ref. The
    feat shortens the naming to the end of your next turn."""

    def designate(who: int) -> None:
        foes = c.within(10, of=who, side="enemy")
        if foes:
            c.quarry(on=foes[0], until=When.EOTNT)

    c.give(fn=designate, on=c.me, uses=1, cost=MINOR)


@power("f337", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f337(c: Cast) -> None:
    """A pact's at-will as an encounter power.

    Which pact is a choice this character makes about a class it is not
    -- `c.build` reads the caster's own leg and there is no leg for
    another class's fork -- so the pact is not read and the at-will is
    chosen from that class's 1st-level at-wills directly. In this game
    those *are* the pact rows, one per pact, so the set is right even
    though the pact behind it is not recorded."""
    c.borrow_row("warlock", level=1, uses=1)


@power("f338", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f338(c: Cast) -> None:
    """Another class's heal, once a day, named by ref. Same shape as
    f333: the granted row is an encounter power and one fight is one
    day, so it carries its own limit."""
    c.grant_row("p1590", on=c.me, until=When.ENCOUNTER)


@power("f339", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f339(c: Cast) -> None:
    """Swapping one known power for another is a build-time exchange."""


@power("f340", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f340(c: Cast) -> None:
    """A build-time exchange."""


@power("f341", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def f341(c: Cast) -> None:
    """A build-time exchange."""


@power("f363", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f363(c: Cast) -> None:
    if c.wielding("two-weapon"):
        c.bonus("damage", 3, on=c.me, until=When.ENCOUNTER, when=_opportunity)


@power("f396", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f396(c: Cast) -> None:
    """Reloading a load-minor crossbow as a free action.

    **Written.** The old note said loading "is not modelled at all, so
    there is no action to cheapen", and that was true: firing left a
    crossbow loaded forever. `actions._loading` now offers the reload at
    the printed minor and `c.loads_free` is what lowers the price. #675,
    #725.

    `only="crossbow"` is the group, which is what the card names -- and it
    is the group rather than a ref because crossbow is three weapons.
    Nothing else the character carries gets a cheaper reload, and nothing
    else *can* need one: of the ten weapons printing a load property only
    three print the costed `load minor`, and the blowgun is not a crossbow.
    """
    c.loads_free(only="crossbow")


@power("f419", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f419(c: Cast) -> None:
    """+4 to the bull rush attack roll, 6 at 11th and 8 at 21st.

    **Written.** There is a bull rush action for the bonus to sit on now, and
    `as_` rides the attack context so "a bull rush attack roll" is one gate
    rather than a guess.

    The tier steps are read off the level rather than written as three rows,
    the way every other scaling feat bonus in this file is.
    """
    step = 4 + 2 * sum(c.level >= n for n in (11, 21))
    c.bonus("attack", step, kind="feat", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("as_") == "bull_rush")


@power("f433", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f433(c: Cast) -> None:
    """Another class's feature, and the spec names it by ref --
    `cf:warlord-marshal-f3` is declared now, so the whole printed
    benefit is one `c.grant_row`."""
    c.grant_row("cf:warlord-marshal-f3", on=c.me, until=When.ENCOUNTER)


@power("f449", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f449(c: Cast) -> None:
    """Asked at the start of each of the caster's turns, because the printed
    line is a standing condition rather than a one-off count."""

    def look(ev: Any) -> None:
        if ev.actor != c.me:
            return
        if len([e for e in c.enemies() if c.adjacent(e)]) >= 3:
            c.bonus("attack", 1, on=c.me, until=When.EOT)
            c.bonus("damage", 1, on=c.me, until=When.EOT)

    c.watch(TurnStart, look, on=c.me, until=When.ENCOUNTER)
