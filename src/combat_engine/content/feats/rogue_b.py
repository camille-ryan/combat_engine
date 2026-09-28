"""Rogue feats, the second batch.

`rogue.py` holds the first, and the split it describes runs through this
one twice as hard. **Twenty-three of these thirty-seven ride on the
class's extra damage or on a weapon the catalogue does not carry**, and
those are two different gaps that look alike from the outside.

**The extra damage announces nothing.** `cf:rogue-scoundrel-f4` pays out inside
a closure in `content/features/strikers.py` -- `extra_damage` latches
per turn in a dict and calls `c.damage(..., detail=label)` -- so there
is no moment at which a feat can offer to trade the payout, forgo a die
of it, or spend it a second time. Five rows here say `c.on_extra_damage()`
and three more say `c.extra_damage(applies=)`, which is the narrower
half: the *condition* on which the payout happens is the `applies=`
callable handed to that helper, and widening it ("even without combat
advantage", "on this racial power's target") is what four of these
feats print.

**The weapon gate is a ref, not a group, wherever the group is wider
than the card.** `chargen` carries ten weapons. A card reading "while
wielding a rapier" cannot be written as the `light blade` group, because
the dagger every rogue starts with is a light blade and is not a rapier
-- so the benefit would be paid in a fight the card never paid it in.
Those rows ask `Weapon.ref` instead, which is exact, and is inert on a
board until `chargen` grows a rapier. Where the group genuinely covers
the printed list -- bows and crossbows -- the group is used, which is
the reading `strikers._SNEAK_GROUPS` already settled on.

The style family is here too, and behaves as it does in `fighter_b.py`
and `ranger_b.py`: the `Associated Powers:` list resolves to refs, so
the clause is one `ev.power in ...` read, and the second benefit is
`c.as_basic`, filed under the window the card names.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    DamageType,
    Gear,
    Hit,
    Keyword,
    Miss,
    PowerUsed,
    Trigger,
    When,
    Window,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import AttackDeclared, PowerResolved
from combat_engine.engine.query import allies

from .styles import hit_with_one_of, used_one_of

#: Nothing announces that the class's extra damage was about to be paid.
#: `rogue.py` named it first and three other classes wait on it.
EXTRA = ("c.on_extra_damage()",)
#: The narrower half: *when* the extra damage applies is the `applies=`
#: callable closed over inside `strikers.extra_damage`, and a feat that
#: widens it has nothing to widen.
APPLIES = ("c.extra_damage(applies=)",)
#: **A standing clause and a triggered one on the same card.** The
#: dispatcher only reaches a no-action row when its declared trigger
#: fires, so a row that also has to be *true* from the start of the
#: fight -- "you can use this in place of a melee basic attack" is --
#: is never armed. Those rows keep the printed Trigger as text and
#: answer it with `c.watch`, the shape `p7419` already uses.
#: One weapon group standing in for another, for named rows only.
COUNTS_AS = ("c.counts_as(group=)",)
#: Nothing adds to the distance somebody else's shift covers.
EXTEND_SHIFT = ("c.extend_shift()",)

#: The two conditions f2369 narrows its save penalty to. Compared by
#: value, as `ranger_b.f2367` does -- the saving throw's context hands
#: over `Condition` members and the card names words.
_STUNNING = ("dazed", "stunned")

#: The printed weapons that `chargen` has no entry for. Asking by ref
#: keeps the row exact; see the module docstring for why the group is
#: not good enough.
_RAPIER = ("w:rapier",)
_SWORDS = ("w:longsword", "w:short-sword", "w:rapier")


def _holding(c: Cast, *groups: str) -> bool:
    """Is the caster holding one of these weapon groups, in either hand?

    The same helper `ranger_b.py` defines. Repeated rather than imported
    for the reason the class files are separate at all.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    ranged = [gear.ranged] if gear.ranged is not None else []
    return any(w.group in groups for w in (*gear.melee, *ranged))


def _holding_ref(c: Cast, *refs: str) -> bool:
    """The same question asked of the weapon itself rather than its group."""
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(w.ref in refs for w in gear.held)


def _martial(p, *, usage=None) -> bool:  # noqa: ANN001
    if p is None or Keyword.MARTIAL not in p.keywords:
        return False
    return usage is None or p.usage in usage


def _my_martial_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and _martial(get(ev.power))


def _my_martial_encounter_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and _martial(get(ev.power), usage=(ENCOUNTER,))


def _my_rogue_encounter_miss(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.cls == "rogue"
        and p.usage is ENCOUNTER
    )


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _i_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me


def _at_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.target == me


def _was_opportunity(ev: Any) -> bool:
    """`getattr`, because `resolve.attack` hangs `opportunity` on the
    outcome as a plain attribute rather than declaring it a field.

    Asked in the body rather than in the predicate for the same reason
    `fighter_b.f1971` asks it there: a declared trigger is matched
    against the event class and its fields, and a gate on an attribute
    the dataclass does not carry belongs on the other side of the offer.
    """
    return bool(getattr(ev, "opportunity", False))


def _slip_away(c: Cast, squares: int) -> None:
    """"Shift N squares and make a Stealth check to become hidden."

    The DC is the best passive Perception in the room, which is the same
    number `cf:rogue-tactic-stealth` rolls against -- written the same
    way here so the two cannot disagree about what going unseen costs.
    """
    c.shift(squares)
    watching = [c.passive("perception", of=foe) for foe in c.enemies()]
    if c.check("stealth", max(watching) if watching else 10):
        c.hide()


# -- the rows that play -----------------------------------------------------


@power("f2075", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2075(c: Cast) -> None:
    """Charisma on two skills, as a feat bonus after the errata.

    Not `out_of_combat`: `skills.modifier` reads a `skill:<name>`
    modifier like any other, so this is an ordinary standing bonus and
    an Athletics check inside a fight sees it.
    """
    for skill in ("acrobatics", "athletics"):
        c.bonus(f"skill:{skill}", c.cha_mod, on=c.me, until=When.ENCOUNTER,
                kind="feat")


@power("f820", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.extend_move()",),
       trigger="an opportunity attack hits you while you are moving",
       on=Trigger(Hit, _at_me, "you are hit"))
def f820(c: Cast) -> None:
    """Being caught on the way out makes you faster.

    Untyped and `stacks=True` by default, which is the printed
    "cumulative if you are hit multiple times" and the only reason the
    bonus is left unkinded. `When.EOT` rather than the printed "for that
    move": the move in flight has already had its budget measured, so
    what is dropped is the retroactive half and what plays is the rest
    of the turn.
    """
    if _was_opportunity(c.trigger):
        c.bonus("speed", 1, on=c.me, until=When.EOT)


@power("f2077", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with a rogue encounter attack",
       on=Trigger(Miss, _my_rogue_encounter_miss, "you miss"))
def f2077(c: Cast) -> None:
    """Consolation damage on a miss.

    `c.flat` rather than `c.damage`, because the printed number is a
    modifier and not dice -- and a flat number is not maxed by anything.
    """
    if _holding_ref(c, *_RAPIER):
        c.flat(c.cha_mod, on=c.trigger.target)


@power("f2380", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit")
def f2380(c: Cast) -> None:
    """A crit leaves the target open; `p4477` stands in for the melee
    basic on an opportunity attack. Only `p4477` of the printed pair is
    heroic, so the list is one long here."""
    if not _holding_ref(c, *_SWORDS):
        return
    c.as_basic("p4477", window="opportunity")

    def on_crit(ev: Any) -> None:
        if _i_crit(c.world, c.me, ev) and _holding_ref(c, *_SWORDS):
            c.grants_advantage(on=ev.target, until=When.EONT)

    c.watch(Hit, on_crit, on=c.me, until=When.ENCOUNTER)


@power("f2451", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an opportunity attack, or one misses you",
       on=(Trigger(Hit, _i_hit, "you hit"),
           Trigger(Miss, _at_me, "an attack misses you")))
def f2451(c: Cast) -> None:
    """Two printed triggers, so two declared ones -- and the creature
    that grants the advantage is on the other end of the swing in each
    case, which is what the branch picks out."""
    ev = c.trigger
    if not _was_opportunity(ev):
        return
    c.grants_advantage(
        on=ev.target if isinstance(ev, Hit) else ev.attacker, until=When.EONT
    )


@power("f2350", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a martial encounter power")
def f2350(c: Cast) -> None:
    """"Any ally, while adjacent to you", so the adjacency is asked per
    attack: the ally walks in and out of it while the bonus stands."""
    me = c.me
    gear = c.world.get(me, Gear)
    if gear is None or not any(
        w.group in ("axe", "hammer", "mace") and "versatile" in w.properties
        for w in gear.melee
    ):
        return
    c.as_basic("p4488", "p2284", window="opportunity")

    def on_hit(ev: Any) -> None:
        if not _my_martial_encounter_hit(c.world, me, ev):
            return
        for friend in [a for a in allies(c.world, me) if a != me]:
            c.bonus(
                AC, 2, on=friend, until=When.EONT, kind="feat",
                when=lambda ctx, f=friend: c.adjacent_to(f, me),
            )

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f2369", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a martial power, or use an associated power",
       on=(Trigger(Hit, _my_martial_hit, "you hit with a martial power"),
           Trigger(PowerUsed, used_one_of("p10769", "p1387"),
                   "you attack with an associated power")))
def f2369(c: Cast) -> None:
    """Both printed benefits, and they answer different events.

    The save penalty is narrowed by the saving throw's own context,
    which carries the conditions the effect holds -- the same reading
    `ranger_b.f2367` uses.

    The rattling half is laid on `PowerUsed`, which fires *before* the
    body: `c.rattling` is a modifier `c.damage` reads beside the header,
    so it has to be standing by the time the blow lands. `When.EOT`
    rather than the instant, because there is no duration shorter than
    the turn and the row is the only attack being made inside it.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None or not any(
        w.group in ("hammer", "flail", "mace") and not w.two_handed
        for w in gear.melee
    ):
        return
    if isinstance(c.trigger, PowerUsed):
        c.rattling(on=c.me, until=When.EOT)
        return
    c.penalty(
        "save", 2, on=c.trigger.target, until=When.EONT,
        when=lambda ctx: any(
            str(x.value) in _STUNNING for x in ctx.get("conditions", ())
        ),
    )


@power("f2388", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a martial power, or use an associated power",
       on=(Trigger(Hit, _my_martial_hit, "you hit with a martial power"),
           Trigger(PowerUsed, used_one_of("p982"),
                   "you attack with an associated power")))
def f2388(c: Cast) -> None:
    """A Perception penalty, and a vanishing act before the shot.

    `skill:perception` is a modifier key `skills.modifier` reads, so the
    first benefit is an ordinary penalty rather than a narrative one --
    and it is what a passive Perception is measured from, which is the
    number the second benefit rolls against.

    "Before the attack" is only sayable on `PowerUsed`, which is
    announced above the body.
    """
    if not _holding(c, "bow", "crossbow"):
        return
    if isinstance(c.trigger, PowerUsed):
        _slip_away(c, 2)
        return
    c.penalty("skill:perception", 2, on=c.trigger.target, until=When.EONT)


@power("f2362", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=EXTEND_SHIFT,
       trigger="you attack with an associated power",
       on=Trigger(PowerResolved, lambda w, me, ev: (
           ev.actor == me and ev.power == "p4488"
       ), "you attack with an associated power"))
def f2362(c: Cast) -> None:
    """"**After** the attack", so `PowerResolved` and not `PowerUsed`.

    The two are the same row's bookends and picking the wrong one puts
    the shift on the far side of the swing from where the card prints
    it. The other benefit -- every shift this turn is a square longer --
    is dropped: nothing reaches into the distance another row's shift
    covers, which `ranger_b.f2361` named first.
    """
    if _holding(c, "light blade"):
        _slip_away(c, 2)


@power("f2338", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.as_ranged(ref)", "c.counts_as(group=)"),
       trigger="you attack with a bow or a crossbow",
       on=Trigger(AttackDeclared, lambda w, me, ev: ev.attacker == me,
                  "you attack", window=Window.BEFORE))
def f2338(c: Cast) -> None:
    """No reprisal from the creature you are shooting at.

    Declared `BEFORE`, for the reason `ranger_b.f2337` is: the
    provocation happens as the shot is taken, and an `AFTER` window
    hands over the exemption once the reprisal has been made.
    `from_=` names the one creature the card exempts, which is not the
    same as not provoking at all.

    The second benefit is two clauses and both are gaps: turning a named
    melee row into a ranged one for this use, and letting a crossbow
    stand in for the light blade it asks for.
    """
    if _holding(c, "bow", "crossbow"):
        c.no_provoke(from_=c.trigger.target, on=c.me, until=When.EOT)


# -- the extra damage, which announces nothing ------------------------------


def _extra(ref: str, what: str, *, wants: tuple[str, ...] = EXTRA) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=wants)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = what


_extra("f809", """Trades combat advantage to every enemy for a bigger
       payout. Nothing announces that the payout is about to happen, so
       there is no moment at which to offer the trade.""")
_extra("f813", """A save penalty on whatever condition the blow applied,
       but only when the blow paid the extra damage. `c.penalty("save")`
       and the saving throw's `conditions` context say the second half
       exactly -- see f2369 -- and the first half is unaskable, so the
       whole row waits rather than firing on every mace hit.""")
_extra("f818", """A second helping of the extra damage after an action
       point. `ActionPointSpent` is a real event and `Hit.action_point`
       is set beside it; what is missing is the once-a-turn latch, which
       lives in a dict inside `strikers.extra_damage`.""")
_extra("f952", """Forgoes one die of the extra damage to lay an attack
       penalty. Needs the announcement and a way to take a die back out
       of a roll another row is making.""",
       wants=("c.on_extra_damage()", "c.forgo_damage()"))
_extra("f1661", """Rerolls the low dice of the extra damage when a named
       racial power's necrotic rides along. `p8278` is a ref and not
       prose, so the naming is not the gap; the dice are rolled inside
       `c.damage` and are gone by the time anything sees them.""",
       wants=("c.on_extra_damage()", "c.reroll_ones()"))
_extra("f2076", """Pays the extra damage without combat advantage when
       you are the only creature beside the target. The condition is the
       `applies=` callable `strikers.extra_damage` closes over, and
       nothing widens it. The rapier half is writable -- see f2077 --
       and is not what holds this up.""", wants=APPLIES)
_extra("f2426", """Pays the extra damage on a named racial power's
       target, and off the once-a-turn latch. Both halves live inside
       that same closure.""", wants=("c.extra_damage(applies=)",
                                     "c.on_extra_damage()"))


# -- one weapon group standing in for another -------------------------------


def _counts_as(ref: str, what: str, *, wants: tuple[str, ...] = COUNTS_AS) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=wants)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = (
        f"{what} `c.as_implement` rewrites a weapon's group outright; the "
        "general form -- count as a light blade *for these rows only* -- "
        "has no verb. `rogue.py`'s f799 named it first."
    )


_counts_as("f821", """A mace where the rows ask for a light blade, at the
           cost of a die of the extra damage.""",
           wants=("c.counts_as(group=)", "c.change_dice()"))
_counts_as("f825", """An axe, a hammer or a pick where the rows ask for a
           light blade, at the cost of a die of the extra damage.""",
           wants=("c.counts_as(group=)", "c.change_dice()"))
_counts_as("f2078", """A one-handed heavy blade where the rows ask for a
           light blade, the extra damage included. The proficiency half
           is a column and not a body.""")
_counts_as("f2437", """A hammer where the rows ask for a light blade.""")
_counts_as("f2471", """A bow where the rows ask for a crossbow.""")
_counts_as("f2895", """A shortbow where the rows ask for a crossbow. The
           proficiency half is a column.""")


# -- the rest of the gaps, each named exactly -------------------------------


@power("f810", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.rattling(penalty=)",))
def f810(c: Cast) -> None:
    """Deepens the rattling penalty against `p1628`'s target. The
    trigger is sayable now the power is a ref; the penalty
    `Cast._rattle` applies is a fixed 2 with nothing to raise it, and
    the whole printed benefit is that number."""


@power("f2449", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p6189",
       on=Trigger(Hit, hit_with_one_of("p6189"), "you hit with it"))
def f2449(c: Cast) -> None:
    """"The enemy you hit" is the blow rather than the declaration, so
    this hangs on `Hit` and not on `PowerUsed` -- the racial power can
    miss."""
    c.grants_advantage(on=c.trigger.target, until=When.EONT)


@power("f819", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_reroll()",))
def f819(c: Cast) -> None:
    """Refunds `p1450` when the reroll it bought misses anyway. The power
    is named by ref and `c.restore_use` takes one -- what is missing is
    that nothing announces a roll was a reroll. The fighter's f805 is the
    same row from the other class."""


@power("f829", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f829(c: Cast) -> None:
    """`p1766` burns through fire resistance and immunity while you have
    combat advantage against its target.

    `advantage` is a key the damage context carries, asked of the board
    at damage time -- which is right for a standing grant and blind to a
    one-shot that the attack roll already spent. The narrower reading
    would need the rolled result threaded down to here."""
    c.ignore_resistance(
        None, DamageType.FIRE, on=c.me, until=When.ENCOUNTER, immunity=True,
        when=lambda ctx: ctx.get("power") == "p1766"
        and bool(ctx.get("advantage")),
    )


@power("f1775", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.triggering_attacker()",))
def f1775(c: Cast) -> None:
    """Combat advantage against whoever provoked `p2475`.

    The ref comes out of this feat's own prerequisite, so the naming is
    not the gap. `PowerUsed` says who used the row and which targets it
    chose, and `p2475` is an interrupt whose own trigger names the
    attacker -- that event is not carried anywhere the answering row can
    read it.
    """


@power("f826", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("Weapon.off_hand_anyway", "c.reload()"))
def f826(c: Cast) -> None:
    """A hand crossbow held in the off hand and reloaded one-handed.
    `Gear.off` is the second *melee* weapon by construction, so there is
    nowhere to put a shooter, and loading is not modelled at all -- which
    makes "have a loaded one in your off hand" unaskable and the free
    shot on a crit with it unreachable."""


@power("f2073", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("query.shield_bonus()",))
def f2073(c: Cast) -> None:
    """Raises the light shield's bonus by one. `Gear.shield` is a bool
    and the light-or-heavy number was folded into the defence totals at
    spawn, so there is neither a number to raise nor a way to tell which
    shield is being carried. The fighter's f1741 named it first."""


@power("f2074", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.shield_bonus()", "c.on_power_bonus()"))
def f2074(c: Cast) -> None:
    """Adds one to a power bonus to defences while a light shield is
    carried. Two gaps: which shield it is, and that a bonus being laid
    announces nothing a row can answer -- `Mods` records the number and
    its kind, not the act of granting it."""


@power("f2354", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("feat.associated_powers",))
def f2354(c: Cast) -> None:
    """The list is absent from the spec and present on the page: an
    errata block sits between the benefit and it, and `etl/feat._benefit`
    breaks at an errata heading and drops the rest of that paragraph. So
    `c.ignore_cover(partial=True)` is the whole of the benefit and has
    nowhere to aim. The fighter's `f2071` is cut off the same way."""


@power("f2405", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.counts_as(property=)", "Weapon.proficiency"))
def f2405(c: Cast) -> None:
    """The sling exists now; what does not is any way to rewrite the
    weapon a character is holding. Both clauses are that -- a better
    proficiency bonus and the high-crit property -- and `Weapon` is read
    off the item rather than off the wielder."""


@power("f2429", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.instead_of()",))
def f2429(c: Cast) -> None:
    """Shortens the distance `cf:rogue-scoundrel-f1s2` asks a move to
    cover. That row is declared, so the name is not the hold -- the 3 is
    a literal inside it and nothing rewrites one."""


@power("f2459", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTEND_SHIFT)
def f2459(c: Cast) -> None:
    """Every shift is a square longer, at the price of combat advantage.
    A shift is taken inside the granting row's body with its distance
    already decided; `c.forces` lengthens a push and there is no twin of
    it for a shift. `ranger_b.f2361` and f2362 above want the same
    verb."""


@power("f2468", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.advantage_on_roll()",))
def f2468(c: Cast) -> None:
    """Roll two Stealth checks and keep the better after using `p1217`.
    The trigger is a ref and `skills.check` rolls one die with no way to
    ask for two -- `c.reroll_check` answers a check already made, which
    is a different and worse bargain."""


@power("f2890", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.feint()", "c.change_dice()"))
def f2890(c: Cast) -> None:
    """Feinting with Bluff, and a bigger payout against whoever fell for
    it. Both halves are gaps: there is no feint in the action menu to
    put a bonus on, and the extra die is inside `strikers.extra_damage`
    as a dice string rather than a count."""
