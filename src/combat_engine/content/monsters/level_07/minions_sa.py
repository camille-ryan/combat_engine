"""Monster abilities, level 7, minions.

Twenty stat blocks, thirty-six rows. Five of the twenty print no ability at
all and have nothing to decorate: m288, m421, m4876, m4917, m5046.

Conventions, inherited from the level 1-6 minion sweeps:

* a minion's damage is a flat number in the header, `Damage("", n,
  kind=MINION)`, and the body calls `c.hit()`. Its one hit point is in the
  database;
* a card printing two numbers for one blow keeps the base in the header and
  adds the difference with `c.flat`;
* "two others of its kind within N squares" counts by `Ident.ref`, because
  every creature on the board may share a type word and the sentence is
  about this stat block;
* a card that prints no range at all is melee 1; a printed band such as
  "10/20" takes the short number;
* `c.mark`, never `c.condition(Condition.MARKED, ...)`;
* "escape DC N" has nowhere to go -- the engine ends a grab or an
  escape-worded condition on a clock or a save, not a skill contest, so
  `until=When.SAVE_ENDS` stands in and the DC itself is not written, the
  same simplification the rest of the tree already takes.

Two name-shaped leaks, both written around: m3785a1 and m962a1 each print
their own ref twice in the raw text ("m3785 m3785", "blade of m962" naming
itself) -- a collective or doubled-noun extraction artefact for "it",
matched here by `Ident.ref` rather than any word.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_04.brutes import _change_shape, _in_shape
from combat_engine.content.monsters.level_06.minions_sa import _ref_of
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    EACH_OTHER,
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
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Gear,
    Keyword,
    Melee,
    Powers,
    Ranged,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import AttackDeclared, Dropped, EffectApplied, Hit
from combat_engine.engine.grid import distance
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    distance_between,
    has_combat_advantage,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

_M5783_SHAPE = "m5783a3 "
_M5783_SHAPES = ("beast", "humanoid")


def _ranged_or_area_hit(world: World, me: int, ev: Hit) -> bool:
    if ev.target != me:
        return False
    row = get(ev.power or "")
    return row is not None and row.reach.kind in ("ranged", "area_burst")


def _has_bell(world: World, eid: int) -> bool:
    """A printed "must be holding a bell", asked of `Gear` the way a javelin
    or a quarterstaff requirement elsewhere in the tree is."""
    gear = world.get(eid, Gear)
    weapon = gear.main if gear is not None else None
    return weapon is not None and (weapon.group == "bell" or "bell" in weapon.properties)


def _slide_near_us(c: Cast, victim: int, squares_: int) -> None:
    """Slide up to `squares_` squares, ending adjacent to the caster or one
    of its allies -- the nearest such square to where the victim already
    stands, the same "pick the nearer qualifying square" shape the level-6
    brute sweep's `_slide_toward` uses for a single anchor."""
    anchors = {sq for a in (c.me, *c.allies()) for sq in squares(c.world, a)}
    mine = next(iter(squares(c.world, victim)), None)
    if mine is None or not anchors:
        return
    ring = {sq for s in anchors for sq in spread({s}, 1)} - anchors
    if not ring:
        return
    dest = min(ring, key=lambda sq: distance(sq, mine))
    c.slide(squares_, on=victim, to=dest)


# ==========================================================================
# m115803
# ==========================================================================


@power(
    "m115803a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
)
def m115803a0(c: Cast) -> None:
    me = c.me

    def charged(ev: Hit) -> None:
        if ev.attacker == me and bool(getattr(ev, "charge", False)) and ev.target is not None:
            c.grants_advantage(on=ev.target, to="team", until=When.EONT)

    c.watch(Hit, charged, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m115803a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 7, kind=MINION),
)
def m115803a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m115883
# ==========================================================================


@power(
    "m115883a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 7, kind=MINION),
)
def m115883a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m115883a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 7, kind=MINION),
)
def m115883a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


# ==========================================================================
# m3453
# ==========================================================================


@power(
    "m3453a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 5, kind=MINION),
)
def m3453a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3453a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 5, kind=MINION),
)
def m3453a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3453a2",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="the hobgoblin becomes subject to an effect",
    on=Trigger(EffectApplied, targets_me, "it becomes subject to an effect"),
)
def m3453a2(c: Cast) -> None:
    ev = c.trigger
    if isinstance(ev, EffectApplied) and ev.save_ends:
        c.save(on=c.me, against=ev.label)


@power("m3453a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3453a3(c: Cast) -> None:
    """Read as a trait -- an always-on bonus conditioned on an ally of its
    own kind standing beside it, not a chosen encounter power."""
    me = c.me
    c.bonus(
        AC, 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: any(
            w != me and _ref_of(c, w) == "m3453" and c.adjacent_to(w, me) for w in c.allies()
        ),
    )


# ==========================================================================
# m3475
# ==========================================================================


@power(
    "m3475a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 5, kind=MINION),
)
def m3475a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


_M3475_COULD_HIT_ME = (
    "an ally within 5 squares is the target of an attack that could instead target the m3475"
)


def _could_also_target_me(world: World, me: int, ev: AttackDeclared) -> bool:
    """"Could instead target the m3475" -- the board has no way to re-run a
    declared attack's own legality check against a different creature, so
    this is read as the m3475 standing within the same distance of the
    attacker as the ally it is covering, the nearest askable stand-in."""
    attacker, victim = ev.attacker, ev.target
    if attacker is None or victim is None or victim == me or attacker == me:
        return False
    if team(world, victim) is not team(world, me):
        return False
    return distance_between(world, me, victim) <= 5 and distance_between(world, me, attacker) <= 5


@power(
    "m3475a1",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=WILL, printed=10),
    trigger=_M3475_COULD_HIT_ME,
    on=Trigger(AttackDeclared, _could_also_target_me, _M3475_COULD_HIT_ME),
)
def m3475a1(c: Cast) -> None:
    """A single-target attack is redirected onto the m3475 outright.
    A burst or a blast has nowhere to redirect -- it already has its whole
    target list -- so "include the m3475" instead appends it to that list,
    which is what `c.add_target` is for."""
    ev = c.trigger
    attacker = ev.attacker if isinstance(ev, AttackDeclared) else None
    if attacker is None or not c.strike(on=attacker):
        return
    row = get(ev.power or "") if isinstance(ev, AttackDeclared) else None
    if row is not None and row.reach.kind in ("close_burst", "close_blast", "area_burst"):
        c.add_target(c.me)
    else:
        c.redirect(to=c.me)


# ==========================================================================
# m3785
# ==========================================================================


@power(
    "m3785a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 6, kind=MINION),
)
def m3785a0(c: Cast) -> None:
    """"8 damage on a critical hit" is a fixed number, not the automatic
    double of a flat minion blow with no dice to double."""
    if not c.strike():
        return
    if c.crit:
        c.flat(8)
    else:
        c.hit()


@power(
    "m3785a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m3785a1(c: Cast) -> None:
    """The doubled ref in the raw text ("m3785 m3785") is read as "it"."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None:
            return
        known = c.world.get(me, Powers)
        if known is None or ev.power != known.basic:
            return
        extra = len(
            [a for a in c.allies() if _ref_of(c, a) == "m3785" and c.adjacent_to(a, ev.target)]
        )
        if extra:
            c.flat(extra, dtype=DamageType.FIRE, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3785a2",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m3785a2(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m5323
# ==========================================================================


@power("m5323a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5323a0(c: Cast) -> None:
    me = c.me
    for which in ALL_DEFENCES:
        c.bonus(
            which, 2, on=me, until=When.ENCOUNTER,
            when=lambda ctx: bool(c.within(1, of=me, side="ally")),
        )


@power("m5323a1", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5323a1(c: Cast) -> None:
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=ctx.get("target")),
    )


@power(
    "m5323a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 7, kind=MINION),
)
def m5323a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5323a3",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=10),
    requires=_has_bell,
    requires_text="the m5323 must be holding a bell",
)
def m5323a3(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        _slide_near_us(c, victim, 5)


# ==========================================================================
# m5573
# ==========================================================================


@power("m5573a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5573a0(c: Cast) -> None:
    """"+1 to attack rolls for every ally adjacent to the target" is counted
    fresh at the moment the attack is declared -- before the roll, which is
    when the printed bonus has to apply -- and laid as a one-use bonus
    scoped to that declared target so a second use with a different count
    is not polluted by the first."""
    me = c.me

    def declared(ev: AttackDeclared) -> None:
        if ev.attacker != me or ev.target is None:
            return
        count = len([a for a in c.allies() if c.adjacent_to(a, ev.target)])
        if count:
            c.bonus(
                "attack", count, on=me, until=When.EONT, once=True,
                when=lambda ctx, t=ev.target: ctx.get("target") == t,
            )

    c.watch(AttackDeclared, declared, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5573a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 8, kind=MINION),
)
def m5573a1(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is not None and (
        c.is_(Condition.GRABBED, on=victim) or c.is_(Condition.UNCONSCIOUS, on=victim)
    ):
        c.flat(2)
    c.grab()


# ==========================================================================
# m5615
# ==========================================================================


@power(
    "m5615a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 6, kind=MINION),
)
def m5615a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SONT)


# ==========================================================================
# m5783
# ==========================================================================


@power("m5783a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5783a0(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


@power(
    "m5783a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 7, kind=MINION),
    requires=_in_shape(_M5783_SHAPE, "beast"),
    requires_text="it must be in beast form",
)
def m5783a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m5783a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 5, kind=MINION),
    requires=_in_shape(_M5783_SHAPE, "humanoid"),
    requires_text="it must be in humanoid form",
)
def m5783a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5783a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m5783a3(c: Cast) -> None:
    _change_shape(c, _M5783_SHAPE, _M5783_SHAPES)


# ==========================================================================
# m5873
# ==========================================================================


@power(
    "m5873a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 7, dtype=DamageType.NECROTIC, kind=MINION),
)
def m5873a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5873a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("", 7, dtype=DamageType.THUNDER, kind=MINION),
)
def m5873a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


# ==========================================================================
# m6420
# ==========================================================================


@power(
    "m6420a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 7, kind=MINION),
)
def m6420a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m6420a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with a ranged attack or an area attack",
    on=Trigger(Hit, _ranged_or_area_hit, "an enemy hits it with a ranged or area attack"),
)
def m6420a1(c: Cast) -> None:
    c.reroll_attack(keep="new")


# ==========================================================================
# m6433
# ==========================================================================


@power(
    "m6433a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 7, kind=MINION),
)
def m6433a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if has_combat_advantage(c.world, c.me, c.target):
            c.flat(2)


@power(
    "m6433a1",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
    trigger="the m6433 drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m6433a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m6444
# ==========================================================================


@power(
    "m6444a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 6, kind=MINION),
)
def m6444a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m6444a1",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=10),
)
def m6444a1(c: Cast) -> None:
    """"Escape DC 16" has nowhere to go -- the engine ends this on a save,
    not a skill contest."""
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m949
# ==========================================================================


@power(
    "m949a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 5, kind=MINION),
)
def m949a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m962
# ==========================================================================


@power(
    "m962a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 4, kind=MINION),
)
def m962a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m962a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
)
def m962a1(c: Cast) -> None:
    """"A blade of m962's basic attack" names itself -- read as "it"."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None:
            return
        known = c.world.get(me, Powers)
        if known is None or ev.power != known.basic:
            return
        extra = len(
            [a for a in c.allies() if _ref_of(c, a) == "m962" and c.adjacent_to(a, ev.target)]
        )
        if extra:
            c.flat(extra, dtype=DamageType.COLD, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m962a2",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m962a2(c: Cast) -> None:
    c.teleport(5)
