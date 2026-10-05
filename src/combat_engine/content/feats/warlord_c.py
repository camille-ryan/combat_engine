"""Warlord feats, the third batch.

Three things decide whether a row here is writable.

**Inspiring word is `p1590` and the spec names it.** Four rows ride on
it and three of them are ordinary: `PowerUsed` fires before the body,
so a rider can lay concealment or hand out extra hit points and the
word's own heal lands on top. `f822` marked the healing half
`c.bonus(healing)` because it wanted to *add to* the amount; a second
`c.heal` is the same number against a capped pool, so `f2797` and
`f2434` are written rather than marked.

**Combat Leader is `cf:warlord-marshal-f3` in `features/leaders_sc.py`,
and it gives +2.** So "the bonus increases to +3" is one more point,
and `f2413` copies the feature's own shielding-build exclusion rather
than inventing a second version of the question.

**"Whenever you grant an ally an attack" is still the warlord's one big
hole.** A granted swing is announced as the row it is, not as a grant.
Two rows here wait on `c.on_granted_basic()` beside `f797`.

One thing that was thought to be a gap is not. **Standing up announces
itself**: the stand action ends the prone effect with `why="stood up"`,
so `ConditionEnded` separates getting up on purpose from an effect
expiring. `f2713` writes the clause `fighter_b.f1322` dropped as
`c.provokes_on_stand()`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    FREE,
    NO_TARGET,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionPointSpent,
    ActionType,
    Cast,
    Condition,
    ConditionEnded,
    ForcedMove,
    Gear,
    Hit,
    InitiativeRolled,
    Keyword,
    Moved,
    PowerUsed,
    Trigger,
    TurnStart,
    When,
    power,
)
from combat_engine.engine.basic import BEAST, MELEE, RANGED
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies, distance_between, enemies
from combat_engine.engine.types import Forced

#: A class feature named in prose with no ref. Nine rows wait on it.
FEATURE = ("c.class_feature()",)
#: A racial power named in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: The thirteen racial powers of `r33`, one per elemental
#: manifestation. A character takes one of them, so a rider printed for
#: two of the thirteen can only ever meet the one this character has.
R33 = (
    "p1766", "p1767", "p1769", "p1770", "p1828",
    "p10043", "p10044", "p10045", "p10046",
    "p14073", "p14074", "p14075", "p14076",
)
#: **A standing clause and a triggered one on the same card.** The
#: dispatcher only reaches a no-action row when its declared trigger
#: fires, so a row that also has to be *true* from the start of the
#: fight -- "you can use this in place of a melee basic attack" is --
#: is never armed. Those rows keep the printed Trigger as text and
#: answer it with `c.watch`, the shape `p7419` already uses.
#: …nor turn a melee row into a ranged one.
AS_RANGED = ("c.recast(reach=)",)
#: The basic attacks. A grant hands over whichever of these the
#: creature's own is, so "you grant an ally a basic attack" is the ref
#: being one of them.
BASICS = (MELEE, RANGED, BEAST)

#: Inspiring word, named by ref in three of these prerequisites.
WORD = "p1590"

#: The conditions f2365 and f2368 narrow themselves to.
_HELD = ("immobilized", "restrained", "slowed")
_STUNNING = ("dazed", "stunned")


def _grip(c: Cast, *groups: str, hands: int) -> bool:
    """One of those groups, held in that many hands."""
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(
        w.group in groups and w.two_handed == (hands == 2) for w in gear.melee
    )


def _holding(c: Cast, *groups: str) -> bool:
    """One of those groups, in either grip."""
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.group in groups for w in gear.melee)


def _versatile(c: Cast, *groups: str) -> bool:
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(
        w.group in groups and "versatile" in w.properties for w in gear.melee
    )


def _i_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _my_point(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me


def _ally_point(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    from combat_engine.engine.query import team

    return ev.actor != me and team(world, ev.actor) == team(world, me)


def _my_word(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == WORD


def _my_push(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.source == me and ev.how is Forced.PUSH


def _martial(ref: str) -> bool:
    p = get(ref)
    return p is not None and Keyword.MARTIAL in p.keywords


def _led(c: Cast) -> list[int]:
    """The allies Combat Leader reaches -- within 10 and able to see me,
    which is how `cf:warlord-marshal-f3` asks it."""
    me = c.me
    return [
        a for a in allies(c.world, me)
        if a != me and distance_between(c.world, me, a) <= 10 and c.can_see(a)
    ]


def _ranged_or_area(ctx: dict[str, Any]) -> bool:
    """"Ranged or area attacks". The attack context carries `ranged`;
    an area row has to be asked of its own range line."""
    if ctx.get("ranged", False):
        return True
    p = get(ctx.get("power", ""))
    return p is not None and p.reach.kind.startswith("area")


# -- the style feats, now that the associated lists resolve -----------------


@power("f2357", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you hit an enemy",
       on=Trigger(Hit, _i_hit, "you hit"))
def f2357(c: Cast) -> None:
    """Both printed benefits pay out on a hit, so they are one trigger
    with two branches rather than a trait and a rider: a row declared
    `on=` never lays a standing modifier."""
    if not _grip(c, "polearm", "spear", hands=2):
        return
    c.bonus(AC, 1, on=c.me, until=When.EONT, kind="feat")
    if c.trigger.power in ("p2562", "p158"):
        c.push(2, on=c.trigger.target)


@power("f2365", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("resolve.ctx.conditions",))
def f2365(c: Cast) -> None:
    """The substitution plays. The defence bonus does not: it is
    against attacks that would immobilize, restrain or slow, and the
    attack context says who is swinging, with what and from where, and
    nothing about what the row would *do* on a hit. The saving-throw
    context carries `conditions`; the attack context does not."""
    if _grip(c, "axe", "hammer", "pick", hands=2):
        c.as_basic("p1413", "p2331", window="opportunity")


@power("f2368", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you hit an enemy",
       on=Trigger(Hit, _i_hit, "you hit"))
def f2368(c: Cast) -> None:
    """The save penalty is narrowed to two conditions, which the saving
    throw's context carries -- a blanket penalty would be worth several
    times the printed line."""
    if not _grip(c, "hammer", "flail", "mace", hands=1):
        return
    ev = c.trigger
    if _martial(ev.power):
        c.penalty(
            "save", 2, on=ev.target, until=When.EONT,
            when=lambda ctx: any(
                str(x.value) in _STUNNING for x in ctx.get("conditions", ())
            ),
        )
    if ev.power in ("p158", "p4568"):
        c.prone(on=ev.target)


@power("f2372", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2372(c: Cast) -> None:
    """Takes the combat-advantage bonus away from adjacent enemies.

    Written as a penalty that cancels it rather than as a suppression:
    combat advantage is worked out inside `resolve.attack` and reaches
    the modifiers only as the `advantage` key, so that is where it is
    answered.
    """
    me = c.me
    if not _versatile(c, "heavy blade"):
        return
    c.as_basic("p2562", "p1556", window="opportunity")
    for foe in enemies(c.world, me):
        c.penalty(
            "attack", 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: (
                ctx.get("advantage", False)
                and ctx.get("target") == me
                and c.adjacent(to=f)
            ),
        )


@power("f2377", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2377(c: Cast) -> None:
    """19-20 on a charge. `crit_range` is read with the attack context,
    so "whenever you charge" is a gate rather than a second row."""
    if _grip(c, "hammer", "mace", hands=2):
        c.as_basic("p4568", "p1065", window="charge")
    c.bonus(
        "crit_range", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("charge", False) and _grip(c, "hammer", "mace", hands=2)
        ),
    )


@power("f2385", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a martial power")
def f2385(c: Cast) -> None:
    """Punishes the target for shifting: a watch on the creature rather
    than a modifier, because the payment happens on a *move* and
    `Moved.kind_` is what tells a shift from a walk. `once=True` --
    "it takes damage" is one payment, not one per square.

    The substitution names no window, so it answers the charge, the
    opportunity attack and the defender's swing alike."""
    if not _holding(c, "flail"):
        return
    c.as_basic("p2562", "p1556")

    def on_hit(ev: Any) -> None:
        if not _i_hit(c.world, c.me, ev) or not _martial(ev.power):
            return
        foe, hurt = ev.target, c.wis_mod

        def on_shift(moved: Any) -> None:
            if moved.actor == foe and getattr(moved, "kind_", "") == "shift":
                c.flat(hurt, on=foe)

        c.watch(Moved, on_shift, on=foe, until=When.EONT, once=True)

    c.watch(Hit, on_hit, on=c.me, until=When.ENCOUNTER)


@power("f2710", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2710(c: Cast) -> None:
    """"Against attacks from enemies adjacent to you" is two adjacency
    questions, and both are askable: the ally's is asked of the board
    and the attacker's off `ctx["attacker"]`, which `query.defence` is
    handed along with everything else."""
    me = c.me
    if _grip(c, "pick", "spear", hands=1):
        c.as_basic("p4568", "p1065", window="opportunity")
    for friend in [a for a in allies(c.world, me) if a != me]:
        for d in (AC, REF):
            c.bonus(
                d, 2, on=friend, until=When.ENCOUNTER, kind="feat",
                when=lambda ctx, f=friend: (
                    _grip(c, "pick", "spear", hands=1)
                    and c.adjacent_to(f, me)
                    and ctx.get("attacker") is not None
                    and c.adjacent(to=ctx["attacker"])
                ),
            )


@power("f2711", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you push an enemy, or hit with an associated power",
       on=(Trigger(ForcedMove, _my_push, "you push an enemy"),
           Trigger(Hit, _i_hit, "you hit")))
def f2711(c: Cast) -> None:
    """Two printed clauses, two events. The advantage half turns on the
    push itself rather than on a hit, because a hit knows nothing about
    whether anybody moved -- and the push this row's own second clause
    makes is a push like any other, so the two chain as printed."""
    if not _holding(c, "polearm"):
        return
    ev = c.trigger
    if isinstance(ev, ForcedMove):
        c.grants_advantage(on=ev.target, until=When.EONT)
    elif ev.power in ("p158", "p2331"):
        c.push(2, on=ev.target)


@power("f2713", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=AS_RANGED,
       trigger="you score a critical hit with a one-handed axe",
       on=Trigger(Hit, _i_crit, "you crit"))
def f2713(c: Cast) -> None:
    """Prone, and a swing at it when it gets back up.

    The fighter's f1322 dropped the second half as
    `c.provokes_on_stand()`, and it need not be: the stand action ends
    the prone effect with `why="stood up"`, so `ConditionEnded`
    separates getting up on purpose from an effect expiring, and
    `c.provoke` opens the window. `once=True` is "the first time".

    What is dropped is casting an associated row at range: reach is
    header data the menu reads before anything runs.
    """
    if not _grip(c, "axe", hands=1):
        return
    me, foe = c.me, c.trigger.target
    c.prone(on=foe)

    def stood(ev: Any) -> None:
        if (
            ev.target == foe
            and ev.condition is Condition.PRONE
            and ev.why == "stood up"
        ):
            c.provoke(me, on=foe, why=c.ref)

    c.watch(ConditionEnded, stood, on=foe, until=When.EONT, once=True)


@power("f2716", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2716(c: Cast) -> None:
    """The list reaches the spec now -- the errata heading that
    `etl/feat._benefit` used to break at no longer swallows it -- so this
    is `f2377`'s shape with the two refs as the gate in place of the
    charge. `crit_range` is read with the attack context, which carries
    the power and so can tell the associated rows from the rest."""
    c.bonus(
        "crit_range", 1, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("power") in ("p10935", "p158")
            and _grip(c, "heavy blade", hands=2)
        ),
    )


# -- inspiring word, which is a ref -----------------------------------------


@power("f2407", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, trigger="you use p1590",
       on=Trigger(PowerUsed, _my_word, "you use inspiring word"))
def f2407(c: Cast) -> None:
    """"Either ... or" is a real choice, so `c.choose` makes it rather
    than the row picking a half. `PowerUsed.targets` is a list even
    though the word aims at one."""
    pick = c.choose(["attack", "defences"], "the inspiring word rider")
    for who in c.trigger.targets:
        if pick == "attack":
            c.bonus(
                "attack", 1, on=who, until=When.EONT, when=_ranged_or_area
            )
        else:
            for d in (AC, FORT, REF, WILL):
                c.bonus(d, 1, on=who, until=When.EONT, when=_ranged_or_area)


@power("f2416", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, trigger="you use p1590",
       on=Trigger(PowerUsed, _my_word, "you use inspiring word"))
def f2416(c: Cast) -> None:
    for who in c.trigger.targets:
        c.conceal(on=who, until=When.EONT)


@power("f2797", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, trigger="you use p1590",
       on=Trigger(PowerUsed, _my_word, "you use inspiring word"))
def f2797(c: Cast) -> None:
    """A second `c.heal` rather than an addition to the word's own.
    `PowerUsed` fires before the body, so this lands first -- and against
    a pool that caps at maximum the order does not change the total,
    which is why this is written and not marked."""
    for who in c.trigger.targets:
        c.heal(c.int_mod, on=who)


@power("f2434", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2434(c: Cast) -> None:
    """"An enemy you have hit during this turn" is a memory, so this is a
    trait with three watches rather than a declared trigger: one to
    remember the hits, one to forget them when my turn comes round
    again, and one to pay out when the word is used."""
    me = c.me
    struck: set[int] = set()

    def remember(ev: Any) -> None:
        if ev.attacker == me:
            struck.add(ev.target)

    def forget(ev: Any) -> None:
        if ev.actor == me:
            struck.clear()

    def paid(ev: Any) -> None:
        if ev.actor != me or ev.power != WORD:
            return
        for who in ev.targets:
            if any(c.adjacent_to(foe, who) for foe in struck):
                c.heal(c.str_mod, on=who)

    c.watch(Hit, remember, on=me, until=When.ENCOUNTER)
    c.watch(TurnStart, forget, on=me, until=When.ENCOUNTER)
    c.watch(PowerUsed, paid, on=me, until=When.ENCOUNTER)


# -- Combat Leader, and the rest of the board -------------------------------


@power("f2413", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you roll initiative",
       on=Trigger(InitiativeRolled, lambda w, me, ev: ev.actor == me,
                  "you roll initiative"))
def f2413(c: Cast) -> None:
    """+2 becomes +3, so this is the one extra point and not a whole
    bonus. Declared on the roll like `f2062`, because a trait is armed
    after initiative has been taken. The shielding build gives the
    feature up, and the exclusion is copied from the feature rather than
    restated, so the two cannot disagree about who has it."""
    if c.build("shielding"):
        return
    c.initiative(1, on=c.me)
    for friend in _led(c):
        c.initiative(1, on=friend)


@power("f2393", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2393(c: Cast) -> None:
    """The long-range penalty is 2 and `c.ignores_long_range` hands
    exactly 2 back. The five-square reach is measured when the fight
    starts rather than per shot, because the waiver is an effect on the
    ally and there is no gate on the shooter's neighbours."""
    me = c.me
    c.ignores_long_range(on=me, until=When.ENCOUNTER)
    for friend in allies(c.world, me):
        if friend != me and distance_between(c.world, me, friend) <= 5:
            c.ignores_long_range(on=friend, until=When.ENCOUNTER)


@power("f2477", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2477(c: Cast) -> None:
    """"Starts his or her turn within 5 squares", so the set is asked
    again every turn and the row is a watch rather than a standing list.
    `query.speed` is handed `{"charge": True}` by the three places that
    measure a charge's run, which is what makes "when charging" a gate
    instead of a bonus to all movement."""
    me = c.me

    def started(ev: Any) -> None:
        who = ev.actor
        if (
            who != me
            and who in allies(c.world, me)
            and distance_between(c.world, me, who) <= 5
        ):
            c.bonus(
                "speed", 2, on=who, until=When.EOT, kind="feat",
                when=lambda ctx: ctx.get("charge", False),
            )

    c.watch(TurnStart, started, on=me, until=When.ENCOUNTER)


@power("f2431", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally who can see you spends an action point to attack",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f2431(c: Cast) -> None:
    """A plain "+1 bonus", so untyped, and spent on the first roll --
    "for that attack" is one swing, not a standing modifier."""
    who = c.trigger.actor
    if c.can_see(who):
        c.bonus("attack", 1, on=who, until=When.EONT, once=True)


@power("f2414", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a r33 racial power",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and ev.power in R33
       ), "you hit with your racial power"))
def f2414(c: Cast) -> None:
    """The feat names two of the race's powers and both are refs now --
    `p1766` and one the spec gives only as a word. Widened to the race's
    thirteen, which costs nothing: a character has one manifestation and
    so one of the thirteen, and the gate requires it be one of the two
    this card is printed for."""
    me, foe = c.me, c.trigger.target
    for friend in [a for a in allies(c.world, me) if a != me]:
        c.bonus(
            "attack", 2, on=friend, until=When.EONT,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power("f2466", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you use p1770 or p1828",
       on=(Trigger(PowerUsed, lambda w, me, ev: (
               ev.actor == me and ev.power == "p1770"
           ), "you use p1770"),
           Trigger(PowerUsed, lambda w, me, ev: (
               ev.actor == me and ev.power == "p1828"
           ), "you use p1828")))
def f2466(c: Cast) -> None:
    """Both racial powers are refs here, so the whole row plays."""
    me = c.me
    for friend in allies(c.world, me):
        if friend != me and distance_between(c.world, me, friend) <= 5:
            c.bonus("speed", 2, on=friend, until=When.EONT)


# -- the rest, each gap named -----------------------------------------------


@power("f2396", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("chargen.armor_proficiency()", "c.max_surges()"))
def f2396(c: Cast) -> None:
    """Armour proficiency and one more healing surge. Proficiency is a
    chargen column nothing writes to from a row, and `Health` counts
    surges spent against a maximum that no verb moves."""


def _my_grant(c: Cast, ev: Any, *refs: str) -> bool:
    """Is this use a swing *I* handed an ally, with one of these rows?

    `granted_by` is set for a self-grant too -- a defender punishing an
    opening hands itself a swing -- so the ally test is separate and is
    the printed "an ally".
    """
    return (
        ev.granted_by == c.me
        and ev.actor != c.me
        and ev.power in refs
    )


@power("f2423", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2423(c: Cast) -> None:
    """A ranged basic the warlord hands over ignores cover.

    Laid on the ally the moment the grant is announced -- `PowerUsed`
    comes before the body, so the waiver is standing by the time the
    shot is rolled -- and gated on the grant so it cannot be spent by an
    ordinary shot the ally takes later in the same turn.

    `partial=True` is the printed parenthetical: superior cover and
    total concealment still stand.
    """
    def granted(ev: Any) -> None:
        if not _my_grant(c, ev, RANGED):
            return
        c.ignore_cover(
            on=ev.actor, until=When.EOT, partial=True,
            when=lambda ctx: ctx.get("granted_by") == c.me,
        )

    c.watch(PowerUsed, granted, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} granted shot")


@power("f2436", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2436(c: Cast) -> None:
    """A damage bonus on a granted basic against an enemy beside you.

    The adjacency is judged when the grant is made, which is the printed
    "against an enemy that is adjacent to you" -- the enemy can be
    pushed out of reach by the swing itself. A one-shot, so it pays for
    the granted blow and not for whatever the ally does next.

    No type word is printed, so it is untyped.
    """
    def granted(ev: Any) -> None:
        if not _my_grant(c, ev, *BASICS):
            return
        if not any(c.adjacent(foe) for foe in ev.targets):
            return
        c.bonus(
            "damage", 2, on=ev.actor, until=When.EOT, once=True,
            when=lambda ctx: ctx.get("granted_by") == c.me,
        )

    c.watch(PowerUsed, granted, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} granted swing")


@power("f2424", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_granted_shift()",))
def f2424(c: Cast) -> None:
    """Allies ignore difficult terrain during a shift one of your powers
    let them make. `c.ignores_difficult` says the benefit; what is
    missing is knowing that a row granted a shift, which is a fact about
    somebody else's body and not about any event."""


@power("f2430", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.instead_of()",))
def f2430(c: Cast) -> None:
    """Lets an ally trade the all-defences bonus `cf:warlord-marshal-f4s1`
    gives for a bigger one on a single defence. That row is declared, so
    the name is not the hold: the bonus is laid from inside it and
    nothing hands one back."""


@power("f2435", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p1448",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and ev.power == "p1448"
       ), "you hit with your racial power"))
def f2435(c: Cast) -> None:
    """`f2414` with one power instead of two and damage instead of
    attack. The damage context carries `target`, which is the whole gate
    the sentence needs; the bonus is untyped, the card printing no word
    in front of it."""
    me, foe = c.me, c.trigger.target
    for friend in [a for a in allies(c.world, me) if a != me]:
        c.bonus(
            "damage", 5, on=friend, until=When.EONT,
            when=lambda ctx: ctx.get("target") == foe,
        )


@power("f2463", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.boost_roll()",))
def f2463(c: Cast) -> None:
    """Re-aimed three times over. `c.expend_row` spends a row from
    outside it, and a level-11 monster wave declared `m4421a6`, so there
    is now something to spend.

    The remaining hold is the boost itself: `c.boost_check` reaches a
    skill check and neither an attack roll nor a saving throw, which are
    the two this row is printed to improve."""
