"""General feats: the no-class slice, offset 120.

Four shapes carry the batch.

**Racial and psionic riders.** There is still no race, and it does not
matter for the benefit -- the prerequisite is a column `chargen.meets`
enforces at build time. What decides a row is whether the power it rides
on arrives as a **ref**. `p11052`, `p2482`, `p2483`, `p2484`, `p12577`,
`p1747`, `m4421a6` and `m5139a3` are refs, so a rider on one is an
ordinary `PowerUsed` trigger. Dilettante, Ferocity, Augment Energy and
the r44 racial powers are named in prose and carry the usual markers.

**The granted pair.** A feat whose printed benefit is "you gain the
fNNNb power" is a trait that hands the card over. Nine of these are
printed as a *swap* -- "you can swap one 1st-level at-will attack power
for ..." -- and giving a power up is `chargen`'s business, so those hand
the card over and drop the exchange.

**The untiered weapon and defence ladder**, f3119 through f3157. Each
prints "+1 feat bonus to weapon attack rolls you make with an X", and
whether it can be written at all comes down to whether X is one of this
engine's ten weapon groups. Axe, bow, crossbow, heavy blade, implement,
light blade, mace, spear, staff and unarmed are; hammer, orb, sling and
wand are not, and a gate on `group == "orb"` is false in every fight
rather than wrong in an interesting way. Those four carry a marker
naming the group, the way `general_f.f69` does for the hammer.

**Second wind.** Five rows here ride on it and it is an action rather
than a power, so it announces nothing but the surge it spends. That is
the single commonest gap in the batch.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionPointSpent,
    ActionType,
    Attack,
    AttackRolled,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    DamageRolled,
    DamageType,
    ForcedMove,
    Gear,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Miss,
    Moved,
    PowerResolved,
    PowerUsed,
    Ranged,
    SavingThrow,
    SecondWind,
    SkillCheck,
    SurgeSpent,
    Swap,
    Trigger,
    TurnEnd,
    TurnStart,
    Usage,
    When,
    about_me,
    get,
    power,
)
from combat_engine.engine.durations import keywords_of
from combat_engine.engine.grid import neighbours, spread
from combat_engine.engine.query import (
    allies,
    distance_between,
    flankers,
    has_combat_advantage,
    team,
)

#: "You can swap one N-level power you know for this one." The card is
#: handed over; giving a power *up* is a build-time exchange.
SWAP = ("chargen.power_swap()",)
#: Which weapons a character may pick up is settled when it is built.
PROFICIENCY = ("chargen.proficiency()",)
#: A class feature named in prose with no ref behind it.
FEATURE = ("c.class_feature()",)
#: A racial power or trait the benefit names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: The three racial powers of `r44`, which the page offers as a choice.
R44 = ("p7441", "p7442", "p7443")
#: An augmentable clause: spending power points to change what a named
#: power does is the power's own business and there is no door in.
#: **Re-aimed.** `dsl.use(augment=)` arrived: a row declares its augments
#: in its own header and the spend is settled before targeting. None of
#: these four is that. Each hangs an augment clause on a *racial* power
#: from outside that power's card -- "your pNNNN gains the augmentable
#: keyword, and you can spend 1 power point to ..." -- and nothing adds an
#: offer to another row's augment. Same symbol the five psionic aspect
#: dailies in `docs/blocked.json` already name, so they group.
AUGMENT = ("c.lend_augment(ref, clause)",)
MELEE_REACH = ("melee", "close_burst", "close_blast")
ALL_DEFENCES = (AC, FORT, REF, WILL)
FORCED = ("push", "pull", "slide")


def _best(c: Cast) -> int:
    """"Your highest ability modifier". The header names one ability, so
    the roll carries the difference as `plus=`."""
    return max(c.str_mod, c.con_mod, c.dex_mod, c.int_mod, c.wis_mod, c.cha_mod)


def _used_any(*refs: str):  # noqa: ANN202
    """"A <race> racial power", where the race prints more than one."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power in refs

    return when


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _group(c: Cast, *groups: str) -> bool:
    """Is the caster holding a weapon of one of those groups?"""
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.group in groups for w in gear.held)


def _keyworded(ctx: dict[str, Any], *words: Keyword) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and all(k in p.keywords for k in words)


def _near_allies(c: Cast, radius: int) -> list[int]:
    me = c.me
    return [
        a for a in allies(c.world, me)
        if a != me and distance_between(c.world, me, a) <= radius
    ]


def _granted(ref: str, card: str, **kw: Any):  # noqa: ANN202
    """The parent half of a feat whose benefit is "you gain <card>"."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, **kw)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


def _implement(c: Cast, *refs: str) -> bool:
    """Which implement, by ref. The seven share one group, so `_group`
    cannot tell a wand from an orb and these cards name exactly one."""
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.ref in refs for w in gear.held)


def _weapon_attack(c: Cast, *groups: str):  # noqa: ANN202
    """"Weapon attack rolls you make with an X", as an attack-context gate."""

    def gate(ctx: dict[str, Any]) -> bool:
        return _keyworded(ctx, Keyword.WEAPON) and _group(c, *groups)

    return gate


# -- the r7 batch: a granted card and a swapped at-will, four times ---------


_granted("f2901", "f2901b")


def _melee_weapon(ctx: dict[str, Any]) -> bool:
    """A melee weapon attack, read off the row the damage context names."""
    p = get(ctx.get("power", ""))
    return (p is not None and p.reach.kind == "melee"
            and Keyword.WEAPON in p.keywords)


@power("f2901b", level=1, cls="", usage=DAILY, action=MINOR,
       reach=Melee(1), target=SELF, keywords=[Keyword.POISON],
       dropped=("Target.kind",))
def f2901b(c: Cast) -> None:
    """The printed target is *one weapon*, and nothing on this board is a
    weapon you can aim at -- so the row arms the caster's own next hit
    instead, which is what touching your own blade comes to in every
    fight the engine can set up. `escalate` is the "each failed saving
    throw" clause: it is handed the live effect and rewrites its burn."""
    me = c.me

    def worse(eff: Any) -> None:
        amount, dtype = eff.ongoing
        eff.ongoing = (min(20, amount + 5), dtype)

    def envenom(ev: Any) -> None:
        if ev.attacker != me:
            return
        c.condition(
            on=ev.target, until=When.SAVE_ENDS,
            ongoing=(5, DamageType.POISON), escalate=worse,
        )

    c.watch(Hit, envenom, on=me, until=When.ENCOUNTER, once=True)


@power("f2902", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w:blowgun",), swap=Swap(1, Usage.AT_WILL),
       dropped=("c.change_dice()",))
def f2902(c: Cast) -> None:
    """The card is handed over here and the two build-time clauses are
    header data: the blowgun `chargen` deals, and the at-will it is
    traded for. What is left is the die that weapon rolls, which is a
    field on the `Weapon` and not a thing a row edits."""
    c.grant_row("f2902b", on=c.me, until=When.ENCOUNTER)


@power("f2902b", level=1, cls="", usage=AT_WILL, action=STANDARD,
       reach=Ranged(10), target=ONE_CREATURE,
       keywords=[Keyword.POISON, Keyword.WEAPON], attack=Attack(DEX, vs=AC))
def f2902b(c: Cast) -> None:
    """"If the target is already slowed it is immobilized instead" is
    asked before the slow lands, or the row would always immobilise."""
    best = _best(c)
    if not c.strike(plus=best - c.attack_mod):
        return
    already = c.is_(Condition.SLOWED)
    c.damage(c.w(), 0)
    c.damage(0, best, dtype=DamageType.POISON)
    if already:
        c.immobilized(until=When.EONT)
    else:
        c.slowed(until=When.EONT)


_granted("f2903", "f2903b")


@power("f2903b", level=1, cls="", usage=AT_WILL, action=MOVE,
       reach=PERSONAL, target=SELF, dropped=("c.terrain(penalty=)",))
def f2903b(c: Cast) -> None:
    """A swim the length of your speed. The second sentence waives the
    attack penalty for fighting underwater with the wrong weapon, and
    `c.terrain` only answers *whether* the fight is aquatic -- there is
    no penalty attached to it to waive."""
    c.move(c.speed_of(), at="swim")


@power("f2904", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w:net",), swap=Swap(1, Usage.AT_WILL))
def f2904(c: Cast) -> None:
    """All three clauses. The weapon table keys on the ref, so the +1 is
    narrowed to the net rather than widened to the flail group it is
    filed under -- which would have paid a spiked chain as well."""
    me = c.me
    c.grant_row("f2904b", on=me, until=When.ENCOUNTER)
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: _keyworded(ctx, Keyword.WEAPON)
            and _implement(c, "w:net"))


@power("f2904b", level=1, cls="", usage=AT_WILL, action=STANDARD,
       reach=MeleeOrRanged(1, 10), target=ONE_CREATURE,
       keywords=[Keyword.WEAPON], attack=Attack(DEX, vs=AC))
def f2904b(c: Cast) -> None:
    """The two halves of the rider differ by branch, which is what
    `c.ranged` is for -- the keywords say nothing, because the same row
    is thrown and swung."""
    best = _best(c)
    if not c.strike(plus=best - c.attack_mod):
        return
    victim = c.target
    c.damage(c.w())
    c.grab()
    if c.ranged:
        c.pull(1, on=victim)
    else:
        c.slide(1, on=victim)


_granted("f2905", "f2905b")


@power("f2905b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL,
       target=NO_TARGET, keywords=[Keyword.HEALING],
       trigger="an enemy would deal fire or radiant damage to you",
       on=Trigger(DamageRolled, lambda w, me, ev: (
           ev.target == me
           and ev.dtype in (DamageType.FIRE, DamageType.RADIANT)
           and ev.source is not None and ev.source != me
           and team(w, ev.source) != team(w, me)
       ), "an enemy would deal fire or radiant damage to you"))
def f2905b(c: Cast) -> None:
    """The healing is the damage *before* it is reduced, so the amount is
    read off the event first and `c.reduce` zeroes it afterwards."""
    ev = c.trigger
    was = ev.amount
    c.reduce(was, ev)
    c.heal(was, on=c.me)


@power("f2906", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, swap=Swap(1, Usage.AT_WILL))
def f2906(c: Cast) -> None:
    """A standing modifier and a granted card on one row, which is fine:
    the grant is a line of the body, not a trigger. Being mounted is
    asked per blow -- a rider is unhorsed mid-fight."""
    me = c.me
    c.grant_row("f2906b", on=me, until=When.ENCOUNTER)
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.mount() is not None,
    )


@power("f2906b", level=1, cls="", usage=AT_WILL, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.RADIANT, Keyword.WEAPON], attack=Attack(DEX, vs=AC))
def f2906b(c: Cast) -> None:
    best = _best(c)
    if c.strike(plus=best - c.attack_mod):
        c.damage(c.w(), best, dtype=DamageType.RADIANT)
        c.penalty("attack", 2, until=When.SONT)


_granted("f2907", "f2907b")


@power("f2907b", level=1, cls="", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.STANCE],
       dropped=("c.immune(when=)",))
def f2907b(c: Cast) -> None:
    """The forced-movement clause is unconditional; the resistance is
    gated on being bloodied and so is laid as a modifier rather than as
    flat resistance. "Cannot be knocked prone" is the same gated shape
    and `c.immune` takes no `when`, so that third clause is named."""
    me = c.me
    c.stance(on=me, label=c.ref)
    c.resist_forced(2, on=me, until=When.STANCE)
    c.resist(5, on=me, until=When.STANCE, when=lambda ctx: c.bloodied(on=me))


@power("f2908", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, swap=Swap(1, Usage.AT_WILL))
def f2908(c: Cast) -> None:
    """The extra die is hung on `ActionPointSpent` rather than declared,
    because the row also hands over a card -- a declared trigger would
    mean the grant only happened when a point was spent."""
    me = c.me
    c.grant_row("f2908b", on=me, until=When.ENCOUNTER)

    def paid(ev: Any) -> None:
        if ev.actor != me or not c.bloodied(on=me):
            return
        c.bonus(
            "damage", 0, dice="1d6", on=me, until=When.EOT, once=True,
            when=lambda ctx: (p := get(ctx.get("power", ""))) is not None
            and p.reach.kind in (*MELEE_REACH, "ranged"),
        )

    c.watch(ActionPointSpent, paid, on=me, until=When.ENCOUNTER)


@power("f2908b", level=1, cls="", usage=AT_WILL, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
       attack=Attack(DEX, vs=AC))
def f2908b(c: Cast) -> None:
    best = _best(c)
    if c.strike(plus=best - c.attack_mod):
        c.damage(c.w(), best)
        for foe in c.within(1, side="enemy"):
            c.push(1, on=foe)


# -- the r37 batch ----------------------------------------------------------


@power("f2914", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with a melee weapon daily attack",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me
           and (p := get(ev.power)) is not None
           and p.usage.value == "daily"
           and Keyword.WEAPON in p.keywords
           and p.reach.kind == "melee"
       ), "you hit with a melee weapon daily attack"))
def f2914(c: Cast) -> None:
    """`Hit` fires partway through the attack's body, which is the right
    moment: the push and the knockdown are printed as part of the hit
    rather than after the whole power has resolved."""
    victim = c.trigger.target
    c.push(1, on=victim)
    c.prone(on=victim)


@power("f2915", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.escape()",))
def f2915(c: Cast) -> None:
    """Pays out when a creature escapes a grab you have on it. Escaping
    is an action nothing in the engine performs or announces -- a grab
    ends through `c.cure` or through its duration and says nothing about
    who broke it -- so the moment this row is printed for never comes."""


@power("f2916", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.forgo_defences()",))
def f2916(c: Cast) -> None:
    """"Instead of the normal +2", and the normal one is laid inside
    `Cast.second_wind`. Nothing forgoes it, and laying a +3 on top would
    come to +5 because untyped bonuses stack."""


@power("f2917", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2917(c: Cast) -> None:
    """An Intimidate bonus and a skill-challenge clause. Neither is a
    fight."""


# -- the r49 psionic batch --------------------------------------------------


@power("f2943", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2943(c: Cast) -> None:
    """Punches through the first 5 points of psychic resistance. Heroic
    tier, so 5."""
    c.ignore_resistance(5, DamageType.PSYCHIC, on=c.me, until=When.ENCOUNTER)


@power("f2944", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p11052",
       on=Trigger(PowerResolved, _used("p11052"), "you use that power"))
def f2944(c: Cast) -> None:
    """Declared on `PowerResolved` rather than `PowerUsed`: the mark is
    on "any creature you affect", and a use announces itself before its
    body has affected anybody."""
    for who in c.trigger.targets:
        c.mark(on=who, until=When.EONT)


@power("f2945", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recast(reach=)",))
def f2945(c: Cast) -> None:
    """Turns a close burst 1 into an area burst 1 within 5. Reach is
    header data the action menu reads before anything runs, and nothing
    rewrites one."""


@power("f2946", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p11052",
       on=Trigger(PowerUsed, _used("p11052"), "you use that power"))
def f2946(c: Cast) -> None:
    c.temp_hp(5, on=c.me)


@power("f2947", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p11052",
       on=Trigger(PowerUsed, _used("p11052"), "you use that power"))
def f2947(c: Cast) -> None:
    """"No creature can benefit from concealment from you" is
    `c.ignore_cover` from the attacker's end. It waives cover as well,
    which is a shade wider than the printed line; the vocabulary has no
    concealment-only form and the narrower `partial=True` waives less
    than printed rather than more."""
    c.ignore_cover(on=c.me, until=When.EONT)


@power("f2948", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you spend a healing surge",
       on=Trigger(SurgeSpent, lambda w, me, ev: ev.actor == me,
                  "you spend a healing surge"),
       dropped=("c.telepathy_range()",))
def f2948(c: Cast) -> None:
    """`by_me` is no use on `SurgeSpent` -- it names its subject `actor`.
    Telepathy is a racial trait nothing carries, so the reach is written
    as 10 squares, which is what the races printing it have."""
    for friend in _near_allies(c, 10):
        c.save(on=friend)


# -- flanking, and a feat power that answers a miss -------------------------


@power("f2955", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="a creature flanking you hits you",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.target == me and ev.attacker in flankers(w, me)
       ), "a creature flanking you hits you"))
def f2955(c: Cast) -> None:
    """`flankers` is the standing question "who is flanking this
    creature", which is exactly the printed condition. The benefit is
    `c.cannot_be_flanked`, held for a turn rather than the fight."""
    c.cannot_be_flanked(on=c.me, until=When.EONT)


_granted("f2956", "f2956b", swap=Swap(6, utility=True))


@power("f2956b", level=6, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with a melee or ranged attack roll",
       on=Trigger(Miss, lambda w, me, ev: (
           ev.attacker == me
           and (p := get(ev.power)) is not None
           and p.reach.kind in ("melee", "ranged", "melee_or_ranged")
       ), "you miss with a melee or ranged attack"))
def f2956b(c: Cast) -> None:
    """The bonus is against *that* target and nobody else, which is a
    gate on the attack context rather than a flat +3."""
    victim = c.trigger.target
    c.bonus("attack", 3, on=c.me, until=When.EONT, kind="power",
            when=lambda ctx: ctx.get("target") == victim)


# -- the beast companion batch ----------------------------------------------


@power("f2968", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2968(c: Cast) -> None:
    """+3 from combat advantage instead of +2 is one extra point, laid
    on top of the +2 `resolve.attack` already adds. The companion is
    looked up inside the gate, not at arming -- it is called onto the
    board mid-fight -- but the companion's own half of the bonus has to
    be hung on a creature that exists, so it is laid only if one is
    already out."""
    me = c.me

    def paired(who: int, ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        pet = c.companion(of=me)
        if victim is None or pet is None:
            return False
        crew = flankers(c.world, victim)
        return who in crew and pet in crew and me in crew

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: paired(me, ctx))
    pet = c.companion(of=me)
    if pet is not None:
        c.bonus("attack", 1, on=pet, until=When.ENCOUNTER,
                when=lambda ctx: paired(pet, ctx))


@power("f2969", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2969(c: Cast) -> None:
    """An Insight check rolled twice. A check, not a fight."""


@power("f2971", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2971(c: Cast) -> None:
    """An Intimidate bonus while the companion is beside you. A check,
    not a fight."""


# -- the q346 batch ---------------------------------------------------------


@power("f2975", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.run()",))
def f2975(c: Cast) -> None:
    """Difficult terrain is ignored *while running*. `c.ignores_difficult`
    names which sort of ground, not which sort of move, and running is
    not a state anything holds -- `c.moving_as` knows climb and swim and
    nothing announces a run. The two skill bonuses are not a fight."""


@power("f2976", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p2483 or p2484",
       on=Trigger(PowerUsed, lambda w, me, ev: (
           ev.actor == me and ev.power in ("p2483", "p2484")
       ), "you use either of those powers"))
def f2976(c: Cast) -> None:
    """"End one effect" -- so the daze goes first and the weakness only
    if there was no daze, rather than both."""
    if not c.cure(Condition.DAZED, on=c.me):
        c.cure(Condition.WEAKENED, on=c.me)


@power("f2977", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2977(c: Cast) -> None:
    """A floor under two skill checks. Neither is a fight."""


# -- the r8 batch -----------------------------------------------------------


@power("f3014", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3014(c: Cast) -> None:
    """An Intimidate check rolled twice. A check, not a fight."""


_granted("f3015", "f3015b")


@power("f3015b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE, dropped=("Target.kind",))
def f3015b(c: Cast) -> None:
    """The printed target is *one object*, and the two branches under it
    -- a weapon whose attacks lose damage, armour whose wearer loses AC
    -- are both about which kind of object it is. Nothing on the board
    is an object you can aim at, so the row aims at a creature and lays
    the vulnerability that is common to every branch."""
    c.vulnerable(c.level // 2 + c.int_mod, until=When.EONT)


@power("f3016", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use f3015b",
       on=Trigger(PowerResolved, _used("f3015b"), "you use that power"))
def f3016(c: Cast) -> None:
    """Relays the vulnerability for the rest of the fight, or until sight
    of the target is lost. There is no event for losing sight of
    somebody, so it is asked at the end of every turn -- which is as
    often as anything on the board has moved."""
    for who in c.trigger.targets:
        hold = c.vulnerable(c.level // 2 + c.int_mod, on=who,
                            until=When.ENCOUNTER)

        def lost(ev: TurnEnd, who: int = who, hold: Any = hold) -> None:
            if not c.can_see(who):
                c.end_effect(hold)

        c.watch(TurnEnd, lost, until=When.ENCOUNTER, once=True)


# -- the q248 batch: what an ally beside you gets ---------------------------


@power("f3019", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3019(c: Cast) -> None:
    """Gated resistance, which is a modifier rather than flat resistance
    -- and the damage context it is handed carries `source`, so "from
    enemies marked by you" is a real question. Adjacency is asked per
    blow because an ally steps in and out of it."""
    me = c.me

    def mine(ctx: dict[str, Any], friend: int) -> bool:
        src = ctx.get("source")
        return (
            src is not None
            and c.adjacent_to(me, friend)
            and c.marked(on=src)
        )

    for ally in allies(c.world, me):
        if ally == me:
            continue
        c.resist(2, on=ally, until=When.ENCOUNTER,
                 when=lambda ctx, f=ally: mine(ctx, f))


@power("f3020", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3020(c: Cast) -> None:
    """"You *end* that movement adjacent to an ally", and neither event
    on its own says that.

    `ForcedMove` names the shover but is answered before a square has
    been crossed -- `movement._forced` emits it, reads the agreed
    distance back, and only then steps. `Moved` knows where the creature
    landed but not who pushed it, and fires once per square. So the
    shove is noted here and the steps counted down, and the row acts on
    the last one. A shove cut short by a wall leaves a stale count, which
    the next shove of that creature overwrites.
    """
    me = c.me
    pending: dict[int, int] = {}

    def shoved(ev: Any) -> None:
        if ev.source == me:
            pending[ev.target] = ev.squares

    def stepped(ev: Any) -> None:
        left = pending.get(ev.actor)
        if left is None or getattr(ev, "kind_", "") not in FORCED:
            return
        if left > 1:
            pending[ev.actor] = left - 1
            return
        pending.pop(ev.actor, None)
        beside = [
            a for a in allies(c.world, me)
            if a != me and c.adjacent_to(ev.actor, a)
        ]
        if beside:
            c.grants_advantage(on=ev.actor, to=beside[0], until=When.EONT)

    c.watch(ForcedMove, shoved, on=me, until=When.ENCOUNTER)
    c.watch(Moved, stepped, on=me, until=When.ENCOUNTER)


@power("f3021", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.bonus(surge_value)",))
def f3021(c: Cast) -> None:
    """A bonus to an adjacent ally's healing surge value.
    `Health.surge_value` is a derived property -- a quarter of maximum
    hit points -- and nothing reads a modifier beside it, so the whole
    benefit has nowhere to land."""


@power("f3022", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3022(c: Cast) -> None:
    """The damage context carries `target`, which is the enemy, so both
    halves of the sentence are askable: does that enemy grant combat
    advantage to *me*, and is the ally standing beside me."""
    me = c.me

    def gate(ctx: dict[str, Any], friend: int) -> bool:
        foe = ctx.get("target")
        return (
            foe is not None
            and c.adjacent_to(me, friend)
            and has_combat_advantage(c.world, me, foe)
        )

    for ally in allies(c.world, me):
        if ally == me:
            continue
        c.bonus("damage", 2, on=ally, until=When.ENCOUNTER,
                when=lambda ctx, f=ally: gate(ctx, f))


# -- the artificer batch ----------------------------------------------------
#
# All three name a feature that has a ref and a declared row now, so the
# feature is no longer what any of them is waiting for.


@power("f3045", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.race_option()",))
def f3045(c: Cast) -> None:
    """Spends a racial power to buy an extra use of a feature's power.

    Re-aimed. `cf:artificer-f2`'s three cards are `p4128`, `p7635` and
    `p10187` and `c.restore_use` hands one of them back; `c.expend_row`
    now charges a price. What is left is *which* row to charge: the
    racial power is whatever the character's dilettante choice took,
    and a build decision with nowhere to write it down is the same hold
    nineteen other rows name."""


@power("f3046", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.boost_roll()",))
def f3046(c: Cast) -> None:
    """Rides on an ally's attack that benefited from `cf:artificer-f0s0`.

    That feature is declared and refused in play: the +2 it banks in a
    weapon is spent after the roll and `c.boost_roll()` is what it
    waits on. Until the charge exists nothing can have benefited from
    it."""


@power("f3047", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.effects_on()",))
def f3047(c: Cast) -> None:
    """Re-aimed. Rewrites what an ally gets for *ending* two of
    `cf:artificer-f2`'s infusions early -- `p7635` and `p10187`, both
    written. Ending one is `c.end_effect` now, and the card prints no
    moment for it: the ally may take the trade at any time, which is
    `c.endable` with `then=` as the teleport. That wants the effect
    itself, and nothing asks what a creature is currently under --
    `c.end_effect` finds one by label and ends what it finds, which is
    the wrong half of the operation to arm a choice with."""


# -- the shadow batch -------------------------------------------------------


@power("f3064", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.darkvision()",))
def f3064(c: Cast) -> None:
    """Dropped: darkvision, which is not a sense the sight code knows.
    The Stealth bonus is not a fight."""
    c.set_origin("shadow", until=When.ENCOUNTER)


_granted("f3065", "f3065b", swap=Swap(3, Usage.ENCOUNTER))


@power("f3065b", level=3, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.COLD, Keyword.NECROTIC, Keyword.SHADOW,
                 Keyword.WEAPON],
       attack=Attack(DEX, vs=REF))
def f3065b(c: Cast) -> None:
    """"Dexterity or Charisma" is the higher of the two, carried as
    `plus=` because the header names one. The 1d6 is one roll that is
    cold *and* necrotic, so it is its own `c.damage` with both types
    rather than two rolls; the weapon damage keeps the weapon's own type.
    Paragon swaps are out of scope."""
    best = max(c.dex_mod, c.cha_mod)
    if c.strike(plus=best - c.attack_mod):
        c.damage(c.w(), best)
        c.damage("1d6", dtypes=(DamageType.COLD, DamageType.NECROTIC))
        c.insubstantial(on=c.me, until=When.EONT)


_granted("f3066", "f3066b", swap=Swap(6, utility=True))


@power("f3066b", level=6, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.SHADOW, Keyword.TELEPORTATION],
       dropped=("c.low_light()",))
def f3066b(c: Cast) -> None:
    """The destination must contain dim light or darkness. Lighting is
    not on the board, so the teleport is unrestricted and the
    restriction is named."""
    c.teleport(10)


_granted("f3067", "f3067b", swap=Swap(9, Usage.DAILY))


@power("f3067b", level=9, cls="", usage=DAILY, action=STANDARD,
       reach=CloseBurst(2), target=EACH_ENEMY,
       keywords=[Keyword.COLD, Keyword.NECROTIC, Keyword.SHADOW,
                 Keyword.WEAPON],
       attack=Attack(DEX, vs=FORT),
       dropped=("c.low_light()",))
def f3067b(c: Cast) -> None:
    """The damage is one roll that is cold *and* necrotic, which is what
    `dtypes=` says: a creature resisting only one of them takes all of
    it. The Effect line happens whether or not anything is hit, so it sits
    outside the hit branch under `c.first`. The last sentence turns dim
    light into total concealment for the rest of the fight, and lighting
    is not on the board."""
    best = max(c.dex_mod, c.cha_mod)
    if c.strike(plus=best - c.attack_mod):
        c.damage(c.w(), best, dtypes=(DamageType.COLD, DamageType.NECROTIC))
        c.dazed(until=When.SAVE_ENDS)
    if c.first:
        c.invisible(on=c.me, until=When.EONT)
        c.shift(1)


# -- single riders ----------------------------------------------------------


@power("f3070", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3070(c: Cast) -> None:
    """"Creatures taking ongoing fire damage" is read off the live
    effects rather than off any event -- an ongoing burn is an `Effect`
    with a `(amount, dtype)` pair on it, and that is the only place the
    state exists."""
    me = c.me

    def burning(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or not _keyworded(ctx, Keyword.ARCANE, Keyword.FIRE):
            return False
        return any(
            eff.ongoing is not None and eff.ongoing[1] is DamageType.FIRE
            for eff in c.world.effects.of(victim)
        )

    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, kind="feat",
            when=burning)


@power("f3073", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a r44 racial power",
       on=Trigger(PowerUsed, _used_any(*R44), "you use a r44 racial power"))
def f3073(c: Cast) -> None:
    """The race's three powers are declared, so "a r44 racial power" is
    a list of refs. `side="ally"` leaves the caster out, which is what
    "one ally within 10 squares of you" means; the free action is the
    shift itself and costs the ally nothing here."""
    mate = c.choose([a for a in c.within(10, side="ally")], "which ally")
    if mate is not None:
        c.shift(1, who=mate)


@power("f3074", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.ignores_difficult(shift=)",))
def f3074(c: Cast) -> None:
    """Re-aimed: "a r44 racial power" is three declared refs now, so the
    trigger is writable. The benefit is not. `c.ignores_difficult` is
    per terrain kind and board-wide, and the printed line is per *kind
    of move* -- laid blanket it would exempt a full run as well as a
    shift, which is a much larger rule and the whole of this feat.
    `rt:r4-wild-step` is held back by the same sentence."""


@power("f3091", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with an attack",
       on=Trigger(Hit, lambda w, me, ev: ev.attacker == me,
                  "you hit with an attack"),
       )
def f3091(c: Cast) -> None:
    """`Hit` fires before the body rolls its damage, which is what makes
    "apply its damage bonus to the triggering hit" writable at all --
    the once-shot bonus is in place for the roll that follows.

    `c.expend_row` charges the p1747 use the card charges, and refuses
    the whole rider once that row is spent -- which is the limit, and
    the reason this row stays `AT_WILL`."""
    if not c.expend_row("p1747"):
        return
    c.bonus("damage", c.str_mod, on=c.me, until=When.EOT, once=True)


@power("f3101", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3101(c: Cast) -> None:
    """+2, or +4 against a dragon -- written as a +2 and a *second* +2
    under its own kind, because two bonuses of one kind do not add and
    a +2 plus a gated +2 of the same kind would come to +2 forever."""
    me = c.me
    fearful = lambda ctx: _keyworded(ctx, Keyword.FEAR)  # noqa: E731

    def draconic(ctx: dict[str, Any]) -> bool:
        who = ctx.get("attacker")
        return (
            fearful(ctx) and who is not None and c.is_kind("dragon", on=who)
        )

    for defence in ALL_DEFENCES:
        c.bonus(defence, 2, on=me, until=When.ENCOUNTER, when=fearful)
        c.bonus(defence, 2, on=me, until=When.ENCOUNTER,
                kind=f"{c.ref}:dragon", when=draconic)


@power("f3102", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit a creature with p12577",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and ev.power == "p12577"
       ), "you hit with that racial power"))
def f3102(c: Cast) -> None:
    c.mark(on=c.trigger.target, until=When.EONT)


# -- four feats with no prerequisite at all ---------------------------------


@power("f3106", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3106(c: Cast) -> None:
    """"An effect you imposed" is `c.suffering`, which is the only thing
    that knows who laid what -- and it cannot be asked from a trigger
    predicate, which is handed `(world, me, event)` and no `Cast`. So
    this is a trait with a watch rather than a declared trigger."""
    me = c.me

    def failed(ev: Any) -> None:
        if ev.saved or ev.actor == me:
            return
        if ev.actor in c.suffering():
            c.temp_hp(5, on=me)

    c.watch(SavingThrow, failed, on=me, until=When.ENCOUNTER)


@power("f3107", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you spend an action point to take an extra action",
       on=Trigger(ActionPointSpent, lambda w, me, ev: ev.actor == me,
                  "you spend an action point"))
def f3107(c: Cast) -> None:
    for defence in ALL_DEFENCES:
        c.bonus(defence, 1, on=c.me, until=When.SONT)


@power("f3108", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you make a successful saving throw",
       on=Trigger(SavingThrow, lambda w, me, ev: ev.actor == me and ev.saved,
                  "you succeed at a saving throw"))
def f3108(c: Cast) -> None:
    """"The first time in an encounter" is the row's own usage: a
    triggered row spends a use every time it fires, so `ENCOUNTER` is
    the printed limit rather than a counter in the body. `"skill"` is
    the key `skills.check` totals for every check."""
    me = c.me
    c.bonus("attack", 2, on=me, until=When.EONT)
    c.bonus("skill", 2, on=me, until=When.EONT)
    c.bonus("save", 2, on=me, until=When.EONT)


@power("f3109", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you roll a natural 20",
       on=(
           Trigger(AttackRolled, lambda w, me, ev: (
               ev.attacker == me and ev.natural == 20
           ), "you roll a natural 20 on an attack roll"),
           Trigger(SkillCheck, lambda w, me, ev: (
               ev.actor == me and ev.natural == 20
           ), "you roll a natural 20 on a skill check"),
           Trigger(SavingThrow, lambda w, me, ev: (
               ev.actor == me and ev.natural == 20
           ), "you roll a natural 20 on a saving throw"),
       ))
def f3109(c: Cast) -> None:
    """Three printed sources for one trigger line, so all three are
    declared -- declaring only the attack roll would look finished and
    be two thirds wrong."""
    c.save(on=c.me)
    near = _near_allies(c, 5)
    if near:
        c.save(on=near[0])


# -- the psionic racial batch -----------------------------------------------


@power("f3111", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.no_provoke(when=)",))
def f3111(c: Cast) -> None:
    """No opportunity attacks from enemies that are granting you combat
    advantage. `c.no_provoke` names one creature or all of them and
    takes no gate, and which enemies are granting advantage changes
    every time somebody moves."""


@power("f3112", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use m4421a6",
       on=Trigger(PowerUsed, _used("m4421a6"), "you use that racial power"),
       dropped=("c.triggering_of()",))
def f3112(c: Cast) -> None:
    """The shift plays. The temporary hit points turn on whether the roll
    that triggered *the racial power* then missed or failed, and a row
    answering a use has no way back to the event that use was answering:
    `PowerUsed` carries the actor, the ref and the targets."""
    c.shift(1)


@power("f3113", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you are bloodied",
       on=Trigger(Bloodied, lambda w, me, ev: ev.actor == me,
                  "you are bloodied"))
def f3113(c: Cast) -> None:
    """`Bloodied` carries `actor` and nothing else, which is all this
    needs. "The first time in each encounter" is the row's usage."""
    for friend in _near_allies(c, 5):
        c.bonus("attack", 1, on=friend, until=When.EONT, kind="racial")


@power("f3114", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f3114(c: Cast) -> None:
    """The printed constraint is on where the shift *ends*, so the square
    is picked first and `to=` is what says it."""
    grid = c.world.grid
    near = {s for foe in c.enemies() for s in spread(grid.squares_of(foe), 1)}
    good = sorted(
        sq for sq in neighbours(c.here)
        if sq in near and grid.passable(sq) and grid.occupant(sq) is None
    )
    if good:
        c.shift(1, to=good[0])


@power("f3117", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3117(c: Cast) -> None:
    """`c.bonus("initiative", ...)` is read by nothing -- `Initiative`
    holds its own number -- so the initiative half is `c.initiative`.
    Neither bonus prints a type word, so both are untyped."""
    me = c.me
    c.initiative(2, on=me)
    c.bonus("save", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.bloodied(on=me))


@power("f3118", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3118(c: Cast) -> None:
    """A trait rather than a declared trigger, because the printed
    condition -- the effect saved against is one *I* laid, with a
    psychic attack -- needs `c.suffering` and `keywords_of`, and a
    predicate is handed no `Cast`."""
    me = c.me

    def shrugged(ev: Any) -> None:
        if not ev.saved or ev.actor == me:
            return
        if ev.actor not in c.suffering():
            return
        if Keyword.PSYCHIC not in keywords_of(ev.against):
            return
        c.slide(1, on=ev.actor)
        c.vulnerable(5, DamageType.PSYCHIC, on=ev.actor, until=When.EONT)

    c.watch(SavingThrow, shrugged, on=me, until=When.ENCOUNTER)


# -- the untiered ladder ----------------------------------------------------


@power("f3119", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3119(c: Cast) -> None:
    """A trait is armed before anybody has taken a turn, so "your first
    turn" is `When.EONT` -- the end of the next turn of mine, which is
    the first one."""
    for foe in c.enemies():
        c.grants_advantage(on=foe, to="me", until=When.EONT)


@power("f3121", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3121(c: Cast) -> None:
    """The armour check penalty falls on skills and nothing else, so
    waiving it is not a combat effect."""


@power("f3122", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.reroll_ones()",))
def f3122(c: Cast) -> None:
    """Axe is a real group, so the attack bonus plays. Rerolling a
    damage die that came up 1 is read where the dice are rolled, and
    `DamageRolled` carries a total with no dice behind it."""
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
            when=_weapon_attack(c, "axe"))


@power("f3123", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3123(c: Cast) -> None:
    """Hammer is a printed group the weapon table carries and `chargen`
    now deals, so both clauses pay on either weapon. `c.forces` is the
    printed "+1 to the number of squares you push or slide", and it is
    keyed on the shover."""
    me = c.me
    armed = lambda ctx: _group(c, "mace", "hammer")  # noqa: E731
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=_weapon_attack(c, "mace", "hammer"))
    c.forces(1, on=me, until=When.ENCOUNTER, when=armed)


@power("f3124", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3124(c: Cast) -> None:
    """"A single creature that is not adjacent to any other creature" is
    geometry asked at the moment of the roll, which the damage context's
    `target` allows."""
    me = c.me

    def alone(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or not _group(c, "bow"):
            return False
        return not [
            other for other in c.within(1, of=victim) if other != victim
        ]

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=_weapon_attack(c, "bow"))
    c.bonus("damage", 1, on=me, until=When.ENCOUNTER, when=alone)


@power("f3125", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3125(c: Cast) -> None:
    c.resist(5, DamageType.COLD, on=c.me, until=When.ENCOUNTER)


@power("f3126", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3126(c: Cast) -> None:
    """Partial *and* superior cover, so the full waiver rather than
    `partial=True`, which leaves superior cover standing. It waives
    concealment too, which the vocabulary gives no way to keep."""
    me = c.me
    crossbow = lambda ctx: _group(c, "crossbow")  # noqa: E731
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=_weapon_attack(c, "crossbow"))
    c.ignore_cover(on=me, until=When.ENCOUNTER, when=crossbow)


@power("f3127", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.bonus('save:death')",))
def f3127(c: Cast) -> None:
    """A bonus to death saving throws. A death save is not rolled through
    `Effects.save` and has no modifier key of its own, so there is
    nowhere for the +5 to be read."""


@power("f3128", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.escape()",))
def f3128(c: Cast) -> None:
    """The extra saving throw plays and is the larger half. Escaping is
    an action nothing performs, so the +5 to the check has no check to
    be added to."""
    me = c.me
    held = (Condition.IMMOBILIZED, Condition.SLOWED, Condition.RESTRAINED)

    def early(ev: Any) -> None:
        if ev.actor != me or ev.ghost:
            return
        if any(c.is_(cond, on=me) for cond in held):
            c.save(on=me)

    c.watch(TurnStart, early, on=me, until=When.ENCOUNTER)


@power("f3129", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use an at-will attack power and miss every target",
       on=Trigger(PowerResolved, lambda w, me, ev: (
           ev.actor == me
           and (p := get(ev.power)) is not None
           and p.usage.value == "at-will"
           and bool(ev.rolls)
           and not any(r.hit for r in ev.rolls)
       ), "you miss every target with an at-will attack"))
def f3129(c: Cast) -> None:
    """`PowerResolved` is the only event that carries every roll a use
    made; `Miss` fires once per target and cannot say "every"."""
    c.bonus("attack", 1, on=c.me, until=When.EONT)


@power("f3130", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.forgo_healing()",))
def f3130(c: Cast) -> None:
    """Handing the hit points to a neighbour costs you yours, and nothing
    refuses the healing a second wind does."""


@power("f3131", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.aid_another()",))
def f3131(c: Cast) -> None:
    """Aid another is an action nothing in the engine performs, so
    neither the +5 to the attempt nor the larger grant has anywhere to
    go."""


@power("f3132", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3132(c: Cast) -> None:
    """A trait with a watch rather than a declared trigger, because the
    bloodied test has to be made at the moment the surge goes -- by the
    time the hit points arrive the creature may not be bloodied any
    more. `by_me` is no use on `SurgeSpent`; it names its subject
    `actor`."""
    me = c.me

    def spent(ev: Any) -> None:
        if ev.actor != me or not c.bloodied(on=me):
            return
        for friend in _near_allies(c, 5):
            c.temp_hp(3, on=friend)

    c.watch(SurgeSpent, spent, on=me, until=When.ENCOUNTER)


@power("f3133", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3133(c: Cast) -> None:
    """A bonus to trained skills and nothing else. Not a fight."""


@power("f3134", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you spend a healing surge",
       on=Trigger(SurgeSpent, lambda w, me, ev: ev.actor == me,
                  "you spend a healing surge"))
def f3134(c: Cast) -> None:
    c.temp_hp(5, on=c.me)


@power("f3135", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f3135(c: Cast) -> None:
    """"Your next damage roll" is `once=True`; the damage context carries
    the row that made it, which is where melee and weapon are read."""
    c.bonus("damage", 5, on=c.me, until=When.EONT, kind="power", once=True,
            when=_melee_weapon)


@power("f3136", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f3136(c: Cast) -> None:
    """A free action answering the same moment."""
    c.shift(3)


@power("f3137", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.darkvision()",))
def f3137(c: Cast) -> None:
    """Darkvision out to 2 squares. Sight is line of effect plus
    visibility, with no notion of light level behind it, so there is no
    state for this to set."""


@power("f3138", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3138(c: Cast) -> None:
    """Armed before anybody acts, so "your first turn" is the end of my
    next turn."""
    c.bonus("speed", 4, on=c.me, until=When.EONT, kind="feat")


@power("f3139", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3139(c: Cast) -> None:
    c.resist(5, DamageType.FIRE, on=c.me, until=When.ENCOUNTER)


@power("f3140", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Gear.armour_speed",))
def f3140(c: Cast) -> None:
    """Waives the speed penalty for heavy armour. `Gear` carries the
    armour as a word and `Movement.speed` never looks at it, so there is
    no penalty here to waive."""


@power("f3141", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3141(c: Cast) -> None:
    """The defence context is the attack context, and it carries
    `opportunity` -- so "against opportunity attacks" is a real gate on
    the defending side, which the damage side could not have said."""
    me = c.me

    def parrying(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("opportunity")) and _group(c, "heavy blade")

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=_weapon_attack(c, "heavy blade"))
    for defence in ALL_DEFENCES:
        c.bonus(defence, 2, on=me, until=When.ENCOUNTER, when=parrying)


@power("f3142", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.chosen_weapon_group()",))
def f3142(c: Cast) -> None:
    """Printed as "choose an implement", and nothing records a choice
    made at build time, so the bonus pays on every implement attack --
    wider than print for a character holding two kinds, and exactly
    right for the one implement `chargen` actually hands out."""
    c.bonus(
        "damage", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _keyworded(ctx, Keyword.IMPLEMENT),
    )


@power("f3143", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3143(c: Cast) -> None:
    for defence in (FORT, REF, WILL):
        c.bonus(defence, 1, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f3144", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3144(c: Cast) -> None:
    """The damage context carries no `advantage`, unlike the attack one,
    so the second clause asks `has_combat_advantage` again at the moment
    the damage is rolled. A grant that was spent on the attack roll is
    gone by then -- see the report."""
    me = c.me

    def exposed(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            victim is not None and _group(c, "light blade")
            and has_combat_advantage(c.world, me, victim)
        )

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=_weapon_attack(c, "light blade"))
    c.bonus("damage", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=exposed)


@power("f3145", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.draw()",))
def f3145(c: Cast) -> None:
    """Every weapon group, so no group gate at all -- just the weapon
    keyword. Sheathing one weapon and drawing another on one minor
    action is the dropped half; nothing puts a weapon into a hand."""
    c.bonus(
        "attack", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _keyworded(ctx, Keyword.WEAPON),
    )


@power("f3146", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w:orb",))
def f3146(c: Cast) -> None:
    """Both clauses. The implements share one group, so the gate is on
    the ref -- gating on `"implement"` would pay every rod and wand as
    well. Heroic tier, so +1 each."""
    me = c.me
    orbed = lambda ctx: _implement(c, "w:orb")  # noqa: E731
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: _keyworded(ctx, Keyword.IMPLEMENT)
            and _implement(c, "w:orb"))
    c.forces(1, on=me, until=When.ENCOUNTER, when=orbed)


@power("f3147", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3147(c: Cast) -> None:
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f3148", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f3148(c: Cast) -> None:
    """A shield's check penalty falls on skills, as an armour's does."""


@power("f3149", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w:sling",),
       dropped=("c.no_provoke(when=)",))
def f3149(c: Cast) -> None:
    """Sling is a printed group the weapon table carries and `chargen`
    now deals, so the attack bonus plays. Heroic tier, so +1.

    Dropped: "you don't provoke opportunity attacks". `c.no_provoke` is
    all-or-nothing on the creature and cannot be narrowed to the attacks
    made with one weapon, and turning it on whole would take every
    ranged attack the character makes out of the opportunity window."""
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
            when=_weapon_attack(c, "sling"))


@power("f3150", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3150(c: Cast) -> None:
    """The damage context carries `charge`, which is what makes the
    second clause writable -- "when charging" would otherwise be a key
    the context does not have, and silently false."""
    me = c.me
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=_weapon_attack(c, "spear"))
    c.bonus(
        "damage", 1, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: bool(ctx.get("charge")) and _group(c, "spear"),
    )


@power("f3151", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.no_provoke(when=)", "c.reach_bonus()"))
def f3151(c: Cast) -> None:
    """Staff is a real group, and the bonus is printed for implement
    *and* weapon powers, so there is no keyword gate on top of it. The
    other two clauses each want something the vocabulary does not have:
    a gate on `c.no_provoke`, and a way to lengthen a melee attack's
    reach as opposed to the squares a creature threatens."""
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: _group(c, "staff"))


@power("f3152", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3152(c: Cast) -> None:
    """Ongoing damage arrives through `world.damage` with the effect's
    own description as its detail, so "resist 3 to ongoing damage" is
    read off that -- it is the only mark an ongoing tick leaves in the
    damage context."""
    me = c.me
    c.bonus(FORT, 2, on=me, until=When.ENCOUNTER, kind="feat")
    c.resist(
        3, on=me, until=When.ENCOUNTER,
        when=lambda ctx: "ongoing" in str(ctx.get("power", "")),
    )


@power("f3153", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3153(c: Cast) -> None:
    """Same first-turn reading as f3119: a trait is armed before anybody
    has acted, so the end of my next turn is the end of my first."""
    me = c.me
    c.bonus(REF, 2, on=me, until=When.ENCOUNTER, kind="feat")
    for foe in c.enemies():
        c.grants_advantage(on=foe, to="me", until=When.EONT)


@power("f3154", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3154(c: Cast) -> None:
    """"Even if the effect doesn't normally end on a save" is why this is
    not `c.save`: that one only finds save-ends effects and would never
    reach a daze clocked on a turn. The roll is `bare=True`, which still
    totals the caster's save modifiers, and what it ends is found by the
    condition rather than by the row that laid it."""
    me = c.me
    c.bonus(WILL, 2, on=me, until=When.ENCOUNTER, kind="feat")

    def early(ev: Any) -> None:
        if ev.actor != me or ev.ghost:
            return
        for cond in (Condition.DAZED, Condition.STUNNED):
            if not c.is_(cond, on=me):
                continue
            if c.save(on=me, bare=True, against=c.ref):
                c.end_effect(on=me, carrying=cond)
            return

    c.watch(TurnStart, early, on=me, until=When.ENCOUNTER)


@power("f3155", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.bonus(surge_value)",))
def f3155(c: Cast) -> None:
    """A bonus to your own healing surge value. `Health.surge_value` is a
    derived quarter of maximum hit points with no modifier read beside
    it -- the same gap f3021 carries from the other end."""


@power("f3156", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3156(c: Cast) -> None:
    """The saving-throw context carries `ongoing` as a plain flag, which
    is exactly this printed narrowing."""
    c.bonus(
        "save", 5, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: bool(ctx.get("ongoing")),
    )


@power("f3157", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w:wand",))
def f3157(c: Cast) -> None:
    """Both clauses, gated on the ref for the reason `f3146` is. Heroic
    tier, so +1, and `c.ignore_cover` is the second sentence whole --
    partial and superior are the only two kinds there are."""
    me = c.me
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: _keyworded(ctx, Keyword.IMPLEMENT)
            and _implement(c, "w:wand"))
    c.ignore_cover(on=me, until=When.ENCOUNTER)


# -- the augmentable batch --------------------------------------------------


@power("f3158", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=AUGMENT)
def f3158(c: Cast) -> None:
    """Gives a named power the augmentable keyword and a new clause to
    buy with a point. An augment is a branch inside the power's own row,
    chosen by `dsl.use`, and nothing adds one from outside."""


@power("f3159", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=AUGMENT)
def f3159(c: Cast) -> None:
    """Same shape as f3158, on a different racial power."""


@power("f3160", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use m5139a3",
       on=Trigger(PowerUsed, _used("m5139a3"), "you use that racial power"))
def f3160(c: Cast) -> None:
    """The Athletics substitution is a check rather than a fight; the
    Will bonus is the combat half, and it is gated on still holding a
    power point at the moment the racial power goes off."""
    if c.points() >= 1:
        c.bonus(WILL, 2, on=c.me, until=When.EONT)


@power("f3161", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=AUGMENT)
def f3161(c: Cast) -> None:
    """Same shape as f3158, on a racial power that answers a hit."""


@power("f3162", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use rt:r24-ferocity",
       on=Trigger(PowerUsed, _used("rt:r24-ferocity"),
                  "you use that racial trait"))
def f3162(c: Cast) -> None:
    """`rt:r24-ferocity` is a declared row and a triggered one, so its
    firing announces itself like any other use -- and `PowerUsed` is
    announced above the body, which is the one window in which a
    modifier can still reach the swing it is about to make.

    Not an augment after all: the point is spent by the feat rather
    than by the power, which `c.spend_points` says. The trait's blow is
    a melee basic, so the weapon branch is the only one that applies.
    """
    if c.points() >= 1 and c.spend_points(1):
        c.bonus("damage", 0, dice=c.w(), on=c.me, until=When.EOT, once=True)


@power("f3163", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("query.charging()",))
def f3163(c: Cast) -> None:
    """`rt:r24-heedless-charge` is declared and lays +2 `kind="racial"`
    on the same gate. Two of a kind do not stack and the larger wins,
    so laying the modifier under the same kind *is* "the bonus is equal
    to" for any character whose better mod is 2 or more -- which the
    prerequisite's psionic class makes near-certain. Below that the
    trait's +2 stands, which is the one place this reads generously.

    Dropped, and the trait drops it too: the narrowing is to opportunity
    attacks provoked by **your own charge**, and the defence context
    carries the incoming blow's `opportunity` and nothing about what the
    defender was doing when it provoked one.
    """
    c.bonus(AC, max(c.con_mod, c.wis_mod), kind="racial", on=c.me,
            until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("opportunity")))


@power("f3164", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p2484",
       on=Trigger(PowerUsed, _used("p2484"), "you use that power"))
def f3164(c: Cast) -> None:
    """"While under the effects of" is held to the end of the fight,
    which is what that power's own hold lasts; the Insight bonus is a
    check rather than a fight."""
    c.bonus(WILL, 1, on=c.me, until=When.ENCOUNTER)


@power("f3165", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with an attack on your turn",
       on=Trigger(Hit, lambda w, me, ev: ev.attacker == me,
                  "you hit with an attack"),
       dropped=("c.effects_on()",))
def f3165(c: Cast) -> None:
    """The regeneration plays. "While you benefit from p2483" is the
    dropped half: reading somebody else's live effects by the row that
    laid them has no verb, and `c.suffering` only finds my own."""
    if c.turn_of() == c.me:
        c.regeneration(2, on=c.me, until=When.EONT)


#: The thirteen racial powers of `r33`, one per elemental
#: manifestation. A character takes one, so "your racial power" is
#: whichever of these it has -- the same list `general_g` keeps.
_R33 = (
    "p1766", "p1767", "p1769", "p1770", "p1828",
    "p10043", "p10044", "p10045", "p10046",
    "p14073", "p14074", "p14075", "p14076",
)


@power("f3167", level=1, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL,
       target=NO_TARGET,
       trigger="you would take typed damage",
       on=Trigger(DamageRolled, lambda w, me, ev: (
           ev.target == me and ev.dtype is not DamageType.UNTYPED
       ), "you would take damage of a type"))
def f3167(c: Cast) -> None:
    """`DamageRolled` is announced above the resistance block in
    `resolve.damage`, so resistance laid from an interrupt on it covers
    the triggering blow as well as the rest of the round.

    Re-read, and the marker was aimed at the wrong verb: nothing here
    is *spent* except the power point, which `c.spend_points` already
    took. "You have not yet expended your racial power" is a **read**,
    and `c.expended` is the read -- the rows this creature has used up.
    `r33` prints thirteen racial powers, one per manifestation, and a
    character takes one, so the condition is that none of the ones it
    knows is among them.

    The point has to be there too: `c.spend_points` returns what it
    actually took, and a pool at zero buys nothing.
    """
    spent = c.expended(on=c.me)
    if any(ref in spent for ref in _R33):
        return
    if not c.spend_points(1):
        return
    c.resist(5, c.trigger.dtype, on=c.me, until=When.SONT)


@power("f3168", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=AUGMENT)
def f3168(c: Cast) -> None:
    """Same shape as f3158: a keyword added to a named power and a
    clause bought with a point."""


@power("f3169", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p2482",
       on=Trigger(PowerUsed, _used("p2482"), "you use that power"),
       dropped=("c.extend_move()",))
def f3169(c: Cast) -> None:
    """The insubstantiality plays. Lengthening the teleport the power
    itself makes would have to reach inside that row, and `PowerUsed` is
    announced before its body runs."""
    c.insubstantial(on=c.me, until=When.EONT)


@power("f3174", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.regain_points()",))
def f3174(c: Cast) -> None:
    """Trades the hit points a racial power would restore for a power
    point. Points are spent and transferred and never handed back, so
    there is nothing to trade for."""


@power("f3175", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3175(c: Cast) -> None:
    """The saving-throw context carries the keywords of the row that laid
    the effect, so "against poison effects" is a real narrowing rather
    than a guess at a label."""
    me = c.me
    c.resist(5, DamageType.POISON, on=me, until=When.ENCOUNTER)
    c.bonus(
        "save", 2, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: Keyword.POISON in ctx.get("keywords", ()),
    )
