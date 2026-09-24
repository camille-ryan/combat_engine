"""Monster abilities, level 2: the artillery.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=9)` and `Damage("1d10", 4)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

Two conventions the level 1 file settled and this one keeps.

A printed range of "10/20" is a normal range and a long range, and `Range`
holds one number, so the **normal** range is what gets written: the band
where the creature shoots at no penalty, rather than a distance at a -2 the
engine has no way to apply.

A **trait** costs no action and has no target, and arms the watches that
hold it for the rest of the fight. `usage=ENCOUNTER` is what stops it being
armed twice and paying twice.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    Condition,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Square,
    Target,
    Usage,
    When,
    distance,
    get,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackDeclared,
    AttackRolled,
    Hit,
    Miss,
    MoveEnd,
    MoveStart,
    RelationCleared,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import has_combat_advantage, squares
from combat_engine.engine.triggers import (
    Trigger,
    both,
    by_me,
    by_melee,
    enemy_within,
    targets_me,
)


def _is_ranged(ref: str) -> bool:
    """Was that row a ranged one? Asked off the modifier context's power ref.

    `c.bonus(when=...)` is handed the attack context, which carries the ref
    and not the range, so the lookup is done here rather than in four
    lambdas.
    """
    p = get(ref)
    return p is not None and p.reach.kind == "ranged"


# --------------------------------------------------------------------------
# m188
# --------------------------------------------------------------------------


@power(
    "m188a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m188a0(c: Cast) -> None:
    """Covering ground makes its shooting more accurate until its next turn.

    The starting point is taken when the move begins rather than at the top
    of the turn: the printed line measures one move, and a creature that
    moves twice has each of them measured on its own. The bonus is a gated
    modifier rather than one put on and taken off, so a melee swing in the
    same turn does not get it.
    """
    me = c.me
    began: list[Square] = []

    def off(ev: MoveStart) -> None:
        if ev.actor == me:
            began.append(c.here)

    def landed(ev: MoveEnd) -> None:
        if ev.actor != me or not began:
            return
        start = began.pop()
        if distance(start, ev.at) < 4:
            return
        c.bonus(
            "attack",
            2,
            until=When.SONT,
            on=me,
            when=lambda ctx: _is_ranged(ctx["power"]),
        )

    c.watch(MoveStart, off, until=When.ENCOUNTER, on=me, label="m188a0")
    c.watch(MoveEnd, landed, until=When.ENCOUNTER, on=me, label="m188a0 mobile")


@power(
    "m188a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m188a1(c: Cast) -> None:
    """Rough ground costs it nothing when it steps.

    The printed line is about shifting in particular and `c.ignores_difficult`
    is about moving at all; nothing tells the two apart, so the broader
    reading is the one that can be said -- the judgement m189a1 made.
    """
    c.ignores_difficult(until=When.ENCOUNTER)


@power(
    "m188a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 4),
)
def m188a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m188a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m188a3(c: Cast) -> None:
    if c.strike():
        c.hit()


_MAKES_AN_ATTACK_ROLL = "the m188 makes an attack roll"


@power(
    "m188a4",
    level=2,
    usage=ENCOUNTER,
    action=FREE,
    trigger=_MAKES_AN_ATTACK_ROLL,
    on=Trigger(AttackRolled, when=by_me, text=_MAKES_AN_ATTACK_ROLL),
    reach=PERSONAL,
    target=SELF,
)
def m188a4(c: Cast) -> None:
    """The second result stands whatever it is, so `keep="new"`, not "best".

    `AttackRolled` rather than `AttackDeclared`: the printed trigger is the
    roll, and only that event carries the live result for the reroll to
    change. It is emitted before the hit or miss is worked out, so a free
    action answering it still lands in time.
    """
    c.reroll_attack(keep="new")


_SWUNG_AT_IN_MELEE = "an enemy makes a melee attack against the m188"


@power(
    "m188a5",
    level=2,
    usage=ENCOUNTER,
    action=REACTION,
    trigger=_SWUNG_AT_IN_MELEE,
    on=Trigger(
        AttackDeclared, when=both(targets_me, by_melee), text=_SWUNG_AT_IN_MELEE
    ),
    reach=PERSONAL,
    target=SELF,
)
def m188a5(c: Cast) -> None:
    """Step back and shoot whoever closed on it.

    The shot is m188a3 fired by the creature itself, named outright rather
    than left to `c.basic()` -- its basic attack is the melee one, and the
    printed line says the bow. Being a ranged attack next to an enemy, it
    provokes, which `use` already sees to.
    """
    enemy = getattr(c.trigger, "attacker", None)
    if enemy is None:
        return
    c.shift(1)
    c.grant_attack(c.me, on=enemy, ref="m188a3")


# --------------------------------------------------------------------------
# m242
# --------------------------------------------------------------------------


@power(
    "m242a0",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m242a0(c: Cast) -> None:
    """Extra damage against anything that has given it an opening.

    No once-a-round latch is printed, so this is a plain watch rather than
    `features.strikers.extra_damage`. Combat advantage is asked of the board
    at the moment of the hit: flanking ends the instant an ally steps away
    and a flag stored when the trait was armed would not notice.
    """
    me = c.me

    def on_hit(ev: Hit) -> None:
        if ev.attacker != me:
            return
        if has_combat_advantage(c.world, me, ev.target):
            c.damage("1d6", on=ev.target, detail="m242a0")

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label="m242a0")


@power(
    "m242a1",
    level=2,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m242a1(c: Cast) -> None:
    """Shooting from cover and missing does not give it away.

    Attacking normally breaks hidden -- `resolve.attack` clears it for
    whoever swung -- so this is written as the exemption it is printed as
    rather than as a special case inside the engine. The miss is noted while
    the creature is still unseen, and the break is undone as it happens: the
    `Miss` listener runs before the relation is cleared, and the
    `RelationCleared` listener puts it back.
    """
    me = c.me
    spared: set[int] = set()

    def missed(ev: Miss) -> None:
        p = get(ev.power)
        if ev.attacker != me or p is None or p.reach.kind != "ranged":
            return
        if c.is_hidden(from_=ev.target):
            spared.add(ev.target)

    def broke(ev: RelationCleared) -> None:
        if ev.kind_ is not Relation.HIDDEN_FROM or ev.source != me:
            return
        if ev.why == "attacked" and ev.target in spared:
            spared.discard(ev.target)
            c.world.relations.set(Relation.HIDDEN_FROM, me, ev.target)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label="m242a1")
    c.watch(RelationCleared, broke, until=When.ENCOUNTER, on=me, label="m242a1 keep")


@power(
    "m242a2",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("2d6", 2),
)
def m242a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m242a3",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 7),
)
def m242a3(c: Cast) -> None:
    if c.strike():
        c.hit()


_MISSED_BY_AN_ATTACK = "the m242 is missed by an attack"


@power(
    "m242a4",
    level=2,
    usage=AT_WILL,
    action=REACTION,
    trigger=_MISSED_BY_AN_ATTACK,
    on=Trigger(Miss, when=targets_me, text=_MISSED_BY_AN_ATTACK),
    reach=PERSONAL,
    target=SELF,
)
def m242a4(c: Cast) -> None:
    """The printed effect line reads Immediate Reaction, so that is the action
    type, whatever the stat block's own header says."""
    c.shift(1)


# --------------------------------------------------------------------------
# m3027
# --------------------------------------------------------------------------


@power(
    "m3027a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d6", 3),
)
def m3027a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3027a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.POISON),
)
def m3027a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m3027a2",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON, Keyword.AREA],
    attack=Attack(vs=FORT, printed=5),
    damage=Damage("1d6", 3, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m3027a2(c: Cast) -> None:
    """Both halves leave the target soft to poison; only the duration differs.

    Printed target is "creatures in the burst", not enemies, so it catches
    its own side as readily as anybody else's.
    """
    if c.strike():
        c.hit()
        c.vulnerable(5, DamageType.POISON, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.vulnerable(5, DamageType.POISON, until=When.EONT)


@power(
    "m3027a3",
    level=2,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(20),
    target=Target("enemy", 1, label="One creature taking ongoing poison damage"),
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=7),
)
def m3027a3(c: Cast) -> None:
    """Only against something m3027a1 has already dosed.

    `target` cannot filter on what a creature is suffering and `requires` is
    asked of the caster, so the printed restriction is written into the
    target label for the card and checked here for the rules. It is a real
    gate, not a note: without it this is an unconditional at-will slide and
    slow, which is a different power.
    """
    victim = c.target
    if victim is None:
        return
    dosed = any(
        e.ongoing is not None and e.ongoing[1] is DamageType.POISON
        for e in c.world.effects.of(victim)
    )
    if not dosed:
        return
    if c.strike():
        c.slide(3)
        c.slowed(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m5031
# --------------------------------------------------------------------------


@power(
    "m5031a0",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d4", 4),
)
def m5031a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5031a1",
    level=2,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC),
)
def m5031a1(c: Cast) -> None:
    """Worse the more crowded the target is, so the bonus is counted at the
    moment of the shot rather than declared in the header.

    "Per creature adjacent to the target" is every creature, the m5031
    included if it has closed -- `side="other"` is the whole board minus the
    target itself.
    """
    crowd = len(c.within(1, of=c.target, side="other")) if c.target else 0
    if c.strike(plus=crowd):
        c.hit()
        c.grants_advantage(until=When.EONT)


@power(
    "m5031a2",
    level=2,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m5031a2(c: Cast) -> None:
    """One friend already in reach gets a free swing at the same creature.

    `c.grant_attack` with no `ref` rolls whatever that creature's own basic
    attack actually is, which is the point of it -- a monster whose basic is
    one of its own abilities swings with that and not with a notional
    weapon.
    """
    if not c.strike():
        return
    c.hit()
    beside = [a for a in c.within(1, of=c.target, side="ally") if a != c.me]
    friend = c.choose(sorted(beside), "an ally makes a melee basic attack")
    if friend is not None:
        c.grant_attack(friend, on=c.target)


@power(
    "m5031a3",
    level=2,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RANGED],
    attack=Attack(vs=REF, printed=7),
)
def m5031a3(c: Cast) -> None:
    """No damage on the hit at all: the whole line is the hold and the bleed.

    "Save ends both" is one effect carrying both, not two saved against
    separately, so it is a single `c.condition` with its `ongoing`.
    """
    if c.strike():
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.UNTYPED),
        )


_HIT_BY_ADJACENT = "an enemy adjacent to the m5031 hits it"


@power(
    "m5031a4",
    level=2,
    usage=AT_WILL,
    action=REACTION,
    trigger=_HIT_BY_ADJACENT,
    on=Trigger(Hit, when=both(targets_me, enemy_within(1)), text=_HIT_BY_ADJACENT),
    reach=PERSONAL,
    target=SELF,
)
def m5031a4(c: Cast) -> None:
    """Round to the other side of whoever just landed one.

    The destination is named outright rather than left to a teleport of some
    distance, which would also allow squares nowhere near the attacker.
    "Another" square is had for free: the one it is standing in has an
    occupant and is filtered out with every other occupied square.
    """
    enemy = getattr(c.trigger, "attacker", None)
    if enemy is None:
        return
    grid = c.world.grid
    spots = sorted(
        sq
        for sq in spread(squares(c.world, enemy), 1)
        if grid.passable(sq) and grid.occupant(sq) is None
    )
    dest = c.choose(spots, "teleport beside the attacker")
    if dest is not None:
        c.teleport(1, to=dest)
