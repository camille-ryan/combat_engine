"""General feats, eighth batch: no class gate.

The slice is mixed -- a run of multiclass feats, three exotic-weapon
chains, the "Associated Powers" family again, a fellowship family whose
bonus counts nearby allies who took the same feat, and the arcane
at-will riders. Five things decided most of the rows.

**A multiclass feat that names another class's feature by ref is one
`c.grant_row`.** It was not, because the refs -- `cf:swordmage-f0`,
`cf:wizard-arcanist-f0`, `cf:bard-f0`, `cf:warlock-f3` -- were not
declared anywhere in the tree and `grant_row` had nothing to hand over.
All four are declared now, and so is f1219 -- it prints its two features
by **name** rather than by ref, which read like "no ref exists" and was
not: `cf:bard-f5` and `cf:bard-f4` were both declared, and the brief's
phrasing is #340's residual. Resolved by keying the localisation index on
`(class, name)`, since 29 of the 290 feature names are shared by two or
more features and only the class tells them apart.

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

**A standing state is a window, and f1282b's marker was the claim that it
is not.** That row read "nothing announces the moment it becomes true, so
the card has no window to open in", which is true about the first half and
does not follow: a `Trigger` splits into an event class that says *when to
look* and a predicate that says *what to look for*, so a state is sayable
the moment anything that can change it is announced -- which is what
`m5854a4` and `m983a3` have done with `query.flanked_by` since they were
written. And `on=` takes a **sequence**, so a printed Trigger naming two
things gets two windows rather than a choice between them. f1282b declares
three and shares one predicate across them.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.feats.exotic import _swap
from combat_engine.content.feats.exploits import _riders
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
    ConditionEnded,
    DamageType,
    Effect,
    Fell,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    MoveEnd,
    PowerResolved,
    PowerUsed,
    Ranged,
    Relation,
    RelationSet,
    SurgeSpent,
    Trigger,
    Usage,
    When,
    World,
    about_me,
    get,
    power,
    targets_me,
)
from combat_engine.engine.durations import keywords_of
from combat_engine.engine.query import (
    allies,
    bloodied,
    distance_between,
    enemies,
    flanked_by,
    has_combat_advantage,
    since_turn_began,
)

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


@_trait("f1219")
def f1219(c: Cast) -> None:
    """Two more features of the same class, one `c.grant_row` each, exactly
    as `f1218` above does it for the third.

    **"No id in the tree answers to either" was wrong, and that was the
    whole of the marker.** Both are declared -- `cf:bard-f5` and
    `cf:bard-f4` -- and the brief printing them by name rather than by ref
    is #340's residual, not a missing row. Resolved by asking the
    localisation index for `(class, name)`: the class is the one the
    sentence itself names, which matters because **29 of the 290 feature
    names are shared by two or more features** and only the class tells
    them apart.

    `cf:bard-f5` carries its own `todo=`, so it is refused in play until
    that clears while the ref still lands in `Powers.known` -- which is
    what "you gain the class feature" reads, and the arrangement `f1220`
    below spells out.
    """
    c.grant_row("cf:bard-f5", on=c.me, until=When.ENCOUNTER)
    c.grant_row("cf:bard-f4", on=c.me, until=When.ENCOUNTER)


@_trait("f1220", proficiency=("w3610",))
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


@_trait("f1224", proficiency=("w3594", "w:staff"))
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
    a build feature that raises cf:warlock-f4 damage raises this too.
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


@_trait("f1236")
def f1236(c: Cast) -> None:
    """Adds the Intelligence modifier to the distance `p2482` teleports.

    **Not a second teleport laid beside the first**, which this row's own
    note said before the verb existed: two hops of 3 and 4 are not one hop
    of 7 the moment anything is in the way. #502.
    """
    c.extend_move("p2482", c.int_mod)


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


@_trait("f1270", todo=("actions.bluff()",))
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
        proficiency=("w3623",))
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
       dropped=("actions.granted_target",))
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


@_trait("f1277", proficiency=("w3662",))
def f1277(c: Cast) -> None:
    """Two of the three rewrites land. The proficiency always did.

    **The old note called this exactly right and is why the marker is
    precise now.** It said the clauses "are three different rewrites rather
    than one: the range (`Weapon.ranged`), the high crit property
    (`Weapon.properties`), and re-filing the weapon so a class feature and
    a group-gated power will take it (`Weapon.group`) ... a marker naming
    only the first would go quiet the day a range verb landed and two
    clauses would still be gone."

    A range verb has landed. So has the property one -- `c.gains_property`
    was promoted out of `feats.general_s` a while ago and nothing re-read
    these rows against it. `"high crit"` is a property with a live reader,
    `Cast._high_crit`, so that clause is not merely written but consulted.

The third has landed too: `c.weapon_group` re-files the
    weapon, which is the field that had no writer.

    **Two words, and only one of them can be the group.** The card names
    the powers that take a crossbow *or* a sling, so the first becomes the
    group and the second is laid as a property -- which costs nothing,
    because `query.holding` asks `what in w.properties or w.group == what`
    and answers to either. The weapon also keeps its own word, since
    `c.weapon_group` carries the old group across as a property for exactly
    this reason: measured, `holding("blowgun")` and `holding("crossbow")`
    both return it afterwards where only the first did before.

    **The "if you are a rogue" half is not enforced**, which is
    `c.as_implement`'s call on the identical sentence shape and its
    reasoning: nothing in `query` answers what class a creature is. The
    exposure is narrower than it sounds -- the clause only bites on a row
    that is group-gated in the first place -- but it is wider than print
    for a non-rogue holding a crossbow-gated power, and that is said here
    rather than left for somebody to find.

    The free-action reload is still not marked: nothing in the engine makes
    this weapon cost an action to load, so there is no cost to remove."""
    me = c.me
    c.weapon_range(ranged=(10, 20), ref="w3662", on=me)
    c.gains_property("high crit", ref="w3662", on=me)
    c.weapon_group("crossbow", ref="w3662", on=me)
    c.gains_property("sling", ref="w3662", on=me)


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


@_trait("f1288", usage=AT_WILL, proficiency=("w3663",))
def f1288(c: Cast) -> None:
    """The proficiency lands and the penalty hangs on the grab being made
    while that weapon is in hand -- `RelationSet` is the only event that
    names both ends of a grab.

    **"With two hands" is a fact about this weapon, and `c.two_handed()`
    was a marker for a question already answerable.** The old note said the
    clause "turns on the grip and not on the weapon". For `w3663` it is the
    weapon: `game.db` records it `hands = 'two-handed'`, and
    `Weapon.__post_init__` writes that word into `properties` as well --
    deliberately, so a row gets one answer whichever field it reads --
    which is the field `Weapon.two_handed` asks. So holding it *is* using
    it with both hands, and `f650b` already reads the property this way.
    It is asked rather than assumed, so the clause follows the weapon
    rather than a constant.

    **The grab is read, not sustained.** This module's own rule is that
    "each turn you maintain the grab" is a sustained effect -- and that is
    the rule for the rows that *make* the grab and pay for keeping it
    (`f1291b` lays one). This feat makes no grab and may not add a sustain
    cost to somebody else's, so what it needs is the standing record, which
    is the `GRABBED_BY` relation `c.grabbing` reads. A gate consulted at
    the moment of the swing is therefore true exactly while the grab is
    still held, which is what maintaining it comes to.

    `c.gains_advantage` rather than `c.grants_advantage`: the printed
    sentence is "**you** have combat advantage against the target you are
    grabbing", and the set it is about is whatever this character happens
    to be holding at the time, which is not knowable when the trait arms.

    One narrowing is not sayable and is **wider than print by nothing that
    can happen**: the context carries `attacker`, `target` and `power`, so
    "for the purpose of attacking again with the garrote" cannot be asked
    of the weapon. It does not need to be -- `w3663` takes both hands, so
    nothing else is in them, and every weapon attack made while the gate
    holds is made with it.

    The light-blade clause lands now. It re-files the weapon's group so
    `cf:rogue-scoundrel-f4` and the rogue's group-gated rows take it, which
    is `c.weapon_group` -- and **not** `c.counts_as(satisfies=, holding=)`,
    which waives a printed weapon *Requirement* read by `wielding`, where
    what this card buys is what `Weapon.is_light_blade` answers. That
    reader is literally `self.group == "light blade"`, so the group is the
    only field that can say it.

    The weapon keeps its own word too: `c.weapon_group` carries the old
    group across as a property, so a row asking for either answers.

    **The "if you are a rogue" half is not enforced**, for the reason
    `c.as_implement` gives on the identical sentence shape -- nothing in
    `query` answers a creature's class. `f1277` is the sibling with the
    same clause and the same caveat."""
    me = c.me
    c.weapon_group("light blade", ref="w3663", on=me)

    def garrote_in_both_hands() -> bool:
        return any(w.ref == "w3663" and w.two_handed for w in c.held(on=me))

    def seized(ev: Any) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.source != me:
            return
        if any(w.ref == "w3663" for w in c.held(on=me)):
            c.penalty("escape", 2, on=ev.target, until=When.ENCOUNTER)

    def still_holding_it(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") in c.grabbing() and garrote_in_both_hands()

    c.watch(RelationSet, seized, until=When.ENCOUNTER, on=me)
    c.gains_advantage(still_holding_it, until=When.ENCOUNTER, on=me)


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


_F1282B = "you are flanked, or your prey gains combat advantage against you"


def _f1282b_triggered(world: World, me: int) -> list[int]:
    """Which enemies have just set this card off, by the two printed routes.

    Clause one is geometry: *"you are flanked"*, which is every enemy
    `query.flanked_by` names -- plural on purpose, since a flank takes two
    and the Effect pays against *"those who triggered this power"* rather
    than against one creature.

    Clause two is narrower than clause one and not a subset of it: the prey
    gaining combat advantage **by any route**, which is
    `query.has_combat_advantage` and nothing else. Asked only of the quarry,
    because the card asks only about the quarry -- an ordinary enemy that
    has combat advantage some other way has not triggered anything, and
    reading the wider question for everybody would hand the character a
    blanket denial the card does not print.

    `Relation.QUARRY_OF` rather than `c.is_quarry`, because a Trigger
    predicate is handed `(world, me, event)` and has no `Cast` to ask --
    f1280 lays that relation and this reads the same side of it.
    """
    out: list[int] = []
    for foe in enemies(world, me):
        if flanked_by(world, me, foe) or (
            world.relations.holds(Relation.QUARRY_OF, me, foe)
            and has_combat_advantage(world, foe, me)
        ):
            out.append(foe)
    return out


def _f1282b_window(world: World, me: int, _ev: Any) -> bool:
    """The printed Trigger, asked of the board rather than of the event.

    Both printed clauses are **states**, so the predicate reads the state
    and the event only says when to look. That is why the same function
    serves all three declared windows.
    """
    return bool(_f1282b_triggered(world, me))


@power("f1282b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET, trigger=_F1282B,
       on=(Trigger(MoveEnd, _f1282b_window, _F1282B),
           Trigger(ConditionApplied, _f1282b_window, _F1282B),
           Trigger(ConditionEnded, _f1282b_window, _F1282B)))
def f1282b(c: Cast) -> None:
    """**Re-marked as written. The old note said the card had no window to
    open in and that was the wrong reading of a true observation.**

    What it got right: being flanked is standing geometry, and nothing
    emits a "you are now flanked" event. What it got wrong: a `Trigger`
    does not need one. `Trigger(event, predicate, text)` splits exactly
    this way -- the event class says *when to look* and the predicate says
    *what to look for* -- so a state becomes a window the moment something
    that can change it is announced. `m5854a4` and `m983a3` have both read
    `query.flanked_by` out of a movement event since they were written.

    **And `on=` takes a sequence**, which is the other half of why this is
    sayable: `Power.triggers` normalises one Trigger or several, so a
    printed line naming two things is two windows rather than a choice
    between them. All three here share one predicate, because both printed
    clauses are states:

    * `MoveEnd` -- somebody finished a move. The flank being established is
      this, nearly always, and so is the prey stepping somewhere it gains
      combat advantage from. Not `MoveStart` and not `Moved`: the question
      is about the square arrived in, which is the same argument `m983a3`
      records.
    * `ConditionApplied` -- the prey gaining combat advantage without
      anybody moving, which is the second clause's real content. A condition
      landing on *me* is what does it: `query.grants_ca` answers off the
      conditions standing on the creature, so prone, dazed or blinded hands
      every enemy the advantage at once and the prey is among them.
    * `ConditionEnded` -- a flanker that was furniture becoming a flanker.
      `flanked_by` requires `can_act` of **both** squares, so a stunned
      enemy in the far square is not a flank until the stun ends, and that
      moment is a move nobody made.

    The Effect is two sentences and both are narrow rather than blanket.
    `c.no_advantage(when=)` is handed the attacking pair, which is the
    printed *"to those who triggered this power"* -- the wider bare call
    would deny combat advantage to the whole board. `c.grants_advantage`
    defaults to `to="me"`, so the second sentence is one call once the prey
    is known to be in that set.

    `on=c.me` on both, because this row is `target=NO_TARGET` and a bare
    call in one of those acts on nobody at all.
    """
    me = c.me
    who = set(_f1282b_triggered(c.world, me))
    if not who:
        return
    c.no_advantage(
        on=me, until=When.EONT,
        when=lambda ctx: ctx.get("attacker") in who,
    )
    prey = next((foe for foe in sorted(who) if c.is_quarry(on=foe)), None)
    if prey is not None:
        c.grants_advantage(on=prey, until=When.EONT)


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
# **A row's second swing says which it is.** The riposte four of these
# cards ride on is rolled longhand inside its own body, so its `Hit`
# carries the same `power` as the opening attack -- and a rider hung there
# used to pay on both, which is what `c.on_riposte()` named. p653 stamps
# `as_="riposte"` on the counter now and the attack context carries the
# same key (#501), so those clauses are written.
#
# **The damage context does not carry `as_`**, which is the half of it
# that is still not askable: a damage-side gate cannot say which swing it
# is. The one clause that adds to the counter's *damage roll* is laid at
# the counter's own `Hit` instead -- see `_riposte_off_kind`.
#
# **A clause that is not about hitting does not belong on `Hit`.** f1302's
# two writable clauses are about *the target of* the exploit, hit or not,
# so that row is written by hand on `PowerUsed` -- which is announced
# before the body and carries `targets`, both of which suit it.

# `_HELD_FAST` (the four holds f1300's clauses name together) and
# `_NAMED_KINDS` (the four creature types f1298's name together) were here.
# Both had one caller left -- the p1061 clause of each feat -- and both are
# written into p1061's body now (#550), with a copy of the tuple each, for
# the reason every other migration in this file gives: a body cannot reach
# a feat module's privates.


# `_melee_half` was here -- "was this the melee half of a melee-or-ranged
# row", off `Hit.branch` and `Power.reach_of`. Its last caller was
# `_extra_in_surprise`, f1306's clause on p87, which is written into that
# row's body now (#550): a body asks its own `Cast` for the branch through
# `c.ranged`, so the event reader had nowhere left to be read from.


# `_swings` was here -- "who a finished use hit, one entry per swing,
# oldest first", walked back over `world.bus.log` to the `PowerUsed` that
# opened the use. **Both clauses its docstring named as dependents now read
# `PowerResolved.rolls` instead**: `f1304`'s and `f1102`'s clauses on p87
# are written into that row's body (#550), inside `_p87_both_swings`, and
# `#810` measured `ev.rolls` at 2 for that row whether the two swings go
# into one creature or two -- which is the per-swing ordering this reader
# existed to supply. So it lost its last caller in an earlier wave and
# `lint._unreferenced_defs` named it the moment this file was next touched.
#
# Deleted rather than kept: its own docstring argued it should stay because
# "a clause in `general_g` still depends on that ordering", and `general_g`
# holds only a comment about f1102 now. Said at this length because that
# argument is the thing a reader would otherwise restore it on.


# `_surprise_round` was here -- an enemy still holding
# `Condition.SURPRISED` *is* the surprise round, which `Encounter.start`
# lays and the round's end lifts. Both of its callers were f1306's clauses,
# on p2248 and p87, and both are written into those bodies now (#550) with
# a copy of the reader each. The encounter's own `_surprise` flag is still
# private and there is still no query for it, which is why the copies
# exist.


# -- the clauses ------------------------------------------------------------


# `_slow_if_open` and `_slide_if_open` were here -- f1297's entries on p917
# and p2248 -- and are written into those two bodies now (#550). `c.ranged`
# replaces `_melee_half` there, because a body asks its own `Cast` for the
# branch rather than reading it off an event, and `c.result.advantage`
# replaces `c.had_advantage(ev)` for the same reason. `_melee_half` is gone
# with the last of them.


# `_is_named_kind` was here -- "is this creature one of the four kinds
# f1298 names" -- and its last caller was `_ally_adds_half_int`, that
# feat's clause on p1061, which is written into p1061's body now (#550).
# The body asks `c.is_kind` over its own copy of the tuple.


# `_temp_hp_off_kind` was here, called only by f1298's entry on p2099,
# which is written into p2099's body now (#550). `_extra_off_kind` was here
# too -- f1298's entry on p87 -- and is written into p87's body now, inside
# that row's swing loop, because p87 announces one `Hit` per swing and a
# clause outside the loop would pay once where the rider paid twice.
#
# `_riposte_off_kind` was the third -- f1298's entry on p653 -- and is
# written into that row's body now, inside the riposte closure, where the
# counter *is* the branch and `as_` is no longer the discriminator.
#
# `_is_named_kind` went with them. This said it stayed because
# `_ally_adds_half_int` read it and "that entry has not migrated because
# p1061 hands out no swing for it to read" -- p1061 grants the swing now,
# so that clause moved too and nothing here is left to ask the question.


# `_ongoing_if_alone` was here, called only by f1299's entry on p992,
# which is written into p992's body now (#550). `lint.py` named it.
#
# `_beast_shifts_if_open` was here as well -- f1297's entry on p4369, and
# the only one of this file's clauses that was in the `used=` window. It is
# written into p4369's body now, **above** that row's adjacency guard,
# which is where `PowerUsed` is: announced before the body, so a use whose
# target line fails still gave the beast its step.


# `_beast_ongoing_instead` was here -- f1299's entry on p4369, in the
# `resolved=` window because the hit is the *beast's* and `clauses` gates
# on `ev.attacker == me`. It is written into p4369's body now (#550), and
# the move is what made its **"instead of" half expressible**: its note
# here said the ongoing damage lands beside the Wisdom modifier it was
# meant to replace, that nothing can take a damage bonus back the way
# `ForcedMove` takes a shove back, and that `c.pre_empt(ref, clause)` was
# the symbol owed. In the body the Wisdom term is simply left out of the
# damage expression, so no verb is owed at all.
#
# `_slow_instead_of_push` was here too -- f1297's entry on p1000, the only
# clause in this family that *replaced* a clause of the row rather than
# adding to it. Out here that needed a one-shot `Window.BEFORE` veto of the
# row's own `ForcedMove`, because by the time a `Hit` rider runs the push
# has already happened. It is written into p1000's body now, where the
# substitution is the other arm of an `if` and there is nothing to cancel.


# Three more clauses about the counter p653 arms -- `_ongoing_on_riposte`
# (f1299), `_riposte_off_kind` (f1298) and `_cow_on_riposte` (f1304) -- were
# here and are written into p653's body now (#550), inside the riposte
# closure. Each of them had to tell the counter from the opening blow by
# reading `as_` off the `Hit`, because p653 rolls both longhand and both
# carry that row's `power`; inside the closure the branch *is* the counter.
#
# `_riposte_off_kind` is the one the move simplified rather than relocated.
# Its damage half could not be gated on `as_` at all -- the damage context
# does not carry it -- so it laid a one-shot damage modifier from a second
# `Hit` watcher closed over a latch. In the body it is `c.flat` on the
# counter's own hit, and the opening blow's "one of the four kinds" is a
# local read taken before the closure is built.


# `_extra_if_held` was here -- f1300's entry on p917 -- and is written into
# p917's body now (#550). `_HELD_FAST` went with `_ally_adds_con`, this
# feat's clause on the swing p1061 hands an ally: that one has moved as
# well, so the tuple has no reader left in this file.


# `_mark_the_hit` was here -- f1304's whole `clauses` leg, on p992 -- and
# is written into p992's body now (#550).


# `_advantage_in_surprise` and `_extra_in_surprise` were here -- f1306's
# entries on p2248 and p87 -- and both are written into those bodies now
# (#550), each with its own copy of `_surprise_round`. The note here said
# the p87 half had **deliberately not** moved, because it was the card's
# last live leg out here and migrating it would leave the trait arming no
# watcher, doing nothing, and reporting silent. That is answered by
# `implemented_in=` instead, which `audit.py` buckets as ELSEWHERE and does
# not fire -- the row is not silent, it is written somewhere else.
#
# `_splash_in_cloud` and `_rattle_in_cloud` were here, f1305's two clauses
# on p992 and p2248. Both are written into those bodies now (#550, #1174),
# each with its own copy of the `_others_in_cloud` reader, so nothing out
# here reads the cloud any more and the helpers went with the clauses.


# -- the rows ---------------------------------------------------------------


@_trait("f1237", todo=("c.split_weapon()",))
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


@_trait("f1296", todo=("query.cover_gained_in_move()", "c.forgo_attack()"))
def f1296(c: Cast) -> None:
    """Both refs resolve now and neither clause turns on the hit. The
    second withdraws the second of a two-attack row to stay hidden, which no
    verb does to a row that is already swinging.

    **Re-pointed off `c.cover_from()`, which was wrong about this row and was
    the last of five hanging on it.** That note read "nothing asks what cover
    a creature has", and `query.cover_between` has been exactly that reader
    all along -- so the symbol arriving would have said nothing here. The
    other four wanted a *writer* narrowed to the attack's shape, which
    landed as `c.cover(when=)` (#644), and `i778x1` wanted attribution,
    which landed as `query.cover_granters`. One name over three unrelated
    questions.

    What is wanted is **a change, not a state**. The card pays out for
    *gaining* cover before the shot, and the state reading is the wrong rule:
    a ranger standing permanently behind a pillar would collect this every
    turn without moving, which is strictly stronger than the card.

    **And the fact is derivable, so the marker says "no reader" and not "not
    recorded".** That distinction is the whole lesson of this family --
    `query.cover_between` was the reader a sibling row said did not exist.
    `query.since_turn_began` returns the events of this creature's turn so
    far and `Moved` carries **both ends of each step**, so the square the
    move began in is on the log; `Grid.cover` from the target to that square,
    against the same from the current square, is the comparison. Nobody has
    written it, which is a reader-shaped gap and what the symbol names.

    The rest of it is already here. `c.hide` makes the check, `c.passive`
    reads the target's passive Perception, and a free action is the usual
    `ActionType.FREE`. Per #550 the clause belongs **in `p971`** gated on
    `c.feat`, not in this body.
    """


# **Every clause of this card is in the body of the row it names** (#550),
# so this is a pointer and nothing is armed. p917's, p2248's and p4369's
# moved earlier; p1000's was the last and was the only *substitution* in
# this family -- "slow the target **instead of** pushing it". Out here that
# had to be a one-shot `Window.BEFORE` veto of p1000's own `ForcedMove`,
# because a `Hit` rider runs after the push; in that body it is the other
# arm of an `if` and skips `c.instead_of` entirely, which is also what
# stops it stacking with the two registered substitutions for the same
# clause.
_riders("f1297", {}, implemented_in=("p917", "p1000", "p2248", "p4369"))

# `_ally_adds_half_int` (f1298 on p1061) and `_ally_adds_con` (f1300 on
# p1061) were here, in the `granted=` window, and both are written into
# p1061's body now (#550) -- the last two `granted=` clauses in the tree.
#
# **The move changed nothing about the reading and one thing about the
# window.** Both still lay the modifier on the *ally*, because it is read
# off whoever is rolling, and both are still one-shot and gated on this
# row's own grant. What `granted=` bought was running before the swing;
# in the body that is simply being written above `c.grant_attack`, which
# is where a modifier has to be laid for the sum to see it.


# `_ongoing_on_granted_hit` was here -- f1299's entry on p315, in the
# `landed=` table -- and is written into p315's body now (#550).
#
# **It could never have fired where it was.** `landed=` is keyed on
# `ev.granted_via` and gates on `ev.granted_by == me and ev.actor != me`,
# which is a swing the row *hands over*; p315 hands over no swing. What it
# gives an ally is a power bonus to that ally's next attack roll and damage
# roll against the target, so no event in any fight carried
# `granted_via == "p315"` and the clause paid nothing. In the body it is a
# `Hit` watcher on that ally and that target, inside the window the bonus
# itself holds for, which is what the card describes.
#
# `_cow_on_granted_hit` (f1304 on p4541) and `_cow_if_both_hit` (f1304 on
# p87) were here too, and both are in those bodies now. p4541 really does
# hand out two swings, so that one goes through
# `warlord/level_1_c._granted_hit` -- `c.grant_attack` reports that a row
# went off and not that it connected. p87's reads `PowerResolved.rolls`
# rather than walking the bus through `_swings`, which is what that
# function's own docstring points at.


# **p2099's, p87's and p653's clauses are in the bodies of those rows**
# (#550). p653's was the last to move and the migration simplified it: out
# here it fired on the *opening* blow and carried "one of the four kinds"
# forward to a counter rolled later, through a latch and a second `Hit`
# watcher, because the damage context carries no `as_` to gate on. Inside
# p653's riposte closure the fact is a local read and the damage half is
# `c.flat` on the counter's own hit.
#
# **p1061's has moved too, so this is a pointer and nothing is armed.**
# The note here said the leg had to stay because "p1061's body hands out
# nothing -- it records what would happen with `c.note` -- so a clause
# written there would be a branch that can never be true". That premise
# was false for three waves: `c.grant_attack` had always existed and takes
# the `damage_bonus=` p1061's own Effect line needs. The row grants the
# swing now, so "your ally can add half your Intelligence modifier to the
# attack roll" is a plain unbracketed `if` above that grant.
_riders("f1298", {}, implemented_in=("p87", "p653", "p1061", "p2099"))

# **Every clause of this card is in the body of the row it names** (#550),
# so this is a pointer and nothing is armed. p992's moved earlier; p653's,
# p315's and p4369's were the last three, and two of them were wrong where
# they sat. p315's `landed=` leg could never fire -- see
# `_ongoing_on_granted_hit` above -- and p4369's carried the whole "instead
# of adding your Wisdom modifier to the damage roll" half as an unwritable
# gap, because a rider cannot take a damage bonus back. In p4369's body the
# Wisdom term is left out of the damage expression, so the clause is
# faithful and owes no verb.
_riders("f1299", {}, implemented_in=("p315", "p653", "p992", "p4369"))

# p997's clause pays out **on a miss**, which a rider hung on `Hit` never
# sees -- and `_riders` has carried a `missed=` leg since the family was
# written, so the marker here was naming a verb for a window that already
# existed. The clause read `ev.target`, which `Miss` carries beside `Hit`,
# so one clause served both windows. p1061 is the granted attack.
#
# **p704's, p997's and p917's entries moved earlier and p1061's is the
# last**, so every clause of this card is in the body of the row it names
# and this is a pointer with nothing armed. The `missed=` note above went
# with p997's.
#
# The reason p1061's stayed was a false premise rather than a gap: the note
# in that body claimed granting an ally an attack was not expressible, so
# this comment read "that body hands out nothing at all, in fact". It hands
# out a real swing through `c.grant_attack`, and "your ally can add your
# Constitution modifier to the attack roll" is written above it.
#
# The withheld `implemented_in=` this comment used to argue for is now
# simply the pointer: with no live leg left there is nothing for `audit.py`
# to fire, so bucketing the row ELSEWHERE costs nothing and
# `lint._dangling_implementations` gains four hosts it can check.
_riders("f1300", {}, implemented_in=("p704", "p917", "p997", "p1061"))


@_trait("f1301")
def f1301(c: Cast) -> None:
    """Two clauses, each rewriting the movement its row prints. Both land.

    **`p919`: a move of 2 in place of its shift of 1.** Written as a
    substitution -- `p919` reads `c.instead_of("shift", ...)` at its own
    shift now -- rather than as a rider, which would have moved *and*
    shifted and given the ranger three squares where the card gives two.

    **`p971`: written, and `query.moved_this_turn()` was a dead symbol.**
    The note here read "nothing records whether a creature moved this
    turn", and the log held every `Moved` the whole time:
    `query.since_turn_began` bounds this creature's own turn off
    `world.bus.log`, which is `drivers.squares_moved`'s ruling and #645.

    **"You didn't move before the attack" is the whole turn, and that is
    where this parts company with `f1303`'s clause on the same row.** That
    card prints "chose not to move before the attack *while using this
    exploit*" -- `p971`'s own walk and nothing else -- where this one is
    unqualified, so a rogue who stepped in with a move action has moved
    before the attack and collects nothing here.

    `PowerResolved` is the printed "after the attack", and it is also the
    earliest window that can see whether `p971`'s own `c.move(2)` was
    taken: the use is announced *before* the body runs, so a `PowerUsed`
    rider would read the turn as it stood before the walk.
    """
    me = c.me
    c.pre_empt("p919", "shift", lambda using: using.move(2))

    def shift_after(ev: Any) -> None:
        if ev.actor != me or ev.power != "p971":
            return
        if any(isinstance(past, Moved) and past.actor == me
               for past in since_turn_began(c.world, me)):
            return
        # A free action costs nothing, so the printed "you can" is the only
        # gate -- `exploits._forgo_shift_instead` reads its twin the same way.
        if c.may("shift 1 square", who=me):
            c.shift(1, who=me)

    c.watch(PowerResolved, shift_after, on=me, until=When.ENCOUNTER)


@_trait("f1302")
def f1302(c: Cast) -> None:
    """Two of the four clauses are the same sentence on two rows: a
    defence bonus against *the target of* the exploit, which does not
    wait for a hit. So this row is written by hand on `PowerUsed` rather
    than through `_riders` -- the use is announced before the body and
    carries `targets`, and hanging it on `Hit` would pay out on hits
    only, which is less often than printed.

    "Against that enemy" is a `when=` on the attacker, which the defence
    query is handed. No type word is printed, so the bonus is untyped.

    **The other two clauses are written now.** `p971` prints "+Cha to
    defences against opportunity attacks provoked by **this movement**" and
    `p1505` prints the same for "opportunity attacks made against you
    **during that movement**", and the note this replaces said both were
    dropped because gating on `opportunity` alone "would also pay for the
    openings a ranged attack gives, which is more often than printed".

    `ctx["provoked_kind"]` answers it: it is `movement.step`'s own kind --
    `walk`, `shift`, `charge` -- and **empty when a row rather than a move
    opened the window**. So the move case is the non-empty one, and the
    ranged openings the old note worried about are excluded by
    construction. #880.

    Both clauses are the same gate, which is why they are one rider: the
    printed difference between them is *which* movement, and neither card
    narrows further than "the move this row is about". Hung on the same
    `PowerUsed` watch so the span matches the clause above it.
    """
    me = c.me
    guarded = {"p4541", "p2620"}
    moves = {"p971", "p1505"}

    def on_use(ev: Any) -> None:
        if ev.actor != me or c.cha_mod <= 0:
            return
        if ev.power in guarded:
            for foe in ev.targets:
                for defence in (AC, FORT, REF, WILL):
                    c.bonus(
                        defence, c.cha_mod, on=me, until=When.SONT,
                        when=lambda ctx, foe=foe: ctx.get("attacker") == foe,
                    )
        elif ev.power in moves:
            for defence in (AC, FORT, REF, WILL):
                c.bonus(
                    defence, c.cha_mod, on=me, until=When.SONT,
                    when=lambda ctx: bool(ctx.get("opportunity"))
                    and bool(ctx.get("provoked_kind")),
                )

    c.watch(PowerUsed, on_use, on=me, until=When.ENCOUNTER)


@_trait("f1303", dropped=("c.within(extend=)",))
def f1303(c: Cast) -> None:
    """All four refs resolve. p2099 goes in the place of the melee basic a
    charge swings; p971 rewrites the movement its row prints and p620 the
    pool its Special line picks from.

    **p1505 is written, and the old marker was looking at the wrong
    thing.** It named a field on the opportunity window, and no field was
    needed: the window opens *while the provoker is still in the square it
    is leaving*, so "when you leave the first square adjacent to the
    target" is adjacency asked at veto time. `c.no_provoke`'s gate is read
    inside that veto, which is also the one place a latch is safe to close
    -- nothing evaluates it speculatively the way a `c.bonus` gate is
    evaluated.

    **"If you move after using this exploit" needs nothing recorded, and
    the note here said it did.** The waiver is laid from inside the
    `PowerUsed` handler, so it does not exist until the exploit is used --
    a character who had already walked in cannot have spent it, because
    there was nothing standing to spend. The ordering is the laying time
    and not a fact about the move.

    **p971: written, and `query.moved_this_turn()` was a dead symbol** --
    `query.since_turn_began` has bounded the turn off `world.bus.log` all
    along (`drivers.squares_moved`, #645). This card's gate is the
    narrower of the two printings: "chose not to move *while using this
    exploit*" is `p971`'s own `c.move(2)` declined and not the turn's
    travel, so the span walked back here is from that row's `PowerUsed` to
    its `PowerResolved` -- the only window the row's own walk can be in.
    `f1301` prints the unqualified sentence and reads the whole turn.

    **Still dropped, and it is p620's clause, not p971's.** "The ally you
    allow to shift can be within 2 squares of you, instead of adjacent to
    you or the target" rewrites the pool `warlord/level_1._beside` builds
    out of two literal `c.within(1, ...)` calls inside `p620`'s own body,
    and no modifier reaches a literal -- `i1825x1` is the same gap on the
    same symbol. Note for whoever lands it: this card **substitutes** the
    pool rather than growing it, so a parameter that only widens a radius
    would give "within 2 of you *or* of the target", which is wider than
    printed.

    No gate on possessing p2099: `dsl.basic_options` refuses a row the
    character does not have, which is the same question asked later and
    once."""
    c.as_basic("p2099", window="charge")
    me = c.me

    def moved_after(ev: Any) -> None:
        if ev.actor != me or ev.power != "p971":
            return
        for past in reversed(c.world.bus.log[:ev.seq]):
            if isinstance(past, Moved) and past.actor == me:
                return
            if (past.kind == "PowerUsed" and past.actor == me
                    and past.power == "p971"):
                break
        c.move(2, who=me)

    def hit_and_run(ev: Any) -> None:
        if ev.actor != me or ev.power != "p1505":
            return
        foes = tuple(ev.targets)
        if not foes:
            return
        spent: list[int] = []

        def leaving(ctx: dict[str, Any]) -> bool:
            if spent or not ctx.get("move_kind"):
                return False
            if not any(c.adjacent_to(foe, me) for foe in foes):
                return False
            spent.append(1)
            return True

        c.no_provoke(on=me, until=When.EOT, when=leaving)

    c.watch(PowerUsed, hit_and_run, on=me, until=When.ENCOUNTER)
    c.watch(PowerResolved, moved_after, on=me, until=When.ENCOUNTER)


# **Every clause of this card is in the body of the row it names** (#550),
# so this is a pointer and nothing is armed. p992's moved earlier; p653's,
# p87's and p4541's were the last three, and each sat in a different window
# out here -- the riposte told apart by `as_`, both of p87's swings seen
# only by `resolved`, and p4541's granted basic attack read off `landed=`.
# In the bodies those three windows are the riposte closure,
# `PowerResolved.rolls` and `warlord/level_1_c._granted_hit`.
_riders("f1304", {}, implemented_in=("p87", "p653", "p992", "p4541"))

# All four clauses are about the zone `p2473` lays. The two splash ones
# are riders on a hit inside it and are written; p87's wants the zone to
# travel with its owner -- `c.move_zone` puts one on a named square and
# nothing ties it to a creature -- and p620's wants one named ally left
# out of a zone that is otherwise blinding everybody in it.
#
# **p992's entry has moved into p992's body** (#550), and `_others_in_cloud`
# went with it as a copy -- p2248's clause below still reads this one.
#
# **p2248's has moved now, and the fixture moved with it** (`#1174`).
# Migrating it emptied this card's last live leg, so the row is a pointer
# -- and `audit.VERDICT_ROWS` pinned `f1305` as its one example of a row
# watching `Hit` from its own body, which `implemented_in=` stops being
# true of. Measured before the swap: `audit.py --verdicts` reported 12 of
# 13 and `f1305 is credited with nothing as written`, the fixture going
# stale rather than the row going silent. `f1338` is the replacement and
# `f1339`, `f1340` and `f1342` each answer clean too.
#
# It waited for something else to touch `scripts/audit.py`, since that
# file is in `audit.WIDE` and a wide sweep is not worth one clause. This
# change is batched with that sweep.
_riders("f1305", {}, implemented_in=("p992", "p2248"),
        dropped=("c.move_zone(with_me=)", "c.zone_exempt()"))

# p2105 and p4542 both put the exploit in the place of a charge's melee
# basic attack -- but only "during the surprise round", and `c.as_basic`
# holds its swap for a stretch of time `When` cannot name. Re-aimed
# there: it is the duration that is missing, not the substitution.
#
# **p2248's and p87's entries are both in those bodies now** (#550). The
# note here said p87's had deliberately *not* moved, because it was the
# last live clause this card had out here and migrating it would leave the
# trait arming no watcher, doing nothing, and reporting silent -- and that
# `c.credit` could not cover it, since the audit board holds nobody
# carrying `Condition.SURPRISED` for the clause to pay on. The second half
# is still true and the conclusion was the wrong answer to it:
# `implemented_in=` says the clause is written elsewhere and `audit.py`
# does not fire the row at all, which is the state this card is in.
_riders("f1306", {}, implemented_in=("p87", "p2248"),
        dropped=("When.SURPRISE",))


def _poisoned(c: Cast, who: int) -> bool:
    """Is this creature suffering a poison effect?

    `c.world.effects.of` is the holds standing on a creature and an
    effect's label is the ref of the row that laid it, so `keywords_of`
    reads that row's keywords back -- which makes this a keyword question
    rather than a label one, and `c.suffering` could only ask the second.
    A burn answers by its own damage type instead: a hold ticking poison
    is a poison effect whatever the row that laid it was keyworded.
    """
    for eff in c.world.effects.of(who):
        if eff.ended:
            continue
        if Keyword.POISON in keywords_of(eff):
            return True
        burn = eff.ongoing
        if burn is not None and DamageType.POISON in (
            eff.ongoing_types or (burn[1],)
        ):
            return True
    return False


@_trait("f1307", dropped=("c.stored_dose()",))
def f1307(c: Cast) -> None:
    """Three of the four clauses still want the dose itself: two raise the
    attack roll of a secondary poison attack, which only exists once a
    dose has been applied and is not labelled when it is, and one trades a
    power's printed move for applying a poison you possess.

    **The fourth is written.** "The target suffers from a poison effect"
    is `_poisoned` above, off the holds on the creature; the shift is
    `MoveEnd.kind_`, which is the end of the move rather than the
    declaration of it. Asked at the shift and not at the hit: both halves
    of the printed sentence are about that moment, so a dose that lands
    in between still counts.
    """
    me = c.me

    def swung(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "p1063":
            return
        foe = ev.target

        def shifted(move: Any) -> None:
            if move.actor == foe and move.kind_ == "shift" and _poisoned(c, foe):
                c.grants_advantage(on=foe, to="team", until=When.SONT)

        c.watch(MoveEnd, shifted, until=When.SONT, label=f"{c.ref} watches a shift")

    c.watch(Hit, swung, until=When.ENCOUNTER, on=me, label=f"{c.ref} riders")


@_trait("f1308", dropped=("p653.riposte_hook",))
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

    **Dropped, and the marker is re-aimed.** It said p653's clause rides
    the riposte and could not be told from the opening swing -- which is
    `c.on_riposte()`, and which p653's `as_="riposte"` answers now. That
    was never this card's clause. It does not hang anything on the
    counter: it **widens what provokes one**, from the target attacking me
    to the target attacking me *or any ally adjacent to me*.

    That cannot be written from out here. p653 arms its riposte inside its
    own body, behind a private latch, and reads nothing from outside -- so
    a watcher armed here would counter in *addition* to the row's own and
    hand the character two swings where the card prints one. The widening
    belongs in p653, which is `f985`'s gap from the other side: that row
    wants the same closure to let a feat decline the counter.
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
    is out of reach -- and `query.familiar_active` is the reader built for
    exactly that, since two of the four sites asking this question are
    gates of this shape.

    It replaces a hand-walk of the companions that asked owner, kind and
    not-passive: three conditions where the card wants four. A destroyed
    familiar keeps its `Companion` row, so the gate opened for a corpse.
    #620.
    """
    from combat_engine.engine.query import familiar_active

    return familiar_active(world, eid) is not None


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
    `c.move_companion` walks it, and `c.grant_action` is the verb that
    makes an ordinary thing cost a different action -- but `actions.GRANTABLE`
    is the authority on which things, and none of its twelve words is a
    companion's move.

    **Still engine work, and the old note here described a trap that has
    since been closed.** It said `c.grant_action` "understands `shift` and
    `stand` and silently eats anything else", which was #583's fault and is
    fixed: an unrecognised word now **raises**, naming the set. So the
    marker is not "the verb would quietly do nothing" -- it is that the word
    and its reader in `engine/actions.py` have to land together, which is a
    change in that file and not in a row."""


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


@_trait("f1341")
def f1341(c: Cast) -> None:
    """"That enemy treats all squares adjacent to you as difficult terrain
    until the end of your next turn."

    **Re-pointed, not written.** `c.aura(difficult=)` works now -- the field
    was always there and `Zones.aura` simply did not pass it on -- so the
    old marker has arrived and would have made this row report ready.

    What this card needs is narrower than the aura: difficult terrain for
    **one enemy**, the one just hit, and ordinary ground for everybody else.
    The waiver is per *side* (`c.ignores_difficult_in(zone, side=)`), so
    laying the aura flat and exempting the caster's team would also make it
    difficult for every other enemy on the board -- which is wider than the
    card by the whole opposing side.

    Three theme powers print "for enemies" and are written with the pair;
    this is the one that names a creature, and `c.difficult_for(zone=)` is
    that -- the burden goes on the zone by id, so the other enemies standing
    in the same squares are on ordinary ground. #831.

    **An aura 1, because "adjacent to you" follows you.** `Zones.refresh`
    re-centres it every round, so the rough squares move with the character
    for as long as the clause is live -- which matters here, since the
    duration runs to the end of the character's *next* turn and the
    character acts inside it. A set of squares taken at the moment of the
    hit would have been right until they moved.

    The aura is laid once and stands for the encounter; what the hit does is
    add one enemy to it by name. So two hits on two enemies burden both
    independently, each on the same clock, and the aura is not re-laid.

    `_arcane_at_will` is the gate and was already in this file -- the card
    says "an arcane at-will attack power", which is a keyword and a usage."""
    me = c.me
    aura = c.aura(1, label=c.ref, on=me)

    def underfoot(hit: Hit) -> None:
        if hit.attacker != me or not _arcane_at_will(getattr(hit, "power", "")):
            return
        foe = getattr(hit, "target", None)
        if foe is None or foe not in c.enemies():
            return
        c.difficult_for(on=foe, zone=aura, until=When.EONT)

    c.watch(Hit, underfoot, until=When.ENCOUNTER, on=me, label=c.ref)


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
       )
def f1347b(c: Cast) -> None:
    """"Enemies take a -2 penalty to attack rolls made against you" is
    written as +2 to each of your defences, which is the same arithmetic
    and is the only form that reaches an enemy who walks onto the board
    after the stance is taken. A penalty laid on each enemy present
    would miss every latecomer.

    The Special line ends the stance the moment you are bloodied, and
    the four bonuses go with it -- they are separate effects clocked on
    the stance, and nothing else would come for them.

    The bright light it sheds within 6 squares is laid with the stance and
    clocked on it, so it goes out when the stance does.
    """
    holds = [c.stance(on=c.me, label=c.ref), c.light(6, on=c.me)]
    for defence in (AC, FORT, REF, WILL):
        holds.append(c.bonus(defence, 2, on=c.me, until=When.STANCE))

    def bled(ev: Bloodied) -> None:
        if ev.actor != c.me:
            return
        for hold in holds:
            c.end_effect(hold)

    holds.append(c.watch(Bloodied, bled, until=When.STANCE, on=c.me))


def _is_bloodied(world, eid: int) -> bool:  # noqa: ANN001

    return bloodied(world, eid)
