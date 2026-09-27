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

What the engine cannot say, and what is therefore marked:

* **A choice the page makes you record.** Thirteen elemental
  manifestations, three aspects, an at-will borrowed from another class:
  each is a build decision with no leg and no component --
  `c.race_option()`.
* **Escaping a grab** announces nothing, so a trait that pays out when
  you do cannot hear it -- `c.on_escape()`.
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
    DamageType,
    Dropped,
    Gear,
    Keyword,
    SecondWind,
    SurgeSpent,
    Trigger,
    TurnStart,
    When,
    about_me,
    power,
)
from combat_engine.engine.durations import keywords_of
from combat_engine.engine.query import flanked_by

#: A trait is armed once at the start of the fight and holds all fight.
_HOLDS = When.ENCOUNTER

#: The conditions the "defended mind" family of saves names.
_MIND = frozenset({Condition.DAZED, Condition.DOMINATED, Condition.STUNNED})
#: And the one the "elusive" family names.
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


def _option(ref: str, why: str) -> None:
    """A choice the page makes a player record, with nowhere to record it.

    An elemental manifestation, an aspect of nature, an at-will borrowed
    from another class: each picks one of a printed set, and each set
    hands out a different resistance, defence bonus and power. A build
    leg is the machinery for exactly this and a race has none.
    """

    def body(c: Cast) -> None:
        pass

    body.__name__ = ref.replace(":", "_").replace("-", "_")
    body.__doc__ = why
    power(
        ref,
        level=0, cls="", usage=AT_WILL, action=ActionType.NONE,
        reach=PERSONAL, target=SELF, todo=("c.race_option()",),
    )(body)


# -- r1 ----------------------------------------------------------------


@power("rt:r1-surge-value", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r1_surge_value(c: Cast) -> None:
    """A quarter of maximum hit points is what `query.surge_value`
    already answers; the Constitution modifier is laid on top of it.
    Untyped -- the page prints no word in front of it and does not call
    it a bonus at all."""
    c.bonus("surge_value", c.con_mod, on=c.me, until=_HOLDS)


@power("rt:r1-bloodied-attack", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r1_bloodied_attack(c: Cast) -> None:
    """Gated rather than laid when the blooding happens: a trait is armed
    once and the condition comes and goes with healing."""
    me = c.me
    c.bonus("attack", 1, kind="racial", on=me, until=_HOLDS,
            when=lambda ctx: c.bloodied(me))


# -- r2 ----------------------------------------------------------------


@power("rt:r2-poison-save", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r2_poison_save(c: Cast) -> None:
    """"Against poison" is read off the keywords of the row that laid the
    effect, which is what the save context carries."""
    c.bonus("save", 5, kind="racial", on=c.me, until=_HOLDS,
            when=_keyword(Keyword.POISON))


@power("rt:r2-hammers", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       out_of_combat=True,
       proficiency=("w:throwing-hammer", "w:warhammer"))
def rt_r2_hammers(c: Cast) -> None:
    """Which weapons a character may pick up is settled when it is built,
    so the whole benefit is the header field `chargen.proficiency` reads.
    The body has nothing to do in a fight."""


@power("rt:r2-armour-speed", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       dropped=("Gear.load",))
def rt_r2_armour_speed(c: Cast) -> None:
    """The armour penalty is a square taken off in `chargen.spawn`, so
    giving it back is a square of speed rather than a rule about armour --
    and it is laid only when there is a penalty to undo, or a dwarf in
    leather would walk 6. A heavy load is not carried anywhere."""
    gear = c.world.get(c.me, Gear)
    if gear is not None and gear.armour in ("scale", "plate"):
        c.bonus("speed", 1, on=c.me, until=_HOLDS)


@power("rt:r2-stand-your-ground", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       dropped=("query.knocked_prone()",))
def rt_r2_stand_your_ground(c: Cast) -> None:
    """One square less of any forced move is exactly `c.resist_forced`.

    The prone half is dropped: `ConditionApplied` says who applied the
    condition and not whether an *attack* did, so a save laid on every
    prone would also answer a row that puts you down as an Effect line,
    which the printed trait does not.
    """
    c.resist_forced(1, on=c.me, until=_HOLDS)


# -- r3 ----------------------------------------------------------------

_inert("rt:r3-skill-training",
       "Training in a skill of your choice. `engine/skills.py` has no "
       "training model at all -- a check is the ability modifier plus "
       "half level -- so there is nothing for the +5 to be laid on.")
_inert("rt:r3-longsword", "Proficiency, which is a build-time sentence.",
       proficiency=("w:longsword",))
_inert("rt:r3-trance",
       "Four hours of trance for six of sleep. A rest rule; no fight "
       "reaches it.")
_origin("r3", "fey")


@power("rt:r3-will", level=0, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def rt_r3_will(c: Cast) -> None:
    """Both halves are printed racial, so neither stacks with another
    racial bonus to the same thing."""
    me = c.me
    c.bonus(WILL, 1, kind="racial", on=me, until=_HOLDS)
    c.bonus("save", 5, kind="racial", on=me, until=_HOLDS,
            when=_keyword(Keyword.CHARM))


# -- r4 ----------------------------------------------------------------

_inert("rt:r4-elven-bows", "Proficiency, which is a build-time sentence.",
       proficiency=("w:longbow", "w:shortbow"))
_origin("r4", "fey")


@power("rt:r4-group-perception", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       dropped=("c.grants_in(unless=)",))
def rt_r4_group_perception(c: Cast) -> None:
    """An aura and not a snapshot: the printed line is about standing
    within 5 squares, so it has to end when an ally walks out, which is
    what `c.grants_in` says and a plain `c.bonus` cannot.

    "Non-<race> allies" is dropped -- nothing on a creature records its
    race, so the exclusion has no subject.
    """
    c.grants_in(c.aura(5, label=c.ref, until=_HOLDS),
                "skill:perception", 1, side="ally", kind="racial")


@power("rt:r4-wild-step", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.ignores_difficult(shift=)",))
def rt_r4_wild_step(c: Cast) -> None:
    """`c.ignores_difficult` is per terrain kind and board-wide, and the
    printed line is per *kind of move*. Laid blanket it would exempt a
    full run as well as a shift, which is a much larger rule."""


# -- r5 ----------------------------------------------------------------


@power("rt:r5-fear-save", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r5_fear_save(c: Cast) -> None:
    """Read off the keywords of the row that laid the effect."""
    c.bonus("save", 5, kind="racial", on=c.me, until=_HOLDS,
            when=_keyword(Keyword.FEAR))


@power("rt:r5-nimble-reaction", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r5_nimble_reaction(c: Cast) -> None:
    """The attack context carries `opportunity`, so the narrowing is a
    gate rather than a guess at which row an opportunity attack is."""
    c.bonus(AC, 2, kind="racial", on=c.me, until=_HOLDS,
            when=lambda ctx: bool(ctx.get("opportunity")))


# -- r6 ----------------------------------------------------------------

_inert("rt:r6-dual-heritage",
       "Which feats a character may take. `chargen.meets` reads one race "
       "off `Character.race`; counting as two is a second field there, "
       "not a thing that happens in a fight.")
_option("rt:r6-dilettante",
        "A 1st-level at-will from another class, used as an encounter "
        "power. The card is chosen when the character is built and "
        "nothing records the choice.")


@power("rt:r6-group-diplomacy", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r6_group_diplomacy(c: Cast) -> None:
    """An aura for the same reason the perception one is: the bonus is
    about where an ally is standing now."""
    c.grants_in(c.aura(10, label=c.ref, until=_HOLDS),
                "skill:diplomacy", 1, side="ally", kind="racial")


# -- r7 ----------------------------------------------------------------

_inert("rt:r7-bonus-feat",
       "An extra feat at 1st level. Already true: `chargen.feat_slots` "
       "deals this race one more, which is where a build-time rule "
       "belongs.")
_inert("rt:r7-bonus-skill",
       "Training in one more skill, and there is no training model.")
_option("rt:r7-bonus-at-will",
        "One extra 1st-level at-will from your own class, which is a "
        "slot `chargen.loadout` would have to deal rather than a row.")


@power("rt:r7-defences", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r7_defences(c: Cast) -> None:
    """Three separate modifiers, because a defence bonus is keyed by the
    defence it is a bonus to."""
    me = c.me
    for defence in (FORT, REF, WILL):
        c.bonus(defence, 1, kind="racial", on=me, until=_HOLDS)


# -- r8 ----------------------------------------------------------------


@power("rt:r8-bloodied-enemies", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r8_bloodied_enemies(c: Cast) -> None:
    """The attack context names its target, so "against bloodied enemies"
    is asked of the creature being swung at rather than of the swinger."""
    me = c.me
    c.bonus(
        "attack", 1, kind="racial", on=me, until=_HOLDS,
        when=lambda ctx: ctx.get("target") is not None and c.bloodied(ctx["target"]),
    )


@power("rt:r8-fire-resist", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r8_fire_resist(c: Cast) -> None:
    """Five plus half level, which is the printed formula and not a
    number to transcribe."""
    c.resist(5 + c.level // 2, DamageType.FIRE, on=c.me, until=_HOLDS)


# -- r10 ---------------------------------------------------------------


@power("rt:r10-oversized", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.oversized()",))
def rt_r10_oversized(c: Cast) -> None:
    """Wielding a weapon a size up. `Weapon` carries no size and nothing
    refuses one for being too big, so the permission has nothing to
    permit."""


# -- r14 ---------------------------------------------------------------

_origin("r14", "shapechanger")


@power("rt:r14-will", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r14_will(c: Cast) -> None:
    """A flat racial bonus to one defence."""
    c.bonus(WILL, 1, kind="racial", on=c.me, until=_HOLDS)


# -- r16 ---------------------------------------------------------------

_inert("rt:r16-trance", "A rest rule; no fight reaches it.")
_origin("r16", "fey")


# -- r17 ---------------------------------------------------------------


@power("rt:r17-willpower", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r17_willpower(c: Cast) -> None:
    """**Untyped, both halves.** The card prints no word in front of
    "bonus" here where its cousins print "racial", so these two stack
    with a racial bonus to the same thing and the others do not."""
    me = c.me
    c.bonus(WILL, 1, on=me, until=_HOLDS)
    c.bonus("save", 2, on=me, until=_HOLDS, when=_keyword(Keyword.CHARM))


# -- r18 ---------------------------------------------------------------


@power("rt:r18-defended-mind", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r18_defended_mind(c: Cast) -> None:
    """The save context carries the conditions the effect holds, so the
    three the card names are a gate."""
    c.bonus("save", 2, kind="racial", on=c.me, until=_HOLDS,
            when=_against(*_MIND))


@power("rt:r18-shifting-fortunes", level=0, cls="", usage=AT_WILL,
       action=ActionType.FREE, reach=PERSONAL, target=NO_TARGET,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def rt_r18_shifting_fortunes(c: Cast) -> None:
    """`SecondWind` is the event that exists for exactly this sentence;
    `SurgeSpent` is not a substitute, since a dozen leader rows spend a
    surge without a second wind being taken."""
    c.shift(3)


# -- r19 ---------------------------------------------------------------


@power("rt:r19-blood-fury", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r19_blood_fury(c: Cast) -> None:
    """Untyped: the card prints no word in front of "bonus". The 21st
    level step is paragon and out of scope."""
    me = c.me
    c.bonus("damage", 2, on=me, until=_HOLDS, when=lambda ctx: c.bloodied(me))


@power("rt:r19-pack-attack", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r19_pack_attack(c: Cast) -> None:
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

_inert("rt:r20-master-trickster",
       "A wizard cantrip once an encounter, and every cantrip in the "
       "tree is itself out of combat.")
_origin("r20", "fey")


@power("rt:r20-illusion-save", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r20_illusion_save(c: Cast) -> None:
    """Read off the keywords of the row that laid the effect."""
    c.bonus("save", 5, kind="racial", on=c.me, until=_HOLDS,
            when=_keyword(Keyword.ILLUSION))


@power("rt:r20-reactive-stealth", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.on_initiative()",))
def rt_r20_reactive_stealth(c: Cast) -> None:
    """`Encounter.start` rolls initiative and arms traits afterwards, so
    a trait cannot be present at the moment the check is made. Nothing
    hands a row the initiative roll."""


# -- r21 ---------------------------------------------------------------


@power("rt:r21-reflexes", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r21_reflexes(c: Cast) -> None:
    """A flat racial bonus to one defence."""
    c.bonus(REF, 1, kind="racial", on=c.me, until=_HOLDS)


# -- r22 ---------------------------------------------------------------


@power("rt:r22-phalanx", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r22_phalanx(c: Cast) -> None:
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


@power("rt:r23-trap-sense", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r23_trap_sense(c: Cast) -> None:
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


@power("rt:r24-ferocity", level=0, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL,
       target=NO_TARGET,
       trigger="you drop to 0 hit points or fewer",
       on=Trigger(Dropped, about_me, "you drop to 0 hit points or fewer"))
def rt_r24_ferocity(c: Cast) -> None:
    """An interrupt, so the swing happens while the character is still
    up. A melee basic needs somebody in reach and there may be nobody --
    a death throe with no neighbour simply does not land."""
    near = [e for e in c.enemies() if c.adjacent(e)]
    if near:
        c.basic(on=near[0])


@power("rt:r24-heedless-charge", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       dropped=("query.charging()",))
def rt_r24_heedless_charge(c: Cast) -> None:
    """The attack context's `charge` is the *attacker's* charge, and the
    printed narrowing is to opportunity attacks provoked during **your**
    charge -- which nothing records. Widened to every opportunity attack
    would be the other race's trait, so the narrowing is dropped and the
    bonus is laid on what can be asked."""
    c.bonus(AC, 2, kind="racial", on=c.me, until=_HOLDS,
            when=lambda ctx: bool(ctx.get("opportunity")))


# -- r25 ---------------------------------------------------------------


@power("rt:r25-running-charge", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r25_running_charge(c: Cast) -> None:
    """`query.speed` is handed `{"charge": True}` by the three places
    that measure a charge's run and nothing by everything else, so the
    gate is the whole of the printed narrowing."""
    c.bonus("speed", 2, on=c.me, until=_HOLDS,
            when=lambda ctx: bool(ctx.get("charge")))


# -- r26 ---------------------------------------------------------------

_origin("r26", "shadow")


@power("rt:r26-winterkin", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r26_winterkin(c: Cast) -> None:
    """A death save is labelled `death` in the save context, which is how
    "to death saving throws" is kept apart from a blanket save bonus."""
    me = c.me
    c.bonus(FORT, 1, kind="racial", on=me, until=_HOLDS)
    c.bonus("save", 2, kind="racial", on=me, until=_HOLDS,
            when=lambda ctx: ctx.get("label") == "death")
    c.bonus("save", 2, kind="racial", on=me, until=_HOLDS,
            when=_against(Condition.UNCONSCIOUS))


# -- r28 ---------------------------------------------------------------

_inert("rt:r28-living-construct",
       "No eating, drinking, breathing or sleeping. None of the four is "
       "modelled and the trait says all other effects apply normally.")
_inert("rt:r28-unsleeping-watcher", "A rest rule; no fight reaches it.")


@power("rt:r28-mind", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r28_mind(c: Cast) -> None:
    """A flat racial bonus to one defence."""
    c.bonus(WILL, 1, kind="racial", on=c.me, until=_HOLDS)


@power("rt:r28-resilience", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       dropped=("c.floor_save()",))
def rt_r28_resilience(c: Cast) -> None:
    """The save context says whether the effect carries ongoing damage.
    Taking the better of the die and 10 on a death save is a floor on the
    roll, and a save is rolled and then announced -- a listener can change
    whether it succeeded and not what the die came to."""
    c.bonus("save", 2, kind="racial", on=c.me, until=_HOLDS,
            when=lambda ctx: bool(ctx.get("ongoing")))


# -- r33 ---------------------------------------------------------------

_origin("r33", "elemental")
_option("rt:r33-manifestation",
        "Thirteen manifestations, each a different resistance, defence "
        "bonus and encounter power. One choice, recorded nowhere.")


# -- r35 ---------------------------------------------------------------

_origin("r35", "immortal")


@power("rt:r35-astral-majesty", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r35_astral_majesty(c: Cast) -> None:
    """Untyped -- the card prints no word before "bonus" -- and gated on
    the attacker, which the attack context names."""
    me = c.me

    def by_the_wounded(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return who is not None and c.bloodied(who)

    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 1, on=me, until=_HOLDS, when=by_the_wounded)


@power("rt:r35-astral-resistance", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r35_astral_resistance(c: Cast) -> None:
    """Two resistances, not one of two types: the card names both."""
    me = c.me
    amount = 5 + c.level // 2
    c.resist(amount, DamageType.NECROTIC, on=me, until=_HOLDS)
    c.resist(amount, DamageType.RADIANT, on=me, until=_HOLDS)


# -- r36 ---------------------------------------------------------------


@power("rt:r36-resilience", level=0, cls="", usage=ENCOUNTER,
       action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
       trigger="the first time you are bloodied during an encounter",
       on=Trigger(Bloodied, about_me, "you are bloodied"))
def rt_r36_resilience(c: Cast) -> None:
    """`ENCOUNTER` is what "the first time" means: the row is refused the
    second time its trigger fires. The 11th and 21st level steps are out
    of scope."""
    c.temp_hp(5, on=c.me)


@power("rt:r36-swift-charge", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r36_swift_charge(c: Cast) -> None:
    """Untyped, and gated on the one key `query.speed` is handed."""
    c.bonus("speed", 2, on=c.me, until=_HOLDS,
            when=lambda ctx: bool(ctx.get("charge")))


# -- r37 ---------------------------------------------------------------

_inert("rt:r37-powerful-athlete",
       "Roll twice on an Athletics check to jump or climb. `c.check` "
       "rolls once and nothing rerolls a skill check before it is made.")


@power("rt:r37-tenacity", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r37_tenacity(c: Cast) -> None:
    """A flat racial bonus to one defence."""
    c.bonus(WILL, 1, kind="racial", on=c.me, until=_HOLDS)


# -- r38 ---------------------------------------------------------------


@power("rt:r38-acid-resist", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r38_acid_resist(c: Cast) -> None:
    """Five plus half level, the printed formula."""
    c.resist(5 + c.level // 2, DamageType.ACID, on=c.me, until=_HOLDS)


@power("rt:r38-barbed-body", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.on_escape()",))
def rt_r38_barbed_body(c: Cast) -> None:
    """Escaping a grab announces nothing, in either direction, so the
    damage has no moment to happen in."""


# -- r41 ---------------------------------------------------------------


@power("rt:r41-swamp-walk", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r41_swamp_walk(c: Cast) -> None:
    """Said once per printed word, which is the shape `ignores_difficult`
    takes: the labels are the ones the map gives its squares."""
    me = c.me
    c.ignores_difficult("mud", on=me, until=_HOLDS)
    c.ignores_difficult("shallow water", on=me, until=_HOLDS)


@power("rt:r41-rancid-air", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       keywords=[Keyword.POISON])
def rt_r41_rancid_air(c: Cast) -> None:
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

_inert("rt:r43-mimicry", "Imitating a sound, behind a Bluff check.")


@power("rt:r43-flock-effect", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r43_flock_effect(c: Cast) -> None:
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
_option("rt:r44-aspects",
        "An aspect of nature chosen at every extended rest, each one a "
        "different power. Nothing records which is up.")


@power("rt:r44-hardy-form", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r44_hardy_form(c: Cast) -> None:
    """The card says choose, so the row asks rather than picking one for
    the character: `c.choose` puts it to whoever is playing it."""
    defence = c.choose([FORT, REF, WILL], "which defence is hardened")
    if defence is not None:
        c.bonus(defence, 1, kind="racial", on=c.me, until=_HOLDS)


# -- r46 ---------------------------------------------------------------

_inert("rt:r46-telepathy",
       "Two-way speech within 5 squares. Nothing in a fight turns on "
       "whether a creature can talk.")


@power("rt:r46-dual-soul", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
       trigger="the start of your turn",
       on=Trigger(TurnStart, about_me, "the start of your turn"))
def rt_r46_dual_soul(c: Cast) -> None:
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

_inert("rt:r47-past-life",
       "Counting as a second race for prerequisites. `Character.race` "
       "holds one ref and `chargen.meets` reads that one.")
_origin("r47", "undead", "living", dropped=("query.living()",), why=_BOTH)


@power("rt:r47-unnatural-vitality", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.dying_as()",))
def rt_r47_unnatural_vitality(c: Cast) -> None:
    """Being dazed instead of unconscious while dying. `resolve` applies
    the dying condition itself and nothing chooses what comes with it."""


# -- r49 ---------------------------------------------------------------

_inert("rt:r49-living-construct",
       "No eating, drinking, breathing or sleeping; none is modelled.")
_inert("rt:r49-telepathy", "Speech within 5 squares.")
_origin("r49", "immortal")


@power("rt:r49-crystalline-mind", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r49_crystalline_mind(c: Cast) -> None:
    """Flat 5 through heroic; the 11th and 21st level steps are out of
    scope."""
    c.resist(5, DamageType.PSYCHIC, on=c.me, until=_HOLDS)


# -- r50 ---------------------------------------------------------------

_inert("rt:r50-born-of-two-races",
       "Counting as a second race for prerequisites, which is one field "
       "on `Character` and not a rule in a fight.")
_inert("rt:r50-tireless", "A rest rule.")


# -- r51 ---------------------------------------------------------------

_inert("rt:r51-torpor", "A rest rule.")


@power("rt:r51-multiple-arms", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.stow()",))
def rt_r51_multiple_arms(c: Cast) -> None:
    """Drawing or sheathing a weapon costs nothing here because it is not
    an action the engine has: `Gear.stowed` is set when the character is
    built and nothing moves a weapon in or out of it mid-fight."""


@power("rt:r51-natural-jumper", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.running_start()",))
def rt_r51_natural_jumper(c: Cast) -> None:
    """`c.jump` takes a number of squares and knows nothing about a
    run-up, so "always considered to have a running start" has nothing to
    be true of."""


# -- r52 ---------------------------------------------------------------

_inert("rt:r52-master-of-shadows",
       "Trading a class utility for a racial one, which is a choice made "
       "when the character is built.")
_inert("rt:r52-practiced-sneak",
       "Training in Stealth, and there is no training model.")
_origin("r52", "shadow")


# -- r53 ---------------------------------------------------------------

_inert("rt:r53-human-heritage", "A Bluff bonus for passing as something.")
_inert("rt:r53-vampiric-heritage",
       "Trading a class utility for a racial one, made when the "
       "character is built.")
_origin("r53", "undead", "living", dropped=("query.living()",), why=_BOTH)


@power("rt:r53-blood-dependency", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r53_blood_dependency(c: Cast) -> None:
    """Gated rather than laid when the blooding happens, for the reason
    `rt:r1-bloodied-attack` is: a trait is armed once and bloodied comes
    and goes with healing."""
    me = c.me
    c.penalty("surge_value", 2, on=me, until=_HOLDS,
              when=lambda ctx: c.bloodied(me))


@power("rt:r53-necrotic-resist", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r53_necrotic_resist(c: Cast) -> None:
    """Five plus half level, the printed formula."""
    c.resist(5 + c.level // 2, DamageType.NECROTIC, on=c.me, until=_HOLDS)


# -- r60 ---------------------------------------------------------------

_inert("rt:r60-oaken-vitality",
       "Endurance against starvation and thirst, and meditation instead "
       "of sleep.")
_origin("r60", "fey")


@power("rt:r60-forest-walk", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r60_forest_walk(c: Cast) -> None:
    """One call per printed word, which is how the labels the map gives
    its squares are matched."""
    me = c.me
    for kind in ("trees", "underbrush", "plants", "natural growth"):
        c.ignores_difficult(kind, on=me, until=_HOLDS)


@power("rt:r60-tree-mind", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r60_tree_mind(c: Cast) -> None:
    """The three conditions the card names, read off the effect."""
    c.bonus("save", 2, kind="racial", on=c.me, until=_HOLDS,
            when=_against(*_MIND))


# -- r61 ---------------------------------------------------------------

_inert("rt:r61-speak-with-beasts", "Talking to animals.")
_inert("rt:r61-wee-warrior",
       "A reach of 1 rather than the 0 a Tiny creature normally has. "
       "Reach is not derived from size here -- every creature reaches 1 "
       "unless a weapon says otherwise -- so this is already true. The "
       "Strength-check penalty is a check no row makes.")
_origin("r61", "fey")


# -- r62 ---------------------------------------------------------------

_inert("rt:r62-pleasant-recovery",
       "Extra hit points per surge spent during a short rest; a rest is "
       "not played out.")
_inert("rt:r62-sly-words", "Bluff as a class skill; there is no skill list.")
_origin("r62", "fey")


@power("rt:r62-light-of-heart", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
       trigger="the start of your turn",
       on=Trigger(TurnStart, about_me, "the start of your turn"))
def rt_r62_light_of_heart(c: Cast) -> None:
    """The printed line is an *extra* throw at the start of the turn; the
    end-of-turn one is the ordinary save `Effects.roll_saves` already
    makes. Named by label, so the extra throw reaches the fear effect and
    nothing else standing."""
    for effect in list(c.world.effects.of(c.me)):
        if effect.when is When.SAVE_ENDS and Keyword.FEAR in keywords_of(effect.label):
            c.save(on=c.me, against=effect.label)


# -- r65 ---------------------------------------------------------------

_inert("rt:r65-animal-form",
       "A +2 to one skill, picked from a list of twelve animals. The "
       "choice is recorded nowhere and every option is a skill bonus.")
_inert("rt:r65-language-of-beasts", "Talking to animals.")
_origin("r65", "fey", "beast", "humanoid", "shapechanger",
        why="Three printed sentences and one row: the page gives a type, "
            "an origin and a subtype, and `rt:r65-origin` is the only "
            "trait ref the race has for any of them, so all four words go "
            "on together.")


@power("rt:r65-elusive", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       dropped=("c.on_escape()",))
def rt_r65_elusive(c: Cast) -> None:
    """The saving-throw half is a gate on the conditions the effect
    carries. The escape-check half is dropped: an escape attempt is not a
    skill check any row can reach."""
    c.bonus("save", 2, kind="racial", on=c.me, until=_HOLDS,
            when=_against(*_HELD))


# -- r66 ---------------------------------------------------------------

_inert("rt:r66-under-dweller",
       "Dungeoneering as a class skill; there is no skill list.")
_origin("r66", "fey")


@power("rt:r66-earth-walk", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF)
def rt_r66_earth_walk(c: Cast) -> None:
    """One call per printed word."""
    me = c.me
    for kind in ("rubble", "uneven stone", "earthen construction"):
        c.ignores_difficult(kind, on=me, until=_HOLDS)


# -- r69 ---------------------------------------------------------------

_inert("rt:r69-quick-fix",
       "Arcana and Thievery checks as a minor action at a penalty. "
       "Neither check is made in a fight and neither costs an action.")


@power("rt:r69-improvised", level=0, cls="", usage=AT_WILL,
       action=ActionType.NONE, reach=PERSONAL, target=SELF,
       todo=("c.improvised()",))
def rt_r69_improvised(c: Cast) -> None:
    """Proficiency with improvised weapons. There is no improvised weapon
    in the `weapon` table to be proficient with, so the header field has
    no ref to name."""
