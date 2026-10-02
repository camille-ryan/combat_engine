"""General feats, eighth batch: no class gate.

The slice is mixed -- a run of multiclass feats, three exotic-weapon
chains, the "Associated Powers" family again, a fellowship family whose
bonus counts nearby allies who took the same feat, and the arcane
at-will riders. Five things decided most of the rows.

**A multiclass feat that names another class's feature by ref is one
`c.grant_row`.** It was not, because the refs -- `cf:swordmage-f0`,
`cf:wizard-arcanist-f0`, `cf:bard-f0`, `cf:warlock-f3` -- were not
declared anywhere in the tree and `grant_row` had nothing to hand over.
All four are declared now. Only f1219, which prints its two features by
name and gives no ref for either, still has nothing to point at.

**The exotic-weapon chains follow `assassin/level_0.py`, not
`exotic.py`.** Spiked chain, blowgun and garrote are not in the weapon
table, so a `requires=` gate on one is false forever and the card is
never offered. The printed Requirement is carried as `requires_text`
with no gate, which is what the assassin's garrote and blowgun at-wills
already do -- the rows then play, and the missing weapon is one
chargen gap rather than nine dead rows.

**"Each turn you maintain the grab" is a sustained effect**, not the
grab. `c.effect(until=When.SUSTAIN, sustain=...)` plus `c.on_sustain`
is the shape `p13793` uses for exactly this sentence, so the two
strangling cards pay out rather than dropping their payout clause.

**A saving throw's context carries `ongoing`, `dtype` and `keywords`.**
`durations.keywords_of` reads the last off the row that laid the effect,
so "against ongoing necrotic damage" and "against charm or fear effects"
are both sayable -- f1230, f1241, f1260 and f1328 all narrow this way.

**The Associated Powers rows here are no longer prose.** The label
matcher reads a bracketed class now, so thirteen of the fourteen cards
name their exploits by ref and eight of them have a clause that can be
hung. `exploits._riders` is the machine for that shape and they use it.
The six that stay marked are re-aimed at what the clause actually wants
-- only f1237, whose brackets carry a capitalised class, is still
waiting on a name.

A later sweep of the markers closed four more, and all four were a
docstring asserting a limit rather than a limit.

**A failed saving throw is answerable.** `Effect.escalate` is a field on
every effect, not only on one carrying a condition, and `durations.save`
runs it on any failure -- so the "First Failed Saving Throw" line on
f1295b hangs off the *modifier* that row lays. `c.penalty` takes no
`escalate=`, so it is set on the hold that comes back.

**A striker's extra damage names itself.** `extra_damage` stamps the
blow's `detail` with the label it was armed under, and any row may arm
it, so f1225 both grants `cf:warlock-f4` and answers "the first time you
deal the extra damage".

**A familiar's mode is a field.** `Companion.passive` is what
`c.familiar_mode` moves and a `requires=` gate can read, which is
f1334b's whole Requirement.

**Two markers named things that already existed** and are re-aimed:
`c.grants_ca_to(ally)` on f1270 (`c.grants_advantage(to=<eid>)` takes an
ally) and `c.on_shift_away()` on f1307 (`Moved` carries `kind_`, and
`"shift"` is one of its words).
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.feats.exotic import _swap
from combat_engine.content.feats.exploits import _hits, _riders
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    Ability,
    ActionPointSpent,
    ActionType,
    Attack,
    AttackDeclared,
    Bloodied,
    Cast,
    Condition,
    ConditionApplied,
    DamageType,
    Effect,
    Fell,
    Hit,
    Keyword,
    Melee,
    Miss,
    PowerUsed,
    Ranged,
    Relation,
    RelationSet,
    SurgeSpent,
    Trigger,
    Usage,
    When,
    Window,
    about_me,
    get,
    power,
    targets_me,
)
from combat_engine.engine.events import ForcedMove
from combat_engine.engine.grid import Square
from combat_engine.engine.query import allies, distance_between

#: The racial zone `p2473` lays, by the label it carries.
CLOUD = "p2473"

#: The class feature f1225 hands over, and the label its extra damage is
#: filed under -- `features/strikers.py:extra_damage` stamps it as the
#: `detail` of the blow, which is how "the first time you deal the extra
#: damage" is recognised from outside the feature.
CURSE = "cf:warlock-f4"

#: Another class's feature **named in prose**, with no ref in the brief
#: and nothing in the tree answering to it. What is left of the old
#: `c.borrow_feature()` group once the declared features were swept: the
#: handing-over is `c.grant_row` and the choosing is `c.borrow_row`, so
#: the only rows still stuck are the ones with nothing to point at.
NAMED_FEATURE = ("spec.feature_ref()",)
#: Which weapons and implements a character may pick up is settled when
#: it is built, not on a board.
PROFICIENCY = ("chargen.proficiency()",)

WEAPON = [Keyword.WEAPON]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.FORCE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.POISON,
    DamageType.PSYCHIC,
    DamageType.RADIANT,
    DamageType.THUNDER,
)

_DAMAGE_KEYWORDS = {k.value: k for k in DamageType}


def _trait(ref: str, *, usage: Any = ENCOUNTER, **header: Any):  # noqa: ANN202
    """The plain feat header, which is the same on nearly every row here.

    `usage` is AT_WILL on the three rows that carry a declared trigger:
    a triggered `action=NONE` row spends a use every time it fires, so
    an ENCOUNTER one answers once and is inert for the rest of the
    fight. None of the three prints a limit.
    """
    return power(ref, level=1, cls="", usage=usage, action=ActionType.NONE,
                 reach=PERSONAL, target=SELF, **header)


def _fellowship(c: Cast, base: int, cap: int = 5) -> int:
    """`base`, plus one for each ally within 10 squares holding the same
    feat, to a maximum.

    Counted once, when the trait is armed. The alternative is a `when=`
    that recounts per roll, which would be truer to the printed line and
    would also make the number move when an ally walks away mid-round --
    and these are printed as a warband's standing bond, not as a
    proximity aura.
    """
    me = c.me
    near = sum(
        1 for friend in allies(c.world, me)
        if friend != me
        and distance_between(c.world, me, friend) <= 10
        and c.feat(c.ref, on=friend)
    )
    return min(cap, base + near)


def _arcane_at_will(ref: str) -> bool:
    p = get(ref)
    return (
        p is not None
        and Keyword.ARCANE in p.keywords
        and p.usage == Usage.AT_WILL
    )


def _mod_of(c: Cast, ability: Ability | None) -> int:
    return getattr(c, f"{ability.value}_mod", 0) if ability is not None else 0


def _dtype_of(ref: str) -> DamageType:
    """The damage type a power's keywords name, if any.

    A card printing "fire" prints it as a keyword as well as rolling it,
    which is the only place a character power says its type in data --
    the number itself is worked out inside the body.
    """
    p = get(ref)
    for k in p.keywords if p is not None else ():
        found = _DAMAGE_KEYWORDS.get(getattr(k, "value", ""))
        if found is not None and found is not DamageType.UNTYPED:
            return found
    return DamageType.UNTYPED


# -- the multiclass feats ---------------------------------------------------


@_trait("f1218", proficiency=("w:wand",))
def f1218(c: Cast) -> None:
    """Skill training, another class's feature by ref, and that class's
    implements. The implements are header data `chargen` reads at build
    time and the training is not a fight, so the feature is the whole
    row -- and it is declared now, which makes it one `c.grant_row`."""
    c.grant_row("cf:bard-f0", on=c.me, until=When.ENCOUNTER)


@_trait("f1219", todo=NAMED_FEATURE)
def f1219(c: Cast) -> None:
    """Two more features of the same class, **both named in prose**. The
    grant itself is writable now -- f1218 above is the same sentence
    with a ref -- so what is left is only that the brief prints these
    two by name and no id in the tree answers to either."""


@_trait("f1220", proficiency=("w:longsword",))
def f1220(c: Cast) -> None:
    """`cf:swordmage-f0` is declared now, so the grant has something to
    hand over. That class's implement is a blade, which is why the
    proficiency is a weapon rather than one of the seven implements.

    The feature it hands over carries its own `todo`, so it is refused
    in play until that clears -- the ref still lands in `Powers.known`,
    which is what "you are considered to have the class feature" reads.
    """
    c.grant_row("cf:swordmage-f0", on=c.me, until=When.ENCOUNTER)


@_trait("f1221")
def f1221(c: Cast) -> None:
    """`cf:wizard-arcanist-f0` is declared now as well. Same as f1220,
    and this one's feature plays."""
    c.grant_row("cf:wizard-arcanist-f0", on=c.me, until=When.ENCOUNTER)


@_trait("f1222", out_of_combat=True)
def f1222(c: Cast) -> None:
    """Skill training, Ritual Casting and that class's implements. A
    ritual is not a fight and neither is a skill; which implement a
    character may hold is chargen's, and no part of this row is ever
    asked on a board."""


@_trait("f1223")
def f1223(c: Cast) -> None:
    """"Strength modifier **or** Dexterity modifier" is a standing
    choice with no downside, so it is the larger of the two. The 21st
    level step is paragon and out of scope. No type word is printed, so
    the bonus is untyped."""
    me = c.me
    mod = max(c.str_mod, c.dex_mod)
    c.bonus(
        "damage", mod, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (p := get(ctx.get("power", ""))) is not None
        and Keyword.ARCANE in p.keywords,
    )


@_trait("f1224", proficiency=("w:dagger", "w:staff"))
def f1224(c: Cast) -> None:
    """"Choose a damage type" is a build choice. `c.element` is the one
    place a chassis records one, and where it has none the choice is put
    to the world's decider rather than defaulted -- a hard-coded fire
    would be inventing half the feat."""
    kind = c.element(on=c.me) or c.choose(list(_ELEMENTS), "resist 5 to what")
    if kind is not None:
        c.resist(5, kind, on=c.me, until=When.ENCOUNTER)



def _wielding(name: str):  # noqa: ANN202
    """A `requires=` gate on holding one named weapon.

    **These rows displayed a requirement they did not apply.** `usable` returns
    `requires_text` only as the words a refusal prints; with no `requires` beside
    it the card said "you must be wielding a garrote" and the row was offered to
    anybody at all. #236.

    `query.holding` matches by ref as well as by group, which is what makes this
    one line: a garrote has no group of its own, and a short sword shares `light
    blade` with thirteen other things, so the group is not the question.
    """
    from combat_engine.engine.query import holding

    def gate(world, eid: int) -> bool:  # noqa: ANN001
        return bool(holding(world, eid, name))

    return gate


@power("f1225", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE, proficiency=("w:rod", "w:wand"))
def f1225(c: Cast) -> None:
    """The one row here that costs an action, and the whole of
    `cf:warlock-f4` once a fight: the curse, and the extra damage that
    comes with it.

    **The dropped clause is written.** It was held on the ground that the
    extra damage belongs to a feature this character has not got and that
    nothing announces it -- both halves are false now. `extra_damage` is
    an ordinary helper any row may arm, and it stamps the blow's `detail`
    with the label it was armed under, so "the first time you deal the
    extra damage" is a thing that can be recognised and answered.

    Armed here by hand rather than through `c.use_power(CURSE)`: that
    feature's own rider pays once a **round** for the rest of the fight,
    and this card's whole difference is that it pays once and then the
    curse is over. Using the row would leave its rider behind, still
    paying, after the curse this feat laid had ended.

    `c.total(f"{CURSE} damage")` is the same number the feature rolls, so
    a build feature that raises a warlock's curse damage raises this too.
    """
    foe = c.target
    if foe is None:
        return
    me = c.me
    hold = c.curse(on=foe)
    paid = False

    def on_hit(ev: Hit) -> None:
        nonlocal paid
        if paid or ev.attacker != me or ev.target != foe:
            return
        paid = True
        c.damage("1d6", c.total(f"{CURSE} damage"), on=foe, detail=CURSE)
        c.end_effect(hold)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=CURSE)


@_trait("f1226")
def f1226(c: Cast) -> None:
    """One more feature, and the spec names it by ref."""
    c.grant_row("cf:warlock-f3", on=c.me, until=When.ENCOUNTER)


# -- resistance, and saving throws against ongoing damage -------------------


@_trait("f1230")
def f1230(c: Cast) -> None:
    """The save half is narrowed on the context `durations` builds, which
    carries `ongoing` and the `dtype` of the burn -- which is exactly
    what "against ongoing necrotic damage" asks and nothing more."""
    me = c.me
    c.resist(5, DamageType.NECROTIC, on=me, until=When.ENCOUNTER)
    c.bonus(
        "save", 2, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: bool(ctx.get("ongoing"))
        and ctx.get("dtype") is DamageType.NECROTIC,
    )


@_trait("f1241")
def f1241(c: Cast) -> None:
    """The same shape as f1230, for cold."""
    me = c.me
    c.resist(5, DamageType.COLD, on=me, until=When.ENCOUNTER)
    c.bonus(
        "save", 2, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: bool(ctx.get("ongoing"))
        and ctx.get("dtype") is DamageType.COLD,
    )


@_trait("f1260")
def f1260(c: Cast) -> None:
    """Both halves of "a poison effect": the keywords of the row that laid
    the hold, and the burn's own type for an ongoing poison laid by a row
    that prints no keyword."""
    me = c.me
    c.bonus(
        "save", c.con_mod, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: Keyword.POISON in ctx.get("keywords", ())
        or ctx.get("dtype") is DamageType.POISON,
    )


@_trait("f1235")
def f1235(c: Cast) -> None:
    """The first 5 points of a target's necrotic resistance, walked
    through. Heroic tier, so 5. Laid on the caster: an ignore is the
    attacker's, not a change to the creature being hit."""
    c.ignore_resistance(5, DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER)


@_trait("f1292")
def f1292(c: Cast) -> None:
    """The same as f1235 for poison, and the immunity clause with it:
    "treat a creature immune to poison as if it had resist poison 20" is
    what `immunity=20` says, and the five ignored points then come off
    that twenty.

    "Attacks that have a poison effect" is the blow being poison, which
    the damage context carries. The Thievery training is not a fight."""
    c.ignore_resistance(
        5, DamageType.POISON, on=c.me, until=When.ENCOUNTER, immunity=20,
        when=lambda ctx: ctx.get("dtype") is DamageType.POISON,
    )


@_trait("f1236", todo=("c.extend_move()",))
def f1236(c: Cast) -> None:
    """Adds a modifier to the distance a named racial power teleports.
    The distance is an argument inside that row's own body; a second
    teleport laid beside it would be two hops, which is a different
    thing when something stands between."""


# -- the standing bonuses ---------------------------------------------------


@_trait("f1238", usage=AT_WILL, trigger="you spend an action point",
        on=Trigger(ActionPointSpent, lambda w, me, ev: ev.actor == me,
                   "you spend an action point"))
def f1238(c: Cast) -> None:
    """"All rolls you make during the granted extra action" is every key
    a roll is totalled against: attack, damage, saving throw, and
    `"skill"`, which is the one `engine/skills.py` reads for a check of
    any name -- `"check"` is not a key anything consults and laying one
    there would be a line that quietly does nothing.

    Bloodied is asked here rather than in the predicate: the point may
    be spent by a creature that was whole when the trait was armed.
    """
    me = c.me
    if not c.bloodied(on=me):
        return
    for what in ("attack", "damage", "save", "skill"):
        c.bonus(what, 2, on=me, until=When.EOT)


@_trait("f1257")
def f1257(c: Cast) -> None:
    """Asked per query rather than at arming: being bloodied arrives in
    the middle of a fight, which is the whole of this feat."""
    me = c.me
    c.bonus(
        "speed", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=me),
    )


@_trait("f1261", usage=AT_WILL, trigger="you fall",
        on=Trigger(Fell, about_me, "you fall"))
def f1261(c: Cast) -> None:
    """`Fell` is announced before the landing and carries `soften`, which
    is what `c.cushion` adds to. The printed line is a replacement --
    the whole check result instead of half -- and the engine takes
    nothing off a fall for Acrobatics on its own, so the whole result is
    what goes on."""
    c.cushion(max(0, c.check("acrobatics").total))


@_trait("f1346")
def f1346(c: Cast) -> None:
    """Two clauses and only one of them prints a type word. The swap is
    written as the arithmetic difference between the two modifiers,
    added to the +2 the card names -- one adjustment rather than two,
    because the order is moved rather than a modifier laid.

    `c.initiative`, not `c.bonus("initiative", ...)`. `Initiative.bonus`
    is summed before the d20 and `Mods` is never consulted, so the
    modifier spelling sits in the table and no roll ever reads it --
    seven rows across four files were inert that way. `c.initiative`
    moves the creature in the order after the fact, which is the only
    thing a trait can do about a roll already made.
    """
    me = c.me
    c.initiative(2 + (c.wis_mod - c.dex_mod), on=me)


@_trait("f1256", todo=("c.opportunity_instead()",))
def f1256(c: Cast) -> None:
    """Use an alchemical item in place of the melee basic an opportunity
    attack would be. Nothing substitutes for the swing an opportunity
    window is spent on, and alchemical items are not modelled."""


#: The three holds f1259 answers, in the words the card prints.
_HELD = (Condition.GRABBED, Condition.IMMOBILIZED, Condition.RESTRAINED)


@_trait("f1259", usage=AT_WILL,
        trigger="you are grabbed, immobilized or restrained",
        on=Trigger(
            ConditionApplied,
            lambda w, me, ev: ev.target == me and ev.condition in _HELD,
            "you are grabbed, immobilized or restrained",
        ))
def f1259(c: Cast) -> None:
    """`c.use_power` is the verb this waited for: the teleport is used
    here and now, at this row's action cost rather than its own.

    `ConditionApplied` names its subject `target`, so the predicate is
    written on `ev.target` and not `about_me`, which reads `ev.actor`
    and would be false forever.

    `AT_WILL` and not `ENCOUNTER`: a triggered `action=NONE` row spends
    a use every firing, and the card prints no limit of its own -- the
    limit is p1449's, which using it spends."""
    c.use_power("p1449")


@_trait("f1270", todo=("actions.bluff()", "c.pre_empt(ref, clause)"))
def f1270(c: Cast) -> None:
    """Hands the combat advantage a Bluff check would win to an ally
    instead of taking it.

    **Re-aimed off `c.grants_ca_to(ally)`**, which names a thing that
    exists: `c.grants_advantage(on=foe, to=<eid>)` takes an ally's eid
    and f2092 already wins the advantage with
    `c.check("bluff", c.passive("insight", of=foe))`. So the contest is
    sayable and so is giving the result away.

    What is missing is the action itself. Bluffing for combat advantage
    is a standard action `engine/actions.py` does not offer -- f2092 only
    gets to make the check because its own card hands it one off a
    trigger -- so this trait has no action to intercept, and "instead of
    for yourself" is the beneficiary of an action, which is the hold
    twenty-odd other rows name.
    """


# -- the exotic weapon chains -----------------------------------------------
#
# Spiked chain, blowgun and garrote are not in the weapon table, so the
# printed Requirement is carried as `requires_text` and not as a gate --
# `assassin/level_0.py` settled that, and a gate would make every card
# here unofferable rather than merely unequipped.


@_trait("f1252", todo=("Weapon.double",),
        proficiency=("w:spiked-chain",))
def f1252(c: Cast) -> None:
    """The proficiency lands: the weapon table carries this one and
    `chargen` deals it. What is left is the four sentences that make it a
    *double* weapon -- two ends, two groups, two properties -- and a
    `Weapon` has one of each."""


_swap("f1253", "f1253b")


@power("f1253b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=MARTIAL_WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
       requires=_wielding("spiked chain"),
       requires_text="must be wielding a spiked chain")
def f1253b(c: Cast) -> None:
    """The 11th and 21st steps are paragon and out of scope."""
    if c.strike():
        c.damage(c.w(), c.dex_mod)
        c.slide(2)
        c.prone()


_swap("f1254", "f1254b")


@power("f1254b", level=1, cls="", usage=DAILY, action=MINOR, reach=PERSONAL,
       target=SELF, keywords=[Keyword.MARTIAL, Keyword.STANCE, Keyword.WEAPON],
       requires=_wielding("spiked chain"),
       requires_text="must be wielding a spiked chain")
def f1254b(c: Cast) -> None:
    """"You threaten all squares within your reach" is `c.threatens`,
    which raises the ring an opportunity window is opened from. Two
    squares is a spiked chain's reach; at adjacency the sentence would
    be saying nothing, which is why the card is printed for this
    weapon."""
    c.stance(on=c.me, label=c.ref)
    c.threatens(2, on=c.me, until=When.STANCE)


_swap("f1255", "f1255b")


@power("f1255b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=MARTIAL_WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
       requires=_wielding("spiked chain"),
       requires_text="must be wielding a spiked chain",
       dropped=("c.grant_action(slide=)",))
def f1255b(c: Cast) -> None:
    """The grab lands on a hit and on a miss; only the damage differs.
    The sustained half is a named hold beside the grab rather than the
    grab itself, because only an effect carries a Sustain and its
    payout -- the same shape `p13793` uses.

    Dropped: sliding the grabbed creature as a minor action.
    `c.grant_action` understands `shift` and `stand` and silently eats
    anything else, so writing it there would look finished and do
    nothing.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(), c.dex_mod)
    else:
        c.half_damage(c.w(), c.dex_mod)
    c.grab(on=victim)
    c.penalty("escape", 2, on=victim)
    hold = c.effect(f"{c.ref} grab", until=When.SUSTAIN, on=victim,
                    sustain=MINOR)
    c.on_sustain(hold, lambda: c.damage(c.w(), on=victim))


@_trait("f1277", todo=("c.weapon_range()", "c.counts_as(property=)",
                       "c.counts_as(group=)"),
        proficiency=("w:blowgun",))
def f1277(c: Cast) -> None:
    """The proficiency lands. What is left is the clauses that rewrite
    the weapon itself, and they are three different rewrites rather than
    one: the range (`Weapon.ranged`), the high crit property
    (`Weapon.properties`), and re-filing the weapon so a class feature
    and a group-gated power will take it (`Weapon.group`). Each field is
    there and nothing edits a `Weapon` in place, so all three are named
    -- a marker naming only the first would go quiet the day a range
    verb landed and two clauses would still be gone.

    The free-action reload is not marked: nothing in the engine makes a
    blowgun cost an action to load, so there is no cost to remove."""


_swap("f1276", "f1276b")


@power("f1276b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Ranged(10, by_weapon=True), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
       requires=_wielding("blowgun"),
       requires_text="must be wielding a blowgun")
def f1276b(c: Cast) -> None:
    """The Special line -- staying hidden on a miss -- is already true:
    nothing in `resolve` gives a hidden attacker away, so there is no
    revealing for the card to undo. The tier steps are out of scope."""
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.dazed()


_swap("f1278", "f1278b")


@power("f1278b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF,
       requires=_wielding("blowgun"),
       requires_text="must be wielding a blowgun")
def f1278b(c: Cast) -> None:
    """"Your next attack" is `once=True` on both halves, so the pair is
    spent together on one swing rather than standing for the round.
    `dice=` is how a bonus carries `+1[W]` instead of a number."""
    me = c.me
    c.bonus("attack", 2, on=me, until=When.EONT, once=True)
    c.bonus("damage", 0, dice=c.w(), on=me, until=When.EONT, once=True)


_swap("f1279", "f1279b")


@power("f1279b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Ranged(10, by_weapon=True), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.DEX, vs=AC),
       requires=_wielding("blowgun"),
       requires_text="must be wielding a blowgun")
def f1279b(c: Cast) -> None:
    """The Aftereffect is `Effect.on_end`: the stun expires at the end of
    your next turn and the daze is laid as it goes. A second `c.dazed`
    written beside the stun would run at once and overlap it."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        held = c.stunned(until=When.EONT)
        if held is not None:
            held.on_end.append(
                lambda: c.dazed(until=When.SAVE_ENDS, on=victim)
            )
    else:
        c.half_damage(c.w(2), c.dex_mod)
        c.dazed(until=When.SAVE_ENDS)


@_trait("f1288", usage=AT_WILL, proficiency=("w:garrote",),
        dropped=("c.two_handed()", "c.counts_as(group=)"))
def f1288(c: Cast) -> None:
    """The proficiency lands and the penalty hangs on the grab being made
    while that weapon is in hand -- `RelationSet` is the only event that
    names both ends of a grab. The combat advantage clause turns on the
    weapon being used *with two hands*, which is a fact about the grip
    and not about the weapon; the light-blade clause re-files the weapon
    into another group for a class feature's purposes."""
    me = c.me

    def seized(ev: Any) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.source != me:
            return
        if any(w.ref == "w:garrote" for w in c.held(on=me)):
            c.penalty("escape", 2, on=ev.target, until=When.ENCOUNTER)

    c.watch(RelationSet, seized, until=When.ENCOUNTER, on=me)


_swap("f1289", "f1289b")


@power("f1289b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.STR, vs=REF),
       requires=_wielding("garrote"),
       requires_text="must be wielding a garrote, against a creature you have "
                     "combat advantage against")
def f1289b(c: Cast) -> None:
    """"Choose Strength or Dexterity when you take this power" is a build
    choice nothing records, so it is taken as Strength -- one of the two,
    which is what choosing comes to."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.dazed()
        c.grab()


_swap("f1290", "f1290b")


@power("f1290b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=NO_TARGET,
       keywords=WEAPON, requires=_wielding("garrote"),
                        requires_text="must be wielding a garrote",
       trigger="you are attacked while grabbing a creature",
       on=Trigger(AttackDeclared, targets_me, "an enemy attacks you"))
def f1290b(c: Cast) -> None:
    """"The creature you are grabbing becomes the attack's target" is
    `c.redirect`, which is what an interrupt may do to an attack it is
    answering. The grabbed creature is excluded when it is the attacker,
    which is the printed exception."""
    attacker = getattr(c.trigger, "attacker", None)
    shield = [v for v in c.grabbing() if v != attacker]
    if shield:
        c.redirect(to=shield[0])


_swap("f1291", "f1291b")


@power("f1291b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.RELIABLE, Keyword.WEAPON],
       attack=Attack(Ability.STR, vs=REF),
       requires=_wielding("garrote"),
       requires_text="must be wielding a garrote, against a creature you have "
                     "combat advantage against")
def f1291b(c: Cast) -> None:
    """Two failed saving throws in sequence, which is `escalate` nested
    once: the daze replaces itself with a stun, and the stun with
    unconsciousness. The maintained-grab damage is the same sustained
    hold f1255b uses. Strength is taken for the same reason as f1289b.

    Each step ends the one before it, which the card prints as "instead
    of". Left standing, the lighter condition is invisible while the
    heavier one is on and then outlives it -- a target that saves
    against the stun is still dazed, off a line that said it would not
    be.
    """
    victim = c.target
    if victim is None:
        return

    def worse(eff: Effect) -> None:
        c.end_effect(eff)
        c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=eff.owner)

    def stun(eff: Effect) -> None:
        c.end_effect(eff)
        c.condition(Condition.STUNNED, until=When.SAVE_ENDS, on=eff.owner,
                    escalate=worse)

    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    c.condition(Condition.DAZED, until=When.SAVE_ENDS, escalate=stun)
    c.grab(on=victim)
    hold = c.effect(f"{c.ref} grab", until=When.SUSTAIN, on=victim,
                    sustain=MINOR)
    c.on_sustain(hold, lambda: c.flat(c.str_mod, on=victim))


# -- the prey chain ---------------------------------------------------------


@power("f1280", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(20), target=ONE_CREATURE)
def f1280(c: Cast) -> None:
    """The prey is carried as the quarry relation, which is the one thing
    on the board that means "the creature this character has singled
    out" -- and it is what `c.is_quarry` asks, so the three cards below
    that target "one creature that is your prey" have something to read.
    `c.quarry` lays the relation and nothing else, so the ranger's own
    damage rider does not come with it.

    The bonuses run to the end of your next turn as printed; the prey
    itself stands for the encounter, which is the longest of the three
    printed endings. The skill training is not a fight.
    """
    foe = c.target
    if foe is None:
        return
    c.quarry(on=foe, until=When.ENCOUNTER)
    for what in ("attack", "damage"):
        c.bonus(
            what, 2, on=c.me, until=When.EONT,
            when=lambda ctx, foe=foe: ctx.get("target") == foe,
        )


_swap("f1281", "f1281b")


def _at_will_attack(c: Cast, *, melee: bool = True, ranged: bool = True) -> str:
    """One of the character's own at-will attack powers, chosen now.

    "Use a melee or ranged at-will attack power" is a choice among rows
    the character already has, and `c.borrowed_rows` filters exactly the
    way the printed line does -- an at-will, a standard action, carrying
    an attack. It takes one range at a time, so both are asked for and
    joined here; a card naming only one range passes the other as False.
    """
    options: list[str] = []
    if melee:
        options += c.borrowed_rows(c.me, melee=True)
    if ranged:
        options += c.borrowed_rows(c.me, melee=False)
    if not options:
        return ""
    return c.choose(options, "which at-will attack to use") or options[0]


@power("f1281b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.RATTLING],
       dropped=("c.damage_of(ref)",))
def f1281b(c: Cast) -> None:
    """"Use a melee or ranged at-will attack power on the target" is
    `c.use_power` over a row the character already has;
    `_at_will_attack` is the choice, and it asks for both ranges because
    the card offers both.

    The extra [W] is laid **before** the borrowed row runs and spent by
    the first damage roll, so it needs no answer to "did it hit" -- if
    the attack missed there is no roll to spend it on.

    Dropped: "+1 die of damage if it is a nonweapon attack". That die is
    the chosen row's own, and a row's damage expression cannot be read
    from outside it -- the same hold `f2408` names."""
    chosen = _at_will_attack(c)
    if not chosen:
        return
    c.bonus("damage", 0, dice=c.w(), on=c.me, until=When.EOT, once=True)
    c.use_power(chosen, on=c.target)


_swap("f1282", "f1282b")


@power("f1282b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET, todo=("c.on_flanked()",))
def f1282b(c: Cast) -> None:
    """`c.no_advantage` is the Effect and is writable. The Trigger is
    not: being flanked is a standing geometry that `query.flanked_by`
    answers when asked, and nothing announces the moment it becomes
    true, so the card has no window to open in."""


_swap("f1283", "f1283b")


@power("f1283b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.RELIABLE],
       dropped=("c.damage_of(ref)",))
def f1283b(c: Cast) -> None:
    """Same shape as f1281b, one tier up, plus a daze on a hit.

    `c.use_power` leaves the borrowed row's last attack in `c.result`,
    so `c.landed` below it is the printed "if the attack hits" -- there
    is no other way to ask, because the attack was rolled in the other
    row's own `Cast`."""
    chosen = _at_will_attack(c)
    if not chosen:
        return
    c.bonus("damage", 0, dice=c.w(2), on=c.me, until=When.EOT, once=True)
    c.use_power(chosen, on=c.target)
    if c.landed:
        c.dazed(until=When.SAVE_ENDS)


_swap("f1285", "f1285b")


@power("f1285b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=Melee(1),
       target=ONE_CREATURE, keywords=[Keyword.RATTLING, Keyword.WEAPON],
       trigger="you or an ally is attacked",
       on=Trigger(AttackDeclared,
                  lambda w, me, ev: ev.target == me or ev.target in allies(w, me),
                  "you or an ally is attacked"),
       )
def f1285b(c: Cast) -> None:
    """The trigger is declared -- an attack on anyone on my side, which
    is what "you or an ally" is -- and `c.use_power` is the Effect.

    "Target: the attacking creature" is read off `c.trigger`, not off
    `c.target`: an immediate action is aimed at whoever set it off, and
    the header's own targeting knows nothing about that."""
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is None:
        return
    chosen = _at_will_attack(c)
    if chosen:
        c.use_power(chosen, on=attacker)


_swap("f1286", "f1286b")


@power("f1286b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(20), target=ONE_CREATURE)
def f1286b(c: Cast) -> None:
    """"Ranged sight" has no `Range` kind, so it is written as 20 -- past
    anything the boards are.

    The widened critical range is narrowed to this one creature with a
    `when=`, because the attack context carries the target and a bare
    `crit_range` bonus would widen every swing of the round.
    """
    foe = c.target
    if foe is None:
        return
    c.grants_advantage(on=foe, until=When.EONT, to="me")
    c.bonus(
        "crit_range", 1, on=c.me, until=When.EONT,
        when=lambda ctx, foe=foe: ctx.get("target") == foe,
    )


_swap("f1287", "f1287b")


@power("f1287b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.RELIABLE],
       dropped=("c.damage_of(ref)",))
def f1287b(c: Cast) -> None:
    """Same shape as f1281b, against a creature that cannot sense you --
    which is `c.is_hidden(from_=...)`, the engine's only reading of "does
    not know where you are". The rider is two dice rather than one [W],
    because the card prints dice here and not weapons."""
    if not c.is_hidden(from_=c.target):
        return
    chosen = _at_will_attack(c)
    if not chosen:
        return
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.EOT, once=True)
    c.use_power(chosen, on=c.target)


# -- the poison chain -------------------------------------------------------


_swap("f1293", "f1293b")


@power("f1293b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.POISON])
def f1293b(c: Cast) -> None:
    """Runs an at-will attack power and rewrites the type it deals.

    `c.deals` is the rewrite: it is an override rather than an addition,
    which is what "change that damage type to poison" says, and it is
    held only to the end of this turn because the card changes one
    attack and not the fight. "If you deal typed damage" is the
    player's option, so it is `c.may`.

    The ongoing damage waits on `c.landed`, which `c.use_power` fills in
    from the borrowed row's own attack."""
    chosen = _at_will_attack(c)
    if not chosen:
        return
    if c.may("change the damage type to poison", who=c.me):
        c.deals(DamageType.POISON, until=When.EOT, on=c.me)
    c.use_power(chosen, on=c.target)
    if c.landed:
        c.ongoing(5, DamageType.POISON)


_swap("f1294", "f1294b")


@power("f1294b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.POISON],
       trigger="you miss with a poison attack",
       on=Trigger(Miss, lambda w, me, ev: (
           ev.attacker == me
           and (p := get(ev.power)) is not None
           and Keyword.POISON in p.keywords
       ), "you miss with a poison attack"))
def f1294b(c: Cast) -> None:
    """`Miss` carries the live `AttackResult` as a plain attribute, which
    is what `c.reroll_attack` reads -- so the reroll lands on the roll
    being answered rather than on the next one.

    The printed trigger is "the poison keyword **or** a poison effect";
    only the keyword is a thing a power declares, and a row whose poison
    is an untyped effect is the same power with the keyword left off.
    """
    c.reroll_attack()


_swap("f1295", "f1295b")


@power("f1295b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.POISON])
def f1295b(c: Cast) -> None:
    """Same shape as f1293b, and it pays out on a miss as well, which is
    why the two branches are written rather than one guarded block.

    **The two aftereffects are written.** They were dropped on the
    reading that `escalate` only grows a condition a row already applied
    -- but `Effect.escalate` is a field on every effect, not only on one
    carrying a condition, and `durations.save` runs it on any failed
    save. A modifier is an effect, so the penalty this row lays can carry
    its own worsening; `c.penalty` takes no `escalate=` keyword, so it is
    set on the hold that comes back, which is how f1279b reaches
    `on_end` two rows up.

    "Blinded **instead of** taking the penalty" is the end of the old
    effect and the start of the new one in the same breath -- unlike
    f1291b's daze-into-stun, where the card prints "instead" and the
    heavier condition swallows the lighter one anyway.

    The printed "Miss: half damage" belongs to the borrowed row's own
    damage roll and is not this row's to halve."""
    chosen = _at_will_attack(c)
    if not chosen:
        return
    if c.may("change the damage type to poison", who=c.me):
        c.deals(DamageType.POISON, until=When.EOT, on=c.me)
    c.use_power(chosen, on=c.target)

    def twice_over(eff: Effect) -> None:
        c.end_effect(eff)
        c.condition(Condition.BLINDED, Condition.WEAKENED,
                    until=When.SAVE_ENDS, on=eff.owner)

    def blinded_instead(eff: Effect) -> None:
        c.end_effect(eff)
        c.condition(Condition.BLINDED, until=When.SAVE_ENDS, on=eff.owner,
                    escalate=twice_over)

    hold = c.penalty("attack", 2, until=When.SAVE_ENDS)
    if hold is not None:
        hold.escalate = blinded_instead
    c.ongoing(10 if c.landed else 5, DamageType.POISON)


# -- the Associated Powers family -------------------------------------------
#
# One printed shape: a line of preamble, then a clause per named exploit.
# `exploits._riders` is the machine -- a trait arming one `Hit` watcher,
# the clause picked by which power fired -- and every row here with a
# hangable clause uses it. Three things decided which clauses those were.
#
# **"The melee version of this exploit" is askable.** `resolve.attack`
# sets `branch` on the `Hit` as a plain attribute and `Power.reach_of`
# says which range that half printed, so a rider on a melee-or-ranged row
# tells the two apart instead of paying out on both.
#
# **A row's second swing cannot be told from its first.** The riposte four
# of these cards ride on is rolled longhand inside its own body, so its
# `Hit` carries the same `power` as the opening attack and a rider hung
# there would pay twice. Those clauses are `c.on_riposte()`.
#
# **A clause that is not about hitting does not belong on `Hit`.** f1302's
# two writable clauses are about *the target of* the exploit, hit or not,
# so that row is written by hand on `PowerUsed` -- which is announced
# before the body and carries `targets`, both of which suit it.

#: The four holds f1300's clauses name together.
_HELD_FAST = (
    Condition.IMMOBILIZED,
    Condition.RESTRAINED,
    Condition.STUNNED,
    Condition.UNCONSCIOUS,
)

#: The four creature types every clause of f1298 names together.
_NAMED_KINDS = ("demon", "drow", "orc", "spider")


def _melee_half(ev: Any) -> bool:
    """Was this the melee half of a melee-or-ranged row?

    `resolve.attack` hangs `branch` on the `Hit` after emitting it, the
    same way it hangs `opportunity` and `charge`, so it wants a
    `getattr`. A single-range row answers off branch 0, which is its one
    range -- so this is also simply "was it a melee attack".
    """
    p = get(getattr(ev, "power", ""))
    return p is not None and p.reach_of(getattr(ev, "branch", 0)).kind == "melee"


def _surprise_round(c: Cast) -> bool:
    """`Encounter.start` lays `Condition.SURPRISED` on whoever was caught
    and lifts every one of them when the round ends, so an enemy still
    holding it *is* the surprise round. The encounter's own `_surprise`
    flag is private and there is no query for it."""
    return any(c.is_(Condition.SURPRISED, on=foe) for foe in c.enemies())


# -- the clauses ------------------------------------------------------------


def _slow_if_open(c: Cast, ev: Any) -> None:
    if _melee_half(ev) and c.had_advantage(ev):
        c.slowed(on=ev.target, until=When.EONT)


def _slide_if_open(c: Cast, ev: Any) -> None:
    if _melee_half(ev) and c.had_advantage(ev):
        c.slide(1, on=ev.target)


def _is_named_kind(c: Cast, who: int) -> bool:
    return any(c.is_kind(word, on=who) for word in _NAMED_KINDS)


def _temp_hp_off_kind(c: Cast, ev: Any) -> None:
    if c.int_mod > 0 and _is_named_kind(c, ev.target):
        c.temp_hp(c.int_mod, on=c.me)


def _extra_off_kind(c: Cast, ev: Any) -> None:
    if c.int_mod > 0 and _is_named_kind(c, ev.target):
        c.flat(c.int_mod, on=ev.target)


def _ongoing_if_alone(c: Cast, ev: Any) -> None:
    foe = ev.target
    if c.wis_mod <= 0:
        return
    if any(other != foe for other in c.within(1, of=foe, side="enemy")):
        return
    c.ongoing(c.wis_mod, on=foe)


def _beast_shifts_if_open(c: Cast, ev: Any) -> None:
    """"Your beast companion can shift 1 square before the attack."

    On the `used` window, which is what "before the attack" means: the body
    has not run, so the shift lands before the swing it is meant to set up.
    `c.beast` answers None for a character that keeps none, so the gate is
    honest rather than silently true.
    """
    from combat_engine.engine.query import has_combat_advantage

    beast = c.beast()
    if beast is None:
        return
    foes = [t for t in (ev.targets or ()) if has_combat_advantage(c.world, c.me, t)]
    if foes:
        c.shift(1, who=beast)


def _beast_ongoing_instead(c: Cast, ev: Any) -> None:
    """Ongoing damage **instead of** the Wisdom modifier on the damage roll.

    **On the `resolved` window, not `clauses`.** The hit is the *beast's* --
    `p4369` declares `by="companion"` -- and `clauses` is gated on
    `ev.attacker == me`. `resolved` fires on the character's own
    `PowerResolved`, which is where the use is announced and where `ev.rolls`
    names who was actually hit.

    **The "instead of" half cannot be expressed and is marked.** `p4369` adds
    the Wisdom modifier to its damage *inside its own body*, and there is no
    cancellable event for a damage bonus the way `ForcedMove` is cancellable
    for a shove -- so the ongoing damage lands and the modifier it was meant
    to replace cannot be taken back. That is `c.pre_empt(ref, clause)`, the
    symbol 29 rows wait on for exactly this shape.
    """
    from combat_engine.engine.query import has_combat_advantage

    beast = c.beast()
    if beast is None or c.wis_mod <= 0:
        return
    for foe in _hits(ev):
        if has_combat_advantage(c.world, beast, foe):
            c.ongoing(c.wis_mod, on=foe)


def _slow_instead_of_push(c: Cast, ev: Any) -> None:
    """"You can slow the target **instead of** pushing it."

    The hard shape in this family, and the one `c.pre_empt(ref, clause)` marks:
    the clause does not add to the row, it *replaces* a clause of the row. By
    the time a `Hit` rider runs, a push laid in the body would already have
    happened -- so this cannot be written as an effect and has to pre-empt.

    `ForcedMove` is a cancellable `Decision` carrying the `power` doing the
    shoving, and `c.watch` takes a `BEFORE` window. So the rider arms a
    one-shot that refuses this row's shove against this target and slows
    instead. Nothing new was needed in the engine.

    One-shot by a latch rather than `once=True`, for the reason p653 gives
    about its riposte: `once` would be burnt by a shove aimed at somebody
    else.
    """
    foe = ev.target
    me = c.me
    if c.choose(["slow", "push"], f"{c.ref}:instead") != "slow":
        return
    done: list[bool] = []

    def swap(shove: Any) -> None:
        if done or shove.source != me or shove.target != foe:
            return
        if getattr(shove, "power", "") != "p1000":
            return
        done.append(True)
        shove.cancel("slowed instead of pushed")
        c.slowed(on=foe, until=When.EONT)

    c.watch(ForcedMove, swap, until=When.EOT, window=Window.BEFORE, on=me,
            label=f"{c.ref} instead")


def _ongoing_on_riposte(c: Cast, ev: Any) -> None:
    """Ongoing damage, but only on the **counter** the row grants.

    p653 rolls its riposte longhand with `c.attack`, so the opening blow and
    the counter both arrive carrying that row's `power` -- which is why this
    clause had no way to ask and the feat carried `c.on_riposte()`. The swing
    now says which it is in `as_`, hung on the `Hit` the way `charge` and
    `opportunity` are.
    """
    if getattr(ev, "as_", "") != "riposte" or c.wis_mod <= 0:
        return
    c.ongoing(c.wis_mod, on=ev.target)


def _extra_if_held(c: Cast, ev: Any) -> None:
    if c.con_mod > 0 and any(c.is_(hold, on=ev.target) for hold in _HELD_FAST):
        c.flat(c.con_mod, on=ev.target)


def _mark_the_hit(c: Cast, ev: Any) -> None:
    c.mark(on=ev.target)


def _advantage_in_surprise(c: Cast, ev: Any) -> None:
    if _surprise_round(c):
        c.grants_advantage(on=ev.target, until=When.EONT, to="me")


def _extra_in_surprise(c: Cast, ev: Any) -> None:
    if not _surprise_round(c):
        return
    c.flat(c.str_mod if _melee_half(ev) else c.dex_mod, on=ev.target)


def _others_in_cloud(c: Cast, ev: Any) -> list[int]:
    """"All other enemies within the area" of the caster's own `p2473`.

    Empty unless the creature just hit is standing in it, which is the
    clause's first half. `Cast.zone` labels a zone with the ref that laid
    it when the row passes no `label=`, so that ref is the whole match.
    """
    area: frozenset[Square] = frozenset()
    for _zid, zone in c.world.zones.all():
        if zone.owner == c.me and zone.label == CLOUD:
            area = zone.squares
            break
    inside = c.in_squares(area, side="enemy") if area else []
    return [] if ev.target not in inside else [f for f in inside if f != ev.target]


def _splash_in_cloud(c: Cast, ev: Any) -> None:
    if c.str_mod > 0:
        for foe in _others_in_cloud(c, ev):
            c.flat(c.str_mod, on=foe)


def _rattle_in_cloud(c: Cast, ev: Any) -> None:
    """The rattling keyword, paid to creatures the blow never touched.

    `Cast._rattle` pays it out on damage dealt and these enemies take
    none, so the two halves of the word -- the penalty, and the hold
    `c.rattled` reads -- are laid directly.
    """
    for foe in _others_in_cloud(c, ev):
        c.penalty("attack", 2, on=foe, until=When.EONT)
        c.effect("rattled", on=foe, until=When.EONT)


# -- the rows ---------------------------------------------------------------


@_trait("f1237", todo=("c.split_weapon()", "c.instead_of()"))
def f1237(c: Cast) -> None:
    """Re-aimed: the bracketed capitalised class no longer defeats the
    label matcher and all four refs are in the spec, so the naming gap
    that held this is closed and was never the whole of it.

    Not one of the four clauses is a rider on a hit. Two of them --
    `p2104`'s and `p87`'s -- ask for one weapon to count as both hands
    at once, and `p971`'s rewrites the movement its own row prints.
    `p4541`'s is **no longer one of the holds**: the swing that row
    hands over carries `granted_via` now, so "the attack granted by this
    power" is readable. All four clauses are still about a weapon the
    table does not carry, which `exotic.py` states at length and
    deliberately does not mark."""


@_trait("f1296", todo=("c.cover_from()", "c.forgo_attack()"))
def f1296(c: Cast) -> None:
    """Both refs resolve now and neither clause turns on the hit. The
    first is a free Stealth check made *before* a ranged attack, on
    condition of having moved into an obscured space or gained cover --
    and nothing asks what cover a creature has. The second withdraws the
    second of a two-attack row to stay hidden, which no verb does to a
    row that is already swinging."""


# p1000's clause slows *instead of* the push its row prints, and the
# ranger's beast clause is the one name here the matcher still misses.
_riders("f1297", {
    "p917": _slow_if_open,
    "p2248": _slide_if_open,
    "p1000": _slow_instead_of_push,
}, used={"p4369": _beast_shifts_if_open})

def _ally_adds_half_int(c: Cast, ev: Any) -> None:
    """Half the caster's Intelligence on the granted swing's attack roll.

    Laid on the ally rather than on the warlord, because the modifier is
    read off whoever is rolling. A one-shot gated on the grant, so an
    ordinary swing the ally takes later does not spend it.
    """
    half = -(-c.int_mod // 2)  # "round up", as printed
    if half <= 0 or not any(_is_named_kind(c, foe) for foe in ev.targets):
        return
    c.bonus(
        "attack", half, on=ev.actor, until=When.EOT, once=True,
        when=lambda ctx: ctx.get("granted_by") == c.me,
    )


def _ally_adds_con(c: Cast, ev: Any) -> None:
    """The caster's Constitution on the granted swing, against a target
    that is being held still."""
    if c.con_mod <= 0:
        return
    if not any(
        any(c.is_(hold, on=foe) for hold in _HELD_FAST) for foe in ev.targets
    ):
        return
    c.bonus(
        "attack", c.con_mod, on=ev.actor, until=When.EOT, once=True,
        when=lambda ctx: ctx.get("granted_by") == c.me,
    )


def _ongoing_on_granted_hit(c: Cast, ev: Any) -> None:
    """Ongoing damage on whoever the granted swing caught."""
    if c.wis_mod > 0:
        for foe in _hits(ev):
            c.ongoing(c.wis_mod, on=foe)


def _cow_on_granted_hit(c: Cast, ev: Any) -> None:
    for foe in _hits(ev):
        c.penalty("attack", 2, on=foe, until=When.EONT)


# p1061 adds to the attack roll of the basic attack that row hands an
# ally, which is now an ordinary read; p653's clause rides the riposte,
# which shares its row's `Hit`.
_riders("f1298", {
    "p2099": _temp_hp_off_kind,
    "p87": _extra_off_kind,
}, granted={"p1061": _ally_adds_half_int},
   dropped=("c.on_riposte()",))

# p315's clause rides the swing that row hands an ally, p653 the
# riposte, and the ranger's beast clause is still a printed name.
_riders("f1299", {
    "p992": _ongoing_if_alone,
    "p653": _ongoing_on_riposte,
}, landed={"p315": _ongoing_on_granted_hit},
   resolved={"p4369": _beast_ongoing_instead},
   dropped=("c.pre_empt(ref, clause)",))

# p997's clause pays out **on a miss**, which a rider hung on `Hit` never
# sees; p1061 is the granted attack, which is readable now.
_riders("f1300", {
    "p917": _extra_if_held,
    "p704": _extra_if_held,
}, granted={"p1061": _ally_adds_con},
   dropped=("c.on_miss(ref)",))


@_trait("f1301", todo=("c.pre_empt(ref, clause)",))
def f1301(c: Cast) -> None:
    """Both refs resolve. Both clauses rewrite the movement their row
    already prints -- a shift traded for a move, and a move allowed only
    if the row's own optional move was declined -- and that choice is
    made inside the other body with nothing announcing it."""


@_trait("f1302", dropped=("c.pre_empt(ref, clause)", "query.provoked_by()"))
def f1302(c: Cast) -> None:
    """Two of the four clauses are the same sentence on two rows: a
    defence bonus against *the target of* the exploit, which does not
    wait for a hit. So this row is written by hand on `PowerUsed` rather
    than through `_riders` -- the use is announced before the body and
    carries `targets`, and hanging it on `Hit` would pay out on hits
    only, which is less often than printed.

    "Against that enemy" is a `when=` on the attacker, which the defence
    query is handed. No type word is printed, so the bonus is untyped.

    Dropped: p971's clause lengthens the move its row prints, and
    p1505's covers only the opportunity attacks *that* movement provokes
    -- gating on `opportunity` alone would also pay for the openings a
    ranged attack gives, which is more often than printed.
    """
    me = c.me
    guarded = {"p4541", "p2620"}

    def on_use(ev: Any) -> None:
        if ev.actor != me or ev.power not in guarded or c.cha_mod <= 0:
            return
        for foe in ev.targets:
            for defence in (AC, FORT, REF, WILL):
                c.bonus(
                    defence, c.cha_mod, on=me, until=When.SONT,
                    when=lambda ctx, foe=foe: ctx.get("attacker") == foe,
                )

    c.watch(PowerUsed, on_use, on=me, until=When.ENCOUNTER)


@_trait("f1303", dropped=("c.pre_empt(ref, clause)", "events.OpportunityWindow.step"))
def f1303(c: Cast) -> None:
    """All four refs resolve and none of the clauses is a rider. p2099
    goes in the place of the melee basic a charge swings; the other
    three rewrite the movement their own rows print, or widen which
    ally p620 may pick, which is that row's targeting rather than
    anything hung on it.

    No gate on possessing p2099: `dsl.basic_options` refuses a row the
    character does not have, which is the same question asked later and
    once."""
    c.as_basic("p2099", window="charge")


# p4541's clause rides the basic attack that row hands an ally -- which
# `granted_via` names now -- p653's the riposte, and p87's both of its
# two attacks landing.
_riders("f1304", {
    "p992": _mark_the_hit,
}, landed={"p4541": _cow_on_granted_hit},
   dropped=("c.on_riposte()", "c.hit_twice()"))

# All four clauses are about the zone `p2473` lays. The two splash ones
# are riders on a hit inside it and are written; p87's wants the zone to
# travel with its owner -- `c.move_zone` puts one on a named square and
# nothing ties it to a creature -- and p620's wants one named ally left
# out of a zone that is otherwise blinding everybody in it.
_riders("f1305", {
    "p992": _splash_in_cloud,
    "p2248": _rattle_in_cloud,
}, dropped=("c.move_zone(with_me=)", "c.zone_exempt()"))

# p2105 and p4542 both put the exploit in the place of a charge's melee
# basic attack -- but only "during the surprise round", and `c.as_basic`
# holds its swap for a stretch of time `When` cannot name. Re-aimed
# there: it is the duration that is missing, not the substitution.
_riders("f1306", {
    "p2248": _advantage_in_surprise,
    "p87": _extra_in_surprise,
}, dropped=("When.SURPRISE",))


@_trait("f1307", todo=("c.stored_dose()", "c.effects_on()", "c.pre_empt(ref, clause)"))
def f1307(c: Cast) -> None:
    """All four refs resolve. Re-aimed off `c.apply_poison`, which coats a
    weapon now: what these clauses want is the dose itself. Two of them
    raise the attack roll of a secondary poison attack, which only exists
    once a dose has been applied and is not labelled when it is; one
    trades a power's printed move for applying a poison you possess.

    **The fourth is re-aimed off `c.on_shift_away()`**, which names a
    thing that exists: `MoveStart`, `MoveEnd` and `Moved` all carry
    `kind_`, and `"shift"` is one of its six words, so "if it shifts
    before the start of your next turn" is an ordinary `c.watch`. The
    half that cannot be asked is the other one -- "if the target suffers
    from a poison effect" -- because `c.suffering` matches an effect's
    label, which is the ref of the row that laid it, and nothing reads
    back what effects a creature is under or what type their burn is.
    """


@_trait("f1308", dropped=("c.on_riposte()",))
def f1308(c: Cast) -> None:
    """Written by hand rather than through `_riders`: p4368's clause needs
    a memory of what happened on somebody else's turn, which a table of
    clauses has nowhere to keep.

    "During that enemy's turn" is `c.turn_of`, so an enemy's immediate
    action against me does not arm it. "During your next turn" is the
    round it was armed in or the one after, which is what "next turn"
    comes to whichever side of me the enemy acts on.

    p2620 goes in the place of the melee basic Combat Challenge allows,
    which is the window `c.as_basic` calls `"challenge"`.

    p1061's clause hands the ally combat advantage for the swing that
    row grants it, and the grant is readable now: the use carries who
    handed it over and through which row. `PowerUsed` is announced
    before the swing is rolled, which is exactly the window a one-shot
    grant of combat advantage has to be in.

    Dropped: p653's clause rides the riposte, whose `Hit` carries the
    same `power` as the opening swing.
    """
    me = c.me
    c.as_basic("p2620", window="challenge")
    #: enemy -> the round in which it hit me or my beast, on its own turn.
    stung: dict[int, int] = {}
    #: (enemy, victim) -> the round in which it hit that victim, likewise.
    struck: dict[tuple[int, int], int] = {}

    def watch_hits(ev: Hit) -> None:
        if c.turn_of() == ev.attacker and ev.attacker != ev.target:
            struck[(ev.attacker, ev.target)] = c.world.round
        mine = {me, c.beast()} - {None}
        if ev.target in mine and ev.attacker not in mine:
            if c.turn_of() == ev.attacker:
                stung[ev.attacker] = c.world.round
            return
        if ev.attacker != me or ev.power != "p4368" or c.wis_mod <= 0:
            return
        armed = stung.get(ev.target)
        if armed is not None and c.world.round <= armed + 1:
            c.flat(c.wis_mod, on=ev.target)

    def on_grant(ev: Any) -> None:
        """"On its last turn" is the same window `stung` measures: the
        round the blow landed in, or the one before this."""
        if ev.granted_by != me or ev.actor == me or ev.granted_via != "p1061":
            return
        for foe in ev.targets:
            hit_then = struck.get((foe, ev.actor))
            if hit_then is not None and c.world.round <= hit_then + 1:
                c.grants_advantage(on=foe, to=ev.actor, once=True)

    c.watch(Hit, watch_hits, on=me, until=When.ENCOUNTER)
    c.watch(PowerUsed, on_grant, on=me, until=When.ENCOUNTER)


# -- the fellowship family --------------------------------------------------
#
# One printed shape: a bonus that grows by one for each ally within 10
# squares who took the same feat, capped at +5. `c.feat` answers that
# question of another creature, so the count is real rather than assumed.


@_trait("f1325")
def f1325(c: Cast) -> None:
    c.initiative(_fellowship(c, 2), on=c.me)


@_trait("f1327")
def f1327(c: Cast) -> None:
    """Both contexts carry `opportunity`, so the same gate serves the
    attack half and the damage half -- which is unusual, and the reason
    this one of the family is writable where a "when charging" twin
    would need care."""
    me = c.me
    amount = _fellowship(c, 1)
    for what in ("attack", "damage"):
        c.bonus(
            what, amount, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: bool(ctx.get("opportunity")),
        )


@_trait("f1328")
def f1328(c: Cast) -> None:
    """Counted once like the rest of the fellowship rows, so the cap is
    reached at three nearby allies holding the feat."""
    me = c.me
    c.bonus(
        "save", _fellowship(c, 2), on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: bool(
            {Keyword.CHARM, Keyword.FEAR} & set(ctx.get("keywords", ()))
        ),
    )


@_trait("f1329", usage=AT_WILL, trigger="you spend a healing surge",
        on=Trigger(SurgeSpent, about_me, "you spend a healing surge"))
def f1329(c: Cast) -> None:
    """`SurgeSpent` is emitted from every site that decrements a surge,
    so the extra hit points land whatever spent it. The heal itself has
    already happened by then, which is right: this is "you regain N
    additional", not a replacement."""
    c.heal(_fellowship(c, 2), on=c.me)


@_trait("f1326", out_of_combat=True)
def f1326(c: Cast) -> None:
    """A Thievery bonus and nothing else."""


@_trait("f1330", out_of_combat=True)
def f1330(c: Cast) -> None:
    """An Intimidate bonus and nothing else."""


@_trait("f1331", out_of_combat=True)
def f1331(c: Cast) -> None:
    """An Athletics bonus and nothing else."""


@_trait("f1332", out_of_combat=True)
def f1332(c: Cast) -> None:
    """A Stealth bonus and nothing else."""


@_trait("f1333", out_of_combat=True)
def f1333(c: Cast) -> None:
    """A Perception bonus and nothing else."""


# -- skill feats that are only skills ---------------------------------------


@_trait("f1272", out_of_combat=True)
def f1272(c: Cast) -> None:
    """An Acrobatics bonus and a better aid-another between two
    characters who both took it. Checks, not a fight."""


@_trait("f1273", out_of_combat=True)
def f1273(c: Cast) -> None:
    """A Stealth bonus and a reroll of a Stealth check. Same."""


@_trait("f1274", out_of_combat=True)
def f1274(c: Cast) -> None:
    """A Streetwise bonus, and halving how long it takes to ask
    around."""


@_trait("f1275", out_of_combat=True)
def f1275(c: Cast) -> None:
    """An Athletics bonus and a better aid-another."""


# -- the familiar feats -----------------------------------------------------


def _familiar_is_active(world, eid: int) -> bool:  # noqa: ANN001
    """Does this creature keep a familiar, and is it on the board?

    A `requires=` gate gets `(world, eid)` and no `Cast`, so `c.familiar`
    is out of reach; the component is not. `passive` is the mode word the
    cards print, and `c.familiar_mode` is what moves it.
    """
    from combat_engine.engine.components import Companion

    return any(
        (pet := world.get(who, Companion)) is not None
        and pet.owner == eid
        and pet.kind == "familiar"
        and not pet.passive
        for who in world.having(Companion)
    )


@power("f1334b", level=1, cls="", usage=DAILY, action=FREE, reach=PERSONAL,
       target=SELF, keywords=[Keyword.ARCANE],
       requires=_familiar_is_active,
       requires_text="your familiar must be in its active state")
def f1334b(c: Cast) -> None:
    """Destroys the familiar for a damage bonus against whatever stood
    next to it.

    **The Requirement is askable.** `c.familiar_state()` named a verb
    that does not exist, but the state does: `Companion.passive` is the
    field `c.familiar_mode` moves, and a passive familiar is lifted off
    the grid entirely. So the printed "must be in its active state" is a
    `requires=` gate reading it, the same shape f1347b's "you must be
    not bloodied" uses at the foot of this file.

    Adjacency is read **before** the familiar goes, which is the printed
    "creatures that were adjacent". `side="other"` leaves the familiar
    itself out of its own circle.

    Destroyed rather than dismissed: `c.dismiss_companion` walks
    `c.companion`, which is whatever single body the caster keeps, and a
    sorcerer with both a familiar and something else would lose the
    wrong one. Coming back is a matter for the rest, not the board.
    """
    pet = c.familiar()
    if pet is None:
        return
    near = {who for who in c.within(1, of=pet, side="other") if who != c.me}
    c.world.despawn(pet)
    if not near:
        return
    c.bonus(
        "damage", 5, on=c.me, until=When.EOT, kind="power",
        when=lambda ctx: ctx.get("target") in near,
    )


@_trait("f1336", todo=("c.grant_action(familiar=)",))
def f1336(c: Cast) -> None:
    """Moves the familiar for a minor action instead of a move action.
    `c.move_companion` walks it and `c.grant_action` understands `shift`
    and `stand` and silently eats anything else, so there is nothing
    that makes moving a companion cost less."""


@_trait("f1337")
def f1337(c: Cast) -> None:
    """"All movement modes it has" is what a speed modifier already means
    -- `query.speed` is asked per mode -- so the one bonus is the whole
    clause. A character with no familiar on the board gets its own half,
    which is the printed line."""
    me = c.me
    c.bonus("speed", 1, on=me, until=When.ENCOUNTER, kind="feat")
    pet = c.familiar()
    if pet is not None:
        c.bonus("speed", 1, on=pet, until=When.ENCOUNTER, kind="feat")


# -- the arcane at-will riders ----------------------------------------------


@_trait("f1338")
def f1338(c: Cast) -> None:
    """A trait with a `c.watch`, not a declared trigger: a row holds one
    or the other, and the defence bonuses have to be laid when the hit
    lands rather than at arming.

    "Against that enemy" is a `when=` on the attacker, which the defence
    query is handed -- this is the side of the engine that is rich.
    """
    me = c.me

    def on_hit(ev: Any) -> None:
        if ev.attacker != me or not _arcane_at_will(ev.power):
            return
        foe = ev.target
        for defence in (AC, FORT, REF, WILL):
            c.bonus(
                defence, 1, on=me, until=When.SONT,
                when=lambda ctx, foe=foe: ctx.get("attacker") == foe,
            )

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@_trait("f1339")
def f1339(c: Cast) -> None:
    """"The defense the attack power targeted" is not on `Hit` -- three
    other rows carry `Hit.vs` for wanting it -- but it is header data on
    the power that fired, which is the same answer for every row whose
    attack line is single."""
    me = c.me

    def on_hit(ev: Any) -> None:
        if ev.attacker != me or not _arcane_at_will(ev.power):
            return
        p = get(ev.power)
        if p is not None and p.attack is not None:
            c.penalty(p.attack.vs, 1, on=ev.target, until=When.EONT)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@_trait("f1340")
def f1340(c: Cast) -> None:
    """"During a turn in which you hit" is the shift laid on the hit and
    expiring at the end of that turn, which is what `until=When.EOT`
    says. A stance-length grant would outlive the sentence."""
    me = c.me

    def on_hit(ev: Any) -> None:
        if ev.attacker == me and _arcane_at_will(ev.power):
            c.shift_as(MINOR, 1, on=me, until=When.EOT)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@_trait("f1341", todo=("c.aura(difficult=)",))
def f1341(c: Cast) -> None:
    """Difficult terrain around you, for one creature only and moving
    with you. `c.zone` lays terrain for everybody and stays where it is
    put; `c.aura` follows a creature and carries no terrain."""


@_trait("f1342")
def f1342(c: Cast) -> None:
    """Three things the sentence needs and where each comes from: the
    damage type is the power's own damage keyword, the amount is the
    modifier of the ability its attack line rolls, and the window is
    `c.on_attack(by=)` watching that one enemy until the start of your
    next turn.

    A power with no damage keyword deals untyped, which is what a card
    printing no type deals.
    """
    me = c.me

    def on_hit(ev: Any) -> None:
        if ev.attacker != me or not _arcane_at_will(ev.power):
            return
        foe = ev.target
        p = get(ev.power)
        amount = _mod_of(c, p.attack.ability if p and p.attack else None)
        dtype = _dtype_of(ev.power)
        if amount <= 0:
            return

        def bites(att: Any) -> None:
            if att.target == me:
                c.flat(amount, dtype=dtype, on=foe)

        c.on_attack(bites, by=foe, until=When.SONT, label=f"{c.ref} sting")

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


# -- the last pair ----------------------------------------------------------


_swap("f1347", "f1347b")


@power("f1347b", level=1, cls="", usage=DAILY, action=MINOR, reach=PERSONAL,
       target=SELF, keywords=[Keyword.STANCE],
       requires=lambda world, eid: not _is_bloodied(world, eid),
       requires_text="you must be not bloodied",
       dropped=("c.light()",))
def f1347b(c: Cast) -> None:
    """"Enemies take a -2 penalty to attack rolls made against you" is
    written as +2 to each of your defences, which is the same arithmetic
    and is the only form that reaches an enemy who walks onto the board
    after the stance is taken. A penalty laid on each enemy present
    would miss every latecomer.

    The Special line ends the stance the moment you are bloodied, and
    the four bonuses go with it -- they are separate effects clocked on
    the stance, and nothing else would come for them.

    Dropped, and re-aimed off `c.end_effect`: the light it sheds lights
    nothing the engine models.
    """
    holds = [c.stance(on=c.me, label=c.ref)]
    for defence in (AC, FORT, REF, WILL):
        holds.append(c.bonus(defence, 2, on=c.me, until=When.STANCE))

    def bled(ev: Bloodied) -> None:
        if ev.actor != c.me:
            return
        for hold in holds:
            c.end_effect(hold)

    holds.append(c.watch(Bloodied, bled, until=When.STANCE, on=c.me))


def _is_bloodied(world, eid: int) -> bool:  # noqa: ANN001
    from combat_engine.engine.components import Health

    health = world.get(eid, Health)
    return health is not None and health.bloodied
