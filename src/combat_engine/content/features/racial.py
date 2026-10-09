"""The racial traits, as ordinary rows.

A race's page is three kinds of sentence and only the third is here.

**Numbers on the sheet** -- size, speed, fly speed, the two ability
scores, the skill bonuses, the healing surge a race adds or takes away,
and the initiative bonus three of them print -- are read off the `race`
table by `chargen.RaceLine` and laid by `chargen.spawn`. None of it is
transcribed and none of it belongs in a row: a trait is armed at the top
of an encounter, and initiative is rolled before that and a skill check
outside it entirely.

**Racial powers** are separate cards with refs of their own, written
elsewhere. `RaceLine.granted` puts them in `Powers.known` beside the
traits -- all of them, or one where the block says to choose.

**Everything else is here**, one row per named trait, `rt:<race>-<what
it does>`. `RaceLine.traits` finds them by that prefix rather than from a
list, so writing one wires it up.

Two families are built by a factory rather than typed out. Nineteen
races print an origin, a type or a subtype and all nineteen want the
same one-line body; thirty-odd print a trait whose whole content is a
rest rule, a language or a skill choice. Copying either fifty times
would be fifty chances to mistype a ref and nothing gained.

**A choice the page makes you record was already recorded.** Every
racial option in the book is "choose one of these *powers*", and
`RaceLine.one_of` says which races mean it: `RaceLine.granted` picks one
of the list and puts it in `Powers.known`. So the pick is written down,
by ref, in the place the compendium's own feats read it from -- their
prerequisite line is `race r33 & has p10043`, not a build leg. `_holds`
is that read, and the four rows that carried `c.race_option()` all use
it: three fork on which power arrived, and the fourth is inert because
the power *is* the whole benefit.

What is still missing there is smaller than a verb. `Character` has no
field naming which option was taken, so `granted` always deals the first
of the list and a player cannot pick. That is one field in `chargen.py`
beside `race`, and no row waits on it: a row reading `Powers.known` is
right whichever one is dealt.

What the engine still cannot say, and what is therefore marked, is in
each row's own docstring; nothing in this file is blocked on a symbol
more than two rows want.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Bloodied,
    Cast,
    Condition,
    ConditionEnded,
    Cover,
    DamageApplied,
    DamageType,
    Dropped,
    Escaped,
    Gear,
    Ident,
    InitiativeRolled,
    Keyword,
    Powers,
    SavingThrow,
    SecondWind,
    SurgeSpent,
    Trigger,
    TurnStart,
    When,
    Window,
    about_me,
    power,
)
from combat_engine.engine.durations import keywords_of
from combat_engine.engine.query import concealment_of, cover_between, flanked_by

#: A trait is armed once at the start of the fight and holds all fight.
_HOLDS = When.ENCOUNTER

#: The three conditions the mind-defence family of saves names. Spelled by
#: condition rather than by the family's printed name, which belongs in
#: `localization/` -- `leaks.py` reported it here the moment racial traits got
#: rows and their labels got indexed. #341.
_MIND = frozenset({Condition.DAZED, Condition.DOMINATED, Condition.STUNNED})
#: And the three the movement-freeing family names.
_HELD = frozenset({Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED})


def _against(*conditions: Condition) -> Callable[[dict[str, Any]], bool]:
    """A save-context gate reading the conditions the effect carries."""
    wanted = frozenset(conditions)
    return lambda ctx: bool(wanted & ctx.get("conditions", frozenset()))


def _keyword(word: Keyword) -> Callable[[dict[str, Any]], bool]:
    """A save-context gate reading the keywords of the row that laid it."""
    return lambda ctx: word in ctx.get("keywords", frozenset())


def _shielded(c: Cast, eid: int) -> bool:
    """Is this creature holding a shield? `Gear.shield` is the only record."""
    gear = c.world.get(eid, Gear)
    return bool(gear is not None and gear.shield)


def _melee(ctx: dict[str, Any]) -> bool:
    """A damage context's "this was a melee attack"."""
    return not ctx.get("ranged", False)


def _ongoing(*types: DamageType) -> Callable[[dict[str, Any]], bool]:
    """A save-context gate on ongoing damage, of these types or of any.

    The save context carries `ongoing`, `dtype` and `dtypes`, which is both
    halves of "saving throws against ongoing fire damage".
    """

    def gate(ctx: dict[str, Any]) -> bool:
        if not ctx.get("ongoing"):
            return False
        if not types:
            return True
        carried = set(ctx.get("dtypes") or ())
        if ctx.get("dtype") is not None:
            carried.add(ctx["dtype"])
        return bool(carried & set(types))

    return gate


def _holds(c: Cast, ref: str) -> bool:
    """Does **this** creature have that row?

    Not `c.knows`, which answers who *on the board* has it and is true for
    a character standing next to somebody else's manifestation. A race's
    option is recorded as the power `RaceLine.granted` dealt, so this is
    the read that tells one leg of a racial fork from another.
    """
    known = c.world.get(c.me, Powers)
    return known is not None and ref in known.all


def _my_class(c: Cast) -> str:
    """The character's class, off `Ident.ref` -- `chargen` writes `c:<cls>`.

    Empty for anything that is not a built character, which is what the two
    rows reading it want: neither has anything to borrow from.
    """
    ident = c.world.get(c.me, Ident)
    ref = ident.ref if ident is not None else ""
    return ref[2:] if ref.startswith("c:") else ""


def _origin(
    race: str, *words: str, dropped: tuple[str, ...] = (), why: str = ""
) -> None:
    """"You are considered a <kind> creature for the purpose of effects
    that relate to creature origin." The same factory covers the two
    pages that print a type or a subtype rather than an origin; all three
    are one word to `c.kinds_of`.

    `c.kinds_of` reads the `kind` and `origin` columns of a compendium
    row and a character's row is its class, so `c.set_origin` writes the
    word onto the creature instead and `kinds_of` unions the two. Every
    reader in the tree asks `c.kinds_of` or `c.is_kind`, so one place to
    write it is one place to read it.
    """

    def body(c: Cast) -> None:
        c.set_origin(*words, until=_HOLDS)

    body.__name__ = f"rt_{race}_origin"
    body.__doc__ = why or _origin.__doc__
    power(
        f"rt:{race}-origin",
        level=0, cls="", usage=AT_WILL, action=ActionType.NONE,
        reach=PERSONAL, target=SELF, **({"dropped": dropped} if dropped else {}),
    )(body)


#: What the two pages that print "you are both X and undead" lose. Every
#: row meaning "a living creature" spells it as the absence of `undead`,
#: so a creature holding both words reads as neither -- and neither page
#: can be written any other way until one reader settles it.
_BOTH = (
    "Both words are written. The living half is dropped: no row asks "
    "for it directly, they all spell it as not being undead, so a "
    "creature that is both reads as neither."
)


def _inert(ref: str, why: str, **header: Any) -> None:
    """A named trait with no combat consequence: a rest rule, a language,
    a skill a character is trained in, a prerequisite it may claim.

    Declared rather than left out so that the page is accounted for. The
    flag is what tells `audit.py` to stop expecting the row to do
    anything and `coverage.py` to count it done.
    """

    def body(c: Cast) -> None:
        pass

    body.__name__ = ref.replace(":", "_").replace("-", "_")
    body.__doc__ = why
    power(
        ref,
        level=0, cls="", usage=AT_WILL, action=ActionType.NONE,
        reach=PERSONAL, target=SELF, out_of_combat=True, **header,
    )(body)


# -- r1 ----------------------------------------------------------------


@power("rt:r1-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r1_t0(c: Cast) -> None:
    """A quarter of maximum hit points is what `query.surge_value`
    already answers; the Constitution modifier is laid on top of it.
    Untyped -- the page prints no word in front of it and does not call
    it a bonus at all."""
    c.bonus("surge_value", c.con_mod, on=c.me, until=_HOLDS)


@power("rt:r1-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r1_t1(c: Cast) -> None:
    """Gated rather than laid when the blooding happens: a trait is armed
    once and the condition comes and goes with healing."""
    me = c.me
    c.bonus("attack", 1, kind="racial", on=me, until=_HOLDS,
            when=lambda ctx: c.bloodied(me))


# -- r2 ----------------------------------------------------------------


@power("rt:r2-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r2_t0(c: Cast) -> None:
    """"Against poison" is read off the keywords of the row that laid the
    effect, which is what the save context carries."""
    c.bonus("save", 5, kind="racial", on=c.me, until=_HOLDS,
            when=_keyword(Keyword.POISON))


@power("rt:r2-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       out_of_combat=True,
       proficiency=("w3606", "w3607"))
def rt_r2_t2(c: Cast) -> None:
    """Which weapons a character may pick up is settled when it is built,
    so the whole benefit is the header field `chargen.proficiency` reads.
    The body has nothing to do in a fight."""


@power("rt:r2-t3", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       dropped=("Gear.load",))
def rt_r2_t3(c: Cast) -> None:
    """The armour penalty is a square taken off in `chargen.spawn`, so
    giving it back is a square of speed rather than a rule about armour --
    and it is laid only when there is a penalty to undo, or a dwarf in
    leather would walk 6. A heavy load is not carried anywhere."""
    gear = c.world.get(c.me, Gear)
    if gear is not None and gear.armour in ("scale", "plate"):
        c.bonus("speed", 1, on=c.me, until=_HOLDS)


@power("rt:r2-t4", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       dropped=("query.knocked_prone()",))
def rt_r2_t4(c: Cast) -> None:
    """One square less of any forced move is exactly `c.resist_forced`.

    The prone half is dropped: `ConditionApplied` says who applied the
    condition and not whether an *attack* did, so a save laid on every
    prone would also answer a row that puts you down as an Effect line,
    which the printed trait does not.
    """
    c.resist_forced(1, on=c.me, until=_HOLDS)


# -- r3 ----------------------------------------------------------------

_inert("rt:r3-t0",
       "Training in a skill of your choice. `engine/skills.py` has no "
       "training model at all -- a check is the ability modifier plus "
       "half level -- so there is nothing for the +5 to be laid on.")
_inert("rt:r3-t1", "Proficiency, which is a build-time sentence.",
       proficiency=("w3610",))
_inert("rt:r3-t5",
       "Four hours of trance for six of sleep. A rest rule; no fight "
       "reaches it.")
_origin("r3", "fey")


@power("rt:r3-t2", level=0, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def rt_r3_t2(c: Cast) -> None:
    """Both halves are printed racial, so neither stacks with another
    racial bonus to the same thing."""
    me = c.me
    c.bonus(WILL, 1, kind="racial", on=me, until=_HOLDS)
    c.bonus("save", 5, kind="racial", on=me, until=_HOLDS,
            when=_keyword(Keyword.CHARM))


# -- r4 ----------------------------------------------------------------

_inert("rt:r4-t1", "Proficiency, which is a build-time sentence.",
       proficiency=("w3631", "w3630"))
_origin("r4", "fey")


@power("rt:r4-t3", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       dropped=("c.grants_in(unless=)",))
def rt_r4_t3(c: Cast) -> None:
    """An aura and not a snapshot: the printed line is about standing
    within 5 squares, so it has to end when an ally walks out, which is
    what `c.grants_in` says and a plain `c.bonus` cannot.

    "Non-<race> allies" is dropped, and **not for want of a race on the
    creature** -- `chargen.Character.choices` carries `race:<ref>` on
    `Build.choices`, so `c.build("race:r4", on=ally)` is the question.
    It is that `c.grants_in` takes a side and no predicate: the exclusion
    has a subject and nowhere to sit. `c.bonus(on=ally, when=...)` laid
    per ally is not a substitute -- it would snapshot the allies standing
    there when the trait was armed and miss anything summoned later.
    """
    c.grants_in(c.aura(5, label=c.ref, until=_HOLDS),
                "skill:perception", 1, side="ally", kind="racial")


@power("rt:r4-t4", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r4_t4(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    **The earlier note here was wrong on its own suggestion** and it is worth
    saying which way: it proposed `Movement.using`, which names the *mode* a
    creature is travelling in -- flying, climbing, swimming -- and a shift is
    not a mode, so the gate would never have read true. The lever is the move
    `kind`, which `step` and `MoveStart.kind_` already carry, and the cost
    search now takes it. The `c.ignores_difficult(while_shifting=)` spelling
    that note mentions is the same gap and folds in here.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


# -- r5 ----------------------------------------------------------------


@power("rt:r5-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r5_t0(c: Cast) -> None:
    """Read off the keywords of the row that laid the effect."""
    c.bonus("save", 5, kind="racial", on=c.me, until=_HOLDS,
            when=_keyword(Keyword.FEAR))


@power("rt:r5-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r5_t1(c: Cast) -> None:
    """The attack context carries `opportunity`, so the narrowing is a
    gate rather than a guess at which row an opportunity attack is."""
    c.bonus(AC, 2, kind="racial", on=c.me, until=_HOLDS,
            when=lambda ctx: bool(ctx.get("opportunity")))


# -- r6 ----------------------------------------------------------------

_inert("rt:r6-t0",
       "Which feats a character may take. `chargen.meets` reads one race "
       "off `Character.race`; counting as two is a second field there, "
       "not a thing that happens in a fight.")


@power("rt:r6-t3", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r6_t3(c: Cast) -> None:
    """"A 1st-level at-will attack power from a class different from
    yours, which you can use as an encounter power" -- the multiclass
    sentence, and `c.borrow_row` is the verb nineteen feats already say
    it with. `uses=1` is the printed cadence laid over an at-will row.

    The set is built here rather than passed as `cls=`, because the
    printed narrowing is *every* class but this character's and
    `c.borrow_row` takes one name.

    The page prints this **or** a racial power and means one of them, so
    the row stands down for a character `RaceLine.granted` dealt the
    power: which one arrived is the record of the choice, the same way
    the compendium's own feats gate on it.
    """
    if _holds(c, "p13689"):
        return
    from combat_engine.engine.dsl import REGISTRY

    mine = _my_class(c)
    among = [
        ref
        for ref, p in REGISTRY.items()
        if p.cls and p.cls != mine and p.level == 1
        and p.usage is AT_WILL and p.attack is not None
        and not ref.startswith("cf:")
    ]
    c.borrow_row(among=among, uses=1)


@power("rt:r6-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r6_t1(c: Cast) -> None:
    """An aura for the same reason the perception one is: the bonus is
    about where an ally is standing now."""
    c.grants_in(c.aura(10, label=c.ref, until=_HOLDS),
                "skill:diplomacy", 1, side="ally", kind="racial")


# -- r7 ----------------------------------------------------------------

_inert("rt:r7-t0",
       "An extra feat at 1st level. Already true: `chargen.feat_slots` "
       "deals this race one more, which is where a build-time rule "
       "belongs.")
_inert("rt:r7-t1",
       "Training in one more skill, and there is no training model.")


@power("rt:r7-t4", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r7_t4(c: Cast) -> None:
    """"One extra 1st-level at-will attack power from your class."

    `c.borrow_row` reads that set off the registry by class, level and
    usage -- the same read `chargen.loadout` makes -- and `uses=0` leaves
    the row its own printed cadence, which for an at-will is the whole
    benefit: an extra one, every turn.

    The other leg of the fork is the racial power the page offers
    instead, read off `Powers.known` the way `rt:r6-t3` reads it.
    """
    if _holds(c, "p13213"):
        return
    mine = _my_class(c)
    if mine:
        c.borrow_row(mine, level=1, usage=AT_WILL, uses=0)


@power("rt:r7-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r7_t2(c: Cast) -> None:
    """Three separate modifiers, because a defence bonus is keyed by the
    defence it is a bonus to."""
    me = c.me
    for defence in (FORT, REF, WILL):
        c.bonus(defence, 1, kind="racial", on=me, until=_HOLDS)


# -- r8 ----------------------------------------------------------------


@power("rt:r8-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r8_t0(c: Cast) -> None:
    """The attack context names its target, so "against bloodied enemies"
    is asked of the creature being swung at rather than of the swinger."""
    me = c.me
    c.bonus(
        "attack", 1, kind="racial", on=me, until=_HOLDS,
        when=lambda ctx: ctx.get("target") is not None and c.bloodied(ctx["target"]),
    )


@power("rt:r8-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r8_t1(c: Cast) -> None:
    """Five plus half level, which is the printed formula and not a
    number to transcribe."""
    c.resist(5 + c.level // 2, DamageType.FIRE, on=c.me, until=_HOLDS)


# -- r10 ---------------------------------------------------------------


@power("rt:r10-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.oversized()",))
def rt_r10_t0(c: Cast) -> None:
    """Wielding a weapon a size up. `Weapon` carries no size and nothing
    refuses one for being too big, so the permission has nothing to
    permit."""


# -- r14 ---------------------------------------------------------------

_origin("r14", "shapechanger")


@power("rt:r14-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r14_t2(c: Cast) -> None:
    """A flat racial bonus to one defence."""
    c.bonus(WILL, 1, kind="racial", on=c.me, until=_HOLDS)


# -- r16 ---------------------------------------------------------------

_inert("rt:r16-t2", "A rest rule; no fight reaches it.")
_origin("r16", "fey")


# -- r17 ---------------------------------------------------------------


@power("rt:r17-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r17_t1(c: Cast) -> None:
    """**Untyped, both halves.** The card prints no word in front of
    "bonus" here where its cousins print "racial", so these two stack
    with a racial bonus to the same thing and the others do not."""
    me = c.me
    c.bonus(WILL, 1, on=me, until=_HOLDS)
    c.bonus("save", 2, on=me, until=_HOLDS, when=_keyword(Keyword.CHARM))


# -- r18 ---------------------------------------------------------------


@power("rt:r18-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r18_t1(c: Cast) -> None:
    """The save context carries the conditions the effect holds, so the
    three the card names are a gate."""
    c.bonus("save", 2, kind="racial", on=c.me, until=_HOLDS,
            when=_against(*_MIND))


@power("rt:r18-t3", level=0, cls="", usage=AT_WILL,
       action=ActionType.FREE, reach=PERSONAL, target=NO_TARGET,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def rt_r18_t3(c: Cast) -> None:
    """`SecondWind` is the event that exists for exactly this sentence;
    `SurgeSpent` is not a substitute, since a dozen leader rows spend a
    surge without a second wind being taken."""
    c.shift(3)


# -- r19 ---------------------------------------------------------------


@power("rt:r19-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r19_t0(c: Cast) -> None:
    """Untyped: the card prints no word in front of "bonus". The 21st
    level step is paragon and out of scope."""
    me = c.me
    c.bonus("damage", 2, on=me, until=_HOLDS, when=lambda ctx: c.bloodied(me))


@power("rt:r19-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r19_t2(c: Cast) -> None:
    """The damage context carries the target and whether the attack was
    ranged, which is both halves of the printed line. `c.allies` leaves
    the character itself out, which is what "two or more of your allies"
    means."""
    me = c.me

    def crowded(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or not _melee(ctx):
            return False
        return sum(1 for a in c.allies() if c.adjacent_to(victim, a)) >= 2

    c.bonus("damage", 2, on=me, until=_HOLDS, when=crowded)


# -- r20 ---------------------------------------------------------------

_inert("rt:r20-t2",
       "A wizard cantrip once an encounter, and every cantrip in the "
       "tree is itself out of combat.")
_origin("r20", "fey")


@power("rt:r20-t4", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r20_t4(c: Cast) -> None:
    """Read off the keywords of the row that laid the effect."""
    c.bonus("save", 5, kind="racial", on=c.me, until=_HOLDS,
            when=_keyword(Keyword.ILLUSION))


@power("rt:r20-t3", level=0, cls="", usage=AT_WILL,
       action=ActionType.FREE, reach=PERSONAL, target=NO_TARGET,
       trigger="you make an initiative check",
       on=Trigger(InitiativeRolled, about_me, "you make an initiative check"))
def rt_r20_t3(c: Cast) -> None:
    """Written as a **triggered** row rather than a trait, which is what
    reaches the moment the card names.

    `Encounter.start` arms triggers *before* it rolls initiative and arms
    traits after, deliberately and in a comment saying so -- so a trait
    really cannot be present for the check, and a trigger on
    `InitiativeRolled` can. The old note here claimed neither the event
    nor the ordering existed.

    "Any cover or concealment" is asked of both: concealment is carried
    on the creature, cover is traced from an attacker, so any enemy the
    check could be made against will do. The Stealth check is rolled
    against the best passive Perception watching, which is the shape
    `cf:rogue-tactic-stealth` already uses.

    Not `ENCOUNTER` (#210): the card prints no limit, and initiative is
    rolled once a fight anyway.
    """
    me = c.me
    foes = c.enemies()
    sheltered = concealment_of(c.world, me) is not Cover.NONE or any(
        cover_between(c.world, foe, me) is not Cover.NONE for foe in foes
    )
    if not sheltered:
        return
    watching = [c.passive("perception", of=foe) for foe in foes]
    if c.check("stealth", max(watching) if watching else 10):
        c.hide()


# -- r21 ---------------------------------------------------------------


@power("rt:r21-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r21_t0(c: Cast) -> None:
    """A flat racial bonus to one defence."""
    c.bonus(REF, 1, kind="racial", on=c.me, until=_HOLDS)


# -- r22 ---------------------------------------------------------------


@power("rt:r22-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r22_t2(c: Cast) -> None:
    """Both shields and the adjacency are asked when the bonus is read
    rather than when it is laid: the line is about where the two of them
    are standing at the moment of the blow."""
    me = c.me

    def in_line(_ctx: dict[str, Any]) -> bool:
        if not _shielded(c, me):
            return False
        return any(c.adjacent(a) and _shielded(c, a) for a in c.allies())

    c.bonus(AC, 1, kind="racial", on=me, until=_HOLDS, when=in_line)


# -- r23 ---------------------------------------------------------------

_origin("r23", "reptile")


@power("rt:r23-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r23_t2(c: Cast) -> None:
    """The attack context names the attacker, and `c.is_trap` is the
    question the engine already answers about one -- a trap is a thing on
    the board with no `Health` and no `Side`."""
    me = c.me

    def by_a_trap(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.is_trap(who)

    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, kind="racial", on=me, until=_HOLDS, when=by_a_trap)


# -- r24 ---------------------------------------------------------------


@power("rt:r24-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL,
       target=NO_TARGET,
       trigger="you drop to 0 hit points or fewer",
       on=Trigger(Dropped, about_me, "you drop to 0 hit points or fewer"))
def rt_r24_t0(c: Cast) -> None:
    """An interrupt, so the swing happens while the character is still
    up. A melee basic needs somebody in reach and there may be nobody --
    a death throe with no neighbour simply does not land."""
    near = [e for e in c.enemies() if c.adjacent(e)]
    if near:
        c.basic(on=near[0])


@power("rt:r24-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       dropped=("query.charging()",))
def rt_r24_t2(c: Cast) -> None:
    """The attack context's `charge` is the *attacker's* charge, and the
    printed narrowing is to opportunity attacks provoked during **your**
    charge -- which nothing records. Widened to every opportunity attack
    would be the other race's trait, so the narrowing is dropped and the
    bonus is laid on what can be asked.

    `OpportunityWindow.why` is not the missing piece, checked: the only
    thing `movement` ever puts in it is "moved away". `c.charge_at` runs
    the walk through `run_at` and only then sets the flag on the *swing*,
    so the run itself is an ordinary move to everything watching it.
    """
    c.bonus(AC, 2, kind="racial", on=c.me, until=_HOLDS,
            when=lambda ctx: bool(ctx.get("opportunity")))


# -- r25 ---------------------------------------------------------------


@power("rt:r25-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r25_t0(c: Cast) -> None:
    """`query.speed` is handed `{"charge": True}` by the three places
    that measure a charge's run and nothing by everything else, so the
    gate is the whole of the printed narrowing."""
    c.bonus("speed", 2, on=c.me, until=_HOLDS,
            when=lambda ctx: bool(ctx.get("charge")))


# -- r26 ---------------------------------------------------------------

_origin("r26", "shadow")


@power("rt:r26-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r26_t2(c: Cast) -> None:
    """A death save is labelled `death` in the save context, which is how
    "to death saving throws" is kept apart from a blanket save bonus."""
    me = c.me
    c.bonus(FORT, 1, kind="racial", on=me, until=_HOLDS)
    c.bonus("save", 2, kind="racial", on=me, until=_HOLDS,
            when=lambda ctx: ctx.get("label") == "death")
    c.bonus("save", 2, kind="racial", on=me, until=_HOLDS,
            when=_against(Condition.UNCONSCIOUS))


# -- r28 ---------------------------------------------------------------

_inert("rt:r28-t0",
       "No eating, drinking, breathing or sleeping. None of the four is "
       "modelled and the trait says all other effects apply normally.")
_inert("rt:r28-t1", "A rest rule; no fight reaches it.")


@power("rt:r28-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r28_t2(c: Cast) -> None:
    """A flat racial bonus to one defence."""
    c.bonus(WILL, 1, kind="racial", on=c.me, until=_HOLDS)


@power("rt:r28-t3", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r28_t3(c: Cast) -> None:
    """Two printed halves. The first is a gate: the save context says
    whether the effect carries ongoing damage.

    The second -- "take the better result of your die roll or 10" on a
    death save -- was marked `c.floor_save()` on the grounds that a
    listener can change whether a save succeeded and not what the die
    came to. **That is true and it is enough.** `turns._death_saves`
    beats 10, so a floor of 10 on the die is a save that cannot fail
    unless something else is dragging it down, and `SavingThrow` is a
    `Decision` whose `saved` is read back after the window. Taking 10
    also never takes the natural 20, so the surge that comes with one is
    untouched.
    """
    me = c.me
    c.bonus("save", 2, kind="racial", on=me, until=_HOLDS,
            when=lambda ctx: bool(ctx.get("ongoing")))

    def floor(ev: SavingThrow) -> None:
        if ev.actor == me and ev.against == "death" and not ev.saved:
            ev.saved = max(ev.natural, 10) + ev.bonus >= 10

    c.watch(SavingThrow, floor, until=_HOLDS, on=me, label=c.ref,
            window=Window.BEFORE)


# -- r33 ---------------------------------------------------------------

_origin("r33", "elemental")


def _magma(c: Cast) -> None:
    """"Whenever you take fire damage, your melee attacks deal 1d6 extra
    fire damage until the end of your next turn." A listener, because the
    moment is a blow landing and not the top of the fight."""
    me = c.me

    def stoked(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.FIRE in ev.types():
            c.bonus("damage", 0, dice="1d6", dtype=DamageType.FIRE, on=me,
                    until=When.EONT, when=_melee)

    c.watch(DamageApplied, stoked, until=_HOLDS, on=me, label=c.ref)


#: The thirteen manifestations, by the ref of the power each comes with.
#:
#: `RaceLine.one_of` is true for this race and `RaceLine.granted` deals
#: exactly one of these, so the ref in `Powers.known` *is* the choice --
#: which is how the compendium's own feats read it, their prerequisite
#: line being "race r33 & has p10044".
_MANIFESTATIONS = (
    "p1766", "p1767", "p1769", "p1770", "p1828", "p10043", "p10044",
    "p10045", "p10046", "p14073", "p14074", "p14075", "p14076",
)


@power("rt:r33-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r33_t0(c: Cast) -> None:
    """Thirteen legs, and the one taken is the one `Powers.known` holds.

    This carried `c.race_option()` on the grounds that a choice made when
    the character is built has nowhere to live. It has one: the whole of
    the choice is which of the thirteen *powers* comes with it, and
    `RaceLine.granted` already puts that one ref and no other in
    `Powers.known`. Nothing new had to be recorded.

    Resistances are flat 5 through heroic, as `rt:r49-t0`'s
    is: each block prints a step at 11th and another at 21st and both are
    out of scope. Breathing underwater and shrugging off the weather are
    printed on three of these legs and are not written -- no fight
    reaches either.
    """
    me = c.me
    taken = next((ref for ref in _MANIFESTATIONS if _holds(c, ref)), "")

    # The one leg printing no word in front of its defence bonus where
    # every other prints "racial". Untyped, therefore, and it stacks.
    if taken == "p1766":
        c.bonus(REF, 1, on=me, until=_HOLDS)
        c.resist(5, DamageType.FIRE, on=me, until=_HOLDS)
    elif taken == "p1767":
        c.bonus(FORT, 1, kind="racial", on=me, until=_HOLDS)
        c.bonus("save", 1, kind="racial", on=me, until=_HOLDS)
    elif taken == "p1769":
        c.bonus(FORT, 1, kind="racial", on=me, until=_HOLDS)
        c.resist(5, DamageType.LIGHTNING, on=me, until=_HOLDS)
    elif taken == "p1770":
        c.bonus("save", 2, kind="racial", on=me, until=_HOLDS,
                when=_ongoing())
    elif taken == "p1828":
        c.resist(5, DamageType.COLD, on=me, until=_HOLDS)
    elif taken == "p10043":
        c.resist(5, DamageType.ACID, on=me, until=_HOLDS)
    elif taken == "p10044":
        c.bonus(FORT, 1, kind="racial", on=me, until=_HOLDS)
        c.resist(5, DamageType.FIRE, on=me, until=_HOLDS)
    elif taken == "p10045":
        c.resist(5, DamageType.POISON, on=me, until=_HOLDS)
        c.bonus("save", 5, kind="racial", on=me, until=_HOLDS,
                when=_keyword(Keyword.DISEASE))
    elif taken == "p10046":
        c.resist(5, DamageType.PSYCHIC, on=me, until=_HOLDS)
        c.bonus(WILL, 1, kind="racial", on=me, until=_HOLDS)
    elif taken == "p14073":
        c.bonus(REF, 1, kind="racial", on=me, until=_HOLDS)
        c.bonus("save", 2, kind="racial", on=me, until=_HOLDS,
                when=_ongoing(DamageType.FIRE))
    elif taken == "p14074":
        c.bonus(FORT, 1, kind="racial", on=me, until=_HOLDS)
        _magma(c)
    elif taken == "p14075":
        # `escape` and not `skill:athletics`: `engine/escape.py` keeps a
        # key of its own for exactly this, so a bonus to getting out of a
        # grab does not raise every tumble the character ever makes.
        c.bonus("escape", 4, kind="racial", on=me, until=_HOLDS)
        c.bonus("save", 2, kind="racial", on=me, until=_HOLDS,
                when=_against(*_HELD))
    elif taken == "p14076":
        c.bonus("save", 2, kind="racial", on=me, until=_HOLDS,
                when=_ongoing(DamageType.FIRE, DamageType.RADIANT))


# -- r35 ---------------------------------------------------------------

_origin("r35", "immortal")


@power("rt:r35-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r35_t0(c: Cast) -> None:
    """Untyped -- the card prints no word before "bonus" -- and gated on
    the attacker, which the attack context names."""
    me = c.me

    def by_the_wounded(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.bloodied(who)

    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 1, on=me, until=_HOLDS, when=by_the_wounded)


@power("rt:r35-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r35_t1(c: Cast) -> None:
    """Two resistances, not one of two types: the card names both."""
    me = c.me
    amount = 5 + c.level // 2
    c.resist(amount, DamageType.NECROTIC, on=me, until=_HOLDS)
    c.resist(amount, DamageType.RADIANT, on=me, until=_HOLDS)


# -- r36 ---------------------------------------------------------------


@power("rt:r36-t1", level=0, cls="", usage=ENCOUNTER,
       action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
       trigger="the first time you are bloodied during an encounter",
       on=Trigger(Bloodied, about_me, "you are bloodied"))
def rt_r36_t1(c: Cast) -> None:
    """`ENCOUNTER` is what "the first time" means: the row is refused the
    second time its trigger fires. The 11th and 21st level steps are out
    of scope."""
    c.temp_hp(5, on=c.me)


@power("rt:r36-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r36_t2(c: Cast) -> None:
    """Untyped, and gated on the one key `query.speed` is handed."""
    c.bonus("speed", 2, on=c.me, until=_HOLDS,
            when=lambda ctx: bool(ctx.get("charge")))


# -- r37 ---------------------------------------------------------------

_inert("rt:r37-t1",
       "Roll twice on an Athletics check to jump or climb. `c.check` "
       "rolls once and nothing rerolls a skill check before it is made.")


@power("rt:r37-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r37_t0(c: Cast) -> None:
    """A flat racial bonus to one defence."""
    c.bonus(WILL, 1, kind="racial", on=c.me, until=_HOLDS)


# -- r38 ---------------------------------------------------------------


@power("rt:r38-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r38_t0(c: Cast) -> None:
    """Five plus half level, the printed formula."""
    c.resist(5 + c.level // 2, DamageType.ACID, on=c.me, until=_HOLDS)


@power("rt:r38-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r38_t1(c: Cast) -> None:
    """**Escaping a grab announces itself now.** `engine/escape.py` emits
    `Escaped`, carrying `actor` (whoever struggled), `holder` (the
    grabber) and `success` -- which is both printed directions in one
    event, and it is only emitted for an attempt that was actually
    rolled.

    "Whenever you escape a creature's grab **on your turn**" is
    `c.turn_of`; the other half, a creature escaping *your* grab, has no
    such narrowing and is read off `holder`.

    The armour clause -- "if you are wearing barbed armour the creature
    takes this damage only once" -- is not written: `Gear.armour` holds
    the printed armour kinds and there is no barbed one, so the
    condition is never true and the unqualified line is the whole of it.
    """
    me = c.me

    def barbs(ev: Escaped) -> None:
        if not ev.success:
            return
        if ev.actor == me and ev.holder != me and c.turn_of() == me:
            c.flat(2 + c.level // 2, on=ev.holder)
        elif ev.holder == me and ev.actor != me:
            c.flat(2 + c.level // 2, on=ev.actor)

    c.watch(Escaped, barbs, until=_HOLDS, on=me, label=c.ref)


# -- r41 ---------------------------------------------------------------


@power("rt:r41-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r41_t1(c: Cast) -> None:
    """Said once per printed word, which is the shape `ignores_difficult`
    takes: the labels are the ones the map gives its squares."""
    me = c.me
    c.ignores_difficult("mud", on=me, until=_HOLDS)
    c.ignores_difficult("shallow water", on=me, until=_HOLDS)


@power("rt:r41-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       keywords=[Keyword.POISON])
def rt_r41_t0(c: Cast) -> None:
    """An aura and a listener: the aura is the geometry the printed line
    names and `SurgeSpent` is the moment it pays out. Asking the aura at
    the moment the surge is spent is the point -- a snapshot taken when
    the trait is armed would weaken whoever happened to be standing there
    at the top of the fight."""
    me = c.me
    c.aura(2, label=c.ref, until=_HOLDS, on=me)

    def choke(ev: SurgeSpent) -> None:
        if ev.actor == me or ev.actor not in c.enemies():
            return
        if c.in_my_aura(ev.actor, label=c.ref):
            c.weakened(on=ev.actor, until=When.EOTNT)

    c.watch(SurgeSpent, choke, until=_HOLDS, on=me, label=c.ref)


# -- r43 ---------------------------------------------------------------

_inert("rt:r43-t2", "Imitating a sound, behind a Bluff check.")


@power("rt:r43-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r43_t0(c: Cast) -> None:
    """Combat advantage's +2 is computed in `resolve.attack` and is not a
    modifier, so the printed "+3 rather than +2" is written as the
    difference: one more, only when the advantage came from flanking."""
    me = c.me

    def by_flanking(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            victim is not None
            and bool(ctx.get("advantage"))
            and flanked_by(c.world, victim, me)
        )

    c.bonus("attack", 1, on=me, until=_HOLDS, when=by_flanking)


# -- r44 ---------------------------------------------------------------

_origin("r44", "fey")
_inert("rt:r44-t2",
       "An aspect of nature chosen at every extended rest, and each of "
       "the three is a power and nothing else -- 'you can use p744N "
       "while you are in this aspect' is the whole of every one of them. "
       "`RaceLine.one_of` is true for this race, so `RaceLine.granted` "
       "already deals exactly one of the three and the choice is made "
       "and recorded in `Powers.known`. There is nothing left for the "
       "row to lay. Re-choosing is an extended-rest rule and no fight "
       "reaches it.")


@power("rt:r44-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r44_t1(c: Cast) -> None:
    """The card says choose, so the row asks rather than picking one for
    the character: `c.choose` puts it to whoever is playing it."""
    defence = c.choose([FORT, REF, WILL], "which defence is hardened")
    if defence is not None:
        c.bonus(defence, 1, kind="racial", on=c.me, until=_HOLDS)


# -- r46 ---------------------------------------------------------------

_inert("rt:r46-t2",
       "Two-way speech within 5 squares. Nothing in a fight turns on "
       "whether a creature can talk.")


@power("rt:r46-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
       trigger="the start of your turn",
       on=Trigger(TurnStart, about_me, "the start of your turn"))
def rt_r46_t1(c: Cast) -> None:
    """One save per qualifying effect, named by its own label so that the
    extra throw reaches the daze and not every save-ends effect standing.

    The second half -- failing this one costs you the throw at the end of
    the turn -- is not written: `Effects.roll_saves` has no per-effect
    skip, and adding one would be an engine change.
    """
    for effect in list(c.world.effects.of(c.me)):
        if effect.when is When.SAVE_ENDS and _MIND & set(effect.conditions):
            c.save(on=c.me, against=effect.label)


# -- r47 ---------------------------------------------------------------

_inert("rt:r47-t1",
       "Counting as a second race for prerequisites. `Character.race` "
       "holds one ref and `chargen.meets` reads that one.")
_origin("r47", "undead", "living", dropped=("query.living()",), why=_BOTH)


@power("rt:r47-t3", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
       trigger="you drop to 0 hit points or fewer",
       on=Trigger(Dropped, about_me, "you drop to 0 hit points or fewer"))
def rt_r47_t3(c: Cast) -> None:
    """Dazed instead of unconscious while dying.

    `resolve` lays one effect labelled "dropped" carrying all three of
    unconscious, prone and dying, and nothing chooses what comes with
    it -- which is what `c.dying_as()` was asking for. It does not have
    to: `c.ignore_condition` **suppresses** a condition without ending
    the effect that carries it, which is exactly "you fall dazed instead
    of unconscious, and you make death saving throws as normal".

    Written as a trigger rather than a trait because the moment is the
    drop; `ev.dead` keeps it off a creature that was killed outright,
    which has no dying condition to soften.

    "If you fail a death saving throw you fall unconscious instead of
    being dazed" is the second listener, and being healed out of it is
    the third -- `_revive` ends the "dropped" effect, which announces
    `ConditionEnded` for each condition it held.
    """
    ev = c.trigger
    if ev is None or getattr(ev, "dead", False):
        return
    me = c.me
    hushed = c.ignore_condition(Condition.UNCONSCIOUS, on=me, until=_HOLDS)
    c.dazed(on=me, until=_HOLDS)

    def wake_up(why: str) -> None:
        if hushed is not None:
            c.end_effect(hushed, why=why)
        c.cure(Condition.DAZED, on=me)

    def failed(saved: SavingThrow) -> None:
        if saved.actor == me and saved.against == "death" and not saved.saved:
            wake_up("a death save was failed")

    def revived(ended: ConditionEnded) -> None:
        if ended.target == me and ended.condition is Condition.DYING:
            wake_up("no longer dying")

    c.watch(SavingThrow, failed, until=_HOLDS, on=me, label=c.ref)
    c.watch(ConditionEnded, revived, until=_HOLDS, on=me, label=c.ref)


# -- r49 ---------------------------------------------------------------

_inert("rt:r49-t2",
       "No eating, drinking, breathing or sleeping; none is modelled.")
_inert("rt:r49-t4", "Speech within 5 squares.")
_origin("r49", "immortal")


@power("rt:r49-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r49_t0(c: Cast) -> None:
    """Flat 5 through heroic; the 11th and 21st level steps are out of
    scope."""
    c.resist(5, DamageType.PSYCHIC, on=c.me, until=_HOLDS)


# -- r50 ---------------------------------------------------------------

_inert("rt:r50-t0",
       "Counting as a second race for prerequisites, which is one field "
       "on `Character` and not a rule in a fight.")
_inert("rt:r50-t3", "A rest rule.")


# -- r51 ---------------------------------------------------------------

_inert("rt:r51-t3", "A rest rule.")


@power("rt:r51-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.draw()",))
def rt_r51_t0(c: Cast) -> None:
    """Drawing or sheathing a weapon costs nothing here because it is not
    an action the engine has: `Gear.stowed` is set when the character is
    built and nothing moves a weapon in or out of it mid-fight.

    Re-aimed from `c.stow()`, which was this row alone, to `c.draw()`,
    which twelve rows in the tree already name for the same missing
    action. Sheathing is the same verb read backwards and does not need
    a second symbol.
    """


@power("rt:r51-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.running_start()",))
def rt_r51_t1(c: Cast) -> None:
    """`c.jump` takes a number of squares and knows nothing about a
    run-up, so "always considered to have a running start" has nothing to
    be true of."""


# -- r52 ---------------------------------------------------------------

_inert("rt:r52-t1",
       "Trading a class utility for a racial one, which is a choice made "
       "when the character is built.")
_inert("rt:r52-t3",
       "Training in Stealth, and there is no training model.")
_origin("r52", "shadow")


# -- r53 ---------------------------------------------------------------

_inert("rt:r53-t1", "A Bluff bonus for passing as something.")
_inert("rt:r53-t5",
       "Trading a class utility for a racial one, made when the "
       "character is built.")
_origin("r53", "undead", "living", dropped=("query.living()",), why=_BOTH)


@power("rt:r53-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r53_t0(c: Cast) -> None:
    """Gated rather than laid when the blooding happens, for the reason
    `rt:r1-t1` is: a trait is armed once and bloodied comes
    and goes with healing."""
    me = c.me
    c.penalty("surge_value", 2, on=me, until=_HOLDS,
              when=lambda ctx: c.bloodied(me))


@power("rt:r53-t4", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r53_t4(c: Cast) -> None:
    """Five plus half level, the printed formula."""
    c.resist(5 + c.level // 2, DamageType.NECROTIC, on=c.me, until=_HOLDS)


# -- r60 ---------------------------------------------------------------

_inert("rt:r60-t4",
       "Endurance against starvation and thirst, and meditation instead "
       "of sleep.")
_origin("r60", "fey")


@power("rt:r60-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r60_t2(c: Cast) -> None:
    """One call per printed word, which is how the labels the map gives
    its squares are matched."""
    me = c.me
    for kind in ("trees", "underbrush", "plants", "natural growth"):
        c.ignores_difficult(kind, on=me, until=_HOLDS)


@power("rt:r60-t5", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r60_t5(c: Cast) -> None:
    """The three conditions the card names, read off the effect."""
    c.bonus("save", 2, kind="racial", on=c.me, until=_HOLDS,
            when=_against(*_MIND))


# -- r61 ---------------------------------------------------------------

_inert("rt:r61-t2", "Talking to animals.")
_inert("rt:r61-t3",
       "A reach of 1 rather than the 0 a Tiny creature normally has. "
       "Reach is not derived from size here -- every creature reaches 1 "
       "unless a weapon says otherwise -- so this is already true. The "
       "Strength-check penalty is a check no row makes.")
_origin("r61", "fey")


# -- r62 ---------------------------------------------------------------

_inert("rt:r62-t4",
       "Extra hit points per surge spent during a short rest; a rest is "
       "not played out.")
_inert("rt:r62-t5", "Bluff as a class skill; there is no skill list.")
_origin("r62", "fey")


@power("rt:r62-t1", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
       trigger="the start of your turn",
       on=Trigger(TurnStart, about_me, "the start of your turn"))
def rt_r62_t1(c: Cast) -> None:
    """The printed line is an *extra* throw at the start of the turn; the
    end-of-turn one is the ordinary save `Effects.roll_saves` already
    makes. Named by label, so the extra throw reaches the fear effect and
    nothing else standing."""
    for effect in list(c.world.effects.of(c.me)):
        if effect.when is When.SAVE_ENDS and Keyword.FEAR in keywords_of(effect.label):
            c.save(on=c.me, against=effect.label)


# -- r65 ---------------------------------------------------------------

_inert("rt:r65-t0",
       "A +2 to one skill, picked from a list of twelve animals. The "
       "choice is recorded nowhere and every option is a skill bonus.")
_inert("rt:r65-t4", "Talking to animals.")
_origin("r65", "fey", "beast", "humanoid", "shapechanger",
        why="Three printed sentences and one row: the page gives a type, "
            "an origin and a subtype, and `rt:r65-t3` is the only "
            "trait ref the race has for any of them, so all four words go "
            "on together.")


@power("rt:r65-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r65_t2(c: Cast) -> None:
    """The saving-throw half is a gate on the conditions the effect
    carries.

    The escape half was dropped as unreachable. **It is reachable now**:
    `engine/escape.py` rolls the check through `skills.check` and reads
    an `escape` modifier off the struggling creature, a key it keeps
    apart from `skill:acrobatics` on purpose -- a bonus to getting out of
    a grab is not a bonus to tumbling.
    """
    me = c.me
    c.bonus("escape", 2, kind="racial", on=me, until=_HOLDS)
    c.bonus("save", 2, kind="racial", on=me, until=_HOLDS,
            when=_against(*_HELD))


# -- r66 ---------------------------------------------------------------

_inert("rt:r66-t3",
       "Dungeoneering as a class skill; there is no skill list.")
_origin("r66", "fey")


@power("rt:r66-t0", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r66_t0(c: Cast) -> None:
    """One call per printed word."""
    me = c.me
    for kind in ("rubble", "uneven stone", "earthen construction"):
        c.ignores_difficult(kind, on=me, until=_HOLDS)


# -- r69 ---------------------------------------------------------------

_inert("rt:r69-t1",
       "Arcana and Thievery checks as a minor action at a penalty. "
       "Neither check is made in a fight and neither costs an action.")


@power("rt:r69-t2", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.improvised()",))
def rt_r69_t2(c: Cast) -> None:
    """Proficiency with improvised weapons. There is no improvised weapon
    in the `weapon` table to be proficient with, so the header field has
    no ref to name."""
