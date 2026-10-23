"""General feats, the `f3477`-`f3561` band: the racial riders that hang off
one named power, the staff and quarterstaff run, a long stretch of
perception and concealment feats, two channel divinity pairs and the mount
pair.

Five shapes account for nearly all of it.

**"When you use `pNNNN`".** Most of the racial rows here are a rider on one
named power, and which event they hang off is the whole of the work.
`PowerUsed` is announced *above* the body, so it is right for "during the
move" and "before making the attack" and wrong for everything that reads a
consequence -- those take `PowerResolved`. Where the named power is printed
in prose rather than by ref there is nothing to match and the row is
marked.

**Combat advantage is a relation, not a modifier.** It cannot be laid as a
standing `when=` gate, so the four rows reading "you gain combat advantage
against a creature that ..." watch `AttackDeclared` at `Window.BEFORE` --
the last moment still early enough, since `resolve.attack` asks
`has_combat_advantage` inside the resolve callback -- and lay a one-shot
grant on the creature actually being swung at.

**Concealment is a modifier and cover is traced.** `c.conceal` lays the
first and `query._carried_cover` reads a plain `"cover"` bonus for the
second, but that one is read with an empty context, so "partial cover
against ranged attacks" cannot be narrowed and is `c.cover_from()`.

**A triggered `action=NONE` row spends a use every time it fires**, so the
standing riders here are `AT_WILL`. The two immediate-action rows that
expend another power are `ENCOUNTER`, which is the nearest the engine has
to the cost their card actually prints.

**Weapon groups are a closed set**: axe, bow, crossbow, heavy blade,
implement, light blade, mace, spear, staff, unarmed. Quarterstaff is
`"staff"` and is written; the zadatl and the rod are not groups the engine
carries and are `spec.weapon_ref()`.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    ANY_FACE,
    AREA_OR_CLOSE,
    AT_WILL,
    DAILY,
    DEX,
    ENCOUNTER,
    EVERY_DIE,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    STR,
    WILL,
    WIS,
    ActionType,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    ConditionEnded,
    DamageRolled,
    DamageType,
    Dropped,
    Escaped,
    ForcedMove,
    Gear,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    PowerResolved,
    PowerUsed,
    Relation,
    SecondWind,
    Size,
    SurgeSpent,
    Swap,
    Target,
    Trigger,
    TurnEnd,
    Usage,
    When,
    Window,
    World,
    about_me,
    by_me,
    distance,
    get,
    power,
    targets_me,
)
from combat_engine.engine.components import Position, Powers
from combat_engine.engine.query import concealment_of, creatures, is_, team, unseen_by

#: **Retired.** It read `c.class_feature()` -- "a class feature the benefit
#: names in prose, with no `cf:` ref to read" -- and both halves of that are
#: false for all four rows that carried it, `f3531` to `f3534`. The clause
#: each one dropped is "if you are in `f3529`", and the ETL resolves it: a
#: **feat** ref, not a feature named in prose, and `f3529b` below is the power
#: `f3529` grants, declared and fully written. Nothing is unresolved and no
#: reader is missing.
#:
#: What is in the way is the **tier**. `f3529`'s own gate is `level>=11` and
#: it replaces one of the `r44` aspect options, so the clause is reachable
#: only at paragon -- the same band in which those four rows already leave
#: their 11th- and 21st-level damage steps, and an out-of-tier clause carries
#: no marker here. So the four are finished and nothing waits on this symbol.
#:
#: Kept as a comment rather than deleted because `#577` group 1 still reads
#: it the old way: that triage predates the ETL resolving the name to `f3529`,
#: and the `c.in_form()`-or-a-sibling decision it proposes is moot. The
#: `i1942` pair that shared this symbol was always a different gap and is now
#: on `c.on_defiling()`, where five other rows already wait.
#: A racial power named by its race rather than by a ref.
RACIAL_POWER = ("c.on_racial_power()",)
#: **Retired.** It read `c.manifestation()` -- "which of this racial trait's
#: several modes is the character in now", wanted by `f3530` for `rt:r44-t2`
#: and by `f1521` and `f602` for `rt:r33-t0`. All three premises were false
#: and in the same way: a race that offers a choice of modes offers a choice
#: of **powers**, `RaceLine.one_of` says which races do, and
#: `RaceLine.granted` puts the one taken in `Powers.known`. So the mode is
#: recorded, by ref, in the place the compendium's own prerequisite lines read
#: it from, and `features/racial._holds` is the reader this symbol was filed
#: for. `rt:r33-t0` forks thirteen ways on it and `rt:r44-t2` is `_inert`
#: because the power *is* the whole of the aspect.
#:
#: The three rows are written or re-pointed. Kept as a comment rather than
#: deleted so the next reader meets the correction: the symbol argued that
#: a mode is in-fight state where a race option is build-time, and for both
#: of these races it is build-time.
#: The three racial powers of `r44`, which the page offers as a choice.
R44 = ("p7441", "p7442", "p7443")
#: A power traded for another at build time.
SWAP = ("chargen.power_swap()",)
#: Which weapons a character may pick up is settled when it is built.
PROFICIENCY = ("chargen.proficiency()",)
#: **Retired.** It read "a printed weapon the engine has no group and no
#: ref for", and the engine has both: the weapon these three rows require
#: is `w3739`, a superior polearm with a group, a category, a price and a
#: place in `chargen.PRINTED`, so a character can be dealt one. The three
#: rows now declare the Requirement they were dropping. Kept as a comment
#: rather than deleted so the next reader meets the correction.


def _wields_w3739(world: World, eid: int) -> bool:
    """The printed Requirement of `f3485b`, `f3486b` and `f3487b`.

    **Matched on the ref, not the slug**, which keeps the printed name out
    of this file altogether. `query.holding` would answer the same
    question by slug -- a weapon type is deliberately sayable here -- but
    the ref says it with no name at all, and `c.wielding` cannot be used:
    it tests property, group and category and excludes the slug on
    purpose, so asking it would pass any superior polearm.
    """
    from combat_engine.engine.components import Gear

    gear = world.get(eid, Gear)
    return any(w.ref == "w3739" for w in (gear.held if gear is not None else ()))
#: Spending a use of another row as the price of this one.
EXPEND = ("c.expend_row()",)
#: Suppressing a clause of the power that triggered this one.
INSTEAD = ("c.pre_empt(ref, clause)",)

#: The four an rt:r33-s2 rider narrows on.
ELEMENTS = (
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)
#: What "ends the dazed, slowed, stunned or weakened condition" names.
SHAKEABLE = (
    Condition.DAZED,
    Condition.SLOWED,
    Condition.STUNNED,
    Condition.WEAKENED,
)

DIVINE = [Keyword.DIVINE]


# -- small shared questions -------------------------------------------------


def _at(world: Any, eid: int) -> tuple[int, int]:
    pos = world.get(eid, Position)
    return pos.square if pos is not None else (0, 0)


def _groups(world: Any, eid: int) -> set[str]:
    gear = world.get(eid, Gear)
    return {w.group for w in gear.held} if gear is not None else set()


def _holding_ref(c: Cast, *refs: str) -> bool:
    """Is one of these exact things in hand?

    By **ref**, which is the only way to name one kind of implement: all
    eight share `group="implement"` and have to, because `dsl.usable` reads
    that group to mean "not something you can hit anybody with". #517.
    """
    from combat_engine.engine.components import Gear

    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.ref in refs for w in gear.held)


def _keyword(ref: str, word: Keyword) -> bool:
    p = get(ref)
    return p is not None and word in p.keywords


def _used(ref: str):  # noqa: ANN202
    """`PowerUsed`/`PowerResolved`: this creature used that row."""

    def when(world: Any, me: int, ev: Any) -> bool:
        return ev.actor == me and ev.power == ref

    return when


def _used_any(*refs: str):  # noqa: ANN202
    """"A <race> racial power", where the race prints more than one."""

    def when(world: Any, me: int, ev: Any) -> bool:
        return ev.actor == me and ev.power in refs

    return when


def _shape(ref: str) -> str:
    p = get(ref)
    return p.reach.kind if p is not None and p.reach is not None else ""


def _hit_with(ref: str):  # noqa: ANN202
    def when(world: Any, me: int, ev: Any) -> bool:
        return ev.attacker == me and ev.power == ref

    return when


def _free_beside(c: Cast, who: int) -> tuple[int, int] | None:
    """An empty square next to that creature, for a teleport that names one."""
    grid = c.world.grid
    x, y = _at(c.world, who)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            sq = (x + dx, y + dy)
            if (dx or dy) and grid.passable(sq) and grid.occupant(sq) is None:
                return sq
    return None


def _step_toward(c: Cast, who: int, n: int) -> tuple[int, int] | None:
    """The nearest free square within `n` that is closer to that creature."""
    grid = c.world.grid
    here = _at(c.world, c.me)
    there = _at(c.world, who)
    best: tuple[int, int] | None = None
    for dx in range(-n, n + 1):
        for dy in range(-n, n + 1):
            sq = (here[0] + dx, here[1] + dy)
            if sq == here or not grid.passable(sq) or grid.occupant(sq) is not None:
                continue
            if distance(sq, there) >= distance(here, there):
                continue
            if best is None or distance(sq, there) < distance(best, there):
                best = sq
    return best


def _burst(c: Cast, n: int) -> list[tuple[int, int]]:
    x, y = _at(c.world, c.me)
    return [
        (x + dx, y + dy)
        for dx in range(-n, n + 1)
        for dy in range(-n, n + 1)
        if c.world.grid.inside((x + dx, y + dy))
    ]


def _advantage_when(c: Cast, ok) -> None:  # noqa: ANN001
    """"You gain combat advantage against a creature that ..."

    Combat advantage is a relation between two creatures rather than a
    modifier, so there is no standing gate to lay: it has to be put on a
    named creature. `AttackDeclared` at `Window.BEFORE` is the last moment
    still early enough -- `resolve.attack` asks `has_combat_advantage`
    inside the resolve callback, after that window has closed -- and
    `once=True` spends the grant on the roll it was laid for.
    """
    me = c.me

    def declared(ev: Any) -> None:
        if ev.attacker == me and ok(ev):
            c.grants_advantage(on=ev.target, to=me, until=When.EOT, once=True)

    c.watch(AttackDeclared, declared, until=When.ENCOUNTER, window=Window.BEFORE)


def _grants(ref: str, card: str):  # noqa: ANN202
    """The parent half of a feat whose whole benefit is the card beside it."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


# -- the goliath band: p4809, p11738 and the toughness riders ---------------


def _ally_winded(world: Any, me: int, ev: Any) -> bool:
    """Any ally but you. The printed limit is adjacency to the spirit
    companion, which the body measures."""
    who = getattr(ev, "actor", None)
    return (who is not None and who != me
            and team(world, who) is team(world, me))


@power("f3477", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3477(c: Cast) -> None:
    """A standing modifier and a triggered one on one card, so the row is a
    trait and the second half is a `c.watch`. `query.speed` is handed
    `{"charge": True}` by the three places that measure a charge's run and
    nothing by everything else, which is what makes the speed gate say what
    the card says. The damage bonus is scoped to the turn `p4809` is used
    rather than gated on its ref: the swing a charge power grants is a
    basic attack, so the damage context names that and not the row that
    sent it."""
    me = c.me
    c.bonus("speed", 1, kind="racial", on=me, until=When.ENCOUNTER,
            when=lambda ctx: bool(ctx.get("charge")))

    def charged(ev: Any) -> None:
        if ev.actor == me and ev.power == "p4809":
            c.bonus("damage", c.con_mod, kind="power", on=me, until=When.EOT,
                    when=lambda ctx: bool(ctx.get("charge")))

    c.watch(PowerUsed, charged, until=When.ENCOUNTER)


@power("f3478", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p11738",
       on=Trigger(PowerResolved, _used("p11738"), "you use p11738"))
def f3478(c: Cast) -> None:
    """The mark lands after the power has finished, because a creature the
    power itself pushes out of reach is not adjacent when the marking
    happens -- and `PowerUsed` fires above the body."""
    for foe in c.within(1, side="enemy"):
        c.mark(on=foe, until=When.EONT)


@power("f3479", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3479(c: Cast) -> None:
    """"While you have maximum hit points" is a fact about the roller and
    not a key the damage context carries, so the gate asks the board each
    time it is read rather than reading `ctx`. Untyped: the card prints no
    word in front of "bonus"."""
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.missing(on=c.me) == 0)


@power("f3480", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an ally uses second wind while adjacent to your spirit companion",
       on=Trigger(SecondWind, _ally_winded, "an ally takes a second wind"))
def f3480(c: Cast) -> None:
    """The printed distance is to the spirit rather than to you, which is
    why the predicate lets every ally through and the body measures."""
    spirit = c.companion()
    who = c.trigger.actor
    if spirit is None or not c.adjacent_to(spirit, who):
        return
    held = [x for x in (Condition.DAZED, Condition.SLOWED, Condition.WEAKENED)
            if c.is_(x, on=who)]
    picked = c.choose(held) if held else None
    if picked is not None:
        c.cure(picked, on=who)


@power("f3481", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3481(c: Cast) -> None:
    """`Effects.save` ends a beaten effect with `why="saved"`, which is the
    only place that word is written, so "with a save" is readable off
    `ConditionEnded` and does not need the saving throw itself."""
    me = c.me

    def ended(ev: Any) -> None:
        if ev.target == me and ev.condition in SHAKEABLE and ev.why == "saved":
            c.bonus("attack", 1, on=me, until=When.EONT, once=True)

    c.watch(ConditionEnded, ended, until=When.ENCOUNTER)


def _proned_me(world: Any, me: int, ev: Any) -> bool:
    return ev.target == me and ev.condition is Condition.PRONE


@power("f3482", level=1, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=SELF,
       trigger="an effect knocks you prone or pushes, pulls or slides you",
       on=(
           Trigger(ForcedMove, targets_me, "you are pushed, pulled or slid"),
           Trigger(ConditionApplied, _proned_me, "you are knocked prone",
                   window=Window.AFTER),
       ))
def f3482(c: Cast) -> None:
    """Two printed triggers, and only one of them is refusable.
    `ForcedMove` is a `Decision` and `c.cancel` is the printed "you ignore
    the forced movement". `ConditionApplied` is a notification, so "remain
    standing" cannot be interrupted -- the trigger is declared at
    `Window.AFTER` and the row stands the creature back up instead, which
    is the same board a heartbeat later.

    `AT_WILL` now that `c.expend_row` charges the printed price: the
    limit is `p11738`'s single use and not a second one on this row,
    and the interrupt is refused outright when there is nothing left to
    spend -- which is the card's Requirement."""
    if not c.expend_row("p11738"):
        return
    ev = c.trigger
    if isinstance(ev, ForcedMove):
        c.cancel()
    else:
        c.cure(Condition.PRONE, on=c.me)


def _immobilised(world: Any, eid: int) -> bool:
    return is_(world, eid, Condition.IMMOBILIZED)


@power("f3483", level=1, cls="", usage=AT_WILL, action=FREE,
       reach=PERSONAL, target=SELF,
       requires=_immobilised, requires_text="you must be immobilized")
def f3483(c: Cast) -> None:
    """`AT_WILL` for the same reason as `f3482`: the printed cost is a
    use of `p11738` and `c.expend_row` charges it, so the cap belongs to
    that row rather than to a stand-in on this one. The `requires=` gate
    is what "an immobilizing effect on you" means for a row that is
    offered rather than triggered -- without it the policy takes a free
    action every turn to cure nothing."""
    if not c.expend_row("p11738"):
        return
    c.cure(Condition.IMMOBILIZED, on=c.me)


@power("f3484", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p5032",
       on=Trigger(PowerResolved, _used("p5032"), "you use p5032"))
def f3484(c: Cast) -> None:
    """"Until the end of your turn" is `When.EOT` measured from the wild
    shape, which is why this answers the resolved use rather than the
    declaration.

    `c.expend_row` is both the price and the choice: it spends the use
    and returns False when there is none left, so the `c.may` that stood
    in for it -- which charged nothing -- is gone."""
    if c.expend_row("p11738"):
        c.bonus("damage", c.con_mod, kind="power", on=c.me, until=When.EOT)


# -- the zadatl swaps -------------------------------------------------------


@power("f3485", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, swap=Swap(3, Usage.ENCOUNTER))
def f3485(c: Cast) -> None:
    """An encounter attack power traded for `f3485b`.

    The body hands the card over; `chargen` takes the one that
    goes back."""
    c.grant_row("f3485b", on=c.me, until=When.ENCOUNTER)


@power("f3485b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=Target(side="enemy", count=1, max_size=Size.LARGE),
       keywords=[Keyword.MARTIAL, Keyword.WEAPON],
       attack=Attack((STR, DEX), vs=REF),
       requires=_wields_w3739,
       requires_text="it must be wielding the printed weapon")
def f3485b(c: Cast) -> None:
    """"Strength or Dexterity" is the header after all: `Attack.ability`
    takes a tuple and `ability_for` answers `max(..., key=stats.mod)`,
    which is what "whichever is better" means on a line the user picks at
    the moment of use. The damage still reads `c.attack_mod` -- whatever
    the declared branch actually swung with -- rather than naming one of
    the two twice. The Requirement names a weapon the engine has no group
    and no ref for. The secondary attack answers `Escaped`, and the watch
    ends with the grab it is about rather than running for the
    encounter."""
    if not c.strike():
        return
    c.damage(c.w(2), c.attack_mod)
    c.grab()
    me, foe = c.me, c.target

    def broke(ev: Escaped) -> None:
        if ev.holder != me or ev.actor != foe or not ev.success:
            return
        # The secondary line prints the same pair of abilities as the
        # primary, and both are full attack bonuses, so the better of the
        # two is the printed choice.
        if c.attack(max(c.str_, c.dex_), FORT, on=foe):
            c.damage(c.w(1), c.attack_mod, on=foe)

    c.watch(Escaped, broke, until=When.ENCOUNTER, on=me, once=True)


@power("f3486", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, swap=Swap(6, utility=True))
def f3486(c: Cast) -> None:
    """A 6th-level or higher utility traded for `f3486b`.

    The body hands the card over; `chargen` takes the one that
    goes back."""
    c.grant_row("f3486b", on=c.me, until=When.ENCOUNTER)


@power("f3486b", level=1, cls="", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.MARTIAL, Keyword.STANCE], requires=_wields_w3739,
       requires_text="it must be wielding the printed weapon")
def f3486b(c: Cast) -> None:
    """The stance is the hold and the grab is a watch on what the stance
    makes possible. `When.STANCE` is the duration the watch takes, so it
    dies with the stance rather than on a turn boundary."""
    me = c.me
    c.stance(label=c.ref)

    def struck(ev: Any) -> None:
        p = get(ev.power)
        if (
            ev.attacker == me
            and p is not None
            and p.usage.name == "AT_WILL"
            and Keyword.WEAPON in p.keywords
            and c.may("grab the target", who=me)
        ):
            c.grab(on=ev.target)

    c.watch(Hit, struck, until=When.STANCE)


@power("f3487", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, swap=Swap(9, Usage.DAILY))
def f3487(c: Cast) -> None:
    """A 9th-level or higher daily attack traded for `f3487b`.

    The body hands the card over; `chargen` takes the one that
    goes back."""
    c.grant_row("f3487b", on=c.me, until=When.ENCOUNTER)


@power("f3487b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE,
       keywords=[Keyword.MARTIAL, Keyword.WEAPON, Keyword.RELIABLE],
       attack=Attack((STR, DEX), vs=REF),
       requires=_wields_w3739,
       requires_text="it must be wielding the printed weapon")
def f3487b(c: Cast) -> None:
    """"Miss: this power is not expended" is the reliable keyword and is
    declared in the header rather than written in the body. The -2 to
    escape is a penalty on the grabbed creature's own check; the slide
    that follows the grabber is a watch on `Moved`, which is the only
    event carrying both ends of a step.

    "Strength or Dexterity" is the header, as `f3485b` above: `Attack`
    takes a tuple of abilities and `ability_for` answers the better
    modifier, which is what a choice made at the moment of use means."""
    if not c.strike():
        return
    c.damage(c.w(3), c.attack_mod)
    foe = c.target
    if foe is None:
        return
    c.grab(on=foe)
    c.penalty("escape", 2, on=foe, until=When.ENCOUNTER)
    me = c.me

    def broke(ev: Escaped) -> None:
        if ev.holder != me or ev.actor != foe or not ev.success:
            return
        if c.attack(max(c.str_, c.dex_), FORT, on=foe):
            c.damage(c.w(2), c.attack_mod, on=foe)
            c.prone(on=foe)

    c.watch(Escaped, broke, until=When.ENCOUNTER, on=me, once=True)

    def stepped(ev: Any) -> None:
        if ev.actor == me and foe in c.grabbing(of=me):
            c.slide(max(1, distance(ev.from_, ev.to)), on=foe)

    c.watch(Moved, stepped, until=When.ENCOUNTER)


# -- the genasi band --------------------------------------------------------


@power("f3488", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p10043",
       on=Trigger(PowerUsed, _used("p10043"), "you use p10043"))
def f3488(c: Cast) -> None:
    """"During the move" is the one thing `PowerUsed` firing above the body
    is exactly right for: the waiver has to be standing before the move the
    body makes."""
    c.ignore_condition(
        Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED,
        on=c.me, until=When.EOT,
    )


@power("f3489", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you knock a creature prone with p1767",
       on=Trigger(PowerResolved, _used("p1767"), "you use p1767"))
def f3489(c: Cast) -> None:
    """`ConditionApplied` names no power, so "knocked prone **with
    p1767**" is asked of the resolved use and the board it left: the
    targets that are down are the ones it put down."""
    for foe in c.trigger.targets:
        if is_(c.world, foe, Condition.PRONE):
            c.condition(Condition.REMOVED, on=foe, until=When.SOTNT)


@power("f3490", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p10044",
       on=Trigger(PowerResolved, _used("p10044"), "you use p10044"))
def f3490(c: Cast) -> None:
    """The penalty is laid on each adjacent enemy and gated on the damage
    being aimed back at the caster, because "against you" is a narrowing of
    the roll and not of who carries it."""
    me = c.me
    c.cure(Condition.GRABBED, on=me)
    c.immune(Condition.GRABBED, on=me, until=When.EONT)
    for foe in c.within(1, side="enemy"):
        c.penalty("damage", 5, on=foe, until=When.EONT,
                  when=lambda ctx: ctx.get("target") == me)


@power("f3491", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3491(c: Cast) -> None:
    """Another row's Target line cannot be rewritten, but `c.use_power`
    aims it: the widened power is `p1766` used once more per adjacent
    enemy the triggering use left out, at no action and spending nothing,
    which is one attack roll each exactly as a two-target line would be.

    The guard is the whole of the difficulty -- each extra use announces
    its own `PowerResolved`, which is this watch's own trigger."""
    me = c.me
    busy: list[bool] = []

    def widen(ev: Any) -> None:
        if busy or ev.actor != me or ev.power != "p1766":
            return
        busy.append(True)
        already = set(ev.targets)
        for foe in c.within(1, side="enemy"):
            if foe not in already:
                c.use_power("p1766", on=foe, spend=False, again=True)
        busy.clear()

    c.watch(PowerResolved, widen, until=When.ENCOUNTER, label=f"{c.ref} widen")


@power("f3492", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with p1767",
       on=Trigger(Hit, _hit_with("p1767"), "you hit with p1767"))
def f3492(c: Cast) -> None:
    c.push(2, on=c.trigger.target)


@power("f3493", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p1770",
       on=Trigger(PowerUsed, _used("p1770"), "you use p1770"))
def f3493(c: Cast) -> None:
    """`f3488` on a different power, and the same reason for `PowerUsed`."""
    c.ignore_condition(
        Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED,
        on=c.me, until=When.EOT,
    )


@power("f3494", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p10045",
       on=Trigger(PowerResolved, _used("p10045"), "you use p10045"))
def f3494(c: Cast) -> None:
    """"While adjacent to you" is geometry rather than a duration, so this
    is an aura with `c.grants_in` hung on it: the penalty arrives when a
    creature steps in and goes when it leaves, which a plain `c.penalty`
    on today's neighbours cannot say. Untyped, as a penalty always is."""
    aura = c.aura(1, label=c.ref, on=c.me, until=When.EONT)
    for defence in (AC, FORT, REF, WILL):
        c.grants_in(aura, defence, -2, side="enemy", kind="untyped")


@power("f3495", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p1769",
       on=Trigger(PowerResolved, _used("p1769"), "you use p1769"))
def f3495(c: Cast) -> None:
    """The teleport names its square, so the row looks for an empty one
    beside the creature struck rather than handing a distance to the
    world's decider -- "to a square adjacent to that creature" is a
    destination, not a range."""
    me = c.me

    def struck(ev: Any) -> None:
        p = get(ev.power)
        if ev.attacker != me or p is None:
            return
        if not ({Keyword.LIGHTNING, Keyword.THUNDER} & set(p.keywords)):
            return
        sq = _free_beside(c, ev.target)
        if sq is not None and c.may("teleport beside the target", who=me):
            c.teleport(20, to=sq)

    c.watch(Hit, struck, until=When.EONT)


@power("f3496", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p1828",
       on=Trigger(PowerUsed, _used("p1828"), "you use p1828"))
def f3496(c: Cast) -> None:
    """The waiver has to stand before the flight, so `PowerUsed`.

    **Narrowed to the flying**, which is all the card waives. The window says how
    the creature travelled now -- `ctx["mode"]` is `movement.mode_of`'s answer --
    so walking out of reach still provokes as it should. It used to cover every
    kind of going (#301)."""
    c.no_provoke(on=c.me, until=When.EOT,
                 when=lambda ctx: ctx.get("mode") == "fly")


# -- staves ------------------------------------------------------------------


def _divine_staff_melee(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and Keyword.DIVINE in p.keywords
        and Keyword.WEAPON in p.keywords
        and p.reach.kind == "melee"
        and "staff" in _groups(world, me)
    )


@power("f3497", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3497(c: Cast) -> None:
    """"The first ... during an encounter" is a flag the trait keeps, not
    an `ENCOUNTER` usage: this row has no printed trigger and is armed
    once, so spending it would take the whole trait away."""
    me = c.me
    spent = False

    def declared(ev: Any) -> None:
        nonlocal spent
        if spent or not _divine_staff_melee(c.world, me, ev):
            return
        spent = True
        c.grants_advantage(on=ev.target, to=me, until=When.EOT, once=True)

    c.watch(AttackDeclared, declared, until=When.ENCOUNTER, window=Window.BEFORE)


@power("f3498", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a divine melee weapon attack using a staff",
       on=Trigger(Hit, _divine_staff_melee, "you hit with a staff"))
def f3498(c: Cast) -> None:
    c.shift(1)


def _staff_p12710(world: Any, me: int, ev: Any) -> bool:
    return (
        ev.attacker == me
        and ev.power == "p12710"
        and "staff" in _groups(world, me)
    )


@power("f3499", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with p12710 using a staff",
       on=Trigger(Hit, _staff_p12710, "you hit with p12710 using a staff"))
def f3499(c: Cast) -> None:
    c.dazed(on=c.trigger.target, until=When.EONT)


@power("f3500", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       
       proficiency=("w3601",))
def f3500(c: Cast) -> None:
    """A quarterstaff where the rogue rows ask for a light blade.

    One waiver answers all three places the old note listed:
    `cf:rogue-scoundrel-f4`'s `requires=` asks for a light blade, a
    crossbow or a sling and is checked through `c.wielding`; so is every
    rogue power printing the same line. Waiving it once covers them.

    By slug rather than by group -- a quarterstaff's group is `staff`, and
    waiving the whole staff group would let a card naming any other staff
    through as well.
    """
    c.counts_as("light blade", holding="quarterstaff")
def _proned_by_me(world: Any, me: int, ev: Any) -> bool:
    return (
        ev.source == me
        and ev.condition is Condition.PRONE
        and "staff" in _groups(world, me)
    )


@power("f3501", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       )
def f3501(c: Cast) -> None:
    """A standing weapon property and a triggered shift, so this is a trait
    with a watch and **not** a declared trigger.

    **That is not a style choice.** `content/CLAUDE.md`: "a row holds either
    a printed trigger **or** standing modifiers, not both: declared `on=`,
    the body runs only when the trigger fires, so modifiers laid there are
    never laid." The first version of this change left the `on=Trigger` in
    place and put `c.gains_property` at the top of the body -- which lays
    the property only on a turn the knockdown happens, and raised on
    `c.trigger.target` the moment anything called the body without one.
    `feats/fighter_c.py`'s header records the same conversion for ten rows
    of this shape.

    "Larger than you" is read off `Position.size` at the moment of the
    knockdown, and that half plays.

    **"Using a staff" is answered by `ConditionApplied.weapon`** (#653).
    `ConditionApplied.power` was added for the four rows printing the
    *keyword* or the *shape* of the clause -- `f1871` and `f3276` read it --
    and the ref of the row cannot say which weapon swung it. `c.condition`
    stamps the weapon from the `Cast` that laid the hold, which is the only
    thing that knows.

    **A group, not a ref**, because the card says "a staff" and not one
    staff: the knockdown counts if the weapon the hold came through is in
    the `staff` group, which is the same read `_close_arcane_staff` below
    makes for this row's sibling.

    **Wielding the quarterstaff as a small weapon is written now**, and
    `c.counts_as(property=)` was the wrong verb for it: that one waives a
    printed Requirement and changes no weapon, where this changes the
    weapon. `small` is a real entry in the `properties` column and
    `c.gains_property` is the writer. `w3601` is the quarterstaff and its
    group is `staff`. #676."""
    c.gains_property("small", group="staff", on=c.me)
    me = c.me
    order = list(Size)

    def knocked(ev: Any) -> None:
        if not _proned_by_me(c.world, me, ev):
            return
        swung = getattr(ev, "weapon", "")
        if not swung or swung not in _staves(c.world, me):
            return
        foe = ev.target
        if order.index(c.size_of(on=foe)) > order.index(c.size_of(on=me)):
            c.shift(1)

    c.watch(ConditionApplied, knocked, on=me, until=When.ENCOUNTER)


def _staves(world: Any, me: int) -> set[str]:
    """The refs of the staves this creature is holding.

    `ConditionApplied.weapon` is a ref and the card says "a staff", so the
    comparison is against the group rather than against one weapon --
    `_groups` below is the same read `_close_arcane_staff` makes.
    """
    from combat_engine.engine import Gear

    gear = world.get(me, Gear)
    if gear is None:
        return set()
    return {w.ref for w in gear.weapons if (w.group or "") == "staff"}


def _close_arcane_staff(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    return (
        ev.actor == me
        and p is not None
        and Keyword.ARCANE in p.keywords
        and p.reach.kind in ("close_burst", "close_blast")
        and "staff" in _groups(world, me)
    )


@power("f3502", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a close arcane attack with a staff",
       on=Trigger(PowerUsed, _close_arcane_staff, "you use a close arcane attack"))
def f3502(c: Cast) -> None:
    """"Before making the attack" is `PowerUsed`, which is announced above
    the body. The slide is anchored on the caster's own square so the
    creature stays beside it, which is the printed destination."""
    beside = c.within(1, side="any")
    if not beside:
        return
    who = c.choose(beside, "slide one adjacent creature")
    if who is not None:
        c.slide(1, on=who, anchor=_at(c.world, c.me))


# -- halfling second chance -------------------------------------------------


def _triggering_attacker(ev: Any) -> int | None:
    """Who threw the blow the triggering power was used to answer.

    `PowerUsed`/`PowerResolved` carry `trigger` -- the event the power
    was used *in answer to* -- and `p1452` is declared on `Hit`, so the
    creature that swung is `ev.trigger.attacker`. The marker that stood
    on both rows below wanted a method for a field the event has."""
    hit = getattr(ev, "trigger", None)
    return getattr(hit, "attacker", None)


@power("f3503", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p1452 while bloodied",
       on=Trigger(PowerResolved, _used("p1452"), "you use p1452"))
def f3503(c: Cast) -> None:
    """`to="team"` is the printed "you and your allies"; `"ally"` would
    leave the caster out."""
    who = _triggering_attacker(c.trigger)
    if who is not None and c.bloodied(on=c.me):
        c.grants_advantage(on=who, to="team", until=When.EONT)


@power("f3504", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p1452 while bloodied",
       on=Trigger(PowerResolved, _used("p1452"), "you use p1452"))
def f3504(c: Cast) -> None:
    """Untyped, and one bonus of the right size rather than a +2 and a
    gated +2: `c.reroll_attack` writes `result.hit` back onto the
    `AttackResult` riding on the triggering `Hit`, so whether the attack
    still hits is settled by the time `p1452` resolves and the number can
    simply be chosen."""
    if not c.bloodied(on=c.me):
        return
    hit = getattr(c.trigger, "trigger", None)
    result = getattr(hit, "result", None)
    c.bonus("damage", 4 if result is not None and result.hit else 2,
            on=c.me, until=When.EONT)


@power("f3507", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("query.knocked_prone()",))
def f3507(c: Cast) -> None:
    """The racial row is `rt:r2-t4`, a declared ref, and
    `c.reroll_save` is the printed "twice, and use the better" -- neither
    is the hold. The hold is that the trait's prone half is itself
    dropped on the same symbol: `ConditionApplied` says who applied a
    condition and not whether an *attack* did, so no saving throw against
    falling prone is ever rolled and there is none to roll twice.

    The Special is a treaty and carries nothing."""


# -- wardens ----------------------------------------------------------------


def _f3508_step(using: Cast) -> None:
    """Two squares closer to the target, instead of `p5094`'s slide.

    "Closer to the target" is a destination rather than a distance. The
    target comes off the using row's own target list -- the watcher this
    replaces had to dig it out of a `PowerUsed` event.
    """
    aimed = using.target if using.target is not None else (
        using.targets[0] if using.targets else None
    )
    if aimed is None:
        return
    sq = _step_toward(using, aimed, 2)
    if sq is not None:
        using.teleport(2, to=sq)


@power("f3508", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,)
def f3508(c: Cast) -> None:
    """Steps toward the target instead of `p5094`'s slide.

    **Rewritten from a watcher**, which slid *and* teleported.
    """
    c.pre_empt("p5094", "slide", _f3508_step)
@power("f3509", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3509(c: Cast) -> None:
    """`Effects.save` builds its context with `keywords_of(eff.label)`, so
    "against charm effects" is a gate on the row that laid the effect and
    needs nothing new."""
    me = c.me
    for skill in ("nature", "perception", "streetwise"):
        c.bonus(f"skill:{skill}", 1, kind="feat", on=me, until=When.ENCOUNTER)
    c.bonus("save", 2, kind="feat", on=me, until=When.ENCOUNTER,
            when=lambda ctx: Keyword.CHARM in ctx.get("keywords", ()))


@power("f3510", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f3510(c: Cast) -> None:
    """Two ends and the earlier wins: the concealment holds to the start
    of your next turn, and the first attack you declare drops it."""
    hidden = c.conceal(on=c.me, until=When.SONT)

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == c.me and hidden is not None:
            c.world.effects.end(hidden, "you attacked")

    c.watch(AttackDeclared, swung, on=c.me, until=When.SONT)


@power("f3511", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use cf:warden-f2",
       on=Trigger(PowerResolved, _used("cf:warden-f2"), "you use cf:warden-f2"))
def f3511(c: Cast) -> None:
    """"Shift 1 square, swapping positions" is one move: `c.swap` moves
    both or neither, which is what keeps the marked enemy from being left
    standing in the caster's square."""
    for foe in c.within(1, side="enemy"):
        if c.marked(on=foe) and c.swap(foe):
            return


@power("f3512", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit an enemy with p5093",
       on=Trigger(Hit, _hit_with("p5093"), "you hit with p5093"))
def f3512(c: Cast) -> None:
    """"Instead of causing damage" is a hold on the blow and `Hit` is
    announced before the damage is rolled, so the hold is a one-shot
    watch on the `DamageRolled` that is still to come: that event is a
    `Decision` and `resolve.deal` returns 0 the moment it is cancelled.
    `detail` is the ref of the row being rolled, which is what keeps the
    cancellation on `p5093`'s own blow and off anything else the caster
    does this turn.

    The choice is three-way, not two: declining is leaving the damage
    alone, and `optional=True` puts it last so that a board with no
    decider takes the clause rather than skips it."""
    me = c.me
    foe = c.trigger.target
    pick = c.choose(["prone", "slide"], "prone or slide instead of damage",
                    optional=True, decline="deal the damage")
    if pick is None:
        return
    spent: list[bool] = []

    def forgo(rolled: Any) -> None:
        if spent or rolled.source != me or rolled.detail != "p5093":
            return
        spent.append(True)
        rolled.cancel()

    c.watch(DamageRolled, forgo, until=When.EOT, on=me,
            window=Window.BEFORE, label=f"{c.ref} forgo")
    if pick == "prone":
        c.prone(on=foe)
    else:
        c.slide(1, on=foe)


def _warden_encounter(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.cls == "warden"
        and p.usage.name == "ENCOUNTER"
        and p.attack is not None
    )


@power("f3513", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a warden encounter attack power",
       on=Trigger(Hit, _warden_encounter, "you hit with a warden encounter power"))
def f3513(c: Cast) -> None:
    """`c.no_cover` waives cover as well as concealment, which is wider
    than the card -- but a creature with traced cover and no concealment
    reads the larger of the two anyway, so the widening only bites where
    the cover is the bigger number. `partial=True` would be the narrower
    lie: it leaves total concealment standing, which the card removes."""
    c.no_cover(on=c.trigger.target, until=When.EONT)


# -- seeing, and not being seen ---------------------------------------------


@power("f3515", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3515(c: Cast) -> None:
    """`c.bonus("initiative", ...)` is read by nothing -- `Initiative.bonus`
    is summed before the d20 and `Mods` is never consulted. `c.initiative`
    moves the creature in the order, which is the only thing a trait armed
    after the opening rolls can do. The substitution is the difference
    between the two modifiers."""
    c.initiative(c.wis_mod - c.dex_mod, on=c.me)


@power("f3516", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3516(c: Cast) -> None:
    """The Perception penalty while blinded is a check the engine never
    rolls in a fight, and the bonus below is the part of the same sentence
    that is read. `c.no_advantage`'s gate is handed `attacker` and
    `target`, which is what narrows this to the creatures actually unseen."""
    me = c.me
    c.no_advantage(on=me, until=When.ENCOUNTER,
                   when=lambda ctx: unseen_by(c.world, me, ctx["attacker"]))
    c.bonus("skill:perception", 2, kind="feat", on=me, until=When.ENCOUNTER)


@power("f3517", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3517(c: Cast) -> None:
    """"Your melee attacks take no penalties due to partial concealment or
    total concealment."

    **Both halves of the sentence are sayable now.** The gate was always
    the easy one -- `not ctx.get("ranged")` is "melee". What could not be
    said was *concealment and not cover*: `cover_waived` answered one
    number for both, so this feat waived a wall too. `concealment_only=True`
    is the carve-out. #771.

    The card names partial **and** total concealment, which is the whole of
    it, so no `partial=` narrowing: that parameter is for the rows printing
    only the lesser one."""
    c.ignore_cover(on=c.me, until=When.ENCOUNTER, concealment_only=True,
                   when=lambda ctx: not ctx.get("ranged"))


@power("f3518", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3518(c: Cast) -> None:
    """"No creatures adjacent to them other than you" counts bodies rather
    than sides: an ally of the caster standing next to the enemy spoils it
    exactly as another enemy would."""
    me = c.me

    def alone(ev: Any) -> bool:
        there = _at(c.world, ev.target)
        return not any(
            other not in (me, ev.target)
            and distance(_at(c.world, other), there) <= 1
            for other in creatures(c.world)
        )

    _advantage_when(c, alone)


@power("f3520", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3520(c: Cast) -> None:
    """Concealment is a modifier the concealed creature carries, so "if you
    have partial concealment" is asked of the caster and not of the
    target. `_is_ranged` is private, so the shape of the attack is read off
    the row's own reach."""
    me = c.me

    def concealed_and_ranged(ev: Any) -> bool:
        p = get(ev.power)
        return (
            p is not None
            and p.reach.kind in ("ranged", "area_burst")
            and int(concealment_of(c.world, me)) > 0
        )

    _advantage_when(c, concealed_and_ranged)


@power("f3521", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3521(c: Cast) -> None:
    """Low-light vision, the whole benefit."""
    c.low_light()


@power("f3522", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3522(c: Cast) -> None:
    """A rod is not one of the ten weapon groups, so the attack bonus is
    narrowed to implement attacks -- which is the widest true statement --
    and the narrowing to the rod itself is the dropped half. Heroic tier,
    so +1. The shield bonus is printed as one and does not stack with a
    shield's own.

    The attack context carries the row's ref and not its keywords, so the
    gate looks the row up: `ctx["keywords"]` is a key only the *save*
    context has, and reading it here would be silently false."""
    me = c.me
    c.bonus("attack", 1, kind="feat", on=me, until=When.ENCOUNTER,
            when=lambda ctx: (_keyword(ctx.get("power", ""), Keyword.IMPLEMENT)
                              and _holding_ref(c, "w:rod")))
    # "When you hold a rod", not "when you hold an implement" -- the shield
    # bonus was keyed on the group, so an orb bought it too.
    if _holding_ref(c, "w:rod"):
        c.bonus(AC, 1, kind="shield", on=me, until=When.ENCOUNTER)
        c.bonus(REF, 1, kind="shield", on=me, until=When.ENCOUNTER)


@power("f3523", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3523(c: Cast) -> None:
    """The moment is the `Hit`'s interrupt window, and the critical is a
    field on the live `AttackResult` rather than a fact: `resolve.attack`
    recomputes the outcome from that object and `c.hit()` reads `c.crit` off
    the same one, so the event's own field has to be written too or the log
    and the damage disagree. f281b is the same demotion from a declared
    interrupt and `_next_blow_of_mine_crits` writes both fields the other
    way; this one is a standing watch because the card is not a choice.

    `result.hit` is left alone -- the attack is still a hit, which is what
    "a normal hit, not a critical hit" says, and touching it would make
    `resolve.attack` re-announce the outcome as a miss."""
    me = c.me

    def glancing(ev: Hit) -> None:
        if ev.target != me or not ev.critical or c.roll("1d20") < 10:
            return
        c.crit_becomes(False, ev=ev)

    c.watch(Hit, glancing, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
            label=f"{c.ref} glancing blow")


@power("f3524", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an enemy reduces you to 0 hit points or fewer",
       on=Trigger(Dropped, about_me, "you drop to 0 hit points"))
def f3524(c: Cast) -> None:
    """A death throe: `Triggers._offer` lets a creature answer its own
    downfall, which is why this can fire at all. `Dropped.source` is
    whoever struck the blow and is None for ongoing damage or a failed
    death save, which is the "with an attack" half of the sentence.
    Heroic tier, so 10."""
    who = c.trigger.source
    if who is not None:
        c.flat(10, dtype=DamageType.THUNDER, on=who)


@power("f3525", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3525(c: Cast) -> None:
    """`World.difficult` answers per creature, because a row that ignores
    rough going of one sort sees a different map -- so the question is
    asked of the creature standing in the square, not of the caster."""

    def in_the_rough(ev: Any) -> bool:
        return _at(c.world, ev.target) in c.world.difficult(ev.target)

    _advantage_when(c, in_the_rough)


@power("f3527", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3527(c: Cast) -> None:
    """Written: the read site takes a context now, so the narrowing is sayable.

    Two facts have to be true at once and they come from opposite places.
    **Where the holder is standing** is world state a closure reads with no
    context -- `Grid.difficult` is a dict of square to label, the same read
    `p16434` does against `Grid.blocking`. **What shape the attack is** is
    the attack's, and arrives as `ctx["ranged"]`, which
    `query.cover_between` now hands down to `_carried_cover`. Before that it
    was asked with `{}` and read false forever, which is why this clause sat
    marked while the skill half paid out. #644.

    `ctx.get`, not `ctx[...]`: the hide offer in `actions.py` has no attack
    to describe and passes nothing, and the right answer there is no carried
    cover rather than a raise.
    """
    me = c.me
    c.bonus("skill:acrobatics", 2, kind="feat", on=me, until=When.ENCOUNTER)
    c.bonus("skill:athletics", 2, kind="feat", on=me, until=When.ENCOUNTER)

    def ranged_while_in_rough(ctx: dict[str, Any]) -> bool:
        if not ctx.get("ranged"):
            return False
        here = c.world.get(me, Position)
        return here is not None and any(
            sq in c.world.grid.difficult for sq in here.squares
        )

    c.cover(on=me, until=When.ENCOUNTER, when=ranged_while_in_rough)


@power("f3528", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit a slowed or immobilized target",
       on=Trigger(Hit, by_me, "you hit a creature"))
def f3528(c: Cast) -> None:
    """The condition is asked in the body rather than in the predicate, so
    that the printed "you can" is offered only when there is something to
    offer -- a predicate answering it would be the same question a beat
    earlier and reads no better."""
    foe = c.trigger.target
    slowed = is_(c.world, foe, Condition.SLOWED)
    if (slowed or is_(c.world, foe, Condition.IMMOBILIZED)) and c.may(
        "knock the target prone", who=c.me
    ):
        c.prone(on=foe)


# -- the elemental aspect band ----------------------------------------------


def _elemental_blow(world: Any, me: int, ev: Any) -> bool:
    return ev.target == me and ev.dtype in ELEMENTS


@power("f3529b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=SELF,
       trigger="you are hit by an attack dealing cold, fire, lightning or thunder damage",
       on=Trigger(DamageRolled, _elemental_blow, "you are hit by elemental damage"))
def f3529b(c: Cast) -> None:
    """Declared on `DamageRolled` rather than on `Hit`: the damage type is
    what the printed trigger narrows on and `Hit` does not carry one.
    `DamageRolled` is a `Decision` announced before the hit points come
    off, which is the interrupt window "you take half damage" needs.

    The extra die is `c.bonus(dice=)`, rolled afresh each time it is
    read, and it takes the type off the triggering `DamageRolled` -- "the
    type or types dealt by the triggering attack" is exactly the field
    the trigger was declared on to read."""
    c.halve(c.trigger)
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.EONT, once=True,
            dtype=c.trigger.dtype)


@power("f3530", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.resist(once=)",))
def f3530(c: Cast) -> None:
    """**Re-pointed off `ASPECT`, whose premise was false twice over.**
    This said "whenever you choose an aspect of nature" had no moment,
    because `rt:r44-t2` is refused in play and nothing records which
    aspect was chosen. That row is not refused -- it is `_inert`, and its
    own note says why: `RaceLine.one_of` holds for `r44`, so
    `RaceLine.granted` deals exactly one of the three aspects and the
    choice is recorded in `Powers.known`. `f3304` reads it from there and
    carries no marker for it. Re-choosing is an extended-rest rule that
    no fight reaches, so the choosing is the moment this row is armed.

    What is left is the one gap the marker still names: resistance
    **spent by the first hit that reads it**. The printed line is resist
    5 for the *next* attack that hits and deals that type; laying it for
    the encounter instead is a row stronger than its card, so nothing is
    written rather than half of it.

    `c.bonus(once=)` is not that flag forwarded. `c.resist`'s gated path
    lays a `"resist <type>"` mod, which is neither a `Defense` nor
    `damage`, `save`, `skill`, `crit_range` nor `forced` -- and since
    `drivers.once_spend_moments`, a key with no spend moment **raises**
    rather than being quietly handed to the attack roll. So it now fails
    loudly where it used to spend the resistance on the resisting
    creature's own next swing. Either way there is no flag."""


@power("f3531", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a r44 racial power",
       on=Trigger(PowerUsed, _used_any(*R44), "you use a r44 racial power"))
def f3531(c: Cast) -> None:
    """The race's three powers are declared, so the trigger is a list of
    refs. `ForcedMove` is a `Decision`, so `Window.BEFORE` is the
    interrupt window in which "you can ignore the forced movement" is
    still true -- by `Moved` the shove has happened. `once=True` is the
    printed "the first time".

    **Un-marked off `c.class_feature()`, which was wrong about this row
    twice.** The last clause is not a class feature named in prose: the
    spec resolves it to `f3529`, a feat, whose granted power `f3529b`
    is declared above. And nothing is waiting to be built -- `f3529`
    gates on `level>=11`, so the clause sits in the same tier as this
    card's own 11th- and 21st-level steps, which carry no marker either.
    """
    me = c.me

    def dodge(ev: Any) -> None:
        if ev.target != me:
            return
        ev.cancel()
        c.shift(1)
        near = [x for x in c.within(1) if x != me]
        if near:
            c.flat(c.wis_mod, dtype=DamageType.COLD, on=near[0])

    c.watch(ForcedMove, dodge, window=Window.BEFORE, once=True,
            until=When.SONT, on=me, label=f"{c.ref} dodge")


@power("f3532", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a r44 racial power",
       on=Trigger(PowerUsed, _used_any(*R44), "you use a r44 racial power"))
def f3532(c: Cast) -> None:
    """"Targets you" is `AttackDeclared`, which names one `target` --
    the close-or-area half is asked of the row that is being used, the
    way `p7441` asks it.

    The aspect clause is `f3529`, a feat gated on `level>=11` -- out of
    tier, like this card's own 11th- and 21st-level steps. See `f3531`."""
    me = c.me

    def sting(ev: Any) -> None:
        if ev.target != me:
            return
        # `AREA_OR_CLOSE` adds the `"wall"` this omitted. #616.
        if _shape(ev.power) not in AREA_OR_CLOSE:
            return
        c.flat(c.wis_mod, dtype=DamageType.LIGHTNING, on=ev.attacker)

    c.watch(AttackDeclared, sting, once=True, until=When.SONT, on=me,
            label=f"{c.ref} sting")


@power("f3533", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a r44 racial power",
       on=Trigger(PowerUsed, _used_any(*R44), "you use a r44 racial power"))
def f3533(c: Cast) -> None:
    """The damage context carries `opportunity`, so the narrowing is a
    gate rather than a guess at which row an opportunity attack is, and
    `Hit` carries the same as a plain attribute rather than a field.

    The two points are thunder and carry that type, so a creature
    resisting thunder shrugs them off and still takes the weapon.

    The aspect clause is `f3529`, a feat gated on `level>=11` -- out of
    tier, like this card's own 11th- and 21st-level steps. See `f3531`.
    """
    me = c.me
    opportune = lambda ctx: bool(ctx.get("opportunity"))  # noqa: E731
    c.bonus("damage", 2, on=me, until=When.SONT, when=opportune,
            dtype=DamageType.THUNDER)

    def shove(ev: Any) -> None:
        if ev.attacker == me and getattr(ev, "opportunity", False):
            c.push(1, on=ev.target)

    c.watch(Hit, shove, until=When.SONT, on=me, label=f"{c.ref} push")


@power("f3534", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use a r44 racial power",
       on=Trigger(PowerUsed, _used_any(*R44), "you use a r44 racial power"))
def f3534(c: Cast) -> None:
    """The melee half is read off the row that hit; `Hit` names it.

    The aspect clause is `f3529`, a feat gated on `level>=11` -- out of
    tier, like this card's own 11th- and 21st-level steps. See `f3531`."""
    me = c.me

    def burn(ev: Any) -> None:
        if ev.target != me or _shape(ev.power) != "melee":
            return
        c.flat(c.wis_mod, dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(Hit, burn, once=True, until=When.SONT, on=me,
            label=f"{c.ref} burn")


@power("f3535", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("actions.aid_defence(requires=bloodied)",))
def f3535(c: Cast) -> None:
    """"Once per round, you can use the aid defense action as a minor
    action, but only if the chosen ally is bloodied. Also, you gain a +2
    feat bonus to initiative checks."

    **The cheaper action lands.** `c.grant_action` is the general
    mechanism -- the same one `c.shift_as` uses for "you can shift 2
    squares as a move action" -- and `actions._manoeuvres` now reads the
    granted cost back instead of gating every aid on a standard. The
    cheaper cost *replaces* the standard rather than joining it, so the
    menu does not carry two entries differing only in what they spend.

    The initiative half is `c.initiative`: `c.bonus("initiative", ...)`
    sits in the table and no roll ever reads it.

    **Two clauses dropped, and they are the same clause.** "Only if the
    chosen ally is bloodied" and "once per round" are both conditions on
    the *option* rather than on the effect, and the menu cannot ask
    either: aid is offered per adjacent enemy and the ally is chosen when
    the action resolves, so at the moment the entry is built there is no
    chosen ally to test. Named as an `actions.` symbol rather than a
    `c.` one because the fix is in the menu, not in a verb. See #524.
    """
    from combat_engine.engine.types import ActionType

    c.initiative(2, on=c.me)
    c.grant_action("aid_defence", ActionType.MINOR, on=c.me,
                   until=When.ENCOUNTER)


@power("f3536", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3536(c: Cast) -> None:
    """"For each milestone you've reached since your last extended rest, you
    gain a +1 bonus to ability checks, saving throws, and skill checks."

    A **count**, so this is the second of `c.milestone()`'s two shapes and
    the other one that needed a number rather than a yes -- the five item
    rows ask `>= 1`. #666.

    **Three keys, because the engine reads three.** `"save"` is read by the
    saving throw; `"skill"` is the wide key `skills.modifier` sums beside
    `skill:<name>`; `"ability_check"` is the wide key the check's own
    `finish` sums beside the rolled skill. There is no bare `"ability"` key
    and writing one would have been a modifier nothing reads --
    `cf:warlock-f1s*` already enumerates exactly these four minus attack,
    which is this card's list.

    Untyped and **not** `once=`: the card is a standing bonus until the next
    extended rest, not something the first roll spends.

    Zero milestones lays nothing at all rather than three +0 modifiers. A
    +0 would read as a working bonus on the audit board and in `lint.py`'s
    unread-modifier pass, which is the shape that hides a dead key.
    """
    got = c.milestone()
    if not got:
        return
    for what in ("save", "skill", "ability_check"):
        c.bonus(what, got, on=c.me, until=When.ENCOUNTER)


# -- the mount pair ---------------------------------------------------------


f3539 = _grants("f3539", "f3539b")


def _ridden_m112a1(world: Any, eid: int) -> bool:
    """The printed Target line, asked of the board before the row is offered."""
    found = world.relations.sources(Relation.RIDDEN_BY, eid)
    if not found:
        return False
    known = world.get(found[0], Powers)
    return known is not None and "m112a1" in known.all


@power("f3539b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Melee(1), target=NO_TARGET, requires=_ridden_m112a1,
       requires_text="you must be riding a mount with a m112a1 power")
def f3539b(c: Cast) -> None:
    """The aura goes on the mount, so the damage is asked of adjacency to
    the mount rather than of `c.in_my_aura` -- the aura's owner is the
    creature carrying it and the caster is only riding. "Ends its turn in
    the aura" is `TurnEnd`; `c.burns` would pay out on entering and at the
    start of a turn instead, which is a different sentence."""
    mount = c.mount()
    if mount is None:
        return
    known = c.world.get(mount, Powers)
    if known is None or "m112a1" not in known.all:
        return
    c.aura(1, label=c.ref, on=mount, until=When.SONT)
    order = list(Size)
    medium = order.index(Size.MEDIUM)

    def ended(ev: Any) -> None:
        foe = ev.actor
        if foe == mount or foe not in c.enemies():
            return
        if order.index(c.size_of(on=foe)) > medium or not c.adjacent_to(mount, foe):
            return
        c.flat(3, on=foe)
        c.push(1, on=foe, by=mount)

    c.watch(TurnEnd, ended, until=When.SONT)


@power("f3540", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("query.provoked_by()",))
def f3540(c: Cast) -> None:
    """The attack context carries `opportunity`, so "against opportunity
    attacks" is a gate. What it does not carry is what the mount was doing
    when it provoked, which is the narrowing to a `m112a1` power."""
    mount = c.mount()
    if mount is not None:
        c.bonus(AC, 4, on=mount, until=When.ENCOUNTER,
                when=lambda ctx: bool(ctx.get("opportunity")))


@power("f3541", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3541(c: Cast) -> None:
    """"You can choose to summon a x10_13 instead of a x10_12" -- a
    substitution on one clause of another row, which is `c.pre_empt`.

    **The note this replaces was right when it was written and is wrong
    now.** It said neither block existed, so "the two forms are the same
    creature and the choice this row grants has nothing to choose between".
    #459 made both rows and they differ: `x10_13` is speed 9 with defences
    at the summoner's +1, `x10_12` is speed 8 at +0. The choice is real.

    `until=When.ENCOUNTER` because a feat is held for the fight, and the
    offer surfaces as a variant on `p13744`'s menu entry rather than as a
    prompt inside its body -- which is what makes it weighable by `policy/`.
    """
    c.pre_empt(
        "p13744", "steed",
        # No square passed: `c.summon` finds a free one near the caster when
        # given none, which is what `p13744` does for its own default too.
        lambda _c: c.summon("x10_13"),
        on=c.me, until=When.ENCOUNTER,
    )


# -- channel divinity -------------------------------------------------------


f3545 = _grants("f3545", "f3545b")


@power("f3545b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=CloseBurst(5), target=ONE_CREATURE,
       keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.SHADOW],
       group=CHANNEL_DIVINITY, attack=Attack(WIS, vs=WILL))
def f3545b(c: Cast) -> None:
    """The card's attack line is **Wisdom vs. Will**, so the header says
    Wisdom.

    I wrote `Attack(None, vs=WILL)` first, reasoning about "your primary
    ability modifier" -- which is the card's *slide distance*, not its
    attack line. `dsl.bonus_for` raises on an `Attack` with neither an
    ability nor a `printed=`, so the row blew up the moment `c.strike`
    was reached. It audited silent only because the undead guard above
    returns first; on a board where the target is undead it raised.

    The slide still reads `c.attack_mod`, which is the right thing for
    that clause and the reason the confusion was available.

    The 5 damage is a watch on `TurnEnd` rather than an aura on the
    target, because it is the creature standing beside it that pays and
    the target is not the one being hurt.
    """
    if not c.is_kind("undead"):
        return
    foe = c.target
    if not c.strike():
        c.dazed(until=When.EONT)
        return
    c.slide(3 + c.attack_mod)
    c.immobilized(until=When.EONT)

    def ended(ev: Any) -> None:
        if ev.actor != foe and c.adjacent_to(foe, ev.actor):
            c.flat(5, on=ev.actor)

    c.watch(TurnEnd, ended, until=When.EONT)
    c.grant_attack(foe)


def _divine_necrotic(ref: str) -> bool:
    p = get(ref)
    return (
        p is not None
        and Keyword.DIVINE in p.keywords
        and Keyword.NECROTIC in p.keywords
        and p.usage.name in ("ENCOUNTER", "DAILY")
        and p.attack is not None
    )


def _my_necrotic_use(world: Any, me: int, ev: Any) -> bool:
    return ev.actor == me and _divine_necrotic(ev.power)


def _my_necrotic_hit(world: Any, me: int, ev: Any) -> bool:
    return ev.attacker == me and _divine_necrotic(ev.power)


@power("f3546", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.ZONE],
       trigger="you use a divine necrotic encounter or daily attack power",
       on=Trigger(PowerResolved, _my_necrotic_use, "you use a necrotic power"))
def f3546(c: Cast) -> None:
    """The zone is drawn around the caster's own square, because this row has no
    area of its own to read with `c.area`.

    **The +1 is narrowed to necrotic powers now**, which `c.grants_in(when=)`
    says: `ctx["power"]` is the row being rolled and the gate is a keyword test
    on it. It used to pay for every attack an ally made from inside, which is a
    wider feat than the printed one.

    "Bright light in the zone becomes dim light" is the zone's own light
    level, which `c.zone(obscured=)` now carries -- so the zone conceals
    whoever stands in it from anyone who cannot see in dim light."""
    zone = c.zone(_burst(c, 1), label=c.ref, until=When.EONT, obscured="dim")
    c.grants_in(
        zone, "attack", 1, side="ally", kind="power",
        when=lambda ctx: Keyword.NECROTIC in getattr(
            get(str(ctx.get("power", ""))), "keywords", ()),
    )


@power("f3547", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with a divine necrotic encounter or daily attack power",
       on=Trigger(Hit, _my_necrotic_hit, "you hit with a necrotic power"))
def f3547(c: Cast) -> None:
    foe = c.trigger.target
    if c.is_kind("undead", on=foe):
        c.slowed(on=foe, until=When.EONT)


@power("f3548", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("chargen.skill_power_choice()",))
def f3548(c: Cast) -> None:
    """Which skill powers a character may choose is settled when it is
    built, and counting as trained for that choice is the whole benefit.

    **Re-pointed, because this is not skill training.** It shared a symbol
    with twelve rows that grant training, and the training model landed
    (#565) without making this writable: the card does not say the
    character *is* trained, it says it may **choose skill powers as if**
    it were. That is a question about the selectable set, and nothing in
    `chargen` offers skill powers at all -- so `Skills.trained` is the
    wrong thing to add to and would hand out the +5 this card never
    grants. #575.
    """


@power("f3549", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3549(c: Cast) -> None:
    """The first five points of a necrotic resistance, and only when the
    blow came out of a divine power carrying the necrotic keyword --
    which is the power the damage context names, read back through
    `get`. A plain trait now that it has a body and no trigger."""

    def divine_necrotic(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", ""))
        return (
            p is not None
            and Keyword.DIVINE in p.keywords
            and Keyword.NECROTIC in p.keywords
        )

    c.ignore_resistance(
        5, DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER,
        when=divine_necrotic,
    )


f3550 = _grants("f3550", "f3550b")


def _drops_within(squares: int):  # noqa: ANN202
    """`Dropped` carries the creature going down as `actor`, which is what
    "a creature within 5 squares of you drops" is about -- `by_me` would
    read `source` and answer for whoever struck the blow instead."""

    def when(world: Any, me: int, ev: Any) -> bool:
        return (
            ev.actor != me
            and distance(_at(world, me), _at(world, ev.actor)) <= squares
        )

    return when


@power("f3550b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=CloseBurst(5),
       target=NO_TARGET, keywords=DIVINE, group=CHANNEL_DIVINITY,
       trigger="a creature within 5 squares of you drops below 1 hit point",
       on=Trigger(Dropped, _drops_within(5), "a creature nearby drops"))
def f3550b(c: Cast) -> None:
    """The target is the creature going down, so the row reads `c.trigger`
    rather than `c.target`: a burst that picked its own target would filter
    out the dying, which `query.enemies` does. The Special is the group,
    which is what holds a channel divinity to one a fight.

    **"Against a creature you choose" was the half that never arrived.**
    `c.grant_attack`'s first argument is who *swings*, and its `on=` is who
    is swung at -- which resolves through `_who`, so bare it meant this
    row's target. The row declares `NO_TARGET`, so the grant returned False
    on its own `if target is None` guard and the dying creature never
    attacked anything. #631.

    Chosen by the caster, which is the card's own word, and from the
    creatures the dying one can actually reach -- a free basic attack it
    cannot deliver is not the benefit printed.
    """
    dying = c.trigger.actor
    reach = sorted(
        foe for foe in c.within(1, of=dying, side="enemy") if foe != dying
    )
    victim = c.choose(reach, f"{c.ref}: whom it strikes") if reach else None
    if victim is None:
        return
    c.grant_attack(dying, on=victim)


# -- the last of the general run --------------------------------------------


def _missed_with_advantage(world: Any, me: int, ev: Any) -> bool:
    p = get(ev.power)
    result = getattr(ev, "result", None)
    return (
        ev.attacker == me
        and p is not None
        and p.usage.name == "ENCOUNTER"
        and p.attack is not None
        and bool(result and result.advantage)
    )


@power("f3551", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you miss an enemy granting combat advantage with an encounter power",
       on=Trigger(Miss, _missed_with_advantage, "you miss with an encounter power"))
def f3551(c: Cast) -> None:
    """"An enemy that grants combat advantage to you" is asked of the
    attack that was made, not of the board afterwards: a one-shot grant has
    been spent by the time the miss is announced, which is why the
    predicate reads the `AttackResult` riding on the event. Heroic tier, so
    2 extra damage."""
    foe = c.trigger.target
    friends = set(c.allies())

    def struck(ev: Any) -> None:
        if ev.target == foe and ev.attacker in friends:
            c.flat(2, on=foe)

    c.watch(Hit, struck, until=When.SONT, once=True)


def _opportunity_with_shield(world: Any, me: int, ev: Any) -> bool:
    gear = world.get(me, Gear)
    return (
        ev.attacker == me
        and getattr(ev, "opportunity", False)
        and gear is not None
        and gear.shield
    )


@power("f3552", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you hit with an opportunity attack while using a shield",
       on=Trigger(Hit, _opportunity_with_shield, "you hit with an opportunity attack"))
def f3552(c: Cast) -> None:
    """`Hit` does not declare `opportunity`; `resolve.attack` sets it as a
    plain attribute afterwards, so the predicate reads it with a default.
    Untyped, so it stacks with the shield's own bonus, which is what the
    card's silence about a type means."""
    c.bonus(AC, 2, on=c.me, until=When.SONT)
    beside = c.within(1, side="team")
    if beside:
        c.bonus(AC, 2, on=beside[0], until=When.SONT)


@power("f3553", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3553(c: Cast) -> None:
    """`SurgeSpent` says whose surge went and how many are left, and
    nothing about what took it. It does not have to: `PowerUsed` is
    announced above a body and `PowerResolved` below it, so every event
    between the two belongs to that use, and "a power **you** used" is
    the bracket rather than a field. A second wind an ally takes on its
    own turn falls outside it and is not offered. A stack rather than a
    flag, because a row reaching another nests."""
    me = c.me
    running: list[str] = []

    def opened(ev: Any) -> None:
        if ev.actor == me:
            running.append(ev.power)

    def closed(ev: Any) -> None:
        if ev.actor == me and running:
            running.pop()

    def spent(ev: Any) -> None:
        if not running:
            return
        who = ev.actor
        if who == me or who not in c.allies():
            return
        if c.may("shift 1 square", who=who):
            c.shift(1, who=who)
        else:
            c.bonus(AC, 2, on=who, until=When.SOTNT)
            c.bonus(REF, 2, on=who, until=When.SOTNT)

    c.watch(PowerUsed, opened, until=When.ENCOUNTER, label=f"{c.ref} open")
    c.watch(PowerResolved, closed, until=When.ENCOUNTER, label=f"{c.ref} close")
    c.watch(SurgeSpent, spent, until=When.ENCOUNTER)


@power("f3554", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3554(c: Cast) -> None:
    """The count is taken when the trait is armed, which is the only moment
    a standing bonus has -- an ally walking into range later does not
    reopen it. `c.feat` asks whether a creature knows a row, so the feat
    can look for itself on its neighbours by its own ref."""
    me = c.me
    together = 1 + sum(1 for who in c.within(5, side="ally") if c.feat(c.ref, on=who))
    bonus = min(5, together)
    c.initiative(bonus, on=me)
    c.bonus("save", bonus, kind="feat", on=me, until=When.ENCOUNTER,
            when=lambda ctx: Keyword.FEAR in ctx.get("keywords", ()))


@power("f3555", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3555(c: Cast) -> None:
    """Every Perception this engine consults is one creature looking for a
    hidden one, so "to detect a hidden enemy" narrows nothing here and the
    whole condition left to say is the adjacent ally holding the same feat,
    which `c.feat` asks. Two feat bonuses do not stack, so the second is
    the full +4 rather than another +2. Sleep is not a state a fight has."""
    me = c.me
    c.bonus("skill:perception", 2, kind="feat", on=me, until=When.ENCOUNTER)
    c.bonus(
        "skill:perception", 4, kind="feat", on=me, until=When.ENCOUNTER,
        when=lambda ctx: any(
            c.adjacent(to=a) and c.feat("f3555", on=a) for a in c.allies()
        ),
    )


@power("f3556", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p2339",
       on=Trigger(PowerUsed, _used("p2339"), "you use p2339"))
def f3556(c: Cast) -> None:
    """`PowerUsed` because the extra square has to be granted before the
    slide the body makes, and because its `targets` are chosen above the
    body and so are trustworthy there. `c.forces` lengthens every push,
    pull and slide the caster makes, which for the length of one turn is
    the nearest thing to "one extra square on this one"."""
    c.forces(1, on=c.me, until=When.EOT)
    for who in c.trigger.targets:
        c.bonus("damage", 2, on=who, until=When.EOTNT, once=True)


@power("f3557", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use cf:bard-f1",
       on=Trigger(PowerResolved, _used("cf:bard-f1"), "you use cf:bard-f1"))
def f3557(c: Cast) -> None:
    c.shift(1)


@power("f3558", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, narrative=("skill:diplomacy",))
def f3558(c: Cast) -> None:
    """A standing bonus and a printed trigger on one card, so the row is a
    trait and the triggered half is a `c.watch`. The Intimidate bonus
    `p2339`'s cousin lays is put on alongside the Diplomacy one rather than
    in place of it, because nothing can reach into another row's effect and
    take it back."""
    me = c.me
    c.bonus("skill:intimidate", 2, kind="feat", on=me, until=When.ENCOUNTER)

    def spoke(ev: Any) -> None:
        if ev.actor == me and ev.power == "p2887" and c.may("aim it at Intimidate"):
            c.bonus("skill:intimidate", 5, kind="power", on=me,
                    until=When.EONT, once=True)

    c.watch(PowerResolved, spoke, until=When.ENCOUNTER)


#: The six origins, so that "changes to shadow" can displace whichever
#: one a race wrote on. `c.set_origin` takes one `instead_of` and a
#: creature has one origin, but which one is not knowable here: this row
#: and the racial trait that lays the old word are both traits armed at
#: the start of a fight, in an order neither may assume.
ORIGINS = ("aberrant", "elemental", "fey", "immortal", "natural")


@power("f3559", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3559(c: Cast) -> None:
    """`c.set_origin` writes the word onto the creature and `c.kinds_of`
    unions it with the stat block, so "your origin changes to shadow" is
    a word laid and the rest taken off -- "changes to", not "also counts
    as", and an origin is exclusive.

    The saving-throw half is gated on standing in dim light or darkness
    rather than laid flat -- an ungated +1 to every save is a bigger number
    than the card gives, which is why it waited for a light model."""
    for word in ORIGINS:
        c.set_origin(instead_of=word, on=c.me)
    c.set_origin("shadow", on=c.me)
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.unlit())


@power("f3561", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3561(c: Cast) -> None:
    """"Whenever you make a weapon attack using an axe or a heavy blade
    against an undead creature, you can reroll any damage die but must use
    the second result."

    **`c.reroll_ones(below=ANY_FACE, pick=…)` is the verb**, and five
    different symbols were filed for it across eight rows (#703).
    `c.reroll_damage` is a different and stronger rule -- the whole
    expression twice, keeping the higher -- and none of the eight prints
    that. What was actually in the way was one line: `_rolled_pick` carried
    `floor > faces` as a guard, copied from the looping case where it is
    necessary, so a floor above every face returned the roll untouched.

    `pick=EVERY_DIE` is "any damage die", and `ANY_FACE` is the card
    printing no threshold -- read as the die's own break-even, because
    rerolling a 6 blind throws away a 6 and the card is offering a choice.
    `_rolled_pick` has the measurement.

    **Two gates, both on the `when=`**, because neither is a property of the
    creature: the weapon group is whatever is in hand at the moment of the
    roll, and the victim is whichever creature this blow is landing on.
    `_reroll_ctx` carries `target` for exactly the second one.
    """
    def swung_at_undead(ctx: dict[str, Any]) -> bool:
        # `c.wielding` takes the printed group word and answers for whatever
        # is in hand, which is the only way to ask this: the group is a fact
        # about the weapon and the weapon can change mid-fight.
        if not (c.wielding("axe") or c.wielding("heavy blade")):
            return False
        foe = ctx.get("target")
        return foe is not None and c.is_kind("undead", on=foe)

    c.reroll_ones(below=ANY_FACE, pick=EVERY_DIE, on=c.me,
                  until=When.ENCOUNTER, when=swung_at_undead)
