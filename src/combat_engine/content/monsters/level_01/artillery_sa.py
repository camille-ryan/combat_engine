"""Monster abilities, level 1, artillery: the second sweep.

Fourteen stat blocks whose rows were still undeclared. `artillery.py` holds
the first sweep of this level; the split is by *when* the work was done
rather than by what the creatures are, so the conventions are the ones that
file settled:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=8)`) and the damage line goes in the header
  as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight;
* a printed range of "15/30" takes the **normal** range, so the creature
  shoots inside the band where it has no penalty;
* a minion's flat damage says so with `kind=MINION`, a recharge or encounter
  attack with `kind=LIMITED`.

Four helpers here are shared with `brutes_sa.py`, which imports them: six
blocks across the two roles print the same four sentences and the pair of
"runners" traits are word for word the same line about two different stat
blocks.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.content.monsters.level_02.skirmishers import (
    _still_hidden_on_a_miss,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Effect,
    Health,
    Keyword,
    Melee,
    Ranged,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackRolled,
    Bloodied,
    ConditionApplied,
    Dropped,
    Hit,
    Miss,
    Moved,
    MoveEnd,
    MoveStart,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import cover_between, enemies, is_
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_me,
    by_melee,
    by_ranged,
    targets_me,
)

# -- what the two roles share ----------------------------------------------


def _is_bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _recharge_when_bloodied(c: Cast) -> None:
    """Put this row back up when the printed line says so, not only on a die.

    Three blocks across this wave print "Recharge when first bloodied" where
    the database files a plain 6+. The number stays in the header, because
    that is what `actions.recharge` rolls and what the card shows; this is the
    printed sentence on top of it, and the two only ever agree to make the row
    available sooner. Armed from the body, which is all that is needed: a
    recharge row cannot be spent before it has been used once.
    """
    me, ref = c.me, c.ref

    def bled(ev: Bloodied) -> None:
        if ev.actor == me:
            c.restore_use(ref, on=me)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, once=True, label=f"{ref} recharge")


def _any_enemy_suffering(*conditions: Condition):  # noqa: ANN202
    """A Requirement that somebody out there is in the state a target line names.

    Several rows across this wave print a target restriction about what a
    creature is *suffering* -- "an immobilized creature", "a dazed creature", "a
    helpless or unconscious creature". `Target` filters on side and size and
    nothing else, so the restriction has to be asked of `c.target` in the body;
    this is the other half, and it decides whether the row is offered at all.

    Without it the row is offered every turn, aimed at whoever is nearest, and
    returns having done nothing -- which from the outside is indistinguishable
    from a row that was written wrong. `audit.py` reported exactly that for four
    of them before this existed.
    """

    def gate(world: World, eid: int) -> bool:
        return any(
            any(is_(world, foe, cond) for cond in conditions)
            for foe in enemies(world, eid)
        )

    return gate


def _runners(c: Cast, kin: str) -> None:
    """Two damage to an enemy that starts its turn beside two or more of these.

    Every one of the pack arms the trait, and the printed sentence is one hit
    of 2 damage rather than one per creature standing there -- so the lowest
    numbered of whoever is adjacent is the one that deals it. `Ident.ref` is
    what "two or more of *these*" asks: `c.is_kind` answers about type words,
    and every creature in the fight may share those.
    """
    me = c.me

    def at_the_top(ev: TurnStart) -> None:
        foe = ev.actor
        if ev.ghost or foe == me or foe not in c.enemies():
            return
        pack = [
            a
            for a in (me, *c.allies())
            if _ref_of(c, a) == kin and c.adjacent_to(a, foe)
        ]
        if len(pack) >= 2 and min(pack) == me:
            c.flat(2, on=foe)

    c.watch(TurnStart, at_the_top, until=When.ENCOUNTER, on=me, label=f"{c.ref} pack")


def _prone_save(c: Cast) -> None:
    """A saving throw to stay on its feet when an attack would floor it.

    `ConditionApplied` is the only moment the fall can be seen, so the throw
    is made there and a success lifts the prone that was just laid. `bare`
    because there is no save-ends effect to shake off -- this is one of the
    handful of printed saves against nothing in particular.
    """
    me = c.me

    def floored(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.PRONE:
            return
        if c.save(on=me, bare=True, against=f"{c.ref} footing"):
            c.cure(Condition.PRONE, on=me)

    c.watch(
        ConditionApplied, floored, until=When.ENCOUNTER, on=me,
        label=f"{c.ref} footing",
    )


def _sure_footed_shift(c: Cast) -> None:
    """"Ignores difficult terrain when it shifts", and only when it shifts.

    `Movement.ignores` is a per-creature set that `ecs.rough` reads with no
    move-kind gate, so there is nothing to narrow -- a plain
    `c.ignores_difficult()` would let the creature *walk* through rough ground
    for nothing too, which the card does not say. So the exemption is switched
    on for the length of the shift and off again at the end of it:
    `MoveStart` carries `kind_` and is emitted before the first step, which
    is the only window where it can be turned on in time.
    """
    me, ref = c.me, c.ref
    held: list[Effect] = []

    def began(ev: MoveStart) -> None:
        if ev.actor == me and ev.kind_ == "shift":
            eased = c.ignores_difficult(on=me, until=When.ENCOUNTER)
            if eased is not None:
                held.append(eased)

    def finished(ev: MoveEnd) -> None:
        if ev.actor != me:
            return
        while held:
            c.world.effects.end(held.pop(), ref)

    c.watch(MoveStart, began, until=When.ENCOUNTER, on=me, label=f"{ref} sure-footed")
    c.watch(MoveEnd, finished, until=When.ENCOUNTER, on=me, label=f"{ref} sure-footed")


# -- what only this file shares --------------------------------------------


def _beside_kin(c: Cast, kin: str) -> bool:
    """Is one of its own, off the same stat block, standing next to it?"""
    return any(_ref_of(c, a) == kin and c.adjacent(a) for a in c.allies())


def _beside_kind(c: Cast, word: str) -> bool:
    """Is an ally of that printed type word standing next to it?"""
    return any(c.is_kind(word, on=a) and c.adjacent(a) for a in c.allies())


def _uncovered(c: Cast, foe: int | None) -> bool:
    """Does the target have no cover and no concealment from here?

    Measured at the moment of the swing rather than asked of a modifier,
    because cover is a fact about two positions and both of them move.
    """
    return foe is not None and cover_between(c.world, c.me, foe, ranged=True) is Cover.NONE


def _cheb(a: tuple[int, int], b: tuple[int, int]) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


# --------------------------------------------------------------------------
# m1128
# --------------------------------------------------------------------------


@power(
    "m1128a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 3),
)
def m1128a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1128a1",
    level=1,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d12", 2, kind=LIMITED),
    dropped=("actions.legal('reload')",),
)
def m1128a1(c: Cast) -> None:
    """The second half of the recharge line is the dropped clause: the card
    also comes back when the creature spends a move action reloading, and
    "reload" is not a word `actions.legal` knows, so there is no action to
    grant and no event to watch for. The 6+ in the header is the half that
    plays."""
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m1128a2",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m1128a2(c: Cast) -> None:
    """The swing and the six hit points are two lines, not one: a monster's
    surge is a quarter of its maximum and the card names a flat number, so
    nothing is spent and the printed amount is healed."""
    c.basic()
    if c.first:
        c.heal(6, on=c.me)


# --------------------------------------------------------------------------
# m1135
# --------------------------------------------------------------------------


@power(
    "m1135a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d10", 2),
)
def m1135a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1135a1",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
    dropped=("compendium.attack_defence",),
)
def m1135a1(c: Cast) -> None:
    """The card carries a second attack line -- "+6 vs ; 2d10+3" -- whose
    defence the extraction lost, so that half cannot be declared at all and
    is named rather than guessed. What plays is the sentence that survived
    intact: a melee basic attack and six hit points back."""
    c.basic()
    if c.first:
        c.heal(6, on=c.me)


@power(
    "m1135a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.AREA],
    attack=Attack(vs=REF, printed=4),
    damage=Damage("1d8", 3, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m1135a2(c: Cast) -> None:
    """The critical knocks prone on top of the ordinary maximised dice; the
    miss is half damage and no burn, which is why the ongoing line sits inside
    the hit branch rather than beside it."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
        if c.crit:
            c.prone()
    else:
        c.hit(half=True)


@power(
    "m1135a3",
    level=1,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m1135a3(c: Cast) -> None:
    """Printed as the other burst thrown one last time -- same defence, same
    dice, same burn, same critical -- behind a Requirement that there be one
    left. So it is that row, used: `c.use_power` spends the use the
    Requirement is about and refuses when there is none, which is the printed
    sentence and invents no area and no defence of its own."""
    c.use_power("m1135a2")


# --------------------------------------------------------------------------
# m115713
# --------------------------------------------------------------------------


@power(
    "m115713a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115713a0(c: Cast) -> None:
    """Asked inside the gate rather than once when the trait arms: the pack
    shuffles, and a bonus fixed at the start of the fight would be wrong from
    the first time somebody moved."""
    for defence in (AC, REF):
        c.bonus(
            defence, 4, until=When.ENCOUNTER, on=c.me,
            when=lambda ctx: _beside_kin(c, "m115713"),
        )


@power(
    "m115713a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115713a1(c: Cast) -> None:
    c.resist_forced(1)


@power(
    "m115713a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115713a2(c: Cast) -> None:
    _prone_save(c)


@power(
    "m115713a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=4, kind=MINION),
)
def m115713a3(c: Cast) -> None:
    """Four in the header and the difference flat on top, so the card's first
    number is the one the policy and the page read."""
    if c.strike():
        c.hit()
        if _beside_kin(c, "m115713"):
            c.flat(2)


@power(
    "m115713a4",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=4, kind=MINION),
)
def m115713a4(c: Cast) -> None:
    if c.strike():
        foe = c.target
        c.hit()
        if _uncovered(c, foe):
            c.flat(2)


# --------------------------------------------------------------------------
# m4228
# --------------------------------------------------------------------------


@power(
    "m4228a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=3, kind=MINION),
)
def m4228a0(c: Cast) -> None:
    if c.strike():
        foe = c.target
        c.hit()
        if foe is not None and any(c.adjacent_to(a, foe) for a in c.allies()):
            c.flat(2)


@power(
    "m4228a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=3, kind=MINION),
)
def m4228a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4228a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4228a2(c: Cast) -> None:
    """`opportunity` is a key the attack context carries and `query.defence`
    is handed that same context, so the narrowing is a gate rather than a
    watch."""
    c.bonus(
        AC, 4, until=When.ENCOUNTER, on=c.me,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


# --------------------------------------------------------------------------
# m4592
# --------------------------------------------------------------------------


@power(
    "m4592a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4"),
)
def m4592a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4592a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d10", 3),
)
def m4592a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4592a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("1d6", 3, dtype=DamageType.RADIANT),
)
def m4592a2(c: Cast) -> None:
    """"If the target moves closer on its next turn" is read off `Moved`,
    which is the only one of the three movement events carrying both ends of
    a step -- so "closer" is a comparison rather than a guess. Paid once,
    whatever else the creature does with the rest of its move."""
    if not c.strike():
        return
    c.hit()
    victim, me = c.target, c.me
    if victim is None:
        return
    paid: dict[str, bool] = {}

    def closed(ev: Moved) -> None:
        if paid.get("done") or ev.actor != victim:
            return
        if _cheb(ev.to, c.here) < _cheb(ev.from_, c.here):
            paid["done"] = True
            c.flat(c.roll("1d6") + 3, dtype=DamageType.RADIANT, on=victim)

    c.watch(Moved, closed, until=When.EOTNT, on=me, label=f"{c.ref} {victim}")


@power(
    "m4592a3",
    level=1,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d8", 3, kind=LIMITED),
)
def m4592a3(c: Cast) -> None:
    """Enemies rather than creatures: the card names no set, and the whole
    point of the row is to clear the squares round a creature that would
    rather be shooting."""
    if c.strike():
        c.hit()
        c.push(4)


@power(
    "m4592a4",
    level=1,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by an attack",
    on=Trigger(Hit, targets_me, "it is hit"),
)
def m4592a4(c: Cast) -> None:
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m4601
# --------------------------------------------------------------------------


@power(
    "m4601a0",
    level=1,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4601a0(c: Cast) -> None:
    """`once=True` spends the watch on the first blow that actually lands on
    this creature rather than on the first `Hit` of any kind in the fight --
    which is what the flag means and why it is safe behind a guard."""
    me = c.me

    def struck(ev: Hit) -> None:
        if ev.target == me:
            c.penalty(AC, 4, until=When.ENCOUNTER, on=me)

    c.watch(Hit, struck, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} armour")


@power(
    "m4601a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6"),
)
def m4601a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4601a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.AREA],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d6", 3),
)
def m4601a2(c: Cast) -> None:
    """"In the origin square of the burst" is `c.origin`, the square the area
    was aimed at, asked of the board rather than of the target: a Large
    creature standing across the middle of the burst is in it."""
    if not c.strike():
        return
    c.hit()
    if c.origin is not None and c.target in c.in_squares({c.origin}):
        c.ongoing(5)


@power(
    "m4601a3",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4601a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4718
# --------------------------------------------------------------------------


@power(
    "m4718a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=3, kind=MINION),
)
def m4718a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4718a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage(bonus=4, kind=MINION),
)
def m4718a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4718a2",
    level=1,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits with a ranged attack",
    on=Trigger(Hit, both(by_me, by_ranged), "it hits with a ranged attack"),
)
def m4718a2(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4757
# --------------------------------------------------------------------------


@power(
    "m4757a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 4),
)
def m4757a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4757a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
)
def m4757a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4757a2",
    level=1,
    usage=ENCOUNTER,
    uses=3,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=6),
)
def m4757a2(c: Cast) -> None:
    """The primary is the creature's own bow row, borrowed rather than copied,
    so its numbers stay in one place; the header's attack line is the
    **secondary**, which is the only one this card prints for itself.
    `c.landed` reads the borrowed row's result, which is what the printed "on
    a hit" is asking. "Save ends both" is one effect with one saving throw."""
    if not c.use_power("m4757a1") or not c.landed:
        return
    if c.strike():
        c.condition(
            Condition.DAZED, until=When.SAVE_ENDS, ongoing=(3, DamageType.POISON)
        )


@power(
    "m4757a3",
    level=1,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it makes an attack roll",
    on=Trigger(AttackRolled, by_me, "it makes an attack roll"),
)
def m4757a3(c: Cast) -> None:
    """"It must use the second roll, even if it is lower" is `keep="new"`,
    which is the whole of the printed restriction."""
    c.reroll_attack(keep="new")


@power(
    "m4757a4",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4757a4(c: Cast) -> None:
    _sure_footed_shift(c)


# --------------------------------------------------------------------------
# m5146
# --------------------------------------------------------------------------


@power(
    "m5146a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5146a0(c: Cast) -> None:
    """Ranged only -- the card says nothing about missing from hiding with a
    blade, and `resolve.attack` gives the creature away either way."""
    _still_hidden_on_a_miss(c, ("ranged",))


@power(
    "m5146a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=4, kind=MINION),
)
def m5146a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5146a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=4, kind=MINION),
)
def m5146a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5146a3",
    level=1,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed in melee"),
)
def m5146a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m5284
# --------------------------------------------------------------------------


@power(
    "m5284a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5284a0(c: Cast) -> None:
    _runners(c, "m5284")


@power(
    "m5284a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d4", 5),
)
def m5284a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5284a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(12),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d10", 4),
)
def m5284a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5284a3",
    level=1,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Ranged(12),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d10", 3, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m5284a3(c: Cast) -> None:
    """The Aftereffect is a second, lighter hold beginning when the first one
    is shaken off, and the end of an effect is the only moment that can be
    seen, so it is hung there. `on_end` also runs when the fight does, which
    is the cost of being able to say it at all. The miss carries its own,
    shorter slow, which is a different sentence."""
    if not c.strike():
        c.hit(half=True)
        c.slowed(until=When.EONT)
        return
    c.hit()
    victim = c.target
    held = c.immobilized(until=When.SAVE_ENDS)
    if held is not None and victim is not None:
        held.on_end.append(lambda: c.slowed(until=When.SAVE_ENDS, on=victim))


# --------------------------------------------------------------------------
# m5532
# --------------------------------------------------------------------------


@power(
    "m5532a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5532a0(c: Cast) -> None:
    """`c.gains_advantage` rather than `c.grants_advantage`: the set this is
    true of is whoever happens to be standing beside one of the pack at the
    moment of the swing, and there is no creature to lay a relation on when
    the trait arms."""
    me = c.me

    def hemmed_in(ctx: dict[str, object]) -> bool:
        foe = ctx.get("target")
        if not isinstance(foe, int):
            return False
        return any(
            a != me and _ref_of(c, a) == "m5532" and c.adjacent_to(a, foe)
            for a in c.allies()
        )

    c.gains_advantage(hemmed_in, until=When.ENCOUNTER, on=me)


@power(
    "m5532a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=4, kind=MINION),
)
def m5532a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5532a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=4, kind=MINION),
)
def m5532a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


# --------------------------------------------------------------------------
# m6624
# --------------------------------------------------------------------------


@power(
    "m6624a0",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6624a0(c: Cast) -> None:
    """A printed type word, not a stat block: any ally of that kind counts,
    which is `c.is_kind` and not an `Ident` match."""
    for defence in (FORT, WILL):
        c.bonus(
            defence, 4, until=When.ENCOUNTER, on=c.me,
            when=lambda ctx: _beside_kind(c, "dwarf"),
        )


@power(
    "m6624a1",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6624a1(c: Cast) -> None:
    c.resist_forced(1)


@power(
    "m6624a2",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6624a2(c: Cast) -> None:
    _prone_save(c)


@power(
    "m6624a3",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage(bonus=4, kind=MINION),
)
def m6624a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        if _beside_kind(c, "dwarf"):
            c.flat(2)


@power(
    "m6624a4",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage(bonus=4, kind=MINION),
)
def m6624a4(c: Cast) -> None:
    """"Plus 2 psychic" is a second type on the same blow, so it is its own
    flat rather than part of the header's untyped four -- a resistance to
    psychic has to be able to eat one and not the other."""
    if c.strike():
        foe = c.target
        c.hit()
        if _uncovered(c, foe):
            c.flat(2, dtype=DamageType.PSYCHIC)


# --------------------------------------------------------------------------
# m6669
# --------------------------------------------------------------------------


@power(
    "m6669a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d8", 3),
)
def m6669a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6669a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 5),
)
def m6669a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6669a2",
    level=1,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("2d8", 3, kind=LIMITED),
    dropped=("Usage.RECHARGE(when=)",),
)
def m6669a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6669a3",
    level=1,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=6),
)
def m6669a3(c: Cast) -> None:
    """Three clauses, three verbs. The grant goes to the whole side, because
    the card qualifies "grants combat advantage" with nobody; `c.no_cover` is
    the concealment half -- `query.cover_waived` is the one number cover and
    concealment both come out of -- and invisibility is a relation per
    onlooker, so it is lifted for each of them in turn."""
    if not c.strike():
        return
    c.grants_advantage(until=When.EONT, to="team")
    c.no_cover(until=When.EONT)
    for watcher in (c.me, *c.allies()):
        c.see_invisible(on=watcher, until=When.EONT)


# --------------------------------------------------------------------------
# m908
# --------------------------------------------------------------------------


@power(
    "m908a0",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=5),
    damage=Damage("1d6", 3),
)
def m908a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m908a1",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3),
)
def m908a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m908a2",
    level=1,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m908a2(c: Cast) -> None:
    """The special shot the row above points at with "see also". Its line
    prints no attack and no defence at all -- not a lost one, nothing where
    one would be -- so there is nothing to roll and the hold is the whole of
    what the card says. Declared without an attack rather than lent the other
    row's, which would be an invented number in a header a policy reads as
    printed."""
    c.immobilized(until=When.SAVE_ENDS)


@power(
    "m908a3",
    level=1,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m908a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m908a4",
    level=1,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m908a4(c: Cast) -> None:
    """"Against traps" is a question about the attacker, and `Trap` is what
    makes something on the board one -- so the gate reads `attacker` out of
    the context `query.defence` is handed."""

    def by_a_trap(ctx: dict[str, object]) -> bool:
        who = ctx.get("attacker")
        return isinstance(who, int) and c.is_trap(who)

    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, until=When.ENCOUNTER, on=c.me, when=by_a_trap)
