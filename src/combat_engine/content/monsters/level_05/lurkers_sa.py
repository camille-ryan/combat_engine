"""Monster abilities, level 5, lurkers.

Twenty-nine stat blocks, a hundred and seven rows. There is no earlier
`lurkers.py` sweep at this level to avoid -- this role's first pass at level 5
is this file. Six of the twenty-nine print no abilities at all and have
nothing to decorate: m1279, m2904, m318, m4901, m690, m708.

Conventions, inherited from the level-1 to level-4 lurker sweeps and from this
week's `artillery_sa.py` / `brutes_sa.py` / `minions_sa.py` / `misc_sa.py`:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=10)`) and the damage line goes in the header
  as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** costs no action, has no target, and arms what holds it, whatever
  action the compendium's column claims for it;
* a printed range band such as "6/12" takes the short (normal) number;
* a close burst or blast whose card names no target set takes **enemies**,
  except where it says "creatures in the burst" outright;
* a recharge or encounter attack says `Damage(..., kind=LIMITED)`, a minion's
  flat damage `Damage("", n, kind=MINION)`;
* `half_on_miss=True` is card data only -- a Miss line is also written as
  `else: c.hit(half=True)`.

Lurkers lean on concealment, invisibility and combat-advantage riders more
than any other role, and this file leans on `level_02..04/lurkers_sa.py` and
`level_03/skirmishers.py` for the standing shapes those sweeps already named:
`_vanish_until_it_swings` (roll-gated invisibility with a clock),
`_vanish_until_struck` (the same, ending on being hit too),
`_edge_damage` (1d6 extra against a combat-advantage target),
`_blind_to_me` / `_cannot_see_me_in_reach` (the target redirect for "a
creature that cannot see it"), `_triggering_enemy`, `_recharge_when_using`
and `_is_bloodied`.

One block, `m6530`, is a two-form body-snatcher (an ooze wearing a dead body).
Which form it is in is tracked here with a single effect label, `_R28` --
its presence means the body, its absence means the ooze -- since the two rows
that flip it (`m6530a6`, `m6530a7`) are in this file and can set and clear
their own marker without a new verb.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.brutes_sa import _crit_line
from combat_engine.content.monsters.level_01.skirmishers_sa import _moved_far
from combat_engine.content.monsters.level_02.artillery_sa import _saves_off_prone
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _edge_damage,
    _recharge_when_using,
    _triggering_enemy,
)
from combat_engine.content.monsters.level_02.skirmishers_sa import (
    _aura_holds,
    _melee_only,
)
from combat_engine.content.monsters.level_03.lurkers_sa import _my_captive_escaped
from combat_engine.content.monsters.level_03.skirmishers import (
    _is_bloodied,
    _vanish_until_it_swings,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Position,
    Ranged,
    Relation,
    Square,
    Target,
    Usage,
    When,
    Window,
    World,
    distance,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackRolled,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    Dropped,
    Escaped,
    Hit,
    InitiativeRolled,
    Moved,
    PowerUsed,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import cover_between, hidden_from, moving_as
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, by_power, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _not_grabbing(world: World, eid: int) -> bool:
    """"Must have no creature grabbed." `c.grabbing` is on `Cast`; a gate has
    only `(world, eid)`, so the relation is read straight off `relations`."""
    return not world.relations.targets(Relation.GRABBED_BY, eid)


def _landed_with(ref: str) -> Any:
    """"Must have hit this turn with <ref>." Read off the log rather than a
    flag laid and lifted by hand -- a flag would need its own reset watch for
    a fact the log already answers, the same shape `_hit_me_since_my_turn`
    uses two levels down."""

    def gate(world: World, eid: int) -> bool:
        for ev in reversed(world.bus.log):
            if isinstance(ev, TurnStart) and ev.actor == eid and not ev.ghost:
                return False
            if isinstance(ev, Hit) and ev.attacker == eid and ev.power == ref:
                return True
        return False

    return gate


_DISLIKED_ROLL = "it makes an attack roll and dislikes the result"


def _disliked_my_roll(world: World, me: int, ev: AttackRolled) -> bool:
    """Its own roll, and one about to come up short. Lives in the predicate
    rather than the body, so a roll that was landing anyway is not spent on."""
    result = getattr(ev, "result", None)
    return ev.attacker == me and result is not None and not result.hit


def _hides_if_it_can(c: Cast) -> None:
    """Checked, not rolled: the engine has no opposed Stealth-vs-Perception
    roll to make, so whether it has cover or concealment decides it outright
    -- the same simplification `_conceal`/`_hides_with_cover` already make
    two levels down."""
    foes = c.enemies()
    if not foes or any(cover_between(c.world, foe, c.me) is not Cover.NONE for foe in foes):
        c.hide()


# ==========================================================================
# m1137
# ==========================================================================


@power(
    "m1137a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 5),
)
def m1137a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1137a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 5),
)
def m1137a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1137a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m1137a2(c: Cast) -> None:
    """No attack line at all -- the burst rolls nothing and simply blinds."""
    c.blinded(until=When.SAVE_ENDS)


@power(
    "m1137a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m1137a3(c: Cast) -> None:
    c.shift(1)
    c.conceal(until=When.EONT)


@power(
    "m1137a4",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1137a4(c: Cast) -> None:
    _edge_damage(c)


@power(
    "m1137a5",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1137a5(c: Cast) -> None:
    c.bonus(AC, 4, on=c.me, until=When.EOT, when=lambda ctx: bool(ctx.get("opportunity")))
    me = c.me
    c.move(4)
    for foe in c.enemies():
        if c.adjacent_to(foe, me):
            c.gains_advantage(lambda _ctx: True, until=When.EONT, on=foe)


# ==========================================================================
# m115702
# ==========================================================================


@power(
    "m115702a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m115702a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115702a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=8),
)
def m115702a1(c: Cast) -> None:
    """The charm is one hold on the victim, dropped and relaid rather than
    stacked if it is used again -- the card charms one creature at a time.
    The retaliation half ("half damage to it, half to the charmed creature,
    and a forced free attack when the attacker is adjacent") is a watch kept
    on the caster and torn down with the hold, found again each blow by its
    label rather than a reference carried between uses.
    """
    me = c.me
    victim = c.target
    if victim is None or not c.strike():
        return
    c.pull(5, on=victim)
    for eff in list(c.world.effects.of(me)):
        if eff.label == f"{c.ref} charm":
            c.world.effects.end(eff, "recharmed")
    hold = c.effect(f"{c.ref} charm", until=When.ENCOUNTER, on=victim)
    if hold is None:
        return
    c.immobilized(on=victim, until=When.ENCOUNTER)
    held = c.cannot_attack(on=victim, against=me, until=When.ENCOUNTER)
    if held is not None:
        hold.on_end.append(lambda: c.world.effects.end(held, "charm ended"))

    def broke(ev: Moved) -> None:
        if ev.actor not in (me, victim):
            return
        if not c.adjacent_to(victim, me):
            c.world.effects.end(hold, "no longer adjacent")

    guard = c.watch(Moved, broke, until=When.ENCOUNTER, on=me, label=f"{c.ref} charm watch")
    hold.on_end.append(lambda: c.world.effects.end(guard, "charm ended"))

    def shared(ev: DamageRolled) -> None:
        if ev.target != me or hold not in c.world.effects.of(victim):
            return
        from combat_engine.engine import get

        row = get(getattr(ev, "power", "") or "")
        if row is None or row.reach.kind not in ("melee", "ranged"):
            return
        spared = c.halve(ev)
        attacker = getattr(ev, "source", None) or getattr(ev, "attacker", None)
        if spared > 0:
            c.flat(spared, on=victim)
        if attacker is not None and c.adjacent_to(attacker, victim):
            c.grant_attack(victim, on=attacker)

    relay = c.watch(
        DamageRolled, shared, until=When.ENCOUNTER, on=me, window=Window.BEFORE,
        label=f"{c.ref} charm relay",
    )
    hold.on_end.append(lambda: c.world.effects.end(relay, "charm ended"))


def _near_a_tree(world: World, eid: int) -> bool:
    """"Adjacent to a tree or a Large plant." `query.scenery` reads the first
    half; the second has no match -- a Large *creature* of the plant kind is
    not scenery -- so it is not asked, which narrows the gate rather than
    loosening it."""
    from combat_engine.engine.query import scenery

    return bool(scenery(world, "tree", within=1, of=eid))


@power(
    "m115702a2",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    requires=_near_a_tree,
    requires_text="it must be adjacent to a tree or a Large plant",
    dropped=("c.is_kind(size=)",),
)
def m115702a2(c: Cast) -> None:
    """The "or a Large plant" half of the Requirement cannot be asked: there
    is no size-and-kind query to find a Large plant creature standing beside
    it, only `c.is_kind` for the word alone."""
    c.teleport(8)
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == "m115702a1 charm":
            victim = eff.owner
            c.teleport(1, who=victim, to=c.here)


@power(
    "m115702a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m115702a3(c: Cast) -> None:
    """Deliberately inert. The disguise changes how the creature looks and
    nothing it can do; the DC 27 Insight check to see through it is not
    rolled on a board that already knows what stands on it."""


# ==========================================================================
# m115741
# ==========================================================================


@power(
    "m115741a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m115741a0(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            near = len([a for a in c.allies() if c.adjacent_to(a, victim)])
            if near:
                c.flat(2 * near)


@power(
    "m115741a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    no_provoke=True,
)
def m115741a1(c: Cast) -> None:
    c.move(c.speed_of(), at="fly")
    foe = next((f for f in c.enemies() if c.adjacent(f)), None)
    if foe is not None:
        c.use_power("m115741a0", on=foe)


@power(
    "m115741a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF)
def m115741a2(c: Cast) -> None:
    """Tremorsense 10 comes with the form, as the card prints it.

    "Cannot take actions except to end the effect" is the shape
    `level_09/lurkers.py` already settled: `Condition.STUNNED` would make the
    printed way out unreachable, so its own attacks are taken away instead and
    given back when the form ends."""
    me, ref = c.me, c.ref
    shape = c.form(until=When.ENCOUNTER, revert=MINOR, label=ref)
    for held in (
        c.resist(20, on=me, until=When.ENCOUNTER),
        c.forbid("m115741a0", on=me, until=When.ENCOUNTER),
        c.forbid("m115741a1", on=me, until=When.ENCOUNTER),
        c.no_basic(on=me, until=When.ENCOUNTER),
    ):
        if held is not None:
            shape.on_end.append(lambda h=held: c.world.effects.end(h, "form ended"))

    def pulse(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost and shape in c.world.effects.of(me):
            c.temp_hp(5, on=me)

    watch = c.watch(TurnStart, pulse, until=When.ENCOUNTER, on=me, label=f"{ref} pulse")
    shape.on_end.append(lambda: c.world.effects.end(watch, "form ended"))
    shape.on_end.append(lambda: c.bonus("damage", 15, on=me, until=When.EONT, once=True))


# ==========================================================================
# m115777
# ==========================================================================


@power(
    "m115777a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115777a0(c: Cast) -> None:
    me = c.me

    def rolled(ev: InitiativeRolled) -> None:
        if ev.actor == me:
            _hides_if_it_can(c)

    c.watch(InitiativeRolled, rolled, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} open")


@power(
    "m115777a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
)
def m115777a1(c: Cast) -> None:
    me = c.me
    victim = c.target
    unseen = victim is not None and me in hidden_from(c.world, victim)
    if c.strike():
        if unseen:
            c.damage("4d6", 4)
        else:
            c.hit()


@power(
    "m115777a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 5),
)
def m115777a2(c: Cast) -> None:
    me = c.me
    victim = c.target
    unseen = victim is not None and me in hidden_from(c.world, victim)
    if c.strike():
        if unseen:
            c.damage("4d4", 5)
        else:
            c.hit()


@power(
    "m115777a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m115777a3(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


@power(
    "m115777a4",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger="it takes damage",
    on=Trigger(DamageApplied, targets_me, "it takes damage"),
)
def m115777a4(c: Cast) -> None:
    _vanish_until_it_swings(c, When.EONT)


# ==========================================================================
# m1168
# ==========================================================================


@power(
    "m1168a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 3),
)
def m1168a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1168a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1168a1(c: Cast) -> None:
    """"At any point during the move" is abstracted, as `_mobile_attack`
    already abstracts it two levels down: the shift happens first and the two
    swings land on whoever is adjacent afterwards, each at a different
    target."""
    c.shift(8)
    foes = sorted({f for f in c.enemies() if c.adjacent(f)}, key=c.distance)[:2]
    for foe in foes:
        c.use_power("m1168a0", on=foe)
        if c.landed:
            c.slide(3, on=foe)


@power(
    "m1168a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1168a2(c: Cast) -> None:
    me = c.me
    _moved_far(c, me, 3, lambda: c.invisible(on=me, until=When.EONT))


@power(
    "m1168a3",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1168a3(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, once=True,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


# ==========================================================================
# m1480
# ==========================================================================


@power(
    "m1480a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 3, dtype=DamageType.ACID),
)
def m1480a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1480a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(6),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.ACID, kind=LIMITED),
)
def m1480a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.blinded(until=When.SAVE_ENDS)


@power(
    "m1480a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m1480a2(c: Cast) -> None:
    c.invisible(until=When.EONT)
    c.move(6)


@power(
    "m1480a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1480a3(c: Cast) -> None:
    me = c.me

    def bonus_hit(ev: Hit) -> None:
        if ev.attacker != me:
            return
        victim = ev.target
        if victim is not None and victim in hidden_from(c.world, me):
            c.flat(c.roll("1d10"), on=victim)
            c.dazed(on=victim, until=When.SAVE_ENDS)

    c.watch(Hit, bonus_hit, until=When.ENCOUNTER, on=me, label=f"{c.ref} unseen")


# ==========================================================================
# m1986
# ==========================================================================


@power(
    "m1986a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1986a0(c: Cast) -> None:
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.RADIANT:
            c.forbid("m1986a4", on=me, until=When.EONT)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label=f"{c.ref} scorched")


@power(
    "m1986a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6, dtype=DamageType.NECROTIC),
)
def m1986a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1986a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(2),
    target=Target(
        side="enemy",
        count=1,
        label="one creature granting combat advantage to it",
        grants_ca=True,
    ),
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m1986a2(c: Cast) -> None:
    """"Loses a healing surge" is the *target* paying, and `c.spend_surge`
    defaults to the caster -- so that one stays named. #401."""
    me = c.me
    label = f"{c.ref} recharge"
    if not any(eff.label == label for eff in c.world.effects.of(me)):

        def bled(ev: Bloodied) -> None:
            if c.distance(ev.actor) <= 2:
                c.restore_use(c.ref, on=me)

        c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, label=label)

    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)
        c.spend_surge(on=c.target)
        c.heal(12, on=me)


@power(
    "m1986a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m1986a3(c: Cast) -> None:
    """Deliberately inert: the disguise only changes how it looks, and
    nothing a fight rolls cares."""


@power(
    "m1986a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m1986a4(c: Cast) -> None:
    me = c.me
    held = [
        h
        for h in (
            c.insubstantial(on=me, until=When.ENCOUNTER),
            c.mode("fly", 6, on=me, until=When.ENCOUNTER),
            c.hover(on=me, until=When.ENCOUNTER),
            c.phasing(on=me, until=When.ENCOUNTER),
        )
        if h is not None
    ]

    def end_all(reason: str) -> None:
        for h in held:
            c.world.effects.end(h, reason)

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == me:
            end_all("it attacked")

    def afflicted(ev: ConditionApplied) -> None:
        if ev.target == me and ev.condition in (
            Condition.DAZED, Condition.STUNNED, Condition.UNCONSCIOUS,
        ):
            end_all("it was afflicted")

    c.watch(
        AttackRolled, swung, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} unwind",
    )
    c.watch(
        ConditionApplied, afflicted, until=When.ENCOUNTER, on=me, once=True,
        label=f"{c.ref} unwind2",
    )


# ==========================================================================
# m3187
# ==========================================================================


@power(
    "m3187a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d4", 2, dtype=DamageType.NECROTIC),
)
def m3187a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


def _has_an_opening(world: World, eid: int) -> bool:
    from combat_engine.engine.query import enemies, has_combat_advantage

    return any(has_combat_advantage(world, eid, foe) for foe in enemies(world, eid))


def _sleep_chain(c: Cast, victim: int) -> None:
    def to_stun(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        held = c.stunned(on=victim, until=When.SAVE_ENDS, )
        if held is not None:
            held.escalate = to_unconscious

    def to_unconscious(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        held = c.unconscious(on=victim, until=When.SAVE_ENDS)
        if held is not None:
            held.on_end.append(lambda: c.dazed(on=victim, until=When.EONT))

    held = c.dazed(on=victim, until=When.SAVE_ENDS)
    if held is not None:
        held.escalate = to_stun


@power(
    "m3187a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("2d4", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
    requires=_has_an_opening,
    requires_text="it must have combat advantage against a target",
)
def m3187a1(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    _sleep_chain(c, victim)


@power(
    "m3187a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3187a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", dtype=DamageType.NECROTIC, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")) and _melee_only(ctx),
    )


@power(
    "m3187a3",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3187a3(c: Cast) -> None:
    c.shift(3)


# ==========================================================================
# m3528
# ==========================================================================


@power(
    "m3528a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 2, dtype=DamageType.NECROTIC),
)
def m3528a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3528a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d8", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3528a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.prone()


@power(
    "m3528a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3528a2(c: Cast) -> None:
    """Unseen until it swings or is struck, except that using `m3528a1` does
    not give it away -- a one-ref exception `_vanish_until_struck` has no room
    for, so the watches are written out rather than shared."""
    me = c.me
    veil = c.invisible(on=me, until=When.ENCOUNTER)
    if veil is None:
        return

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == me and ev.power != "m3528a1":
            c.world.effects.end(veil, "it attacked")

    def struck(ev: Hit) -> None:
        if ev.target == me:
            c.world.effects.end(veil, "it was hit")

    for event, fn in ((AttackRolled, swung), (Hit, struck)):
        seen = c.watch(event, fn, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} unseen")
        veil.on_end.append(lambda s=seen: c.world.effects.end(s, "no longer unseen"))


@power(
    "m3528a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3528a3(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d8", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


# ==========================================================================
# m3976
# ==========================================================================


@power(
    "m3976a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
)
def m3976a0(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.penalty(WILL, 2, on=victim, until=When.EONT)


@power(
    "m3976a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m3976a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.invisible(to=victim, on=c.me, until=When.EONT)


@power(
    "m3976a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MINOR,
    reach=CloseBurst(1),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
    dropped=("c.spend_surge(unless=)",),
)
def m3976a2(c: Cast) -> None:
    """The toll on attacking her during this window -- spend a healing surge
    and heal nothing for it -- has no hook: nothing here makes spending a
    surge a *cost of attacking*, only a thing a creature may choose on its
    own turn. The combat-advantage half plays in full."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.grants_advantage(on=victim, until=When.EONT)


@power(
    "m3976a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3976a3(c: Cast) -> None:
    me = c.me

    def opening_hit(ev: Hit) -> None:
        if ev.attacker == me and ev.target is not None and getattr(ev.result, "advantage", False):
            c.ongoing(5, DamageType.NECROTIC, on=ev.target)

    c.watch(Hit, opening_hit, until=When.ENCOUNTER, on=me, label=f"{c.ref} opening")


@power(
    "m3976a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m3976a4(c: Cast) -> None:
    """Deliberately inert: a DC 17 Insight check to pierce an illusion with no
    combat payload of its own."""


# ==========================================================================
# m4210
# ==========================================================================


@power(
    "m4210a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 4),
)
def m4210a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4210a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 6),
)
def m4210a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4210a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=0,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes damage",
    on=Trigger(DamageApplied, targets_me, "it takes damage"),
    recharge_when=Trigger(PowerUsed, by_power("m4210a3"),
                          "when it uses m4210a3"),
)
def m4210a2(c: Cast) -> None:
    _recharge_when_using(c, "m4210a3")
    c.shift(c.speed_of())
    _hides_if_it_can(c)


@power(
    "m4210a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
    recharge_when=Trigger(PowerUsed, by_power("m4210a2"),
                          "when it uses m4210a2"),
)
def m4210a3(c: Cast) -> None:
    _recharge_when_using(c, "m4210a2")
    c.bonus(
        "damage", 0, dice="3d6", dtype=DamageType.LIGHTNING, on=c.me, until=When.SONT,
        when=_melee_only,
    )


@power(
    "m4210a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4210a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m4210a5",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4210a5(c: Cast) -> None:
    me = c.me
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence, 2, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_trap(ctx.get("attacker")),
        )


# ==========================================================================
# m4241
# ==========================================================================


@power(
    "m4241a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m4241a0(c: Cast) -> None:
    """"If the target moves more than 2 squares on its turn" is measured from
    the square it occupies the next time its own turn opens, not from the
    instant it was hit -- a judgement call, since nothing forces the two to
    coincide, but the closer of the two readings available."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me
    state: dict[str, Square | None] = {"from": None}

    def dawn(ev: TurnStart) -> None:
        if ev.actor == victim and not ev.ghost:
            pos = c.world.get(victim, Position)
            state["from"] = pos.square if pos else None

    def moved(ev: Moved) -> None:
        if ev.actor != victim or state["from"] is None:
            return
        pos = c.world.get(victim, Position)
        if pos is not None and distance(pos.square, state["from"]) > 2:
            c.flat(c.roll("1d6"), on=victim)

    c.watch(TurnStart, dawn, until=When.EONT, on=me, label=f"{c.ref} chase")
    c.watch(Moved, moved, until=When.EONT, on=me, once=True, label=f"{c.ref} chase move")


@power(
    "m4241a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one creature that cannot see it",
        relation=Relation.HIDDEN_FROM,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
)
def m4241a1(c: Cast) -> None:
    """The restriction is the target line now, routed through
    `query.unseen_by` rather than the stored triple, so an enemy seeing through
    the hiding is excluded and one whose sight range cannot reach is included.
    #401."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
        c.ongoing(5)


@power(
    "m4241a2",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=Target(side="other", count=1, label="one dying creature"),
    todo=("c.death_save()",),
)
def m4241a2(c: Cast) -> None:
    """Refused in play: a monster never rolls a death save at all -- only a
    character does, per `Health`'s own comment -- so there is no verb to force
    one here and nothing of the row plays."""


@power(
    "m4241a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_DISLIKED_ROLL,
    on=Trigger(AttackRolled, _disliked_my_roll, _DISLIKED_ROLL),
)
def m4241a3(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m4241a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m4241a4(c: Cast) -> None:
    _vanish_until_it_swings(c, When.ENCOUNTER)
    c.shift(1)


@power(
    "m4241a5",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4241a5(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5081
# ==========================================================================


@power(
    "m5081a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5081a0(c: Cast) -> None:
    me = c.me
    for defence in (AC, REF):
        c.bonus(defence, 2, on=me, until=When.ENCOUNTER, when=lambda _ctx: bool(c.grabbing()))


@power(
    "m5081a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("", 5, kind=MINION),
)
def m5081a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if victim in c.grabbing() or c.strike():
        c.hit()
    else:
        return
    c.grab(on=victim, dc=15)
    me = c.me
    label = f"{c.ref} suck"
    if not any(eff.label == label for eff in c.world.effects.of(me)):

        def squeeze(ev: TurnStart) -> None:
            if ev.actor != victim or ev.ghost:
                return
            from combat_engine.content.monsters.level_02.soldiers_sa import _ref_of

            count = len(
                [
                    g
                    for g in c.world.relations.sources(Relation.GRABBED_BY, victim)
                    if _ref_of(c, g) == "m5081"
                ]
            )
            if count:
                c.flat(count, on=victim)

        c.watch(TurnStart, squeeze, until=When.ENCOUNTER, on=me, label=label)


# ==========================================================================
# m5302
# ==========================================================================


@power(
    "m5302a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5302a0(c: Cast) -> None:
    """Already true: nothing in `actions._charges` restricts a charge by
    movement mode, so burrowing grants nothing it did not already have."""
    c.note(f"{c.ref}: nothing stops it from charging while burrowing")


@power(
    "m5302a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("query.in_sunlight(world, square)",),
)
def m5302a1(c: Cast) -> None:
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.RADIANT:
            c.penalty("attack", 2, on=me, until=When.EONT)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label=f"{c.ref} sunburn")


@power(
    "m5302a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m5302a2(c: Cast) -> None:
    """A plain grab and nothing else printed, so there was no dropped clause --
    the `c.grab(dc=)` marker named a number this card does not carry."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.grab(on=victim)


@power(
    "m5302a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy",
        count=1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6, dtype=DamageType.POISON),
)
def m5302a3(c: Cast) -> None:
    """"If the target is already slowed, it is instead immobilized" is a swap
    and not a second condition, so the slow is cured before the hold goes on --
    two counts standing at once would make the clear-up wrong either way."""
    if not c.strike():
        return
    c.hit()
    if c.is_(Condition.SLOWED):
        c.cure(Condition.SLOWED)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m5302a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1, label="one immobilized creature or one creature grabbed by it",
    ),
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d8", 6),
    dropped=("Target.any_of",),
)
def m5302a4(c: Cast) -> None:
    """**Deliberately not moved onto `Target.conditions` either.** The printed
    line is a *disjunction across two kinds* -- immobilized (a condition) or
    grabbed by it (a relation) -- and every target field narrows the pool, so
    setting one of them throws away the other branch of the same sentence. The
    condition filter now exists; the one remaining gap is a way to say "either
    of these", so the re-pick stays in the body. #401.
    """
    victim = c.target
    held_already = victim is not None and (
        c.is_(Condition.IMMOBILIZED, on=victim) or victim in c.grabbing()
    )
    if not held_already:
        victim = next(
            (f for f in c.enemies() if c.is_(Condition.IMMOBILIZED, on=f) or f in c.grabbing()),
            None,
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    held = c.condition(
        Condition.REMOVED, on=victim, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED),
    )
    if held is not None:
        held.on_end.append(lambda: c.immobilized(on=victim, until=When.SAVE_ENDS))


# ==========================================================================
# m5311
# ==========================================================================


@power(
    "m5311a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5311a0(c: Cast) -> None:
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype is DamageType.RADIANT:
            c.forbid("m5311a2", on=me, until=When.EONT)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label=f"{c.ref} scorched")


def _unseen_at_dawn(c: Cast) -> frozenset[int]:
    """"Could not see it at the start of its turn" wants a snapshot taken
    then, not a fresh read at attack time: `resolve.attack` has already
    cleared the live state for whoever just swung. The snapshot is kept as an
    attribute on the watch's own effect, found again by label, since the body
    runs on a different call than the one that armed the watch."""
    me, label = c.me, f"{c.ref} dawn"
    for eff in c.world.effects.of(me):
        if eff.label == label:
            return getattr(eff, "snapshot", frozenset())

    def dawn(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            holder.snapshot = frozenset(hidden_from(c.world, me))

    holder = c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=label)
    holder.snapshot = frozenset()
    return holder.snapshot


@power(
    "m5311a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 3),
)
def m5311a1(c: Cast) -> None:
    victim = c.target
    snapshot = _unseen_at_dawn(c)
    if c.strike():
        c.hit()
        if victim is not None and victim in snapshot:
            c.flat(c.roll("3d6"), dtype=DamageType.NECROTIC)
        else:
            c.flat(c.roll("1d6"), dtype=DamageType.NECROTIC)


@power(
    "m5311a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION, Keyword.ZONE],
    dropped=("c.zone(exempt=)",),
)
def m5311a2(c: Cast) -> None:
    """The sight-blocking half of the zone catches this creature too --
    `c.zone(blocks_sight=True)` is terrain and blinds both sides -- so the
    exemption it prints for itself is the gap. The blind itself is exempted,
    laid per occupant rather than by the zone."""
    c.teleport(5)
    area = spread({c.here}, 1)
    zone = c.zone(area, blocks_sight=True, until=When.SONT, label=c.ref)
    me = c.me

    def blind(who: int) -> Effect | None:
        return None if who == me else c.blinded(on=who, until=When.ENCOUNTER)

    _aura_holds(c, zone, blind)


# ==========================================================================
# m5317
# ==========================================================================


@power(
    "m5317a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 3),
)
def m5317a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5317a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 3),
)
def m5317a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m5317a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5317a2(c: Cast) -> None:
    me = c.me
    melee_foe = next((f for f in c.enemies() if c.adjacent(f)), None)
    ranged_foe = min(
        (f for f in c.enemies() if f != melee_foe), key=c.distance, default=None,
    )
    if melee_foe is not None:
        c.use_power("m5317a0", on=melee_foe)
    if ranged_foe is not None:
        if melee_foe is not None:
            c.no_provoke(from_=melee_foe, on=me, until=When.EOT)
        c.use_power("m5317a1", on=ranged_foe)


@power(
    "m5317a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(3),
    target=Target(side="enemy", everyone=True, label="enemies in the burst"),
    attack=Attack(vs=WILL, printed=6),
)
def m5317a3(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(until=When.EONT)


# ==========================================================================
# m5635
# ==========================================================================


@power(
    "m5635a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5635a0(c: Cast) -> None:
    c.bonus(
        "damage", 5, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None
            and len([a for a in c.allies() if c.adjacent_to(a, ctx["target"])]) >= 2
        ),
    )


@power(
    "m5635a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
)
def m5635a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _burrowing_and_free(world: World, eid: int) -> bool:
    return moving_as(world, eid, "burrow") and _not_grabbing(world, eid)


@power(
    "m5635a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
    requires=_burrowing_and_free,
    requires_text="it must be burrowing and have no creature grabbed",
)
def m5635a2(c: Cast) -> None:
    """"Ignoring cover and concealment" is passed as far as `c.strike` goes --
    `ignore_cover=True` -- which does not separately carve out concealment;
    the two swings are rolled here rather than through `m5635a1` so that flag
    can be set."""
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        if c.strike(on=victim, ignore_cover=True):
            c.hit(on=victim)
            hits += 1
    if hits == 2:
        c.grab(on=victim, dc=15)
        c.condition(
            Condition.RESTRAINED, on=victim, until=When.SAVE_ENDS,
            ongoing=(5, DamageType.UNTYPED),
        )


# ==========================================================================
# m5838
# ==========================================================================


@power(
    "m5838a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d4", 6),
)
def m5838a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5838a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=8),
    requires=_not_grabbing,
    requires_text="it must not be grabbing a creature",
    dropped=("c.cover_from()",),
)
def m5838a1(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    held = c.grab(on=victim, dc=22)
    if held is None:
        return
    c.immovable(on=c.me, until=When.EONT)
    c.immovable(on=victim, until=When.EONT)
    timer = c.effect(f"{c.ref} grab clock", until=When.EONT, on=c.me)
    if timer is not None:
        timer.on_end.append(lambda: c.world.effects.end(held, "grab timed out"))


@power(
    "m5838a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy",
        count=1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 5),
)
def m5838a2(c: Cast) -> None:
    """"The grab then ends" is this creature's own hold, found by the label
    m5838a1 laid on the victim."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.ongoing(10)
    for eff in list(c.world.effects.of(victim)):
        if eff.label == "m5838a1 grab":
            c.world.effects.end(eff, "grab released")


@power(
    "m5838a3",
    level=5,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy escapes its grab",
    on=Trigger(Escaped, _my_captive_escaped, "an enemy escapes its grab"),
)
def m5838a3(c: Cast) -> None:
    ev = c.trigger
    foe = getattr(ev, "actor", None)
    if foe is not None:
        c.use_power("m5838a0", on=foe)


# ==========================================================================
# m6445
# ==========================================================================


@power(
    "m6445a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6445a0(c: Cast) -> None:
    """Deliberately inert, as the matching trait two levels down: the whole
    printed trait is a check to notice the creature is a creature, and a
    board that has it placed on it already knows."""


@power(
    "m6445a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=Target(
        side="any", everyone=True,
        label="nonplant creatures in the burst",
        kinds_without=frozenset({"plant"}),
    ),
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("", 3, dtype=DamageType.THUNDER, kind=MINION),
)
def m6445a1(c: Cast) -> None:
    """"Nonplant" is the negative field, so the caster -- which is one -- drops
    out of its own burst and the body's guard came out. #401."""
    if c.first:
        c.as_basic(c.ref, on=c.me, until=When.ENCOUNTER)
    if c.strike():
        c.hit()


@power(
    "m6445a2",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6445a2(c: Cast) -> None:
    """Deliberately inert. The whole effect is a noise heard 20 squares off;
    nothing on a board hears, and no creature, square or hold changes. The
    trigger is left undeclared for the same reason -- there is nothing for it
    to fire into."""


# ==========================================================================
# m6530
# ==========================================================================

_R28 = "m6530 r28"


def _in_r28(world: World, eid: int) -> bool:
    return any(e.label == _R28 for e in world.effects.of(eid))


def _in_ooze(world: World, eid: int) -> bool:
    return not _in_r28(world, eid)


@power(
    "m6530a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.insubstantial(bypass=)",),
)
def m6530a0(c: Cast) -> None:
    """`m6530a6`/`m6530a7` end and relay this as the creature changes shape.
    `Condition.INSUBSTANTIAL` has one built-in exception -- force, and only
    when the attacker's own row grants it -- and this card wants two,
    unconditionally, which there is no hook for."""
    c.insubstantial(on=c.me, until=When.ENCOUNTER)


@power(
    "m6530a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6530a1(c: Cast) -> None:
    from combat_engine.content.monsters.level_03.brutes import _squeezes_freely

    _squeezes_freely(c)


@power(
    "m6530a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6530a2(c: Cast) -> None:
    """Regeneration 5, switched off for a turn by force or psychic."""
    heals = c.regeneration(5, until=When.ENCOUNTER, on=c.me)
    c.suspend_when(
        heals, DamageApplied,
        lambda ev: ev.target == c.me
        and bool({DamageType.FORCE, DamageType.PSYCHIC} & {ev.dtype, *ev.dtypes}),
        for_=When.EONT,
    )


@power(
    "m6530a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_in_r28,
    requires_text="it must be in r28 form",
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m6530a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6530a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=_in_ooze,
    requires_text="it must be in ooze form",
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("3d6", 2, dtype=DamageType.PSYCHIC),
)
def m6530a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6530a5",
    level=5,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, label="one creature carrying equipment"),
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d10", 4, kind=LIMITED),
    dropped=("Gear.carried",),
)
def m6530a5(c: Cast) -> None:
    """"One creature carrying equipment" is not a target line `Target` can
    narrow: `Gear` records weapons, a shield, armour, worn magic and
    ammunition and nothing for ordinary kit, so `Gear.carried` is the gap and
    the row is offered against anybody."""
    if c.strike():
        c.hit()
        held = c.slowed(until=When.SAVE_ENDS)
        if held is not None:
            c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m6530a6",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    requires=_in_ooze,
    requires_text="it must be in ooze form",
)
def m6530a6(c: Cast) -> None:
    """The intact body of a dead r28 is not a thing tracked on a board;
    nothing here enforces that one be at hand."""
    for eff in list(c.world.effects.of(c.me)):
        if Condition.INSUBSTANTIAL in eff.conditions:
            c.world.effects.end(eff, "took on r28 form")
    c.effect(_R28, until=When.ENCOUNTER, on=c.me)


@power(
    "m6530a7",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_in_r28,
    requires_text="it must be in r28 form",
)
def m6530a7(c: Cast) -> None:
    """"The r28 body falls prone in its space" is the discarded host, not a
    creature on the board, so nothing is knocked prone for it."""
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == _R28:
            c.world.effects.end(eff, "returns to ooze form")
    c.insubstantial(on=c.me, until=When.ENCOUNTER)
    c.shift(2)


@power(
    "m6530a8",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_in_r28,
    requires_text="while in r28 form, it is first bloodied",
    trigger="while in r28 form, it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m6530a8(c: Cast) -> None:
    if not _in_r28(c.world, c.me):
        return
    c.use_power("m6530a7")
    c.temp_hp(10, on=c.me)


# ==========================================================================
# m6534
# ==========================================================================


@power(
    "m6534a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6534a0(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m6534a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6534a1(c: Cast) -> None:
    c.resist_forced(1, on=c.me)


@power(
    "m6534a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6534a2(c: Cast) -> None:
    _saves_off_prone(c)


@power(
    "m6534a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d4", 5),
)
def m6534a3(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "2d8", 17)


@power(
    "m6534a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d4", 5),
)
def m6534a4(c: Cast) -> None:
    """The thrown weapon returning to hand is a flavour-only consequence --
    nothing on a board tracks ammunition for it to matter to."""
    if c.strike():
        _crit_line(c, "2d8", 17)


@power(
    "m6534a5",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
)
def m6534a5(c: Cast) -> None:
    """The printed Requirement is enforced now: it must be standing in an
    obscured square, which `c.unlit` reads. Asked in the body rather than as
    a `requires=` gate, because that is settled once when the row arms and
    the light it stands in changes as it moves."""
    me = c.me
    if not c.unlit():
        return
    veil = c.invisible(on=me, until=When.ENCOUNTER)
    if veil is not None:
        c.bonus(
            "attack", 2, on=me, kind="power", until=When.ENCOUNTER,
            when=lambda _ctx: veil in c.world.effects.of(me),
        )

        def swung(ev: AttackRolled) -> None:
            if ev.attacker == me:
                c.world.effects.end(veil, "it attacked")

        seen = c.watch(
            AttackRolled, swung, until=When.ENCOUNTER, on=me, once=True,
            label=f"{c.ref} unseen",
        )
        veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))
    if c.strike():
        c.hit()


@power(
    "m6534a6",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    requires=_landed_with("m6534a3"),
    requires_text="it must have hit this turn with m6534a3",
)
def m6534a6(c: Cast) -> None:
    c.shift(c.speed_of())


@power(
    "m6534a7",
    level=5,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_DISLIKED_ROLL,
    on=Trigger(AttackRolled, _disliked_my_roll, _DISLIKED_ROLL),
)
def m6534a7(c: Cast) -> None:
    c.reroll_attack(keep="new")


# ==========================================================================
# m6598
# ==========================================================================


@power(
    "m6598a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6598a0(c: Cast) -> None:
    me = c.me

    def mobbed(_ctx: dict[str, Any]) -> bool:
        return len([f for f in c.enemies() if c.adjacent_to(f, me)]) >= 2

    for defence in (AC, FORT, REF, WILL):
        c.penalty(defence, 4, on=me, until=When.ENCOUNTER, when=mobbed)


@power(
    "m6598a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 8),
)
def m6598a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6598a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 8),
)
def m6598a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6598a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m6598a3(c: Cast) -> None:
    me = c.me
    label = f"{c.ref} coated"
    if any(eff.label == label for eff in c.world.effects.of(me)):
        return

    def poisoned_strike(ev: Hit) -> None:
        if ev.attacker == me and ev.power in ("m6598a1", "m6598a2"):
            c.ongoing(10, DamageType.POISON, on=ev.target)

    c.watch(Hit, poisoned_strike, until=When.ENCOUNTER, on=me, once=True, label=label)


@power(
    "m6598a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=5,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger="an enemy hits it with a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits it with a melee attack"),
)
def m6598a4(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    c.bonus("attack", 2, on=c.me, until=When.EOT, once=True)
    c.use_power("m6598a1", on=foe)
    c.flat(8 if c.landed else 4, on=foe)


# ==========================================================================
# m889
# ==========================================================================


@power(
    "m889a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 2),
)
def m889a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m889a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 2, kind=LIMITED),
)
def m889a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(2)
        c.invisible(until=When.SONT)


@power(
    "m889a2",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 2),
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m889a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.adjacent_to(foe, c.me) and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m889a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m889a3(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")) and _melee_only(ctx),
    )


@power(
    "m889a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m889a4(c: Cast) -> None:
    c.heal(5, on=c.me)
