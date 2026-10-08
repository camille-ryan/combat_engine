"""Head-slot magic items, heroic tier: their Properties and their Powers.

Nothing here declares an item. The level, the price, the slot and the
ladder are columns in `game.db`; nothing in this slot carries an
enhancement bonus, so `c.enhancement` is 0 here and every number below is
the heroic one the card prints. A `Level 11:` line is paragon and out of
scope.

Five judgements run through the file.

* **A skill modifier is real** -- `skills.modifier` reads `skill:<name>`
  off `Mods` -- but the only context it is handed is `{actor, skill}`.
  So "+2 to Perception checks" is written in full, and "+2 to Perception
  checks **to find secret doors**" is written as the same flat modifier
  with `narrative=("skill:perception",)`: the bonus over-applies without
  the circumstance, and the circumstance is not one a fight ever asks for,
  so it is declared inert rather than marked missing.
* **A save carries its effect and not its keywords.** The save gate is
  handed `effect`, so "against ongoing psychic damage" and "against
  effects that daze, stun or dominate" are exact, and "against fear
  effects" is not -- those rows lay the bonus and carry
  `dropped=("SavingThrow.keywords",)`.
* **Languages, literacy, telepathy, disguise and reading a creature's hit
  point total are narrative**, the way `docs/AUTHORING.md` treats lighting
  a lamp. They are `out_of_combat=True`, which is a finished row.
* **An aura of modifiers is a snapshot.** "You and each ally within 5
  squares" has no standing membership test -- `c.aura` carries no
  modifier -- so those rows lay the bonus on whoever is in range when the
  trait arms, and say so.
* **A race survives onto the board only as its traits.** `c.kinds_of`
  reads a *stat block's* type line, so it answers a monster's race and
  never a character's -- only the nineteen races printing an origin
  sentence give a character even a word. A race's traits are
  `rt:<race>-<what>` and are known rows, so a clause naming a race by ref
  is exact and one naming it in words is not.

One item keeps a counter of its own: `i3230` captures souls in seven gems
and two of its powers ask how many are held. The count is an untyped
`"souls"` modifier on the wearer, which is the only number the engine
carries that a `requires=` gate can read back.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AT_WILL,
    CHA,
    DAILY,
    ENCOUNTER,
    FREE,
    INT,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    WILL,
    Ability,
    ActionType,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    DamageType,
    Dropped,
    EffectApplied,
    Fell,
    Hit,
    InitiativeRolled,
    Keyword,
    Melee,
    Miss,
    PowerUsed,
    Ranged,
    SavingThrow,
    SkillCheck,
    Trigger,
    Usage,
    When,
    World,
    both,
    by_charge,
    by_me,
    by_melee,
    get,
    power,
    query,
    targets_me,
)
from combat_engine.engine.basic import RANGED as RANGED_BASIC
from combat_engine.engine.components import Mods, Powers
from combat_engine.engine.durations import keywords_of

ITEM = "item"

#: The five checks a card means by "knowledge or monster knowledge".
_KNOWLEDGE = ("arcana", "dungeoneering", "history", "nature", "religion")


# -- shared reading of the board --------------------------------------------


def _skills(c: Cast, value: int, *names: str, kind: str = "item") -> None:
    """Lay one item bonus per named skill. There is no key for a set."""
    for name in names:
        c.bonus(f"skill:{name}", value, on=c.me, until=When.ENCOUNTER, kind=kind)


def _keyword_gate(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    """Gate on the keywords of the power in the attack context."""

    def gate(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return row is not None and any(w in row.keywords for w in words)

    return gate


def _save_keywords(*words: Keyword) -> Callable[[dict[str, Any]], bool]:
    """Save gate: the row that laid the effect printed one of these. The
    save context gets them from `durations.keywords_of`, which reads the
    effect's label back as a ref."""
    wanted = set(words)

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(wanted & set(ctx.get("keywords", ())))

    return gate


def _ability_gate(ability: Ability) -> Callable[[dict[str, Any]], bool]:
    """"A Charisma attack": the attacking ability is on the row, not the ctx."""

    def gate(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return (
            row is not None
            and row.attack is not None
            and row.attack.ability is ability
        )

    return gate


def _reach_gate(*kinds: str) -> Callable[[dict[str, Any]], bool]:
    """"Against close and area attacks" -- `Range.kind` is the only word
    that tells a burst from a bow, and the damage context has no power
    reach at all, so this is an attack-side gate only."""

    def gate(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return row is not None and row.reach is not None and any(
            row.reach.kind.startswith(k) for k in kinds
        )

    return gate


#: `both` and `either` combine *event* predicates, which take three
#: arguments; a modifier gate takes one dict, so the pair has its own.
def _all_ctx(*gates: Callable[[dict[str, Any]], bool]) -> Callable[
        [dict[str, Any]], bool]:
    def gate(ctx: dict[str, Any]) -> bool:
        return all(g(ctx) for g in gates)

    return gate


def _any_ctx(*gates: Callable[[dict[str, Any]], bool]) -> Callable[
        [dict[str, Any]], bool]:
    def gate(ctx: dict[str, Any]) -> bool:
        return any(g(ctx) for g in gates)

    return gate


def _burning(*types: DamageType) -> Callable[[dict[str, Any]], bool]:
    """Save gate: the effect being saved against burns with one of these."""

    def gate(ctx: dict[str, Any]) -> bool:
        burn = getattr(ctx.get("effect"), "ongoing", None)
        return burn is not None and burn[1] in types

    return gate


def _holding(*conditions: Condition) -> Callable[[dict[str, Any]], bool]:
    """Save gate: the effect being saved against imposes one of these."""
    wanted = set(conditions)

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(wanted & set(getattr(ctx.get("effect"), "conditions", ())))

    return gate


def _ranged_basic(c: Cast) -> Callable[[dict[str, Any]], bool]:
    """"A ranged basic attack" -- the attack context names both the row and
    the creature swinging it, and `Powers` says which row that creature's
    ranged basic is: `rba` for a character, its own line for a monster,
    plus whatever `c.as_basic` has filed under the bow's window."""

    def gate(ctx: dict[str, Any]) -> bool:
        ref = ctx.get("power") or ""
        who = ctx.get("attacker")
        if not ref:
            return False
        known = c.world.get(who, Powers) if who is not None else None
        if known is None:
            return ref == RANGED_BASIC
        return ref in {RANGED_BASIC, known.ranged,
                       *known.instead_of_basic("ranged")}

    return gate


def _carrying_keywords(c: Cast, *words: Keyword) -> Callable[
        [dict[str, Any]], bool]:
    """"While you are affected by a <keyword> power". An effect's label is
    the ref of the row that laid it, so `keywords_of` reads the keywords
    back off whatever is standing on the wearer right now -- the gate is
    asked at read time, not when the trait armed."""
    wanted = set(words)

    def gate(ctx: dict[str, Any]) -> bool:
        return any(wanted <= keywords_of(eff.label)
                   for eff in c.world.effects.of(c.me))

    return gate


def _undead_foe(c: Cast) -> Callable[[dict[str, Any]], bool]:
    """"Against undead enemies", on either side of the roll: the attack
    and the damage context both carry `target`."""

    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return (who is not None and c.is_kind("undead", on=who)
                and who in c.enemies())

    return gate


def _channelled(world: World, me: int, ev: PowerUsed) -> bool:
    """A channelled row being used. The four class features the card names
    are the *permission* to channel; what is used is one of the 115 rows
    that declare `group=CHANNEL_DIVINITY`."""
    row = get(ev.power)
    return ev.actor == me and row is not None and row.group == CHANNEL_DIVINITY


def _granted_swing(world: World, me: int, ev: PowerUsed) -> bool:
    """An ally swinging a basic attack this creature handed over."""
    return ev.granted_by == me and ev.actor != me


def _foe(c: Cast) -> int | None:
    """The other creature in whatever event this row is answering."""
    ev = c.trigger
    for name in ("attacker", "source", "actor"):
        who = getattr(ev, name, None)
        if who is not None and who != c.me:
            return who
    return c.target


def _souls(world: World, eid: int) -> int:
    """How many of the seven gems hold a soul.

    A plain untyped modifier rather than a component, because a
    `requires=` gate is handed `(world, eid)` and `Mods` is the only
    per-creature number it can read without a new component."""
    mods = world.get(eid, Mods)
    return mods.total("souls", {}) if mods is not None else 0


def _gems(c: Cast, delta: int) -> None:
    c.bonus("souls", delta, on=c.me, until=When.ENCOUNTER)


# -- level 1 ----------------------------------------------------------------


@power("i1520x1", level=1, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1520x1(c: Cast) -> None:
    _skills(c, 1, "perception")


# -- level 2 ----------------------------------------------------------------


@power("i1156x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1156x1(c: Cast) -> None:
    """Narrowed to the *basic* shot. The attack context carries `attacker`
    as well as `power`, so the creature's own `Powers.ranged` -- and the
    rows `c.as_basic` filed under the bow's window -- answer which row
    counts, rather than the bonus reaching every ranged attack."""
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_ranged_basic(c))


@power("i1390x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1390x1(c: Cast) -> None:
    """The extra language is narrative, like lighting a lamp."""
    _skills(c, 1, "bluff", "diplomacy")


@power("i2146x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2146x1(c: Cast) -> None:
    """Literacy only."""


@power("i3490p1", level=2, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=Ranged(20), target=ONE_CREATURE, out_of_combat=True)
def i3490p1(c: Cast) -> None:
    """Speaking at a distance, and a malfunction that changes who hears
    you. Neither end of it is a combat effect."""


@power("i663x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       narrative=("skill:diplomacy", "skill:insight"))
def i663x1(c: Cast) -> None:
    """The flat bonus is laid. The larger one is for talking to one sort
    of creature, and talking is not a move: no fight rolls diplomacy, and
    the insight the card means is the reading of a conversation rather
    than anything the board asks. A creature type is not the gap."""
    _skills(c, 1, "diplomacy", "insight")


# -- level 3 ----------------------------------------------------------------


@power("i525x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i525x1(c: Cast) -> None:
    """Detecting magic, which nothing on a board asks, and no Arcana check
    is rolled in a fight for the flat version to reach."""


@power("i888p1", level=3, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you fail a saving throw",
       on=Trigger(SavingThrow,
                  lambda world, me, ev: ev.actor == me and not ev.saved,
                  "you fail a saving throw"))
def i888p1(c: Cast) -> None:
    """"Even if it's lower" is `keep="new"`, which is the default."""
    c.reroll_save(keep="new")


# -- level 4 ----------------------------------------------------------------


@power("i1543x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1543x1(c: Cast) -> None:
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: bool(ctx.get("opportunity")))


@power("i1550x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1550x1(c: Cast) -> None:
    c.bonus(WILL, 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_keyword_gate(Keyword.CHARM))


@power("i3225x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("query.trained()",))
def i3225x1(c: Cast) -> None:
    """`skills.py` has no training model, so "untrained" cannot be asked
    and the blanket `skill` key reaches every check instead."""
    c.bonus("skill", 1, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i3225p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("query.trained()",))
def i3225p1(c: Cast) -> None:
    """Granting training is the whole of the power and nothing is trained
    in the first place."""


@power("i838x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i838x1(c: Cast) -> None:
    """`c.initiative` during arming moves the order itself, which is what
    the number is for."""
    c.initiative(1, on=c.me)


@power("i838p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="initiative is rolled",
       on=Trigger(InitiativeRolled, lambda world, me, ev: ev.actor == me,
                  "initiative is rolled"))
def i838p1(c: Cast) -> None:
    """Swapping with the ally who rolled worst is the only reading of
    "willing" the board can offer."""
    allies = c.allies()
    if allies:
        c.swap_initiative(min(allies, key=lambda a: c.distance(a)))


# -- level 5 ----------------------------------------------------------------


@power("i1004x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       narrative=("skill:insight", "skill:perception"))
def i1004x1(c: Cast) -> None:
    """The Will half is exact. Seeing through an illusion is the other
    circumstance, and it is not the one the engine rolls: perception is
    consulted only against a hider, insight not at all, so laying either
    flat would pay the bonus out for spotting the wrong thing."""
    c.bonus(WILL, 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_keyword_gate(Keyword.ILLUSION))


@power("i1447x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1447x1(c: Cast) -> None:
    _skills(c, 2, "heal")


@power("i1447p1", level=5, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE, out_of_combat=True)
def i1447p1(c: Cast) -> None:
    """Reading a creature's hit points and diseases tells the user
    something and does nothing to anybody."""


@power("i2527x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2527x1(c: Cast) -> None:
    """"Enemies who can see you" is read once, when the trait arms -- the
    same treatment the other standing-presence items here get. The fear
    narrowing comes off the laying row's keywords."""
    c.resist(5, DamageType.NECROTIC, on=c.me)
    _skills(c, 1, "intimidate")
    for foe in c.enemies():
        if c.can_see(foe):
            c.penalty("save", 2, on=foe, until=When.ENCOUNTER,
                      when=_save_keywords(Keyword.FEAR))


@power("i2656x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.passive_only()", "c.surprise_round()"))
def i2656x1(c: Cast) -> None:
    """`skills.passive` is 10 plus the same modifier an active check uses,
    so a passive-only bonus cannot be separated from the rolled one."""
    _skills(c, 2, "perception")


@power("i3230p1", level=5, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i3230p1(c: Cast) -> None:
    """Learning a hit point total is information, not an effect."""


@power("i3230p2", level=5, cls=ITEM, usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you kill a living creature with an attack",
       on=Trigger(Dropped, both(by_me, lambda world, me, ev: ev.dead),
                  "you kill a creature"))
def i3230p2(c: Cast) -> None:
    """Seven gems, one soul each. "A living creature" is unasked: nothing
    on the board says a thing was alive before it stopped being."""
    if _souls(c.world, c.me) < 7:
        _gems(c, 1)


@power("i3230p3", level=5, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.HEALING],
       requires=lambda world, eid: _souls(world, eid) >= 3,
       requires_text="at least three gems must hold a soul")
def i3230p3(c: Cast) -> None:
    c.heal(5 + c.level // 2, on=c.me)
    _gems(c, -2)


@power("i3230p4", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       requires=lambda world, eid: _souls(world, eid) >= 7,
       requires_text="all seven gems must hold a soul",
       dropped=("c.maximise_dice()",))
def i3230p4(c: Cast) -> None:
    """`c.maximise` maxes the whole roll; "up to four of the dice" is the
    half that has no verb, so this is generous rather than absent."""
    c.maximise(on=c.me, until=When.EONT)
    _gems(c, -7)


@power("i878p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i878p1(c: Cast) -> None:
    """A `"range"` modifier is read where a ranged line's reach is worked
    out, so the extra five squares decide what may be aimed at and not
    merely what the body may touch. That reader is handed the row being
    measured, which is what narrows this to the arcane ones."""
    c.bonus("range", 5, on=c.me, until=When.EOT,
            when=_keyword_gate(Keyword.ARCANE))


@power("i938x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i938x1(c: Cast) -> None:
    """Telepathy is a way of talking."""


def _fear_on_ally(world: World, me: int, ev: EffectApplied) -> bool:
    """A save-ends hold laid on an ally by a row printing fear.
    `EffectApplied.label` is that row's ref, which is what `keywords_of`
    reads back."""
    return (
        ev.save_ends
        and ev.target != me
        and query.team(world, ev.target) == query.team(world, me)
        and Keyword.FEAR in keywords_of(ev.label or "")
    )


@power("i938p1", level=5, cls=ITEM, usage=DAILY, action=REACTION,
       reach=Ranged(10), target=ONE_CREATURE,
       trigger="an ally is hit by a fear effect that a save can end",
       on=Trigger(EffectApplied, _fear_on_ally,
                  "an ally takes a save-ends fear effect"),
       )
def i938p1(c: Cast) -> None:
    """The fear half of the trigger now plays, and the save is rolled
    against the triggering hold by its label rather than against whichever
    save-ends effect the ally happens to be carrying first.

    **The race clause plays now.** It was dropped because "nothing reads
    another creature's race" -- which was never true: the ref is on
    `Build.choices` and `c.race_of()` reads it (#411). The ally must be of
    r28, whose racial trait the card names, so an ally of any other race
    gets no save.
    """
    who = getattr(c.trigger, "target", None)
    if who is not None and c.race_of(on=who) == "r28":
        c.save(on=who, against=getattr(c.trigger, "label", "") or "")


# -- level 6 ----------------------------------------------------------------


@power("i1539x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1539x1(c: Cast) -> None:
    """A snapshot of who is within 3 when the fight starts: a modifier
    cannot follow an aura's membership, and `c.aura` carries none."""
    for who in [c.me, *c.within(3, side="ally")]:
        c.bonus("damage", 2, on=who, until=When.ENCOUNTER,
                when=lambda ctx: bool(ctx.get("opportunity")))


@power("i1576x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1576x1(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("charge")))


@power("i2048x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2048x1(c: Cast) -> None:
    _skills(c, 2, "heal", "religion")


@power("i2398x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2398x1(c: Cast) -> None:
    c.bonus(WILL, 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_reach_gate("close", "area"))


@power("i3226x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3226x1(c: Cast) -> None:
    _skills(c, 2, "bluff", "diplomacy")


@power("i3226p1", level=6, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=Ranged(5), target=ONE_CREATURE, keywords=[Keyword.CHARM])
def i3226p1(c: Cast) -> None:
    """"The eyes' level + 5" is the *item's* level, so the roll is made in
    the body: `Attack(printed=)` would take the wearer's level term out.
    The target not knowing it was attacked is narrative."""
    if c.attack(get(c.ref).level + 5, WILL).hit:
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power("i3546x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3546x1(c: Cast) -> None:
    """Telepathy is narrative; the rest is exact, because a save-ends
    effect carries the type of the damage it burns with."""
    c.resist(5, DamageType.NECROTIC, on=c.me)
    c.resist(5, DamageType.POISON, on=c.me)
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_burning(DamageType.NECROTIC, DamageType.POISON))


@power("i841p1", level=6, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i841p1(c: Cast) -> None:
    """Spent as a minor action, so the sense lasts the encounter rather than
    standing permanently -- which is the difference between this and the
    racial grants."""
    c.darkvision()


@power("i976x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i976x1(c: Cast) -> None:
    """Secret doors and hidden passages, not hidden creatures. The flat +2
    that stood here was a bonus to spotting a hider, which the card does
    not print."""


# -- level 7 ----------------------------------------------------------------


@power("i1545p1", level=7, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an attack would blind or deafen you",
       on=Trigger(ConditionApplied,
                  lambda world, me, ev: ev.target == me and ev.condition in (
                      Condition.BLINDED, Condition.DEAFENED),
                  "an attack would blind or deafen you"))
def i1545p1(c: Cast) -> None:
    """`ConditionApplied` is announced, not proposed, so the condition is
    taken off again rather than refused."""
    c.cure(Condition.BLINDED, Condition.DEAFENED, on=c.me)


@power("i1585x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1585x1(c: Cast) -> None:
    """Foraging, and neither skill is rolled on a board."""


@power("i2042x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2042x1(c: Cast) -> None:
    _skills(c, 1, *_KNOWLEDGE)


@power("i2042p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you dislike a knowledge check you made",
       on=Trigger(SkillCheck,
                  lambda world, me, ev: ev.actor == me and ev.skill in _KNOWLEDGE,
                  "you make a knowledge check"))
def i2042p1(c: Cast) -> None:
    """"Use either result" is `keep="best"`, since nobody rerolls to do
    worse on purpose."""
    c.reroll_check(keep="best")


@power("i2047x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2047x1(c: Cast) -> None:
    """`Hit` does not carry which defence was attacked; `AttackRolled`
    does, and it fires whether the blow landed or not, which is what
    "whenever you attack a creature's Will defense" says."""

    def rolled(ev: Any) -> None:
        if ev.attacker != c.me or ev.vs is not WILL:
            return
        c.penalty("save", 1, on=ev.target, until=When.ENCOUNTER, once=True)

    c.watch(AttackRolled, rolled, until=When.ENCOUNTER, on=c.me)


@power("i2177x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2177x1(c: Cast) -> None:
    """The enemies not knowing about it is narrative. Whoever is within 10
    when the fight starts is who it reaches."""
    for foe in c.within(10, side="enemy"):
        c.penalty("skill:insight", 2, on=foe, until=When.ENCOUNTER)


@power("i2177p1", level=7, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Ranged(5), target=NO_TARGET)
def i2177p1(c: Cast) -> None:
    """The advantage is granted to the ally, not to the wearer, which is
    what `to=` is for."""
    allies = [a for a in c.within(5, side="ally") if c.can_see(a)]
    for ally in allies:
        foes = [f for f in c.enemies() if c.adjacent_to(f, ally)]
        if foes:
            c.grants_advantage(on=foes[0], to=ally, until=When.EONT)
            return


@power("i481p1", level=7, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION],
       out_of_combat=True)
def i481p1(c: Cast) -> None:
    """A disguise, with no clause that changes a fight."""


@power("i481p2", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with a charm or illusion attack power",
       on=Trigger(
           Miss,
           lambda world, me, ev: (
               ev.attacker == me
               and (row := get(ev.power)) is not None
               and row.usage in (Usage.ENCOUNTER, Usage.DAILY)
               and bool({Keyword.CHARM, Keyword.ILLUSION} & set(row.keywords))
           ),
           "you miss with a charm or illusion power"))
def i481p2(c: Cast) -> None:
    c.reroll_attack(keep="best")


@power("i725x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.grant_weapon()",))
def i725x1(c: Cast) -> None:
    """The whole property is a new weapon in the wearer's hands --
    proficiency, dice, enhancement and basic-attack standing -- and
    nothing puts one there."""


@power("i725p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a weapon at the end of a charge",
       on=Trigger(Hit, both(by_me, by_charge), "you hit on a charge"))
def i725p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is None:
        return
    c.flat(c.str_mod, on=foe)
    c.push(1, on=foe)
    c.prone(on=foe)


@power("i880x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i880x1(c: Cast) -> None:
    _skills(c, 2, "diplomacy", "intimidate")


@power("i980x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i980x1(c: Cast) -> None:
    _skills(c, 2, "nature", "insight")


# -- level 8 ----------------------------------------------------------------


@power("i1080x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1080x1(c: Cast) -> None:
    _skills(c, 2, "insight", "perception")


@power("i1235x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1235x1(c: Cast) -> None:
    """The save context carries the keywords of the row that laid the
    effect, which is what "the illusion or charm keywords" means."""
    _skills(c, 2, "bluff", "stealth")
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_save_keywords(Keyword.ILLUSION, Keyword.CHARM))


@power("i1268x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1268x1(c: Cast) -> None:
    """"At the start of each encounter" is exactly when a trait arms."""
    c.temp_hp(c.cha_mod, on=c.me)


@power("i1371x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1371x1(c: Cast) -> None:
    """Finding and disabling traps, both halves. The flat +4 that stood
    here was read by the one Perception a fight does consult -- the passive
    a hider is measured against -- which this item does not grant."""


@power("i1371p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=NO_TARGET, todo=("c.disable_trap()",))
def i1371p1(c: Cast) -> None:
    """A trap is a creature to the board -- `c.is_trap` finds one -- and
    there is no verb for taking one out of action with a check."""


@power("i1816p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(1), target=ONE_CREATURE,
       )
def i1816p1(c: Cast) -> None:
    """"Intelligence, Wisdom, or Charisma" is a choice with no downside,
    so it is the best of the three and needs no verb of its own. The
    sustain repeats the attack, which `c.on_sustain` runs with no target of
    its own.

    The borrowed sight is granted **only on a hit**, and for as long as the
    blindness it is borrowed from: the card hangs it on "while the target is
    blinded". Its own half -- not suffering the negatives of blindness -- is
    already true of the caster, who is not the one blinded."""
    best = max(c.int_mod, c.wis_mod, c.cha_mod)
    if c.attack(best + c.level // 2 + 2, WILL).hit:
        c.blinded(until=When.EONT)
        c.darkvision(on=c.me, until=When.EONT)


@power("i2372x1", level=8, cls=ITEM, usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use one of the four class features the card names",
       on=Trigger(PowerUsed, _channelled, "you use a channelled row"))
def i2372x1(c: Cast) -> None:
    """A channelled use *is* marked, by `group=CHANNEL_DIVINITY` on each
    of the rows the four named features hand over -- the features
    themselves are the permission and are never used. 18-20 is a
    `crit_range` of 2, read off the attacker's modifiers with the attack
    context, and both halves gate on the target, which the attack and the
    damage context each carry."""
    undead = _undead_foe(c)
    c.bonus("damage", 0, dice="1d6", dtype=DamageType.RADIANT, on=c.me,
            until=When.EONT, when=undead)
    c.bonus("crit_range", 2, on=c.me, until=When.EONT, when=undead)


@power("i2668x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2668x1(c: Cast) -> None:
    """Low-light vision, standing while the item is worn."""
    c.low_light()


@power("i3470x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3470x1(c: Cast) -> None:
    """Six squares is thirty feet. `Fell` is read back by its emitter, so
    softening the drop and keeping the wearer up are both writable."""
    _skills(c, 2, "stealth")
    c.bonus("escape", 2, on=c.me, until=When.ENCOUNTER, kind="item")
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_holding(Condition.IMMOBILIZED, Condition.RESTRAINED,
                          Condition.SLOWED))

    def landing(ev: Fell) -> None:
        if ev.actor == c.me and ev.squares <= 6:
            ev.soften = max(ev.soften, ev.squares * 10)
            ev.prone = False

    c.watch(Fell, landing, until=When.ENCOUNTER, on=c.me)


@power("i3470p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=CloseBurst(3), target=NO_TARGET, keywords=[Keyword.ZONE],
       todo=("c.silence()",))
def i3470p1(c: Cast) -> None:
    """A zone whose only content is that no sound crosses it. Sound is not
    modelled, so the zone would be an empty shape."""


@power("i693x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.save_order()", "c.skill_circumstance()"))
def i693x1(c: Cast) -> None:
    """Nothing here plays. The light is narrative; the Charisma bonus is
    against one sort of creature, which a check's context has no room
    for; and the rest is *when* a saving throw is rolled -- `Effects`
    rolls them at `TurnEnd` and nothing moves them."""


@power("i883x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i883x1(c: Cast) -> None:
    """The card prints no type word, so the bonus is untyped."""
    c.bonus(WILL, 1, on=c.me, until=When.ENCOUNTER)


@power("i933p1", level=8, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you would be dazed by an attack against your Will",
       on=Trigger(ConditionApplied,
                  lambda world, me, ev: (
                      ev.target == me and ev.condition is Condition.DAZED),
                  "you would be dazed"),
       dropped=("ConditionApplied.vs",))
def i933p1(c: Cast) -> None:
    """Which defence the attack went after is not on the event, so this
    answers a daze from any source."""
    c.cure(Condition.DAZED, on=c.me)


# -- level 9 ----------------------------------------------------------------


@power("i1372x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1372x1(c: Cast) -> None:
    """`SavingThrow.against` is `str(effect)`, which spells out both the
    burn and the conditions -- so the payout can be matched by the same
    words the bonus is gated on."""
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_any_ctx(_burning(DamageType.PSYCHIC),
                          _holding(Condition.DAZED, Condition.STUNNED,
                                   Condition.DOMINATED)))
    words = ("psychic", "dazed", "stunned", "dominated")

    def saved(ev: SavingThrow) -> None:
        if ev.actor == c.me and ev.saved and any(w in ev.against for w in words):
            c.temp_hp(5, on=c.me)

    c.watch(SavingThrow, saved, until=When.ENCOUNTER, on=c.me)


@power("i1449x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1449x1(c: Cast) -> None:
    """Recalling what a creature is, which no fight asks. The flat +3 that
    stood here reached the passive History a monster reads to choose whom
    to go for, and that is not a bonus this item prints."""


@power("i1449p1", level=9, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1449p1(c: Cast) -> None:
    """Learning a creature's origin and keywords is information."""


@power("i1538x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1538x1(c: Cast) -> None:
    """Traits arm before the order is read back, so the allies move too."""
    for who in [c.me, *c.within(5, side="ally")]:
        c.initiative(1, on=who)


@power("i1810x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1810x1(c: Cast) -> None:
    _skills(c, 2, "intimidate")


@power("i1810p1", level=9, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.FEAR],
       trigger="an enemy hits you with a melee attack",
       on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits you"))
def i1810p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is not None:
        c.push(1, on=foe)


@power("i631x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i631x1(c: Cast) -> None:
    """"While affected by a primal polymorph power" is a gate after all:
    an effect's label is the ref of the row that laid it, so the two
    keywords are readable off whatever is standing. No type word is
    printed in front of the Will bonus, so it is untyped."""
    _skills(c, 2, "nature")
    c.bonus(WILL, 1, on=c.me, until=When.ENCOUNTER,
            when=_carrying_keywords(c, Keyword.PRIMAL, Keyword.POLYMORPH))


@power("i979x1", level=9, cls=ITEM, usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p1628",
       on=Trigger(PowerUsed,
                  lambda world, me, ev: ev.actor == me and ev.power == "p1628",
                  "you use that racial power"))
def i979x1(c: Cast) -> None:
    """The racial power is `p1628`, which is declared, so the property
    is an ordinary rider on `PowerUsed`. "Your next attack" is `once=`:
    the bonus is spent by the first roll that could use it rather than
    inside the gate. The level 19 step is out of scope."""
    c.bonus("damage", c.cha_mod // 2, on=c.me, until=When.EONT, once=True)


# -- level 10 ---------------------------------------------------------------


@power("i1512x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i1512x1(c: Cast) -> None:
    """Passing off a disguise is not a combat circumstance. The flat +5
    that stood here landed on the one Bluff a fight rolls -- the one to
    gain combat advantage -- which is a different card entirely."""


@power("i1512p1", level=10, cls=ITEM, usage=AT_WILL, action=STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION],
       out_of_combat=True)
def i1512p1(c: Cast) -> None:
    """A disguise, with no clause that changes a fight."""


@power("i1519x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       narrative=tuple(f"skill:{s}" for s in _KNOWLEDGE))
def i1519x1(c: Cast) -> None:
    """The attack half is exact, and the five knowledge skills take the
    flat bonus. Recalling what a monster is remains the narrower
    circumstance and stays unsaid: arcana, dungeoneering, history, nature
    and religion are never rolled in a fight, so there is nothing for a
    second, larger bonus to attach to."""
    _skills(c, 2, *_KNOWLEDGE)
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_keyword_gate(Keyword.PSYCHIC))


@power("i1519p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1519p1(c: Cast) -> None:
    c.bonus("attack", 2, on=c.me, until=When.EOT, kind="power", once=True,
            when=_ability_gate(INT))


@power("i1541x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1541x1(c: Cast) -> None:
    """Narrowed to fear now the save context carries the laying row's
    keywords. Counted once, when the trait arms: an ally who walks out of
    range keeps it, which is how every aura-shaped item here is written."""
    for who in [c.me, *c.within(10, side="ally")]:
        c.bonus("save", 2, on=who, until=When.ENCOUNTER, kind="item",
                when=_save_keywords(Keyword.FEAR))


@power("i1541p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you grant an ally a basic attack",
       on=Trigger(PowerUsed, _granted_swing, "an ally swings one you gave"),
       dropped=("c.pre_empt(ref, clause)",))
def i1541p1(c: Cast) -> None:
    """`PowerUsed.granted_by` names the granter, so the trigger is
    declared, and `c.extra_action` drops the standard action into the
    ally's budget where `Encounter.can` reads it back.

    Withdrawing the granted swing is the half with no verb: nothing takes
    back an attack another row is in the middle of handing over, so the
    ally is offered the standard action *beside* the basic attack rather
    than in place of it, which is generous rather than absent."""
    ally = getattr(c.trigger, "actor", None)
    if ally is None:
        return
    c.extra_action(STANDARD, on=ally)
    c.bonus("damage", 2, on=ally, until=When.EOT, kind="power")


@power("i1548p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you use a melee at-will attack power",
       on=Trigger(
           PowerUsed,
           lambda world, me, ev: (
               ev.actor == me
               and (row := get(ev.power)) is not None
               and row.usage is Usage.AT_WILL
               and row.reach is not None
               and row.reach.kind == "melee"
           ),
           "you make a melee at-will attack"))
def i1548p1(c: Cast) -> None:
    """`PowerUsed` fires before the body, which is the right moment: the
    maximum has to be standing before the damage is rolled."""
    c.dazed(on=c.me, until=When.EONT)
    c.maximise(on=c.me, until=When.EOT)
    if c.may("make the damage fire"):
        c.deals(DamageType.FIRE, on=c.me, until=When.EOT)


@power("i1678x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1678x1(c: Cast) -> None:
    _skills(c, 2, "arcana", "history", "religion")


@power("i1678p1", level=10, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=NO_TARGET, out_of_combat=True)
def i1678p1(c: Cast) -> None:
    """A ritual that gives a direction and a distance in miles."""


@power("i1709x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i1709x1(c: Cast) -> None:
    _skills(c, 2, "diplomacy", "insight")
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_keyword_gate(Keyword.CHARM, Keyword.ILLUSION))


@power("i1709p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i1709p1(c: Cast) -> None:
    c.bonus("attack", 2, on=c.me, until=When.EOT, kind="power", once=True,
            when=_ability_gate(CHA))


@power("i2450p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you dislike a Bluff or Stealth check you made",
       on=Trigger(SkillCheck,
                  lambda world, me, ev: (
                      ev.actor == me and ev.skill in ("bluff", "stealth")),
                  "you make a Bluff or Stealth check"))
def i2450p1(c: Cast) -> None:
    c.reroll_check(keep="best", bonus=3)


@power("i3229x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3229x1(c: Cast) -> None:
    """Languages only."""


@power("i831x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i831x1(c: Cast) -> None:
    """Breathing water. Drowning is not a rule the engine keeps."""


@power("i887x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       )
def i887x1(c: Cast) -> None:
    """Three clauses, each gated on a nearby ally's race, and all three play.

    **The ref'd one now plays.** A race's traits are `rt:<race>-<what>`
    and land in the character's known rows, which is the only place a
    race ref survives onto the board, so "an r3 ally" is exact.

    **The race clauses play now.** They asked `c.is_kind`, which reads a
    *stat block's* type line -- so they answered for a monster ally and
    never for a character, which is every ally a character usually has.
    `c.race_of()` is the reader they were waiting on and it existed as a
    marker on this row (#411). Both are asked: a monster of that race does
    satisfy the card, and it carries the word rather than a race ref.

    The third clause was also being read off the second's gate, which gave
    the wrong ally's race the Perception bonus."""
    near = c.within(10, side="ally")
    if any(c.race_of(on=a) == "r3" for a in near):
        c.bonus("save", 5, on=c.me, until=When.ENCOUNTER, kind="item",
                when=_save_keywords(Keyword.CHARM))
    if any(c.race_of(on=a) == "r4" or c.is_kind("elf", on=a) for a in near):
        for who in [c.me, *c.within(5, side="ally")]:
            c.bonus("skill:perception", 1, on=who, until=When.ENCOUNTER,
                    kind="item")


@power("i985x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i985x1(c: Cast) -> None:
    _skills(c, 2, "diplomacy", "insight")


@power("i985p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i985p1(c: Cast) -> None:
    """Two item bonuses, and the same-type rule keeps the larger -- which
    is exactly what "this bonus increases to +3" means."""
    c.bonus("attack", 2, on=c.me, until=When.EOT, kind="item",
            when=_ability_gate(CHA))
    c.bonus("attack", 3, on=c.me, until=When.EOT, kind="item",
            when=_all_ctx(_ability_gate(CHA), _keyword_gate(Keyword.CHARM)))
