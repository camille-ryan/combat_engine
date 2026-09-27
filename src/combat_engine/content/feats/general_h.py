"""General feats, eighth batch: no class gate.

The slice is mixed -- a run of multiclass feats, three exotic-weapon
chains, the "Associated Powers" family again, a fellowship family whose
bonus counts nearby allies who took the same feat, and the arcane
at-will riders. Five things decided most of the rows.

**A multiclass feat names another class's feature in prose**, and the
two that do print a ref -- `cf:swordmage-f0`, `cf:wizard-arcanist-f0` --
name a row that is not declared anywhere in the tree, so there is
nothing for `c.grant_row` to hand over either way.
`c.borrow_feature()` is the symbol the earlier waves chose and it is
what these carry.

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

**The Associated Powers rows here are all prose.** Where the spec does
print a ref -- p1061, p620, p997, p1063 -- the clause hung on it reaches
inside another row's granted attack or its miss, so even those are not
hangable. Each carries `spec.power_ref()` and whatever second symbol
its ref'd clause wanted.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.feats.exotic import _swap
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
    Cast,
    Condition,
    DamageType,
    Effect,
    Fell,
    Hit,
    Keyword,
    Melee,
    Miss,
    Ranged,
    SurgeSpent,
    Trigger,
    Usage,
    When,
    about_me,
    get,
    power,
    targets_me,
)
from combat_engine.engine.query import allies, distance_between

#: Another class's feature, named in prose or pointing at a row that is
#: not declared. The symbol the multiclass waves settled on.
BORROW = ("c.borrow_feature()",)
#: Which weapons and implements a character may pick up is settled when
#: it is built, not on a board.
PROFICIENCY = ("chargen.proficiency()",)
#: The brief prints a power by name where a ref belongs.
NAMED = ("spec.power_ref()",)

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


@_trait("f1218", todo=(*BORROW, *PROFICIENCY))
def f1218(c: Cast) -> None:
    """Skill training, another class's feature named in prose, and that
    class's implements. The training is not a fight and the other two
    are the two markers."""


@_trait("f1219", todo=BORROW)
def f1219(c: Cast) -> None:
    """Two more features of the same class, both named in prose."""


@_trait("f1220", todo=(*BORROW, *PROFICIENCY))
def f1220(c: Cast) -> None:
    """The spec prints a ref for the feature -- and `cf:swordmage-f0` is
    not declared anywhere in the tree, so the grant has nothing to hand
    over. Same hold as the prose ones, from the other side."""


@_trait("f1221", todo=BORROW)
def f1221(c: Cast) -> None:
    """`cf:wizard-arcanist-f0` is undeclared as well. Same as f1220."""


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


@_trait("f1224", dropped=PROFICIENCY)
def f1224(c: Cast) -> None:
    """"Choose a damage type" is a build choice. `c.element` is the one
    place a chassis records one, and where it has none the choice is put
    to the world's decider rather than defaulted -- a hard-coded fire
    would be inventing half the feat."""
    kind = c.element(on=c.me) or c.choose(list(_ELEMENTS), "resist 5 to what")
    if kind is not None:
        c.resist(5, kind, on=c.me, until=When.ENCOUNTER)


@power("f1225", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE,
       dropped=("c.curse_damage()", "chargen.proficiency()"))
def f1225(c: Cast) -> None:
    """The one row here that costs an action. `c.curse` is an ordinary
    relational verb -- two cursers on a board read their own -- so the
    grant itself is writable.

    Dropped: "the curse ends the first time you deal the extra damage".
    The extra damage belongs to the warlock's own feature, which a
    character taking this feat does not have, and nothing announces it.
    """
    foe = c.target
    if foe is not None:
        c.curse(on=foe)


@_trait("f1226", todo=BORROW)
def f1226(c: Cast) -> None:
    """One more feature named in prose."""


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


@_trait("f1235", todo=("c.ignore_resistance()",))
def f1235(c: Cast) -> None:
    """Attacks ignore the first 5 points of necrotic resistance.
    Resistance is subtracted inside `Health` and nothing lets an
    attacker eat into it."""


@_trait("f1292", todo=("c.ignore_resistance()",))
def f1292(c: Cast) -> None:
    """The same hold as f1235, for poison, plus "treat immunity as
    resist 20" -- which is the same subtraction from the other end. The
    skill training is not a fight."""


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


@_trait("f1259", todo=("c.on_racial_power()",))
def f1259(c: Cast) -> None:
    """Changes what action a racial power costs and when it may be used.
    The power is named in prose, and an action cost is header data the
    menu reads before anything runs."""


@_trait("f1270", todo=("c.grants_ca_to(ally)",))
def f1270(c: Cast) -> None:
    """Hands the combat advantage a Bluff check would win to an ally
    instead of taking it. Bluffing for advantage is not an action the
    engine has, so there is nothing to redirect."""


# -- the exotic weapon chains -----------------------------------------------
#
# Spiked chain, blowgun and garrote are not in the weapon table, so the
# printed Requirement is carried as `requires_text` and not as a gate --
# `assassin/level_0.py` settled that, and a gate would make every card
# here unofferable rather than merely unequipped.


@_trait("f1252", todo=(*PROFICIENCY, "Weapon.double"))
def f1252(c: Cast) -> None:
    """Proficiency with a weapon the table does not have, and then four
    sentences of weapon data about it -- two ends, two groups, two
    properties. All of it is a row in the weapon table, not a body."""


_swap("f1253", "f1253b")


@power("f1253b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=MARTIAL_WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
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


@_trait("f1277", todo=(*PROFICIENCY, "c.weapon_range()"))
def f1277(c: Cast) -> None:
    """Proficiency with a weapon the table does not have, a free-action
    reload, a longer range and the high crit property -- every clause is
    weapon data. The rogue rider is a class feature reading the same
    absent weapon."""


_swap("f1276", "f1276b")


@power("f1276b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Ranged(10, by_weapon=True), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.DEX, vs=REF),
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


@_trait("f1288", todo=PROFICIENCY)
def f1288(c: Cast) -> None:
    """Proficiency with a weapon the table does not have, and three
    clauses that all begin "when you use a garrote". Nothing is true
    without the weapon."""


_swap("f1289", "f1289b")


@power("f1289b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(Ability.STR, vs=REF),
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
       keywords=WEAPON, requires_text="must be wielding a garrote",
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
       requires_text="must be wielding a garrote, against a creature you have "
                     "combat advantage against")
def f1291b(c: Cast) -> None:
    """Two failed saving throws in sequence, which is `escalate` nested
    once: the daze replaces itself with a stun, and the stun with
    unconsciousness. The maintained-grab damage is the same sustained
    hold f1255b uses. Strength is taken for the same reason as f1289b.
    """
    victim = c.target
    if victim is None:
        return

    def worse(eff: Effect) -> None:
        c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=eff.owner)

    def stun(eff: Effect) -> None:
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


@power("f1281b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.RATTLING],
       todo=("c.use_power()",))
def f1281b(c: Cast) -> None:
    """The whole card is "use an at-will attack power on the target, and
    it deals more". Nothing runs one row from inside another, so there is
    no attack to add to."""


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
       todo=("c.use_power()",))
def f1283b(c: Cast) -> None:
    """Same shape as f1281b, one tier up."""


_swap("f1285", "f1285b")


@power("f1285b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=Melee(1),
       target=ONE_CREATURE, keywords=[Keyword.RATTLING, Keyword.WEAPON],
       trigger="you or an ally is attacked",
       on=Trigger(AttackDeclared,
                  lambda w, me, ev: ev.target == me or ev.target in allies(w, me),
                  "you or an ally is attacked"),
       todo=("c.use_power()",))
def f1285b(c: Cast) -> None:
    """The trigger is declared -- an attack on anyone on my side, which
    is what "you or an ally" is -- so the hold is only the Effect: using
    an at-will attack power from inside this row."""


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
       todo=("c.use_power()",))
def f1287b(c: Cast) -> None:
    """Same shape as f1281b, against a creature that cannot sense you."""


# -- the poison chain -------------------------------------------------------


_swap("f1293", "f1293b")


@power("f1293b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.POISON],
       todo=("c.use_power()",))
def f1293b(c: Cast) -> None:
    """Runs an at-will attack power and rewrites the type it deals. Both
    halves want a handle on the other row: the first to run it, the
    second to reach inside it."""


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
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.POISON],
       todo=("c.use_power()",))
def f1295b(c: Cast) -> None:
    """Same shape as f1293b, with two escalating saving throws on top."""


# -- the Associated Powers family -------------------------------------------
#
# Every clause in every one of these names its power in prose. Where the
# spec does resolve a ref, the clause hung on it reaches into an ally's
# granted attack, a miss, or another row's targeting -- so the ref buys
# nothing and each row names the second symbol its clause wanted too.


@_trait("f1237", todo=NAMED)
def f1237(c: Cast) -> None:
    """Four clauses, four prose names, all of them about a spiked chain
    the weapon table does not have either."""


@_trait("f1296", todo=NAMED)
def f1296(c: Cast) -> None:
    """Two clauses about staying hidden through a ranged attack."""


@_trait("f1297", todo=NAMED)
def f1297(c: Cast) -> None:
    """Four clauses, each a small rider on hitting a creature that grants
    combat advantage."""


@_trait("f1298", todo=(*NAMED, "c.on_granted_basic()"))
def f1298(c: Cast) -> None:
    """Three prose names and p1061, whose clause adds to the attack roll
    of the basic attack that row hands an ally -- a roll made inside
    another row with nothing announcing it."""


@_trait("f1299", todo=NAMED)
def f1299(c: Cast) -> None:
    """Four clauses, each turning a modifier into ongoing damage."""


@_trait("f1300", todo=(*NAMED, "c.on_miss(ref)"))
def f1300(c: Cast) -> None:
    """Two prose names, p1061 with the same granted-attack hold as f1298,
    and p997 whose clause pays out **on a miss** -- which is the other
    half of the hold, since a rider hung on `Hit` never sees one."""


@_trait("f1301", todo=NAMED)
def f1301(c: Cast) -> None:
    """Two clauses trading a printed shift for a longer move."""


@_trait("f1302", todo=NAMED)
def f1302(c: Cast) -> None:
    """Four clauses, each a defence bonus against one named creature or
    against the openings a printed movement gives."""


@_trait("f1303", todo=NAMED)
def f1303(c: Cast) -> None:
    """Three prose names and p620, whose clause widens which ally that
    row may pick -- targeting inside another row, not a rider on it."""


@_trait("f1304", todo=NAMED)
def f1304(c: Cast) -> None:
    """Four clauses, all attack penalties on a named row's target."""


@_trait("f1305", todo=NAMED)
def f1305(c: Cast) -> None:
    """Every clause is about `p2473`'s zone, which is now a ref -- but
    three of the four exploits the clauses ride on are still prose
    names, and p620's clause reaches inside that row's own targeting."""


@_trait("f1306", todo=NAMED)
def f1306(c: Cast) -> None:
    """Four clauses about the surprise round. `Condition.SURPRISED`
    exists, so the round is askable; the powers are not."""


@_trait("f1307", todo=(*NAMED, "c.on_shift_away()"))
def f1307(c: Cast) -> None:
    """Three prose names and p1063, whose clause waits for the target to
    shift after the fact -- the same hold four other rows carry."""


@_trait("f1308", todo=(*NAMED, "c.on_granted_basic()"))
def f1308(c: Cast) -> None:
    """Three prose names and p1061 again, handing combat advantage to the
    ally for the basic attack that row grants."""


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


@power("f1334b", level=1, cls="", usage=DAILY, action=FREE, reach=PERSONAL,
       target=SELF, keywords=[Keyword.ARCANE],
       todo=("c.familiar_state()",))
def f1334b(c: Cast) -> None:
    """Destroys the familiar for a damage bonus against whatever stood
    next to it. Its Requirement is the active state f740b and f741 were
    blocked on, and writing the payout alone would make a card free that
    is printed as conditional."""


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
       dropped=("c.end_effect()",))
def f1347b(c: Cast) -> None:
    """"Enemies take a -2 penalty to attack rolls made against you" is
    written as +2 to each of your defences, which is the same arithmetic
    and is the only form that reaches an enemy who walks onto the board
    after the stance is taken. A penalty laid on each enemy present
    would miss every latecomer.

    Dropped: the Special line ending the stance when you become
    bloodied. Nothing takes a live effect off its holder early. The
    light it sheds lights nothing the engine models.
    """
    c.stance(on=c.me, label=c.ref)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.STANCE)


def _is_bloodied(world, eid: int) -> bool:  # noqa: ANN001
    from combat_engine.engine.components import Health

    health = world.get(eid, Health)
    return health is not None and health.bloodied
