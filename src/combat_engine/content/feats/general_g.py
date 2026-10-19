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

*"While you are under the effect of your <racial power>"* was five rows
marked `c.effects_on()`, and the marker was wrong. An effect's **label
is the ref of the row that laid it** -- `durations.keywords_of` says so
and `c.bonus`, `c.condition` and `c.effect` all stamp it -- so
`c.suffering(ref, include_self=True)` has always answered the question.
All five are written, and so is the half of `f719` that was dropped for
the same reason.

*"You gain a benefit with any of the following exploits you possess"*
is nine rows whose page prints the preamble and the Associated Powers
list and **no clause per power**. There is a resolved list of refs and
nothing to hang on it, which is `feat.associated_powers` -- the same
marker `f974` carries for the same reason.

And `c.bonus("initiative", ...)` is not a thing: `c.initiative`'s own
docstring says the component is read before the d20 and a modifier is
never consulted. The two rows here that print an initiative bonus
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
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    Ability,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    Cast,
    Condition,
    DamageType,
    Defences,
    Dropped,
    Gear,
    Health,
    Hit,
    Keyword,
    Melee,
    Miss,
    PowerResolved,
    Powers,
    PowerUsed,
    Rerolled,
    SavingThrow,
    SecondWind,
    Trigger,
    Usage,
    When,
    Window,
    about_me,
    by_me,
    power,
    rerolled_by,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import (
    allies,
    distance_between,
    enemies,
    hidden_from,
    team,
)

#: A racial power the benefit line names in prose and no gate pins.
RACIAL = ("c.on_racial_power()",)
#: The thirteen racial powers of `r33`, one per elemental
#: manifestation. A character takes one, so "the racial power
#: associated with your manifestation" is whichever of these it uses.
R33 = (
    "p1766", "p1767", "p1769", "p1770", "p1828",
    "p10043", "p10044", "p10045", "p10046",
    "p14073", "p14074", "p14075", "p14076",
)
#: Which weapons and implements a character may pick up is settled when
#: it is built, and a `Cast` runs with the gear already in hand.
PROFICIENCY = ("chargen.proficiency()",)
#: The preamble and a list of refs, with no clause printed per ref.
ASSOCIATED = ("feat.associated_powers",)
#: **The clause a member of the list carries, which is thrown away.**
#: These cards set the list one member per line as `<name> : <clause>`,
#: and the clause *is* the feat -- the preamble says only "you gain a
#: benefit". `build._associated_refs` keeps `part.split(":")[0]` and
#: drops the rest, and it splits the list on commas where these are
#: split on newlines, so a clause's own commas are read as members.
#: What arrives is a list of refs and no rules at all.
CLAUSE = ("spec.associated_clause()",)
#: A class feature named in prose, with no ref anywhere in the row.
FEATURE = ("c.class_feature()",)


def _under(c: Cast, ref: str) -> bool:
    """Am I carrying a live effect my own named row laid?

    "While you are under the effect of your <power>." An effect's label
    is the ref of the row that laid it -- `durations.keywords_of` leans
    on the same fact -- so `c.suffering` answers this and nothing new
    was ever needed. `include_self=True` because the method leaves the
    caster out by default and the caster is the whole question here.
    """
    return c.me in c.suffering(ref, by=c.me, include_self=True)


def _in_my_zone(c: Cast, ref: str) -> bool:
    """Am I standing in a zone my own named row laid?

    `c.my_zones` gives ids and `c.in_my_aura` only answers for auras, so
    the squares are read off the zone. `Cast.zone` labels one with the
    ref that laid it when the row passes no `label=`, which is how
    `p2473` is found.
    """
    return any(
        zone.owner == c.me and zone.label == ref and c.here in zone.squares
        for _zid, zone in c.world.zones.all()
    )


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


def _holding_somebody(world, eid: int) -> bool:  # noqa: ANN001
    """"Target: one creature you have grabbed." A `requires=` is handed
    `(world, eid)` and no `Cast`, so the relation is read directly."""
    from combat_engine.engine import Relation

    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


# -- resistances, which `c.resist` adds to rather than replaces -------------


def _arcane_row(ctx: dict[str, Any]) -> bool:
    """An arcane power, read off the row the context names."""
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.ARCANE in p.keywords


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
       reach=PERSONAL, target=SELF)
def f924(c: Cast) -> None:
    """Both halves now. The immunity was dropped while the context could not
    name the row laying the condition; `immune_to` takes a `power` and #309
    threads it from `durations.Effects.apply`, so the narrowing is askable.

    **The gate reads the keyword off the row, not off the context.** The ref is
    what travels -- the same arrangement `no_provoke` uses for `ctx["why"]` --
    so the keyword list stays on the row where it lives. A monster ability
    answers it as readily as a spell does: a stat block's ability is an
    ordinary declared row with its own keywords, which is what the printed
    "cold power" means.

    Empty `power` is the condition that came from no row -- a failed save, a
    trap, a zone's own clause -- and the gate is correctly False there rather
    than immune to everything.
    """
    held = c.world.get(c.me, Defences)
    if held is not None and held.resist.get(DamageType.COLD, 0) > 0:
        c.resist(3, DamageType.COLD, on=c.me)

    def chilled(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power") or "")
        return row is not None and Keyword.COLD in row.keywords

    c.immune(Condition.SLOWED, Condition.IMMOBILIZED, on=c.me,
             until=When.ENCOUNTER, when=chilled)


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
       reach=PERSONAL, target=SELF)
def f927(c: Cast) -> None:
    """The Endurance half is not a fight. The save half reads the
    keywords of the row that laid the hold, and falls back on the burn's
    own type for an ongoing poison laid by a row that prints none."""
    c.bonus(
        "save", 4, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: Keyword.POISON in ctx.get("keywords", ())
        or ctx.get("dtype") is DamageType.POISON,
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
       reach=PERSONAL, target=SELF, proficiency=("w3612",))
def f1004(c: Cast) -> None:
    """Both halves, as `f64` and `f69` now write the same sentence. One
    military two-handed weapon stands for the whole printed line, which
    is what the chassis does with a proficiency line of its own."""
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


#: Whose surge pool has already been raised, by world and creature. The
#: sentence is about the character sheet and a trait re-arms every fight,
#: so the ceiling has to move exactly once.
_RAISED: dict[tuple[int, int], bool] = {}


@power("f1031", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1031(c: Cast) -> None:
    """`c.initiative`, not `c.bonus("initiative", ...)`: the component is
    read before the d20 and a modifier to it is never consulted.

    **The extra surge is written now.** It was marked `c.max_surges()` on
    the argument that nothing raises the pool. `Health.max_surges` is an
    ordinary field a body can reach, `turns` refills to it, and
    `feats/paladin.py` already writes it for the same printed sentence --
    so what was missing was only a door, and the body does not need one.
    Latched per character, and the surge itself is handed over because a
    character arriving at the old ceiling is otherwise one short."""
    c.initiative(3, on=c.me)
    key = (id(c.world), c.me)
    health = c.world.get(c.me, Health)
    if health is None or _RAISED.get(key):
        return
    _RAISED[key] = True
    health.max_surges += 1
    c.regain_surge(1, on=c.me)


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
       reach=PERSONAL, target=SELF,
       trigger="you hit with p1831",
       on=Trigger(Hit, _hit_with("p1831"), "you hit with that racial power"))
def f1122(c: Cast) -> None:
    """Twice the enhancement of the magic implement in hand. Whether it
    is one *your arcane class* may use needs nothing here: `chargen`
    deals a character only what it may carry, so anything in hand
    already answers the clause."""
    magic = [w.enhancement for w in c.held(what="magic") if w.enhancement]
    if magic:
        c.flat(2 * max(magic), on=c.trigger.target)


@power("f1059", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1059(c: Cast) -> None:
    """The critical rider and the wider burst.

    **The burst is written.** The marker said naming one row's range line
    was the gap, and it is already named: `dsl.area_of` hands `_stretched`
    a context carrying the ref being measured, so a gated
    `c.bonus("blast_size", ...)` widens exactly one power and leaves every
    other close attack alone -- which is what `c.widen_areas` could not
    do. p5599 is a close burst, one of the three kinds `_stretched` reads
    `blast_size` for. No type word printed, so untyped."""
    me = c.me
    c.bonus(
        "blast_size", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == "p5599",
    )

    def on_crit(ev: Any) -> None:
        if ev.attacker == me and ev.critical and ev.power == "p5599":
            c.ongoing(5, on=ev.target)

    c.watch(Hit, on_crit, on=me, until=When.ENCOUNTER)


@power("f1025", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p6189",
       on=Trigger(Hit, _hit_with("p6189"), "you hit with that racial power"))
def f1025(c: Cast) -> None:
    """"The enemy you hit", so this is declared on the hit rather than on
    the use: the power picks its targets before the body runs but only
    the ones it lands on take the penalty."""
    for defence in (AC, FORT, REF, WILL):
        c.penalty(defence, 1, on=c.trigger.target, until=When.EONT)


@power("f719", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p377",
       on=Trigger(PowerUsed, _used("p377"), "you use that racial power"))
def f719(c: Cast) -> None:
    """Attacking clears `HIDDEN_FROM` at the foot of `resolve.attack`, and
    the note there says a row that keeps its concealment hides again --
    so the concealment is remembered in the interrupt window and put back
    in the reaction window, which brackets the clear.

    Narrowed to p377's own hold: `clear_source` wipes the relation and
    leaves the `Effect` standing, so the label still names the row that
    laid it and this no longer preserves concealment from any source.
    Put back on p377's clock rather than `c.hide`'s default, which would
    outlive the power it is protecting.
    """
    me = c.me
    kept: list[int] = []

    def remember(ev: Any) -> None:
        kept.clear()
        if (
            ev.attacker == me
            and _has({"power": ev.power}, Keyword.ARCANE)
            and _under(c, "p377")
        ):
            kept.extend(hidden_from(c.world, me))

    def restore(ev: Any) -> None:
        if ev.attacker != me:
            return
        for watcher in kept:
            c.hide(from_=watcher, until=When.EONT)
        kept.clear()

    c.watch(AttackDeclared, remember, on=me, until=When.ENCOUNTER,
            window=Window.BEFORE)
    c.watch(AttackDeclared, restore, on=me, until=When.ENCOUNTER)


#: "An arcane attack power" -- read off the row in the registry, the way
#: `by_keyword` reads it, because `Miss` carries only the ref.
def _missed_with_arcane(world: object, me: int, ev: object) -> bool:
    from combat_engine.engine import get as _get

    row = _get(getattr(ev, "power", ""))
    return (
        getattr(ev, "attacker", None) == me
        and row is not None
        and Keyword.ARCANE in row.keywords
    )


@power("f714", level=1, cls="", usage=AT_WILL, action=ActionType.FREE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION])
def f714(c: Cast) -> None:
    """Spends `p1449` to teleport an ally instead of yourself.
    `c.expend_row` is the price and the Requirement at once: the use
    goes, p1449's own teleport never happens, and the row does nothing
    when there is no use left.

    Judgement: the card picks the ally "within the area of effect
    targeted by the arcane power", and the row is used *before* that
    power, so the area does not exist yet to be asked about. An ally
    you can reach is the nearest honest reading -- `side="ally"`, which
    leaves the caster out, because the whole point is teleporting
    somebody else."""
    if not c.expend_row("p1449"):
        return
    mates = [a for a in c.within(10, side="ally") if c.can_see(a)]
    if not mates:
        return
    chosen = c.choose(mates, "which ally to teleport") or mates[0]
    c.teleport(3, who=chosen)


@power("f717", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with an arcane attack power",
       on=Trigger(Miss, _missed_with_arcane,
                  "you miss with an arcane attack power"))
def f717(c: Cast) -> None:
    """`c.use_power` is both halves: p1628 is used here and now, and it
    is *aimed* at the creature this row missed rather than at whoever
    hit you, which is what `on=` is for. The card's "treat that target
    as the enemy that hit you" is exactly that redirection.

    `AT_WILL`, because a triggered `action=NONE` row spends a use every
    firing and the card prints no limit -- p1628's own encounter use
    is the limit, and using it spends it."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.use_power("p1628", on=victim)


@power("f1114", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.rider_targets()",))
def f1114(c: Cast) -> None:
    """Spreads `p6189`'s extra damage over every target of an area power.

    **Re-pointed: this is not the same gap as the four `p8278` feats.**
    Those read a rider's *amount*; this one changes who it pays out to,
    which is a write and not a read. The power is a ref and the rider is a
    `c.bonus("damage", once=True)`, so what is wanted is "pay this rider
    on every target hit rather than the first", which nothing expresses.
    #619."""


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
       reach=PERSONAL, target=SELF, )
def f923(c: Cast) -> None:
    """The extra die plays, as a rolled modifier narrowed to one ref --
    `c.bonus(dice=)` re-rolls it each time the modifier is read, which is
    once per damage roll. Reliable is the dropped half: nothing adds a
    keyword to a row."""
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=among("p1766"),
    )
    # Reliable, recorded against the creature -- see `f921`.
    c.counts_as_keyword("p1766", Keyword.RELIABLE)
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


def _f1097_necrotic(using: Cast) -> None:
    """Resist necrotic in place of p889's whole ally benefit.

    The Charisma modifier of the character **using the prayer**, which is
    the one the card means -- the same reading f2081's helper gives for its
    own ladder. Until the end of the user's next turn, which is the duration
    every other rider on this family lays.
    """
    ally = using.target
    if ally is None:
        return
    using.resist(using.cha_mod, DamageType.NECROTIC, on=ally,
                 until=When.EONT)


def _f1097(c: Cast) -> None:
    """The two riders that are not about landing a blow.

    **`c.opt_in()` came off this card and the note that removed it dropped
    a clause.** It said f1097 has two riders, an addition and an exemption,
    and that "neither forgoes anything, so there is nothing to substitute".
    The card prints **three**, and the third is an explicit *instead*:
    "grant one ally resist necrotic [...] **instead of** granting temporary
    hit points or the ability to make a saving throw". So there was an opt-in
    in it; what was wrong was the verb, and `c.pre_empt` is the one. #750.

    * **p463** -- "your attack ignores the insubstantial trait" against an
      undead enemy. `c.ignore_resistance(insubstantial=True)` has existed
      all along; the gate is what makes it this card rather than a blanket
      exemption, and it reads the row and the victim's type words off the
      damage context.
    * **p889** -- one `c.pre_empt` against the whole benefit, because the
      card replaces both of its branches and p889 reads one clause word for
      the pair.

    Laid at arming rather than per use: a substitution has to be standing
    before the row is offered, which is `c.pre_empt`'s own reasoning, and
    an exemption gated on the power costs nothing when that power is not
    the one rolling.
    """
    c.ignore_resistance(
        insubstantial=True, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") == "p463"
        and _undead(c, ctx.get("target")),
    )
    c.pre_empt("p889", "ally_benefit", _f1097_necrotic)


_riders("f1097", {"p1567": _p1567}, setup=_f1097)

_riders("f1100", {"p841": _p841, "p835": _p835_will})

_riders("f1102", {"p835": _p835_swarm, "p1758": _p1758, "p620": _p620},
        dropped=("c.hit_twice()",))


# -- the feats that grant a card -------------------------------------------


@power("f1103", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1103(c: Cast) -> None:
    """The Perception and Insight bonuses are checks, so the card's
    Special line is the only other half with a fight in it.

    **It is written, and it needed no new reader.** "Counts as a creature
    of that type for the purpose of effects that relate to it" is the
    printed shape `c.set_origin` exists for: it holds the word as a
    labelled effect, `query.kinds_of` reads it alongside a stat block's
    own `kind` and `origin` columns, and that is the one set `c.is_kind`
    and `Target.kinds` both answer from. So a target line restricting its
    pool to that type now reaches this character, which is what the
    sentence is for. The old marker wanted a `counts_as=` on the reader;
    the write goes on the creature instead.

    The word is a mechanical type and not a name -- it is the `kind`
    column of two stat blocks in the database."""
    c.set_origin("vampire", on=c.me, until=When.ENCOUNTER)
    c.grant_row("f1103b", on=c.me, until=When.ENCOUNTER)


@power("f1103b", level=1, cls="", usage=ENCOUNTER, action=ActionType.STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.HEALING],
       attack=Attack((Ability.STR, Ability.CON, Ability.DEX), vs=FORT, plus=2),
       requires=_holding_somebody,
       requires_text="you must have a creature grabbed",
       )
def f1103b(c: Cast) -> None:
    """"One living creature you have grabbed" is a Requirement rather
    than a guard in the body: `Target.holding` filters on what the
    *target* is carrying, not on who is holding it, and a body that
    returns early looks exactly like a row that does nothing.

    The printed three-way choice of attacking ability is now the header's
    own -- `Attack` takes a tuple and `ability_for` resolves it to
    whichever of the three this character is best at. The card settles the
    choice once at feat selection and never re-asks, so best-of is the
    same answer a player would write down, and it is the only one that can
    be given without a record of the pick.
    """
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
    printed line sustains the whole shape at once.

    **`c.hover`'s first argument is a HEIGHT, not a fly speed.** Its body is
    `if squares_: self.rise(squares_)` and then `mv.using = "hover"`, so
    `c.hover(8)` lifted this creature 8 squares and granted it nothing to
    fly at. The printed speed needs `c.mode("fly", 8)`, which is the verb
    for "grant a way of moving ... for a while", and the hover state needs
    `c.hover()` with no height at all -- no card here prints an ascent.

    Found by following a Bin B agent's fix of `m1062a4`, which had the same
    fault; three other rows shared it.
    """
    c.insubstantial(on=c.me, until=When.SUSTAIN)
    c.cannot_attack(on=c.me, until=When.SUSTAIN)
    c.mode("fly", 8, on=c.me, until=When.SUSTAIN)
    c.hover(on=c.me, until=When.SUSTAIN, sustain=ActionType.MINOR)


@power("f1111", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1111(c: Cast) -> None:
    c.grant_row("f1111b", on=c.me, until=When.ENCOUNTER)


@power("f1111b", level=1, cls="", usage=ENCOUNTER, action=ActionType.FREE,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.DIVINE, Keyword.WEAPON],
       trigger="you make an opportunity attack")
def f1111b(c: Cast) -> None:
    """Swaps what an opportunity attack *is* for one of the character's
    own at-wills. The set is not an associated-powers list but a
    question asked of the character: `c.borrowed_rows` already filters
    to at-will melee attack rows, and the card narrows that to level 1
    and to a single target.

    `c.as_basic` takes no count, but the swap does not need one: the
    Trigger names one opportunity attack, so the offer is withdrawn the
    moment a swing is declared in that window. `AttackDeclared`'s AFTER
    window is where that is done -- ending it any earlier would remove
    the option before the swing that asked for it. The damage rider is
    `once=True` for the same one swing."""
    me = c.me
    picked = [
        r for r in c.borrowed_rows(me)
        if (p := get(r)) is not None and p.level <= 1 and p.target.count == 1
    ]
    if not picked:
        return
    swap = c.as_basic(*picked, window="opportunity")
    chosen = frozenset(picked)
    c.bonus(
        "damage", c.str_mod, on=me, until=When.ENCOUNTER, once=True,
        when=lambda ctx: (
            bool(ctx.get("opportunity")) and ctx.get("power") in chosen
        ),
    )

    done = [False]

    def spent(ev: Any) -> None:
        # Not `once=` on the watch: that spends on the first attack of
        # any kind, and an ordinary swing would retire the offer before
        # the opportunity one it exists for.
        if not done[0] and ev.attacker == me and getattr(ev, "opportunity", False):
            done[0] = True
            c.end_effect(swap, why=f"{c.ref}: the one opportunity attack")

    c.watch(AttackDeclared, spent, on=me, until=When.ENCOUNTER)


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


# -- the Associated Powers family, whose clauses are thrown away ------------


def _associated(ref: str, *, listed: bool = True) -> None:
    """The preamble, a list of refs, and the rules discarded in transit.

    **Re-aimed twice, and the second time was to say the ETL is fine.**
    The first reading was that these cards print no benefit against any
    member of the list. They do: each member is set on its own line as
    `<name> : <clause>`, and the clause is the entire feat -- the preamble
    says only "you gain a benefit with any of the following".

    The second reading was that `_associated_refs` threw that clause away.
    **It does not, and has not for some time.** The spec carries
    `p4368 : Before and after the attack with this exploit, your beast
    companion can shift 1 square.` -- ref resolved, clause intact. Checked
    against the source: of 737 linked Associated-Powers members, 478 have a
    heroic row and **all 478 resolve correctly**.

    So `spec.associated_clause()` names an ETL gap that is not there. What
    is actually missing is that nobody has written these rows, and the
    pattern for writing them is already in the tree: `f1305` arms one
    watcher per window and picks the clause by which power fired.

    `listed=False` for the three that lose the whole block as well: an
    errata paragraph sits above the list and `etl/feat._benefit` breaks
    at an errata heading, taking the rest of that paragraph with it.
    """

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF,
           todo=CLAUSE if listed else (*ASSOCIATED, *CLAUSE))
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = _associated.__doc__


# **#299's ten are all written now, in `exploits.py`**, where the `_riders`
# machinery lives -- so this loop has nothing left to generate. Kept, rather
# than deleted with the list: `_associated` is still the right treatment for a
# card of this shape that nobody has reached, and the next one filed will want
# it. What it must not be used for again is a row whose clauses are writable,
# which was all ten of these.


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


def _used_close_arcane(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """I used a close arcane attack power."""
    row = get(getattr(ev, "power", ""))
    return (
        ev.actor == me
        and row is not None
        and row.attack is not None
        and Keyword.ARCANE in row.keywords
        and row.reach.kind in ("close_burst", "close_blast")
    )


@power("f624", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f624(c: Cast) -> None:
    """"Within the effect of your p2473 power" is its **zone**, not a hold
    on the creature: that row lays one and labels it with its own ref.
    Asked per roll rather than at arming, because the caster walks in
    and out of it. No type word in front of the bonus, so untyped."""
    c.bonus(REF, 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: _in_my_zone(c, "p2473"))


@power("f724", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a close arcane attack power",
       on=Trigger(PowerUsed, _used_close_arcane,
                  "you use a close arcane attack power"))
def f724(c: Cast) -> None:
    """"Before or after using the power" -- `PowerUsed` is announced above
    the body, so this is the "before", which is the half that matters:
    it is the one that can move the burst's origin.

    `AT_WILL` because a triggered `action=NONE` row spends a use every
    firing and the card prints no limit."""
    if _under(c, "p2484"):
        c.shift(1)


@power("f1000", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1000(c: Cast) -> None:
    """The damage context carries `advantage` and `ranged` now -- both were
    absent when this row was first marked, and `AUTHORING.md` still says
    the damage side is thin. "Granting combat advantage to you" is the
    board's answer at damage time, which is right for every standing
    grant and blind to a one-shot one the roll has already spent."""
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            bool(ctx.get("advantage"))
            and not ctx.get("ranged", False)
            and _has(ctx, Keyword.WEAPON)
            and _under(c, "p2484")
        ),
    )


@power("f1005", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1005(c: Cast) -> None:
    """`charge` is in the damage context and the racial power's hold is
    read off the effect's label, so both halves are gates on one
    modifier."""
    c.bonus(
        "damage", 3, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("charge")) and _under(c, "p2483"),
    )


@power("f1136", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1136(c: Cast) -> None:
    """"One enemy adjacent to the target", which is never the target
    itself. The 11th and 21st level steps are out of scope, so 2."""
    me = c.me

    def splash(ev: Any) -> None:
        row = get(ev.power)
        if (
            ev.attacker != me
            or row is None
            or row.reach.kind != "ranged"
            or Keyword.ARCANE not in row.keywords
            or not _under(c, "p2483")
        ):
            return
        near = [
            foe for foe in enemies(c.world, me)
            if foe != ev.target and c.adjacent_to(foe, ev.target)
        ]
        if near:
            c.flat(2, on=near[0])

    c.watch(Hit, splash, on=me, until=When.ENCOUNTER)


# -- the racial powers of r33, which are declared now -----------------------


def _used_any(*refs: str):  # noqa: ANN202
    """`PowerUsed` names its subject `actor`, which `by_me` never reads."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power in refs

    return when


def _arcane(ctx: dict[str, Any]) -> bool:
    """Both the attack and the damage context carry `power`."""
    row = get(ctx.get("power") or "")
    return row is not None and Keyword.ARCANE in row.keywords


@power("f925", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a r33 racial power",
       on=Trigger(PowerUsed, _used_any(*R33), "you use a r33 racial power"))
def f925(c: Cast) -> None:
    """The race's thirteen powers are declared, so "a r33 racial power"
    is a list of refs. "Successfully" is read as using it: `PowerUsed`
    is announced above the body, and none of the thirteen rolls an
    attack that could fail. The choice of modifier is the best of the
    three, which is the one a player takes."""
    c.temp_hp(5 + max(c.str_mod, c.con_mod, c.dex_mod), on=c.me)


@power("f1131", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a r33 racial power",
       on=Trigger(PowerUsed, _used_any(*R33), "you use a r33 racial power"))
def f1131(c: Cast) -> None:
    """A character takes one manifestation, so "the racial power
    associated with your manifestation" is whichever of the race's
    thirteen it has. No type word in front of either bonus, so both are
    untyped. The 11th and 21st level steps are out of scope."""
    c.bonus("attack", 1, on=c.me, until=When.EONT, when=_arcane)
    c.bonus("damage", 2, on=c.me, until=When.EONT, when=_arcane)


# -- rerolls, which nothing announces ---------------------------------------


@power("f633", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1450",
       on=Trigger(Rerolled, rerolled_by("p1450", roll="attack"),
                  "p1450 rolls your attack again"))
def f633(c: Cast) -> None:
    """+1d4 on the reroll `p1450` buys.

    **A die, so it cannot be a standing modifier** the way `f217`'s flat +2
    is -- `Mod.value` is an integer and this has to be rolled. So it answers
    the `Rerolled` moment and adds to the roll still in hand with
    `c.boost_roll`, which is why that verb had to land first (#495).

    `Rerolled` carries the live result as a plain attribute for exactly
    this, and `resolve` recomputes the outcome after the interrupt window,
    so a boost applied here is judged with the rest. #496.

    `AT_WILL`, because `lint.py` is right that a triggered trait declared
    per-encounter is spent on its first firing and this card prints no limit
    of its own -- the limit is `p1450`'s single encounter use.
    """
    c.boost_roll(c.roll("1d4"), kind="attack")


@power("f715", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.reroll_attack(all_targets=)",))
def f715(c: Cast) -> None:
    """**Re-pointed: this was never the announcement gap (#496).**

    `c.reroll_attack` rerolls *the triggering roll* -- one roll, read off
    `c.trigger`. An area power rolls separately against every creature it
    touches, and this feat says the one reroll applies to all of them. There
    is no second roll to find: the others have already been resolved and
    their results are not on the triggering event.
    """


# -- build-time choices -----------------------------------------------------


@power("f922", level=1, cls="", usage=DAILY, action=ActionType.MINOR,
       reach=PERSONAL, target=SELF)
def f922(c: Cast) -> None:
    """Changes which elemental manifestation the character is on.

    **Written: the manifestation is a row, not a word.** The marker said
    there is no race on a character to hold one, and that is stale twice
    over -- `Build.race` exists, and `RaceLine.granted` puts exactly one
    of r33's thirteen powers into `Powers.known` because its block says to
    choose. So the manifestation *is* whichever of `R33` the creature
    holds, and changing it is `c.forbid` on the one it has and
    `c.grant_row` on the one it takes.

    Read off this creature's own `Powers.all`. `c.knows` answers who on
    the board holds a row, so it is true for a character merely standing
    next to another manifestation.

    The second sentence needs nothing extra: the new row is a different
    ref, so its own use is unspent whatever was done with the old one.
    Within one fight `When.ENCOUNTER` is the whole horizon, which is also
    why the once-a-day limit is the header's `DAILY` and not a counter."""
    known = c.world.get(c.me, Powers)
    if known is None:
        return
    held = [ref for ref in known.all if ref in R33]
    options = [r for r in R33 if r not in held and get(r) is not None]
    if not held or not options:
        return
    taken = c.choose(options, "which elemental manifestation now")
    if taken is None:
        return
    for ref in held:
        c.forbid(ref, on=c.me, until=When.ENCOUNTER)
    c.grant_row(taken, on=c.me, until=When.ENCOUNTER)


@power("f1115", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True,
       proficiency=("w:wand",))
def f1115(c: Cast) -> None:
    """The whole benefit is "you can now use that kind of implement", and
    it lands when the character is built. Nothing is left for a fight,
    which is what `out_of_combat` says. The second sentence is about an
    implement that is *also a weapon*; a wand is not one, so it has no
    subject here."""


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
       reach=PERSONAL, target=SELF)
def f621(c: Cast) -> None:
    """One named weapon rolls a d8, and becomes high crit.

    **Both halves are the same write, and neither needs a door.**
    `Gear.weapons` holds `replace(w)` copies made per character by
    `chargen.spawn` -- the whole argument `c.weapon_dice` makes for
    needing no reader -- and `Weapon.properties` has had a reader since
    #240: `Cast._high_crit` pays a rolled extra `[W]` on a critical and
    looks for the printed word in that field. So the property goes on this
    character's own copy directly, the way `feats/paladin.py` reaches
    `Health`. A set union, so arming the trait twice says the same thing
    twice.

    Re-aimed three times before this. `c.bonus('crit_range')` **exists**
    and is wrong twice over -- high crit is extra damage on a critical,
    not a wider one, and the modifier sits on the wielder where the
    property belongs to the weapon. Then `Weapon.high_crit`, on the
    argument that nothing read the field, which stopped being true. Then
    `c.counts_as(property=)`, a new verb for a write a body can make."""
    c.weapon_dice("1d8", ref="w3627", on=c.me)
    gear = c.world.get(c.me, Gear)
    for weapon in gear.weapons if gear else ():
        if weapon.ref == "w3627":
            weapon.properties = weapon.properties | {"high crit"}


@power("f999", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f999(c: Cast) -> None:
    """The racial power adds a d8 to the roll it answers, not a d6.

    `p6186` reads its die through `c.dice_for`, so this is the one line. No
    gate: the card narrows by nothing, unlike f1836, which raises the same
    power's die only on a Nature check and has to say so."""
    c.change_dice("p6186", "1d8")


@power("f1061", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1061(c: Cast) -> None:
    """The racial attack rolls d8s for damage instead of d6s.

    One die, so "1d8" is the whole sentence; `p2480` asks `c.dice_for` for
    it rather than carrying the literal it used to."""
    c.change_dice("p2480", "1d8")


@power("f921", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       )
def f921(c: Cast) -> None:
    """Gives one named power damage it does not print, and the keyword that
    hands it back on a miss.

    The damage is written. `p1767` deals none on its card -- it is a knock-down
    burst -- so this is `c.change_dice` turning a die **on** rather than
    raising one: that row asks for a die defaulting to the empty string, and
    only this feat ever answers.

    **Reliable is what is dropped, and it is one named clause.** `dsl.use`
    reads `Keyword.RELIABLE in p.keywords` -- the row's *declared* keywords,
    which are the same tuple for every character holding it. Saying "this
    character's copy also has it" needs a per-creature set and a reader that
    consults it, which is the verb named above and not a sentence this row
    can write. The row plays without it; it simply spends on a miss.
    """
    c.change_dice("p1767", "1d8")
    # Reliable: recorded against the creature, because a row's keywords
    # are header data shared by everyone who holds it.
    c.counts_as_keyword("p1767", Keyword.RELIABLE)
@power("f725", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f725(c: Cast) -> None:
    """Written: the aiming is **offered**, which is what "instead of" means.

    The old note called this one row away and named the near miss exactly:
    a gated `blast_size` bonus rewrites a named row's range through
    `dsl._stretched`, but only the *size* of the kind the header declares,
    and this card changes the **kind** -- which decides provoking,
    `c.ranged`, `by_ranged` and the `ranged` context key, so a bigger blast
    would say the wrong rule as well as the wrong shape.

    `c.reshape_area` is that rewrite one word wider, and `optional=True` is
    the half the card insists on: "you can **choose** to make it an area
    burst 2 **instead of** a close blast 3" leaves the close blast on the
    menu. Replacing it would take the printed shape away from the only
    power this feat is about. #614.

    **The near miss is worth naming, because it is one row away.** A gated
    `c.bonus("blast_size", ...)` really does rewrite one named power's
    range line through `dsl._stretched` -- `f1059` above is written that
    way. But `_stretched` only adds to the size of the kind the header
    already declares, and this card changes the *kind*: `reach.kind`
    decides provoking, `c.ranged`, `by_ranged` and the `ranged` context
    key, so a bigger blast would say the wrong rule as well as the wrong
    shape.

    **Re-pointed off `c.recast(reach=)`, which was one symbol over two
    mechanisms.** This row rewrites a *named row's area* -- its size or
    its shape. `c.widen_areas` lays a `blast_size` modifier and
    `dsl._stretched` reads it, so growing every burst this caster throws
    is already sayable; what is not is naming **one** row, which is what
    all of these cards do. The other five rows on the old symbol wanted
    melee-as-ranged, which is a different rewrite -- see
    `c.recast(as_ranged=)`.
    """
    c.reshape_area(
        lambda _r: AreaBurst(2, within=10),
        ref="p1448",
        optional=True,
        on=c.me,
        until=When.ENCOUNTER,
    )


def _melee_or_close_at_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """I am the target of a melee or close attack."""
    row = get(getattr(ev, "power", ""))
    return (
        getattr(ev, "target", None) == me
        and row is not None
        and row.reach.kind in ("melee", "close_burst", "close_blast")
    )


@power("f935", level=1, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_REACTION, reach=PERSONAL, target=NO_TARGET,
       trigger="you are the target of a melee or close attack",
       on=Trigger(AttackDeclared, _melee_or_close_at_me,
                  "you are the target of a melee or close attack"))
def f935(c: Cast) -> None:
    """`c.recast` rewrites what a row costs and cannot give one a trigger,
    so the feat is written as the reaction itself and spends p2473
    through `c.use_power` -- which is the printed sentence, not an
    approximation of it.

    `AT_WILL`, because p2473's own encounter use is the limit the card
    prints and `c.use_power` spends it; a row of its own would refuse
    the second firing for the wrong reason."""
    c.use_power("p2473")


@power("f928", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f928(c: Cast) -> None:
    """A natural weapon with its own group, dice, proficiency and off-hand
    property, held whenever the hands are empty.

    **Written: `c.as_weapon` is the verb.** The marker said nothing puts a
    weapon into `Gear.weapons` from a row, and that is exactly what the
    verb does -- it was written for a shield that is also a weapon, which
    is the same shape. The profile is hand-written because the weapon
    table has no row for a claw, as the four item rows using the verb
    hand-write theirs.

    Two things the verb does not cover. The proficiency bonus is this
    card's own grant, so the ref is recorded in `Gear.trained`: otherwise
    `Cast._trained_with` withholds it from any creature that *has* a
    record, which is every built character. And "in each hand while you
    aren't holding anything" is a second profile with both in hand rather
    than on the belt -- `as_weapon` stows what it lays, which is right for
    a character already holding something, because then the claw is the
    draw `actions._wielding` offers.

    Enchanting them is not a fight."""
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return
    empty = not gear.held
    for _ in range(2 if empty else 1):
        c.as_weapon(
            damage="1d6", group="light blade", proficiency=3,
            properties=frozenset({"off-hand"}), hands="one-handed",
            until=When.ENCOUNTER,
        )
    gear.trained = gear.trained | {c.ref}
    if empty:
        gear.stowed.discard(c.ref)


# -- the rest of the gaps ---------------------------------------------------


@power("f718", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f718(c: Cast) -> None:
    """+1 to the roll `p6186` is improving, when that roll belongs to an
    arcane power.

    **Written, and the row this one was waiting for has landed.** The
    marker asked for a modifier on the amount of somebody else's boost and
    named `i2295x1` as the same gap from the other side; that row is
    written, and its answer is the one line below. `p6186` asks
    `c.dice_for` for what it adds and `rng.roll` parses `NdM+K` with the
    flat term riding in the `Roll`, so "+1 to the triggering roll" is the
    same die with a `+1` on it. The context `p6186` hands over says which
    kind of roll it is and which power rolled it, so the narrowing is
    exact rather than every roll the race improves.

    Neither `c.boost_roll` nor `c.change_dice` alone would have said it:
    the first adds to a roll already made, and a bare `change_dice` swaps
    the die rather than adding to the result."""

    def arcane_attack(ctx: dict[str, Any]) -> bool:
        return ctx.get("roll_kind") == "attack" and _arcane_row(ctx)

    c.change_dice("p6186", "1d6+1", on=c.me, when=arcane_attack)


@power("f933", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f933(c: Cast) -> None:
    """No opportunity attacks for firing a hand crossbow in one hand with a
    light blade in the other. `c.no_provoke` takes a `when=` now.

    **"Ranged" needs no test here.** `Power.provokes_on` opens this window for
    `ranged`, `area_burst` and `wall` only, so a window that exists is already
    a ranged or area attack -- testing the shape again would be a second copy
    of that rule. What the gate adds is the grip the card names and the attack
    being made with a **weapon** rather than an implement.

    `ENCOUNTER` became `AT_WILL`: the card prints no limit and a triggered
    trait declared per-encounter is spent on its first firing, which `lint.py`
    checks for."""
    def firing_it(ctx: dict[str, Any]) -> bool:
        row = get(str(ctx.get("why", "")).split(" ", 1)[0])
        gear = c.world.get(c.me, Gear)
        if row is None or gear is None or Keyword.WEAPON not in row.keywords:
            return False
        held = gear.held
        return (any(w.ref == "w3627" for w in held)
                and any(w.group == "light blade" for w in held))

    c.no_provoke(on=c.me, until=When.ENCOUNTER, when=firing_it)


def _used_area_arcane(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """I used an area arcane attack power."""
    row = get(getattr(ev, "power", ""))
    return (
        ev.actor == me
        and row is not None
        and row.attack is not None
        and Keyword.ARCANE in row.keywords
        and row.reach.kind in ("area_burst", "wall")
    )


@power("f1149", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use an area arcane attack power",
       on=Trigger(PowerUsed, _used_area_arcane,
                  "you use an area arcane attack power"))
def f1149(c: Cast) -> None:
    """Not `c.no_provoke(when=)` after all: `from_` names the creature
    whose opening is closed, which is exactly "the creatures you target
    with that power". `dsl.use` announces `PowerUsed` **above** the
    provoke check, so the immunity is laid in time, and targets are
    chosen before the body so `ev.targets` is trustworthy there.

    `AT_WILL` because a triggered `action=NONE` row spends a use every
    firing and the card prints no limit."""
    for foe in getattr(c.trigger, "targets", ()):
        c.no_provoke(from_=foe, on=c.me, until=When.EOT)


@power("f1021", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.pre_empt(keyword=)",))
def f1021(c: Cast) -> None:
    """A trade offered on every implement attack: two off the roll for
    two radiant on a hit. `c.may` asks a yes-or-no inside a body that is
    already running; nothing offers a choice from a standing modifier,
    so the penalty would be compulsory and the row strictly worse than
    not having it.

    **`c.pre_empt` is not the near miss it looks like.** That verb keys a
    substitute to a `(ref, what)` pair and `Powers.pre_empts` turns each
    registration into its own entry in the action menu. This card names no
    row -- the trade is on *any* implement attack -- so there is nothing to
    key it to and no menu entry it could become. The two siblings below
    each name their rows and are a different gap for that reason.

    **Re-pointed, because `c.opt_in()` was serving two needs and is now
    down to this one.** `f1097`, `f1098` and `f1099` carried it too and
    none of them wanted what this row wants: each named *specific* powers,
    so each belongs to #550's convention -- the clause written into the
    power, gated on `c.feat` -- and those are written. `f1097`'s was not
    even an opt-in; its card forgoes nothing.

    What is left here is precisely the thing the paragraph above describes:
    a substitution keyed to a **keyword** rather than a ref, so the offer
    can be made at any implement attack. `c.pre_empt(keyword=)` names
    that, and `content/CLAUDE.md` already carves out this case -- *"the
    exception is a feat naming a class of powers -- 'any implement
    attack'"*. #550."""


@power("f1099", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       implemented_in=("p836", "p1580"))
def f1099(c: Cast) -> None:
    """The skill bonus is this row's own; both riders are written where
    they are read.

    **The old note located the work exactly and is why this was quick.**
    It said: *"what is missing is the read site, not the verb ... wrapping
    those is one line each in `powers/paladin/level_1.py` and
    `powers/cleric/level_1.py`, not here; registering from this side alone
    lays a substitute nothing reads and would look finished."* Correct in
    every part, and `#550`'s convention says the same thing in general --
    a feat naming one power writes its clause **into** that power, gated
    on `c.feat`, rather than registering a rider from here.

    So the clauses live in `p836` and `p1580` and this carries
    `implemented_in=`, which `audit.py` buckets separately rather than
    reporting the row silent. The feat is unbracketed (`feat.category` is
    empty in `game.db`), so each is a plain `if` and not a `c.declare`
    chain.

    `p1580`'s half is the one worth reading twice: the card trades the
    bonus granted to **an ally**, so the caster's own +1 is untouched.

    A plain "+2 bonus" with the word "bonus" and no type in front of it,
    so untyped.
    """
    c.bonus("skill:intimidate", 2, on=c.me, until=When.ENCOUNTER)


def _arcane_damage(ctx: dict[str, Any]) -> bool:
    """The blow being resolved came out of an arcane power."""
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.ARCANE in p.keywords


@power("f1098", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       )
def f1098(c: Cast) -> None:
    """Re-aimed from `todo` to `dropped`: the p839 clause plays, so the
    row is offered rather than refused.

    Which ally p839 handed the opening to is a `c.choose` inside that
    row's body and nothing reports it -- but the ally it chose is the
    one now carrying an effect p839 laid, so `c.suffering("p839")`
    names them. Read on `PowerResolved`, which is emitted *below* the
    body: a `Hit` watcher fires while p839 is still mid-strike and the
    opening has not been handed over yet.

    **Dropped, and both for a read site rather than a verb.** p1458
    retypes one named row's damage against one kind of target, and
    `c.deals` is an override keyed only to `Keyword.WEAPON` or
    `Keyword.IMPLEMENT`: `Cast._retyped` reads that label and nothing
    else, so narrowing it to a ref -- let alone to the target's origin --
    is a change at `cast.py`'s own read site.

    **p833's half is written and `c.opt_in()` has come off.** This note
    located it exactly -- "the one line owed is in
    `powers/paladin/level_1.py`" -- and proposed `c.pre_empt` with p833
    asking `c.instead_of("temp_hp", ...)`. It went in as #550's shape
    instead: the gate is `c.feat` and the branch lives in p833, because
    that convention replaced the rider one for a feat naming a single
    power, and `content/CLAUDE.md` gives the reason -- the rider shape only
    ever reached a power written to *ask*, and almost none were.

    **And the p1458 half is written, which was the last of the three.**
    That read-site change landed as two label fields: `ref=` picks the one
    named row and `vs_kind=` is the card's "against undead targets". It is
    laid from this body rather than written into `p1458`, because
    `Cast._typed` reads a standing retype unconditionally -- #550's
    convention is for a clause the power must *ask* about, and this is not
    one.

    So the row carries no marker. All three printed clauses play: the
    Diplomacy bonus, p833's save in lieu of temporary hit points, and
    p1458's radiant.

    The Diplomacy bonus was called "a check" and left unwritten, which
    was wrong: `skill:` bonuses are consulted, and the sibling f1099
    writes the same sentence about Intimidate. Untyped, no type word."""
    me = c.me
    c.bonus("skill:diplomacy", 2, on=me, until=When.ENCOUNTER)
    # **The p1458 clause, laid from here rather than written into that
    # row.** #550's convention is for a clause the power has to *ask*
    # about -- `c.instead_of`, a branch gated on `c.feat` -- and this one
    # needs no asking: `Cast._typed` reads a standing retype
    # unconditionally at the moment the dice are rolled, so the row being
    # changed needs no cooperation at all. `ref=` picks it and
    # `vs_kind=` is the card's "against undead targets".
    c.deals(
        DamageType.RADIANT, from_=DamageType.FIRE, ref="p1458",
        vs_kind="undead", implement=True, on=me, until=When.ENCOUNTER,
    )

    def opening(ev: Any) -> None:
        if ev.actor != me or ev.power != "p839":
            return
        struck = [r.target for r in ev.rolls if r.hit and _undead(c, r.target)]
        if not struck:
            return
        foe = struck[0]
        for friend in c.suffering("p839", by=me):
            c.bonus(
                "damage", c.cha_mod, on=friend, until=When.ENCOUNTER,
                once=True, dtype=DamageType.RADIANT,
                when=lambda ctx, t=foe: ctx.get("target") == t,
            )

    c.watch(PowerResolved, opening, on=me, until=When.ENCOUNTER)


@power("f1101", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1101(c: Cast) -> None:
    """All three markers named things that were already there.

    `query.surge_value` reads `Mods.total("surge_value")`, so the printed
    bump is an ordinary `c.bonus` and reaches the second wind and the
    natural twenty on a death save alike. "When you use this exploit and
    miss" is `Miss`, which is an event like any other. And the swing a
    row hands an ally is `granted_by`/`granted_via`, which ride on
    `PowerUsed`.

    p1061's rider is armed and inert, and the fault is not here: that
    row's body only *notes* that it would grant a swing, so nothing ever
    carries `granted_via == "p1061"`. Written against the hook rather
    than approximated, so it starts paying the day p1061 does.

    p1567 already adds Wisdom when the target is marked by me, so the
    printed "Wisdom plus Charisma" is Charisma on top of it.
    """
    me = c.me
    c.bonus("surge_value", 1, on=me, until=When.ENCOUNTER)

    def struck(ev: Any) -> None:
        if ev.attacker != me or not _undead(c, ev.target):
            return
        if ev.power == "p917" and (
            c.feat("cf:ranger-f2") or c.feat("cf:warlock-f2")
        ):
            c.flat(c.attack_mod, on=ev.target)
        elif ev.power == "p1567" and c.marked(on=ev.target, by=me):
            c.flat(c.cha_mod, on=ev.target)

    def fumbled(ev: Any) -> None:
        if ev.attacker != me or ev.power != "p997":
            return
        near = [
            foe for foe in enemies(c.world, me)
            if foe != ev.target and c.adjacent(to=foe) and _undead(c, foe)
        ]
        if near:
            c.flat(
                c.str_mod if c.wielding("two-handed") else c.str_mod // 2,
                on=near[0],
            )

    def handed(ev: Any) -> None:
        if (
            ev.granted_by == me
            and ev.actor != me
            and ev.granted_via == "p1061"
            and any(_undead(c, t) for t in ev.targets)
        ):
            c.bonus("attack", 2, on=ev.actor, until=When.EONT, once=True)

    c.watch(Hit, struck, on=me, until=When.ENCOUNTER)
    c.watch(Miss, fumbled, on=me, until=When.ENCOUNTER)
    c.watch(PowerUsed, handed, on=me, until=When.ENCOUNTER)


@power("f1063", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.as_basic(spent=True)",))
def f1063(c: Cast) -> None:
    """`c.as_basic(window="opportunity")` is the verb that files a stand-in
    for a granted swing -- `Powers.instead`, not `Powers.opportunity` --
    and `c.restore_use` is the printed "without expending it", handed
    back the moment the swing spends it. `Hit`/`Miss` carry
    `opportunity` as a plain attribute, which is the only place the
    window is legible from a watcher.

    Dropped: "even if you have used it this encounter".
    `dsl.basic_options` runs each stand-in past `usable`, which refuses
    a spent encounter power, so the option is missing for the one swing
    before this row has handed a use back."""
    me = c.me
    c.as_basic("p2480", window="opportunity", on=me)

    def unspend(ev: Any) -> None:
        if (
            ev.attacker == me
            and ev.power == "p2480"
            and getattr(ev, "opportunity", False)
        ):
            c.restore_use("p2480", on=me)

    for kind in (Hit, Miss):
        c.watch(kind, unspend, on=me, until=When.ENCOUNTER)


@power("f1066", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1066(c: Cast) -> None:
    """Both rolls of the basic attack the racial feature hands out.

    `rt:r24-t0` calls `c.basic`, so the swing carries that ref and
    the gate is the ref rather than "a basic attack", which would also
    pay for every ordinary one. No type word is printed.
    """
    gate = lambda ctx: (  # noqa: E731
        ctx.get("granted_via") == "rt:r24-t0"
        and ctx.get("granted_by") == c.me
    )
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=gate)
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=gate)


@power("f1026", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1026(c: Cast) -> None:
    """`resolve.attack` clears `Relation.HIDDEN_FROM` after it emits the
    `Miss` and still **inside** the `roll` callback, so the AFTER window
    of `AttackDeclared` is on the far side of the clear. Noting the
    concealment on the miss and putting it back there brackets the
    clear -- the same bracket `f719` uses -- where a watcher on `Miss`
    alone is undone a line later.

    `kept` is filled only by a miss, so a hit leaves the restore with
    nothing to do; it clears the list either way, which is what stops a
    stale miss from hiding the caster after a later swing."""
    me = c.me
    kept: list[int] = []

    def missed(ev: Any) -> None:
        row = get(ev.power)
        if ev.attacker == me and row is not None and row.reach.kind in (
            "ranged", "area_burst", "wall"
        ):
            kept.extend(hidden_from(c.world, me))

    def restore(ev: Any) -> None:
        if ev.attacker != me:
            return
        for watcher in kept:
            c.hide(from_=watcher)
        kept.clear()

    c.watch(Miss, missed, on=me, until=When.ENCOUNTER)
    c.watch(AttackDeclared, restore, on=me, until=When.ENCOUNTER)


@power("f1106", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1106(c: Cast) -> None:
    """Low-light vision, which is neither `c.truesight` nor
    `c.see_invisible` -- it answers dim light and not darkness."""
    c.low_light()


@power("f1148", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your x_m5139a3 racial power",
       on=Trigger(PowerUsed,
                  lambda w, me, ev: ev.actor == me and ev.power == "x_m5139a3",
                  "you use that racial power"))
def f1148(c: Cast) -> None:
    """AT_WILL rather than ENCOUNTER: a triggered `action=NONE` row spends
    a use every firing and the card prints no limit.

    Laid on the caster, which is where an ignore lives -- it is the
    attacker's property, not a change to the creature being hit. No
    type, so it is every resistance, which is what "your enemies'
    resistances" says."""
    c.ignore_resistance(on=c.me, until=When.EONT, when=_arcane_damage)


@power("f1158", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f1158(c: Cast) -> None:
    """"Before the end of your turn", not your next turn. Neither bonus
    prints a type word, so both are untyped."""
    me = c.me
    c.bonus("attack", 1, on=me, until=When.EOT, when=_arcane_row)
    c.bonus("damage", c.con_mod, on=me, until=When.EOT, when=_arcane_row)






