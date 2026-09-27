"""General feats, the seventh batch: races, abilities and a few gates
that are nothing at all.

There is still no race on a character, and none of it matters for the
*benefit*: the prerequisite is a column `chargen.meets` enforces at
build time, and `AUTHORING.md` says outright that a gate the engine
cannot express is not a reason to skip a feat.

What decides each row is how the thing it rides on arrives. A **ref**
-- `p1449`, `p2473`, `p2480`, `p1831`, `p5599`, `m5139a3` -- makes a
rider on it an ordinary trigger, and the `has pNNNN` half of a gate
counts: it pins the power the benefit line only names. A power that
arrives as a **name** and nowhere else carries `c.on_racial_power()`.

Three smaller families come out of this batch.

*"While you are under the effect of your <racial power>"* is six rows.
Nothing asks which row laid an effect that is standing on a creature,
so they carry `c.effects_on()`.

*"You gain a benefit with any of the following exploits you possess"*
is nine rows whose page prints the preamble and the Associated Powers
list and **no clause per power**. There is a resolved list of refs and
nothing to hang on it, which is `feat.associated_powers` -- the same
marker `f974` carries for the same reason.

And `c.bonus("initiative", ...)` is not a thing: `c.initiative`'s own
docstring says the component is read before the d20 and a modifier is
never consulted. The three rows here that print an initiative bonus
call `c.initiative` instead.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.feats.exploits import _riders
from combat_engine.content.feats.styles import among
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    Ability,
    ActionType,
    Attack,
    AttackRolled,
    Bloodied,
    Cast,
    Condition,
    DamageType,
    Defences,
    Dropped,
    Gear,
    Hit,
    Keyword,
    Melee,
    Powers,
    PowerUsed,
    SavingThrow,
    Trigger,
    Usage,
    When,
    about_me,
    by_me,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies, distance_between, enemies, team

#: A racial power the benefit line names in prose and no gate pins.
RACIAL = ("c.on_racial_power()",)
#: Nothing announces that a roll is a reroll, so a rider on one cannot
#: find its moment. `f216` and `f217` carry the same.
REROLL = ("c.on_reroll()",)
#: Which weapons and implements a character may pick up is settled when
#: it is built, and a `Cast` runs with the gear already in hand.
PROFICIENCY = ("chargen.proficiency()",)
#: The preamble and a list of refs, with no clause printed per ref.
ASSOCIATED = ("feat.associated_powers",)
#: "While you are under the effect of your <power>." Nothing asks which
#: row laid a live effect.
UNDER = ("c.effects_on()",)
#: A class feature named in prose, with no ref anywhere in the row.
FEATURE = ("c.class_feature()",)


def _used(ref: str):  # noqa: ANN202
    """A trigger predicate: I used that row."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _hit_with(ref: str):  # noqa: ANN202
    """A trigger predicate: I hit with that row."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me and ev.power == ref

    return when


def _has(ctx: dict[str, Any], *wanted: Keyword) -> bool:
    """Does the row being rolled carry any of these keywords?

    Both the attack and the damage context carry `power` as a ref, which
    is the only thing either carries about what is being used.
    """
    p = get(ctx.get("power", ""))
    return p is not None and any(k in p.keywords for k in wanted)


def _undead(c: Cast, who: int | None) -> bool:
    return who is not None and c.is_kind("undead", on=who)


# -- resistances, which `c.resist` adds to rather than replaces -------------


@power("f615", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f615(c: Cast) -> None:
    """"Increase the resist value by 5" is the bare +5: `c.resist` adds to
    whatever is already standing on the creature rather than setting it.
    `c.element` is where a build's elemental choice is recorded, and with
    no choice there is nothing to increase -- which is the printed "(if
    any)" rather than a gap."""
    dt = c.element(on=c.me)
    if dt is not None:
        c.resist(5, dt, on=c.me)


@power("f632", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f632(c: Cast) -> None:
    """Three flat resistances "regardless of your manifestation", so
    unlike f615 nothing is read first."""
    for dt in (DamageType.COLD, DamageType.FIRE, DamageType.THUNDER):
        c.resist(5, dt, on=c.me)


@power("f920", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f920(c: Cast) -> None:
    """"If you have resistance to fire" is asked of `Defences.resist`,
    which is the flat table `c.resist` writes into.

    The save penalty is laid on each enemy rather than on me, because
    `durations` reads the *saving* creature's own modifiers -- and the
    context it builds carries the effect, so "ongoing fire damage from
    one of your powers" is three keys rather than a guess at a label.
    """
    me = c.me
    held = c.world.get(me, Defences)
    if held is not None and held.resist.get(DamageType.FIRE, 0) > 0:
        c.resist(2, DamageType.FIRE, on=me)

    def mine_and_burning(ctx: dict[str, Any]) -> bool:
        eff = ctx.get("effect")
        return (
            ctx.get("dtype") is DamageType.FIRE
            and eff is not None
            and getattr(eff, "source", None) == me
        )

    for foe in enemies(c.world, me):
        c.penalty("save", 1, on=foe, until=When.ENCOUNTER, when=mine_and_burning)


@power("f924", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.immune(when=)",))
def f924(c: Cast) -> None:
    """The resistance half plays. The immunity is dropped rather than
    written wide: `c.immune` takes no `when=`, and slow and immobilize
    immunity with the "caused by cold powers" clause thrown away is
    strictly stronger than the card."""
    held = c.world.get(c.me, Defences)
    if held is not None and held.resist.get(DamageType.COLD, 0) > 0:
        c.resist(3, DamageType.COLD, on=c.me)


@power("f1073", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1073(c: Cast) -> None:
    """The language is not a fight; the resistance is."""
    c.resist(2, DamageType.NECROTIC, on=c.me)


# -- standing bonuses -------------------------------------------------------


@power("f622", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f622(c: Cast) -> None:
    c.bonus(FORT, 1, on=c.me, until=When.ENCOUNTER, kind="feat")
    c.bonus(WILL, 1, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f625", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f625(c: Cast) -> None:
    """"Doesn't stack if more than one character with this feat is
    adjacent" is what `kind=` is for: two bonuses of a type do not add
    and the larger wins, so naming the kind after the row makes the
    printed restriction the ordinary stacking rule.

    Adjacency and the ally's state are asked per roll, not at arming:
    an ally goes down in the middle of a round and people move.
    """
    me = c.me
    for friend in allies(c.world, me):

        def needs(ctx: dict[str, Any], who: int = friend) -> bool:
            return c.adjacent(to=who) and (
                c.bloodied(on=who)
                or c.is_(Condition.UNCONSCIOUS, on=who)
                or c.is_(Condition.HELPLESS, on=who)
            )

        for what in (AC, FORT, REF, WILL, "save"):
            c.bonus(
                what, 2, on=friend, until=When.ENCOUNTER, kind=c.ref, when=needs
            )


@power("f626", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f626(c: Cast) -> None:
    """Asked per throw: a character that spends its point mid-fight is
    meant to gain this for the rest of the fight."""
    me = c.me
    c.bonus(
        "save", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.action_points(of=me) == 0,
    )


@power("f927", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("SavingThrow.keywords",))
def f927(c: Cast) -> None:
    """The Endurance half is not a fight. The save half is narrowed as
    far as the save context reaches: it carries the *ongoing damage
    type* of the effect being saved against and no keywords, so poison
    ongoing damage is covered and a poison effect that deals none is
    the dropped half."""
    c.bonus(
        "save", 4, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: ctx.get("dtype") is DamageType.POISON,
    )


@power("f934", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f934(c: Cast) -> None:
    """`c.is_kind` reads the creature's printed type words, which is what
    "the spider keyword" means on a monster."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (t := ctx.get("target")) is not None
        and c.is_kind("spider", on=t),
    )


@power("f1004", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=PROFICIENCY)
def f1004(c: Cast) -> None:
    """The damage half plays; the proficiency grant is dropped, as `f64`
    and `f69` drop the same sentence. A character that cannot hold the
    weapon simply never meets the gate."""
    me = c.me

    def two_handed(ctx: dict[str, Any]) -> bool:
        gear = c.world.get(me, Gear)
        return (
            gear is not None
            and any(w.two_handed for w in gear.melee)
            and _has(ctx, Keyword.WEAPON)
        )

    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, kind="feat", when=two_handed)


@power("f1076", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1076(c: Cast) -> None:
    """The Streetwise half is not a fight. `opportunity` is in the attack
    context precisely so "against opportunity attacks" is sayable, and
    `c.moving_as` holds what a creature is doing past the end of the
    move -- which is when the opening is taken."""
    me = c.me

    def running(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("opportunity", False)) and c.moving_as("run", on=me)

    c.bonus(AC, 2, on=me, until=When.ENCOUNTER, kind="feat", when=running)
    c.bonus(REF, 2, on=me, until=When.ENCOUNTER, kind="feat", when=running)


@power("f1090", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1090(c: Cast) -> None:
    """"Radiant prayers" is both keywords at once, so the two questions
    are asked separately rather than with one `any`."""
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: _has(ctx, Keyword.DIVINE)
        and _has(ctx, Keyword.RADIANT)
        and _undead(c, ctx.get("target")),
    )


@power("f1092", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1092(c: Cast) -> None:
    """A damage type is a keyword as well as a type, which is why the
    gate reads the power's keywords rather than the context's `dtype`:
    the card says "a power that has the cold or necrotic keyword", not
    "damage that is cold"."""
    me = c.me
    c.bonus(
        "damage", 1, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _has(ctx, Keyword.COLD, Keyword.NECROTIC),
    )


@power("f1104", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1104(c: Cast) -> None:
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f1116", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1116(c: Cast) -> None:
    """"All your arcane encounter attack powers are expended" is asked
    per damage roll rather than once, because the card's own duration is
    "until you regain the use of one" -- a standing modifier laid at
    arming could never come back off."""
    me = c.me

    def dry(ctx: dict[str, Any]) -> bool:
        rolled = get(ctx.get("power", ""))
        if (
            rolled is None
            or rolled.attack is None
            or rolled.usage is not Usage.AT_WILL
            or Keyword.ARCANE not in rolled.keywords
        ):
            return False
        held = c.world.get(me, Powers)
        if held is None:
            return False
        encounters = [
            row
            for ref in held.known
            if (row := get(ref)) is not None
            and row.attack is not None
            and row.usage is Usage.ENCOUNTER
            and Keyword.ARCANE in row.keywords
        ]
        return bool(encounters) and all(
            held.used.get(row.ref, 0) >= row.uses for row in encounters
        )

    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, when=dry)


@power("f1127", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1127(c: Cast) -> None:
    """"The off-hand implement's enhancement bonus" -- the smaller of the
    two, since the main hand is whichever the attack is already adding.
    Read at arming because a character does not swap hands mid-fight and
    `Gear` names no off hand to read per roll."""
    gear = c.world.get(c.me, Gear)
    magic = sorted(w.enhancement for w in (gear.held if gear else []) if w.enhancement)
    if len(magic) < 2:
        return
    c.bonus(
        "damage", magic[0], on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _has(ctx, Keyword.ARCANE),
    )








# -- initiative, which is a component rather than a modifier ----------------


@power("f1031", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.max_surges()",))
def f1031(c: Cast) -> None:
    """`c.initiative`, not `c.bonus("initiative", ...)`: the component is
    read before the d20 and a modifier to it is never consulted. The
    extra healing surge is dropped -- `Health.max_surges` is set when the
    character is built and nothing raises it."""
    c.initiative(3, on=c.me)


@power("f1074", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1074(c: Cast) -> None:
    """Rolling an Intimidate check twice is narrative; the initiative
    bonus is why this is not an `out_of_combat` row."""
    c.initiative(2, on=c.me)


# -- riders on a racial power that arrives as a ref -------------------------


@power("f616", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1449",
       on=Trigger(PowerUsed, _used("p1449"), "you use that racial power"))
def f616(c: Cast) -> None:
    """Bloodied and alone. `query.allies` never includes the creature
    itself, so nothing has to be subtracted from the count."""
    me = c.me
    if not c.bloodied(on=me):
        return
    near = [
        friend
        for friend in allies(c.world, me)
        if distance_between(c.world, me, friend) <= 5
    ]
    if not near and c.may("spend a healing surge", who=me):
        c.surge(on=me)


@power("f628", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f628(c: Cast) -> None:
    """"Before you first become bloodied, and not again even if healed"
    is a fact about the whole fight, so this is a trait with two
    watchers rather than a triggered row: a row declared `on=` could ask
    whether the caster is bloodied *now* and would pay out again after a
    heal, which is the one case the card spells out."""
    me = c.me
    bled = [c.bloodied(on=me)]

    def remember(ev: Any) -> None:
        if ev.actor == me:
            bled[0] = True

    def spent(ev: Any) -> None:
        if ev.actor == me and ev.power == "p1449" and not bled[0]:
            for defence in (AC, FORT, REF, WILL):
                c.bonus(defence, 1, on=me, until=When.EONT)

    c.watch(Bloodied, remember, on=me, until=When.ENCOUNTER)
    c.watch(PowerUsed, spent, on=me, until=When.ENCOUNTER)


@power("f937", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2473",
       on=Trigger(PowerUsed, _used("p2473"), "you use that racial power"))
def f937(c: Cast) -> None:
    """The benefit line names the power in prose, but the gate pins it as
    `has p2473` -- the same row, so this is an ordinary trigger rather
    than one of the `c.on_racial_power()` family."""
    c.shift(2)


@power("f1060", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p2480",
       on=Trigger(Hit, _hit_with("p2480"), "you hit with that racial power"))
def f1060(c: Cast) -> None:
    """Declared on the hit, not the use: "whenever you hit a target"."""
    c.push(1, on=c.trigger.target)


@power("f1122", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=PROFICIENCY,
       trigger="you hit with p1831",
       on=Trigger(Hit, _hit_with("p1831"), "you hit with that racial power"))
def f1122(c: Cast) -> None:
    """Twice the enhancement of the magic implement in hand. Whether that
    implement is one *your arcane class* may use is a proficiency
    question settled when the character is built, and is the dropped
    half -- a character holding an implement it cannot use never gets
    here in play."""
    magic = [w.enhancement for w in c.held(what="magic") if w.enhancement]
    if magic:
        c.flat(2 * max(magic), on=c.trigger.target)


@power("f1059", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.widen_area()",))
def f1059(c: Cast) -> None:
    """The critical rider plays. Widening one named power's burst is the
    dropped half: `c.widen_areas` widens *every* close attack the
    creature makes, which is strictly more than the card, and nothing
    rewrites the reach of a single row."""
    me = c.me

    def on_crit(ev: Any) -> None:
        if ev.attacker == me and ev.critical and ev.power == "p5599":
            c.ongoing(5, on=ev.target)

    c.watch(Hit, on_crit, on=me, until=When.ENCOUNTER)


@power("f997", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you are bloodied",
       on=Trigger(Bloodied, about_me, "you become bloodied"))
def f997(c: Cast) -> None:
    """`Bloodied` is announced on the crossing and only then, which is
    the printed "the first time"."""
    c.bonus("attack", 2, on=c.me, until=When.EONT)


@power("f936", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you reduce an enemy to 0 hit points",
       on=Trigger(Dropped, by_me, "you drop a creature"))
def f936(c: Cast) -> None:
    """`Dropped.source` is who struck the blow, which is what `by_me`
    reads here. `query.enemies` filters out the dead, so the side is
    compared with `team` directly -- the creature this is about is on
    the floor by the time the row runs."""
    me = c.me
    who = c.trigger.actor
    if team(c.world, who) != team(c.world, me):
        c.bonus("attack", 1, on=me, until=When.EONT, kind="feat")


@power("f1017", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you drop to 0 hit points or fewer",
       on=Trigger(Dropped, about_me, "you go down"))
def f1017(c: Cast) -> None:
    """`about_me` reads `ev.actor`, which on `Dropped` is the creature
    that went down -- the right field here, where `by_me` would read the
    killer."""
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER)
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER)


@power("f1014", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you make a saving throw",
       on=Trigger(SavingThrow, about_me, "you make a saving throw"))
def f1014(c: Cast) -> None:
    """"The first time each encounter" is `usage=ENCOUNTER`: a declared
    trigger goes through `dsl.usable` and `dsl.use` like any other row,
    so the one use is the once. `SavingThrow` is announced before it is
    acted on, which is what makes `c.reroll_save` mean anything."""
    c.reroll_save(keep="best")


@power("f1015", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you make an attack roll",
       on=Trigger(AttackRolled, by_me, "you make an attack roll"))
def f1015(c: Cast) -> None:
    """Same shape as f1014 from the attack side. "Use either result" is
    `keep="best"`; the other printed form is "use the new result even if
    it is worse", which is not this one."""
    c.reroll_attack(keep="best")


@power("f923", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.counts_as(keyword=)",))
def f923(c: Cast) -> None:
    """The extra die plays, as a rolled modifier narrowed to one ref --
    `c.bonus(dice=)` re-rolls it each time the modifier is read, which is
    once per damage roll. Reliable is the dropped half: nothing adds a
    keyword to a row."""
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=among("p1766"),
    )


# -- the undead-hunting riders, where a clause per power is printed ---------


def _p1567(c: Cast, ev: Any) -> None:
    """An adjacent ally's next damage roll against that target."""
    if not _undead(c, ev.target):
        return
    for friend in allies(c.world, c.me):
        if c.adjacent(to=friend):
            c.bonus(
                "damage", c.wis_mod, on=friend, until=When.ENCOUNTER, once=True,
                when=lambda ctx, foe=ev.target: ctx.get("target") == foe,
            )
            return


def _p841(c: Cast, ev: Any) -> None:
    if _undead(c, ev.target):
        c.push(1, on=ev.target)


def _p835_will(c: Cast, ev: Any) -> None:
    if _undead(c, ev.target) and c.marked(on=ev.target):
        c.bonus(WILL, 1, on=c.me, until=When.SONT)


def _p835_swarm(c: Cast, ev: Any) -> None:
    """+1 for each undead standing next to me, paid as extra damage."""
    near = sum(
        1 for foe in enemies(c.world, c.me) if c.adjacent(to=foe) and _undead(c, foe)
    )
    if near:
        c.flat(near, on=ev.target)


def _p1758(c: Cast, ev: Any) -> None:
    result = getattr(ev, "result", None)
    if result is not None and result.natural >= 15 and _undead(c, ev.target):
        c.flat(c.str_mod, on=ev.target)


def _p620(c: Cast, ev: Any) -> None:
    if not _undead(c, ev.target):
        return
    for friend in allies(c.world, c.me):
        if c.adjacent(to=friend):
            c.shift(1, who=friend)
            return


_riders("f1097", {"p1567": _p1567},
        dropped=("c.ignore_insubstantial()", "c.opt_in()"))

_riders("f1100", {"p841": _p841, "p835": _p835_will})

_riders("f1102", {"p835": _p835_swarm, "p1758": _p1758, "p620": _p620},
        dropped=("c.hit_twice()",))


# -- the feats that grant a card -------------------------------------------


@power("f1103", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.counts_as(keyword=)",))
def f1103(c: Cast) -> None:
    """The Perception and Insight bonuses are checks. "You are considered
    a vampire for the purpose of effects that relate to vampires" is the
    dropped half: `c.is_kind` reads a creature's type words and nothing
    adds one."""
    c.grant_row("f1103b", on=c.me, until=When.ENCOUNTER)


@power("f1103b", level=1, cls="", usage=ENCOUNTER, action=ActionType.STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.HEALING],
       attack=Attack(Ability.STR, vs=FORT, plus=2),
       dropped=("c.ability_for(ref)",))
def f1103b(c: Cast) -> None:
    """"One living creature you have grabbed" is asked of the grab
    relation, since `Target.holding` filters on what the *target* is
    carrying rather than on who is holding it.

    The printed three-way choice of attacking ability is a build choice
    nothing records, so the header writes Strength and the choice is the
    dropped half.
    """
    foe = c.target
    if foe is None or foe not in c.grabbing():
        return
    if c.strike().hit:
        c.damage("1d4", c.con_mod)
        if c.may("spend a healing surge", who=c.me):
            c.surge(on=c.me)


@power("f1105", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1105(c: Cast) -> None:
    """Which utility the card is swapped for is a build choice; on the
    board the benefit is that the character has the row."""
    c.grant_row("f1105b", on=c.me, until=When.ENCOUNTER)


@power("f1105b", level=1, cls="", usage=DAILY, action=ActionType.STANDARD,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POLYMORPH])
def f1105b(c: Cast) -> None:
    """Three holds at `When.SUSTAIN`, with the flight carrying the minor
    action that keeps them: only `c.hover` takes a `sustain=`, and the
    printed line sustains the whole shape at once."""
    c.insubstantial(on=c.me, until=When.SUSTAIN)
    c.cannot_attack(on=c.me, until=When.SUSTAIN)
    c.hover(8, on=c.me, until=When.SUSTAIN, sustain=ActionType.MINOR)


@power("f1111", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1111(c: Cast) -> None:
    c.grant_row("f1111b", on=c.me, until=When.ENCOUNTER)


@power("f1111b", level=1, cls="", usage=ENCOUNTER, action=ActionType.FREE,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.DIVINE, Keyword.WEAPON],
       trigger="you make an opportunity attack",
       todo=("c.as_basic(ref)", "c.opportunity_instead()"))
def f1111b(c: Cast) -> None:
    """Swaps what an opportunity attack *is* for one of the character's
    own at-wills. `Powers.opportunity` holds one such row per creature
    and nothing writes it from a `Cast`, so neither half is sayable and
    the printed trigger has nothing to hang on."""


# -- not a fight ------------------------------------------------------------


@power("f634", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f634(c: Cast) -> None:
    """A floor under two named skill checks. `c.treat_roll_as` sets a
    roll's parity and nothing sets a floor, but neither skill is rolled
    in a fight, so this is narrative rather than a gap."""


@power("f926", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f926(c: Cast) -> None:
    """A cantrip that makes a noise, and a Bluff bonus for using it.
    The four wizard cantrips are written the same way."""


@power("f929", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f929(c: Cast) -> None:
    """Tracking, disguises and a skill challenge."""


@power("f1003", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1003(c: Cast) -> None:
    """Two cantrips, both of which are already `out_of_combat` rows
    where they are written."""


@power("f1006", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1006(c: Cast) -> None:
    """A Stealth bonus for the party, which is a check."""


@power("f1071", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f1071(c: Cast) -> None:
    """A language and two skill bonuses. The climb speed is real, but
    every clause of the row is gated on being aboard a ship, and
    `c.terrain` knows no such place -- so the row is narrative entire
    rather than one working clause and two checks."""


# -- the Associated Powers family, printed with no clause -------------------


def _associated(ref: str) -> None:
    """The preamble, a resolved list of refs, and nothing to hang.

    `f974` carries the same marker because its list is empty; these nine
    have a list and no benefit printed against any member of it.
    """

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=ASSOCIATED)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = _associated.__doc__


for _ref in (
    "f972", "f977", "f980", "f981", "f982",
    "f985", "f988", "f992", "f994",
):
    _associated(_ref)


@power("f1113", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=ASSOCIATED)
def f1113(c: Cast) -> None:
    """"When you hit a target with an f1113 power" -- the ETL resolved the
    printed name in that sentence to the feat's own ref, which is how it
    reads when a feat names itself. So the clause is a rider on the
    feat's associated powers, and the page prints no list against this
    one. `c.vulnerable` would say the payout; nothing says which rows
    it hangs on."""


# -- "while under the effect of your racial power" --------------------------


@power("f624", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=UNDER)
def f624(c: Cast) -> None:
    """A defence bonus while standing in what a named racial power laid
    down. The power is a ref; what is missing is asking which row put a
    live effect on a creature."""


@power("f724", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=UNDER)
def f724(c: Cast) -> None:
    """A free shift around a close arcane power, gated on being under a
    named racial power's effect. Same gap as f624."""


@power("f1000", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=UNDER)
def f1000(c: Cast) -> None:
    """Melee damage against a target granting combat advantage, gated on
    a named racial power's effect. The advantage half is sayable; the
    gate is not, and without it the bonus is unconditional."""


@power("f1005", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=UNDER)
def f1005(c: Cast) -> None:
    """Charge damage under a named racial power's effect. `charge` is in
    the damage context; the effect is not."""




@power("f1136", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=UNDER)
def f1136(c: Cast) -> None:
    """Splash damage on a ranged arcane hit, gated on a named racial
    power's effect. Same gap as f624."""


# -- a racial power that arrives only as a name -----------------------------


@power("f714", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*RACIAL, "c.expend_row()"))
def f714(c: Cast) -> None:
    """Spends a racial power to teleport an ally instead of yourself.
    The power is named in prose with no ref, and spending a row without
    using it has no verb either."""


@power("f717", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f717(c: Cast) -> None:
    """Redirects a named racial power onto a creature you missed. Named
    in prose, and the gate names only the race."""


@power("f719", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f719(c: Cast) -> None:
    """Stops an attack ending a named racial power's effect. Same gap."""


@power("f925", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f925(c: Cast) -> None:
    """Temporary hit points whenever *any* power of a race is used
    successfully. The gate names the race and no row."""


@power("f1025", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f1025(c: Cast) -> None:
    """A defence penalty riding on a named racial power's hit."""


@power("f1114", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=(*RACIAL, "c.on_extra_damage()"))
def f1114(c: Cast) -> None:
    """Spreads a named racial power's extra damage over every target of
    an area power. Two gaps: the power has no ref, and nothing announces
    a rider paying out."""


@power("f1131", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACIAL)
def f1131(c: Cast) -> None:
    """Rides on "the racial power associated with your elemental
    manifestation" -- a race, a build choice, and no ref between them."""


# -- rerolls, which nothing announces ---------------------------------------


@power("f633", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f633(c: Cast) -> None:
    """A die added to the roll a named racial power buys. The power is a
    ref; what is missing is that nothing says a roll is a reroll, so
    there is no moment at which to add to one."""


@power("f715", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=REROLL)
def f715(c: Cast) -> None:
    """Widens the same racial power's reroll to every target of one
    arcane power. Same gap, from the other side."""


# -- build-time choices -----------------------------------------------------


@power("f922", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.race_choice()",))
def f922(c: Cast) -> None:
    """Changes an elemental manifestation mid-day and hands back the
    encounter power that goes with it. The manifestation is a racial
    choice and there is no race on a character to hold one."""


@power("f1115", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=PROFICIENCY)
def f1115(c: Cast) -> None:
    """The whole benefit is "you can now use that kind of implement",
    which is settled by the chassis when the character is built. Unlike
    `f64` there is no second half to keep, so this is a `todo` rather
    than a `dropped`."""


@power("f1125", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1125(c: Cast) -> None:
    """"The same damage type as your breath weapon" is read off the
    build's recorded element, which is the only place a character's
    chosen damage type lives. A damage type is also a keyword, so the
    gate asks the power's keywords -- the *attack* context carries no
    `dtype` and only the damage one does."""
    dt = c.element(on=c.me)
    if dt is None:
        return
    me = c.me
    matching = Keyword(dt.value)
    for what in ("attack", "damage"):
        c.bonus(
            what, 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: _has(ctx, Keyword.ARCANE) and _has(ctx, matching),
        )


# -- what a row's own header says, which nothing rewrites -------------------


@power("f621", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_dice()", "c.bonus('crit_range')"))
def f621(c: Cast) -> None:
    """Raises a weapon's damage die and makes it high crit. `Weapon.damage`
    is read straight out of the component when a swing is rolled and
    nothing edits it; high crit is a property of the weapon rather than
    of the wielder, so `c.bonus("crit_damage")` is the wrong creature."""


@power("f999", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_dice()",))
def f999(c: Cast) -> None:
    """Enlarges the die a named racial power adds. The power is a ref and
    the die is inside its body, which this row cannot reach."""


@power("f1061", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_dice()",))
def f1061(c: Cast) -> None:
    """Steps one named power's damage dice up a size. Same gap as f999."""


@power("f921", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.change_dice()", "c.counts_as(keyword=)"))
def f921(c: Cast) -> None:
    """Sets one named power's damage outright and adds Reliable to it.
    `f923` beside this one can pay an extra die through
    `c.bonus(dice=)`; *replacing* the printed dice cannot be done that
    way, so unlike f923 nothing here works."""


@power("f725", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recast(reach=)",))
def f725(c: Cast) -> None:
    """Turns a named power's close blast into an area burst. Reach is
    header data the action menu reads before anything runs, and
    `c.recast` rewrites the action a row costs and nothing else."""


@power("f935", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recast(trigger=)",))
def f935(c: Cast) -> None:
    """Makes a named power an immediate reaction to a melee or close
    attack. `c.recast` can lower what a row costs but cannot give it a
    trigger, and a reaction with no declared trigger is a row the
    dispatcher never offers -- which would be worse than leaving it."""


@power("f928", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.grant_weapon()",))
def f928(c: Cast) -> None:
    """A natural weapon with its own group, dice, proficiency and off-hand
    property, held whenever the hands are empty. Nothing puts a weapon
    into a creature's `Gear` from a row."""


# -- the rest of the gaps ---------------------------------------------------


@power("f718", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.boost_roll()",))
def f718(c: Cast) -> None:
    """Adds one to the roll a named racial power is already adding to.
    The power is a ref, so the trigger is sayable -- but by then the d20
    is down, and `c.bonus` is read by the *next* roll. `c.boost_check`
    does this for a skill check and there is no counterpart for an
    attack."""


@power("f933", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.no_provoke(when=)",))
def f933(c: Cast) -> None:
    """No opportunity attacks for firing a hand crossbow in one hand with
    a light blade in the other. `c.no_provoke` names a creature you may
    walk away from; the opening a *ranged attack* gives has no modifier
    to gate."""


@power("f1149", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.no_provoke(when=)",))
def f1149(c: Cast) -> None:
    """The same gap, narrowed to the creatures an area arcane power
    targets."""


@power("f1021", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.opt_in()",))
def f1021(c: Cast) -> None:
    """A trade offered on every implement attack: two off the roll for
    two radiant on a hit. `c.may` asks a yes-or-no inside a body that is
    already running; nothing offers a choice from a standing modifier,
    so the penalty would be compulsory and the row strictly worse than
    not having it."""


@power("f1099", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.opt_in()", *FEATURE))
def f1099(c: Cast) -> None:
    """Both clauses are "you can forgo X to instead Y", one of them on a
    class feature named in prose. The Intimidate bonus is a check."""


@power("f1098", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.deals(ref=)", "c.bonus(dtype=)", "c.opt_in()"))
def f1098(c: Cast) -> None:
    """Three clauses and no two of them the same shape: change one named
    power's damage type, type an ally's damage bonus as radiant, and
    trade a printed payout for a saving throw. `c.deals` overrides a
    *creature's* weapon type and cannot name a row; `c.bonus` carries no
    damage type. The Diplomacy bonus is a check."""


@power("f1101", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.surge_value(bonus=)", "c.class_feature()",
             "c.on_granted_attack()", "c.on_miss(ref)"))
def f1101(c: Cast) -> None:
    """Four clauses, four different gaps. `Health.surge_value` is a
    quarter of maximum computed on read, so nothing raises it; one
    clause is gated on a class feature named in prose; one adds to an
    attack another row grants; and one pays out on a named row's miss."""


@power("f1063", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.opportunity_instead()",))
def f1063(c: Cast) -> None:
    """Swaps what an opportunity attack is for a named racial power, and
    unexpends it into the bargain. `Powers.opportunity` is the field
    that would hold it and no verb writes it."""


@power("f1066", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_basic()",))
def f1066(c: Cast) -> None:
    """A bonus on the basic attack a racial feature hands out. Nothing
    announces a granted basic as distinct from any other."""


@power("f1026", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.stay_hidden()",))
def f1026(c: Cast) -> None:
    """Stay hidden after missing with a ranged or area attack.
    `resolve.attack` clears `Relation.HIDDEN_FROM` **after** it emits the
    `Miss`, so a watcher that hides again is undone a line later -- the
    row needs to suppress the clear, not race it."""


@power("f1106", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.low_light()",))
def f1106(c: Cast) -> None:
    """Low-light vision. `c.truesight` and `c.see_invisible` exist and
    this is neither of them."""


@power("f1148", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.ignore_resistance()",))
def f1148(c: Cast) -> None:
    """The racial power is a ref, so the trigger would be ordinary --
    but nothing makes a creature's attacks ignore resistances, and
    `c.resist` on the other creature is the wrong end of it."""


@power("f1158", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_second_wind()",))
def f1158(c: Cast) -> None:
    """A second wind is an action rather than a row, and announces
    nothing a trigger can be declared on."""






